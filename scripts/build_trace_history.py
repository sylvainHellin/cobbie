"""Reconstruct full agent trace histories from a factorial cell's results.sqlite.

Renders each CodeAct run as LLM-readable markdown for qualitative open-coding of
agentic-search behaviour (what the agent did to find / compute the answer, or
what went wrong):

  - header: cell_id, model, paradigm, tools, question_id, repeat_idx, project,
    category, num_iterations, num_tool_calls, verdict, abstention
  - SYSTEM PROMPT (full; the agent's standing instructions)
  - QUESTION prompt
  - ordered CodeAct steps: "Generated code" (fenced) + "Observation" (truncated)
  - final PREDICTED answer
  - REFERENCE answer (ground truth)
  - JUDGE verdict and reasoning (classification + justification)

So the system prompt comes first and the ground truth + judge come AFTER the
full trace, matching the open-coding prompt layout (context, then trace +
ground truth + judge, then the coding instruction).

When an instruction template is bundled (``--instruction``) it sandwiches the
trace: a context preamble before, the coding task after. If the template
contains the literal token ``{{TRACE}}`` the reconstructed trace block replaces
that token (context-before / instruction-after); otherwise the instruction is
prepended as a fallback.

Question text + ground truth are NOT stored in the cell sqlite, and the live
dataset (``db.db``) has drifted since the runs, so they are recovered from the
frozen run-time judge batches (``judge_batch_*.jsonl`` next to the cell dir),
keyed by ``cell_id|question_id|repeat_idx``. project and category come from the
frozen results row. The agent system prompt is read from
``run_metadata.system_prompt``.

Usage:
    # single question -> one markdown file under the out dir
    uv run python scripts/build_trace_history.py \
        --db outputs/factorial/minimax-m3__agentic__none/results.sqlite \
        --question-id 16 --out /tmp/traces

    # seeded stratified sample (n per verdict)
    uv run python scripts/build_trace_history.py \
        --db outputs/factorial/minimax-m3__agentic__none/results.sqlite \
        --sample --strata correct,wrong --n 5 --seed 7 --out /tmp/traces

    # bundle a coding instruction (ready-to-send prompt) and run through minimax
    uv run python scripts/build_trace_history.py \
        --db outputs/factorial/minimax-m3__agentic__none/results.sqlite \
        --sample --strata correct,wrong --n 5 \
        --instruction prompts/open_coding.md --out /tmp/traces \
        --run --coder-model minimax-anthropic:MiniMax-M3

    # collect every trace into one JSONL instead of per-file markdown
    uv run python scripts/build_trace_history.py --db ... --sample --strata wrong \
        --n 40 --jsonl /tmp/wrong_traces.jsonl

Every sqlite is opened read-only (uri mode=ro) so a live run_cell.py writer is
never locked.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import sqlite3
import sys
from typing import Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS_DIR)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ----------------------------------------------------------------------
# sqlite reads (read-only; never lock a live writer)
# ----------------------------------------------------------------------
def _connect_ro(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_run_metadata(db_path: str) -> dict:
    conn = _connect_ro(db_path)
    try:
        row = conn.execute("SELECT * FROM run_metadata LIMIT 1").fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def load_result_rows(db_path: str) -> list[dict]:
    conn = _connect_ro(db_path)
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM results ORDER BY question_id, repeat_idx"
            ).fetchall()
        ]
    finally:
        conn.close()


def load_result_row(
    db_path: str, question_id: int, repeat_idx: Optional[int]
) -> dict:
    conn = _connect_ro(db_path)
    try:
        if repeat_idx is None:
            row = conn.execute(
                "SELECT * FROM results WHERE question_id = ? "
                "ORDER BY repeat_idx LIMIT 1",
                (question_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM results WHERE question_id = ? AND repeat_idx = ?",
                (question_id, repeat_idx),
            ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def load_steps(db_path: str, question_id: int, repeat_idx: int) -> list[dict]:
    conn = _connect_ro(db_path)
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT step_idx, generated_code, observation FROM steps "
                "WHERE question_id = ? AND repeat_idx = ? ORDER BY step_idx",
                (question_id, repeat_idx),
            ).fetchall()
        ]
    finally:
        conn.close()


# ----------------------------------------------------------------------
# question + ground truth recovery (frozen run-time judge batches)
#
# The live dataset (db.db) drifted after the runs, so joining it by question_id
# attaches the wrong question/reference. The faithful question + reference are
# frozen in the run-time judge batches next to each cell dir, keyed by
# cell_id|question_id|repeat_idx.
# ----------------------------------------------------------------------
_Q_RE = re.compile(r"\nQUESTION:\s*(.*?)\n\nREFERENCE ANSWER:", re.DOTALL)
_REF_RE = re.compile(
    r"\nREFERENCE ANSWER:\s*(.*?)\n\n(?:Note:|SYSTEM RESPONSE:|## )", re.DOTALL
)


def _parse_judge_text(text: str) -> dict:
    """Pull the frozen QUESTION and REFERENCE ANSWER from a judge prompt."""
    q = _Q_RE.search(text)
    ref = _REF_RE.search(text)
    return {
        "question": q.group(1).strip() if q else None,
        "ground_truth": ref.group(1).strip() if ref else None,
    }


def load_question_index(db_path: str) -> dict[tuple, dict]:
    """Map (cell_id, question_id, repeat_idx) -> {question, ground_truth}.

    Sourced from the frozen run-time judge batches next to the cell dir
    (``outputs/<run>/judge_batch_*.jsonl``), not the drifted live dataset.
    """
    judge_dir = os.path.dirname(os.path.dirname(os.path.abspath(db_path)))
    index: dict[tuple, dict] = {}
    for path in sorted(glob.glob(os.path.join(judge_dir, "judge_batch_*.jsonl"))):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = rec.get("key")
                if not key or "|" not in key:
                    continue
                cell_id, qid, ridx = key.split("|")
                try:
                    text = rec["request"]["contents"][0]["parts"][0]["text"]
                except (KeyError, IndexError, TypeError):
                    continue
                index[(cell_id, int(qid), int(ridx))] = _parse_judge_text(text)
    return index


# ----------------------------------------------------------------------
# rendering
# ----------------------------------------------------------------------
def truncate_observation(text: Optional[str], cap: int) -> str:
    """Head+tail truncation with an elision marker; observations only."""
    if text is None:
        return ""
    if cap <= 0 or len(text) <= cap:
        return text
    head = int(cap * 0.6)
    tail = cap - head
    removed = len(text) - head - tail
    return (
        text[:head]
        + f"\n\n...[{removed} chars elided]...\n\n"
        + text[-tail:]
    )


TRACE_TOKEN = "{{TRACE}}"


def render_trace_block(
    meta: dict,
    info: dict,
    row: dict,
    steps: list[dict],
    obs_cap: int,
    sysprompt_cap: int,
) -> str:
    """Render the reconstructed trace block (no instruction).

    Order: header -> system prompt -> question -> steps -> predicted answer ->
    ground truth -> judge verdict and reasoning.
    """
    parts: list[str] = []
    verdict = (row.get("classification") or "unknown").lower()

    # 1. header (machine-readable anchor; the instruction references these)
    parts.append(
        "# Agent trace\n\n"
        f"- cell_id: {meta.get('cell_id')}\n"
        f"- model: {meta.get('model')}\n"
        f"- paradigm: {meta.get('paradigm')}\n"
        f"- tools: {meta.get('tools')}\n"
        f"- question_id: {row.get('question_id')}\n"
        f"- repeat_idx: {row.get('repeat_idx')}\n"
        f"- project: {row.get('project')}\n"
        f"- category: {row.get('category')}\n"
        f"- num_iterations: {row.get('num_iterations')}\n"
        f"- num_tool_calls: {row.get('num_tool_calls')}\n"
        f"- status: {row.get('status')}\n"
        f"- verdict: {verdict}\n"
        f"- abstention: {row.get('abstention')}\n"
    )

    # 2. system prompt (full by default; sysprompt_cap <= 0 means no truncation)
    sysprompt = meta.get("system_prompt")
    if sysprompt:
        sp = truncate_observation(str(sysprompt), sysprompt_cap)
        parts.append("\n## System prompt\n\n```\n" + sp.rstrip() + "\n```")
    else:
        parts.append("\n## System prompt\n\n_(not recorded in run_metadata)_")

    # 3. question (the agent's task)
    parts.append("\n## Question\n\n" + str(info.get("question", "")).strip())

    # 4. ordered CodeAct steps
    parts.append("\n## CodeAct transcript\n")
    if not steps:
        parts.append("\n_(no steps recorded)_\n")
    for s in steps:
        idx = s.get("step_idx")
        code = s.get("generated_code") or ""
        obs = truncate_observation(s.get("observation"), obs_cap)
        parts.append(f"\n### Step {idx}\n")
        parts.append("\nGenerated code:\n\n```python\n" + code.rstrip() + "\n```")
        parts.append("\n\nObservation:\n\n```\n" + obs.rstrip() + "\n```")

    # 5. final predicted answer
    parts.append(
        "\n## Final predicted answer\n\n" + str(row.get("predicted", "")).strip()
    )

    # 6. ground truth
    parts.append(
        "\n## Reference answer (ground truth)\n\n"
        + str(info.get("ground_truth", "")).strip()
    )

    # 7. judge verdict and reasoning
    judge = f"verdict: {verdict}"
    just = row.get("justification")
    if just:
        judge += "\n\n" + str(just).strip()
    parts.append("\n## Judge verdict and reasoning\n\n" + judge + "\n")

    return "\n".join(parts)


def assemble_prompt(trace_block: str, instruction: Optional[str]) -> str:
    """Bundle a trace block with an instruction template.

    If the template contains ``{{TRACE}}`` the block is injected there
    (context-before / instruction-after). Otherwise the instruction is
    prepended as a fallback. With no instruction, the block is returned as-is.
    """
    if not instruction:
        return trace_block
    if TRACE_TOKEN in instruction:
        return instruction.replace(TRACE_TOKEN, trace_block)
    return instruction.rstrip() + "\n\n---\n\n" + trace_block


# ----------------------------------------------------------------------
# selection
# ----------------------------------------------------------------------
def select_sample(
    rows: list[dict], strata: list[str], n: int, seed: int
) -> list[tuple[int, int]]:
    """Return [(question_id, repeat_idx)] sampled n per verdict stratum."""
    rng = random.Random(seed)
    picked: list[tuple[int, int]] = []
    for stratum in strata:
        pool = [
            r
            for r in rows
            if (r.get("classification") or "").lower() == stratum.lower()
        ]
        rng.shuffle(pool)
        for r in pool[:n]:
            picked.append((r["question_id"], r["repeat_idx"]))
    return picked


# ----------------------------------------------------------------------
# optional coder run via the cobbie LLM client
# ----------------------------------------------------------------------
def run_coder(prompt: str, coder_model: str) -> str:
    """Send an assembled prompt through the cobbie LLM client and return text."""
    from src.harness.llm import init_llm

    llm = init_llm(coder_model, temperature=0)
    resp = llm.invoke(prompt)
    content = getattr(resp, "content", resp)
    if isinstance(content, list):  # some providers return content blocks
        content = "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content)


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="path to a cell results.sqlite")
    ap.add_argument("--question-id", type=int, help="single question id")
    ap.add_argument(
        "--repeat-idx",
        type=int,
        default=None,
        help="repeat index (default: lowest available)",
    )
    ap.add_argument(
        "--sample", action="store_true", help="stratified sample selection"
    )
    ap.add_argument(
        "--strata",
        default="correct,wrong,abstained",
        help="comma list of verdict strata to sample",
    )
    ap.add_argument("--n", type=int, default=10, help="n per stratum")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--obs-cap", type=int, default=2000, help="chars per observation")
    ap.add_argument(
        "--sysprompt-cap",
        type=int,
        default=0,
        help="chars for the system prompt (0 = full, no truncation)",
    )
    ap.add_argument("--out", help="output dir (one .md per trace)")
    ap.add_argument("--jsonl", help="collect all traces into one JSONL file")
    ap.add_argument(
        "--instruction",
        help=(
            "bundle this file as the coding instruction. If it contains the "
            "token {{TRACE}}, the trace block replaces that token "
            "(context-before / instruction-after); otherwise it is prepended."
        ),
    )
    ap.add_argument("--run", action="store_true", help="run prompts through a coder LLM")
    ap.add_argument("--coder-model", default="minimax-anthropic:MiniMax-M3")
    args = ap.parse_args()

    if not args.out and not args.jsonl:
        ap.error("provide --out DIR or --jsonl PATH")
    if not args.question_id and not args.sample:
        ap.error("provide --question-id or --sample")
    if args.run and not args.instruction:
        ap.error("--run needs --instruction (the coder needs a task)")

    instruction = None
    if args.instruction:
        with open(args.instruction, encoding="utf-8") as fh:
            instruction = fh.read()

    meta = load_run_metadata(args.db)
    qindex = load_question_index(args.db)
    cell_id = meta.get("cell_id")

    if args.question_id:
        targets = [(args.question_id, args.repeat_idx)]
    else:
        rows = load_result_rows(args.db)
        strata = [s.strip() for s in args.strata.split(",") if s.strip()]
        targets = select_sample(rows, strata, args.n, args.seed)

    if args.out:
        os.makedirs(args.out, exist_ok=True)
    jsonl_fh = open(args.jsonl, "w", encoding="utf-8") if args.jsonl else None

    written = 0
    for qid, ridx in targets:
        row = load_result_row(args.db, qid, ridx)
        if not row:
            print(f"  skip q{qid} r{ridx}: no results row", file=sys.stderr)
            continue
        ridx_actual = row["repeat_idx"]
        steps = load_steps(args.db, qid, ridx_actual)
        info = qindex.get((cell_id, qid, ridx_actual))
        if info is None:
            print(
                f"  WARN q{qid} r{ridx_actual}: no judge-batch entry for "
                f"cell {cell_id}; question/reference unavailable",
                file=sys.stderr,
            )
            info = {
                "question": "_(question unavailable: no judge-batch entry)_",
                "ground_truth": "_(reference unavailable: no judge-batch entry)_",
            }
        verdict = (row.get("classification") or "unknown").lower()
        trace_block = render_trace_block(
            meta, info, row, steps, args.obs_cap, args.sysprompt_cap
        )
        trace_md = assemble_prompt(trace_block, instruction)

        response = None
        if args.run:
            response = run_coder(trace_md, args.coder_model)

        if args.out:
            stem = f"q{qid}_r{ridx_actual}_{verdict}"
            with open(
                os.path.join(args.out, stem + ".md"), "w", encoding="utf-8"
            ) as fh:
                fh.write(trace_md)
            if response is not None:
                with open(
                    os.path.join(args.out, stem + ".response.md"),
                    "w",
                    encoding="utf-8",
                ) as fh:
                    fh.write(response)
        if jsonl_fh:
            rec = {
                "question_id": qid,
                "repeat_idx": ridx_actual,
                "verdict": verdict,
                "category": row.get("category"),
                "project": row.get("project"),
                "trace": trace_md,
            }
            if response is not None:
                rec["response"] = response
            jsonl_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        written += 1
        print(f"  wrote q{qid} r{ridx_actual} [{verdict}] ({len(steps)} steps)")

    if jsonl_fh:
        jsonl_fh.close()
    print(f"done: {written} trace(s)")


if __name__ == "__main__":
    main()
