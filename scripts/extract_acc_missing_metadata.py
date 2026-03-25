"""Extract metadata for ACC rules that are missing full traces.

Queries MLflow for child runs of the parent training run and writes
stub JSON files for rules not already in outputs/ec3/acc_traces/.

Usage:
    uv run scripts/extract_acc_missing_metadata.py
    uv run scripts/extract_acc_missing_metadata.py --parent-run-id <id>
"""

import argparse
import json
from pathlib import Path

import mlflow
from mlflow import MlflowClient

DEFAULT_PARENT_RUN_ID = "7ca5817aba3e40879b3205398d958102"
DEFAULT_EXPERIMENT = "ACC_Training_v2"
OUTPUT_DIR = Path("outputs/ec3/acc_traces")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract missing ACC rule metadata")
    parser.add_argument(
        "--parent-run-id",
        default=DEFAULT_PARENT_RUN_ID,
    )
    parser.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    parser.add_argument("--mlflow-uri", default="http://127.0.0.1:5000")
    return parser.parse_args()


def parse_rule_info(run_name: str) -> tuple[int, str] | None:
    parts = run_name.split("_", 2)
    if len(parts) >= 3 and parts[0] == "rule":
        try:
            return int(parts[1]), parts[2]
        except ValueError:
            return None
    return None


def main() -> None:
    args = parse_args()
    mlflow.set_tracking_uri(args.mlflow_uri)
    client = MlflowClient()

    experiment = client.get_experiment_by_name(args.experiment)
    if experiment is None:
        print(f"Experiment '{args.experiment}' not found.")
        return
    exp_id = experiment.experiment_id

    # Find existing trace files
    existing = {p.stem for p in OUTPUT_DIR.glob("*.json")}
    print(f"Existing traces: {len(existing)} files")

    # Fetch child runs
    all_runs = client.search_runs(
        experiment_ids=[exp_id],
        order_by=["start_time ASC"],
        max_results=1000,
    )
    child_runs = [
        r
        for r in all_runs
        if r.data.tags.get("mlflow.parentRunId") == args.parent_run_id
    ]
    print(f"Found {len(child_runs)} child runs for parent {args.parent_run_id}")

    wrote = 0
    for run in child_runs:
        info = parse_rule_info(run.info.run_name or "")
        if info is None:
            continue
        rule_idx, rule_title = info

        if rule_title in existing:
            continue

        run_id = run.info.run_id
        print(f"\nMissing: {rule_title} (run_id={run_id})")

        # Gather all available metadata
        metrics = dict(run.data.metrics)
        params = dict(run.data.params)
        tags = {k: v for k, v in run.data.tags.items() if not k.startswith("mlflow.")}

        output = {
            "parent_run_id": args.parent_run_id,
            "experiment": args.experiment,
            "rule_idx": rule_idx,
            "rule_title": rule_title,
            "run_id": run_id,
            "run_name": run.info.run_name,
            "status": run.info.status,
            "start_time": run.info.start_time,
            "end_time": run.info.end_time,
            "metrics": metrics,
            "params": params,
            "tags": tags,
            "iterations": [],  # No trace data available
            "assessment": None,  # No trace data available
            "note": "Full trace data unavailable — only run metadata extracted from MLflow.",
        }

        out_path = OUTPUT_DIR / f"{rule_title}.json"
        out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        print(f"  Wrote {out_path}")
        for k, v in metrics.items():
            print(f"  metric: {k} = {v}")
        wrote += 1

    print(f"\nWrote {wrote} metadata stubs")


if __name__ == "__main__":
    main()
