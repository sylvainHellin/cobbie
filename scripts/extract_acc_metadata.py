"""Extract run-level metadata for all ACC rules from MLflow.

Queries MLflow for all child runs of the parent training run and writes
a single JSON file with metrics, params, tags, and status per rule.
Trace/iteration data is kept separately in acc_traces.json.

Usage:
    uv run scripts/extract_acc_metadata.py
    uv run scripts/extract_acc_metadata.py --parent-run-id <id>
"""

import argparse
import json
from pathlib import Path

import mlflow
from mlflow import MlflowClient

DEFAULT_PARENT_RUN_ID = "67849559d0fb4fceab2d88bb17ce4737"
DEFAULT_EXPERIMENT = "ACC_Training_v2"
OUTPUT_PATH = Path("outputs/ec3/acc_metadata.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract ACC rule metadata from MLflow")
    parser.add_argument("--parent-run-id", default=DEFAULT_PARENT_RUN_ID)
    parser.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    parser.add_argument("--mlflow-uri", default="http://127.0.0.1:5001")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
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

    rules = []
    for run in child_runs:
        info = parse_rule_info(run.info.run_name or "")
        if info is None:
            continue
        rule_idx, rule_title = info

        metrics = dict(run.data.metrics)
        params = dict(run.data.params)
        tags = {k: v for k, v in run.data.tags.items() if not k.startswith("mlflow.")}

        rules.append({
            "rule_idx": rule_idx,
            "rule_title": rule_title,
            "run_id": run.info.run_id,
            "run_name": run.info.run_name,
            "status": run.info.status,
            "start_time": run.info.start_time,
            "end_time": run.info.end_time,
            "metrics": metrics,
            "params": params,
            "tags": tags,
        })
        print(f"  [{rule_idx}] {rule_title}: {len(metrics)} metrics")

    rules.sort(key=lambda x: x["rule_idx"])

    output = {
        "parent_run_id": args.parent_run_id,
        "experiment": args.experiment,
        "rules": rules,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nExtracted metadata for {len(rules)} rules")
    print(f"Output saved to: {args.output}")


if __name__ == "__main__":
    main()
