"""Read-only Streamlit viewer for the cobbie factorial trace store.

Browses outputs/factorial/<cell_id>/results.sqlite produced by run_cell.py:
pick a cell, pick a question (and repeat), read the CodeAct transcript as
ordered generated_code + observation pairs, with a results/metadata header
joined to the question text and ground truth from the dataset.

Run:
    uv run --with streamlit streamlit run scripts/view_traces_streamlit.py

Opens every sqlite read-only (uri mode=ro) so it never locks a cell that
run_cell.py may still be writing.
"""

from __future__ import annotations

import glob
import os
import sqlite3
import sys

# ----------------------------------------------------------------------
# Data loading (importable, GUI-free; reused by the headless smoke test)
# ----------------------------------------------------------------------

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS_DIR)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_FACTORIAL_GLOB = os.path.join(_ROOT, "outputs", "factorial", "*", "results.sqlite")


def _connect_ro(db_path: str) -> sqlite3.Connection:
    """Open a sqlite file strictly read-only so a live writer is never locked."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def discover_cells() -> list[dict]:
    """List factorial cells that have a results.sqlite, newest first.

    Each entry: {cell_id, db_path}. cell_id is read from run_metadata when
    present, else derived from the directory name.
    """
    cells: list[dict] = []
    for db_path in sorted(glob.glob(_FACTORIAL_GLOB)):
        cell_id = os.path.basename(os.path.dirname(db_path))
        try:
            conn = _connect_ro(db_path)
            try:
                row = conn.execute(
                    "SELECT cell_id FROM run_metadata LIMIT 1"
                ).fetchone()
                if row and row["cell_id"]:
                    cell_id = row["cell_id"]
            finally:
                conn.close()
        except sqlite3.Error:
            pass
        cells.append({"cell_id": cell_id, "db_path": db_path})
    cells.sort(key=lambda c: os.path.getmtime(c["db_path"]), reverse=True)
    return cells


def load_question_index() -> dict[int, dict]:
    """Map question_id -> {question, ground_truth, category, project}.

    Sourced from the dataset (the cell sqlite stores neither question text nor
    ground truth). Imported lazily so import errors surface only when used.
    """
    from src.db.load_dataset import TESTSET

    index: dict[int, dict] = {}
    for q in TESTSET:
        index[q.id] = {
            "question": q.question,
            "ground_truth": q.ground_truth,
            "category": q.category,
            "project": q.ifc.project_name if q.ifc else None,
        }
    return index


def load_run_metadata(db_path: str) -> dict:
    """Return the single run_metadata row as a dict (empty if absent)."""
    conn = _connect_ro(db_path)
    try:
        row = conn.execute("SELECT * FROM run_metadata LIMIT 1").fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def load_result_rows(db_path: str, only_failures: bool = False) -> list[dict]:
    """Return results rows ordered by (question_id, repeat_idx).

    only_failures keeps rows whose status is not 'done' (error rows) or whose
    classification marks them wrong, for fast triage of failures.
    """
    conn = _connect_ro(db_path)
    try:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM results ORDER BY question_id, repeat_idx"
            ).fetchall()
        ]
    finally:
        conn.close()
    if only_failures:
        rows = [
            r
            for r in rows
            if r.get("status") != "done"
            or (r.get("classification") or "").lower() in {"wrong", "incorrect", "false"}
        ]
    return rows


def load_result_row(db_path: str, question_id: int, repeat_idx: int) -> dict:
    """Return a single results row, or {} if missing."""
    conn = _connect_ro(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM results WHERE question_id = ? AND repeat_idx = ?",
            (question_id, repeat_idx),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def load_steps(db_path: str, question_id: int, repeat_idx: int) -> list[dict]:
    """Return ordered transcript steps for one (question, repeat).

    Each step: {step_idx, generated_code, observation}, ordered by step_idx.
    """
    conn = _connect_ro(db_path)
    try:
        return [
            dict(r)
            for r in conn.execute(
                """
                SELECT step_idx, generated_code, observation
                FROM steps
                WHERE question_id = ? AND repeat_idx = ?
                ORDER BY step_idx
                """,
                (question_id, repeat_idx),
            ).fetchall()
        ]
    finally:
        conn.close()


# ----------------------------------------------------------------------
# Streamlit app
# ----------------------------------------------------------------------


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="cobbie trace viewer", layout="wide")
    st.title("cobbie factorial trace viewer")

    cells = discover_cells()
    if not cells:
        st.warning(
            "No factorial cells found under outputs/factorial/*/results.sqlite."
        )
        return

    with st.sidebar:
        st.header("Selection")
        cell_label = st.selectbox(
            "Cell", options=[c["cell_id"] for c in cells], index=0
        )
        db_path = next(c["db_path"] for c in cells if c["cell_id"] == cell_label)
        only_failures = st.toggle("Only error/wrong rows", value=False)

    rows = load_result_rows(db_path, only_failures=only_failures)
    if not rows:
        st.info("No matching rows in this cell.")
        return

    def _label(r: dict) -> str:
        return (
            f"q{r['question_id']} r{r['repeat_idx']} "
            f"[{r.get('status')}] iters={r.get('num_iterations')}"
        )

    label_to_key = {_label(r): (r["question_id"], r["repeat_idx"]) for r in rows}
    with st.sidebar:
        q_label = st.selectbox("Question", options=list(label_to_key.keys()), index=0)
    qid, ridx = label_to_key[q_label]

    meta = load_run_metadata(db_path)
    if meta:
        with st.sidebar:
            st.header("Run metadata")
            st.write(
                {
                    "model": meta.get("model"),
                    "paradigm": meta.get("paradigm"),
                    "tools": meta.get("tools"),
                    "prompt_hash": (meta.get("system_prompt_hash") or "")[:16],
                    "git_sha": (meta.get("git_sha") or "")[:12],
                    "question_set": meta.get("question_set"),
                    "concurrency": meta.get("concurrency"),
                }
            )

    qindex = load_question_index()
    info = qindex.get(qid, {})
    row = load_result_row(db_path, qid, ridx)

    st.subheader(f"Question {qid} (repeat {ridx})")
    cols = st.columns(4)
    cols[0].metric("Status", str(row.get("status")))
    cols[1].metric("Iterations", str(row.get("num_iterations")))
    cols[2].metric("Tool calls", str(row.get("num_tool_calls")))
    cols[3].metric("Latency (s)", str(row.get("latency_s")))
    cols = st.columns(3)
    cols[0].metric("Input tokens", str(row.get("input_tokens")))
    cols[1].metric("Cached input", str(row.get("cached_input_tokens")))
    cols[2].metric("Output tokens", str(row.get("output_tokens")))

    st.caption(
        f"category {info.get('category')}  |  project {info.get('project')}"
    )
    if row.get("classification"):
        st.info(f"classification: {row.get('classification')}")
    if row.get("error"):
        st.error(f"error: {row.get('error')}")

    st.markdown("**Question**")
    st.write(info.get("question", "(unknown)"))
    st.markdown("**Ground truth**")
    st.code(str(info.get("ground_truth", "(unknown)")), language="text")
    st.markdown("**Predicted answer**")
    st.write(row.get("predicted") or "(none)")

    st.divider()
    steps = load_steps(db_path, qid, ridx)
    st.subheader(f"Transcript ({len(steps)} step(s))")
    if not steps:
        st.info("No steps recorded for this question.")
    for s in steps:
        st.markdown(f"**Step {s['step_idx']} - generated code**")
        st.code(s.get("generated_code") or "", language="python")
        st.markdown("Observation")
        st.code(s.get("observation") or "", language="text")


if __name__ == "__main__":
    main()
