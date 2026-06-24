"""Multi-cell batch judge driver for the AUTCON-revision factorial.

Thin orchestration layer over ``scripts/judge.py`` (the canonical Gemini
LLM-as-judge). This driver does NOT reimplement the prompt, the output schema,
the batch-key encoding, the JSONL build, the upload/create, or the sqlite
write-back: all of that lives in ``judge.py`` and is either invoked through a
subprocess (the submit API work) or imported and reused (the per-row routing
helpers used during collect).

What the driver owns:

  * cell enumeration (reuses ``judge.enumerate_cells``)
  * one Gemini Batch API job PER CELL (``--one-job`` overrides to combined)
  * a polling loop with retry/backoff around the Batch SDK calls (fix #1)
  * an assertion gate before any job is marked collected (fix #2)
  * a per-cell classification distribution summary (markdown + stdout)
  * resume-safety: re-running picks up where it left off

Resume story (always safe to relaunch):
  The driver reads the same state file ``judge.py`` uses
  (``outputs/factorial/judge_batch_jobs.json``). On ``--phase all`` it submits a
  job only for cells that have no uncollected job in state, then polls and
  collects every uncollected job. Already-classified rows are skipped by
  ``judge.py``'s write-back (``classification IS NULL`` guard); collected jobs
  are never re-polled. The driver is the single writer of state and sqlite
  during its run (submit runs as a subprocess that finishes before the
  in-process collect begins), so there is never concurrent sqlite access.

Usage:
    uv run python scripts/judge_batch.py --dry-run
    uv run python scripts/judge_batch.py --cells all
    uv run python scripts/judge_batch.py --cells '*static*'
    uv run python scripts/judge_batch.py --cells a,b,c --phase submit
    uv run python scripts/judge_batch.py --phase collect
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Callable, Optional

# Import judge.py as a module so we reuse its canonical helpers (schema, keys,
# routing, write-back, state IO) instead of reimplementing them.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judge  # noqa: E402

from src.config import ROOT_PATH  # noqa: E402

# TODO(cat4-sensitivity): not implemented

# ----------------------------------------------------------------------
# Optional transient-error types for the retry/backoff helper (fix #1)
# ----------------------------------------------------------------------

try:
    import httpx as _httpx
except Exception:  # noqa: BLE001
    _httpx = None

try:
    from google.genai import errors as _genai_errors
except Exception:  # noqa: BLE001
    _genai_errors = None

# google.api_core is named in the spec but is not installed in this venv (the
# google-genai SDK raises google.genai.errors.* instead). Import it defensively
# so the *Retryable* / ServiceUnavailable types are honoured if it ever appears.
try:
    from google.api_core import exceptions as _api_core  # type: ignore
except Exception:  # noqa: BLE001
    _api_core = None


# Batch-job lifecycle states (mirror the local sets in judge.run_batch_collect).
_TERMINAL_FAILURE = {
    "JOB_STATE_FAILED",
    "JOB_STATE_EXPIRED",
    "JOB_STATE_CANCELLED",
}
_READABLE = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_PARTIALLY_SUCCEEDED",
}


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}] {msg}", flush=True)


# ----------------------------------------------------------------------
# Cell resolution
# ----------------------------------------------------------------------


def _cell_id(db_path: str) -> str:
    return os.path.basename(os.path.dirname(db_path))


def resolve_cells(cells_arg: str) -> list[tuple[str, str]]:
    """Resolve --cells (glob | comma-list | 'all') to sorted (cell_id, db_path).

    Reuses ``judge.enumerate_cells`` for every token so the glob semantics match
    judge.py exactly. Deduplicated and stable-sorted by cell_id.
    """
    tokens: list[Optional[str]]
    if cells_arg.strip().lower() == "all":
        tokens = [None]
    elif "," in cells_arg:
        tokens = [t.strip() for t in cells_arg.split(",") if t.strip()]
    else:
        tokens = [cells_arg.strip()]

    seen: dict[str, str] = {}
    for tok in tokens:
        for db_path in judge.enumerate_cells(tok):
            seen[_cell_id(db_path)] = db_path
    return sorted(seen.items())


# ----------------------------------------------------------------------
# Read-only sqlite counters (the only direct sqlite access the driver does)
# ----------------------------------------------------------------------


def _ro_conn(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def _cell_model(db_path: str) -> Optional[str]:
    conn = _ro_conn(db_path)
    try:
        row = conn.execute("SELECT model FROM run_metadata LIMIT 1").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _count_plan(db_path: str) -> dict:
    """Read-only counts for dry-run / summary. Never opens a JudgeStore."""
    conn = _ro_conn(db_path)
    try:
        total = conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
        already = conn.execute(
            "SELECT COUNT(*) FROM results WHERE classification IS NOT NULL"
        ).fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM results WHERE classification IS NULL"
        ).fetchone()[0]
        judgeable = conn.execute(
            "SELECT COUNT(*) FROM results "
            "WHERE classification IS NULL AND status = 'done' "
            "AND TRIM(COALESCE(predicted, '')) != ''"
        ).fetchone()[0]
        return {
            "total": total,
            "already_classified": already,
            "pending": pending,
            "rows_to_judge": judgeable,
            "rows_to_error_short_circuit": pending - judgeable,
        }
    finally:
        conn.close()


def _distribution(db_path: str) -> dict:
    conn = _ro_conn(db_path)
    try:
        dist = {"correct": 0, "wrong": 0, "abstained": 0, "error": 0}
        for cls, n in conn.execute(
            "SELECT classification, COUNT(*) FROM results "
            "WHERE classification IS NOT NULL GROUP BY classification"
        ):
            if cls in dist:
                dist[cls] = n
        return dist
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Self-judge guard (fix I): pre-flight before any API call
# ----------------------------------------------------------------------


def preflight_self_judge_guard(cells: list[tuple[str, str]]) -> None:
    for cell_id, db_path in cells:
        model = _cell_model(db_path)
        if judge._bare_model_id(model) == judge.JUDGE_MODEL:
            raise SystemExit(
                f"self-judge guard: cell {cell_id!r} run model {model!r} equals "
                f"judge model {judge.JUDGE_MODEL!r}; refusing to judge a model "
                f"with itself. Fix the offending cell before re-running."
            )


# ----------------------------------------------------------------------
# State helpers
# ----------------------------------------------------------------------


def _entry_cell_ids(entry: dict) -> set[str]:
    """Cell ids covered by a state entry, derived from its persisted keys."""
    ids: set[str] = set()
    for key in entry.get("keys", []):
        try:
            cid, _qid, _ridx = judge._parse_batch_key(key)
            ids.add(cid)
        except Exception:  # noqa: BLE001
            continue
    return ids


def _uncollected_entries(state: list[dict]) -> list[dict]:
    return [e for e in state if not e.get("collected")]


# ----------------------------------------------------------------------
# Retry/backoff around the Batch SDK calls (fix #1)
# ----------------------------------------------------------------------


def _is_transient(exc: Exception) -> bool:
    """True for transient errors that warrant a backoff retry.

    Retries: ConnectionError / TimeoutError / OSError, httpx transport errors,
    google-genai ServerError (5xx) and 429, and google.api_core *Retryable* /
    ServiceUnavailable / DeadlineExceeded if that package is present. Does NOT
    retry non-429 4xx (ClientError), which are not retryable.
    """
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        return True
    if _httpx is not None and isinstance(exc, _httpx.TransportError):
        return True
    if _genai_errors is not None:
        if isinstance(exc, _genai_errors.ServerError):
            return True
        if isinstance(exc, _genai_errors.APIError):
            code = getattr(exc, "code", None)
            if code == 429 or (isinstance(code, int) and code >= 500):
                return True
            return False  # other 4xx: not retryable
    if _api_core is not None:
        for name in (
            "RetryError",
            "ServiceUnavailable",
            "DeadlineExceeded",
            "TooManyRequests",
            "InternalServerError",
        ):
            cls = getattr(_api_core, name, None)
            if cls is not None and isinstance(exc, cls):
                return True
    return False


def _with_backoff(
    fn: Callable,
    *,
    job_name: str,
    op: str,
    base_s: int,
    max_s: int,
    attempts: int = 6,
):
    """Call ``fn`` with exponential backoff on transient exceptions.

    Delay starts at ``base_s`` and doubles up to ``max_s``. Non-transient
    exceptions (e.g. non-429 4xx) propagate immediately. Each retry is logged
    with job name, attempt number and exception class.
    """
    delay = max(1, int(base_s))
    ceiling = max(delay, int(max_s))
    last: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            if not _is_transient(exc):
                raise
            last = exc
            _log(
                f"retry {op}: job={job_name} attempt={attempt}/{attempts} "
                f"{type(exc).__name__}: {str(exc)[:160]}"
            )
            if attempt < attempts:
                time.sleep(min(delay, ceiling))
                delay = min(delay * 2, ceiling)
    raise RuntimeError(
        f"{op} failed after {attempts} transient retries (job={job_name}); "
        f"last: {type(last).__name__}: {last}"
    )


# ----------------------------------------------------------------------
# Submit phase (delegated to judge.py via subprocess)
# ----------------------------------------------------------------------


def _run_judge_submit(cell_filter: Optional[str]) -> int:
    cmd = [
        "uv",
        "run",
        "python",
        "-u",
        os.path.join("scripts", "judge.py"),
        "--judge-mode",
        "batch",
        "--batch-phase",
        "submit",
    ]
    if cell_filter is not None:
        cmd += ["--cell", cell_filter]
    _log(f"submit: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT_PATH, env=os.environ.copy())
    return proc.returncode


def submit_phase(
    cells: list[tuple[str, str]],
    state: list[dict],
    one_job: bool,
    cells_arg: str,
) -> None:
    """Submit one batch job per cell (default), or one combined job (--one-job).

    Skips any cell that already has an uncollected job in state (resume-safe).
    """
    covered: set[str] = set()
    for entry in _uncollected_entries(state):
        covered |= _entry_cell_ids(entry)

    if one_job:
        # Trade-off: a single combined job is simpler to track but loses
        # per-cell failure isolation and partial recovery; one bad row can sit
        # behind the whole job. Default (per-cell) is preferred.
        pending = [cid for cid, _ in cells if cid not in covered]
        if not pending:
            _log("submit (--one-job): all selected cells already have an uncollected job; skipping")
            return
        if cells_arg.strip().lower() == "all":
            cell_filter = None
        elif "," in cells_arg:
            raise SystemExit(
                "--one-job does not support a comma-list of cells (judge.py submit "
                "takes a single glob). Use --cells all, a single glob, or drop --one-job."
            )
        else:
            cell_filter = cells_arg.strip()
        rc = _run_judge_submit(cell_filter)
        if rc != 0:
            raise SystemExit(f"judge.py submit (combined) failed with rc={rc}")
        return

    for cell_id, _db_path in cells:
        if cell_id in covered:
            _log(f"submit: {cell_id} already has an uncollected job; skipping")
            continue
        rc = _run_judge_submit(cell_id)
        if rc != 0:
            raise SystemExit(f"judge.py submit failed for cell {cell_id} with rc={rc}")


# ----------------------------------------------------------------------
# Wait phase: poll each uncollected job to a terminal/readable state (fix #1)
# ----------------------------------------------------------------------


def _get_job(client, job_name: str, base_s: int, max_s: int):
    return _with_backoff(
        lambda: client.batches.get(name=job_name),
        job_name=job_name,
        op="batches.get",
        base_s=base_s,
        max_s=max_s,
    )


def _job_state_name(job) -> str:
    return getattr(job.state, "name", str(job.state))


def wait_phase(
    client,
    state: list[dict],
    poll_interval_s: int,
    poll_max_interval_s: int,
    poll_timeout_s: int,
) -> None:
    """Block until every uncollected job is terminal or readable, or time out."""
    entries = _uncollected_entries(state)
    if not entries:
        _log("wait: no uncollected jobs")
        return
    deadline = time.monotonic() + poll_timeout_s
    while True:
        pending: list[str] = []
        for entry in entries:
            if entry.get("collected"):
                continue
            job = _get_job(client, entry["job_name"], poll_interval_s, poll_max_interval_s)
            sname = _job_state_name(job)
            if sname in _READABLE or sname in _TERMINAL_FAILURE:
                _log(f"wait: job {entry['job_name']} ready (state={sname})")
            else:
                _log(f"wait: job {entry['job_name']} state={sname}; not ready")
                pending.append(entry["job_name"])
        if not pending:
            _log("wait: all jobs ready")
            return
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"wait: timed out after {poll_timeout_s}s with jobs still pending: "
                f"{', '.join(pending)}. Re-run later; it is safe to relaunch."
            )
        time.sleep(poll_interval_s)


# ----------------------------------------------------------------------
# Collect phase: in-process, reusing judge.py's routing/write-back (fix #2)
# ----------------------------------------------------------------------


def collect_phase(
    client,
    state: list[dict],
    poll_interval_s: int,
    poll_max_interval_s: int,
) -> bool:
    """Download and route every ready uncollected job, then mark it collected.

    Reuses judge.py's per-row routing (``_apply_batch_record``,
    ``_route_job_keys_to_error``) and write-back (``JudgeStore``). The driver is
    the only writer here: no judge.py subprocess runs during collect, so the
    WAL/threading.Lock single-writer invariant in JudgeStore holds.

    Fix #2 gates marking-collected behind an assertion that every persisted key
    was accounted for; on mismatch the job is left uncollected and the run fails
    loudly so a later collect can retry.
    """
    stores: dict[str, judge.JudgeStore] = {}

    def get_store(db_path: str) -> judge.JudgeStore:
        if db_path not in stores:
            stores[db_path] = judge.JudgeStore(db_path)
        return stores[db_path]

    changed = False
    try:
        for entry in state:
            if entry.get("collected"):
                continue
            job_name = entry["job_name"]
            keys = entry.get("keys", [])
            num_requests = entry.get("num_requests", len(keys))
            job = _get_job(client, job_name, poll_interval_s, poll_max_interval_s)
            sname = _job_state_name(job)

            if sname in _TERMINAL_FAILURE:
                # Route every persisted key to classification='error'. fix #2:
                # _route_job_keys_to_error must touch every persisted key; assert
                # the count or fail loudly.
                erred = judge._route_job_keys_to_error(keys, get_store)
                persisted_keys_count = len(keys)
                if erred != persisted_keys_count:
                    raise SystemExit(
                        f"collect: job {job_name} terminal-failure routing mismatch: "
                        f"persisted_keys_count={persisted_keys_count} erred={erred}; "
                        f"NOT marking collected."
                    )
                entry["collected"] = True
                entry["collected_at"] = judge._now_iso()
                entry["written"] = 0
                entry["failed"] = erred
                changed = True
                _log(f"collect: job {job_name} terminal state={sname}; wrote error for {erred} rows")
                continue

            if sname not in _READABLE:
                _log(f"collect: job {job_name} state={sname}; not ready, leaving uncollected")
                continue

            # Readable: REQUIRE a file destination. Per the spec we do not rely on
            # the inline-response fallback (submit does not stamp the key into
            # request metadata), so a missing dest file_name is the wrong shape:
            # treat it as a polling failure and retry later, do NOT mark collected.
            dest = job.dest
            file_name = getattr(dest, "file_name", None) if dest is not None else None
            if not file_name:
                _log(
                    f"collect: job {job_name} state={sname} but dest has no file_name; "
                    f"treating as transient, leaving uncollected for retry"
                )
                continue

            raw = _with_backoff(
                lambda fn=file_name: client.files.download(file=fn),
                job_name=job_name,
                op="files.download",
                base_s=poll_interval_s,
                max_s=poll_max_interval_s,
            )
            written = 0
            failed = 0
            seen_keys: set[str] = set()
            for line in raw.decode("utf-8").splitlines():
                if not line.strip():
                    continue
                obj = judge.json.loads(line)
                key = obj.get("key")
                if key:
                    seen_keys.add(key)
                ok = judge._apply_batch_record(obj, get_store)
                written += int(ok)
                failed += int(not ok)

            # fix #2: before marking collected, assert every request is accounted
            # for. On mismatch, log the discrepancy and the missing keys, and fail.
            missing_keys = [k for k in keys if k not in seen_keys]
            if (written + failed) != num_requests or missing_keys:
                raise SystemExit(
                    "collect: write-back assertion failed; NOT marking collected. "
                    f"job_name={job_name} num_requests={num_requests} "
                    f"written={written} failed={failed} "
                    f"missing_keys={missing_keys[:20]}"
                    + (" ..." if len(missing_keys) > 20 else "")
                )

            entry["collected"] = True
            entry["collected_at"] = judge._now_iso()
            entry["written"] = written
            entry["failed"] = failed
            changed = True
            _log(
                f"collect: job {job_name} state={sname}; wrote {written} verdicts "
                f"({failed} failed) over {num_requests} requests"
            )
    finally:
        for store in stores.values():
            store.close()

    if changed:
        judge._save_batch_state(state)
    return changed


# ----------------------------------------------------------------------
# Dry run (fix G)
# ----------------------------------------------------------------------


def dry_run(cells: list[tuple[str, str]]) -> None:
    if not cells:
        _log("dry-run: no cells matched under outputs/factorial/*/results.sqlite")
        return
    total_judge = 0
    total_err = 0
    for cell_id, db_path in cells:
        model = _cell_model(db_path)
        plan = _count_plan(db_path)
        collision = judge._bare_model_id(model) == judge.JUDGE_MODEL
        flag = "  !! JUDGE-MODEL COLLISION" if collision else ""
        total_judge += plan["rows_to_judge"]
        total_err += plan["rows_to_error_short_circuit"]
        _log(
            f"[{cell_id}] model={model} total={plan['total']} "
            f"already_classified={plan['already_classified']} "
            f"WOULD submit rows_to_judge={plan['rows_to_judge']} "
            f"rows_to_error_short_circuit={plan['rows_to_error_short_circuit']}{flag}"
        )
    _log(
        f"dry-run TOTAL across {len(cells)} cells: rows_to_judge={total_judge} "
        f"rows_to_error_short_circuit={total_err}. No API calls, no state writes."
    )


# ----------------------------------------------------------------------
# Summary (fix F)
# ----------------------------------------------------------------------


def _job_info_for_cell(state: list[dict], cell_id: str) -> tuple[Optional[str], Optional[str], Optional[float]]:
    """Most recent job_name, batch_state label, and turnaround seconds for a cell."""
    job_name = None
    batch_state = None
    seconds = None
    for entry in state:
        if cell_id not in _entry_cell_ids(entry):
            continue
        job_name = entry.get("job_name")
        if entry.get("collected"):
            if entry.get("failed", 0) and not entry.get("written", 0):
                batch_state = "FAILED/ERROR"
            else:
                batch_state = "COLLECTED"
        else:
            batch_state = "PENDING"
        sub = entry.get("submitted_at")
        col = entry.get("collected_at")
        if sub and col:
            try:
                t0 = datetime.fromisoformat(sub)
                t1 = datetime.fromisoformat(col)
                seconds = (t1 - t0).total_seconds()
            except Exception:  # noqa: BLE001
                seconds = None
    return job_name, batch_state, seconds


def write_summary(
    cells: list[tuple[str, str]],
    before: dict[str, dict],
    state: list[dict],
) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = os.path.join(ROOT_PATH, "outputs", "factorial")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"judge_summary_{stamp}.md")

    lines: list[str] = []
    lines.append(f"# Judge batch summary ({stamp})")
    lines.append("")
    rows_for_table: list[dict] = []
    for cell_id, db_path in cells:
        model = _cell_model(db_path)
        plan = _count_plan(db_path)
        dist = _distribution(db_path)
        before_classified = before.get(cell_id, {}).get("already_classified", 0)
        newly = plan["already_classified"] - before_classified
        job_name, batch_state, seconds = _job_info_for_cell(state, cell_id)
        rows_for_table.append(
            {
                "cell_id": cell_id,
                "model": model,
                "total_rows": plan["total"],
                "already_before": before_classified,
                "newly": newly,
                "dist": dist,
                "seconds": seconds,
                "job_name": job_name,
                "batch_state": batch_state,
            }
        )

        lines.append(f"## {cell_id}")
        lines.append("")
        lines.append(f"- model: `{model}`")
        lines.append(f"- total_rows: {plan['total']}")
        lines.append(f"- already_classified_before: {before_classified}")
        lines.append(f"- newly_classified: {newly}")
        lines.append(
            "- classification_distribution: "
            f"correct={dist['correct']} wrong={dist['wrong']} "
            f"abstained={dist['abstained']} error={dist['error']}"
        )
        wc = "n/a" if seconds is None else f"{seconds:.0f}"
        lines.append(f"- wall_clock_seconds: {wc}")
        lines.append(f"- batch_job_name: `{job_name}`")
        lines.append(f"- batch_state: {batch_state}")
        lines.append("")

    lines.append("## All cells")
    lines.append("")
    lines.append(
        "| cell_id | model | total | before | newly | correct | wrong | abstained | "
        "error | wall_s | batch_state |"
    )
    lines.append(
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"
    )
    for r in rows_for_table:
        wc = "n/a" if r["seconds"] is None else f"{r['seconds']:.0f}"
        lines.append(
            f"| {r['cell_id']} | {r['model']} | {r['total_rows']} | {r['already_before']} | "
            f"{r['newly']} | {r['dist']['correct']} | {r['dist']['wrong']} | "
            f"{r['dist']['abstained']} | {r['dist']['error']} | {wc} | {r['batch_state']} |"
        )
    lines.append("")

    text = "\n".join(lines)
    with open(out_path, "w") as fh:
        fh.write(text)
    print("\n" + text, flush=True)
    _log(f"summary written to {out_path}")
    return out_path


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--cells",
        default="all",
        help="glob | comma-list | 'all' of cell-dir names under outputs/factorial",
    )
    parser.add_argument("--poll-interval-s", type=int, default=60)
    parser.add_argument("--poll-max-interval-s", type=int, default=600)
    parser.add_argument("--poll-timeout-s", type=int, default=14400)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--phase",
        choices=["submit", "wait", "collect", "all"],
        default="all",
    )
    parser.add_argument(
        "--one-job",
        action="store_true",
        help="submit one combined job spanning all cells instead of one per cell "
        "(loses per-cell failure isolation; default is per-cell)",
    )
    args = parser.parse_args()

    cells = resolve_cells(args.cells)
    if not cells:
        raise SystemExit(
            f"no cells matched --cells {args.cells!r} under outputs/factorial/*/results.sqlite"
        )

    if args.dry_run:
        dry_run(cells)
        return

    # Snapshot before-counts for the summary (read-only).
    before = {cid: _count_plan(path) for cid, path in cells}

    # Self-judge guard before any API work (fix I).
    preflight_self_judge_guard(cells)

    if args.phase in ("submit", "all"):
        state = judge._load_batch_state()
        submit_phase(cells, state, args.one_job, args.cells)

    if args.phase == "submit":
        # Reload to reflect appended entries, then summarise current state.
        state = judge._load_batch_state()
        write_summary(cells, before, state)
        return

    client = judge._genai_client()

    if args.phase == "wait":
        state = judge._load_batch_state()
        wait_phase(client, state, args.poll_interval_s, args.poll_max_interval_s, args.poll_timeout_s)
        return

    if args.phase == "all":
        state = judge._load_batch_state()
        wait_phase(client, state, args.poll_interval_s, args.poll_max_interval_s, args.poll_timeout_s)

    # collect (phase 'collect' or tail of 'all')
    state = judge._load_batch_state()
    collect_phase(client, state, args.poll_interval_s, args.poll_max_interval_s)
    state = judge._load_batch_state()
    write_summary(cells, before, state)


if __name__ == "__main__":
    main()
