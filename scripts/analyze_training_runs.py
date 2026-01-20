#!/usr/bin/env python3
"""
Analyze Training Run from MLflow

This script extracts detailed training run data from MLflow, enriches it with database
information, and generates an Excel report with comprehensive statistics.

Usage:
    uv run scripts/analyze_training_runs.py --run-id <run_id>
    uv run scripts/analyze_training_runs.py --run-id c0f5d69f17b3400093fa63204c70adc3
"""

import argparse
import re
import sqlite3
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
    # Remove illegal XML characters (Excel uses XML internally)
    # Keep only: tab (0x09), newline (0x0A), carriage return (0x0D), and printable characters (>= 0x20)
    illegal_chars = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')
    return illegal_chars.sub('', text)


def fetch_nested_runs(client: MlflowClient, parent_run_id: str, experiment_id: str) -> List:
    """
    Fetch all nested runs for a given parent run.

    Args:
        client: MLflow client instance
        parent_run_id: ID of the parent training run
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

    # Get question ID from run name (e.g., "question_203_909" -> 909)
    # First digit in the question index (from the trainset)
    run_name = tags.get("mlflow.runName", "")
    question_id = None
    if run_name.startswith("question_"):
        try:
            question_id = int(run_name.split("_")[2])
        except (IndexError, ValueError):
            question_id = params.get("question_id")
    else:
        question_id = params.get("question_id")

    # Determine classification from metrics
    classification = "unknown"
    if metrics.get("answer_correct", 0) == 1:
        classification = "correct"
    elif metrics.get("answer_wrong", 0) == 1:
        classification = "wrong"
    elif metrics.get("answer_abstained", 0) == 1:
        classification = "abstained"

    # Determine tool name (if tool was created or updated)
    tool_name = None
    # Tool name is not directly stored in metrics/params in the current implementation
    # It would be in context.tool_name but not logged to MLflow
    # We'll leave this as None for now

    # Extract all relevant data
    data = {
        "question_id": question_id,
        "run_id": run.info.run_id,
        "experiment_id": run.info.experiment_id,
        "classification": classification,
        # Answer and justification from parameters
        "cobbie_answer": params.get("cobbie_answer", ""),
        "justification": params.get("justification", ""),
        # Latency metrics
        "total_latency": metrics.get("total_duration", 0),
        "cobbie_duration": metrics.get("cobbie_duration", 0),
        "verify_duration": metrics.get("verify_duration", 0),
        "identify_tool_duration": metrics.get("identify_tool_duration", 0),
        "create_tool_duration": metrics.get("create_tool_duration", 0),
        "identify_faulty_duration": metrics.get("identify_faulty_duration", 0),
        "debug_tool_duration": metrics.get("debug_tool_duration", 0),
        "test_cobbie_duration": metrics.get("test_cobbie_duration", 0),
        "test_verify_duration": metrics.get("test_verify_duration", 0),
        "tool_assessment_duration": metrics.get("tool_assessment_duration", 0),
        # Token metrics
        "input_tokens_total": metrics.get("cobbie_input_tokens", 0)
        + metrics.get("verify_input_tokens", 0)
        + metrics.get("identify_tool_input_tokens", 0)
        + metrics.get("create_tool_input_tokens", 0)
        + metrics.get("identify_faulty_input_tokens", 0)
        + metrics.get("debug_tool_input_tokens", 0)
        + metrics.get("test_cobbie_input_tokens", 0)
        + metrics.get("test_verify_input_tokens", 0)
        + metrics.get("tool_assessment_input_tokens", 0),
        "output_tokens_total": metrics.get("cobbie_output_tokens", 0)
        + metrics.get("verify_output_tokens", 0)
        + metrics.get("identify_tool_output_tokens", 0)
        + metrics.get("create_tool_output_tokens", 0)
        + metrics.get("identify_faulty_output_tokens", 0)
        + metrics.get("debug_tool_output_tokens", 0)
        + metrics.get("test_cobbie_output_tokens", 0)
        + metrics.get("test_verify_output_tokens", 0)
        + metrics.get("tool_assessment_output_tokens", 0),
        # Cobbie-specific tokens
        "cobbie_input_tokens": metrics.get("cobbie_input_tokens", 0),
        "cobbie_output_tokens": metrics.get("cobbie_output_tokens", 0),
        # Verify-specific tokens
        "verify_input_tokens": metrics.get("verify_input_tokens", 0),
        "verify_output_tokens": metrics.get("verify_output_tokens", 0),
        # Tool operations
        "tool_created": metrics.get("tool_created", 0) == 1,
        "tool_updated": metrics.get("tool_updated", 0) == 1,
        "tool_saved": metrics.get("tool_saved", 0) == 1,
        "tool_name": tool_name,
        # Tool assessment
        "tool_was_used": metrics.get("tool_was_used", 0) == 1,
        "tool_usage_helpful": metrics.get("tool_usage_helpful", 0) == 1,
        "tool_usage_harmful": metrics.get("tool_usage_harmful", 0) == 1,
        "tool_recommendation_keep": metrics.get("tool_recommendation_keep", 0) == 1,
        "tool_recommendation_discard": metrics.get("tool_recommendation_discard", 0) == 1,
        # Error flag
        "error": metrics.get("error", 0) == 1,
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
            "total_latency": run_data["total_latency"],
            "cobbie_duration": run_data["cobbie_duration"],
            "verify_duration": run_data["verify_duration"],
            "identify_tool_duration": run_data["identify_tool_duration"],
            "create_tool_duration": run_data["create_tool_duration"],
            "identify_faulty_duration": run_data["identify_faulty_duration"],
            "debug_tool_duration": run_data["debug_tool_duration"],
            "test_cobbie_duration": run_data["test_cobbie_duration"],
            "test_verify_duration": run_data["test_verify_duration"],
            "tool_assessment_duration": run_data["tool_assessment_duration"],
            "input_tokens_total": run_data["input_tokens_total"],
            "output_tokens_total": run_data["output_tokens_total"],
            "cobbie_input_tokens": run_data["cobbie_input_tokens"],
            "cobbie_output_tokens": run_data["cobbie_output_tokens"],
            "verify_input_tokens": run_data["verify_input_tokens"],
            "verify_output_tokens": run_data["verify_output_tokens"],
            "tool_created": run_data["tool_created"],
            "tool_updated": run_data["tool_updated"],
            "tool_saved": run_data["tool_saved"],
            "tool_name": sanitize_for_excel(run_data["tool_name"]) if run_data["tool_name"] else None,
            "tool_was_used": run_data["tool_was_used"],
            "tool_usage_helpful": run_data["tool_usage_helpful"],
            "tool_usage_harmful": run_data["tool_usage_harmful"],
            "tool_recommendation_keep": run_data["tool_recommendation_keep"],
            "tool_recommendation_discard": run_data["tool_recommendation_discard"],
            "error": run_data["error"],
            "mlflow_url": mlflow_url,
        }

        rows.append(row)

    df = pd.DataFrame(rows)
    return df


def calculate_statistics(df: pd.DataFrame) -> Dict:
    """
    Calculate comprehensive statistics from the DataFrame.

    Args:
        df: DataFrame with training run data

    Returns:
        Dictionary with statistics
    """
    stats = {}

    # Basic counts
    stats["total_questions"] = len(df)
    stats["correct_answers"] = (df["classification"] == "correct").sum()
    stats["wrong_answers"] = (df["classification"] == "wrong").sum()
    stats["abstained_answers"] = (df["classification"] == "abstained").sum()

    # Accuracy metrics
    evaluated = stats["correct_answers"] + stats["wrong_answers"]
    stats["accuracy"] = stats["correct_answers"] / evaluated if evaluated > 0 else 0
    stats["abstention_rate"] = stats["abstained_answers"] / len(df) if len(df) > 0 else 0

    # Tool operations
    stats["tools_created"] = df["tool_created"].sum()
    stats["tools_updated"] = df["tool_updated"].sum()
    stats["tools_saved"] = df["tool_saved"].sum()
    stats["tools_kept"] = df["tool_recommendation_keep"].sum()
    stats["tools_discarded"] = df["tool_recommendation_discard"].sum()

    # Category breakdown
    stats["by_category"] = {}
    for category in df["category"].unique():
        if category == "N/A":
            continue
        category_df = df[df["category"] == category]
        cat_correct = (category_df["classification"] == "correct").sum()
        cat_wrong = (category_df["classification"] == "wrong").sum()
        cat_evaluated = cat_correct + cat_wrong
        cat_accuracy = cat_correct / cat_evaluated if cat_evaluated > 0 else 0

        stats["by_category"][category] = {
            "count": len(category_df),
            "correct": cat_correct,
            "wrong": cat_wrong,
            "abstained": (category_df["classification"] == "abstained").sum(),
            "accuracy": cat_accuracy,
            "avg_latency": category_df["total_latency"].mean(),
            "avg_tokens": (category_df["input_tokens_total"] + category_df["output_tokens_total"]).mean(),
        }

    # Latency statistics
    stats["avg_latency"] = df["total_latency"].mean()
    stats["median_latency"] = df["total_latency"].median()
    stats["max_latency"] = df["total_latency"].max()
    stats["min_latency"] = df["total_latency"].min()

    # Token statistics
    stats["total_input_tokens"] = df["input_tokens_total"].sum()
    stats["total_output_tokens"] = df["output_tokens_total"].sum()
    stats["avg_input_tokens"] = df["input_tokens_total"].mean()
    stats["avg_output_tokens"] = df["output_tokens_total"].mean()

    # Error count
    stats["errors"] = df["error"].sum()

    return stats


def print_statistics(stats: Dict) -> None:
    """
    Print formatted statistics to console.

    Args:
        stats: Dictionary with statistics
    """
    print("\n" + "=" * 80)
    print("TRAINING RUN ANALYSIS - STATISTICS")
    print("=" * 80)

    # Overall metrics
    print("\n📊 Overall Metrics:")
    print(f"  Total Questions: {stats['total_questions']}")
    print(f"  Correct Answers: {stats['correct_answers']}")
    print(f"  Wrong Answers: {stats['wrong_answers']}")
    print(f"  Abstained Answers: {stats['abstained_answers']}")
    print(f"  Accuracy: {stats['accuracy']:.2%}")
    print(f"  Abstention Rate: {stats['abstention_rate']:.2%}")
    print(f"  Errors: {stats['errors']}")

    # Tool operations
    print("\n🔧 Tool Operations:")
    print(f"  Tools Created: {stats['tools_created']}")
    print(f"  Tools Updated: {stats['tools_updated']}")
    print(f"  Tools Saved: {stats['tools_saved']}")
    print(f"  Tools Kept (after assessment): {stats['tools_kept']}")
    print(f"  Tools Discarded (after assessment): {stats['tools_discarded']}")

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

    # Latency statistics
    print("\n⏱️  Latency Statistics:")
    print(f"  Average: {stats['avg_latency']:.2f}s")
    print(f"  Median: {stats['median_latency']:.2f}s")
    print(f"  Min: {stats['min_latency']:.2f}s")
    print(f"  Max: {stats['max_latency']:.2f}s")

    # Token statistics
    print("\n🎯 Token Usage:")
    print(f"  Total Input Tokens: {stats['total_input_tokens']:,}")
    print(f"  Total Output Tokens: {stats['total_output_tokens']:,}")
    print(f"  Average Input Tokens/Question: {stats['avg_input_tokens']:.0f}")
    print(f"  Average Output Tokens/Question: {stats['avg_output_tokens']:.0f}")

    print("\n" + "=" * 80)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Analyze MLflow training run and generate Excel report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  # Analyze a single run
  uv run scripts/analyze_training_runs.py --run-id c0f5d69f17b3400093fa63204c70adc3
        """,
    )

    parser.add_argument(
        "--run-id",
        required=True,
        help="MLflow run ID to analyze",
    )

    parser.add_argument(
        "--export",
        type=str,
        default=None,
        metavar="NAME",
        help="Export to Excel file: reports/TRAINING_YYYY-MM-DD_NAME.xlsx",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("MLflow Training Run Analysis")
    print("=" * 80)
    print(f"\nAnalyzing run: {args.run_id}")

    # Setup MLflow
    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient()

    # Get main run info
    main_run = client.get_run(args.run_id)
    experiment_id = main_run.info.experiment_id
    run_name = main_run.data.tags.get("mlflow.runName", "Unknown")
    print(f"  Run Name: {run_name}")
    print(f"  Experiment ID: {experiment_id}")

    # Fetch nested runs
    nested_runs = fetch_nested_runs(client, args.run_id, experiment_id)
    print(f"  Found {len(nested_runs)} nested runs (questions)")

    # Extract data from each nested run
    all_run_data = []
    for nested_run in nested_runs:
        run_data = extract_run_data(nested_run)
        all_run_data.append(run_data)

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

    # Export to Excel (only if --export is provided)
    if args.export:
        from datetime import datetime

        date_str = datetime.now().strftime("%Y-%m-%d")
        output_filename = f"{REPORTS_DIR}/TRAINING_{date_str}_{args.export}.xlsx"
        print(f"\nExporting to Excel: {output_filename}")

        with pd.ExcelWriter(output_filename, engine="openpyxl") as writer:
            # Write main data
            df.to_excel(writer, sheet_name="Training Data", index=False)

            # Write statistics summary
            stats_data = {
                "Metric": [
                    "Total Questions",
                    "Correct Answers",
                    "Wrong Answers",
                    "Abstained Answers",
                    "Accuracy",
                    "Abstention Rate",
                    "Tools Created",
                    "Tools Updated",
                    "Tools Saved",
                    "Tools Kept",
                    "Tools Discarded",
                    "Average Latency (s)",
                    "Median Latency (s)",
                    "Total Input Tokens",
                    "Total Output Tokens",
                    "Errors",
                ],
                "Value": [
                    stats["total_questions"],
                    stats["correct_answers"],
                    stats["wrong_answers"],
                    stats["abstained_answers"],
                    f"{stats['accuracy']:.2%}",
                    f"{stats['abstention_rate']:.2%}",
                    stats["tools_created"],
                    stats["tools_updated"],
                    stats["tools_saved"],
                    stats["tools_kept"],
                    stats["tools_discarded"],
                    f"{stats['avg_latency']:.2f}",
                    f"{stats['median_latency']:.2f}",
                    f"{stats['total_input_tokens']:,}",
                    f"{stats['total_output_tokens']:,}",
                    stats["errors"],
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

        print(f"✅ Export complete: {output_filename}")

    print("\nAnalysis complete!")


if __name__ == "__main__":
    main()
