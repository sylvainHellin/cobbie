#!/usr/bin/env python3
"""
Generate a retry manifest for error/abstained questions across the 9 evaluation runs.

For dynamic-auto-doc: collects questions with classification == "abstained"
For all other 8 runs: collects questions with classification == "error"

Maps each question_id to its DEVSET index (needed for --start in run_evaluation.py)
and builds the eval CLI args for each run config.

Outputs JSON manifest to outputs/eval/retry_manifest.json.

Usage:
    uv run scripts/generate_retry_manifest.py
    uv run scripts/generate_retry_manifest.py --dry-run
"""

import argparse
import json

import mlflow
from mlflow import MlflowClient
from tabulate import tabulate

from src.analysis.data_extraction import extract_run_data, fetch_nested_runs
from src.config import MLFLOW_URI
from src.db import DEVSET

# --- Run configuration ---

RUN_CONFIG: dict[str, dict] = {
    "dynamic-manual-doc": {
        "run_id": "316c9f396ced42e6bfb14d86063a2cd8",
        "eval_args": "--system cobbie --tools manual --doc context7",
        "retry_classification": "error",
    },
    "dynamic-auto-doc": {
        "run_id": "2f976d9502b14496857a5334acfcc1a6",
        "eval_args": "--system cobbie --tools created --doc context7",
        "retry_classification": "abstained",  # special case: predates retry mechanism
    },
    "dynamic-None-doc": {
        "run_id": "4ab1263aff1c43a589a7e15bb2d67b48",
        "eval_args": "--system cobbie --doc context7",
        "retry_classification": "error",
    },
    "dynamic-manual-no_doc": {
        "run_id": "b18012e63c424101b139d91f1e3a4066",
        "eval_args": "--system cobbie --tools manual --doc custom",
        "retry_classification": "error",
    },
    "dynamic-auto-no_doc": {
        "run_id": "437a86bd3b864de1863456ecb38d6821",
        "eval_args": "--system cobbie --tools created --doc custom",
        "retry_classification": "error",
    },
    "dynamic-None-no_doc": {
        "run_id": "389125f2d3654b718bf4606d306182cb",
        "eval_args": "--system cobbie --doc custom",
        "retry_classification": "error",
    },
    "static-manual": {
        "run_id": "77e41658053f458fadb33bb7a253bb50",
        "eval_args": "--system static --tools manual",
        "retry_classification": "error",
    },
    "static-created": {
        "run_id": "b03fc6134c5847fe83da0b0c201db52d",
        "eval_args": "--system static --tools created",
        "retry_classification": "error",
    },
    "static-None": {
        "run_id": "d252e3844235428aa52ced2470b9b846",
        "eval_args": "--system static",
        "retry_classification": "error",
    },
}

OUTPUT_PATH = "outputs/eval/retry_manifest.json"


def build_qid_to_devset_index() -> dict[int, int]:
    """Build a mapping from question_id to DEVSET index."""
    return {q.id: idx for idx, q in enumerate(DEVSET)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate retry manifest for matrix errors.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary only, don't write JSON")
    args = parser.parse_args()

    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient()

    qid_to_idx = build_qid_to_devset_index()

    manifest: list[dict] = []
    summary_rows: list[list] = []

    for run_name, config in RUN_CONFIG.items():
        run_id = config["run_id"]
        target_class = config["retry_classification"]

        # Get experiment_id from the parent run
        parent_run = client.get_run(run_id)
        experiment_id = parent_run.info.experiment_id

        nested_runs = fetch_nested_runs(client, run_id, experiment_id)
        count = 0

        for nested_run in nested_runs:
            data = extract_run_data(nested_run)
            qid = data["question_id"]
            classification = data["classification"]

            if classification != target_class:
                continue
            if qid is None:
                continue

            qid_int = int(qid)
            devset_idx = qid_to_idx.get(qid_int)
            if devset_idx is None:
                print(f"  WARNING: question_id {qid_int} not found in DEVSET, skipping")
                continue

            manifest.append({
                "parent_run_id": run_id,
                "run_name": run_name,
                "question_id": qid_int,
                "devset_index": devset_idx,
                "old_classification": classification,
                "eval_args": config["eval_args"],
            })
            count += 1

        summary_rows.append([run_name, target_class, count, run_id[:8]])

    # Sort manifest by run_name then devset_index for predictable execution order
    manifest.sort(key=lambda x: (x["run_name"], x["devset_index"]))

    # Print summary
    print("\n" + "=" * 70)
    print("RETRY MANIFEST SUMMARY")
    print("=" * 70)
    print(tabulate(
        summary_rows,
        headers=["Run", "Retry Class", "Count", "Run ID"],
        tablefmt="grid",
    ))
    print(f"\nTotal questions to retry: {len(manifest)}")

    if args.dry_run:
        print("\n[Dry run] No file written.")
        return

    with open(OUTPUT_PATH, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
