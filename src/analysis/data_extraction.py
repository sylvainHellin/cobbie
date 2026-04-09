"""Shared data-loading functions for evaluation run analysis.

Used by both the CLI script (analyze_evaluation_runs.py) and the Streamlit app.
"""

import re
from datetime import datetime, timezone

import pandas as pd
from mlflow import MlflowClient

from src.config import MLFLOW_URI
from src.db.query import fetch_question_data

CATEGORY_NAMES = {
    1: "Direct Property",
    2: "Aggregation",
    3: "Computation",
    4: "Estimation/Unavailable",
}


def sanitize_for_excel(text: str) -> str:
    """Sanitize text to remove characters that are illegal in Excel cells."""
    if not isinstance(text, str):
        return text

    illegal_chars = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
    return illegal_chars.sub("", text)


def fetch_nested_runs(client: MlflowClient, parent_run_id: str, experiment_id: str) -> list:
    """Fetch all nested runs for a given parent run."""
    nested_runs = client.search_runs(
        experiment_ids=[experiment_id],
        filter_string=f'tags.mlflow.parentRunId = "{parent_run_id}"',
        max_results=1000,
    )
    return nested_runs


def extract_run_data(run) -> dict:
    """Extract relevant data from a single nested run."""
    params = run.data.params
    metrics = run.data.metrics

    question_id = params.get("question_id")
    if question_id is not None:
        try:
            question_id = int(question_id)
        except (ValueError, TypeError):
            pass

    classification = params.get("classification", "unknown")
    if classification == "not_evaluated":
        classification = "unknown"

    # Re-derive classification from stored criteria to apply current 4-criteria logic
    # (faithfulness + completeness + transparency + relevance must all be "Yes")
    faithfulness = params.get("faithfulness", "not_evaluated")
    completeness = params.get("completeness", "not_evaluated")
    transparency = params.get("transparency", "not_evaluated")
    relevance = params.get("relevance", "not_evaluated")

    if classification not in ("unknown", "abstained"):
        if all(c == "Yes" for c in (faithfulness, completeness, transparency, relevance)):
            classification = "correct"
        else:
            classification = "wrong"

    data = {
        "question_id": question_id,
        "run_id": run.info.run_id,
        "experiment_id": run.info.experiment_id,
        "classification": classification,
        "cobbie_answer": params.get("answer", ""),
        "justification": params.get("justification", ""),
        "confidence": params.get("confidence", ""),
        "num_iterations": int(metrics.get("cobbie_calls_count", 0)),
        "cobbie_duration": (
            metrics.get("cobbie_duration", 0)
            or metrics.get("static_duration", 0)
            or metrics.get("static_doc_duration", 0)
            or metrics.get("baseline_duration", 0)
        ),
        "verifier_duration": metrics.get("verifier_duration", 0),
        "total_duration": (
            (
                metrics.get("cobbie_duration", 0)
                or metrics.get("static_duration", 0)
                or metrics.get("static_doc_duration", 0)
                or metrics.get("baseline_duration", 0)
            )
            + metrics.get("verifier_duration", 0)
        ),
        "cobbie_input_tokens": (
            metrics.get("cobbie_input_tokens", 0)
            or metrics.get("static_input_tokens", 0)
            or metrics.get("static_doc_input_tokens", 0)
            or metrics.get("baseline_input_tokens", 0)
        ),
        "cobbie_output_tokens": (
            metrics.get("cobbie_output_tokens", 0)
            or metrics.get("static_output_tokens", 0)
            or metrics.get("static_doc_output_tokens", 0)
            or metrics.get("baseline_output_tokens", 0)
        ),
        "verifier_input_tokens": metrics.get("verifier_input_tokens", 0),
        "verifier_output_tokens": metrics.get("verifier_output_tokens", 0),
        "total_input_tokens": metrics.get("total_input_tokens", 0),
        "total_output_tokens": metrics.get("total_output_tokens", 0),
        "success": metrics.get("success", 0) == 1,
        "faithfulness": faithfulness,
        "completeness": completeness,
        "transparency": transparency,
        "relevance": relevance,
    }

    return data


def build_dataframe(run_data_list: list[dict], question_data: dict[int, dict]) -> pd.DataFrame:
    """Combine MLflow run data with DB question data into a DataFrame."""
    rows = []

    for run_data in run_data_list:
        question_id = run_data["question_id"]
        if question_id is None:
            continue

        q_data = question_data.get(int(question_id), {})
        mlflow_url = f"{MLFLOW_URI}/#/experiments/{run_data['experiment_id']}/runs/{run_data['run_id']}"

        row = {
            "parent_run_name": run_data.get("parent_run_name", "Unknown"),
            "question_id": question_id,
            "question": sanitize_for_excel(q_data.get("question", "N/A")),
            "ground_truth": sanitize_for_excel(q_data.get("ground_truth", "N/A")),
            "category": q_data.get("category", "N/A"),
            "category_name": CATEGORY_NAMES.get(q_data.get("category", 0), "Unknown"),
            "project_name": sanitize_for_excel(q_data.get("project_name", "N/A")),
            "model_name": sanitize_for_excel(q_data.get("model_name", "N/A")),
            "classification": sanitize_for_excel(run_data["classification"]),
            "cobbie_answer": sanitize_for_excel(run_data["cobbie_answer"]),
            "justification": sanitize_for_excel(run_data["justification"]),
            "confidence": sanitize_for_excel(run_data["confidence"]),
            "faithfulness": run_data["faithfulness"],
            "completeness": run_data["completeness"],
            "transparency": run_data["transparency"],
            "relevance": run_data["relevance"],
            "num_iterations": run_data["num_iterations"],
            "cobbie_duration": run_data["cobbie_duration"],
            "verifier_duration": run_data["verifier_duration"],
            "total_duration": run_data["total_duration"],
            "cobbie_input_tokens": run_data["cobbie_input_tokens"],
            "cobbie_output_tokens": run_data["cobbie_output_tokens"],
            "verifier_input_tokens": run_data["verifier_input_tokens"],
            "verifier_output_tokens": run_data["verifier_output_tokens"],
            "total_input_tokens": run_data["total_input_tokens"],
            "total_output_tokens": run_data["total_output_tokens"],
            "success": run_data["success"],
            "mlflow_url": mlflow_url,
        }

        rows.append(row)

    return pd.DataFrame(rows)


def list_evaluation_runs(client: MlflowClient) -> list[dict]:
    """List all parent runs in the 'Evaluation' experiment.

    Returns list of dicts with keys: run_id, run_name, start_time, status.
    Sorted by start_time descending (most recent first).
    """
    experiment = client.get_experiment_by_name("Evaluation")
    if experiment is None:
        return []

    # Parent runs don't have a mlflow.parentRunId tag, but MLflow doesn't support
    # "tag not exists" filters. Paginate through all runs and filter client-side.
    result = []
    page_token = None
    while True:
        runs_page = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            order_by=["start_time DESC"],
            max_results=1000,
            page_token=page_token,
        )
        for run in runs_page:
            # Child (nested) runs have a question_id param; skip them
            if "question_id" not in run.data.params:
                result.append({
                    "run_id": run.info.run_id,
                    "run_name": run.data.tags.get("mlflow.runName", "Unknown"),
                    "start_time": datetime.fromtimestamp(run.info.start_time / 1000, tz=timezone.utc),
                    "status": run.info.status,
                })
        if not runs_page.token:
            break
        page_token = runs_page.token

    return result


def load_run_dataframe(client: MlflowClient, run_id: str) -> pd.DataFrame:
    """Fetch nested runs + DB data for a single parent run, return enriched DataFrame."""
    main_run = client.get_run(run_id)
    experiment_id = main_run.info.experiment_id
    run_name = main_run.data.tags.get("mlflow.runName", "Unknown")

    nested_runs = fetch_nested_runs(client, run_id, experiment_id)

    all_run_data = []
    for nested_run in nested_runs:
        run_data = extract_run_data(nested_run)
        run_data["parent_run_id"] = run_id
        run_data["parent_run_name"] = run_name
        all_run_data.append(run_data)

    question_ids = [r["question_id"] for r in all_run_data if r["question_id"] is not None]
    question_data = fetch_question_data(question_ids)

    return build_dataframe(all_run_data, question_data)
