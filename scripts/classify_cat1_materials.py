#!/usr/bin/env python
"""Classify the 72 Category-1 benchmark questions as 'materials' vs 'not'.

Reviewer R1-3 claims a *materials* subset of Category-1 underperforms. No
'materials' grouping/subtype exists in the dataset schema (IfcBench has only
question/ground_truth/category/cobbie), nor in build_db.py / src/db / docs, so
the subset is induced here with minimax (MiniMax-M3), reusing the call pattern
from outputs/analysis/opencoding_full_20260626/run_minimax.py.

Question text + ground truth are recovered from the frozen run-time judge
batches via scripts.build_trace_history.load_question_index (the live db.db has
drifted). Cat-1 question_ids are identical across all 12 cells, so any one cell
suffices to enumerate them.

Output (REQUIRED, reusable): outputs/analysis/cat1_materials_labels_20260629.csv
with columns question_id, is_materials (0/1), source.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import time

from dotenv import load_dotenv

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

load_dotenv(os.path.join(_ROOT, ".env"))

from scripts.build_trace_history import (  # noqa: E402
    load_question_index,
    load_result_rows,
    load_run_metadata,
)

REF_CELL = "outputs/factorial/glm-5.2__agentic__none/results.sqlite"
OUT_CSV = "outputs/analysis/cat1_materials_labels_20260629.csv"
SOURCE = "minimax-anthropic:MiniMax-M3"

PROMPT = """You are labelling building-information-modelling (BIM) benchmark questions.

Decide whether the QUESTION is a *materials* question. A question is MATERIALS
(label 1) if its core answer is the material / material composition that a
building element is made of — e.g. "which materials are used for the walls",
"what are the foundations made of", "wall finishing material", "material layers
and thicknesses of a wall composition", "which coverings/finishes are applied".

It is NOT materials (label 0) if its core answer is something else: software /
IFC authoring standard, project / location metadata, room areas or names, level
elevations / heights, ceiling heights, element dimensions or counts, GUIDs,
furniture / sanitary / MEP / equipment inventories, structural component lists,
thermal transmittance (U-value), fire ratings, etc. Note: a wall *thickness*
question is NOT materials unless it explicitly asks about the material layers.

Respond with ONLY a JSON object: {{"is_materials": 0 or 1, "reason": "<=12 words"}}

QUESTION:
{question}

REFERENCE ANSWER (ground truth, for disambiguation):
{ground_truth}
"""


def _parse(text: str) -> tuple[int, str]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON in response: {text!r}")
    obj = json.loads(m.group(0))
    return int(obj["is_materials"]), str(obj.get("reason", ""))[:120]


def main() -> None:
    from src.harness.llm import init_llm

    meta = load_run_metadata(REF_CELL)
    cell = meta["cell_id"]
    qidx = load_question_index(REF_CELL)
    rows = [r for r in load_result_rows(REF_CELL) if r["category"] == 1]

    seen: dict[int, dict] = {}
    for r in sorted(rows, key=lambda x: x["question_id"]):
        qid = r["question_id"]
        if qid in seen:
            continue
        info = qidx.get((cell, qid, r["repeat_idx"])) or {}
        seen[qid] = {
            "question": (info.get("question") or "").strip(),
            "ground_truth": (info.get("ground_truth") or "").strip(),
        }

    assert len(seen) == 72, f"expected 72 cat-1 questions, got {len(seen)}"

    llm = init_llm(SOURCE, temperature=0)
    labels: list[dict] = []
    for i, (qid, d) in enumerate(sorted(seen.items()), 1):
        prompt = PROMPT.format(question=d["question"], ground_truth=d["ground_truth"])
        for attempt in range(3):
            try:
                resp = llm.invoke(prompt).content
                resp = resp if isinstance(resp, str) else str(resp)
                is_mat, reason = _parse(resp)
                break
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/72] q{qid} retry {attempt}: {e}", flush=True)
                time.sleep(4)
        else:
            raise RuntimeError(f"failed to classify q{qid}")
        labels.append(
            {
                "question_id": qid,
                "is_materials": is_mat,
                "source": SOURCE,
                "reason": reason,
                "question": d["question"],
            }
        )
        print(f"[{i}/72] q{qid} -> {is_mat}  ({reason})", flush=True)
        time.sleep(1)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["question_id", "is_materials", "source", "reason", "question"]
        )
        w.writeheader()
        w.writerows(labels)
    n_mat = sum(x["is_materials"] for x in labels)
    print(f"\nwrote {OUT_CSV}: {len(labels)} questions, {n_mat} materials", flush=True)


if __name__ == "__main__":
    main()
