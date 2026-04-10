#!/usr/bin/env python3
"""
Backfill missing questions for an evaluation run.

Identifies questions in the DEVSET that have no nested run (or only error-like
runs) under a given parent run, then evaluates them one-by-one via
`run_evaluation.py --continue`.

Also includes a dedupe phase (same logic as clean_and_retry_static_doc.py) to
clean up any duplicate nested runs before/after the backfill.

Usage:
    # Preview missing questions for static-manual
    uv run scripts/backfill_missing_questions.py \
        --parent-run-id 77e41658053f458fadb33bb7a253bb50 \
        --eval-args "--system static --tools manual" \
        --dry-run

    # Run the backfill
    uv run scripts/backfill_missing_questions.py \
        --parent-run-id 77e41658053f458fadb33bb7a253bb50 \
        --eval-args "--system static --tools manual"

Prerequisites:
    - MLflow server must be running (see CLAUDE.md)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

import mlflow
from mlflow import MlflowClient
from mlflow.entities import Run
from tabulate import tabulate

from src.analysis.data_extraction import fetch_nested_runs
from src.config import MLFLOW_URI
from src.db import DEVSET

GOOD_CLASSIFICATIONS = {"correct", "wrong", "abstained"}


@dataclass
class RunInfo:
    """Lightweight view of an MLflow nested run."""

    run_id: str
    question_id: int
    classification: Optional[str]
    status: str
    end_time: int
    is_good: bool
    is_error: bool


def _classify_run(run: Run) -> Optional[RunInfo]:
    """Build a RunInfo or return None if the run lacks a usable question_id."""
    params = run.data.params
    qid_raw = params.get("question_id")
    if qid_raw is None:
        return None
    try:
        qid = int(qid_raw)
    except (TypeError, ValueError):
        return None

    classification = params.get("classification")
    status = run.info.status
    end_time = run.info.end_time or 0

    is_good = classification in GOOD_CLASSIFICATIONS
    is_error = (
        classification == "error"
        or status == "FAILED"
        or (status == "FINISHED" and classification is None)
    )

    return RunInfo(
        run_id=run.info.run_id,
        question_id=qid,
        classification=classification,
        status=status,
        end_time=end_time,
        is_good=is_good,
        is_error=is_error,
    )


def _load_run_infos(client: MlflowClient, parent_run_id: str) -> list[RunInfo]:
    parent_run = client.get_run(parent_run_id)
    nested = fetch_nested_runs(client, parent_run_id, parent_run.info.experiment_id)
    infos: list[RunInfo] = []
    for nested_run in nested:
        info = _classify_run(nested_run)
        if info is not None:
            infos.append(info)
    return infos


def _pick_survivor(runs: list[RunInfo]) -> RunInfo:
    good_runs = [r for r in runs if r.is_good]
    candidates = good_runs if good_runs else runs
    candidates.sort(
        key=lambda r: (r.status == "FINISHED", r.end_time),
        reverse=True,
    )
    return candidates[0]


def dedupe_phase(
    client: MlflowClient,
    parent_run_id: str,
    dry_run: bool,
    phase_label: str = "dedupe",
) -> int:
    infos = _load_run_infos(client, parent_run_id)
    by_qid: dict[int, list[RunInfo]] = {}
    for info in infos:
        by_qid.setdefault(info.question_id, []).append(info)

    deleted = 0
    rows: list[list] = []
    for qid in sorted(by_qid):
        runs = by_qid[qid]
        if len(runs) <= 1:
            continue
        survivor = _pick_survivor(runs)
        for r in runs:
            if r.run_id == survivor.run_id:
                continue
            action = "WOULD DELETE" if dry_run else "DELETED"
            rows.append([qid, r.run_id[:8], r.classification or "none", r.status, "-> keep " + survivor.run_id[:8], action])
            if not dry_run:
                client.delete_run(r.run_id)
            deleted += 1

    print(f"\n=== PHASE: {phase_label} ===")
    if rows:
        print(tabulate(rows, headers=["qid", "run_id", "classification", "status", "survivor", "action"], tablefmt="grid"))
    else:
        print("No duplicates found.")
    print(f"{'Would delete' if dry_run else 'Deleted'}: {deleted} duplicate run(s)")
    return deleted


def _build_qid_to_devset_index() -> dict[int, int]:
    return {q.id: idx for idx, q in enumerate(DEVSET)}


def find_missing_and_error_questions(
    client: MlflowClient,
    parent_run_id: str,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """
    Return (missing, errors) where each is a list of (question_id, devset_index).

    - missing: questions in DEVSET with no nested run at all
    - errors: questions with only error-like nested runs (no good run)
    """
    infos = _load_run_infos(client, parent_run_id)

    by_qid: dict[int, list[RunInfo]] = {}
    for info in infos:
        by_qid.setdefault(info.question_id, []).append(info)

    qid_to_idx = _build_qid_to_devset_index()
    all_devset_qids = set(qid_to_idx.keys())
    evaluated_qids = set(by_qid.keys())

    # Missing: never evaluated
    missing_qids = all_devset_qids - evaluated_qids
    missing = sorted([(qid, qid_to_idx[qid]) for qid in missing_qids], key=lambda x: x[1])

    # Errors: evaluated but only error-like results
    errors: list[tuple[int, int]] = []
    for qid, runs in sorted(by_qid.items()):
        if any(r.is_good for r in runs):
            continue
        if not any(r.is_error for r in runs):
            continue
        devset_idx = qid_to_idx.get(qid)
        if devset_idx is not None:
            errors.append((qid, devset_idx))

    return missing, errors


def backfill_phase(
    client: MlflowClient,
    parent_run_id: str,
    eval_args: str,
    dry_run: bool,
) -> tuple[int, int]:
    missing, errors = find_missing_and_error_questions(client, parent_run_id)
    targets = missing + errors

    print("\n=== PHASE: backfill ===")
    print(f"  Missing (never evaluated): {len(missing)}")
    print(f"  Error-like (need retry):   {len(errors)}")
    print(f"  Total to evaluate:         {len(targets)}")

    if not targets:
        print("Nothing to do.")
        return (0, 0)

    if dry_run:
        preview = [[qid, idx, "missing" if (qid, idx) in missing else "error"] for qid, idx in targets[:30]]
        print(tabulate(preview, headers=["question_id", "devset_index", "reason"], tablefmt="grid"))
        if len(targets) > 30:
            print(f"... and {len(targets) - 30} more")
        print("[dry-run] No subprocess calls will be made.")
        return (0, 0)

    args_list = eval_args.split()
    succeeded = 0
    failed = 0
    total = len(targets)
    for i, (qid, devset_idx) in enumerate(targets, start=1):
        cmd = [
            "uv", "run", "scripts/run_evaluation.py",
            "--start", str(devset_idx),
            "--nb-samples", "1",
            "--continue", parent_run_id,
            *args_list,
        ]
        print(f"\n[{i}/{total}] qid={qid} (devset[{devset_idx}]): {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            succeeded += 1
            print("  OK (exit 0)")
        else:
            failed += 1
            print(f"  FAILED (exit {result.returncode}) -- continuing")

    print(f"\nBackfill summary: succeeded={succeeded}, failed={failed}, total={total}")
    return (succeeded, failed)


def _print_summary(client: MlflowClient, parent_run_id: str, label: str) -> None:
    infos = _load_run_infos(client, parent_run_id)
    counts: dict[str, int] = {}
    for info in infos:
        key = info.classification or f"<none/{info.status}>"
        counts[key] = counts.get(key, 0) + 1
    rows = sorted(counts.items(), key=lambda kv: -kv[1])

    missing, errors = find_missing_and_error_questions(client, parent_run_id)

    print(f"\n--- Summary ({label}) ---")
    print(tabulate(
        rows + [["TOTAL nested", len(infos)], ["distinct qids", len({i.question_id for i in infos})], ["DEVSET size", len(DEVSET)], ["missing", len(missing)], ["errors", len(errors)]],
        headers=["metric", "count"],
        tablefmt="grid",
    ))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--parent-run-id", required=True, help="Parent MLflow run id to backfill")
    parser.add_argument("--eval-args", required=True, help="Arguments forwarded to run_evaluation.py (e.g. '--system static --tools manual')")
    parser.add_argument("--phase", choices=["all", "dedupe", "backfill", "cleanup"], default="all", help="Phase(s) to run (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview actions without executing")
    args = parser.parse_args(list(argv) if argv is not None else None)

    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient()

    print("=" * 72)
    print("backfill_missing_questions")
    print(f"  parent_run_id : {args.parent_run_id}")
    print(f"  eval_args     : {args.eval_args}")
    print(f"  phase         : {args.phase}")
    print(f"  dry_run       : {args.dry_run}")
    print("=" * 72)

    _print_summary(client, args.parent_run_id, "before")

    if args.phase in ("all", "dedupe"):
        dedupe_phase(client, args.parent_run_id, args.dry_run, phase_label="dedupe")

    if args.phase in ("all", "backfill"):
        backfill_phase(client, args.parent_run_id, args.eval_args, args.dry_run)

    if args.phase in ("all", "cleanup"):
        dedupe_phase(client, args.parent_run_id, args.dry_run, phase_label="cleanup")

    _print_summary(client, args.parent_run_id, "after")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
