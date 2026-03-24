#!/usr/bin/env python3
"""
Extract ACC Training Traces for Analysis

Retrieves MLflow traces for ACC training runs and extracts:
- Full prompt per iteration (includes accumulated feedback via `previous_attempts`)
- LLM answer (CodeAction or NewHelperFunction)
- Assessment data
- For all iterations per rule

Usage:
    uv run scripts/extract_acc_traces.py
    uv run scripts/extract_acc_traces.py --parent-run-id <run_id>
"""

import argparse
import json
import warnings
from pathlib import Path

import mlflow
from mlflow import MlflowClient
from mlflow.entities import Run, Trace

# Suppress deprecation warning for experiment_ids parameter (still functional)
warnings.filterwarnings("ignore", category=FutureWarning, message=".*experiment_ids.*")

# Default parent run ID from the plan
DEFAULT_PARENT_RUN_ID = "7ca5817aba3e40879b3205398d958102"
DEFAULT_EXPERIMENT = "ACC_Training_v2"
OUTPUT_DIR = Path("outputs/ec3")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract ACC training traces")
    parser.add_argument(
        "--parent-run-id",
        default=DEFAULT_PARENT_RUN_ID,
        help=f"Parent run ID (default: {DEFAULT_PARENT_RUN_ID})",
    )
    parser.add_argument(
        "--experiment",
        default=DEFAULT_EXPERIMENT,
        help=f"Experiment name (default: {DEFAULT_EXPERIMENT})",
    )
    parser.add_argument(
        "--mlflow-uri",
        default="http://127.0.0.1:5000",
        help="MLflow tracking URI",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR / "acc_traces.json",
        help="Output JSON file path",
    )
    return parser.parse_args()


def fetch_child_runs(client: MlflowClient, exp_id: str, parent_run_id: str) -> list[Run]:
    """Fetch all child runs of the parent run."""
    all_runs: list[Run] = []
    page_token = None
    while True:
        result = client.search_runs(
            experiment_ids=[exp_id],
            order_by=["start_time ASC"],
            max_results=1000,
            page_token=page_token,
        )
        all_runs.extend(result)
        page_token = result.token if hasattr(result, "token") else None
        if not page_token:
            break

    # Filter to child runs of the parent
    child_runs = [
        r for r in all_runs if r.data.tags.get("mlflow.parentRunId") == parent_run_id
    ]
    return child_runs


def parse_rule_info(run_name: str) -> tuple[int, str] | None:
    """Extract rule index and title from run_name like 'rule_4_504_2_non_uniform_risers_treads'."""
    parts = run_name.split("_", 2)  # ['rule', '4', '504_2_non_uniform...']
    if len(parts) >= 3 and parts[0] == "rule":
        try:
            rule_idx = int(parts[1])
            rule_title = parts[2]
            return rule_idx, rule_title
        except ValueError:
            return None
    return None


def extract_iterations_from_trace(trace: Trace) -> list[dict]:
    """Extract iteration data from a trace's spans."""
    iterations = []

    for span in trace.data.spans:
        # Look for LLM_call_N spans
        if span.name.startswith("LLM_call_"):
            try:
                iteration_num = int(span.name.split("_")[-1])
            except ValueError:
                continue

            iteration_data: dict = {
                "iteration": iteration_num,
                "full_prompt": None,
                "answer": None,
                "token_usage": {"input": 0, "output": 0},
            }

            # Extract full_prompt from attributes
            full_prompt = span.get_attribute("full_prompt")
            if full_prompt:
                iteration_data["full_prompt"] = full_prompt

            # Extract token usage from attributes
            input_tokens = span.get_attribute("input_tokens")
            output_tokens = span.get_attribute("output_tokens")
            if input_tokens is not None:
                iteration_data["token_usage"]["input"] = input_tokens
            if output_tokens is not None:
                iteration_data["token_usage"]["output"] = output_tokens

            # Extract answer from outputs
            outputs = span.outputs
            if outputs:
                result_type = outputs.get("result_type")
                if result_type == "CodeAction":
                    iteration_data["answer"] = {
                        "type": "CodeAction",
                        "thoughts": outputs.get("thoughts"),
                        "python_code": outputs.get("python_code"),
                    }
                elif result_type == "NewHelperFunction":
                    iteration_data["answer"] = {
                        "type": "NewHelperFunction",
                        "thoughts": outputs.get("thoughts"),
                        "function_implementation": outputs.get("function_implementation"),
                        "success": outputs.get("success"),
                    }

            iterations.append(iteration_data)

    # Sort by iteration number
    iterations.sort(key=lambda x: x["iteration"])
    return iterations


def extract_assessment_from_trace(trace: Trace) -> dict | None:
    """Extract assessment data from ACCToolAssessor span if present."""
    for span in trace.data.spans:
        if span.name == "ACCToolAssessor":
            outputs = span.outputs
            if outputs:
                return {
                    "thoughts": outputs.get("thoughts"),
                    "diagnosis": outputs.get("diagnosis"),
                    "improvement_hint": outputs.get("improvement_hint"),
                    "recommendation": outputs.get("recommendation"),
                    "confidence": outputs.get("confidence"),
                }
    return None


def extract_rule_data(exp_id: str, run: Run) -> dict | None:
    """Extract all trace data for a single rule run."""
    run_name = run.info.run_name
    if not run_name:
        return None

    rule_info = parse_rule_info(run_name)
    if not rule_info:
        return None

    rule_idx, rule_title = rule_info
    run_id = run.info.run_id

    # Search for traces associated with this run
    traces = mlflow.search_traces(
        experiment_ids=[exp_id],
        run_id=run_id,
        return_type="list",
        include_spans=True,
    )

    if not traces:
        print(f"  No traces found for {run_name}")
        return None

    # Use the first (and typically only) trace
    trace = traces[0]

    # Extract iterations and assessment
    iterations = extract_iterations_from_trace(trace)
    assessment = extract_assessment_from_trace(trace)

    return {
        "rule_idx": rule_idx,
        "rule_title": rule_title,
        "run_id": run_id,
        "run_name": run_name,
        "iterations": iterations,
        "assessment": assessment,
    }


def main() -> None:
    args = parse_args()

    # Set MLflow tracking URI
    mlflow.set_tracking_uri(args.mlflow_uri)
    client = MlflowClient()

    # Get experiment
    experiment = client.get_experiment_by_name(args.experiment)
    if experiment is None:
        print(f"Experiment '{args.experiment}' not found.")
        return
    exp_id = experiment.experiment_id
    print(f"Experiment: {experiment.name} (id={exp_id})")

    # Fetch child runs
    parent_run_id = args.parent_run_id
    print(f"Parent run: {parent_run_id}")
    print("Fetching child runs...")
    child_runs = fetch_child_runs(client, exp_id, parent_run_id)
    print(f"Found {len(child_runs)} child runs")

    # Extract data for each rule
    rules_data = []
    for run in child_runs:
        print(f"Processing: {run.info.run_name}")
        rule_data = extract_rule_data(exp_id, run)
        if rule_data:
            rules_data.append(rule_data)
            n_iters = len(rule_data["iterations"])
            has_assessment = rule_data["assessment"] is not None
            print(f"  -> {n_iters} iterations, assessment: {has_assessment}")

    # Sort by rule index
    rules_data.sort(key=lambda x: x["rule_idx"])

    # Build output structure
    output = {
        "parent_run_id": parent_run_id,
        "experiment": args.experiment,
        "rules": rules_data,
    }

    # Write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nExtracted {len(rules_data)} rules")
    print(f"Output saved to: {args.output}")


if __name__ == "__main__":
    main()
