"""Factorial cell runner: one (model x paradigm x tools) cell to one sqlite.

Owns exactly one cell of the AUTCON-revision factorial and one
``outputs/factorial/<cell_id>/results.sqlite`` (single writer, WAL mode). Runs
the cell's questions concurrently against a pool of agents (one persistent
Jupyter kernel each), with bounded exponential backoff on provider rate limits,
per-question error isolation, and resume.

This runner only produces transcripts and accounting. It computes no answer
correctness -- the Gemini judge (milestone 4) writes ``classification`` back
into the rows later.

Usage:
    uv run python scripts/run_cell.py \
        --model minimax-anthropic:MiniMax-M3 --paradigm agentic --tools none \
        --question-set dev-mini [--limit N] [--question-ids 1 2 3] [--repeats k]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import queue
import random
import sqlite3
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from src.config import ROOT_PATH
from src.db.dev_mini import dev_midi_subset, dev_mini_subset
from src.db.load_dataset import TESTSET
from src.harness.agent import AgentResult, create_ifc_agent, run_question

# Backoff envelope for provider rate limits / quota. Base 2s, doubling, capped
# at ~18 min per wait, with full jitter so a fleet of cells does not resynchronize.
_BACKOFF_BASE_S = 2.0
_BACKOFF_CEILING_S = 18 * 60
_BACKOFF_MAX_ATTEMPTS = 12

_RATE_LIMIT_MARKERS = (
    "429",
    "rate limit",
    "rate_limit",
    "ratelimit",
    "quota",
    "too many requests",
    "overloaded",
    "resource_exhausted",
    "resource exhausted",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT_PATH,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _resolve_ifc(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(ROOT_PATH, path)


# Explicit model-id -> short slug map. Prefer adding an entry here over the
# brittle string transform so each backbone gets a clean, stable cell-dir name
# (e.g. future GLM models map to glm-4.6 rather than glm-z-ai-GLM-4-6).
_MODEL_SLUGS = {
    "minimax-anthropic:MiniMax-M3": "minimax-m3",
    "minimax:MiniMax-M3": "minimax-m3",
    "glm:glm-5.2": "glm-5.2",
    "glm:glm-4.5-air": "glm-4.5-air",
}


def _model_slug(model: str) -> str:
    if model in _MODEL_SLUGS:
        return _MODEL_SLUGS[model]
    return model.replace(":", "-").replace("/", "-")


def _cell_id(model: str, paradigm: str, tools: str) -> str:
    return f"{_model_slug(model)}__{paradigm}__{tools}"


def _is_rate_limit(exc: BaseException) -> bool:
    """Heuristic: does this exception look like a 429 / quota / overload?"""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _RATE_LIMIT_MARKERS)


# ----------------------------------------------------------------------
# Trace -> steps mapping
# ----------------------------------------------------------------------


def _extract_steps(trace: list[dict]) -> list[tuple[int, str, str]]:
    """Pair each generated code block with its following observation.

    Walks the AgentResult trace linearly. Assistant ``tool_calls`` contribute
    their ``args['code']`` to a FIFO queue; each tool-role entry consumes the
    oldest unmatched code and emits one ``(step_idx, code, observation)`` row.
    Any trailing tool call with no observation (e.g. truncated at the recursion
    guard) still emits a row with an empty observation so the transcript is
    complete. step_idx is 0-based per question.
    """
    pending_codes: list[str] = []
    steps: list[tuple[int, str, str]] = []
    step_idx = 0
    for entry in trace:
        role = entry.get("role")
        if role == "assistant":
            for tc in entry.get("tool_calls", []):
                pending_codes.append(tc.get("args", {}).get("code", "") or "")
        elif role == "tool":
            observation = entry.get("content", "") or ""
            code = pending_codes.pop(0) if pending_codes else ""
            steps.append((step_idx, code, observation))
            step_idx += 1
    for code in pending_codes:
        steps.append((step_idx, code, ""))
        step_idx += 1
    return steps


def _count_iterations(trace: list[dict]) -> int:
    """Count assistant tool-call steps (CodeAct iterations)."""
    return sum(
        1 for entry in trace if entry.get("role") == "assistant" and entry.get("tool_calls")
    )


# ----------------------------------------------------------------------
# SQLite store (single writer, WAL)
# ----------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    question_id        INTEGER NOT NULL,
    repeat_idx         INTEGER NOT NULL,
    project            TEXT,
    category           INTEGER,
    predicted          TEXT,
    input_tokens       INTEGER,
    cached_input_tokens INTEGER,
    output_tokens      INTEGER,
    latency_s          REAL,
    num_tool_calls     INTEGER,
    num_iterations     INTEGER,
    status             TEXT,
    retry_count        INTEGER,
    error              TEXT,
    classification     TEXT,
    created_at         TEXT,
    PRIMARY KEY (question_id, repeat_idx)
);

CREATE TABLE IF NOT EXISTS steps (
    question_id     INTEGER NOT NULL,
    repeat_idx      INTEGER NOT NULL,
    step_idx        INTEGER NOT NULL,
    generated_code  TEXT,
    observation     TEXT,
    PRIMARY KEY (question_id, repeat_idx, step_idx)
);

CREATE TABLE IF NOT EXISTS run_metadata (
    git_sha             TEXT,
    system_prompt       TEXT,
    system_prompt_hash  TEXT,
    model               TEXT,
    paradigm            TEXT,
    tools               TEXT,
    cell_id             TEXT,
    concurrency         INTEGER,
    recursion_limit     INTEGER,
    question_set        TEXT,
    started_at          TEXT,
    finished_at         TEXT
);
"""


class CellStore:
    """Single-writer sqlite store for one factorial cell."""

    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()

    def terminal_state(self) -> dict[tuple[int, int], tuple[str, int]]:
        """Map (question_id, repeat_idx) -> (status, retry_count) for resume."""
        cur = self._conn.execute(
            "SELECT question_id, repeat_idx, status, retry_count FROM results"
        )
        out: dict[tuple[int, int], tuple[str, int]] = {}
        for qid, ridx, status, retry in cur.fetchall():
            out[(qid, ridx)] = (status, retry or 0)
        return out

    def write_metadata(self, meta: dict) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM run_metadata")
            self._conn.execute(
                """
                INSERT INTO run_metadata (
                    git_sha, system_prompt, system_prompt_hash, model, paradigm,
                    tools, cell_id, concurrency, recursion_limit, question_set,
                    started_at, finished_at
                ) VALUES (
                    :git_sha, :system_prompt, :system_prompt_hash, :model, :paradigm,
                    :tools, :cell_id, :concurrency, :recursion_limit, :question_set,
                    :started_at, :finished_at
                )
                """,
                meta,
            )
            self._conn.commit()

    def set_finished(self, finished_at: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE run_metadata SET finished_at = ?", (finished_at,)
            )
            self._conn.commit()

    def write_result(self, result_row: dict, step_rows: list[tuple]) -> None:
        """Write one results row and its steps rows in a single transaction."""
        with self._lock:
            qid = result_row["question_id"]
            ridx = result_row["repeat_idx"]
            self._conn.execute(
                "DELETE FROM steps WHERE question_id = ? AND repeat_idx = ?",
                (qid, ridx),
            )
            self._conn.execute(
                """
                INSERT OR REPLACE INTO results (
                    question_id, repeat_idx, project, category, predicted,
                    input_tokens, cached_input_tokens, output_tokens, latency_s,
                    num_tool_calls, num_iterations, status, retry_count, error,
                    classification, created_at
                ) VALUES (
                    :question_id, :repeat_idx, :project, :category, :predicted,
                    :input_tokens, :cached_input_tokens, :output_tokens, :latency_s,
                    :num_tool_calls, :num_iterations, :status, :retry_count, :error,
                    :classification, :created_at
                )
                """,
                result_row,
            )
            if step_rows:
                self._conn.executemany(
                    """
                    INSERT OR REPLACE INTO steps (
                        question_id, repeat_idx, step_idx, generated_code, observation
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    step_rows,
                )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# ----------------------------------------------------------------------
# Question selection
# ----------------------------------------------------------------------


def _select_questions(args) -> list:
    if args.question_ids:
        wanted = set(args.question_ids)
        questions = [q for q in TESTSET if q.id in wanted]
    elif args.question_set == "dev-mini":
        questions = dev_mini_subset(TESTSET)
    elif args.question_set == "dev-midi":
        questions = dev_midi_subset(TESTSET)
    else:
        questions = list(TESTSET)
    questions.sort(key=lambda q: q.id)
    if args.limit is not None:
        questions = questions[: args.limit]
    return questions


# ----------------------------------------------------------------------
# Agent pool + execution
# ----------------------------------------------------------------------


def _run_with_backoff(
    agent,
    interp,
    *,
    ifc_path: str,
    question: str,
    tools: bool,
    recursion_limit: int,
) -> AgentResult:
    """Call run_question with bounded exponential backoff on rate limits."""
    attempt = 0
    while True:
        try:
            return run_question(
                agent,
                interp,
                ifc_path=ifc_path,
                question=question,
                tools=tools,
                recursion_limit=recursion_limit,
            )
        except Exception as exc:  # noqa: BLE001
            if _is_rate_limit(exc) and attempt < _BACKOFF_MAX_ATTEMPTS:
                wait = min(_BACKOFF_BASE_S * (2 ** attempt), _BACKOFF_CEILING_S)
                wait = random.uniform(0, wait)
                print(
                    f"  [backoff] rate limit ({type(exc).__name__}); "
                    f"attempt {attempt + 1}/{_BACKOFF_MAX_ATTEMPTS}, "
                    f"sleeping {wait:.1f}s",
                    flush=True,
                )
                time.sleep(wait)
                attempt += 1
                continue
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="prefixed model id")
    parser.add_argument(
        "--paradigm", required=True, choices=["static", "agentic"]
    )
    parser.add_argument("--tools", required=True, choices=["none", "tools"])
    parser.add_argument(
        "--question-set", default="dev-mini", choices=["dev-mini", "dev-midi", "full"]
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--question-ids", type=int, nargs="+", default=None)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--recursion-limit", type=int, default=120)
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="per-question error-row retry cap across reruns",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help=(
            "Base output directory under which <cell_id>/results.sqlite is "
            "written. Defaults to outputs/factorial. Use a separate base "
            "(e.g. outputs/factorial_rerun_YYYYMMDD) to avoid touching "
            "existing results."
        ),
    )
    args = parser.parse_args()

    static = args.paradigm == "static"
    use_tools = args.tools == "tools"
    cell_id = _cell_id(args.model, args.paradigm, args.tools)
    base_dir = args.out_dir or os.path.join(ROOT_PATH, "outputs", "factorial")
    out_dir = os.path.join(base_dir, cell_id)
    db_path = os.path.join(out_dir, "results.sqlite")

    questions = _select_questions(args)
    if not questions:
        print("No questions selected; nothing to do.")
        return

    store = CellStore(db_path)
    terminal = store.terminal_state()

    # Build the task list (question, repeat_idx, prior_retry_count), skipping
    # done work and error rows that have exhausted their retry budget.
    tasks: list[tuple] = []
    skipped_done = 0
    skipped_exhausted = 0
    for q in questions:
        for ridx in range(args.repeats):
            key = (q.id, ridx)
            prior = terminal.get(key)
            if prior is not None:
                status, retry = prior
                if status == "done":
                    skipped_done += 1
                    continue
                if status == "error" and retry >= args.max_retries:
                    skipped_exhausted += 1
                    continue
                tasks.append((q, ridx, retry))
            else:
                tasks.append((q, ridx, 0))

    print(
        f"cell={cell_id}\n"
        f"db={db_path}\n"
        f"questions={len(questions)} repeats={args.repeats} "
        f"tasks={len(tasks)} skipped_done={skipped_done} "
        f"skipped_exhausted={skipped_exhausted}",
        flush=True,
    )

    if not tasks:
        store.set_finished(_now_iso())
        store.close()
        print("Nothing to run (all done or exhausted).")
        return

    # Agent pool: one persistent kernel per slot. Cap at the number of tasks so
    # a tiny run does not spin up unused kernels. The static system prompt is
    # identical across all pooled agents, so prompt-caching holds.
    pool_size = max(1, min(args.concurrency, len(tasks)))
    print(f"Building agent pool (size={pool_size})...", flush=True)
    pool: queue.Queue = queue.Queue()
    agents: list[tuple] = []
    for _ in range(pool_size):
        agent, interp = create_ifc_agent(
            args.model, static=static, tools=use_tools, max_retries=args.max_retries
        )
        agents.append((agent, interp))
        pool.put((agent, interp))

    system_prompt = agents[0][0]._system_prompt
    store.write_metadata(
        {
            "git_sha": _git_sha(),
            "system_prompt": system_prompt,
            "system_prompt_hash": hashlib.sha256(
                system_prompt.encode("utf-8")
            ).hexdigest(),
            "model": args.model,
            "paradigm": args.paradigm,
            "tools": args.tools,
            "cell_id": cell_id,
            "concurrency": args.concurrency,
            "recursion_limit": args.recursion_limit,
            "question_set": args.question_set,
            "started_at": _now_iso(),
            "finished_at": "",
        }
    )

    def _worker(task):
        q, ridx, prior_retry = task
        agent, interp = pool.get()
        ifc_path = _resolve_ifc(q.ifc.model_path)
        try:
            res = _run_with_backoff(
                agent,
                interp,
                ifc_path=ifc_path,
                question=q.question,
                tools=use_tools,
                recursion_limit=args.recursion_limit,
            )
            return task, res, None
        except Exception as exc:  # noqa: BLE001
            return task, None, exc
        finally:
            pool.put((agent, interp))

    done = 0
    errors = 0
    try:
        with ThreadPoolExecutor(max_workers=pool_size) as executor:
            futures = [executor.submit(_worker, t) for t in tasks]
            for fut in as_completed(futures):
                task, res, exc = fut.result()
                q, ridx, prior_retry = task
                project = q.ifc.project_name if q.ifc else None
                if exc is None and res is not None:
                    step_rows = [
                        (q.id, ridx, s_idx, code, obs)
                        for (s_idx, code, obs) in _extract_steps(res.trace)
                    ]
                    store.write_result(
                        {
                            "question_id": q.id,
                            "repeat_idx": ridx,
                            "project": project,
                            "category": q.category,
                            "predicted": res.answer,
                            "input_tokens": res.input_tokens,
                            "cached_input_tokens": res.cached_input_tokens,
                            "output_tokens": res.output_tokens,
                            "latency_s": res.elapsed_s,
                            "num_tool_calls": res.num_tool_calls,
                            "num_iterations": _count_iterations(res.trace),
                            "status": "done",
                            "retry_count": prior_retry,
                            "error": None,
                            "classification": None,
                            "created_at": _now_iso(),
                        },
                        step_rows,
                    )
                    done += 1
                    print(
                        f"  [done] q={q.id} r={ridx} "
                        f"tool_calls={res.num_tool_calls} "
                        f"in={res.input_tokens} cached={res.cached_input_tokens} "
                        f"out={res.output_tokens} t={res.elapsed_s}s",
                        flush=True,
                    )
                else:
                    store.write_result(
                        {
                            "question_id": q.id,
                            "repeat_idx": ridx,
                            "project": project,
                            "category": q.category,
                            "predicted": None,
                            "input_tokens": 0,
                            "cached_input_tokens": 0,
                            "output_tokens": 0,
                            "latency_s": 0.0,
                            "num_tool_calls": 0,
                            "num_iterations": 0,
                            "status": "error",
                            "retry_count": prior_retry + 1,
                            "error": f"{type(exc).__name__}: {exc}",
                            "classification": None,
                            "created_at": _now_iso(),
                        },
                        [],
                    )
                    errors += 1
                    print(
                        f"  [error] q={q.id} r={ridx} "
                        f"retry_count={prior_retry + 1} "
                        f"{type(exc).__name__}: {exc}",
                        flush=True,
                    )
    finally:
        store.set_finished(_now_iso())
        for _, interp in agents:
            interp.shutdown()
        store.close()

    print(f"\nFinished cell={cell_id}: done={done} errors={errors}", flush=True)


if __name__ == "__main__":
    main()
