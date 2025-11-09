#!/usr/bin/env python3
"""
Analyze Evaluation Runs from MLflow

This script extracts detailed evaluation run data from MLflow, enriches it with database
information, and generates an Excel report with comprehensive statistics.

Usage:
    uv run scripts/analyze_evaluation_runs.py --run-ids <run_id1> <run_id2> ...
    uv run scripts/analyze_evaluation_runs.py --run-ids c0f5d69f17b3400093fa63204c70adc3
"""

import argparse
import re
import sqlite3
from datetime import datetime
from typing import Dict, List

import mlflow
import pandas as pd
from mlflow import MlflowClient
from tabulate import tabulate

from src.config import DB_PATH, MLFLOW_URI

# Constants
REPORTS_DIR = "reports"
CATEGORY_NAMES = {
    1: "Direct Property",
    2: "Aggregation",
    3: "Computation",
    4: "Estimation/Unavailable",
}


def sanitize_for_excel(text: str) -> str:
    """
    Sanitize text to remove characters that are illegal in Excel cells.

    Excel/openpyxl doesn't allow certain control characters (0x00-0x1F except tab, newline, carriage return).

    Args:
        text: Input text string

    Returns:
        Sanitized text safe for Excel
    """
    if not isinstance(text, str):
        return text

    # Remove illegal XML characters (Excel uses XML internally)
    # Keep only: tab (0x09), newline (0x0A), carriage return (0x0D), and printable characters (>= 0x20)
    illegal_chars = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')
    return illegal_chars.sub('', text)


def fetch_nested_runs(client: MlflowClient, parent_run_id: str, experiment_id: str) -> List:
    """
    Fetch all nested runs for a given parent run.

    Args:
        client: MLflow client instance
        parent_run_id: ID of the parent evaluation run
        experiment_id: ID of the experiment

    Returns:
        List of nested run objects
    """
    nested_runs = client.search_runs(
        experiment_ids=[experiment_id],
        filter_string=f'tags.mlflow.parentRunId = "{parent_run_id}"',
        max_results=1000,  # Adjust if you have more questions
    )
    return nested_runs


def extract_run_data(run) -> Dict:
    """
    Extract relevant data from a single nested run.

    Args:
        run: MLflow run object

    Returns:
        Dictionary with extracted run data
    """
    params = run.data.params
    metrics = run.data.metrics
    tags = run.data.tags

    # Get question ID from run name (e.g., "question_909" -> 909)
    run_name = tags.get("mlflow.runName", "")
    question_id = None
    if run_name.startswith("question_"):
        try:
            question_id = int(run_name.split("_")[1])
        except (IndexError, ValueError):
            question_id = params.get("question_id")
    else:
        question_id = params.get("question_id")

    # Get classification from parameters
    classification = params.get("classification", "unknown")
    if classification == "not_evaluated":
        classification = "unknown"

    # Extract all relevant data
    data = {
        "question_id": question_id,
        "run_id": run.info.run_id,
        "experiment_id": run.info.experiment_id,
        "classification": classification,
        # Answer and justification from parameters
        "cobbie_answer": params.get("answer", ""),
        "justification": params.get("justification", ""),
        "confidence": params.get("confidence", ""),
        # Latency metrics
        "cobbie_duration": metrics.get("cobbie_duration", 0),
        "verifier_duration": metrics.get("verifier_duration", 0),
        "total_duration": metrics.get("cobbie_duration", 0) + metrics.get("verifier_duration", 0),
        # Token metrics
        "cobbie_input_tokens": metrics.get("cobbie_input_tokens", 0),
        "cobbie_output_tokens": metrics.get("cobbie_output_tokens", 0),
        "verifier_input_tokens": metrics.get("verifier_input_tokens", 0),
        "verifier_output_tokens": metrics.get("verifier_output_tokens", 0),
        "total_input_tokens": metrics.get("total_input_tokens", 0),
        "total_output_tokens": metrics.get("total_output_tokens", 0),
        # Success flag
        "success": metrics.get("success", 0) == 1,
    }

    return data


def fetch_question_data(question_ids: List[int]) -> Dict[int, Dict]:
    """
    Fetch question data from the database.

    Args:
        question_ids: List of question IDs to fetch

    Returns:
        Dictionary mapping question_id to question data
    """
    if not question_ids:
        return {}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Build query with JOIN to get project and model names
    placeholders = ",".join("?" * len(question_ids))
    query = f"""
        SELECT
            ib.id,
            ib.question,
            ib.ground_truth,
            ib.category,
            im.project_name,
            im.model_name,
            im.model_path
        FROM ifc_bench ib
        LEFT JOIN ifcmodels im ON ib.ifc_id = im.id
        WHERE ib.id IN ({placeholders})
    """

    cursor.execute(query, question_ids)
    rows = cursor.fetchall()
    conn.close()

    # Build dictionary
    question_data = {}
    for row in rows:
        question_data[row[0]] = {
            "question": row[1],
            "ground_truth": row[2],
            "category": row[3],
            "project_name": row[4],
            "model_name": row[5],
            "model_path": row[6],
        }

    return question_data


def build_dataframe(run_data_list: List[Dict], question_data: Dict[int, Dict]) -> pd.DataFrame:
    """
    Build a pandas DataFrame from run data and question data.

    Args:
        run_data_list: List of dictionaries with run data
        question_data: Dictionary mapping question_id to question data

    Returns:
        Pandas DataFrame with enriched data
    """
    rows = []

    for run_data in run_data_list:
        question_id = run_data["question_id"]
        if question_id is None:
            continue

        # Get question data from database
        q_data = question_data.get(int(question_id), {})

        # Build MLflow URL
        mlflow_url = f"{MLFLOW_URI}/#/experiments/{run_data['experiment_id']}/runs/{run_data['run_id']}"

        # Combine all data (sanitize text fields for Excel compatibility)
        row = {
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

    df = pd.DataFrame(rows)
    return df


def calculate_statistics(df: pd.DataFrame) -> Dict:
    """
    Calculate comprehensive statistics from the DataFrame.

    Args:
        df: DataFrame with evaluation run data

    Returns:
        Dictionary with statistics
    """
    stats = {}

    # Basic counts
    stats["total_questions"] = len(df)
    stats["successful_evaluations"] = df["success"].sum()
    stats["failed_evaluations"] = len(df) - df["success"].sum()

    # Classification metrics (only for successful evaluations)
    successful_df = df[df["success"]]
    stats["correct_answers"] = (successful_df["classification"] == "correct").sum()
    stats["wrong_answers"] = (successful_df["classification"] == "wrong").sum()
    stats["abstained_answers"] = (successful_df["classification"] == "abstained").sum()

    # Accuracy metrics
    evaluated = stats["correct_answers"] + stats["wrong_answers"]
    stats["accuracy"] = stats["correct_answers"] / evaluated if evaluated > 0 else 0
    stats["abstention_rate"] = stats["abstained_answers"] / len(successful_df) if len(successful_df) > 0 else 0

    # Latency statistics
    stats["avg_latency"] = df["total_duration"].mean()
    stats["median_latency"] = df["total_duration"].median()
    stats["max_latency"] = df["total_duration"].max()
    stats["min_latency"] = df["total_duration"].min()
    stats["avg_cobbie_duration"] = df["cobbie_duration"].mean()
    stats["avg_verifier_duration"] = df["verifier_duration"].mean()

    # Token statistics
    stats["total_input_tokens"] = df["total_input_tokens"].sum()
    stats["total_output_tokens"] = df["total_output_tokens"].sum()
    stats["total_tokens"] = stats["total_input_tokens"] + stats["total_output_tokens"]
    stats["avg_input_tokens"] = df["total_input_tokens"].mean()
    stats["avg_output_tokens"] = df["total_output_tokens"].mean()
    stats["avg_tokens_per_question"] = (df["total_input_tokens"] + df["total_output_tokens"]).mean()

    # Tokens per second (throughput)
    total_time = df["total_duration"].sum()
    stats["tokens_per_second"] = stats["total_output_tokens"] / total_time if total_time > 0 else 0

    # Category breakdown
    stats["by_category"] = {}
    for category in df["category"].unique():
        if category == "N/A":
            continue
        category_df = df[df["category"] == category]
        category_successful = category_df[category_df["success"]]

        cat_correct = (category_successful["classification"] == "correct").sum()
        cat_wrong = (category_successful["classification"] == "wrong").sum()
        cat_evaluated = cat_correct + cat_wrong
        cat_accuracy = cat_correct / cat_evaluated if cat_evaluated > 0 else 0

        stats["by_category"][category] = {
            "count": len(category_df),
            "correct": cat_correct,
            "wrong": cat_wrong,
            "abstained": (category_successful["classification"] == "abstained").sum(),
            "accuracy": cat_accuracy,
            "avg_latency": category_df["total_duration"].mean(),
            "avg_tokens": (category_df["total_input_tokens"] + category_df["total_output_tokens"]).mean(),
        }

    # Project breakdown
    stats["by_project"] = {}
    for project in df["project_name"].unique():
        if project == "N/A" or pd.isna(project):
            continue
        project_df = df[df["project_name"] == project]
        project_successful = project_df[project_df["success"]]

        proj_correct = (project_successful["classification"] == "correct").sum()
        proj_wrong = (project_successful["classification"] == "wrong").sum()
        proj_evaluated = proj_correct + proj_wrong
        proj_accuracy = proj_correct / proj_evaluated if proj_evaluated > 0 else 0

        stats["by_project"][project] = {
            "count": len(project_df),
            "correct": proj_correct,
            "wrong": proj_wrong,
            "abstained": (project_successful["classification"] == "abstained").sum(),
            "accuracy": proj_accuracy,
            "avg_latency": project_df["total_duration"].mean(),
            "avg_tokens": (project_df["total_input_tokens"] + project_df["total_output_tokens"]).mean(),
        }

    return stats


def print_statistics(stats: Dict) -> None:
    """
    Print formatted statistics to console.

    Args:
        stats: Dictionary with statistics
    """
    print("\n" + "=" * 80)
    print("EVALUATION RUN ANALYSIS - STATISTICS")
    print("=" * 80)

    # Overall metrics
    print("\n📊 Overall Metrics:")
    print(f"  Total Questions: {stats['total_questions']}")
    print(f"  Successful Evaluations: {stats['successful_evaluations']}")
    print(f"  Failed Evaluations: {stats['failed_evaluations']}")
    print(f"  Correct Answers: {stats['correct_answers']}")
    print(f"  Wrong Answers: {stats['wrong_answers']}")
    print(f"  Abstained Answers: {stats['abstained_answers']}")
    print(f"  Accuracy: {stats['accuracy']:.2%}")
    print(f"  Abstention Rate: {stats['abstention_rate']:.2%}")

    # Category breakdown
    print("\n📂 Performance by Category:")
    category_table = []
    for category, cat_stats in sorted(stats["by_category"].items()):
        category_table.append(
            [
                f"{category} - {CATEGORY_NAMES.get(category, 'Unknown')}",
                cat_stats["count"],
                f"{cat_stats['accuracy']:.2%}",
                cat_stats["correct"],
                cat_stats["wrong"],
                cat_stats["abstained"],
                f"{cat_stats['avg_latency']:.1f}s",
                f"{cat_stats['avg_tokens']:.0f}",
            ]
        )
    print(
        tabulate(
            category_table,
            headers=["Category", "Count", "Accuracy", "Correct", "Wrong", "Abstained", "Avg Latency", "Avg Tokens"],
            tablefmt="grid",
        )
    )

    # Project breakdown
    if stats["by_project"]:
        print("\n🏗️  Performance by Project:")
        project_table = []
        for project, proj_stats in sorted(stats["by_project"].items()):
            project_table.append(
                [
                    project,
                    proj_stats["count"],
                    f"{proj_stats['accuracy']:.2%}",
                    proj_stats["correct"],
                    proj_stats["wrong"],
                    proj_stats["abstained"],
                    f"{proj_stats['avg_latency']:.1f}s",
                    f"{proj_stats['avg_tokens']:.0f}",
                ]
            )
        print(
            tabulate(
                project_table,
                headers=["Project", "Count", "Accuracy", "Correct", "Wrong", "Abstained", "Avg Latency", "Avg Tokens"],
                tablefmt="grid",
            )
        )

    # Latency statistics
    print("\n⏱️  Latency Statistics:")
    print(f"  Average Total: {stats['avg_latency']:.2f}s")
    print(f"  Median Total: {stats['median_latency']:.2f}s")
    print(f"  Min: {stats['min_latency']:.2f}s")
    print(f"  Max: {stats['max_latency']:.2f}s")
    print(f"  Average COBBIE: {stats['avg_cobbie_duration']:.2f}s")
    print(f"  Average Verifier: {stats['avg_verifier_duration']:.2f}s")

    # Token statistics
    print("\n🎯 Token Usage:")
    print(f"  Total Input Tokens: {stats['total_input_tokens']:,}")
    print(f"  Total Output Tokens: {stats['total_output_tokens']:,}")
    print(f"  Total Tokens: {stats['total_tokens']:,}")
    print(f"  Average Input Tokens/Question: {stats['avg_input_tokens']:.0f}")
    print(f"  Average Output Tokens/Question: {stats['avg_output_tokens']:.0f}")
    print(f"  Average Total Tokens/Question: {stats['avg_tokens_per_question']:.0f}")
    print(f"  Throughput: {stats['tokens_per_second']:.1f} tokens/second")

    print("\n" + "=" * 80)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Analyze MLflow evaluation runs and generate Excel report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze specific runs
  uv run scripts/analyze_evaluation_runs.py --run-ids c0f5d69f17b3400093fa63204c70adc3 21d1966df8dc47d3a5753cbb9bbbb0e3

  # Analyze a single run
  uv run scripts/analyze_evaluation_runs.py --run-ids c0f5d69f17b3400093fa63204c70adc3
        """,
    )

    parser.add_argument(
        "--run-ids",
        nargs="+",
        required=True,
        help="MLflow run IDs to analyze (space-separated)",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("MLflow Evaluation Run Analysis")
    print("=" * 80)
    print(f"\nAnalyzing {len(args.run_ids)} run(s)...")

    # Setup MLflow
    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient()

    # Collect all run data
    all_run_data = []

    for run_id in args.run_ids:
        print(f"\nProcessing run: {run_id}")

        # Get main run info
        try:
            main_run = client.get_run(run_id)
            experiment_id = main_run.info.experiment_id
            run_name = main_run.data.tags.get("mlflow.runName", "Unknown")
            print(f"  Run Name: {run_name}")
            print(f"  Experiment ID: {experiment_id}")

            # Fetch nested runs
            nested_runs = fetch_nested_runs(client, run_id, experiment_id)
            print(f"  Found {len(nested_runs)} nested runs (questions)")

            # Extract data from each nested run
            for nested_run in nested_runs:
                run_data = extract_run_data(nested_run)
                all_run_data.append(run_data)

        except Exception as e:
            print(f"  Error processing run {run_id}: {e}")
            continue

    print(f"\nTotal questions collected: {len(all_run_data)}")

    # Fetch question data from database
    question_ids = [r["question_id"] for r in all_run_data if r["question_id"] is not None]
    print(f"Fetching data for {len(question_ids)} questions from database...")
    question_data = fetch_question_data(question_ids)

    # Build DataFrame
    print("Building DataFrame...")
    df = build_dataframe(all_run_data, question_data)

    # Calculate statistics
    print("Calculating statistics...")
    stats = calculate_statistics(df)

    # Print statistics
    print_statistics(stats)

    # Export to Excel
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{REPORTS_DIR}/evaluation_analysis_{timestamp}.xlsx"
    print(f"\nExporting to Excel: {output_filename}")

    with pd.ExcelWriter(output_filename, engine="openpyxl") as writer:
        # Write main data
        df.to_excel(writer, sheet_name="Evaluation Data", index=False)

        # Write statistics summary
        stats_data = {
            "Metric": [
                "Total Questions",
                "Successful Evaluations",
                "Failed Evaluations",
                "Correct Answers",
                "Wrong Answers",
                "Abstained Answers",
                "Accuracy",
                "Abstention Rate",
                "Average Latency (s)",
                "Median Latency (s)",
                "Average COBBIE Duration (s)",
                "Average Verifier Duration (s)",
                "Total Input Tokens",
                "Total Output Tokens",
                "Total Tokens",
                "Avg Tokens/Question",
                "Tokens/Second",
            ],
            "Value": [
                stats["total_questions"],
                stats["successful_evaluations"],
                stats["failed_evaluations"],
                stats["correct_answers"],
                stats["wrong_answers"],
                stats["abstained_answers"],
                f"{stats['accuracy']:.2%}",
                f"{stats['abstention_rate']:.2%}",
                f"{stats['avg_latency']:.2f}",
                f"{stats['median_latency']:.2f}",
                f"{stats['avg_cobbie_duration']:.2f}",
                f"{stats['avg_verifier_duration']:.2f}",
                f"{stats['total_input_tokens']:,}",
                f"{stats['total_output_tokens']:,}",
                f"{stats['total_tokens']:,}",
                f"{stats['avg_tokens_per_question']:.0f}",
                f"{stats['tokens_per_second']:.1f}",
            ],
        }
        stats_df = pd.DataFrame(stats_data)
        stats_df.to_excel(writer, sheet_name="Summary", index=False)

        # Write category breakdown
        category_data = []
        for category, cat_stats in sorted(stats["by_category"].items()):
            category_data.append(
                {
                    "Category": category,
                    "Category Name": CATEGORY_NAMES.get(category, "Unknown"),
                    "Count": cat_stats["count"],
                    "Correct": cat_stats["correct"],
                    "Wrong": cat_stats["wrong"],
                    "Abstained": cat_stats["abstained"],
                    "Accuracy": f"{cat_stats['accuracy']:.2%}",
                    "Avg Latency (s)": f"{cat_stats['avg_latency']:.2f}",
                    "Avg Tokens": f"{cat_stats['avg_tokens']:.0f}",
                }
            )
        category_df = pd.DataFrame(category_data)
        category_df.to_excel(writer, sheet_name="By Category", index=False)

        # Write project breakdown
        if stats["by_project"]:
            project_data = []
            for project, proj_stats in sorted(stats["by_project"].items()):
                project_data.append(
                    {
                        "Project": project,
                        "Count": proj_stats["count"],
                        "Correct": proj_stats["correct"],
                        "Wrong": proj_stats["wrong"],
                        "Abstained": proj_stats["abstained"],
                        "Accuracy": f"{proj_stats['accuracy']:.2%}",
                        "Avg Latency (s)": f"{proj_stats['avg_latency']:.2f}",
                        "Avg Tokens": f"{proj_stats['avg_tokens']:.0f}",
                    }
                )
            project_df = pd.DataFrame(project_data)
            project_df.to_excel(writer, sheet_name="By Project", index=False)

    print(f"✅ Export complete: {output_filename}")
    print("\nAnalysis complete!")


if __name__ == "__main__":
    main()
