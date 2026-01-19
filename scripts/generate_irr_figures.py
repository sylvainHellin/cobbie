#!/usr/bin/env python3
"""
Generate figures for Inter-Rater Reliability Analysis.

Usage:
    uv run scripts/generate_irr_figures.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# Output directory
FIGURES_DIR = Path("reports/figures")
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# Style settings
plt.style.use("seaborn-v0_8-whitegrid")
COLORS = {
    "excellent": "#2ecc71",
    "good": "#3498db",
    "moderate": "#f39c12",
    "poor": "#e74c3c",
}


def load_data():
    """Load computed metrics from CSV files."""
    reports_dir = Path("reports")
    return {
        "alpha": pd.read_csv(reports_dir / "irr_krippendorff_alpha.csv"),
        "agreement": pd.read_csv(reports_dir / "irr_percentage_agreement.csv"),
        "category": pd.read_csv(reports_dir / "irr_category_breakdown.csv"),
        "correlations": pd.read_csv(reports_dir / "irr_correlations_combined.csv", index_col=0),
    }


def get_interpretation_color(alpha: float) -> str:
    """Get color based on alpha interpretation."""
    if np.isnan(alpha):
        return "#cccccc"
    elif alpha >= 0.800:
        return COLORS["excellent"]
    elif alpha >= 0.667:
        return COLORS["good"]
    elif alpha >= 0.500:
        return COLORS["moderate"]
    else:
        return COLORS["poor"]


def plot_krippendorff_alpha(data: dict):
    """Create bar chart for Krippendorff's alpha values."""
    df = data["alpha"]

    fig, ax = plt.subplots(figsize=(10, 6))

    colors = [get_interpretation_color(a) for a in df["Alpha"]]

    bars = ax.barh(df["Criterion"], df["Alpha"], color=colors, edgecolor="white", linewidth=1.5)

    # Add value labels
    for bar, val in zip(bars, df["Alpha"]):
        ax.text(val + 0.02, bar.get_y() + bar.get_height() / 2,
                f"{val:.3f}", va="center", fontsize=11, fontweight="bold")

    # Add threshold lines
    ax.axvline(x=0.667, color="#666666", linestyle="--", linewidth=1.5, alpha=0.7, label="Good threshold (0.667)")
    ax.axvline(x=0.800, color="#333333", linestyle="--", linewidth=1.5, alpha=0.7, label="Excellent threshold (0.800)")

    ax.set_xlim(0, 1.0)
    ax.set_xlabel("Krippendorff's Alpha", fontsize=12)
    ax.set_title("Inter-Rater Reliability: Krippendorff's Alpha by Criterion", fontsize=14, fontweight="bold")
    ax.legend(loc="lower right", fontsize=10)

    # Add color legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=COLORS["excellent"], label="Excellent (≥0.80)"),
        Patch(facecolor=COLORS["good"], label="Good (≥0.667)"),
        Patch(facecolor=COLORS["moderate"], label="Moderate (≥0.50)"),
        Patch(facecolor=COLORS["poor"], label="Poor (<0.50)"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "krippendorff_alpha.png", dpi=150, bbox_inches="tight")
    plt.savefig(FIGURES_DIR / "krippendorff_alpha.pdf", bbox_inches="tight")
    plt.close()
    print(f"  Saved: krippendorff_alpha.png/pdf")


def plot_percentage_agreement(data: dict):
    """Create bar chart for percentage agreement."""
    df = data["agreement"]

    fig, ax = plt.subplots(figsize=(10, 6))

    colors = ["#3498db" if p >= 90 else "#f39c12" if p >= 80 else "#e74c3c"
              for p in df["Percentage"]]

    bars = ax.barh(df["Criterion"], df["Percentage"], color=colors, edgecolor="white", linewidth=1.5)

    # Add value labels
    for bar, val in zip(bars, df["Percentage"]):
        ax.text(val + 1, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%", va="center", fontsize=11, fontweight="bold")

    ax.set_xlim(0, 105)
    ax.set_xlabel("Agreement (%)", fontsize=12)
    ax.set_title("Inter-Rater Reliability: Percentage Agreement by Criterion", fontsize=14, fontweight="bold")

    # Add threshold line
    ax.axvline(x=90, color="#666666", linestyle="--", linewidth=1.5, alpha=0.7)
    ax.text(90.5, -0.3, "90%", fontsize=9, color="#666666")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "percentage_agreement.png", dpi=150, bbox_inches="tight")
    plt.savefig(FIGURES_DIR / "percentage_agreement.pdf", bbox_inches="tight")
    plt.close()
    print(f"  Saved: percentage_agreement.png/pdf")


def plot_correlation_heatmap(data: dict):
    """Create heatmap for criterion correlations."""
    corr = data["correlations"]

    # Exclude Binary for cleaner visualization of criteria relationships
    criteria_only = corr.drop("Binary", axis=0).drop("Binary", axis=1)
    criteria_only = criteria_only.drop("Abstention", axis=0).drop("Abstention", axis=1)

    fig, ax = plt.subplots(figsize=(8, 6))

    mask = np.triu(np.ones_like(criteria_only, dtype=bool), k=1)

    sns.heatmap(
        criteria_only,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        center=0,
        vmin=-1,
        vmax=1,
        mask=mask,
        square=True,
        linewidths=2,
        cbar_kws={"shrink": 0.8, "label": "Spearman's ρ"},
        ax=ax,
        annot_kws={"fontsize": 12, "fontweight": "bold"}
    )

    ax.set_title("Correlation Between Evaluation Criteria\n(Combined Human + LLM Ratings)",
                 fontsize=14, fontweight="bold")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "correlation_heatmap.png", dpi=150, bbox_inches="tight")
    plt.savefig(FIGURES_DIR / "correlation_heatmap.pdf", bbox_inches="tight")
    plt.close()
    print(f"  Saved: correlation_heatmap.png/pdf")


def plot_full_correlation_heatmap(data: dict):
    """Create full heatmap including all variables."""
    corr = data["correlations"]

    fig, ax = plt.subplots(figsize=(10, 8))

    sns.heatmap(
        corr,
        annot=True,
        fmt=".2f",
        cmap="RdYlGn",
        center=0,
        vmin=-1,
        vmax=1,
        square=True,
        linewidths=1,
        cbar_kws={"shrink": 0.8, "label": "Spearman's ρ"},
        ax=ax,
        annot_kws={"fontsize": 10, "fontweight": "bold"}
    )

    ax.set_title("Full Correlation Matrix\n(Combined Human + LLM Ratings)",
                 fontsize=14, fontweight="bold")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "correlation_heatmap_full.png", dpi=150, bbox_inches="tight")
    plt.savefig(FIGURES_DIR / "correlation_heatmap_full.pdf", bbox_inches="tight")
    plt.close()
    print(f"  Saved: correlation_heatmap_full.png/pdf")


def plot_category_breakdown(data: dict):
    """Create grouped bar chart for category breakdown."""
    df = data["category"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Plot 1: Agreement percentage by category
    ax1 = axes[0]
    colors = ["#3498db" if p >= 90 else "#f39c12" if p >= 80 else "#e74c3c"
              for p in df["Binary %"]]

    bars = ax1.bar(df["Category Name"], df["Binary %"], color=colors, edgecolor="white", linewidth=1.5)

    for bar, val, n in zip(bars, df["Binary %"], df["N"]):
        ax1.text(bar.get_x() + bar.get_width() / 2, val + 2,
                 f"{val:.1f}%\n(n={n})", ha="center", fontsize=10, fontweight="bold")

    ax1.set_ylim(0, 115)
    ax1.set_ylabel("Agreement (%)", fontsize=12)
    ax1.set_title("Binary Classification Agreement by Category", fontsize=13, fontweight="bold")
    ax1.axhline(y=90, color="#666666", linestyle="--", linewidth=1.5, alpha=0.7)
    ax1.tick_params(axis='x', rotation=15)

    # Plot 2: Krippendorff's alpha by category
    ax2 = axes[1]
    alpha_colors = [get_interpretation_color(a) for a in df["Binary Alpha"]]

    bars = ax2.bar(df["Category Name"], df["Binary Alpha"].fillna(0), color=alpha_colors,
                   edgecolor="white", linewidth=1.5)

    for bar, val in zip(bars, df["Binary Alpha"]):
        if np.isnan(val):
            ax2.text(bar.get_x() + bar.get_width() / 2, 0.05,
                     "N/A", ha="center", fontsize=10, fontweight="bold", color="#666666")
        else:
            ax2.text(bar.get_x() + bar.get_width() / 2, val + 0.03,
                     f"{val:.2f}", ha="center", fontsize=10, fontweight="bold")

    ax2.set_ylim(0, 1.0)
    ax2.set_ylabel("Krippendorff's Alpha", fontsize=12)
    ax2.set_title("Krippendorff's Alpha by Category", fontsize=13, fontweight="bold")
    ax2.axhline(y=0.667, color="#666666", linestyle="--", linewidth=1.5, alpha=0.7)
    ax2.tick_params(axis='x', rotation=15)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "category_breakdown.png", dpi=150, bbox_inches="tight")
    plt.savefig(FIGURES_DIR / "category_breakdown.pdf", bbox_inches="tight")
    plt.close()
    print(f"  Saved: category_breakdown.png/pdf")


def plot_combined_summary(data: dict):
    """Create a combined summary figure for the paper."""
    fig = plt.figure(figsize=(14, 10))

    # Create grid
    gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)

    # Plot 1: Krippendorff's Alpha (top left)
    ax1 = fig.add_subplot(gs[0, 0])
    df = data["alpha"]
    colors = [get_interpretation_color(a) for a in df["Alpha"]]
    bars = ax1.barh(df["Criterion"], df["Alpha"], color=colors, edgecolor="white", linewidth=1)
    for bar, val in zip(bars, df["Alpha"]):
        ax1.text(val + 0.02, bar.get_y() + bar.get_height() / 2,
                 f"{val:.2f}", va="center", fontsize=9, fontweight="bold")
    ax1.axvline(x=0.667, color="#666666", linestyle="--", linewidth=1, alpha=0.7)
    ax1.set_xlim(0, 1.0)
    ax1.set_xlabel("Krippendorff's α", fontsize=10)
    ax1.set_title("(a) Inter-Rater Reliability", fontsize=11, fontweight="bold")

    # Plot 2: Percentage Agreement (top right)
    ax2 = fig.add_subplot(gs[0, 1])
    df = data["agreement"]
    colors = ["#3498db" if p >= 90 else "#f39c12" for p in df["Percentage"]]
    bars = ax2.barh(df["Criterion"], df["Percentage"], color=colors, edgecolor="white", linewidth=1)
    for bar, val in zip(bars, df["Percentage"]):
        ax2.text(val + 1, bar.get_y() + bar.get_height() / 2,
                 f"{val:.1f}%", va="center", fontsize=9, fontweight="bold")
    ax2.set_xlim(0, 105)
    ax2.set_xlabel("Agreement (%)", fontsize=10)
    ax2.set_title("(b) Percentage Agreement", fontsize=11, fontweight="bold")

    # Plot 3: Category Breakdown (bottom left)
    ax3 = fig.add_subplot(gs[1, 0])
    df = data["category"]
    x = np.arange(len(df))
    width = 0.35
    bars1 = ax3.bar(x - width/2, df["Binary %"], width, label="Agreement %", color="#3498db", edgecolor="white")
    bars2 = ax3.bar(x + width/2, df["Binary Alpha"].fillna(0) * 100, width, label="Alpha × 100", color="#2ecc71", edgecolor="white")
    ax3.set_xticks(x)
    ax3.set_xticklabels(["Direct\nProperty", "Aggregation", "Computation", "Estimation"], fontsize=9)
    ax3.set_ylabel("Value", fontsize=10)
    ax3.set_title("(c) Performance by Question Category", fontsize=11, fontweight="bold")
    ax3.legend(fontsize=9)
    ax3.set_ylim(0, 110)

    # Plot 4: Correlation Heatmap (bottom right)
    ax4 = fig.add_subplot(gs[1, 1])
    corr = data["correlations"]
    criteria_only = corr.loc[["Faithfulness", "Completeness", "Transparency", "Relevance"],
                              ["Faithfulness", "Completeness", "Transparency", "Relevance"]]
    mask = np.triu(np.ones_like(criteria_only, dtype=bool), k=1)
    sns.heatmap(
        criteria_only, annot=True, fmt=".2f", cmap="RdYlGn", center=0, vmin=-1, vmax=1,
        mask=mask, square=True, linewidths=1, cbar_kws={"shrink": 0.6},
        ax=ax4, annot_kws={"fontsize": 10, "fontweight": "bold"}
    )
    ax4.set_title("(d) Criteria Correlations", fontsize=11, fontweight="bold")

    plt.savefig(FIGURES_DIR / "irr_summary.png", dpi=150, bbox_inches="tight")
    plt.savefig(FIGURES_DIR / "irr_summary.pdf", bbox_inches="tight")
    plt.close()
    print(f"  Saved: irr_summary.png/pdf")


def main():
    print("Generating IRR figures...")
    print()

    data = load_data()

    plot_krippendorff_alpha(data)
    plot_percentage_agreement(data)
    plot_correlation_heatmap(data)
    plot_full_correlation_heatmap(data)
    plot_category_breakdown(data)
    plot_combined_summary(data)

    print()
    print(f"All figures saved to {FIGURES_DIR}/")


if __name__ == "__main__":
    main()
