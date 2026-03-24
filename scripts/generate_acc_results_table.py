#!/usr/bin/env python3
"""
Generate ACC Results Table from MLflow

Queries the ACC_Training_v2 experiment in MLflow, selects the best run per rule,
and outputs a per-rule results LaTeX table and CSV.

Usage:
    uv run scripts/generate_acc_results_table.py
    uv run scripts/generate_acc_results_table.py --mlflow-uri http://127.0.0.1:5001
"""

import argparse
from pathlib import Path

import mlflow
import pandas as pd
from mlflow import MlflowClient
from mlflow.entities import Run

# ── Hardcoded display mapping ────────────────────────────────────────────────
RULE_DISPLAY: dict[str, tuple[str, int]] = {
    "slab_thickness": ("Slab thickness", 1),
    "504_2_riser_height": ("Riser height", 1),
    "504_2_tread_length": ("Tread length", 1),
    "504_2_non_uniform_risers_treads": ("Non-uniform risers/treads", 2),
    "504_2_stair_slab_connection": (r"Stair--slab connection", 2),
    "doors_and_windows": ("Doors and windows", 2),
    "large_spaces_more_than_one_door": (r"Large spaces $\geq$\,2 doors", 2),
    "spaces_same_storey_same_bottom_elevation": ("Same-storey elevation", 2),
    "space_validation_inside": ("Space validation (inside)", 2),
    "space_validation_intersect": ("Space validation (intersect)", 2),
    "304_3_1_circular_space": ("Circular space (304.3.1)", 3),
    "305_3_size": ("Clear floor space (305.3)", 3),
    "404_2_5_two_doors_in_series": ("Two doors in series (404.2.5)", 3),
    "clearance_front_of_doors": ("Clearance front of doors", 3),
    "slabs_guarded_against_falling": ("Slabs guarded against falling", 3),
    "unallocated_areas": ("Unallocated areas", 3),
}

# Splits and their metric keys
SPLITS = ["training", "validation", "test"]
METRIC_SUFFIXES = ["f1_avg", "precision_aggregated", "recall_aggregated", "f1_aggregated"]


def parse_rule_title(run_name: str) -> str | None:
    """Extract rule_title from run_name like 'rule_4_504_2_non_uniform_risers_treads'."""
    parts = run_name.split("_", 2)  # ['rule', '4', '504_2_non_uniform...']
    if len(parts) >= 3 and parts[0] == "rule":
        return parts[2]
    return None


def fetch_runs(client: MlflowClient, exp_id: str) -> list[Run]:
    """Fetch all runs in the experiment."""
    all_runs: list[Run] = []
    page_token = None
    while True:
        result = client.search_runs(
            experiment_ids=[exp_id],
            order_by=["start_time DESC"],
            max_results=1000,
            page_token=page_token,
        )
        all_runs.extend(result)
        page_token = result.token if hasattr(result, "token") else None
        if not page_token:
            break
    return all_runs


def build_trace_cache(exp_id: str, runs: list[Run]) -> dict[str, int]:
    """For each run, count how many traces it has. Returns {run_id: trace_count}."""
    cache: dict[str, int] = {}
    for run in runs:
        rid = run.info.run_id
        traces = mlflow.search_traces(
            experiment_ids=[exp_id],
            run_id=rid,
            return_type="list",
            include_spans=False,
            max_results=1,
        )
        cache[rid] = len(traces)
    return cache


def select_best_runs(
    runs: list[Run], trace_cache: dict[str, int]
) -> dict[str, Run]:
    """Group runs by rule_title, pick the best one per rule."""
    # Group by rule title
    groups: dict[str, list[Run]] = {}
    for run in runs:
        run_name = run.info.run_name
        if run_name is None:
            continue
        title = parse_rule_title(run_name)
        if title is None:
            continue
        groups.setdefault(title, []).append(run)

    selected: dict[str, Run] = {}
    for title, candidates in groups.items():
        finished = [r for r in candidates if r.info.status == "FINISHED"]
        # Priority 1: FINISHED with traces (latest first — already sorted DESC)
        finished_with_traces = [
            r for r in finished if trace_cache.get(r.info.run_id, 0) > 0
        ]
        if finished_with_traces:
            selected[title] = finished_with_traces[0]
            continue
        # Priority 2: FINISHED with test_f1_aggregated metric
        finished_with_test = [
            r for r in finished if "test_f1_aggregated" in r.data.metrics
        ]
        if finished_with_test:
            selected[title] = finished_with_test[0]
            continue
        # Fallback: any FINISHED run
        if finished:
            selected[title] = finished[0]
            continue
        # Last resort: any run (e.g. RUNNING)
        if candidates:
            selected[title] = candidates[0]

    return selected


def extract_metrics(selected: dict[str, Run], trace_cache: dict[str, int]) -> pd.DataFrame:
    """Build a DataFrame with per-rule, per-split metrics."""
    rows = []
    for title, run in selected.items():
        m = run.data.metrics
        display_name, cls = RULE_DISPLAY.get(title, (title, 0))
        row: dict[str, object] = {
            "rule_title": title,
            "display_name": display_name,
            "class": cls,
            "run_id": run.info.run_id,
            "status": run.info.status,
            "has_trace": trace_cache.get(run.info.run_id, 0) > 0,
        }
        for split in SPLITS:
            for suffix in METRIC_SUFFIXES:
                key = f"{split}_{suffix}"
                row[key] = m.get(key)
            # tp/fn for dagger detection
            row[f"{split}_tp"] = m.get(f"{split}_tp")
            row[f"{split}_fn"] = m.get(f"{split}_fn")
        rows.append(row)

    df = pd.DataFrame(rows)
    # Sort by class then by display_name
    sort_order = list(RULE_DISPLAY.keys())
    df["sort_key"] = df["rule_title"].map(
        lambda t: sort_order.index(t) if t in sort_order else 999
    )
    df = df.sort_values("sort_key").drop(columns=["sort_key"]).reset_index(drop=True)
    return df


def is_all_compliant(row: pd.Series, split: str) -> bool:
    """Check if tp + fn == 0 (all models compliant) for a split."""
    tp = row.get(f"{split}_tp")
    fn = row.get(f"{split}_fn")
    if tp is not None and fn is not None:
        return (tp + fn) == 0
    return False


def fmt_metric(value: object, dagger: bool = False) -> str:
    """Format a metric value for LaTeX."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "--"
    v = f"{value:.2f}"
    if dagger:
        v += r"$^\dagger$"
    return v


def compute_class_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Compute average metrics per class and overall."""
    avg_rows = []
    metric_cols = [
        f"{split}_{suffix}" for split in SPLITS for suffix in METRIC_SUFFIXES
    ]
    for cls in sorted(df["class"].unique()):
        cls_df = df[df["class"] == cls]
        row: dict[str, object] = {
            "rule_title": f"_avg_class_{cls}",
            "display_name": f"\\textit{{Class {cls} avg.}}",
            "class": cls,
            "run_id": "",
            "status": "",
            "has_trace": False,
        }
        for col in metric_cols:
            vals = cls_df[col].dropna().to_list()  # pyright: ignore[reportAttributeAccessIssue]
            row[col] = sum(vals) / len(vals) if vals else None
        # No dagger for averages
        for split in SPLITS:
            row[f"{split}_tp"] = None
            row[f"{split}_fn"] = None
        avg_rows.append(row)

    # Overall average
    row_all: dict[str, object] = {
        "rule_title": "_avg_overall",
        "display_name": r"\textit{Overall avg.}",
        "class": 0,
        "run_id": "",
        "status": "",
        "has_trace": False,
    }
    for col in metric_cols:
        vals = df[col].dropna().to_list()
        row_all[col] = sum(vals) / len(vals) if vals else None
    for split in SPLITS:
        row_all[f"{split}_tp"] = None
        row_all[f"{split}_fn"] = None
    avg_rows.append(row_all)

    return pd.DataFrame(avg_rows)


MAX_RETRIES = 3  # columns Iter₀, Iter₁, Iter₂


def extract_execution_metrics(selected: dict[str, Run]) -> pd.DataFrame:
    """Build a DataFrame with per-rule execution/duration metrics."""
    rows = []
    for title, run in selected.items():
        m = run.data.metrics
        display_name, cls = RULE_DISPLAY.get(title, (title, 0))
        row: dict[str, object] = {
            "rule_title": title,
            "display_name": display_name,
            "class": cls,
            "retry_count": m.get("retry_count"),
            "create_tool_duration": m.get("create_tool_duration"),
            "assessment_duration": m.get("assessment_duration"),
            "validate_duration": m.get("validate_duration"),
            "test_duration": m.get("test_duration"),
            "total_duration": m.get("total_duration"),
            "total_tokens": m.get("total_tokens"),
        }
        for i in range(MAX_RETRIES):
            row[f"creator_calls_count_{i}"] = m.get(f"creator_calls_count_{i}")
        rows.append(row)

    df = pd.DataFrame(rows)
    # Sort using RULE_DISPLAY order
    sort_order = list(RULE_DISPLAY.keys())
    df["sort_key"] = df["rule_title"].map(
        lambda t: sort_order.index(t) if t in sort_order else 999
    )
    df = df.sort_values("sort_key").drop(columns=["sort_key"]).reset_index(drop=True)
    return df


def generate_execution_latex_table(df: pd.DataFrame) -> str:
    """Generate a LaTeX table for execution/duration metrics."""
    iter_cols = " ".join("c" for _ in range(MAX_RETRIES))
    header = (
        r"\begin{table*}[t]"
        "\n"
        r"\centering"
        "\n"
        r"\caption{ACC training execution metrics per rule.}"
        "\n"
        r"\label{tab:acc_execution}"
        "\n"
        r"\small"
        "\n"
        rf"\begin{{tabular}}{{l c {iter_cols} r r r r r r}}"
        "\n"
        r"\toprule"
        "\n"
        r"Rule & Retries"
    )
    for i in range(MAX_RETRIES):
        header += rf" & Iter$_{i}$"
    header += r" & Create (min) & Assess (min) & Train+Val (min) & Test (min) & Total (min) & Tokens \\" + "\n"
    header += r"\midrule" + "\n"

    def format_row(row: pd.Series) -> str:
        name = row["display_name"]
        retries = row.get("retry_count")
        retries_str = str(int(retries)) if retries is not None and not pd.isna(retries) else "--"

        cells = [name, retries_str]
        for i in range(MAX_RETRIES):
            val = row.get(f"creator_calls_count_{i}")
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                cells.append(str(int(val)))
            else:
                cells.append("--")

        # Create (min) = create_tool_duration (stored in seconds, display in minutes)
        ctd = row.get("create_tool_duration")
        cells.append(f"{ctd / 60:.1f}" if ctd is not None and not pd.isna(ctd) else "--")

        # Assess (min) = assessment_duration
        ad = row.get("assessment_duration")
        cells.append(f"{ad / 60:.1f}" if ad is not None and not pd.isna(ad) else "--")

        # Train+Val (min) = validate_duration
        vd = row.get("validate_duration")
        cells.append(f"{vd / 60:.1f}" if vd is not None and not pd.isna(vd) else "--")

        # Test (min)
        td = row.get("test_duration")
        cells.append(f"{td / 60:.1f}" if td is not None and not pd.isna(td) else "--")

        # Total (min)
        total = row.get("total_duration")
        cells.append(f"{total / 60:.1f}" if total is not None and not pd.isna(total) else "--")

        # Tokens with thousands separator
        tokens = row.get("total_tokens")
        cells.append(f"{int(tokens):,}" if tokens is not None and not pd.isna(tokens) else "--")

        return " & ".join(cells) + r" \\"

    body = ""
    current_class = None
    for _, row in df.iterrows():
        if current_class is not None and row["class"] != current_class:
            body += r"\midrule" + "\n"
        current_class = row["class"]
        body += format_row(row) + "\n"

    footer = r"\bottomrule" + "\n" + r"\end{tabular}" + "\n" + r"\end{table*}"
    return header + body + footer


def generate_latex_table(df: pd.DataFrame, avg_df: pd.DataFrame) -> str:
    """Generate a LaTeX table string matching the paper format."""
    header = (
        r"\begin{table*}[t]"
        "\n"
        r"\centering"
        "\n"
        r"\caption{ACC training and evaluation results per rule.}"
        "\n"
        r"\label{tab:acc_results}"
        "\n"
        r"\small"
        "\n"
        r"\begin{tabular}{l c | cccc | cccc | cccc}"
        "\n"
        r"\toprule"
        "\n"
        r" & & \multicolumn{4}{c|}{Training}"
        r" & \multicolumn{4}{c|}{Validation}"
        r" & \multicolumn{4}{c}{Test} \\"
        "\n"
        r"Rule & Cl."
        r" & F1$_\text{avg}$ & P$_\text{agg}$ & R$_\text{agg}$ & F1$_\text{agg}$"
        r" & F1$_\text{avg}$ & P$_\text{agg}$ & R$_\text{agg}$ & F1$_\text{agg}$"
        r" & F1$_\text{avg}$ & P$_\text{agg}$ & R$_\text{agg}$ & F1$_\text{agg}$"
        r" \\"
        "\n"
        r"\midrule"
        "\n"
    )

    def format_row(row: pd.Series, show_class: bool = True) -> str:
        name = row["display_name"]
        cls_str = str(int(row["class"])) if show_class and row["class"] > 0 else ""
        cells = [name, cls_str]
        for split in SPLITS:
            dagger = is_all_compliant(row, split)
            cells.append(fmt_metric(row.get(f"{split}_f1_avg"), dagger=dagger))
            cells.append(fmt_metric(row.get(f"{split}_precision_aggregated"), dagger=dagger))
            cells.append(fmt_metric(row.get(f"{split}_recall_aggregated"), dagger=dagger))
            cells.append(fmt_metric(row.get(f"{split}_f1_aggregated"), dagger=dagger))
        return " & ".join(cells) + r" \\"

    body = ""
    current_class = None
    for _, row in df.iterrows():
        # Add midrule between classes
        if current_class is not None and row["class"] != current_class:
            body += r"\midrule" + "\n"
        current_class = row["class"]
        body += format_row(row) + "\n"

    # Class averages
    body += r"\midrule" + "\n"
    for _, row in avg_df.iterrows():
        if row["rule_title"] == "_avg_overall":
            body += r"\midrule" + "\n"
        body += format_row(row, show_class=False) + "\n"

    footer = (
        r"\bottomrule"
        "\n"
        r"\end{tabular}"
        "\n"
        r"\vspace{1mm}"
        "\n"
        r"\footnotesize{$^\dagger$ All models compliant (TP + FN = 0); F1 is undefined.}"
        "\n"
        r"\end{table*}"
    )

    return header + body + footer


def print_selection_summary(
    selected: dict[str, Run], trace_cache: dict[str, int]
) -> None:
    """Print a summary table of selected runs."""
    print(f"\n{'Rule Title':<45} {'Run ID':<34} {'Traces':>6} {'Status':<10} {'test_f1?'}")
    print("-" * 105)
    for title in sorted(selected.keys()):
        run = selected[title]
        rid = run.info.run_id
        has_trace = trace_cache.get(rid, 0) > 0
        has_test = "test_f1_aggregated" in run.data.metrics
        print(
            f"{title:<45} {rid:<34} {'yes' if has_trace else 'no':>6} "
            f"{run.info.status:<10} {'yes' if has_test else 'no'}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate ACC results table from MLflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mlflow-uri",
        default="http://127.0.0.1:5001",
        help="MLflow tracking URI (default: http://127.0.0.1:5001)",
    )
    parser.add_argument(
        "--experiment",
        default="ACC_Training_v2",
        help="MLflow experiment name (default: ACC_Training_v2)",
    )
    parser.add_argument(
        "--parent-run-id",
        default="7ca5817aba3e40879b3205398d958102",
        help="Parent run ID to filter child runs (default: 7ca5817aba3e40879b3205398d958102)",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/ec3",
        help="Output directory (default: outputs/ec3)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Connect to MLflow
    mlflow.set_tracking_uri(args.mlflow_uri)
    client = MlflowClient()

    experiment = client.get_experiment_by_name(args.experiment)
    if experiment is None:
        print(f"Experiment '{args.experiment}' not found.")
        return
    exp_id = experiment.experiment_id
    print(f"Experiment: {experiment.name} (id={exp_id})")

    # Fetch child runs for the specific parent run
    parent_run_id = args.parent_run_id
    print(f"Parent run: {parent_run_id}")
    print("Fetching child runs...")
    all_runs = fetch_runs(client, exp_id)
    child_runs = [
        r
        for r in all_runs
        if r.data.tags.get("mlflow.parentRunId") == parent_run_id
    ]
    print(f"Found {len(all_runs)} total runs, {len(child_runs)} child runs for parent")

    # Build trace cache
    print("Checking traces (this may take a moment)...")
    trace_cache = build_trace_cache(exp_id, child_runs)

    # Select best run per rule
    selected = select_best_runs(child_runs, trace_cache)
    print(f"\nSelected {len(selected)} rules")
    print_selection_summary(selected, trace_cache)

    # Check for missing rules
    missing = set(RULE_DISPLAY.keys()) - set(selected.keys())
    if missing:
        print(f"\nWARNING: Missing rules: {missing}")

    # Extract metrics
    df = extract_metrics(selected, trace_cache)
    avg_df = compute_class_averages(df)

    # Generate LaTeX
    latex = generate_latex_table(df, avg_df)

    # Write outputs
    tex_path = output_dir / "acc_results_table.tex"
    csv_path = output_dir / "acc_results_table.csv"

    tex_path.write_text(latex)
    print(f"\nSaved LaTeX table: {tex_path}")

    # CSV: include all metric columns for inspection
    csv_cols = ["display_name", "class", "run_id", "status", "has_trace"]
    for split in SPLITS:
        for suffix in METRIC_SUFFIXES:
            csv_cols.append(f"{split}_{suffix}")
        csv_cols.extend([f"{split}_tp", f"{split}_fn"])
    df[csv_cols].to_csv(csv_path, index=False)
    print(f"Saved CSV: {csv_path}")

    # ── Execution metrics table ──────────────────────────────────────────────
    exec_df = extract_execution_metrics(selected)
    exec_latex = generate_execution_latex_table(exec_df)

    exec_tex_path = output_dir / "acc_execution_table.tex"
    exec_csv_path = output_dir / "acc_execution_table.csv"

    exec_tex_path.write_text(exec_latex)
    print(f"\nSaved execution LaTeX table: {exec_tex_path}")

    exec_csv_cols = [
        "display_name",
        "class",
        "retry_count",
        *[f"creator_calls_count_{i}" for i in range(MAX_RETRIES)],
        "create_tool_duration",
        "assessment_duration",
        "validate_duration",
        "test_duration",
        "total_duration",
        "total_tokens",
    ]
    exec_df[exec_csv_cols].to_csv(exec_csv_path, index=False)
    print(f"Saved execution CSV: {exec_csv_path}")


if __name__ == "__main__":
    main()
