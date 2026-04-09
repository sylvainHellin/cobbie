#!/usr/bin/env python3
"""
Clean duplicate nested runs and retry error ones for the static-doc evaluation.

Targets the static-doc parent run `0453b1c2f839495d9f6b7704a0854688`, whose
nested runs were polluted by z.ai API flakiness: some questions have duplicates,
others crashed mid-run or were classified as "error" because of failed LLM calls.

Three phases:
  1. dedupe  -- for each question_id, keep the best run, soft-delete duplicates
  2. retry   -- for each remaining "error-like" run, rerun the question via
                `run_evaluation.py --continue <parent_run_id>`
  3. cleanup -- re-run the same dedupe pass so successful retries replace the
                old error runs

A run is considered "error-like" when any of the following holds:
  - classification == "error" (LLM or verifier returned an AgentError)
  - status == FAILED           (process crashed before MLflow could close it)
  - FINISHED with no `classification` param logged
    (outer-exception handler in `run_evaluation.py`, run name ends in `_error`)

A run is considered "good" when classification in {correct, wrong, abstained}.

Dedupe rule (per user guidance):
  - If at least one duplicate is "good", keep the latest FINISHED good run.
  - Otherwise (all duplicates are errors), keep the latest FINISHED run
    (or the most recent one if none are FINISHED).
  - All other duplicates are soft-deleted via `client.delete_run()`.

Usage:
    uv run scripts/clean_and_retry_static_doc.py --dry-run
    uv run scripts/clean_and_retry_static_doc.py
    uv run scripts/clean_and_retry_static_doc.py --phase dedupe
    uv run scripts/clean_and_retry_static_doc.py --phase retry
    uv run scripts/clean_and_retry_static_doc.py --phase cleanup
    uv run scripts/clean_and_retry_static_doc.py --parent-run-id <id> --eval-args "--system static-doc --doc custom"

Prerequisites:
  - MLflow server must be running (see CLAUDE.md)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable, Optional

import mlflow
from mlflow import MlflowClient
from mlflow.entities import Run
from tabulate import tabulate

from src.analysis.data_extraction import fetch_nested_runs
from src.config import MLFLOW_URI
from src.db import DEVSET

DEFAULT_PARENT_RUN_ID = "0453b1c2f839495d9f6b7704a0854688"
DEFAULT_EVAL_ARGS = "--system static-doc --doc custom"
GOOD_CLASSIFICATIONS = {"correct", "wrong", "abstained"}


@dataclass
class RunInfo:
    """Lightweight view of an MLflow nested run for classification logic."""

    run_id: str
    question_id: int
    classification: Optional[str]
    status: str  # "FINISHED", "FAILED", "RUNNING", "KILLED", "SCHEDULED"
    end_time: int  # ms, 0 if missing
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
    # "error-like": classification == error, or FAILED, or FINISHED with no classification
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
    """Fetch all nested runs and convert to RunInfo."""
    parent_run = client.get_run(parent_run_id)
    nested = fetch_nested_runs(client, parent_run_id, parent_run.info.experiment_id)
    infos: list[RunInfo] = []
    for nested_run in nested:
        info = _classify_run(nested_run)
        if info is not None:
            infos.append(info)
    return infos


def _pick_survivor(runs: list[RunInfo]) -> RunInfo:
    """
    Pick the run to keep among duplicates for a single question_id.

    Rule: if any run is good, keep the latest FINISHED good run.
          Otherwise keep the latest FINISHED run (any classification).
          Break ties by end_time.
    """
    good_runs = [r for r in runs if r.is_good]
    candidates = good_runs if good_runs else runs

    # FINISHED first, then latest end_time.
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
    """
    Group nested runs by question_id and delete duplicates.

    Returns the number of runs deleted (or that would be deleted in dry-run).
    """
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
            rows.append(
                [
                    qid,
                    r.run_id[:8],
                    r.classification or "none",
                    r.status,
                    "-> keep " + survivor.run_id[:8],
                    action,
                ]
            )
            if not dry_run:
                client.delete_run(r.run_id)
            deleted += 1

    print(f"\n=== PHASE: {phase_label} ===")
    if rows:
        print(
            tabulate(
                rows,
                headers=["qid", "run_id", "classification", "status", "survivor", "action"],
                tablefmt="grid",
            )
        )
    else:
        print("No duplicates found.")
    print(
        f"{'Would delete' if dry_run else 'Deleted'}: {deleted} duplicate run(s)"
    )
    return deleted


def _build_qid_to_devset_index() -> dict[int, int]:
    """Map question_id -> DEVSET index (needed for --start in run_evaluation.py)."""
    return {q.id: idx for idx, q in enumerate(DEVSET)}


def retry_phase(
    client: MlflowClient,
    parent_run_id: str,
    eval_args: str,
    dry_run: bool,
) -> tuple[int, int]:
    """
    Find remaining error-like runs and re-evaluate them via run_evaluation.py --continue.

    Returns (succeeded, failed) subprocess counts.
    """
    infos = _load_run_infos(client, parent_run_id)

    # After dedupe, there should be at most one run per qid, but be defensive:
    # collect qids where the "current" run is still error-like.
    by_qid: dict[int, list[RunInfo]] = {}
    for info in infos:
        by_qid.setdefault(info.question_id, []).append(info)

    qid_to_idx = _build_qid_to_devset_index()

    targets: list[tuple[int, int]] = []  # (qid, devset_index)
    missing_in_devset: list[int] = []
    for qid, runs in sorted(by_qid.items()):
        if any(r.is_good for r in runs):
            continue
        if not any(r.is_error for r in runs):
            continue
        devset_idx = qid_to_idx.get(qid)
        if devset_idx is None:
            missing_in_devset.append(qid)
            continue
        targets.append((qid, devset_idx))

    print("\n=== PHASE: retry ===")
    print(f"Candidates to retry: {len(targets)}")
    if missing_in_devset:
        print(
            f"  WARNING: {len(missing_in_devset)} qids not found in DEVSET, skipping: "
            f"{missing_in_devset[:10]}{'...' if len(missing_in_devset) > 10 else ''}"
        )

    if not targets:
        return (0, 0)

    if dry_run:
        preview_rows = [[qid, idx] for qid, idx in targets[:20]]
        print(
            tabulate(
                preview_rows,
                headers=["question_id", "devset_index"],
                tablefmt="grid",
            )
        )
        if len(targets) > 20:
            print(f"... and {len(targets) - 20} more")
        print("[dry-run] No subprocess calls will be made.")
        return (0, 0)

    args_list = eval_args.split()
    succeeded = 0
    failed = 0
    total = len(targets)
    for i, (qid, devset_idx) in enumerate(targets, start=1):
        cmd = [
            "uv",
            "run",
            "scripts/run_evaluation.py",
            "--start",
            str(devset_idx),
            "--nb-samples",
            "1",
            "--continue",
            parent_run_id,
            *args_list,
        ]
        print(
            f"\n[{i}/{total}] Retrying qid={qid} (devset[{devset_idx}]): "
            f"{' '.join(cmd)}"
        )
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            succeeded += 1
            print("  OK (exit 0)")
        else:
            failed += 1
            print(f"  FAILED (exit {result.returncode}) -- continuing")

    print(f"\nRetry summary: succeeded={succeeded}, failed={failed}, total={total}")
    return (succeeded, failed)


def _print_classification_summary(client: MlflowClient, parent_run_id: str, label: str) -> None:
    infos = _load_run_infos(client, parent_run_id)
    counts: dict[str, int] = {}
    for info in infos:
        key = info.classification or f"<none/{info.status}>"
        counts[key] = counts.get(key, 0) + 1
    rows = sorted(counts.items(), key=lambda kv: -kv[1])
    print(f"\n--- Classification summary ({label}) ---")
    print(
        tabulate(
            rows + [["TOTAL", len(infos)], ["distinct qids", len({i.question_id for i in infos})]],
            headers=["classification", "count"],
            tablefmt="grid",
        )
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parent-run-id",
        default=DEFAULT_PARENT_RUN_ID,
        help=f"Parent MLflow run id to clean (default: {DEFAULT_PARENT_RUN_ID})",
    )
    parser.add_argument(
        "--eval-args",
        default=DEFAULT_EVAL_ARGS,
        help=f"Arguments forwarded to run_evaluation.py (default: '{DEFAULT_EVAL_ARGS}')",
    )
    parser.add_argument(
        "--phase",
        choices=["all", "dedupe", "retry", "cleanup"],
        default="all",
        help="Phase(s) to run. 'all' = dedupe -> retry -> cleanup (default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without deleting runs or starting subprocesses",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient()

    print("=" * 72)
    print("clean_and_retry_static_doc")
    print(f"  parent_run_id : {args.parent_run_id}")
    print(f"  eval_args     : {args.eval_args}")
    print(f"  phase         : {args.phase}")
    print(f"  dry_run       : {args.dry_run}")
    print("=" * 72)

    _print_classification_summary(client, args.parent_run_id, "before")

    if args.phase in ("all", "dedupe"):
        dedupe_phase(client, args.parent_run_id, args.dry_run, phase_label="dedupe")

    if args.phase in ("all", "retry"):
        retry_phase(client, args.parent_run_id, args.eval_args, args.dry_run)

    if args.phase in ("all", "cleanup"):
        dedupe_phase(client, args.parent_run_id, args.dry_run, phase_label="cleanup")

    _print_classification_summary(client, args.parent_run_id, "after")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
