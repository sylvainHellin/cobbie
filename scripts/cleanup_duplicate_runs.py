#!/usr/bin/env python3
"""
Clean up duplicate nested runs after retrying error/abstained questions.

For each of the 9 parent evaluation runs, finds duplicate nested runs
(multiple runs for the same question_id) and soft-deletes all but the latest
FINISHED one using mlflow.delete_run().

Usage:
    uv run scripts/cleanup_duplicate_runs.py --dry-run   # preview what would be deleted
    uv run scripts/cleanup_duplicate_runs.py              # actually delete duplicates
"""

import argparse

import mlflow
from mlflow import MlflowClient
from tabulate import tabulate

from src.analysis.data_extraction import fetch_nested_runs
from src.config import MLFLOW_URI

# The 9 parent run IDs
PARENT_RUNS: dict[str, str] = {
    "dynamic-manual-doc": "316c9f396ced42e6bfb14d86063a2cd8",
    "dynamic-auto-doc": "2f976d9502b14496857a5334acfcc1a6",
    "dynamic-None-doc": "4ab1263aff1c43a589a7e15bb2d67b48",
    "dynamic-manual-no_doc": "b18012e63c424101b139d91f1e3a4066",
    "dynamic-auto-no_doc": "437a86bd3b864de1863456ecb38d6821",
    "dynamic-None-no_doc": "389125f2d3654b718bf4606d306182cb",
    "static-manual": "77e41658053f458fadb33bb7a253bb50",
    "static-created": "b03fc6134c5847fe83da0b0c201db52d",
    "static-None": "d252e3844235428aa52ced2470b9b846",
}


def cleanup_parent_run(client: MlflowClient, run_name: str, parent_run_id: str, dry_run: bool) -> int:
    """Find and delete duplicate nested runs for a parent. Returns count of deleted runs."""
    parent_run = client.get_run(parent_run_id)
    experiment_id = parent_run.info.experiment_id

    nested_runs = fetch_nested_runs(client, parent_run_id, experiment_id)

    # Group nested runs by question_id
    by_qid: dict[int, list] = {}
    for run in nested_runs:
        qid = run.data.params.get("question_id")
        if qid is None:
            continue
        by_qid.setdefault(int(qid), []).append(run)

    deleted = 0
    for qid, runs in by_qid.items():
        if len(runs) <= 1:
            continue

        # Sort by end_time descending; prefer FINISHED runs
        runs.sort(key=lambda r: (
            r.info.status == "FINISHED",  # FINISHED = True sorts last -> reversed = first
            r.info.end_time or 0,
        ), reverse=True)

        # Keep the first (latest FINISHED), delete the rest
        keep = runs[0]
        to_delete = runs[1:]

        for run in to_delete:
            old_class = run.data.params.get("classification", "?")
            if dry_run:
                print(f"  [DRY RUN] Would delete qid={qid} run={run.info.run_id[:8]} "
                      f"(class={old_class}, status={run.info.status}), "
                      f"keeping run={keep.info.run_id[:8]}")
            else:
                client.delete_run(run.info.run_id)
            deleted += 1

    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up duplicate nested runs after retries.")
    parser.add_argument("--dry-run", action="store_true", help="Preview deletions without executing")
    args = parser.parse_args()

    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient()

    print("=" * 70)
    print("CLEANUP DUPLICATE NESTED RUNS")
    if args.dry_run:
        print("(DRY RUN — no changes will be made)")
    print("=" * 70)

    summary_rows: list[list] = []
    total_deleted = 0

    for run_name, parent_run_id in PARENT_RUNS.items():
        print(f"\n--- {run_name} ({parent_run_id[:8]}) ---")
        deleted = cleanup_parent_run(client, run_name, parent_run_id, args.dry_run)
        summary_rows.append([run_name, deleted])
        total_deleted += deleted

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(tabulate(summary_rows, headers=["Run", "Duplicates Removed"], tablefmt="grid"))
    print(f"\nTotal: {total_deleted} duplicate runs {'would be' if args.dry_run else ''} deleted")


if __name__ == "__main__":
    main()
