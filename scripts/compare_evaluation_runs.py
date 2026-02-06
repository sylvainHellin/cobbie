#!/usr/bin/env python3
"""
Compare Evaluation Runs from MLflow

This script compares two or more evaluation runs side-by-side, showing:
- Summary metrics comparison
- Category breakdown comparison
- Project breakdown comparison
- Question-level changes between runs

Usage:
    uv run scripts/compare_evaluation_runs.py --run-ids <run_id1> <run_id2> ...
    uv run scripts/compare_evaluation_runs.py --run-ids abc123 def456 ghi789
"""

import argparse
import sqlite3
from typing import Dict, List

import mlflow
import pandas as pd
from mlflow import MlflowClient
from tabulate import tabulate

from src.config import DB_PATH, MLFLOW_URI

# Constants
CATEGORY_NAMES = {
    1: "Direct Property",
    2: "Aggregation",
    3: "Computation",
    4: "Estimation/Unavailable",
}


def fetch_nested_runs(client: MlflowClient, parent_run_id: str, experiment_id: str) -> List:
    """Fetch all nested runs for a given parent run."""
    nested_runs = client.search_runs(
        experiment_ids=[experiment_id],
        filter_string=f'tags.mlflow.parentRunId = "{parent_run_id}"',
        max_results=1000,
    )
    return nested_runs


def extract_run_data(run) -> Dict:
    """Extract relevant data from a single nested run."""
    params = run.data.params
    metrics = run.data.metrics

    # Get question ID - prefer the explicit parameter
    # Run name format: "question_{index}_{question_id}"
    question_id = params.get("question_id")
    if question_id is not None:
        try:
            question_id = int(question_id)
        except (ValueError, TypeError):
            pass

    # Get classification from parameters
    classification = params.get("classification", "unknown")
    if classification == "not_evaluated":
        classification = "unknown"

    return {
        "question_id": question_id,
        "classification": classification,
        "num_iterations": int(metrics.get("cobbie_calls_count", 0)),
        "total_duration": metrics.get("cobbie_duration", 0) + metrics.get("verifier_duration", 0),
        "total_input_tokens": metrics.get("total_input_tokens", 0),
        "total_output_tokens": metrics.get("total_output_tokens", 0),
        "success": metrics.get("success", 0) == 1,
    }


def fetch_question_data(question_ids: List[int]) -> Dict[int, Dict]:
    """Fetch question data from the database."""
    if not question_ids:
        return {}

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    placeholders = ",".join("?" * len(question_ids))
    query = f"""
        SELECT
            ib.id,
            ib.question,
            ib.category,
            im.project_name
        FROM ifc_bench ib
        LEFT JOIN ifcmodels im ON ib.ifc_id = im.id
        WHERE ib.id IN ({placeholders})
    """

    cursor.execute(query, question_ids)
    rows = cursor.fetchall()
    conn.close()

    return {
        row[0]: {
            "question": row[1],
            "category": row[2],
            "project_name": row[3],
        }
        for row in rows
    }


def collect_run_data(client: MlflowClient, run_id: str) -> tuple[str, pd.DataFrame]:
    """Collect all data for a single run and return as DataFrame."""
    main_run = client.get_run(run_id)
    experiment_id = main_run.info.experiment_id
    run_name = main_run.data.tags.get("mlflow.runName", run_id[:8])

    nested_runs = fetch_nested_runs(client, run_id, experiment_id)
    run_data_list = [extract_run_data(r) for r in nested_runs]

    # Filter out invalid entries
    run_data_list = [r for r in run_data_list if r["question_id"] is not None]

    df = pd.DataFrame(run_data_list)
    return run_name, df


def enrich_dataframe(df: pd.DataFrame, question_data: Dict[int, Dict]) -> pd.DataFrame:
    """Add category and project_name columns to dataframe from question metadata."""
    df = df.copy()

    def get_category(qid):
        if pd.isna(qid):
            return None
        return question_data.get(int(qid), {}).get("category")

    def get_project(qid):
        if pd.isna(qid):
            return None
        return question_data.get(int(qid), {}).get("project_name")

    df["category"] = df["question_id"].apply(get_category)
    df["project_name"] = df["question_id"].apply(get_project)

    return df


def calculate_run_stats(df: pd.DataFrame) -> Dict:
    """Calculate statistics for a single run."""
    successful_df = df[df["success"]]

    correct = (successful_df["classification"] == "correct").sum()
    wrong = (successful_df["classification"] == "wrong").sum()
    abstained = (successful_df["classification"] == "abstained").sum()
    evaluated = correct + wrong

    return {
        "total": len(df),
        "successful": len(successful_df),
        "correct": correct,
        "wrong": wrong,
        "abstained": abstained,
        "accuracy": correct / evaluated if evaluated > 0 else 0,
        "abstention_rate": abstained / len(successful_df) if len(successful_df) > 0 else 0,
        "avg_iterations": df["num_iterations"].mean(),
        "avg_latency": df["total_duration"].mean(),
        "total_tokens": (df["total_input_tokens"] + df["total_output_tokens"]).sum(),
    }


def calculate_category_stats(df: pd.DataFrame) -> Dict[int, Dict]:
    """Calculate per-category statistics. DataFrame must have 'category' column."""
    stats = {}
    for category in df["category"].dropna().unique():
        cat_df = df[df["category"] == category]
        successful = cat_df[cat_df["success"]]

        correct = (successful["classification"] == "correct").sum()
        wrong = (successful["classification"] == "wrong").sum()
        evaluated = correct + wrong

        stats[int(category)] = {
            "count": len(cat_df),
            "correct": correct,
            "wrong": wrong,
            "abstained": (successful["classification"] == "abstained").sum(),
            "accuracy": correct / evaluated if evaluated > 0 else 0,
        }

    return stats


def calculate_project_stats(df: pd.DataFrame) -> Dict[str, Dict]:
    """Calculate per-project statistics. DataFrame must have 'project_name' column."""
    stats = {}
    for project in df["project_name"].dropna().unique():
        if project == "N/A" or pd.isna(project):
            continue
        proj_df = df[df["project_name"] == project]
        successful = proj_df[proj_df["success"]]

        correct = (successful["classification"] == "correct").sum()
        wrong = (successful["classification"] == "wrong").sum()
        evaluated = correct + wrong

        stats[project] = {
            "count": len(proj_df),
            "correct": correct,
            "wrong": wrong,
            "abstained": (successful["classification"] == "abstained").sum(),
            "accuracy": correct / evaluated if evaluated > 0 else 0,
        }

    return stats


def analyze_question_changes(dfs: Dict[str, pd.DataFrame]) -> Dict[str, List[int]]:
    """Analyze question-level changes across runs."""
    run_names = list(dfs.keys())

    # Merge all dataframes on question_id
    merged = None
    for name, df in dfs.items():
        df_subset = df[["question_id", "classification", "success"]].copy()
        df_subset = df_subset.rename(
            columns={
                "classification": f"class_{name}",
                "success": f"success_{name}",
            }
        )
        if merged is None:
            merged = df_subset
        else:
            merged = merged.merge(df_subset, on="question_id", how="outer")

    if merged is None or merged.empty:
        return {}

    # Analyze patterns
    changes: Dict[str, List[int]] = {
        "stable_correct": [],
        "stable_wrong": [],
        "stable_abstained": [],
        "improved": [],  # wrong -> correct in later runs
        "regressed": [],  # correct -> wrong in later runs
        "mixed": [],  # other patterns
    }

    def is_valid(val) -> bool:
        """Check if value is not NaN/None."""
        return val is not None and val == val  # NaN != NaN

    for _, row in merged.iterrows():
        qid = int(row["question_id"])
        classifications = [row.get(f"class_{name}") for name in run_names]

        # Skip if all NaN
        valid_classes = [c for c in classifications if is_valid(c)]
        if not valid_classes:
            continue

        # Check stability
        unique = set(valid_classes)
        if len(unique) == 1:
            if "correct" in unique:
                changes["stable_correct"].append(qid)
            elif "wrong" in unique:
                changes["stable_wrong"].append(qid)
            elif "abstained" in unique:
                changes["stable_abstained"].append(qid)
            else:
                changes["mixed"].append(qid)
        else:
            # Check for improvement or regression pattern
            first_class = classifications[0] if is_valid(classifications[0]) else None
            last_class = classifications[-1] if is_valid(classifications[-1]) else None

            if first_class == "wrong" and last_class == "correct":
                changes["improved"].append(qid)
            elif first_class == "correct" and last_class == "wrong":
                changes["regressed"].append(qid)
            else:
                changes["mixed"].append(qid)

    return changes


def print_summary_comparison(run_names: List[str], stats: Dict[str, Dict]) -> None:
    """Print side-by-side summary comparison."""
    print("\n" + "=" * 80)
    print("SUMMARY COMPARISON")
    print("=" * 80)

    metrics = [
        ("Total Questions", "total", ""),
        ("Successful", "successful", ""),
        ("Correct", "correct", ""),
        ("Wrong", "wrong", ""),
        ("Abstained", "abstained", ""),
        ("Accuracy", "accuracy", "%"),
        ("Abstention Rate", "abstention_rate", "%"),
        ("Avg Iterations", "avg_iterations", ".1f"),
        ("Avg Latency", "avg_latency", "s"),
        ("Total Tokens", "total_tokens", ","),
    ]

    table = []
    for label, key, fmt in metrics:
        row = [label]
        for name in run_names:
            val = stats[name].get(key, 0)
            if fmt == "%":
                row.append(f"{val:.1%}")
            elif fmt == "s":
                row.append(f"{val:.1f}s")
            elif fmt == ",":
                row.append(f"{val:,.0f}")
            elif fmt == ".1f":
                row.append(f"{val:.1f}")
            else:
                row.append(str(val))
        table.append(row)

    headers = ["Metric"] + run_names
    print(tabulate(table, headers=headers, tablefmt="grid"))


def print_category_comparison(run_names: List[str], category_stats: Dict[str, Dict[int, Dict]]) -> None:
    """Print category comparison table."""
    print("\n" + "=" * 80)
    print("CATEGORY COMPARISON (Accuracy)")
    print("=" * 80)

    # Get all categories
    all_categories = set()
    for stats in category_stats.values():
        all_categories.update(stats.keys())

    table = []
    for cat in sorted(all_categories):
        row = [f"{cat} - {CATEGORY_NAMES.get(cat, 'Unknown')}"]
        for name in run_names:
            cat_data = category_stats[name].get(cat, {})
            acc = cat_data.get("accuracy", 0)
            count = cat_data.get("count", 0)
            row.append(f"{acc:.1%} ({count})")
        table.append(row)

    headers = ["Category"] + run_names
    print(tabulate(table, headers=headers, tablefmt="grid"))


def print_project_comparison(run_names: List[str], project_stats: Dict[str, Dict[str, Dict]]) -> None:
    """Print project comparison table."""
    print("\n" + "=" * 80)
    print("PROJECT COMPARISON (Accuracy)")
    print("=" * 80)

    # Get all projects
    all_projects = set()
    for stats in project_stats.values():
        all_projects.update(stats.keys())

    if not all_projects:
        print("No project data available.")
        return

    table = []
    for proj in sorted(all_projects):
        row = [proj[:30]]  # Truncate long project names
        for name in run_names:
            proj_data = project_stats[name].get(proj, {})
            acc = proj_data.get("accuracy", 0)
            count = proj_data.get("count", 0)
            row.append(f"{acc:.1%} ({count})")
        table.append(row)

    headers = ["Project"] + run_names
    print(tabulate(table, headers=headers, tablefmt="grid"))


def print_question_changes(changes: Dict[str, List[int]], question_data: Dict[int, Dict]) -> None:
    """Print question-level changes analysis."""
    print("\n" + "=" * 80)
    print("QUESTION-LEVEL CHANGES")
    print("=" * 80)

    summary_table = [
        ["Stable Correct", len(changes.get("stable_correct", []))],
        ["Stable Wrong", len(changes.get("stable_wrong", []))],
        ["Stable Abstained", len(changes.get("stable_abstained", []))],
        ["Improved (wrong -> correct)", len(changes.get("improved", []))],
        ["Regressed (correct -> wrong)", len(changes.get("regressed", []))],
        ["Mixed/Other", len(changes.get("mixed", []))],
    ]
    print(tabulate(summary_table, headers=["Category", "Count"], tablefmt="grid"))

    # Show improved questions
    if changes.get("improved"):
        print("\nImproved Questions (wrong -> correct):")
        for qid in sorted(changes["improved"])[:20]:  # Limit to first 20
            q_text = question_data.get(qid, {}).get("question", "N/A")
            print(f"  - Q{qid}: {q_text[:80]}...")
        if len(changes["improved"]) > 20:
            print(f"  ... and {len(changes['improved']) - 20} more")

    # Show regressed questions
    if changes.get("regressed"):
        print("\nRegressed Questions (correct -> wrong):")
        for qid in sorted(changes["regressed"])[:20]:
            q_text = question_data.get(qid, {}).get("question", "N/A")
            print(f"  - Q{qid}: {q_text[:80]}...")
        if len(changes["regressed"]) > 20:
            print(f"  ... and {len(changes['regressed']) - 20} more")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Compare MLflow evaluation runs side-by-side",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare two runs
  uv run scripts/compare_evaluation_runs.py --run-ids abc123 def456

  # Compare three runs
  uv run scripts/compare_evaluation_runs.py --run-ids abc123 def456 ghi789
        """,
    )

    parser.add_argument(
        "--run-ids",
        nargs="+",
        required=True,
        help="MLflow run IDs to compare (minimum 2, space-separated)",
    )

    parser.add_argument(
        "--fair",
        action="store_true",
        default=False,
        help="Only compare questions present in ALL runs (intersection). Requires multiple --run-ids.",
    )

    args = parser.parse_args()

    if len(args.run_ids) < 2:
        parser.error("At least 2 run IDs are required for comparison")

    print("=" * 80)
    print("MLflow Evaluation Run Comparison")
    print("=" * 80)
    print(f"\nComparing {len(args.run_ids)} runs...")

    # Setup MLflow
    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient()

    # Collect data for each run
    run_dfs: Dict[str, pd.DataFrame] = {}
    run_names: List[str] = []

    for run_id in args.run_ids:
        print(f"\nFetching run: {run_id}")
        try:
            name, df = collect_run_data(client, run_id)
            run_dfs[name] = df
            run_names.append(name)
            print(f"  Name: {name}, Questions: {len(df)}")
        except Exception as e:
            print(f"  Error: {e}")
            continue

    if len(run_dfs) < 2:
        print("\nError: Need at least 2 valid runs for comparison")
        return

    # Get all question IDs and fetch metadata
    all_question_ids = set()
    for df in run_dfs.values():
        all_question_ids.update(df["question_id"].dropna().astype(int).tolist())

    print(f"\nFetching metadata for {len(all_question_ids)} unique questions...")
    question_data = fetch_question_data(list(all_question_ids))

    # Enrich dataframes with category and project data
    for name in run_names:
        run_dfs[name] = enrich_dataframe(run_dfs[name], question_data)

    # Fair mode: restrict to questions present in all runs
    if args.fair:
        qid_sets = {
            name: set(df["question_id"].dropna().astype(int))
            for name, df in run_dfs.items()
        }
        common_qids = set.intersection(*qid_sets.values())
        print(f"\n[Fair mode] Using {len(common_qids)} questions common to all {len(run_names)} runs")
        for name, qids in qid_sets.items():
            excluded = len(qids) - len(qids & common_qids)
            print(f"[Fair mode]   {name}: excluded {excluded} questions")
        common_qids_list = list(common_qids)
        for name in run_names:
            run_dfs[name] = pd.DataFrame(run_dfs[name][run_dfs[name]["question_id"].isin(common_qids_list)])

    # Calculate stats for each run
    run_stats = {name: calculate_run_stats(df) for name, df in run_dfs.items()}
    category_stats = {name: calculate_category_stats(df) for name, df in run_dfs.items()}
    project_stats = {name: calculate_project_stats(df) for name, df in run_dfs.items()}

    # Analyze question changes
    question_changes = analyze_question_changes(run_dfs)

    # Print comparisons
    print_summary_comparison(run_names, run_stats)
    print_category_comparison(run_names, category_stats)
    print_project_comparison(run_names, project_stats)
    print_question_changes(question_changes, question_data)

    print("\n" + "=" * 80)
    print("Comparison complete!")


if __name__ == "__main__":
    main()
