"""
Per-project accuracy vs IFC validation-issue-count analysis (reviewer R1-4).

Joins per-project judged accuracy (from the 12 factorial cells) with per-project
IFC validation issue counts (from scripts/validate_ifc_models.py export).

Claim under test (R1-4): well-formed models (fewer validation issues) yield higher
per-project extraction accuracy.

Outputs:
  - outputs/analysis/per_project_accuracy_20260629.md
  - outputs/analysis/per_project_accuracy_20260629.csv
  - outputs/analysis/figures/per_project_accuracy_vs_issues_20260629.{png,pdf}

Usage:
    python scripts/analyze_per_project.py
"""

import sqlite3
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

FACTORIAL_DIR = Path("outputs/factorial")
IFC_CSV = Path("outputs/ifc-bench/ifc_validation.csv")
ANALYSIS_DIR = Path("outputs/analysis")
FIG_DIR = ANALYSIS_DIR / "figures"
DATE = "20260629"

# Headline configuration: best backbone, agentic, no tools.
HEADLINE = "glm-5.2__agentic__none"

ISSUE_COLS = ["empty_shape_repr", "invalid_refs", "missing_attrs", "other"]


def load_cells() -> pd.DataFrame:
    """Load every judged factorial cell into one long dataframe."""
    frames = []
    for db in sorted(FACTORIAL_DIR.glob("*/results.sqlite")):
        cell = db.parent.name
        model, paradigm, tools = cell.split("__")
        con = sqlite3.connect(str(db))
        df = pd.read_sql_query(
            "SELECT project, category, classification FROM results", con
        )
        con.close()
        df["cell"] = cell
        df["model"] = model
        df["paradigm"] = paradigm
        df["tools"] = tools
        frames.append(df)
    if not frames:
        sys.exit("No factorial cells with results.sqlite found.")
    return pd.concat(frames, ignore_index=True)


def per_project_accuracy(df: pd.DataFrame) -> pd.DataFrame:
    """correct/total per project for a single-cell (or pooled) frame."""
    g = df.groupby("project")["classification"]
    out = pd.DataFrame(
        {
            "n_questions": g.size(),
            "n_correct": (df["classification"] == "correct")
            .groupby(df["project"])
            .sum(),
        }
    )
    out["accuracy"] = out["n_correct"] / out["n_questions"]
    return out.reset_index()


def load_ifc_issues() -> pd.DataFrame:
    """Aggregate validator per-file rows to per-project issue counts."""
    if not IFC_CSV.exists():
        sys.exit(f"Missing {IFC_CSV}; run scripts/validate_ifc_models.py --csv --md first.")
    ifc = pd.read_csv(IFC_CSV)
    if ifc["error"].notna().any():
        bad = ifc.loc[ifc["error"].notna(), "file"].tolist()
        sys.exit(f"Validator reported file errors: {bad}; aborting rather than guessing.")
    agg = (
        ifc.groupby("project")[ISSUE_COLS + ["total_issues"]]
        .sum()
        .reset_index()
    )
    n_files = ifc.groupby("project").size().rename("n_ifc_files").reset_index()
    return agg.merge(n_files, on="project")


def join_and_report(acc: pd.DataFrame, ifc: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Outer-join accuracy with issues; surface name mismatches."""
    acc_projects = set(acc["project"])
    ifc_projects = set(ifc["project"])
    results_without_model = sorted(acc_projects - ifc_projects)
    model_without_results = sorted(ifc_projects - acc_projects)

    merged = acc.merge(ifc, on="project", how="left")
    return merged, results_without_model, model_without_results


def make_figure(df: pd.DataFrame, rho: float, pval: float) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 6))
    # log scale on x; shift issues by +1 so zero-issue projects are plotted.
    x = df["total_issues"].to_numpy(dtype=float)
    y = df["accuracy"].to_numpy(dtype=float)
    ax.scatter(x + 1, y, s=60, color="#2b6cb0", zorder=3)
    for _, r in df.iterrows():
        ax.annotate(
            r["project"],
            (r["total_issues"] + 1, r["accuracy"]),
            textcoords="offset points",
            xytext=(5, 4),
            fontsize=7,
        )
    ax.set_xscale("log")
    ax.set_xlabel("IFC validation issues (total_issues + 1, log scale)")
    ax.set_ylabel("Per-project accuracy (correct / total)")
    ax.set_title(
        f"Per-project accuracy vs IFC validation issues\n"
        f"({HEADLINE}); Spearman rho={rho:.2f}, p={pval:.3f}, n={len(df)}"
    )
    ax.grid(True, which="both", alpha=0.3)
    ax.set_ylim(-0.02, 1.02)
    fig.tight_layout()
    png = FIG_DIR / f"per_project_accuracy_vs_issues_{DATE}.png"
    pdf = FIG_DIR / f"per_project_accuracy_vs_issues_{DATE}.pdf"
    fig.savefig(png, dpi=150)
    fig.savefig(pdf)
    plt.close(fig)
    print(f"Figure written: {png}\n              : {pdf}")


def main() -> None:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    all_cells = load_cells()
    ifc = load_ifc_issues()

    # --- Headline cell ---
    headline_df = all_cells[all_cells["cell"] == HEADLINE]
    if headline_df.empty:
        sys.exit(f"Headline cell {HEADLINE} not found.")
    head_acc = per_project_accuracy(headline_df)

    # Validation: question-weighted mean of per-project accuracy == overall cell accuracy.
    qw_mean = head_acc["n_correct"].sum() / head_acc["n_questions"].sum()
    overall = (headline_df["classification"] == "correct").mean()
    assert abs(qw_mean - overall) < 1e-9, (qw_mean, overall)
    print(f"[validation] {HEADLINE} question-weighted per-project mean accuracy = {qw_mean:.4f}")
    print(f"[validation] {HEADLINE} overall cell accuracy                     = {overall:.4f}")

    merged, res_no_model, model_no_res = join_and_report(head_acc, ifc)

    if res_no_model:
        print(f"[MISMATCH] result projects with NO IFC model: {res_no_model}")
    if model_no_res:
        print(f"[MISMATCH] IFC models with NO result rows: {model_no_res}")

    if merged["total_issues"].isna().any():
        missing = merged.loc[merged["total_issues"].isna(), "project"].tolist()
        sys.exit(f"Unmatched result projects (cannot get issues): {missing}; aborting.")

    # Spearman on headline cell (n=19 projects).
    rho, pval = spearmanr(merged["total_issues"], merged["accuracy"])
    print(f"[headline] Spearman rho(total_issues, accuracy) = {rho:.3f}, p = {pval:.4f}, n = {len(merged)}")

    # --- Pooled view (all 12 cells pooled per project) ---
    pooled_acc = per_project_accuracy(all_cells)
    pooled = pooled_acc.merge(ifc, on="project", how="left")
    prho, ppval = spearmanr(pooled["total_issues"], pooled["accuracy"])
    print(f"[pooled-12-cells] Spearman rho = {prho:.3f}, p = {ppval:.4f}, n = {len(pooled)}")

    # Per-cell Spearman table.
    per_cell_rows = []
    for cell, sub in all_cells.groupby("cell"):
        ca = per_project_accuracy(sub).merge(ifc, on="project", how="left")
        cr, cp = spearmanr(ca["total_issues"], ca["accuracy"])
        per_cell_rows.append(
            {"cell": cell, "n_projects": len(ca), "overall_acc": (sub["classification"] == "correct").mean(),
             "spearman_rho": cr, "spearman_p": cp}
        )
    per_cell = pd.DataFrame(per_cell_rows).sort_values("cell")

    # --- Write outputs ---
    out_cols = ["project", "n_questions", "accuracy", "total_issues"] + ISSUE_COLS + ["n_ifc_files"]
    merged_sorted = merged.sort_values("total_issues").reset_index(drop=True)
    csv_path = ANALYSIS_DIR / f"per_project_accuracy_{DATE}.csv"
    merged_sorted[out_cols].to_csv(csv_path, index=False)
    print(f"CSV written: {csv_path}")

    make_figure(merged_sorted, rho, pval)

    # Markdown report.
    md = []
    md.append(f"# Per-project accuracy vs IFC validation issues ({DATE})\n")
    md.append(f"Headline configuration: **{HEADLINE}** (best backbone, agentic, no tools).\n")
    md.append(f"- Overall headline cell accuracy: **{overall:.4f}** "
              f"(question-weighted per-project mean: {qw_mean:.4f}, identical — validation passes).")
    md.append(f"- Projects (n): **{len(merged_sorted)}**")
    md.append(f"- Spearman rho(total_issues, accuracy) on headline cell: **{rho:.3f}** (p = {pval:.4f}).")
    md.append(f"- Spearman rho pooled over all 12 cells: **{prho:.3f}** (p = {ppval:.4f}).\n")

    if res_no_model:
        md.append(f"**Mismatch — result projects without IFC model:** {res_no_model}\n")
    if model_no_res:
        md.append(f"**Note — IFC models present but no result rows (excluded from correlation):** {model_no_res}\n")

    md.append("## Headline per-project table (sorted by total_issues)\n")
    hdr = ["project", "n_questions", "accuracy", "total_issues",
           "empty_shape_repr", "invalid_refs", "missing_attrs", "other", "n_ifc_files"]
    md.append("| " + " | ".join(hdr) + " |")
    md.append("|" + "---|" * len(hdr))
    for _, r in merged_sorted.iterrows():
        md.append(
            "| " + " | ".join(
                [
                    str(r["project"]),
                    str(int(r["n_questions"])),
                    f"{r['accuracy']:.3f}",
                    str(int(r["total_issues"])),
                    str(int(r["empty_shape_repr"])),
                    str(int(r["invalid_refs"])),
                    str(int(r["missing_attrs"])),
                    str(int(r["other"])),
                    str(int(r["n_ifc_files"])),
                ]
            ) + " |"
        )

    md.append("\n## Per-cell Spearman rho (accuracy vs total_issues)\n")
    md.append("| cell | n_projects | overall_acc | spearman_rho | spearman_p |")
    md.append("|---|---|---|---|---|")
    for _, r in per_cell.iterrows():
        md.append(f"| {r['cell']} | {int(r['n_projects'])} | {r['overall_acc']:.3f} | "
                  f"{r['spearman_rho']:.3f} | {r['spearman_p']:.4f} |")

    md.append("\n## Interpretation\n")
    direction = "negative" if rho < 0 else "positive"
    supports = rho < 0 and pval < 0.05
    md.append(
        f"The headline Spearman correlation is **{direction}** (rho={rho:.3f}, p={pval:.4f}). "
        f"A negative rho is the direction predicted by R1-4 (more validation issues -> lower accuracy). "
        f"{'This is statistically significant at alpha=0.05.' if supports else 'This is NOT statistically significant at alpha=0.05.'}"
    )
    md.append(
        "\n**Caveats:** n=19 projects is small, so the correlation is underpowered and sensitive to a few "
        "high-issue outliers (hitos ~4262, molio ~2862). Validation-issue counts are heavy-tailed (hence the "
        "log x-axis) and dominated by a couple of malformed models. Issue counts also correlate with model "
        "provenance/size and schema (IFC2X3 vs IFC4), so this is observational and confounded; it cannot isolate "
        "representational consistency from project difficulty or model type."
    )

    md_path = ANALYSIS_DIR / f"per_project_accuracy_{DATE}.md"
    md_path.write_text("\n".join(md) + "\n")
    print(f"Markdown written: {md_path}")

    # best/worst
    best = merged_sorted.loc[merged_sorted["accuracy"].idxmax()]
    worst = merged_sorted.loc[merged_sorted["accuracy"].idxmin()]
    print(f"[best ] {best['project']}: acc={best['accuracy']:.3f}, issues={int(best['total_issues'])}")
    print(f"[worst] {worst['project']}: acc={worst['accuracy']:.3f}, issues={int(worst['total_issues'])}")


if __name__ == "__main__":
    main()
