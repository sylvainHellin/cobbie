#!/usr/bin/env python3
"""
Cost / Latency Analysis for the 3x4 Evaluation Matrix.

Reuses the existing data-loading infrastructure from analyze_evaluation_matrix.py
and src/analysis/data_extraction.py to produce summary tables for Section 5.2.5 / 6.3
of the Automation in Construction paper.

Outputs:
  - Console summary tables (ready for paper inclusion)
  - CSV with raw aggregated data (outputs/eval/cost_latency_<date>.csv)

Usage:
    uv run scripts/analyze_cost_latency.py [--export] [--no-fair]
"""

import argparse
from datetime import datetime

import mlflow
import numpy as np
import pandas as pd
from mlflow import MlflowClient
from tabulate import tabulate

from scripts.analyze_evaluation_matrix import (
    COL_LABELS,
    ROW_LABELS,
    RUN_IDS,
    apply_fair_filter,
    load_matrix,
)
from src.config import MLFLOW_URI

# ---- Pricing (USD per 1M tokens) ----
# Source: https://docs.z.ai/guides/overview/pricing

MODEL_PRICING: dict[str, dict[str, float]] = {
    "dynamic-4.7": {"input": 0.60, "output": 2.20},
    "dynamic-4.5": {"input": 0.20, "output": 1.10},
    "static-4.7": {"input": 0.60, "output": 2.20},
}

REPORTS_DIR = "outputs/eval"


def cost_per_question(row: pd.Series, pricing: dict[str, float]) -> float:
    """Compute USD cost for one question (system tokens only, excludes verifier)."""
    input_tok = row["cobbie_input_tokens"]
    output_tok = row["cobbie_output_tokens"]
    # For static runs the metric names are static_* but load_run_dataframe
    # stores them under cobbie_* / total_* columns. If cobbie_input_tokens is 0,
    # fall back to total minus verifier.
    if input_tok == 0 and row["total_input_tokens"] > 0:
        input_tok = row["total_input_tokens"] - row["verifier_input_tokens"]
    if output_tok == 0 and row["total_output_tokens"] > 0:
        output_tok = row["total_output_tokens"] - row["verifier_output_tokens"]
    return float((input_tok * pricing["input"] + output_tok * pricing["output"]) / 1_000_000)


def compute_config_stats(df: pd.DataFrame, model_row: str) -> dict:
    """Compute aggregate cost/latency stats for one configuration cell."""
    n = len(df)
    if n == 0:
        return {"n": 0}

    pricing = MODEL_PRICING[model_row]
    df = df.copy()
    df["cost"] = df.apply(lambda r: cost_per_question(r, pricing), axis=1)

    # System-only tokens (exclude verifier)
    df["system_input_tokens"] = df["total_input_tokens"] - df["verifier_input_tokens"]
    df["system_output_tokens"] = df["total_output_tokens"] - df["verifier_output_tokens"]
    df["system_total_tokens"] = df["system_input_tokens"] + df["system_output_tokens"]

    # Duration: use cobbie_duration (system only, excludes verifier)
    duration = df["cobbie_duration"]

    # Classification breakdown
    correct = df[df["classification"] == "correct"]
    abstained = df[df["classification"] == "abstained"]

    stats: dict[str, object] = {
        "n": n,
        # Accuracy (from existing results)
        "correct_count": len(correct),
        "correct_rate": len(correct) / n,
        # Token usage (system only)
        "input_tokens_mean": df["system_input_tokens"].mean(),
        "input_tokens_median": df["system_input_tokens"].median(),
        "input_tokens_std": df["system_input_tokens"].std(),
        "output_tokens_mean": df["system_output_tokens"].mean(),
        "output_tokens_median": df["system_output_tokens"].median(),
        "output_tokens_std": df["system_output_tokens"].std(),
        "total_tokens_mean": df["system_total_tokens"].mean(),
        "total_tokens_median": df["system_total_tokens"].median(),
        "total_tokens_std": df["system_total_tokens"].std(),
        # Iterations (dynamic only; static will be 0)
        "iterations_mean": df["num_iterations"].mean(),
        "iterations_median": df["num_iterations"].median(),
        "iterations_min": df["num_iterations"].min(),
        "iterations_max": df["num_iterations"].max(),
        # Latency (system only)
        "latency_mean": duration.mean(),
        "latency_median": duration.median(),
        "latency_p90": np.percentile(duration, 90) if n > 0 else 0,
        # Cost
        "cost_mean": df["cost"].mean(),
        "cost_median": df["cost"].median(),
        "cost_total": df["cost"].sum(),
        # Abstention cost
        "abstained_count": len(abstained),
        "abstained_cost_mean": abstained["cost"].mean() if len(abstained) > 0 else 0,
        "abstained_iterations_mean": (
            abstained["num_iterations"].mean() if len(abstained) > 0 else 0
        ),
        "correct_cost_mean": correct["cost"].mean() if len(correct) > 0 else 0,
        "correct_iterations_mean": (
            correct["num_iterations"].mean() if len(correct) > 0 else 0
        ),
    }
    return stats


def build_summary_table(master: pd.DataFrame) -> pd.DataFrame:
    """Build the main summary table across all configurations."""
    rows = []
    for model_row in ROW_LABELS:
        for aug in COL_LABELS:
            key = (model_row, aug)
            if key not in RUN_IDS:
                continue
            mask = (master["model_row"] == model_row) & (master["augmentation"] == aug)
            subset = pd.DataFrame(master[mask])
            stats = compute_config_stats(subset, model_row)
            if stats["n"] == 0:
                continue
            rows.append({
                "config": f"{model_row}/{aug}",
                "model_row": model_row,
                "augmentation": aug,
                **stats,
            })
    return pd.DataFrame(rows)


def print_main_table(df: pd.DataFrame) -> None:
    """Print the compact summary table for the paper."""
    print("\n" + "=" * 100)
    print("COST-ACCURACY TRADEOFF SUMMARY")
    print("=" * 100)

    table = []
    for _, r in df.iterrows():
        table.append([
            r["config"],
            f"{r['correct_rate']:.1%}",
            f"{r['total_tokens_mean']:,.0f}",
            f"{r['iterations_mean']:.1f}" if r["iterations_mean"] > 0 else "-",
            f"{r['latency_mean']:.1f}s",
            f"{r['latency_p90']:.1f}s",
            f"${r['cost_mean']:.4f}",
            int(r["n"]),
        ])
    print(tabulate(
        table,
        headers=[
            "Configuration", "Correct Rate", "Avg Tokens",
            "Avg Iters", "Avg Latency", "P90 Latency",
            "Avg Cost/Q", "n",
        ],
        tablefmt="grid",
    ))


def print_token_details(df: pd.DataFrame) -> None:
    """Print detailed token usage stats."""
    print("\n" + "=" * 100)
    print("TOKEN USAGE (system only, excludes verifier)")
    print("=" * 100)

    table = []
    for _, r in df.iterrows():
        table.append([
            r["config"],
            f"{r['input_tokens_mean']:,.0f} +/- {r['input_tokens_std']:,.0f}",
            f"{r['output_tokens_mean']:,.0f} +/- {r['output_tokens_std']:,.0f}",
            f"{r['total_tokens_mean']:,.0f} +/- {r['total_tokens_std']:,.0f}",
        ])
    print(tabulate(
        table,
        headers=["Configuration", "Input (mean +/- std)", "Output (mean +/- std)", "Total (mean +/- std)"],
        tablefmt="grid",
    ))


def print_abstention_cost(df: pd.DataFrame) -> None:
    """Print cost comparison: correct vs abstained questions."""
    print("\n" + "=" * 100)
    print("ABSTENTION COST ANALYSIS")
    print("=" * 100)

    table = []
    for _, r in df.iterrows():
        if r["abstained_count"] == 0:
            abst_cost = "-"
            abst_iters = "-"
        else:
            abst_cost = f"${r['abstained_cost_mean']:.4f}"
            abst_iters = f"{r['abstained_iterations_mean']:.1f}"

        correct_cost = f"${r['correct_cost_mean']:.4f}" if r["correct_count"] > 0 else "-"
        correct_iters = f"{r['correct_iterations_mean']:.1f}" if r["correct_count"] > 0 else "-"

        table.append([
            r["config"],
            int(r["correct_count"]),
            correct_cost,
            correct_iters,
            int(r["abstained_count"]),
            abst_cost,
            abst_iters,
        ])
    print(tabulate(
        table,
        headers=[
            "Configuration",
            "Correct n", "Correct $/Q", "Correct Iters",
            "Abstained n", "Abstained $/Q", "Abstained Iters",
        ],
        tablefmt="grid",
    ))


def print_pricing_reference() -> None:
    """Print model pricing used for cost calculations."""
    print("\n" + "=" * 100)
    print("MODEL PRICING REFERENCE (USD per 1M tokens)")
    print("=" * 100)
    table = []
    for model, prices in MODEL_PRICING.items():
        table.append([model, f"${prices['input']:.2f}", f"${prices['output']:.2f}"])
    print(tabulate(table, headers=["Model Row", "Input", "Output"], tablefmt="grid"))
    print("Source: https://docs.z.ai/guides/overview/pricing")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cost/Latency analysis for the 3x4 evaluation matrix.",
    )
    parser.add_argument(
        "--export", action="store_true", default=False,
        help="Write CSV to outputs/eval/",
    )
    parser.add_argument(
        "--no-fair", action="store_true", default=False,
        help="Disable fair-mode filter",
    )
    args = parser.parse_args()

    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient()

    print("Loading evaluation matrix...")
    master = load_matrix(client)
    print(f"Loaded {len(master)} rows across {master['config'].nunique()} configs")

    if not args.no_fair:
        master = apply_fair_filter(master)

    summary = build_summary_table(master)

    print_pricing_reference()
    print_main_table(summary)
    print_token_details(summary)
    print_abstention_cost(summary)

    if args.export:
        date_str = datetime.now().strftime("%Y-%m-%d")
        csv_path = f"{REPORTS_DIR}/cost_latency_{date_str}.csv"
        summary.to_csv(csv_path, index=False)
        print(f"\nExported to: {csv_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
