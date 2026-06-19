"""Gemini LLM-as-judge for the AUTCON-revision factorial cells.

Scores every stored answer in each ``outputs/factorial/<cell_id>/results.sqlite``
against the multi-criteria BIM rubric and writes the classification (plus the
full per-criterion judge output) back into that cell's sqlite. This is the
milestone-4 judge that ``run_cell.py`` deliberately leaves as a NULL
``classification`` column.

The judge is a port of the BAML answer-verifier (see
``.agents/research/2026-06-17-judge-port-spec.md``): the rubric prompt is
reproduced verbatim, the BAML output schema becomes a local pydantic
``JudgeResult``, and the classification derivation matches the original.
BAML is dropped entirely; structured output is delivered through google-genai's
``response_schema`` (sync via LangChain ``with_structured_output``; batch via the
native Batch API ``response_schema`` config).

Two judge modes:

  sync   per-row blocking calls with a retry loop. For dev spot-checks.
  batch  native async Batch API, two-phase submit/collect. For the full pass.

Single-writer, WAL-mode sqlite write-back mirrors ``run_cell.py``'s ``CellStore``.
Resume-safe: rows with a non-NULL ``classification`` are skipped.

Usage:
    uv run python scripts/judge.py --judge-mode sync --dry-run
    uv run python scripts/judge.py --judge-mode sync --limit 1
    uv run python scripts/judge.py --judge-mode sync
    uv run python scripts/judge.py --judge-mode batch --batch-phase submit
    uv run python scripts/judge.py --judge-mode batch --batch-phase collect
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.config import ROOT_PATH
from src.db.query import fetch_question_data

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

# Bare model id; the google-genai SDK prepends ``models/`` for both the sync
# generate_content path and batches.create, and langchain-google-genai accepts
# it directly. Confirmed in 2026-06-17-gemini-judge-model-id.md. Constant across
# all cells.
JUDGE_MODEL = "gemini-3.1-pro-preview"

# State file persisting submitted batch jobs between the submit and collect phases.
_BATCH_STATE_FILE = os.path.join(ROOT_PATH, "outputs", "factorial", "judge_batch_jobs.json")

# Display-only category names (the prompt only interpolates the integer).
CATEGORY_NAMES = {
    1: "Direct Retrieval",
    2: "Computational Aggregation",
    3: "Geometric/Spatial",
    4: "Incomplete Information",
}
VALID_CATEGORIES = set(CATEGORY_NAMES)

# Columns this judge adds to ``results`` (Schema Option B). Additive + idempotent.
# Existing rows keep NULL until judged. ``classification`` already exists in the
# run_cell.py schema, so it is NOT added here.
_NEW_COLUMNS: list[tuple[str, str]] = [
    ("abstention", "INTEGER"),
    ("faithfulness", "TEXT"),
    ("completeness", "TEXT"),
    ("transparency", "TEXT"),
    ("relevance", "TEXT"),
    ("justification", "TEXT"),
    ("judge_model", "TEXT"),
]

_MAX_RETRIES = 3
_RETRY_DELAY_S = 10.0


# ----------------------------------------------------------------------
# Output schema (pydantic port of the BAML AnswerEvaluationResult)
# ----------------------------------------------------------------------


class CriterionResult(str, Enum):
    Yes = "Yes"
    No = "No"
    Na = "Na"


class JudgeResult(BaseModel):
    """Structured judge verdict. Field order and descriptions are ported verbatim
    from judge-rubric-schemas.baml (class AnswerEvaluationResult)."""

    abstention: bool = Field(
        description="true if system explicitly declined to answer, false if answer provided"
    )
    faithfulness: CriterionResult = Field(
        description=(
            "Are all claims grounded in valid sources for this question category?\n"
            "- Category 1: BIM data only\n"
            "- Category 2: Simple computations on BIM data\n"
            "- Category 3: Complex geometric computations from BIM data\n"
            "- Category 4: BIM data + explicitly stated assumptions\n"
            "Use 'na' only if abstention is true."
        )
    )
    completeness: CriterionResult = Field(
        description=(
            "Are all relevant facts included to fully answer the question?\n"
            "Use 'na' if abstention is true OR question is open-ended with no "
            "objective completeness standard."
        )
    )
    transparency: CriterionResult = Field(
        description=(
            "Are sources/methods explicitly disclosed for each claim?\n"
            "Use 'na' only if abstention is true."
        )
    )
    relevance: CriterionResult = Field(
        description=(
            "Does the answer directly address the question asked?\n"
            "Use 'na' only if abstention is true."
        )
    )
    justification: str = Field(
        description=(
            "Brief explanation (2-3 sentences) of the evaluation, especially for "
            "edge cases or borderline decisions. Focus on explaining any 'no' "
            "verdicts or unusual circumstances."
        )
    )


def _derive_classification(result: JudgeResult) -> str:
    """Map the 5-criterion verdict to a 4-way label (lowercase).

    Ported from evaluate.py:_derive_classification. ``error`` is never produced
    here; the caller sets it on judge failure or invalid/empty input.
    """
    if result.abstention:
        return "abstained"
    if (
        result.faithfulness == CriterionResult.Yes
        and result.completeness == CriterionResult.Yes
        and result.transparency == CriterionResult.Yes
        and result.relevance == CriterionResult.Yes
    ):
        return "correct"
    return "wrong"


# ----------------------------------------------------------------------
# Prompt (verbatim port of EvaluateResponseGemini, BAML rubric lines 192-336)
# ----------------------------------------------------------------------

# {{ ctx.output_format }} is intentionally dropped: the schema is delivered via
# response_schema, not in the prompt text. Placeholders are filled with str
# .replace (not .format) since the rubric body has no literal braces but we want
# to avoid any accidental brace-parsing.
_PROMPT_TEMPLATE = """You are evaluating a BIM information extraction system's response to a question using a multi-criteria assessment framework.

QUESTION CATEGORY: {{category}}
QUESTION: {{question}}

REFERENCE ANSWER: {{ground_truth}}

Note: This reference answer is one possible response from a human expert labeller.
However, it is not necessarily the only valid answer (see the evaluation framework below)..

SYSTEM RESPONSE: {{system_response}}

---

## QUESTION CATEGORIES (Background)

Category 1 (Direct Retrieval): Direct information from BIM element properties, no computation
Category 2 (Computational Aggregation): Simple unambiguous computations (counting, summing, averaging)
Category 3 (Geometric/Spatial): Complex geometric computations from spatial relationships
Category 4 (Incomplete Information): Required information not in model, may need assumptions

---

## EVALUATION WORKFLOW

**Step 1: Determine if system ABSTAINED or PROVIDED AN ANSWER**

ABSTAINED if response contains explicit refusal:
- "I cannot determine..."
- "Insufficient information to answer..."
- "This data is not available and I cannot provide an answer..."
- "I am unable to answer this question..."

NOT abstained:
- Expressions of uncertainty while providing answer
- Conditional statements ("If X, then Y...")
- Partial information with explanation of limitations

**If ABSTAINED:**
- Set abstention = true
- Set ALL other criteria to 'Na'
- Provide brief justification
- STOP evaluation

**If PROVIDED AN ANSWER:**
- Set abstention = false
- Proceed to evaluate 4 quality criteria independently

---

## CRITERION 1: FAITHFULNESS

Are all claims grounded in valid sources and numerically accurate for this question category?

**Category-Specific Numerical Accuracy Requirements:**

**Category 1 & 2 (Deterministic):**
- Numerical values must match reference answer within tolerance
- These categories involve deterministic retrieval/aggregation -> should produce same results
- Tolerance rules:
  * Continuous measurements (lengths, areas, volumes): within 2% of reference
    Formula: |system_value - reference_answer | / reference_answer <= 0.02
  * Discrete counts (elements, rooms, floors): exact match required
- Fail if: numerical mismatch beyond tolerance

**Category 3 (Geometric):**
- Numerical values can differ from reference answer
- Multiple valid geometric calculation approaches exist
- Require: methodology/approach must be explicitly disclosed
- Fail if: values are implausible OR methodology not disclosed

**Category 4 (Incomplete Information):**
- Numerical values can differ from reference answer
- Answers may involve assumptions leading to different results
- Require: ALL assumptions MUST be disclosed verbatim in answer
  * "Assuming X..." or "Based on assumption that X..." required
  * Implied/hedged assumptions (e.g., "typically...", "generally...") -> FAIL
- Fail if: assumptions not explicitly stated OR values implausible

**Source/Method Disclosure (All Categories):**
- All claims should cite sources (properties, functions, calculations)
- Note: This is primarily assessed in Transparency criterion
- For faithfulness, focus on numerical accuracy per category rules above

**Result:**
- Yes: Numerically accurate per category rules, no hallucinations
- No: Numerical mismatch (Cat 1-2), implausible values, or unstated assumptions (Cat 4)
- Na: Only if abstention = true

---

## CRITERION 2: COMPLETENESS

Are all relevant facts included to fully answer the question?

**When to use 'Na':**
- Question is open-ended ("describe", "explain") with no objective standard
- Abstention occurred (mandatory)

**When to use 'No':**
- Answer omits critical facts for enumerable questions
- Provides only subset of requested items (e.g., lists 2 of 4 adjacent rooms)
- Partial answer to multi-part question

**When to use 'Yes':**
- All relevant facts present for enumerable questions
- Reasonable detail level for open-ended questions

**Result:**
- Yes: Complete answer
- No: Missing relevant facts
- Na: Open-ended question OR abstention

---

## CRITERION 3: TRANSPARENCY

Are sources/methods explicitly disclosed for each claim?

**Passes transparency (Yes):**
- "Width is 900mm from property Door.Width"
- "24 windows counted from IfcWindow elements"
- "Area is 245.8 m2 calculated using ISO 9836"
- "Assuming typical HVAC (20-25 year lifespan)..."

**Fails transparency (No):**
- "Width is 900mm" (no source)
- "According to the model..." (too vague)
- "Generally..." or "Typically..." (hedging, not explicit)

Requirement: Every claim must cite specific property, method, or assumption.

**Result:**
- Yes: All claims have explicit source/method disclosure
- No: Missing disclosure for any claim
- Na: Only if abstention = true

---

## CRITERION 4: RELEVANCE

Does the answer directly address the question asked?

**Passes relevance (Yes):**
- Addresses the correct aspect/property requested
- Addresses correct scope (e.g., specific room vs. whole building)
- May include additional information beyond question

**Fails relevance (No):**
- Answers wrong property (asked width, gave material)
- Answers wrong scope (asked south facade, gave whole building)
- Misunderstands question intent

**Result:**
- Yes: Directly addresses question
- No: Off-topic or misunderstood question
- Na: Only if abstention = true

---

## CRITICAL GUIDELINES

1. **Evaluate criteria INDEPENDENTLY**: Do not let one judgment influence another
   - Faithful but incomplete is valid
   - Complete but unfaithful is valid
   - All combinations are possible

2. **Use 'Na' sparingly**: Only for structural reasons (abstention, open-ended completeness)
   - NOT for uncertainty or difficulty judging
   - If unsure between Yes/No, choose based on best judgment and explain in justification

3. **Focus justification on edge cases**:
   - Explain any 'No' verdicts
   - Explain borderline decisions
   - Keep to 2-3 sentences"""


def build_prompt(category: int, question: str, ground_truth: str, system_response: str) -> str:
    """Fill the rubric template. Category is interpolated as its integer string."""
    return (
        _PROMPT_TEMPLATE.replace("{{category}}", str(category))
        .replace("{{question}}", question or "")
        .replace("{{ground_truth}}", "" if ground_truth is None else str(ground_truth))
        .replace("{{system_response}}", system_response or "")
    )


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_empty(value: Optional[str]) -> bool:
    return value is None or str(value).strip() == ""


def _bare_model_id(model: Optional[str]) -> Optional[str]:
    """Strip a ``provider:`` prefix from a stored model id.

    ``run_metadata.model`` is stored provider-prefixed by run_cell.py/init_llm
    (e.g. ``gemini:gemini-3.1-pro-preview``), but ``JUDGE_MODEL`` is the bare id.
    Compare bare ids so the self-judge guard actually fires on a real collision.
    """
    if model is None:
        return None
    return model.rsplit(":", 1)[-1]


# ----------------------------------------------------------------------
# SQLite store (single writer, WAL) -- mirrors run_cell.py CellStore
# ----------------------------------------------------------------------


class JudgeStore:
    """Single-writer sqlite store for one factorial cell, write side of the judge.

    Connects with the same WAL/PRAGMA conventions as run_cell.py's CellStore and
    serializes all writes behind a threading.Lock. It only ALTERs the schema
    additively and UPDATEs existing rows -- it never inserts, deletes, or
    rewrites the answer rows produced by run_cell.py.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Idempotent additive ALTER: add only the judge columns that are missing.

        Reads PRAGMA table_info(results) first and adds each absent column. Safe
        to call repeatedly; existing rows keep NULL in the new columns.
        """
        with self._lock:
            existing = {row[1] for row in self._conn.execute("PRAGMA table_info(results)")}
            for name, col_type in _NEW_COLUMNS:
                if name not in existing:
                    self._conn.execute(f"ALTER TABLE results ADD COLUMN {name} {col_type}")
            self._conn.commit()

    def cell_model(self) -> Optional[str]:
        row = self._conn.execute("SELECT model FROM run_metadata LIMIT 1").fetchone()
        return row[0] if row else None

    def select_rows(self) -> list[dict]:
        """All rows still needing a verdict: classification IS NULL.

        Returns the fields needed to judge or to short-circuit to error.
        """
        cur = self._conn.execute(
            """
            SELECT question_id, repeat_idx, category, predicted, status
            FROM results
            WHERE classification IS NULL
            ORDER BY question_id, repeat_idx
            """
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def write_verdict(
        self,
        question_id: int,
        repeat_idx: int,
        classification: str,
        result: Optional[JudgeResult],
        judge_model: Optional[str],
        only_if_null: bool = False,
    ) -> None:
        """UPDATE one row's classification + per-criterion columns.

        Keyed by (question_id, repeat_idx). Commits per write under the lock.
        For error short-circuits, ``result`` is None and the criterion columns
        stay NULL.

        ``only_if_null`` adds ``AND classification IS NULL`` to the WHERE clause
        so the write is strictly idempotent. The collect path sets it so a row
        already classified by a prior/overlapping batch job is never overwritten;
        the sync path leaves it False (sync already filters via select_rows).
        """
        if result is None:
            abstention = None
            faithfulness = completeness = transparency = relevance = justification = None
        else:
            abstention = 1 if result.abstention else 0
            faithfulness = result.faithfulness.value
            completeness = result.completeness.value
            transparency = result.transparency.value
            relevance = result.relevance.value
            justification = result.justification
        where_clause = "WHERE question_id = ? AND repeat_idx = ?"
        if only_if_null:
            where_clause += " AND classification IS NULL"
        with self._lock:
            self._conn.execute(
                f"""
                UPDATE results SET
                    classification = ?, abstention = ?, faithfulness = ?,
                    completeness = ?, transparency = ?, relevance = ?,
                    justification = ?, judge_model = ?
                {where_clause}
                """,
                (
                    classification,
                    abstention,
                    faithfulness,
                    completeness,
                    transparency,
                    relevance,
                    justification,
                    judge_model,
                    question_id,
                    repeat_idx,
                ),
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# ----------------------------------------------------------------------
# Cell enumeration + row planning
# ----------------------------------------------------------------------


def enumerate_cells(cell_filter: Optional[str]) -> list[str]:
    """Return sorted results.sqlite paths under outputs/factorial.

    ``cell_filter`` is an optional cell-dir name or glob matched against the cell
    directory name (e.g. ``minimax-m3__static__none`` or ``*static*``).
    """
    base = os.path.join(ROOT_PATH, "outputs", "factorial")
    paths = sorted(glob.glob(os.path.join(base, "*", "results.sqlite")))
    if cell_filter:
        paths = [
            p
            for p in paths
            if fnmatch.fnmatch(os.path.basename(os.path.dirname(p)), cell_filter)
        ]
    return paths


def _split_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Partition selected rows into (judgeable, error-short-circuit).

    Judgeable: status == 'done' AND non-empty predicted.
    Error short-circuit: status == 'error' OR empty predicted (set to 'error'
    without calling Gemini).
    """
    judgeable: list[dict] = []
    errors: list[dict] = []
    for row in rows:
        if row.get("status") == "done" and not _is_empty(row.get("predicted")):
            judgeable.append(row)
        else:
            errors.append(row)
    return judgeable, errors


# ----------------------------------------------------------------------
# Sync judge
# ----------------------------------------------------------------------


def _make_sync_judge():
    """Build a LangChain Gemini chat model with structured JudgeResult output.

    init_llm routes ``gemini:<id>`` to ChatGoogleGenerativeAI (langchain-google-genai),
    which supports ``with_structured_output``; that returns a JudgeResult instance.
    """
    from src.harness.llm import init_llm

    model = init_llm(f"gemini:{JUDGE_MODEL}", temperature=0)
    return model.with_structured_output(JudgeResult)


def judge_one_sync(judge, category: int, question: str, ground_truth: str, predicted: str) -> JudgeResult:
    """Call the judge with the retry loop from the spec (broad except, sleep
    between attempts). Raises the last error if all attempts fail."""
    prompt = build_prompt(category, question, ground_truth, predicted)
    last_error: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = judge.invoke(prompt)
            if not isinstance(result, JudgeResult):
                # with_structured_output may return a dict for some wrappers.
                result = JudgeResult.model_validate(result)
            return result
        except Exception as exc:  # noqa: BLE001 -- broad on purpose (429/5xx/parse)
            last_error = exc
            print(
                f"  ! judge attempt {attempt}/{_MAX_RETRIES} failed: "
                f"{type(exc).__name__}: {str(exc)[:160]}",
                flush=True,
            )
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_S)
    raise RuntimeError(f"all {_MAX_RETRIES} attempts failed; last: {last_error}")


def run_sync(cells: list[str], limit: Optional[int]) -> None:
    judge = None  # lazily built so --dry-run / no judgeable rows never touch the API
    judged = 0
    for db_path in cells:
        cell_id = os.path.basename(os.path.dirname(db_path))
        store = JudgeStore(db_path)
        try:
            cell_model = store.cell_model()
            if _bare_model_id(cell_model) == JUDGE_MODEL:
                raise RuntimeError(
                    f"judge model {JUDGE_MODEL} equals cell run model "
                    f"{cell_model!r} in {cell_id}; would self-judge"
                )
            rows = store.select_rows()
            judgeable, errors = _split_rows(rows)

            # Error short-circuits never call Gemini.
            for row in errors:
                store.write_verdict(
                    row["question_id"], row["repeat_idx"], "error", None, None
                )

            if not judgeable:
                print(f"[{cell_id}] nothing judgeable (errors set: {len(errors)})", flush=True)
                continue

            qdata = fetch_question_data(sorted({r["question_id"] for r in judgeable}))
            for row in judgeable:
                if limit is not None and judged >= limit:
                    print(f"[{cell_id}] reached --limit {limit}; stopping", flush=True)
                    return
                qid = row["question_id"]
                meta = qdata.get(qid)
                if meta is None:
                    store.write_verdict(qid, row["repeat_idx"], "error", None, None)
                    print(f"  [{cell_id}] q={qid}: no ground truth -> error", flush=True)
                    continue
                category = meta["category"]
                if category not in VALID_CATEGORIES:
                    store.write_verdict(qid, row["repeat_idx"], "error", None, None)
                    print(f"  [{cell_id}] q={qid}: bad category {category!r} -> error", flush=True)
                    continue
                if judge is None:
                    judge = _make_sync_judge()
                try:
                    result = judge_one_sync(
                        judge, category, meta["question"], meta["ground_truth"], row["predicted"]
                    )
                except Exception as exc:  # noqa: BLE001
                    store.write_verdict(qid, row["repeat_idx"], "error", None, JUDGE_MODEL)
                    print(f"  [{cell_id}] q={qid} r={row['repeat_idx']}: judge failed -> error: {exc}", flush=True)
                    judged += 1
                    continue
                classification = _derive_classification(result)
                store.write_verdict(qid, row["repeat_idx"], classification, result, JUDGE_MODEL)
                judged += 1
                print(
                    f"  [{cell_id}] q={qid} r={row['repeat_idx']} -> {classification} "
                    f"(abst={result.abstention} f={result.faithfulness.value} "
                    f"c={result.completeness.value} t={result.transparency.value} "
                    f"r={result.relevance.value})",
                    flush=True,
                )
        finally:
            store.close()
    print(f"\nsync judge done: {judged} rows judged", flush=True)


# ----------------------------------------------------------------------
# Batch judge (two-phase submit / collect)
# ----------------------------------------------------------------------


def _genai_client():
    from google import genai

    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _response_schema_dict() -> dict:
    """JudgeResult as the wire-format (camelCase) JSON schema for generationConfig."""
    from google.genai import _transformers as t

    schema = t.t_schema(None, JudgeResult)
    return schema.model_dump(mode="json", exclude_none=True, by_alias=True)


def _batch_key(cell_id: str, question_id: int, repeat_idx: int) -> str:
    """Composite routing key carried through the batch so each response maps back
    to the exact cell row. cell_id contains only [a-z0-9-_], never '|'."""
    return f"{cell_id}|{question_id}|{repeat_idx}"


def _parse_batch_key(key: str) -> tuple[str, int, int]:
    cell_id, qid, ridx = key.rsplit("|", 2)
    return cell_id, int(qid), int(ridx)


def _load_batch_state() -> list[dict]:
    if os.path.exists(_BATCH_STATE_FILE):
        with open(_BATCH_STATE_FILE) as fh:
            return json.load(fh)
    return []


def _save_batch_state(state: list[dict]) -> None:
    os.makedirs(os.path.dirname(_BATCH_STATE_FILE), exist_ok=True)
    with open(_BATCH_STATE_FILE, "w") as fh:
        json.dump(state, fh, indent=2)


def run_batch_submit(cells: list[str], limit: Optional[int]) -> None:
    """Phase 1: build a JSONL of judge requests across all cells, upload it,
    create one batch job, and persist the job name + key->row map to state.

    Error/empty-predicted rows are short-circuited to 'error' immediately (no
    request emitted for them). Already-classified rows are skipped (resume-safe).
    """
    schema = _response_schema_dict()
    requests: list[dict] = []
    key_count = 0
    # Set once --limit is hit so the OUTER per-cell loop stops too; otherwise the
    # inner break would let later cells still write error short-circuits and call
    # fetch_question_data even though no more requests are emitted (review #4).
    cap_reached = False
    # Track stores so we can apply error short-circuits without a second pass.
    for db_path in cells:
        if cap_reached:
            break
        cell_id = os.path.basename(os.path.dirname(db_path))
        store = JudgeStore(db_path)
        try:
            cell_model = store.cell_model()
            if _bare_model_id(cell_model) == JUDGE_MODEL:
                raise RuntimeError(
                    f"judge model {JUDGE_MODEL} equals cell run model "
                    f"{cell_model!r} in {cell_id}"
                )
            rows = store.select_rows()
            judgeable, errors = _split_rows(rows)
            for row in errors:
                store.write_verdict(row["question_id"], row["repeat_idx"], "error", None, None)
            if not judgeable:
                continue
            qdata = fetch_question_data(sorted({r["question_id"] for r in judgeable}))
            for row in judgeable:
                if limit is not None and key_count >= limit:
                    cap_reached = True
                    break
                qid = row["question_id"]
                meta = qdata.get(qid)
                if meta is None or meta["category"] not in VALID_CATEGORIES:
                    store.write_verdict(qid, row["repeat_idx"], "error", None, None)
                    continue
                prompt = build_prompt(
                    meta["category"], meta["question"], meta["ground_truth"], row["predicted"]
                )
                requests.append(
                    {
                        "key": _batch_key(cell_id, qid, row["repeat_idx"]),
                        "request": {
                            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                            "generationConfig": {
                                "responseMimeType": "application/json",
                                "responseSchema": schema,
                            },
                        },
                    }
                )
                key_count += 1
        finally:
            store.close()

    if not requests:
        print("No judgeable rows; nothing to submit.", flush=True)
        return

    os.makedirs(os.path.join(ROOT_PATH, "outputs", "factorial"), exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    jsonl_path = os.path.join(ROOT_PATH, "outputs", "factorial", f"judge_batch_{stamp}.jsonl")
    with open(jsonl_path, "w") as fh:
        for req in requests:
            fh.write(json.dumps(req) + "\n")
    print(f"Wrote {len(requests)} requests to {jsonl_path}", flush=True)

    client = _genai_client()
    uploaded = client.files.upload(
        file=jsonl_path,
        config={"mime_type": "application/jsonl", "display_name": f"judge-batch-{stamp}"},
    )
    job = client.batches.create(
        model=JUDGE_MODEL,
        src=uploaded.name,
        config={"display_name": f"bim-judge-{stamp}"},
    )
    state = _load_batch_state()
    state.append(
        {
            "job_name": job.name,
            "input_file": uploaded.name,
            "jsonl_path": jsonl_path,
            "num_requests": len(requests),
            # Persisted so collect can route per-row errors on terminal-failure or
            # unrecoverable states without re-reading the JSONL (review #3 note).
            "keys": [req["key"] for req in requests],
            "submitted_at": _now_iso(),
            "collected": False,
        }
    )
    _save_batch_state(state)
    print(
        f"Submitted batch job {job.name} ({len(requests)} requests, state={getattr(job.state, 'name', job.state)}).\n"
        f"State saved to {_BATCH_STATE_FILE}. Run --batch-phase collect later.",
        flush=True,
    )


def run_batch_collect() -> None:
    """Phase 2: poll each persisted job; for SUCCEEDED jobs download the output
    JSONL, route each result back to its cell row by key, derive classification,
    and write back. Jobs not yet done report their state and are left for a later
    collect run (exit 0)."""
    state = _load_batch_state()
    if not state:
        print(f"No batch jobs in {_BATCH_STATE_FILE}; submit first.", flush=True)
        return
    client = _genai_client()
    stores: dict[str, JudgeStore] = {}

    def get_store(db_path: str) -> JudgeStore:
        if db_path not in stores:
            stores[db_path] = JudgeStore(db_path)
        return stores[db_path]

    # Terminal failure states: the job will never produce usable output, so route
    # every one of its rows to classification='error' and mark it collected.
    _TERMINAL_FAILURE = {
        "JOB_STATE_FAILED",
        "JOB_STATE_EXPIRED",
        "JOB_STATE_CANCELLED",
    }
    # States that carry a readable dest file (full or partial success). Partial
    # success records carry per-line ``error`` for the failed rows, which route to
    # classification='error' via _apply_batch_record (review #3).
    _READABLE = {
        "JOB_STATE_SUCCEEDED",
        "JOB_STATE_PARTIALLY_SUCCEEDED",
    }

    try:
        changed = False
        for entry in state:
            if entry.get("collected"):
                continue
            job = client.batches.get(name=entry["job_name"])
            job_state = getattr(job.state, "name", str(job.state))

            if job_state in _TERMINAL_FAILURE:
                # No recoverable output: write error for every persisted key.
                erred = _route_job_keys_to_error(entry.get("keys", []), get_store)
                entry["collected"] = True
                entry["collected_at"] = _now_iso()
                entry["written"] = 0
                entry["failed"] = erred
                changed = True
                print(
                    f"job {entry['job_name']}: terminal state={job_state}; "
                    f"wrote error for {erred} rows.",
                    flush=True,
                )
                continue

            if job_state not in _READABLE:
                # PENDING/RUNNING/PAUSED/QUEUED/UNSPECIFIED: not terminal, retry later.
                print(f"job {entry['job_name']}: state={job_state}; not ready, will retry later.", flush=True)
                continue

            # SUCCEEDED or PARTIALLY_SUCCEEDED: read the dest file or inline responses.
            written = 0
            failed = 0
            dest = job.dest
            if dest is not None and getattr(dest, "file_name", None):
                raw = client.files.download(file=dest.file_name)
                for line in raw.decode("utf-8").splitlines():
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    ok = _apply_batch_record(obj, get_store)
                    written += int(ok)
                    failed += int(not ok)
            elif dest is not None and getattr(dest, "inlined_responses", None):
                # Inline-response routing (chosen over abandoning the data, review
                # #2). google-genai 2.8.0 InlinedResponse exposes .response
                # (GenerateContentResponse), .error (JobError), and .metadata
                # (dict[str,str]); the original key was carried in request
                # .metadata, so recover it from inlined_responses[i].metadata.
                for inline in dest.inlined_responses:
                    obj = _inline_response_to_record(inline)
                    if obj is None:
                        failed += 1
                        print(
                            f"job {entry['job_name']}: inline response missing key in "
                            "metadata; cannot route, skipped.",
                            flush=True,
                        )
                        continue
                    ok = _apply_batch_record(obj, get_store)
                    written += int(ok)
                    failed += int(not ok)
            else:
                # No usable destination: do NOT mark collected so a later collect
                # can retry instead of permanently abandoning the rows (review #2).
                print(f"job {entry['job_name']}: {job_state} but no output destination found; will retry later.", flush=True)
                continue

            entry["collected"] = True
            entry["collected_at"] = _now_iso()
            entry["written"] = written
            entry["failed"] = failed
            changed = True
            print(f"job {entry['job_name']}: state={job_state}; wrote {written} verdicts ({failed} failed).", flush=True)
        if changed:
            _save_batch_state(state)
    finally:
        for store in stores.values():
            store.close()


def _inline_response_to_record(inline) -> Optional[dict]:
    """Adapt a google-genai ``InlinedResponse`` to the JSONL-record dict that
    ``_apply_batch_record`` consumes, recovering the original ``key`` from the
    request metadata. Returns None if the key cannot be recovered.

    The submit path carries the routing key only in the per-record ``key`` field;
    inline responses surface request metadata via ``InlinedResponse.metadata``.
    If a future submit also stamps the key into request metadata it lands here;
    otherwise None signals the caller to count it as failed without losing other
    rows (the job is still marked collected, but unrouted rows stay NULL and an
    explicit warning is printed).
    """
    metadata = getattr(inline, "metadata", None) or {}
    key = metadata.get("key")
    if not key:
        return None
    record: dict = {"key": key}
    error = getattr(inline, "error", None)
    if error is not None:
        record["error"] = error.model_dump(mode="json") if hasattr(error, "model_dump") else str(error)
        return record
    response = getattr(inline, "response", None)
    if response is not None:
        record["response"] = response.model_dump(mode="json", exclude_none=True)
    return record


def _route_job_keys_to_error(keys: list[str], get_store) -> int:
    """Write classification='error' for every persisted key of a terminally
    failed job. Returns the count written. Idempotent: only touches rows still
    classification IS NULL.
    """
    erred = 0
    for key in keys:
        try:
            cell_id, qid, ridx = _parse_batch_key(key)
        except Exception:
            print(f"  ! cannot parse key {key!r}; skipped", flush=True)
            continue
        db_path = os.path.join(ROOT_PATH, "outputs", "factorial", cell_id, "results.sqlite")
        store = get_store(db_path)
        store.write_verdict(qid, ridx, "error", None, JUDGE_MODEL, only_if_null=True)
        erred += 1
    return erred


def _apply_batch_record(obj: dict, get_store) -> bool:
    """Route one batch output line back to its cell row and write the verdict.

    Returns True on success, False if the line carried an error or was unparseable.
    Collect-phase writes pass ``only_if_null=True`` so a row already classified by
    a prior/overlapping job is never overwritten (strict idempotency, review nit).
    """
    key = obj.get("key")
    if not key:
        print("  ! batch record missing key; skipped", flush=True)
        return False
    try:
        cell_id, qid, ridx = _parse_batch_key(key)
    except Exception:
        print(f"  ! cannot parse key {key!r}; skipped", flush=True)
        return False
    db_path = os.path.join(ROOT_PATH, "outputs", "factorial", cell_id, "results.sqlite")
    store = get_store(db_path)

    if obj.get("error"):
        store.write_verdict(qid, ridx, "error", None, JUDGE_MODEL, only_if_null=True)
        print(f"  [{cell_id}] q={qid} r={ridx}: batch error -> error", flush=True)
        return False
    try:
        response = obj["response"]
        text = response["candidates"][0]["content"]["parts"][0]["text"]
        result = JudgeResult.model_validate_json(text)
    except Exception as exc:  # noqa: BLE001
        store.write_verdict(qid, ridx, "error", None, JUDGE_MODEL, only_if_null=True)
        print(f"  [{cell_id}] q={qid} r={ridx}: parse failed -> error: {exc}", flush=True)
        return False
    classification = _derive_classification(result)
    store.write_verdict(qid, ridx, classification, result, JUDGE_MODEL, only_if_null=True)
    return True


# ----------------------------------------------------------------------
# Dry run
# ----------------------------------------------------------------------


def run_dry(cells: list[str], limit: Optional[int]) -> None:
    """Enumerate cells and report judgeable vs error/skip counts. No API calls.

    Also ensures the additive schema is present (idempotent ALTER) so the new
    columns exist for inspection, without touching any existing row data.
    """
    if not cells:
        print("No cells found under outputs/factorial/*/results.sqlite", flush=True)
        return
    total_judgeable = 0
    total_errors = 0
    for db_path in cells:
        cell_id = os.path.basename(os.path.dirname(db_path))
        store = JudgeStore(db_path)
        try:
            cell_model = store.cell_model()
            collision = cell_model == JUDGE_MODEL
            rows = store.select_rows()
            judgeable, errors = _split_rows(rows)
            total = store._conn.execute("SELECT COUNT(*) FROM results").fetchone()[0]
            already = store._conn.execute(
                "SELECT COUNT(*) FROM results WHERE classification IS NOT NULL"
            ).fetchone()[0]
            total_judgeable += len(judgeable)
            total_errors += len(errors)
            flag = "  !! JUDGE-MODEL COLLISION" if collision else ""
            print(
                f"[{cell_id}] model={cell_model} rows={total} "
                f"already_classified={already} pending={len(rows)} "
                f"judgeable={len(judgeable)} error_skip={len(errors)}{flag}",
                flush=True,
            )
        finally:
            store.close()
    cap = "" if limit is None else f" (would cap at --limit {limit})"
    print(
        f"\nTOTAL across {len(cells)} cells: judgeable={total_judgeable} "
        f"error_skip={total_errors}{cap}. No API calls made (dry run).",
        flush=True,
    )


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--judge-mode", required=True, choices=["sync", "batch"])
    parser.add_argument(
        "--batch-phase",
        choices=["submit", "collect"],
        help="required when --judge-mode batch",
    )
    parser.add_argument(
        "--cell",
        default=None,
        help="cell-dir name or glob to restrict to (e.g. '*static*'); default all",
    )
    parser.add_argument("--limit", type=int, default=None, help="cap judged/submitted rows")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="select rows and print counts WITHOUT calling Gemini",
    )
    args = parser.parse_args()

    cells = enumerate_cells(args.cell)

    if args.dry_run:
        run_dry(cells, args.limit)
        return

    if args.judge_mode == "sync":
        run_sync(cells, args.limit)
        return

    # batch
    if args.batch_phase is None:
        parser.error("--judge-mode batch requires --batch-phase {submit,collect}")
    if args.batch_phase == "submit":
        run_batch_submit(cells, args.limit)
    else:
        run_batch_collect()


if __name__ == "__main__":
    main()
