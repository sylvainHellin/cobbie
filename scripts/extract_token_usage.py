"""Extract token usage data from MLflow evaluation runs.

Produces:
  - outputs/eval/token_usage_summary.csv  (per-run aggregate)
  - outputs/eval/token_usage_per_question.csv  (per-question breakdown)

Usage:
    uv run scripts/extract_token_usage.py
"""

import csv
from pathlib import Path

import mlflow
from mlflow import MlflowClient

from src.analysis.data_extraction import (
    extract_run_data,
    fetch_nested_runs,
)
from src.config import MLFLOW_URI

# Run IDs from CLAUDE.md evaluation matrix
EVALUATION_RUNS = {
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

OUTPUT_DIR = Path("outputs/eval")

SUMMARY_COLUMNS = [
    "run_name",
    "num_questions",
    "total_input_tokens",
    "total_output_tokens",
    "total_tokens",
    "avg_tokens_per_question",
    "tokens_per_second",
]

QUESTION_COLUMNS = [
    "run_name",
    "question_id",
    "classification",
    "num_iterations",
    "cobbie_input_tokens",
    "cobbie_output_tokens",
    "verifier_input_tokens",
    "verifier_output_tokens",
    "total_input_tokens",
    "total_output_tokens",
    "cobbie_duration",
    "verifier_duration",
    "total_duration",
]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient(tracking_uri=MLFLOW_URI)

    summary_rows: list[dict] = []
    question_rows: list[dict] = []

    for run_name, run_id in sorted(EVALUATION_RUNS.items()):
        print(f"Processing {run_name}...")
        parent_run = client.get_run(run_id)
        experiment_id = parent_run.info.experiment_id
        metrics = parent_run.data.metrics

        # Aggregate summary
        summary_rows.append({
            "run_name": run_name,
            "num_questions": int(
                metrics.get("total_tokens", 0) / max(metrics.get("avg_tokens_per_question", 1), 1)
            ),
            "total_input_tokens": int(metrics.get("total_input_tokens", 0)),
            "total_output_tokens": int(metrics.get("total_output_tokens", 0)),
            "total_tokens": int(metrics.get("total_tokens", 0)),
            "avg_tokens_per_question": round(metrics.get("avg_tokens_per_question", 0), 1),
            "tokens_per_second": round(metrics.get("tokens_per_second", 0), 2),
        })

        # Per-question breakdown
        nested_runs = fetch_nested_runs(client, run_id, experiment_id)
        for nested_run in nested_runs:
            run_data = extract_run_data(nested_run)
            qid = run_data.get("question_id")
            if qid is None:
                continue
            question_rows.append({
                "run_name": run_name,
                "question_id": qid,
                "classification": run_data["classification"],
                "num_iterations": run_data["num_iterations"],
                "cobbie_input_tokens": int(run_data["cobbie_input_tokens"]),
                "cobbie_output_tokens": int(run_data["cobbie_output_tokens"]),
                "verifier_input_tokens": int(run_data["verifier_input_tokens"]),
                "verifier_output_tokens": int(run_data["verifier_output_tokens"]),
                "total_input_tokens": int(run_data["total_input_tokens"]),
                "total_output_tokens": int(run_data["total_output_tokens"]),
                "cobbie_duration": round(run_data["cobbie_duration"], 2),
                "verifier_duration": round(run_data["verifier_duration"], 2),
                "total_duration": round(run_data["total_duration"], 2),
            })

    # Write summary CSV
    summary_path = OUTPUT_DIR / "token_usage_summary.csv"
    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"\nWrote {summary_path}")

    # Write per-question CSV
    question_path = OUTPUT_DIR / "token_usage_per_question.csv"
    with open(question_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=QUESTION_COLUMNS)
        writer.writeheader()
        writer.writerows(question_rows)
    print(f"Wrote {question_path} ({len(question_rows)} rows)")


if __name__ == "__main__":
    main()
