#!/usr/bin/env python3
"""
Analyze 3x4 Evaluation Matrix from MLflow.

Loads all 12 evaluation runs (3 model rows x 4 augmentation strategies), builds a
unified DataFrame, and produces comparative analyses across dimensions
(model variant, augmentation strategy) with breakdowns by question category
and IFC project. Special focus on manual tool bias for duplex/dental_clinic.

Usage:
    uv run scripts/analyze_evaluation_matrix.py [--export] [--no-fair]
"""

import argparse
from datetime import datetime
from pathlib import Path

import mlflow
import pandas as pd
from mlflow import MlflowClient
from tabulate import tabulate

from src.analysis.data_extraction import (
    CATEGORY_NAMES,
    load_run_dataframe,
)
from src.config import MLFLOW_URI

# --- Constants ---

REPORTS_DIR = "outputs/eval"

# (model_row, augmentation) -> run_id
RUN_IDS: dict[tuple[str, str], str] = {
    # dynamic GLM 4.7
    ("dynamic-4.7", "none"): "389125f2d3654b718bf4606d306182cb",
    ("dynamic-4.7", "doc"): "4ab1263aff1c43a589a7e15bb2d67b48",
    ("dynamic-4.7", "manual"): "b18012e63c424101b139d91f1e3a4066",
    ("dynamic-4.7", "auto"): "437a86bd3b864de1863456ecb38d6821",
    # dynamic GLM 4.5 air
    ("dynamic-4.5", "none"): "3b232ec1bc224457be7300ab73a0bbf6",
    ("dynamic-4.5", "doc"): "78fdd42f57314b9198746bddfcc9fb0c",
    ("dynamic-4.5", "manual"): "cb8b67457a7f457ab3830ea9b2ac2c3b",
    ("dynamic-4.5", "auto"): "3fb49ba2784c4541825d602fbb69f9dc",
    # static GLM 4.7
    ("static-4.7", "none"): "d252e3844235428aa52ced2470b9b846",
    ("static-4.7", "doc"): "0453b1c2f839495d9f6b7704a0854688",
    ("static-4.7", "manual"): "77e41658053f458fadb33bb7a253bb50",
    ("static-4.7", "auto"): "b03fc6134c5847fe83da0b0c201db52d",
}

ROW_LABELS = ["dynamic-4.7", "dynamic-4.5", "static-4.7"]
COL_LABELS = ["none", "doc", "manual", "auto"]

# Projects where manual tools were developed (for bias analysis)
DEV_PROJECTS = {"duplex", "dental_clinic"}


# --- Helper functions ---


def compute_cell_stats(df: pd.DataFrame) -> dict:
    """Compute correct_rate, accuracy, abstention/error rates, and n for a subset of rows."""
    n = len(df)
    if n == 0:
        return {
            "correct_rate": float("nan"), "accuracy": float("nan"),
            "abstention": float("nan"), "error_rate": float("nan"), "n": 0,
        }

    successful = pd.DataFrame(df[df["success"]])
    correct = int((successful["classification"] == "correct").sum())
    wrong = int((successful["classification"] == "wrong").sum())
    abstained = int((successful["classification"] == "abstained").sum())
    error = int((successful["classification"] == "error").sum())
    evaluated = correct + wrong

    return {
        "correct_rate": correct / n,  # primary: correct out of ALL questions
        "accuracy": correct / evaluated if evaluated > 0 else float("nan"),  # secondary
        "abstention": abstained / n,
        "error_rate": error / n,
        "n": n,
    }


def compute_marginal_stats(df: pd.DataFrame) -> dict:
    """Compute correct_rate, accuracy, abstention, error, faithfulness, completeness, and n."""
    stats = compute_cell_stats(df)
    successful = pd.DataFrame(df[df["success"]])

    for criterion in ("faithfulness", "completeness"):
        yes = (successful[criterion] == "Yes").sum()
        no = (successful[criterion] == "No").sum()
        total = yes + no
        stats[f"{criterion}_rate"] = yes / total if total > 0 else float("nan")

    return stats


def pct(val: object) -> str:
    """Format a float as a percentage string, or '-' if NaN."""
    if pd.isna(val):  # type: ignore[arg-type]
        return "-"
    return f"{float(val):.1%}"  # type: ignore[arg-type]


# --- Step 1: Load & tag all runs ---


def load_matrix(client: MlflowClient) -> pd.DataFrame:
    """Load all runs by ID, tag each with model_row and augmentation, return concatenated DF."""
    frames: list[pd.DataFrame] = []
    for (model_row, augmentation), run_id in sorted(RUN_IDS.items()):
        config = f"{model_row}-{augmentation}"
        print(f"  Loading {config} ({run_id[:8]}...)  [{model_row}/{augmentation}]")
        df = load_run_dataframe(client, run_id)
        df["model_row"] = model_row
        df["augmentation"] = augmentation
        df["config"] = config
        frames.append(df)

    if not frames:
        raise SystemExit("No runs found. Is MLflow running?")

    return pd.concat(frames, ignore_index=True)


def apply_fair_filter(master: pd.DataFrame) -> pd.DataFrame:
    """Keep only question_ids present in all run configs."""
    configs = master["config"].unique()
    qid_sets = [set(master.loc[master["config"] == c, "question_id"]) for c in configs]
    common = set.intersection(*qid_sets) if qid_sets else set()
    before = len(master)
    filtered = pd.DataFrame(master[master["question_id"].isin(list(common))])
    after = len(filtered)
    print(f"\n[Fair mode] {len(common)} questions common to all {len(configs)} runs "
          f"({before} -> {after} rows)")
    return filtered


# --- Step 2: Analyses ---


def analysis_matrix(master: pd.DataFrame) -> pd.DataFrame:
    """Build the 3x4 accuracy matrix (rows: model variant, cols: augmentation strategy)."""
    rows = []
    for rl in ROW_LABELS:
        row: dict[str, str | float] = {"Config": rl}
        for col in COL_LABELS:
            mask = (master["model_row"] == rl) & (master["augmentation"] == col)
            stats = compute_cell_stats(pd.DataFrame(master[mask]))
            row[f"{col}_cr"] = stats["correct_rate"]
            row[f"{col}_acc"] = stats["accuracy"]
            row[f"{col}_abst"] = stats["abstention"]
            row[f"{col}_err"] = stats["error_rate"]
            row[f"{col}_n"] = stats["n"]
        rows.append(row)
    return pd.DataFrame(rows)


def print_matrix(matrix_df: pd.DataFrame) -> None:
    """Print the 3x4 matrix to console."""
    print("\n" + "=" * 80)
    print("3x4 ACCURACY MATRIX")
    print("=" * 80)

    table = []
    for _, row in matrix_df.iterrows():
        table_row = [row["Config"]]
        for col in COL_LABELS:
            n = int(row[f"{col}_n"])
            if n == 0:
                table_row.append("-")
            else:
                cr = pct(row[f"{col}_cr"])
                abst = pct(row[f"{col}_abst"])
                err = pct(row[f"{col}_err"])
                table_row.append(f"{cr} (abst: {abst}, err: {err}, n={n})")
        table.append(table_row)

    print(tabulate(table, headers=[""] + COL_LABELS, tablefmt="grid"))


def analysis_marginal_effects(master: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Compute marginal effects along each dimension."""
    tables: dict[str, pd.DataFrame] = {}

    # 1. Model row
    rows = []
    for rl in ROW_LABELS:
        subset = pd.DataFrame(master[master["model_row"] == rl])
        stats = compute_marginal_stats(subset)
        rows.append({"Dimension": rl, **stats})
    tables["model_row"] = pd.DataFrame(rows)

    # 2. Augmentation strategy
    rows = []
    for col in COL_LABELS:
        subset = pd.DataFrame(master[master["augmentation"] == col])
        stats = compute_marginal_stats(subset)
        rows.append({"Dimension": col, **stats})
    tables["augmentation"] = pd.DataFrame(rows)

    return tables


def print_marginal_effects(tables: dict[str, pd.DataFrame]) -> None:
    """Print marginal effect tables."""
    print("\n" + "=" * 80)
    print("MARGINAL EFFECTS")
    print("=" * 80)

    labels = {"model_row": "Model Variant", "augmentation": "Augmentation Strategy"}
    for key, df in tables.items():
        print(f"\n--- {labels[key]} ---")
        table = []
        for _, row in df.iterrows():
            table.append([
                row["Dimension"],
                pct(row["correct_rate"]),
                pct(row["accuracy"]),
                pct(row["abstention"]),
                pct(row["error_rate"]),
                pct(row.get("faithfulness_rate", float("nan"))),
                pct(row.get("completeness_rate", float("nan"))),
                int(row["n"]),
            ])
        print(tabulate(
            table,
            headers=["", "Correct Rate", "Accuracy", "Abstention", "Error", "Faithfulness", "Completeness", "n"],
            tablefmt="grid",
        ))


def analysis_by_category(master: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """For each category, build a mini 3x4 matrix."""
    result: dict[int, pd.DataFrame] = {}
    for cat in sorted(master["category"].dropna().unique()):
        cat_df = pd.DataFrame(master[master["category"] == cat])
        result[int(cat)] = analysis_matrix(cat_df)
    return result


def print_by_category(cat_tables: dict[int, pd.DataFrame]) -> None:
    """Print per-category 3x4 matrices."""
    print("\n" + "=" * 80)
    print("CATEGORY BREAKDOWN")
    print("=" * 80)

    for cat, matrix_df in cat_tables.items():
        name = CATEGORY_NAMES.get(cat, "Unknown")
        print(f"\n--- Category {cat}: {name} ---")
        table = []
        for _, row in matrix_df.iterrows():
            table_row = [row["Config"]]
            for col in COL_LABELS:
                n = int(row[f"{col}_n"])
                if n == 0:
                    table_row.append("-")
                else:
                    cr = pct(row[f"{col}_cr"])
                    table_row.append(f"{cr} (n={n})")
            table.append(table_row)
        print(tabulate(table, headers=[""] + COL_LABELS, tablefmt="grid"))


def analysis_by_project(master: pd.DataFrame) -> pd.DataFrame:
    """For each project, show accuracy per run config."""
    configs = sorted(master["config"].unique())
    rows = []
    for project in sorted(master["project_name"].dropna().unique()):
        proj_df = pd.DataFrame(master[master["project_name"] == project])
        row: dict[str, str | float | int] = {"Project": project}
        for cfg in configs:
            subset = pd.DataFrame(proj_df[proj_df["config"] == cfg])
            stats = compute_cell_stats(subset)
            row[cfg] = stats["correct_rate"]
        row["n"] = len(proj_df) // len(configs) if len(configs) > 0 else 0
        row["dev"] = "***" if project in DEV_PROJECTS else ""
        rows.append(row)
    return pd.DataFrame(rows)


def print_by_project(project_df: pd.DataFrame) -> None:
    """Print project breakdown table."""
    print("\n" + "=" * 80)
    print("PROJECT BREAKDOWN")
    print("=" * 80)

    configs = [c for c in project_df.columns if c not in ("Project", "n", "dev")]
    table = []
    for _, row in project_df.iterrows():
        table_row = [row["Project"], row["dev"]]
        for cfg in configs:
            table_row.append(pct(row[cfg]))
        table_row.append(int(row["n"]))
        table.append(table_row)
    print(tabulate(table, headers=["Project", "Dev?"] + configs + ["n/config"], tablefmt="grid"))


def analysis_manual_tool_bias(master: pd.DataFrame) -> pd.DataFrame:
    """Compare accuracy on dev projects vs other projects across all augmentation strategies."""
    dev_list = list(DEV_PROJECTS)
    rows = []
    for aug in COL_LABELS:
        subset = pd.DataFrame(master[master["augmentation"] == aug])
        dev = pd.DataFrame(subset[subset["project_name"].isin(dev_list)])
        other = pd.DataFrame(subset[~subset["project_name"].isin(dev_list)])
        dev_stats = compute_cell_stats(dev)
        other_stats = compute_cell_stats(other)
        delta = dev_stats["correct_rate"] - other_stats["correct_rate"]
        rows.append({
            "Augmentation": aug,
            "Dev Correct Rate": dev_stats["correct_rate"],
            "Dev n": dev_stats["n"],
            "Other Correct Rate": other_stats["correct_rate"],
            "Other n": other_stats["n"],
            "Delta": delta,
        })
    return pd.DataFrame(rows)


def print_manual_tool_bias(bias_df: pd.DataFrame) -> None:
    """Print manual tool bias analysis."""
    print("\n" + "=" * 80)
    print("MANUAL TOOL BIAS ANALYSIS")
    print("(Dev projects: duplex + dental_clinic)")
    print("=" * 80)

    table = []
    for _, row in bias_df.iterrows():
        delta = float(row["Delta"])
        flag = " <--" if not pd.isna(delta) and delta > 0.05 else ""
        table.append([
            row["Augmentation"],
            pct(row["Dev Correct Rate"]),
            int(row["Dev n"]),
            pct(row["Other Correct Rate"]),
            int(row["Other n"]),
            pct(delta),
            flag,
        ])
    print(tabulate(
        table,
        headers=["Augmentation", "Dev CR", "Dev n", "Other CR", "Other n", "Delta", ""],
        tablefmt="grid",
    ))

    # Check if manual bias is larger than for other augmentation strategies
    manual_rows = pd.DataFrame(bias_df[bias_df["Augmentation"] == "manual"])
    if len(manual_rows) > 0:
        manual_delta = float(manual_rows.iloc[0]["Delta"])
        if not pd.isna(manual_delta):
            other_deltas = pd.DataFrame(bias_df[bias_df["Augmentation"] != "manual"])["Delta"]
            avg_other_delta = float(other_deltas.mean())
            print(f"\nManual tools dev-project delta: {pct(manual_delta)}")
            print(f"Average delta for other strategies: {pct(avg_other_delta)}")
            if manual_delta > avg_other_delta + 0.03:
                print("=> Manual tools show HIGHER dev-project advantage than other strategies")
            else:
                print("=> No significant manual tool bias detected")


def analysis_split_by_dev_projects(
    master: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str | float], dict[str, str | float]]:
    """Build separate 3x4 matrices for dev projects vs other projects.

    Returns (dev_matrix, other_matrix, dev_best, other_best) where *_best
    dicts contain {"row", "col", "correct_rate"} of the highest-performing cell.
    """
    dev_list = list(DEV_PROJECTS)
    dev_df = pd.DataFrame(master[master["project_name"].isin(dev_list)])
    other_df = pd.DataFrame(master[~master["project_name"].isin(dev_list)])

    dev_matrix = analysis_matrix(dev_df)
    other_matrix = analysis_matrix(other_df)

    def _find_best(matrix: pd.DataFrame) -> dict[str, str | float]:
        best: dict[str, str | float] = {"row": "", "col": "", "correct_rate": -1.0}
        for _, row in matrix.iterrows():
            for col in COL_LABELS:
                cr = float(row[f"{col}_cr"])
                if not pd.isna(cr) and cr > float(best["correct_rate"]):
                    best = {"row": str(row["Config"]), "col": col, "correct_rate": float(cr)}
        return best

    return dev_matrix, other_matrix, _find_best(dev_matrix), _find_best(other_matrix)


def print_split_by_dev_projects(
    dev_matrix: pd.DataFrame,
    other_matrix: pd.DataFrame,
    dev_best: dict[str, str | float],
    other_best: dict[str, str | float],
    dev_n: int,
    other_n: int,
) -> None:
    """Print the two 3x4 matrices (dev vs other) with best cell highlighted."""
    print("\n" + "=" * 80)
    print("3x4 MATRIX SPLIT BY DEV PROJECTS")
    print(f"Dev projects: {', '.join(sorted(DEV_PROJECTS))} (n={dev_n})")
    print(f"Other projects (n={other_n})")
    print("=" * 80)

    def _format_matrix(matrix: pd.DataFrame, best: dict[str, str | float]) -> list[list[str]]:
        table = []
        for _, row in matrix.iterrows():
            table_row: list[str] = [str(row["Config"])]
            for col in COL_LABELS:
                n = int(row[f"{col}_n"])
                if n == 0:
                    cell = "-"
                else:
                    cr = pct(row[f"{col}_cr"])
                    cell = f"{cr} (n={n})"
                    if row["Config"] == best["row"] and col == best["col"]:
                        cell += " <-- best"
                table_row.append(cell)
            table.append(table_row)
        return table

    print(f"\n--- Dev Projects ({', '.join(sorted(DEV_PROJECTS))}) ---")
    print(tabulate(_format_matrix(dev_matrix, dev_best), headers=[""] + COL_LABELS, tablefmt="grid"))

    print("\n--- Other Projects ---")
    print(tabulate(_format_matrix(other_matrix, other_best), headers=[""] + COL_LABELS, tablefmt="grid"))


# --- Step 3: Excel export & changelog ---


def export_to_excel(
    master: pd.DataFrame,
    matrix_df: pd.DataFrame,
    marginal_tables: dict[str, pd.DataFrame],
    cat_tables: dict[int, pd.DataFrame],
    project_df: pd.DataFrame,
    bias_df: pd.DataFrame,
    dev_matrix: pd.DataFrame,
    other_matrix: pd.DataFrame,
) -> str:
    """Write all analysis results to an Excel file. Returns the file path."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = f"{REPORTS_DIR}/Evaluation_Matrix_{date_str}.xlsx"

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # Raw Data
        master.to_excel(writer, sheet_name="Raw Data", index=False)

        # 3x4 Matrix
        matrix_df.to_excel(writer, sheet_name="3x4 Matrix", index=False)

        # Marginal Effects
        marginal_frames = []
        for key, df in marginal_tables.items():
            labeled = df.copy()
            labeled.insert(0, "Effect", key)
            marginal_frames.append(labeled)
        pd.concat(marginal_frames, ignore_index=True).to_excel(
            writer, sheet_name="Marginal Effects", index=False
        )

        # By Category
        cat_frames = []
        for cat, df in sorted(cat_tables.items()):
            labeled = df.copy()
            labeled.insert(0, "Category", f"{cat} - {CATEGORY_NAMES.get(cat, 'Unknown')}")
            cat_frames.append(labeled)
        pd.concat(cat_frames, ignore_index=True).to_excel(
            writer, sheet_name="By Category", index=False
        )

        # By Project
        project_df.to_excel(writer, sheet_name="By Project", index=False)

        # Manual Tool Bias
        bias_df.to_excel(writer, sheet_name="Manual Tool Bias", index=False)

        # 3x4 split by dev projects
        dev_matrix.to_excel(writer, sheet_name="3x4 Dev Projects", index=False)
        other_matrix.to_excel(writer, sheet_name="3x4 Other Projects", index=False)

    return path


def write_changelog(path: str) -> None:
    """Write a changelog summarising the matrix restructuring."""
    content = """\
# Evaluation Matrix Changelog

## 2026-04-09: Matrix fully populated (12 cells)

- Added the `static-4.7 + doc` run (`0453b1c2f839495d9f6b7704a0854688`,
  CLI args: `--system static-doc --doc custom`).
- The 3x4 matrix now has all 12 cells populated; the previous N/A cell for
  `static-4.7 / doc` is gone.
- `src/analysis/data_extraction.py` was extended to fall back to
  `static_doc_*` MLflow metrics so cost/latency analysis picks up the new
  run correctly.

## 2026-02-21: Restructured from 3x3 to 3x4

### Before (3x3)
- **Rows**: dynamic+doc, dynamic-no_doc, static (system type x doc backend)
- **Columns**: manual, auto, none (tool strategy)
- **Runs**: 9 (GLM 4.7 only)
- Doc was a cross-cutting dimension within the dynamic system type.

### After (3x4)
- **Rows**: dynamic-4.7, dynamic-4.5, static-4.7 (model variant)
- **Columns**: none, doc, manual, auto (augmentation strategy)
- **Runs**: 11 (GLM 4.7 + GLM 4.5 air)
- Doc is now a standalone augmentation column (no longer cross-cutting).
- static-4.7 + doc is N/A (no run exists).

### Impact on downstream artifacts
- Excel sheet names changed: "3x3 Matrix" -> "3x4 Matrix", "3x3 Dev/Other" -> "3x4 Dev/Other"
- Marginal effects now have two dimensions (model_row, augmentation) instead of three (system, doc, tools)
- Manual tool bias table column renamed: "Tools" -> "Augmentation", now includes 4 strategies instead of 3
"""
    Path(path).write_text(content)


# --- Main ---


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze the 3x4 evaluation matrix from MLflow.",
    )
    parser.add_argument(
        "--export", action="store_true", default=False,
        help="Write results to an Excel file in outputs/eval/",
    )
    parser.add_argument(
        "--no-fair", action="store_true", default=False,
        help="Disable fair-mode filter (include all questions even if not in every run)",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("Evaluation Matrix Analysis (3x4)")
    print("=" * 80)

    # Setup MLflow
    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient()

    # Step 1: Load & tag
    print("\nLoading runs...")
    master = load_matrix(client)
    print(f"Loaded {len(master)} total rows across {master['config'].nunique()} configs")

    if not args.no_fair:
        master = apply_fair_filter(master)

    # Step 2: Analyses
    matrix_df = analysis_matrix(master)
    print_matrix(matrix_df)

    marginal_tables = analysis_marginal_effects(master)
    print_marginal_effects(marginal_tables)

    cat_tables = analysis_by_category(master)
    print_by_category(cat_tables)

    project_df = analysis_by_project(master)
    print_by_project(project_df)

    bias_df = analysis_manual_tool_bias(master)
    print_manual_tool_bias(bias_df)

    dev_matrix, other_matrix, dev_best, other_best = analysis_split_by_dev_projects(master)
    dev_list = list(DEV_PROJECTS)
    dev_n = len(master[master["project_name"].isin(dev_list)]) // master["config"].nunique()
    other_n = len(master[~master["project_name"].isin(dev_list)]) // master["config"].nunique()
    print_split_by_dev_projects(dev_matrix, other_matrix, dev_best, other_best, dev_n, other_n)

    # Step 3: Excel export
    if args.export:
        path = export_to_excel(
            master, matrix_df, marginal_tables, cat_tables, project_df, bias_df,
            dev_matrix, other_matrix,
        )
        print(f"\nExported to: {path}")

        changelog_path = f"{REPORTS_DIR}/matrix_changelog.md"
        write_changelog(changelog_path)
        print(f"Changelog written to: {changelog_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
