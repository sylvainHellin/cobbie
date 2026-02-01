# EC3 Paper IRR Statistics Implementation Plan

## Overview

Compute inter-rater reliability (IRR) statistics for 3 raters (Sylvain, Stefan, LLM) on 74 valid questions, outputting CSV reports, LaTeX tables, and figures with Seaborn "mako" palette.

## Current State Analysis

**Data files** (in `src/db/eval/`):
- `EC3-2026 - sylvain (sylvain) 2026-01-20_21-07.csv`
- `EC3-2026 - stefan (stefan) 2026-01-20_21-07.csv`
- `EC3-2026 - LLM_Judge (LLM_Judge) 2026-01-20_21-08.csv`

**Usable sample**: 74 questions (100 total - 19 errors - 3 UPDATED='x' - 4 Stefan incomplete)

**Category distribution**: Cat1=13, Cat2=39, Cat3=5, Cat4=17

**Existing scripts**:
- `scripts/calculate_irr_metrics.py` - 2-rater only, needs extension
- `scripts/generate_irr_figures.py` - green/yellow/red colors, needs palette update

## Desired End State

1. **New script** `scripts/compute_ec3_irr_stats.py` that:
   - Loads and validates all 3 CSV files
   - Filters to 74 valid questions
   - Computes all IRR metrics
   - Outputs results to `reports/ec3_irr/`

2. **Outputs**:
   - `reports/ec3_irr/krippendorff_alpha.csv` + `.tex`
   - `reports/ec3_irr/fleiss_kappa.csv` + `.tex`
   - `reports/ec3_irr/cohen_kappa_pairwise.csv` + `.tex`
   - `reports/ec3_irr/percentage_agreement.csv` + `.tex`
   - `reports/ec3_irr/confusion_matrices.csv` + `.tex`
   - `reports/ec3_irr/spearman_correlations.csv` + `.tex`
   - `reports/ec3_irr/category_breakdown.csv` + `.tex`
   - `reports/ec3_irr/figures/*.png` (with mako palette)

## What We're NOT Doing

- Modifying existing scripts (they serve different purposes)
- Creating interactive dashboards
- Adding new dependencies beyond what's already available

## Implementation Approach

Single new script with modular functions for each metric type. Uses existing dependencies (`krippendorff`, `sklearn`, `scipy`, `pandas`, `seaborn`, `matplotlib`).

---

## Phase 1: Data Loading and Validation

### Overview
Load, clean, and validate the 3 CSV files to produce a merged DataFrame with 74 valid questions.

### Changes Required:

#### 1.1 Create new script with data loading

**File**: `scripts/compute_ec3_irr_stats.py`

```python
#!/usr/bin/env python3
"""
Compute EC3 Paper IRR Statistics

Computes inter-rater reliability metrics for 3 raters:
- Human 1 (Sylvain)
- Human 2 (Stefan)
- LLM Judge

Outputs CSV reports, LaTeX tables, and figures.

Usage:
    uv run scripts/compute_ec3_irr_stats.py
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


# File paths
EVAL_DIR = Path("src/db/eval")
SYLVAIN_FILE = EVAL_DIR / "EC3-2026 - sylvain (sylvain) 2026-01-20_21-07.csv"
STEFAN_FILE = EVAL_DIR / "EC3-2026 - stefan (stefan) 2026-01-20_21-07.csv"
LLM_FILE = EVAL_DIR / "EC3-2026 - LLM_Judge (LLM_Judge) 2026-01-20_21-08.csv"
OUTPUT_DIR = Path("reports/ec3_irr")
FIGURES_DIR = OUTPUT_DIR / "figures"

CRITERIA = ["Abstention", "Faithfulness", "Completeness", "Transparency", "Relevance"]
RATERS = ["sylvain", "stefan", "llm"]


def load_and_clean_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load and clean the 3 CSV files."""
    sylvain = pd.read_csv(SYLVAIN_FILE)
    stefan = pd.read_csv(STEFAN_FILE)
    llm = pd.read_csv(LLM_FILE)

    # Drop empty rows (Stefan has one)
    stefan = stefan.dropna(subset=["Question ID"])

    # Ensure Question ID is int
    for df in [sylvain, stefan, llm]:
        df["Question ID"] = df["Question ID"].astype(int)

    return sylvain, stefan, llm


def filter_valid_questions(
    sylvain: pd.DataFrame, stefan: pd.DataFrame, llm: pd.DataFrame
) -> set[int]:
    """Return set of valid Question IDs (intersection with complete evaluations)."""
    # Filter Sylvain: Error=0, UPDATED != 'x'
    sylvain_valid = sylvain[(sylvain["Error"] == 0) & (sylvain["UPDATED"] != "x")]

    # Filter Stefan: Error=0, UPDATED != 'x', Abstention not NaN
    stefan_valid = stefan[
        (stefan["Error"] == 0) &
        (stefan["UPDATED"] != "x") &
        stefan["Abstention"].notna()
    ]

    # LLM has no Error/UPDATED columns, all are complete
    llm_valid = llm

    # Intersection
    valid_ids = (
        set(sylvain_valid["Question ID"]) &
        set(stefan_valid["Question ID"]) &
        set(llm_valid["Question ID"])
    )

    return valid_ids


def merge_ratings(
    sylvain: pd.DataFrame, stefan: pd.DataFrame, llm: pd.DataFrame, valid_ids: set[int]
) -> pd.DataFrame:
    """Merge ratings from all 3 raters into a single DataFrame."""
    # Filter to valid IDs
    s = sylvain[sylvain["Question ID"].isin(valid_ids)].copy()
    st = stefan[stefan["Question ID"].isin(valid_ids)].copy()
    l = llm[llm["Question ID"].isin(valid_ids)].copy()

    # Rename columns with rater prefix
    s_cols = {c: f"sylvain_{c}" for c in CRITERIA}
    st_cols = {c: f"stefan_{c}" for c in CRITERIA}
    l_cols = {c: f"llm_{c}" for c in CRITERIA}

    s = s.rename(columns=s_cols)
    st = st.rename(columns=st_cols)
    l = l.rename(columns=l_cols)

    # Merge on Question ID
    merged = s[["Question ID", "Category", "Question"] + list(s_cols.values())]
    merged = merged.merge(
        st[["Question ID"] + list(st_cols.values())],
        on="Question ID"
    )
    merged = merged.merge(
        l[["Question ID"] + list(l_cols.values())],
        on="Question ID"
    )

    return merged.sort_values("Question ID").reset_index(drop=True)
```

### Success Criteria:

#### Automated Verification:
- [ ] `uv run scripts/compute_ec3_irr_stats.py --help` runs without error
- [ ] Type check passes: `uvx ty check scripts/compute_ec3_irr_stats.py`
- [ ] Lint passes: `uvx ruff check scripts/compute_ec3_irr_stats.py`

#### Manual Verification:
- [ ] Merged DataFrame has exactly 74 rows
- [ ] All criteria columns present for all 3 raters

---

## Phase 2: Krippendorff's Alpha Computation

### Overview
Compute Krippendorff's alpha for each criterion (overall and pairwise).

### Changes Required:

#### 2.1 Add Krippendorff's alpha functions

**File**: `scripts/compute_ec3_irr_stats.py` (append)

```python
import krippendorff


def encode_criterion(value, criterion: str) -> float:
    """Encode criterion value for Krippendorff's alpha."""
    if pd.isna(value):
        return np.nan

    if criterion == "Abstention":
        # Boolean: True=1, False=0
        return 1.0 if value else 0.0
    else:
        # Yes/No/Na: ordinal encoding
        mapping = {"Yes": 2.0, "Na": 1.0, "No": 0.0}
        return mapping.get(str(value), np.nan)


def compute_krippendorff_alpha(
    merged: pd.DataFrame, criterion: str, raters: list[str] | None = None
) -> float:
    """Compute Krippendorff's alpha for a criterion across specified raters."""
    if raters is None:
        raters = RATERS

    reliability_data = []
    for rater in raters:
        col = f"{rater}_{criterion}"
        values = merged[col].apply(lambda x: encode_criterion(x, criterion))
        reliability_data.append(values.to_numpy())

    level = "nominal" if criterion == "Abstention" else "ordinal"

    try:
        alpha = krippendorff.alpha(reliability_data, level_of_measurement=level)
        return alpha if not np.isnan(alpha) else np.nan
    except Exception:
        return np.nan


def compute_all_krippendorff(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute Krippendorff's alpha for all criteria."""
    results = []

    for criterion in CRITERIA:
        row = {
            "Criterion": criterion,
            "Alpha (3 raters)": compute_krippendorff_alpha(merged, criterion, RATERS),
            "Alpha (Sylvain-Stefan)": compute_krippendorff_alpha(merged, criterion, ["sylvain", "stefan"]),
            "Alpha (Sylvain-LLM)": compute_krippendorff_alpha(merged, criterion, ["sylvain", "llm"]),
            "Alpha (Stefan-LLM)": compute_krippendorff_alpha(merged, criterion, ["stefan", "llm"]),
        }
        results.append(row)

    return pd.DataFrame(results)
```

### Success Criteria:

#### Automated Verification:
- [ ] Function returns DataFrame with 5 rows (one per criterion)
- [ ] All alpha values are between -1 and 1 (or NaN)

---

## Phase 3: Fleiss' Kappa and Cohen's Kappa

### Overview
Compute Fleiss' kappa (3 raters) and Cohen's kappa (pairwise).

### Changes Required:

#### 3.1 Add kappa functions

**File**: `scripts/compute_ec3_irr_stats.py` (append)

```python
from sklearn.metrics import cohen_kappa_score


def compute_fleiss_kappa(merged: pd.DataFrame, criterion: str) -> float:
    """Compute Fleiss' kappa for 3 raters on a criterion."""
    # Build category count matrix (n_subjects x n_categories)
    categories = ["Yes", "No", "Na"] if criterion != "Abstention" else [True, False]
    n_subjects = len(merged)
    n_categories = len(categories)
    n_raters = 3

    # Count matrix
    counts = np.zeros((n_subjects, n_categories))

    for i, row in merged.iterrows():
        for rater in RATERS:
            val = row[f"{rater}_{criterion}"]
            if val in categories:
                cat_idx = categories.index(val)
                counts[i, cat_idx] += 1

    # Fleiss' kappa formula
    N = n_subjects
    n = n_raters
    k = n_categories

    # Proportion of assignments to each category
    p_j = counts.sum(axis=0) / (N * n)

    # Agreement per subject
    P_i = (counts.sum(axis=1) ** 2 - n) / (n * (n - 1))
    # Correction: use sum of squares
    P_i = ((counts ** 2).sum(axis=1) - n) / (n * (n - 1))

    P_bar = P_i.mean()
    P_e = (p_j ** 2).sum()

    if P_e == 1:
        return np.nan

    kappa = (P_bar - P_e) / (1 - P_e)
    return kappa


def compute_cohen_kappa_pairwise(merged: pd.DataFrame, criterion: str) -> dict[str, float]:
    """Compute Cohen's kappa for all rater pairs."""
    pairs = [
        ("sylvain", "stefan"),
        ("sylvain", "llm"),
        ("stefan", "llm"),
    ]

    results = {}
    for r1, r2 in pairs:
        col1 = f"{r1}_{criterion}"
        col2 = f"{r2}_{criterion}"

        # Filter valid pairs
        valid = merged[[col1, col2]].dropna()
        if len(valid) < 2:
            results[f"{r1}-{r2}"] = np.nan
            continue

        try:
            kappa = cohen_kappa_score(valid[col1], valid[col2])
            results[f"{r1}-{r2}"] = kappa
        except Exception:
            results[f"{r1}-{r2}"] = np.nan

    return results


def compute_all_kappas(merged: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute Fleiss' and Cohen's kappa for all criteria."""
    fleiss_results = []
    cohen_results = []

    for criterion in CRITERIA:
        fleiss_results.append({
            "Criterion": criterion,
            "Fleiss Kappa": compute_fleiss_kappa(merged, criterion),
        })

        cohen = compute_cohen_kappa_pairwise(merged, criterion)
        cohen["Criterion"] = criterion
        cohen_results.append(cohen)

    fleiss_df = pd.DataFrame(fleiss_results)
    cohen_df = pd.DataFrame(cohen_results)[["Criterion", "sylvain-stefan", "sylvain-llm", "stefan-llm"]]

    return fleiss_df, cohen_df
```

### Success Criteria:

#### Automated Verification:
- [ ] Fleiss' kappa DataFrame has 5 rows
- [ ] Cohen's kappa DataFrame has 5 rows with 3 pair columns

---

## Phase 4: Percentage Agreement and Confusion Matrices

### Overview
Compute percentage agreement (pairwise + 3-way) and confusion matrices.

### Changes Required:

#### 4.1 Add agreement functions

**File**: `scripts/compute_ec3_irr_stats.py` (append)

```python
from sklearn.metrics import confusion_matrix


def compute_percentage_agreement(merged: pd.DataFrame, criterion: str) -> dict:
    """Compute percentage agreement for a criterion."""
    pairs = [
        ("sylvain", "stefan"),
        ("sylvain", "llm"),
        ("stefan", "llm"),
    ]

    results = {}
    for r1, r2 in pairs:
        col1 = f"{r1}_{criterion}"
        col2 = f"{r2}_{criterion}"

        valid = merged[[col1, col2]].dropna()
        total = len(valid)
        if total == 0:
            results[f"{r1}-{r2}"] = {"agree": 0, "total": 0, "pct": 0.0}
            continue

        agree = (valid[col1] == valid[col2]).sum()
        results[f"{r1}-{r2}"] = {"agree": agree, "total": total, "pct": agree / total}

    # 3-way agreement
    cols = [f"{r}_{criterion}" for r in RATERS]
    valid_all = merged[cols].dropna()
    total_all = len(valid_all)
    if total_all > 0:
        agree_all = ((valid_all.iloc[:, 0] == valid_all.iloc[:, 1]) &
                     (valid_all.iloc[:, 0] == valid_all.iloc[:, 2])).sum()
        results["3-way"] = {"agree": agree_all, "total": total_all, "pct": agree_all / total_all}
    else:
        results["3-way"] = {"agree": 0, "total": 0, "pct": 0.0}

    return results


def compute_all_agreements(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute percentage agreement for all criteria."""
    results = []

    for criterion in CRITERIA:
        agreement = compute_percentage_agreement(merged, criterion)
        row = {
            "Criterion": criterion,
            "Sylvain-Stefan (%)": agreement["sylvain-stefan"]["pct"] * 100,
            "Sylvain-LLM (%)": agreement["sylvain-llm"]["pct"] * 100,
            "Stefan-LLM (%)": agreement["stefan-llm"]["pct"] * 100,
            "3-way (%)": agreement["3-way"]["pct"] * 100,
        }
        results.append(row)

    return pd.DataFrame(results)


def compute_confusion_matrices(merged: pd.DataFrame, criterion: str) -> dict[str, np.ndarray]:
    """Compute confusion matrices for all rater pairs."""
    pairs = [
        ("sylvain", "stefan"),
        ("sylvain", "llm"),
        ("stefan", "llm"),
    ]

    results = {}
    for r1, r2 in pairs:
        col1 = f"{r1}_{criterion}"
        col2 = f"{r2}_{criterion}"

        valid = merged[[col1, col2]].dropna()
        if len(valid) < 2:
            continue

        labels = ["Yes", "No", "Na"] if criterion != "Abstention" else [True, False]
        cm = confusion_matrix(valid[col1], valid[col2], labels=labels)
        results[f"{r1}-{r2}"] = cm

    return results
```

### Success Criteria:

#### Automated Verification:
- [ ] Agreement percentages are between 0 and 100
- [ ] Confusion matrices are square with correct dimensions

---

## Phase 5: Spearman Correlations and Category Breakdown

### Overview
Compute Spearman rank correlations and category-level metrics.

### Changes Required:

#### 5.1 Add correlation and category functions

**File**: `scripts/compute_ec3_irr_stats.py` (append)

```python
from scipy.stats import spearmanr


def compute_spearman_correlations(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute Spearman correlations between criteria (using numeric encoding)."""
    # Encode all criteria numerically for correlation
    encoded = pd.DataFrame()
    encoded["Question ID"] = merged["Question ID"]

    for rater in RATERS:
        for criterion in CRITERIA:
            col = f"{rater}_{criterion}"
            encoded[col] = merged[col].apply(lambda x: encode_criterion(x, criterion))

    # Compute correlations between raters for same criterion
    results = []
    pairs = [("sylvain", "stefan"), ("sylvain", "llm"), ("stefan", "llm")]

    for criterion in CRITERIA:
        row = {"Criterion": criterion}
        for r1, r2 in pairs:
            col1 = f"{r1}_{criterion}"
            col2 = f"{r2}_{criterion}"
            valid = encoded[[col1, col2]].dropna()
            if len(valid) >= 3:
                corr, pval = spearmanr(valid[col1], valid[col2])
                row[f"{r1}-{r2} (rho)"] = corr
                row[f"{r1}-{r2} (p)"] = pval
            else:
                row[f"{r1}-{r2} (rho)"] = np.nan
                row[f"{r1}-{r2} (p)"] = np.nan
        results.append(row)

    return pd.DataFrame(results)


def compute_category_breakdown(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute IRR metrics broken down by question category."""
    results = []

    for cat in sorted(merged["Category"].unique()):
        cat_data = merged[merged["Category"] == cat]
        n = len(cat_data)

        # Compute Krippendorff's alpha for Binary (derived from Faithfulness + Completeness)
        # For simplicity, use Faithfulness as proxy
        alpha_faith = compute_krippendorff_alpha(cat_data, "Faithfulness", RATERS)
        alpha_complete = compute_krippendorff_alpha(cat_data, "Completeness", RATERS)

        # 3-way agreement for Faithfulness
        agreement = compute_percentage_agreement(cat_data, "Faithfulness")

        results.append({
            "Category": cat,
            "N": n,
            "Alpha (Faithfulness)": alpha_faith,
            "Alpha (Completeness)": alpha_complete,
            "3-way Agreement (%)": agreement["3-way"]["pct"] * 100,
        })

    return pd.DataFrame(results)
```

### Success Criteria:

#### Automated Verification:
- [ ] Spearman DataFrame has 5 rows
- [ ] Category breakdown has 4 rows (Cat 1-4)

---

## Phase 6: Output Generation (CSV + LaTeX)

### Overview
Generate all output files with CSV and LaTeX formats.

### Changes Required:

#### 6.1 Add output functions

**File**: `scripts/compute_ec3_irr_stats.py` (append)

```python
def df_to_latex(df: pd.DataFrame, caption: str, label: str) -> str:
    """Convert DataFrame to LaTeX table."""
    # Format numeric columns
    formatted = df.copy()
    for col in formatted.columns:
        if formatted[col].dtype in [np.float64, float]:
            formatted[col] = formatted[col].apply(
                lambda x: f"{x:.3f}" if pd.notna(x) else "N/A"
            )

    latex = formatted.to_latex(index=False, escape=True)

    # Wrap in table environment
    full_latex = f"""\\begin{{table}}[htbp]
\\centering
\\caption{{{caption}}}
\\label{{{label}}}
{latex}
\\end{{table}}
"""
    return full_latex


def save_results(df: pd.DataFrame, name: str, caption: str, label: str) -> None:
    """Save DataFrame as CSV and LaTeX."""
    csv_path = OUTPUT_DIR / f"{name}.csv"
    tex_path = OUTPUT_DIR / f"{name}.tex"

    df.to_csv(csv_path, index=False)

    latex = df_to_latex(df, caption, label)
    with open(tex_path, "w") as f:
        f.write(latex)

    print(f"  Saved: {csv_path}")
    print(f"  Saved: {tex_path}")
```

### Success Criteria:

#### Automated Verification:
- [ ] CSV files are valid and loadable
- [ ] LaTeX files compile without errors

---

## Phase 7: Figure Generation with Mako Palette

### Overview
Generate publication-quality figures using Seaborn's "mako" palette.

### Changes Required:

#### 7.1 Add figure generation functions

**File**: `scripts/compute_ec3_irr_stats.py` (append)

```python
import matplotlib.pyplot as plt
import seaborn as sns


def setup_style() -> None:
    """Setup matplotlib/seaborn style for academic figures."""
    plt.style.use("seaborn-v0_8-whitegrid")
    sns.set_palette("mako")
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
    })


def plot_krippendorff_heatmap(alpha_df: pd.DataFrame) -> None:
    """Plot Krippendorff's alpha as heatmap."""
    fig, ax = plt.subplots(figsize=(8, 5))

    # Prepare data for heatmap
    data = alpha_df.set_index("Criterion")

    sns.heatmap(
        data,
        annot=True,
        fmt=".3f",
        cmap="mako",
        vmin=0,
        vmax=1,
        ax=ax,
        cbar_kws={"label": "Krippendorff's Alpha"},
    )

    ax.set_title("Inter-Rater Reliability: Krippendorff's Alpha")
    ax.set_xlabel("Rater Comparison")
    ax.set_ylabel("Criterion")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "krippendorff_heatmap.png")
    plt.close()
    print(f"  Saved: {FIGURES_DIR / 'krippendorff_heatmap.png'}")


def plot_agreement_bars(agreement_df: pd.DataFrame) -> None:
    """Plot percentage agreement as grouped bar chart."""
    fig, ax = plt.subplots(figsize=(10, 6))

    # Melt for plotting
    melted = agreement_df.melt(
        id_vars=["Criterion"],
        var_name="Comparison",
        value_name="Agreement (%)"
    )

    colors = sns.color_palette("mako", n_colors=4)

    sns.barplot(
        data=melted,
        x="Criterion",
        y="Agreement (%)",
        hue="Comparison",
        palette=colors,
        ax=ax,
    )

    ax.set_title("Percentage Agreement by Criterion")
    ax.set_ylim(0, 100)
    ax.legend(title="", bbox_to_anchor=(1.02, 1), loc="upper left")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "agreement_bars.png")
    plt.close()
    print(f"  Saved: {FIGURES_DIR / 'agreement_bars.png'}")


def plot_category_breakdown(cat_df: pd.DataFrame) -> None:
    """Plot category-level breakdown."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    colors = sns.color_palette("mako", n_colors=4)

    # Alpha by category
    cat_df.plot(
        x="Category",
        y=["Alpha (Faithfulness)", "Alpha (Completeness)"],
        kind="bar",
        ax=axes[0],
        color=colors[:2],
    )
    axes[0].set_title("Krippendorff's Alpha by Category")
    axes[0].set_ylabel("Alpha")
    axes[0].set_ylim(0, 1)
    axes[0].legend(["Faithfulness", "Completeness"])
    axes[0].tick_params(axis="x", rotation=0)

    # Sample size by category
    axes[1].bar(cat_df["Category"], cat_df["N"], color=colors[2])
    axes[1].set_title("Sample Size by Category")
    axes[1].set_xlabel("Category")
    axes[1].set_ylabel("N")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "category_breakdown.png")
    plt.close()
    print(f"  Saved: {FIGURES_DIR / 'category_breakdown.png'}")


def plot_confusion_matrix(cm: np.ndarray, labels: list, title: str, filename: str) -> None:
    """Plot a single confusion matrix."""
    fig, ax = plt.subplots(figsize=(5, 4))

    sns.heatmap(
        cm,
        annot=True,
        fmt="d",
        cmap="mako",
        xticklabels=labels,
        yticklabels=labels,
        ax=ax,
    )

    ax.set_title(title)
    ax.set_xlabel("Rater 2")
    ax.set_ylabel("Rater 1")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / filename)
    plt.close()
```

### Success Criteria:

#### Automated Verification:
- [ ] PNG files are generated in `reports/ec3_irr/figures/`
- [ ] Files have appropriate resolution (300 DPI)

---

## Phase 8: Main Function and CLI

### Overview
Wire everything together in a main function with CLI argument parsing.

### Changes Required:

#### 8.1 Add main function

**File**: `scripts/compute_ec3_irr_stats.py` (append)

```python
def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compute EC3 Paper IRR Statistics"
    )
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Skip figure generation",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("EC3 Paper IRR Statistics")
    print("=" * 60)

    # Setup
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    setup_style()

    # Load data
    print("\n1. Loading data...")
    sylvain, stefan, llm = load_and_clean_data()
    valid_ids = filter_valid_questions(sylvain, stefan, llm)
    merged = merge_ratings(sylvain, stefan, llm, valid_ids)
    print(f"   Valid questions: {len(merged)}")

    # Krippendorff's alpha
    print("\n2. Computing Krippendorff's alpha...")
    alpha_df = compute_all_krippendorff(merged)
    save_results(alpha_df, "krippendorff_alpha",
                 "Krippendorff's Alpha for Inter-Rater Reliability",
                 "tab:krippendorff")

    # Fleiss' and Cohen's kappa
    print("\n3. Computing Fleiss' and Cohen's kappa...")
    fleiss_df, cohen_df = compute_all_kappas(merged)
    save_results(fleiss_df, "fleiss_kappa",
                 "Fleiss' Kappa for Three-Rater Agreement",
                 "tab:fleiss")
    save_results(cohen_df, "cohen_kappa_pairwise",
                 "Cohen's Kappa for Pairwise Agreement",
                 "tab:cohen")

    # Percentage agreement
    print("\n4. Computing percentage agreement...")
    agreement_df = compute_all_agreements(merged)
    save_results(agreement_df, "percentage_agreement",
                 "Percentage Agreement by Criterion",
                 "tab:agreement")

    # Spearman correlations
    print("\n5. Computing Spearman correlations...")
    spearman_df = compute_spearman_correlations(merged)
    save_results(spearman_df, "spearman_correlations",
                 "Spearman Rank Correlations Between Raters",
                 "tab:spearman")

    # Category breakdown
    print("\n6. Computing category breakdown...")
    cat_df = compute_category_breakdown(merged)
    save_results(cat_df, "category_breakdown",
                 "IRR Metrics by Question Category",
                 "tab:category")

    # Figures
    if not args.skip_figures:
        print("\n7. Generating figures...")
        plot_krippendorff_heatmap(alpha_df)
        plot_agreement_bars(agreement_df)
        plot_category_breakdown(cat_df)

        # Confusion matrices for Faithfulness (most important criterion)
        cms = compute_confusion_matrices(merged, "Faithfulness")
        labels = ["Yes", "No", "Na"]
        for pair, cm in cms.items():
            plot_confusion_matrix(
                cm, labels,
                f"Faithfulness: {pair}",
                f"confusion_faithfulness_{pair.replace('-', '_')}.png"
            )

    print("\n" + "=" * 60)
    print("Done! Results saved to:", OUTPUT_DIR)
    print("=" * 60)


if __name__ == "__main__":
    main()
```

### Success Criteria:

#### Automated Verification:
- [ ] `uv run scripts/compute_ec3_irr_stats.py` completes without error
- [ ] All output files exist in `reports/ec3_irr/`
- [ ] Type check passes: `uvx ty check scripts/compute_ec3_irr_stats.py`
- [ ] Lint passes: `uvx ruff check scripts/compute_ec3_irr_stats.py`

#### Manual Verification:
- [ ] Output tables look correct and match expected values
- [ ] Figures use mako palette (blue/teal tones, not green/yellow/red)
- [ ] LaTeX tables compile in paper

---

---

## Phase 9: Cross-System Discriminative Analysis

### Overview
Compare criterion distributions across 3 QA systems (Cobbie, Baseline, Gemini-Flash) to assess discriminative power and identify ceiling/floor effects.

**Systems:**
- **Cobbie**: Main system (from LLM Judge CSV)
- **Baseline**: Same LLM, simpler QA system (MLflow run: `952f4e16f4464e33b4c72f9ed10d9195`)
- **Gemini-Flash**: Same system, weaker LLM (MLflow run: `b1ce27fe59714eaeb343753ddc5f61d0`)

**Key observations from preliminary analysis:**
| Metric | Cobbie | Baseline | Gemini-Flash |
|--------|--------|----------|--------------|
| Abstention | 15% | 52% | 56% |
| Faithfulness=Yes | 72% | 28% | 22% |
| Completeness=Yes | 73% | 17% | 24% |
| Transparency=Yes | 75% | 31% | 18% |
| Relevance=Yes | 76% | 42% | 38% |

**Relevance shows ceiling effect** - high "Yes" rate even for failing systems.

### Changes Required:

#### 9.1 Add MLflow data extraction

**File**: `scripts/compute_ec3_irr_stats.py` (append)

```python
import mlflow
from mlflow import MlflowClient
from src.config import MLFLOW_URI

# MLflow run IDs for comparison systems
BASELINE_RUN_ID = "952f4e16f4464e33b4c72f9ed10d9195"
GEMINI_RUN_ID = "b1ce27fe59714eaeb343753ddc5f61d0"


def extract_mlflow_evaluations(run_id: str, system_name: str) -> pd.DataFrame:
    """Extract LLM judge evaluations from MLflow run."""
    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient()

    run = client.get_run(run_id)
    experiment_id = run.info.experiment_id

    nested = client.search_runs(
        experiment_ids=[experiment_id],
        filter_string=f'tags.mlflow.parentRunId = "{run_id}"',
        max_results=1000,
    )

    rows = []
    for n in nested:
        params = n.data.params
        tags = n.data.tags

        # Extract question ID from run name
        run_name = tags.get("mlflow.runName", "")
        question_id = None
        if run_name.startswith("question_"):
            parts = run_name.split("_")
            if len(parts) >= 3:
                question_id = int(parts[2])
        if question_id is None:
            question_id = int(params.get("question_id", 0))

        rows.append({
            "Question ID": question_id,
            "System": system_name,
            "Abstention": params.get("abstention") == "True",
            "Faithfulness": params.get("faithfulness", "Na"),
            "Completeness": params.get("completeness", "Na"),
            "Transparency": params.get("transparency", "Na"),
            "Relevance": params.get("relevance", "Na"),
        })

    return pd.DataFrame(rows)


def load_all_systems() -> pd.DataFrame:
    """Load evaluations from all 3 systems."""
    # Cobbie from CSV
    llm_csv = pd.read_csv(LLM_FILE)
    cobbie = llm_csv[["Question ID", "Abstention", "Faithfulness", "Completeness",
                       "Transparency", "Relevance"]].copy()
    cobbie["System"] = "Cobbie"

    # Baseline and Gemini from MLflow
    baseline = extract_mlflow_evaluations(BASELINE_RUN_ID, "Baseline")
    gemini = extract_mlflow_evaluations(GEMINI_RUN_ID, "Gemini-Flash")

    # Combine
    all_systems = pd.concat([cobbie, baseline, gemini], ignore_index=True)
    return all_systems
```

#### 9.2 Add discriminative power metrics

**File**: `scripts/compute_ec3_irr_stats.py` (append)

```python
from scipy.stats import entropy


def compute_criterion_entropy(df: pd.DataFrame, criterion: str) -> float:
    """Compute normalized entropy for a criterion (higher = more discriminative)."""
    counts = df[criterion].value_counts(normalize=True)
    n_categories = len(counts)
    if n_categories <= 1:
        return 0.0

    # Normalized entropy (0 = all same, 1 = uniform distribution)
    h = entropy(counts, base=n_categories)
    return h


def compute_discriminative_power(all_systems: pd.DataFrame) -> pd.DataFrame:
    """Compute discriminative power metrics for each criterion across systems."""
    results = []

    for criterion in CRITERIA:
        row = {"Criterion": criterion}

        for system in ["Cobbie", "Baseline", "Gemini-Flash"]:
            sys_data = all_systems[all_systems["System"] == system]

            # Entropy (distribution spread)
            row[f"{system} Entropy"] = compute_criterion_entropy(sys_data, criterion)

            # Yes rate (for non-abstention criteria)
            if criterion != "Abstention":
                yes_rate = (sys_data[criterion] == "Yes").mean()
                row[f"{system} Yes%"] = yes_rate * 100
            else:
                abst_rate = sys_data[criterion].mean()
                row[f"{system} Abst%"] = abst_rate * 100

        # Variance across systems (higher = more sensitive to system quality)
        if criterion != "Abstention":
            yes_rates = [
                (all_systems[all_systems["System"] == s][criterion] == "Yes").mean()
                for s in ["Cobbie", "Baseline", "Gemini-Flash"]
            ]
        else:
            yes_rates = [
                all_systems[all_systems["System"] == s][criterion].mean()
                for s in ["Cobbie", "Baseline", "Gemini-Flash"]
            ]

        row["Cross-System Variance"] = np.var(yes_rates)
        row["Cross-System Range"] = max(yes_rates) - min(yes_rates)

        results.append(row)

    return pd.DataFrame(results)


def identify_ceiling_floor_effects(all_systems: pd.DataFrame) -> pd.DataFrame:
    """Identify criteria with ceiling (>90% Yes) or floor (<10% Yes) effects."""
    results = []

    for criterion in CRITERIA:
        if criterion == "Abstention":
            continue

        for system in ["Cobbie", "Baseline", "Gemini-Flash"]:
            sys_data = all_systems[all_systems["System"] == system]
            yes_rate = (sys_data[criterion] == "Yes").mean() * 100
            no_rate = (sys_data[criterion] == "No").mean() * 100

            effect = "Normal"
            if yes_rate > 90:
                effect = "Ceiling"
            elif yes_rate < 10:
                effect = "Floor (Yes)"
            elif no_rate > 90:
                effect = "Floor (No)"

            results.append({
                "Criterion": criterion,
                "System": system,
                "Yes%": yes_rate,
                "No%": no_rate,
                "Effect": effect,
            })

    return pd.DataFrame(results)
```

#### 9.3 Add cross-system comparison figures

**File**: `scripts/compute_ec3_irr_stats.py` (append)

```python
def plot_cross_system_comparison(all_systems: pd.DataFrame) -> None:
    """Plot criterion distributions across systems."""
    fig, axes = plt.subplots(2, 3, figsize=(14, 9))
    axes = axes.flatten()

    colors = sns.color_palette("mako", n_colors=3)
    system_order = ["Cobbie", "Baseline", "Gemini-Flash"]

    for idx, criterion in enumerate(CRITERIA):
        ax = axes[idx]

        # Compute proportions for each system
        plot_data = []
        for system in system_order:
            sys_data = all_systems[all_systems["System"] == system]

            if criterion == "Abstention":
                # Boolean: show True/False rates
                true_rate = sys_data[criterion].mean() * 100
                false_rate = (1 - sys_data[criterion].mean()) * 100
                plot_data.append({"System": system, "Value": "True", "Rate": true_rate})
                plot_data.append({"System": system, "Value": "False", "Rate": false_rate})
            else:
                # Yes/No/Na
                for val in ["Yes", "No", "Na"]:
                    rate = (sys_data[criterion] == val).mean() * 100
                    plot_data.append({"System": system, "Value": val, "Rate": rate})

        plot_df = pd.DataFrame(plot_data)

        sns.barplot(
            data=plot_df,
            x="System",
            y="Rate",
            hue="Value",
            palette=colors[:len(plot_df["Value"].unique())],
            ax=ax,
        )

        ax.set_title(criterion)
        ax.set_ylabel("Rate (%)")
        ax.set_ylim(0, 100)
        ax.legend(title="", loc="upper right")

    # Remove empty subplot
    axes[5].axis("off")

    plt.suptitle("Criterion Distributions by System", fontsize=14, y=1.02)
    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "cross_system_comparison.png")
    plt.close()
    print(f"  Saved: {FIGURES_DIR / 'cross_system_comparison.png'}")


def plot_discriminative_power(disc_df: pd.DataFrame) -> None:
    """Plot discriminative power (cross-system variance) for each criterion."""
    fig, ax = plt.subplots(figsize=(8, 5))

    colors = sns.color_palette("mako", n_colors=5)

    # Sort by variance
    disc_df_sorted = disc_df.sort_values("Cross-System Range", ascending=True)

    ax.barh(
        disc_df_sorted["Criterion"],
        disc_df_sorted["Cross-System Range"] * 100,
        color=colors[2],
    )

    ax.set_xlabel("Cross-System Range (percentage points)")
    ax.set_title("Criterion Sensitivity to System Quality\n(higher = more discriminative)")

    # Add annotations
    for i, (_, row) in enumerate(disc_df_sorted.iterrows()):
        ax.text(
            row["Cross-System Range"] * 100 + 1,
            i,
            f"{row['Cross-System Range']*100:.1f}pp",
            va="center",
            fontsize=9,
        )

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "discriminative_power.png")
    plt.close()
    print(f"  Saved: {FIGURES_DIR / 'discriminative_power.png'}")
```

#### 9.4 Update main function

**File**: `scripts/compute_ec3_irr_stats.py` (update main)

Add to main() after the IRR analysis:

```python
    # Cross-system analysis
    print("\n8. Cross-system discriminative analysis...")
    all_systems = load_all_systems()
    print(f"   Loaded {len(all_systems)} evaluations across 3 systems")

    disc_df = compute_discriminative_power(all_systems)
    save_results(disc_df, "discriminative_power",
                 "Criterion Discriminative Power Across Systems",
                 "tab:discriminative")

    ceiling_df = identify_ceiling_floor_effects(all_systems)
    save_results(ceiling_df, "ceiling_floor_effects",
                 "Ceiling and Floor Effects by Criterion and System",
                 "tab:ceiling")

    if not args.skip_figures:
        plot_cross_system_comparison(all_systems)
        plot_discriminative_power(disc_df)
```

### Success Criteria:

#### Automated Verification:
- [ ] MLflow data extraction returns 100 rows per system
- [ ] Discriminative power DataFrame has 5 rows
- [ ] Cross-system figures generated

#### Manual Verification:
- [ ] Abstention shows highest discriminative power (~40pp range)
- [ ] Relevance shows lowest discriminative power (ceiling effect confirmed)
- [ ] Transparency becomes more discriminating with weaker systems

---

## Testing Strategy

### Automated Tests:
- Run type checker and linter
- Verify output file existence
- Check DataFrame shapes and value ranges

### Manual Testing:
1. Run script: `uv run scripts/compute_ec3_irr_stats.py`
2. Verify 74 questions processed for IRR
3. Verify 300 evaluations (100 × 3 systems) for cross-system analysis
4. Check figures in `reports/ec3_irr/figures/` for correct colors
5. Spot-check discriminative power values

## Key Expected Results

Based on preliminary analysis:

**IRR Analysis (74 questions, 3 raters):**
- Krippendorff's alpha expected to vary by criterion
- Human-Human agreement typically higher than Human-LLM

**Cross-System Analysis:**
- **Abstention**: ~40pp range (15% → 56%) - highly discriminative
- **Completeness**: ~56pp range (73% → 17%) - highly discriminative
- **Faithfulness**: ~50pp range (72% → 22%) - highly discriminative
- **Transparency**: ~57pp range (75% → 18%) - highly discriminative
- **Relevance**: ~38pp range (76% → 38%) - moderate, but shows ceiling effect

**Implications:**
- Relevance criterion may be redundant for high-quality systems
- Abstention is the most reliable indicator of system capability
- Transparency becomes more informative for weaker systems

## References

- Existing script: `scripts/create_grading_sheet.py` (Krippendorff functions)
- Data files: `src/db/eval/*.csv`
- MLflow runs: Baseline (`952f4e16...`), Gemini (`b1ce27fe...`)
- Krippendorff library: https://github.com/pln-fing-udelar/krippendorff
