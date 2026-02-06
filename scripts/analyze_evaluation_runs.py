#!/usr/bin/env python3
"""
Analyze Evaluation Runs from MLflow

This script extracts detailed evaluation run data from MLflow, enriches it with database
information, and generates an Excel report with comprehensive statistics.

When multiple run IDs are provided, a side-by-side comparison of key metrics
(accuracy, faithfulness, completeness, transparency, relevance, abstention rate)
is printed at the end.

Usage:
    uv run scripts/analyze_evaluation_runs.py --run-ids <run_id>
    uv run scripts/analyze_evaluation_runs.py --run-ids <run_id1> <run_id2> ...
"""

import argparse
from typing import Dict, List

import mlflow
import pandas as pd
from mlflow import MlflowClient
from tabulate import tabulate

from src.analysis.data_extraction import (
    CATEGORY_NAMES,
    build_dataframe,
    extract_run_data,
    fetch_nested_runs,
)
from src.config import MLFLOW_URI
from src.db.query import fetch_question_data

# Constants
REPORTS_DIR = "outputs/eval"



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

    # Criterion-level metrics (only for successful evaluations)
    for criterion in ["faithfulness", "completeness", "transparency", "relevance"]:
        yes_count = (successful_df[criterion] == "Yes").sum()
        no_count = (successful_df[criterion] == "No").sum()
        na_count = (successful_df[criterion] == "Na").sum()
        stats[f"{criterion}_yes"] = yes_count
        stats[f"{criterion}_no"] = no_count
        stats[f"{criterion}_na"] = na_count
        stats[f"{criterion}_rate"] = yes_count / (yes_count + no_count) if (yes_count + no_count) > 0 else 0

    # Iteration statistics
    stats["avg_iterations"] = df["num_iterations"].mean()
    stats["median_iterations"] = df["num_iterations"].median()
    stats["max_iterations"] = df["num_iterations"].max()
    stats["min_iterations"] = df["num_iterations"].min()
    stats["total_iterations"] = df["num_iterations"].sum()

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
        if category == "N/A" or category is None:
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
            "avg_iterations": category_df["num_iterations"].mean(),
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
            "avg_iterations": project_df["num_iterations"].mean(),
            "avg_latency": project_df["total_duration"].mean(),
            "avg_tokens": (project_df["total_input_tokens"] + project_df["total_output_tokens"]).mean(),
        }

    return stats


def print_statistics(stats: Dict, run_names: List[str] | None = None, per_run_stats: Dict[str, Dict] | None = None) -> None:
    """
    Print formatted statistics to console.

    Args:
        stats: Dictionary with statistics
        run_names: List of MLflow run names
        per_run_stats: Per-run statistics keyed by run name (for side-by-side comparison)
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
                f"{cat_stats['avg_iterations']:.1f}",
                f"{cat_stats['avg_latency']:.1f}s",
                f"{cat_stats['avg_tokens']:.0f}",
            ]
        )
    print(
        tabulate(
            category_table,
            headers=["Category", "Count", "Accuracy", "Correct", "Wrong", "Abstained", "Avg Iters", "Avg Latency", "Avg Tokens"],
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
                    f"{proj_stats['avg_iterations']:.1f}",
                    f"{proj_stats['avg_latency']:.1f}s",
                    f"{proj_stats['avg_tokens']:.0f}",
                ]
            )
        print(
            tabulate(
                project_table,
                headers=["Project", "Count", "Accuracy", "Correct", "Wrong", "Abstained", "Avg Iters", "Avg Latency", "Avg Tokens"],
                tablefmt="grid",
            )
        )

    # Iteration statistics
    print("\n🔄 Iteration Statistics:")
    print(f"  Total Iterations: {stats['total_iterations']:.0f}")
    print(f"  Average Iterations: {stats['avg_iterations']:.2f}")
    print(f"  Median Iterations: {stats['median_iterations']:.0f}")
    print(f"  Min Iterations: {stats['min_iterations']:.0f}")
    print(f"  Max Iterations: {stats['max_iterations']:.0f}")

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

    # Key metrics summary at the end for quick reference
    print("\n" + "=" * 80)

    def _format_run_metrics(s: Dict) -> List[str]:
        return [
            f"{s['accuracy']:.2%}",
            f"{s['faithfulness_rate']:.2%}",
            f"{s['completeness_rate']:.2%}",
            f"{s['transparency_rate']:.2%}",
            f"{s['relevance_rate']:.2%}",
            f"{s['abstention_rate']:.2%}",
            f"{s['correct_answers']} / {s['wrong_answers']} / {s['abstained_answers']}",
            f"{s['total_questions']}",
        ]

    metric_names = [
        "Accuracy",
        "Faithfulness",
        "Completeness",
        "Transparency",
        "Relevance",
        "Abstention Rate",
        "Correct / Wrong / Abstained",
        "Total Questions",
    ]

    if per_run_stats and len(per_run_stats) > 1:
        # Side-by-side comparison
        print("KEY METRICS COMPARISON")
        print("=" * 80)
        headers = ["Metric"] + list(per_run_stats.keys())
        columns_per_run = [_format_run_metrics(s) for s in per_run_stats.values()]
        summary_table = [
            [name] + [col[i] for col in columns_per_run]
            for i, name in enumerate(metric_names)
        ]
        print(tabulate(summary_table, headers=headers, tablefmt="grid"))
    else:
        # Single run summary
        run_label = " | ".join(run_names) if run_names else "Unknown"
        print(f"KEY METRICS SUMMARY - {run_label}")
        print("=" * 80)
        values = _format_run_metrics(stats)
        summary_table = [[name, val] for name, val in zip(metric_names, values)]
        print(tabulate(summary_table, headers=["Metric", "Value"], tablefmt="grid"))

    print("=" * 80)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Analyze MLflow evaluation runs and generate Excel report. "
        "When multiple run IDs are provided, prints a side-by-side comparison of key metrics.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze a single run
  uv run scripts/analyze_evaluation_runs.py --run-ids c0f5d69f17b3400093fa63204c70adc3

  # Compare multiple runs side-by-side
  uv run scripts/analyze_evaluation_runs.py --run-ids c0f5d69f17b3400093fa63204c70adc3 21d1966df8dc47d3a5753cbb9bbbb0e3

  # Export results to Excel
  uv run scripts/analyze_evaluation_runs.py --run-ids c0f5d69f17b3400093fa63204c70adc3 --export my_run
        """,
    )

    parser.add_argument(
        "--run-ids",
        nargs="+",
        required=True,
        help="MLflow run IDs to analyze (space-separated). Multiple IDs produce a side-by-side comparison.",
    )

    parser.add_argument(
        "--export",
        type=str,
        default=None,
        metavar="NAME",
        help="Export to Excel file: outputs/eval/Evaluation_YYYY-MM-DD_NAME.xlsx",
    )

    parser.add_argument(
        "--fair",
        action="store_true",
        default=False,
        help="Only compare questions present in ALL runs (intersection). Requires multiple --run-ids.",
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
    run_names = []

    for run_id in args.run_ids:
        print(f"\nProcessing run: {run_id}")

        # Get main run info
        try:
            main_run = client.get_run(run_id)
            experiment_id = main_run.info.experiment_id
            run_name = main_run.data.tags.get("mlflow.runName", "Unknown")
            run_names.append(run_name)
            print(f"  Run Name: {run_name}")
            print(f"  Experiment ID: {experiment_id}")

            # Fetch nested runs
            nested_runs = fetch_nested_runs(client, run_id, experiment_id)
            print(f"  Found {len(nested_runs)} nested runs (questions)")

            # Extract data from each nested run
            for nested_run in nested_runs:
                run_data = extract_run_data(nested_run)
                run_data["parent_run_id"] = run_id
                run_data["parent_run_name"] = run_name
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

    # Fair mode: restrict to questions present in all runs
    if args.fair and len(run_names) > 1 and "parent_run_name" in df.columns:
        qid_sets = {
            name: set(df.loc[df["parent_run_name"] == name, "question_id"])
            for name in run_names
        }
        common_qids = set.intersection(*qid_sets.values())
        print(f"\n[Fair mode] Using {len(common_qids)} questions common to all {len(run_names)} runs")
        for name, qids in qid_sets.items():
            excluded = len(qids) - len(qids & common_qids)
            print(f"[Fair mode]   {name}: excluded {excluded} questions")
        df = pd.DataFrame(df[df["question_id"].isin(list(common_qids))])

    # Calculate statistics
    print("Calculating statistics...")
    stats = calculate_statistics(df)

    # Calculate per-run statistics for side-by-side comparison
    per_run_stats: Dict[str, Dict] | None = None
    if len(run_names) > 1 and "parent_run_name" in df.columns:
        per_run_stats = {}
        for name in run_names:
            run_df = df.loc[df["parent_run_name"] == name]
            if not run_df.empty:
                per_run_stats[name] = calculate_statistics(pd.DataFrame(run_df))

    # Print statistics
    print_statistics(stats, run_names, per_run_stats)

    # Export to Excel (only if --export is provided)
    if args.export:
        from datetime import datetime

        date_str = datetime.now().strftime("%Y-%m-%d")
        output_filename = f"{REPORTS_DIR}/Evaluation_{date_str}_{args.export}.xlsx"
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
                    "Total Iterations",
                    "Average Iterations",
                    "Median Iterations",
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
                    f"{stats['total_iterations']:.0f}",
                    f"{stats['avg_iterations']:.2f}",
                    f"{stats['median_iterations']:.0f}",
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
                        "Avg Iterations": f"{cat_stats['avg_iterations']:.2f}",
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
                            "Avg Iterations": f"{proj_stats['avg_iterations']:.2f}",
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
