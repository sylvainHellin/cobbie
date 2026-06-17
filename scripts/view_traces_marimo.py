"""Read-only marimo viewer for the cobbie factorial trace store.

Browses outputs/factorial/<cell_id>/results.sqlite produced by run_cell.py:
pick a cell, pick a question (and repeat), read the CodeAct transcript as
ordered generated_code + observation pairs, with a results/metadata header
joined to the question text and ground truth from the dataset.

Run:
    uv run --with marimo marimo edit scripts/view_traces_marimo.py
    uv run --with marimo marimo run scripts/view_traces_marimo.py

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
# marimo app
# ----------------------------------------------------------------------

import marimo  # noqa: E402

app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    cells = discover_cells()
    if not cells:
        cell_dropdown = None
        header = mo.md(
            "No factorial cells found under `outputs/factorial/*/results.sqlite`."
        )
    else:
        cell_dropdown = mo.ui.dropdown(
            options={c["cell_id"]: c["db_path"] for c in cells},
            value=cells[0]["cell_id"],
            label="Cell",
        )
        header = mo.md(f"Found {len(cells)} cell(s).")
    mo.vstack([header, cell_dropdown] if cell_dropdown is not None else [header])
    return (cell_dropdown,)


@app.cell
def _(mo):
    only_failures = mo.ui.switch(label="Only error/wrong rows")
    only_failures
    return (only_failures,)


@app.cell
def _(cell_dropdown, mo, only_failures):
    db_path = cell_dropdown.value if cell_dropdown is not None else None
    if db_path:
        rows = load_result_rows(db_path, only_failures=only_failures.value)
    else:
        rows = []

    if rows:
        def _label(r):
            return (
                f"q{r['question_id']} r{r['repeat_idx']} "
                f"[{r.get('status')}] iters={r.get('num_iterations')}"
            )

        q_dropdown = mo.ui.dropdown(
            options={_label(r): (r["question_id"], r["repeat_idx"]) for r in rows},
            value=_label(rows[0]),
            label="Question",
        )
    else:
        q_dropdown = None
    mo.vstack(
        [q_dropdown]
        if q_dropdown is not None
        else [mo.md("No matching rows in this cell.")]
    )
    return db_path, q_dropdown


@app.cell
def _(db_path, mo, q_dropdown):
    meta = load_run_metadata(db_path) if db_path else {}
    if meta:
        meta_md = mo.md(
            "### Run metadata\n"
            f"- model: `{meta.get('model')}`\n"
            f"- paradigm: `{meta.get('paradigm')}`  tools: `{meta.get('tools')}`\n"
            f"- prompt hash: `{(meta.get('system_prompt_hash') or '')[:16]}`\n"
            f"- git sha: `{(meta.get('git_sha') or '')[:12]}`\n"
            f"- question set: `{meta.get('question_set')}`  "
            f"concurrency: `{meta.get('concurrency')}`"
        )
    else:
        meta_md = mo.md("")
    meta_md
    return


@app.cell
def _(db_path, mo, q_dropdown):
    if db_path and q_dropdown is not None and q_dropdown.value is not None:
        qid, ridx = q_dropdown.value
        qindex = load_question_index()
        info = qindex.get(qid, {})
        row = load_result_row(db_path, qid, ridx)

        predicted = row.get("predicted") or "(none)"
        classification = row.get("classification")
        class_line = (
            f"- classification: `{classification}`\n" if classification else ""
        )
        err = row.get("error")
        err_line = f"- error: `{err}`\n" if err else ""

        header_md = mo.md(
            f"## Question {qid} (repeat {ridx})\n"
            f"- category: `{info.get('category')}`  "
            f"project: `{info.get('project')}`\n"
            f"- status: `{row.get('status')}`  "
            f"iterations: `{row.get('num_iterations')}`  "
            f"tool calls: `{row.get('num_tool_calls')}`\n"
            f"- tokens in/cached/out: "
            f"`{row.get('input_tokens')}` / "
            f"`{row.get('cached_input_tokens')}` / "
            f"`{row.get('output_tokens')}`  "
            f"latency: `{row.get('latency_s')}s`\n"
            f"{class_line}{err_line}"
            f"\n**Question**\n\n{info.get('question', '(unknown)')}\n"
            f"\n**Ground truth**\n\n```\n{info.get('ground_truth', '(unknown)')}\n```\n"
            f"\n**Predicted answer**\n\n{predicted}\n"
        )
    else:
        qid = ridx = None
        header_md = mo.md("Select a question to view its transcript.")
    header_md
    return db_path, qid, ridx


@app.cell
def _(db_path, mo, qid, ridx):
    if db_path and qid is not None:
        steps = load_steps(db_path, qid, ridx)
        if steps:
            blocks = [mo.md(f"## Transcript ({len(steps)} step(s))")]
            for s in steps:
                code = s.get("generated_code") or ""
                obs = s.get("observation") or ""
                blocks.append(
                    mo.md(
                        f"### Step {s['step_idx']}\n"
                        f"Generated code\n\n```python\n{code}\n```\n"
                        f"\nObservation\n\n```text\n{obs}\n```\n"
                    )
                )
            transcript = mo.vstack(blocks)
        else:
            transcript = mo.md("No steps recorded for this question.")
    else:
        transcript = mo.md("")
    transcript
    return


if __name__ == "__main__":
    app.run()
