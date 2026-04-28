#!/usr/bin/env python3
"""
Compute EC3 Paper IRR Statistics

Computes inter-rater reliability metrics for 4 raters (H1, H2, LLM₁, LLM₂)
plus post-discussion consolidated human judgment (H_cons).

Includes pairwise and 4-way metrics, plus:
- H1-H2 post-discussion agreement
- Consolidated human vs LLM₁ and LLM₂

Outputs CSV reports, LaTeX tables, and figures.

Usage:
    uv run scripts/compute_ec3_irr_stats.py
"""

import argparse
from pathlib import Path

import krippendorff
import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
import seaborn as sns
from mlflow.tracking import MlflowClient
from scipy.stats import entropy, spearmanr
from sklearn.metrics import confusion_matrix

from src.config import MLFLOW_URI

# File paths
EVAL_DIR = Path("src/db/eval")
H1_FILE = EVAL_DIR / "EC3-2026 - H1 (H1) 2026-01-20_21-07.csv"
H2_FILE = EVAL_DIR / "EC3-2026 - H2 (H2) 2026-01-20_21-07.csv"
LLM_FILE = EVAL_DIR / "EC3-2026 - LLM_Judge (LLM_Judge) 2026-01-20_21-08.csv"
GEMINI_FILE = EVAL_DIR / "EC3-2026 - Gemini_Judge (Gemini_Judge) 2026-01-21_16-00.csv"
CONSOLIDATED_FILE = EVAL_DIR / "EC3-2026 - human-human final agreement.csv"
OUTPUT_DIR = Path("outputs/ec3")
FIGURES_DIR = OUTPUT_DIR / "figures"

CRITERIA = ["Abstention", "Faithfulness", "Completeness", "Transparency", "Relevance"]
RATERS = ["h1", "h2", "llm", "gemini"]

# Display names for figures and tables
RATER_DISPLAY_NAMES = {
    "h1": "H1",
    "h2": "H2",
    "llm": "LLM₁",
    "gemini": "LLM₂",
    "consolidated": "H_cons",
}

# System names for cross-system comparison
SYSTEM_NAMES = {
    "cobbie": "Agentic",
    "baseline": "Static",
    "gemini-flash": "Lightweight",
}
SYSTEMS = ["Agentic", "Static", "Lightweight"]

def get_display_name(rater: str) -> str:
    """Get display name for a rater."""
    return RATER_DISPLAY_NAMES.get(rater, rater)

def get_pair_display_name(pair: str) -> str:
    """Get display name for a rater pair like 'h1-h2' -> 'H1-H2'."""
    parts = pair.split("-")
    return "-".join(get_display_name(p) for p in parts)

# MLflow run IDs for comparison systems
BASELINE_RUN_ID = "952f4e16f4464e33b4c72f9ed10d9195"
GEMINI_RUN_ID = "b1ce27fe59714eaeb343753ddc5f61d0"


# =============================================================================
# Phase 1: Data Loading and Validation
# =============================================================================


def load_and_clean_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load and clean the 5 CSV files (4 original raters + consolidated)."""
    h1 = pd.read_csv(H1_FILE)
    h2 = pd.read_csv(H2_FILE)
    llm = pd.read_csv(LLM_FILE)
    gemini = pd.read_csv(GEMINI_FILE)
    consolidated = pd.read_csv(CONSOLIDATED_FILE)

    # Drop empty rows
    h2 = h2.dropna(subset=["Question ID"])
    consolidated = consolidated.dropna(subset=["Question ID"])

    # Ensure Question ID is int
    for df in [h1, h2, llm, gemini, consolidated]:
        df["Question ID"] = df["Question ID"].astype(int)

    # Normalise Abstention across all sources
    for df in [h1, h2, llm, gemini, consolidated]:
        df["Abstention"] = df["Abstention"].apply(normalise_abstention)

    return h1, h2, llm, gemini, consolidated


def filter_valid_questions(
    h1: pd.DataFrame,
    h2: pd.DataFrame,
    llm: pd.DataFrame,
    gemini: pd.DataFrame,
    consolidated: pd.DataFrame,
) -> set[int]:
    """Return set of valid Question IDs (intersection with complete evaluations).

    For discussed questions (those in consolidated CSV), both evaluators must be present.
    """
    # Filter H1: Error=0, UPDATED != 'x'
    h1_valid = h1[(h1["Error"] == 0) & (h1["UPDATED"] != "x")]

    # Filter H2: Error=0, UPDATED != 'x', Abstention not NaN
    h2_valid = h2[
        (h2["Error"] == 0)
        & (h2["UPDATED"] != "x")
        & h2["Abstention"].notna()
    ]

    # LLM and Gemini have no Error/UPDATED columns, all are complete
    llm_valid = llm
    gemini_valid = gemini

    # Original 4-way intersection
    original_valid = (
        set(h1_valid["Question ID"])
        & set(h2_valid["Question ID"])
        & set(llm_valid["Question ID"])
        & set(gemini_valid["Question ID"])
    )

    # Discussed questions must have both evaluators in consolidated CSV
    discussed_ids = set(consolidated["Question ID"].unique())
    consolidated_valid: set[int] = set()
    for qid in discussed_ids:
        q_rows = consolidated[consolidated["Question ID"] == qid]
        evaluators = set(q_rows["Evaluator"].str.lower().str.strip())
        if {"h1", "h2"} <= evaluators:
            consolidated_valid.add(qid)

    # Valid = original valid, but discussed questions must also be in consolidated_valid
    valid_ids: set[int] = set()
    for qid in original_valid:
        if qid in discussed_ids:
            if qid in consolidated_valid:
                valid_ids.add(qid)
        else:
            valid_ids.add(qid)

    return valid_ids


def merge_ratings(
    h1: pd.DataFrame,
    h2: pd.DataFrame,
    llm: pd.DataFrame,
    gemini: pd.DataFrame,
    valid_ids: set[int],
) -> pd.DataFrame:
    """Merge ratings from all 4 raters into a single DataFrame."""
    # Filter to valid IDs
    s = h1[h1["Question ID"].isin(valid_ids)].copy()
    st = h2[h2["Question ID"].isin(valid_ids)].copy()
    ll = llm[llm["Question ID"].isin(valid_ids)].copy()
    gm = gemini[gemini["Question ID"].isin(valid_ids)].copy()

    # Rename columns with rater prefix
    s_cols = {c: f"h1_{c}" for c in CRITERIA}
    st_cols = {c: f"h2_{c}" for c in CRITERIA}
    l_cols = {c: f"llm_{c}" for c in CRITERIA}
    g_cols = {c: f"gemini_{c}" for c in CRITERIA}

    s = s.rename(columns=s_cols)
    st = st.rename(columns=st_cols)
    ll = ll.rename(columns=l_cols)
    gm = gm.rename(columns=g_cols)

    # Merge on Question ID
    merged = s[["Question ID", "Category", "Question"] + list(s_cols.values())]
    merged = merged.merge(
        st[["Question ID"] + list(st_cols.values())], on="Question ID"
    )
    merged = merged.merge(
        ll[["Question ID"] + list(l_cols.values())], on="Question ID"
    )
    merged = merged.merge(
        gm[["Question ID"] + list(g_cols.values())], on="Question ID"
    )

    return merged.sort_values("Question ID").reset_index(drop=True)


def augment_with_consolidated(
    merged: pd.DataFrame,
    h1: pd.DataFrame,
    h2: pd.DataFrame,
    consolidated: pd.DataFrame,
    valid_ids: set[int],
) -> tuple[pd.DataFrame, int, int]:
    """Add h1_post_*, h2_post_*, and consolidated_* columns to merged.

    For originally-agreed questions: post = original, consolidated = h1's value.
    For discussed questions: post = post-discussion values from consolidated CSV,
    consolidated = agreed value (NaN where still disagreed).

    Returns (merged, n_agreed, n_disagreed).
    """
    discussed_ids = set(consolidated["Question ID"].unique()) & valid_ids

    # Build lookup dicts from consolidated CSV
    # {qid: {evaluator: row_series}}
    cons_lookup: dict[int, dict[str, pd.Series]] = {}
    for qid in discussed_ids:
        q_rows = consolidated[consolidated["Question ID"] == qid]
        for _, row in q_rows.iterrows():
            evaluator = str(row["Evaluator"]).strip().lower()
            cons_lookup.setdefault(qid, {})[evaluator] = row

    n_agreed = 0
    n_disagreed = 0

    for criterion in CRITERIA:
        h1_post_vals = []
        h2_post_vals = []
        consolidated_vals = []

        for _, mrow in merged.iterrows():
            qid = mrow["Question ID"]

            if qid in discussed_ids and qid in cons_lookup:
                # Discussed question: use post-discussion values
                s_post = cons_lookup[qid].get("h1")
                st_post = cons_lookup[qid].get("h2")
                sv = s_post[criterion] if s_post is not None else np.nan
                stv = st_post[criterion] if st_post is not None else np.nan
                h1_post_vals.append(sv)
                h2_post_vals.append(stv)

                # Consolidated = agreed value or NaN
                if encode_criterion(sv, criterion) == encode_criterion(stv, criterion):
                    consolidated_vals.append(sv)
                else:
                    consolidated_vals.append(np.nan)
            else:
                # Originally agreed: post = original
                sv = mrow[f"h1_{criterion}"]
                stv = mrow[f"h2_{criterion}"]
                h1_post_vals.append(sv)
                h2_post_vals.append(stv)
                # Consolidated = h1's value (they agreed)
                consolidated_vals.append(sv)

        merged[f"h1_post_{criterion}"] = h1_post_vals
        merged[f"h2_post_{criterion}"] = h2_post_vals
        merged[f"consolidated_{criterion}"] = consolidated_vals

    # Count agreed/disagreed (check all criteria per question)
    for _, mrow in merged.iterrows():
        all_agree = all(pd.notna(mrow[f"consolidated_{c}"]) for c in CRITERIA)
        if all_agree:
            n_agreed += 1
        else:
            n_disagreed += 1

    return merged, n_agreed, n_disagreed


# =============================================================================
# Phase 2: Krippendorff's Alpha Computation
# =============================================================================


def encode_criterion(value: object, criterion: str) -> float:
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


def normalise_abstention(val: object) -> object:
    """Normalise Abstention to Python bool."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("true", "1", "1.0"):
        return True
    if s in ("false", "0", "0.0"):
        return False
    return np.nan


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
            "Alpha (4 raters)": compute_krippendorff_alpha(merged, criterion, RATERS),
            f"Alpha ({get_display_name('h1')}-{get_display_name('h2')})": compute_krippendorff_alpha(
                merged, criterion, ["h1", "h2"]
            ),
            f"Alpha ({get_display_name('h1')}-{get_display_name('llm')})": compute_krippendorff_alpha(
                merged, criterion, ["h1", "llm"]
            ),
            f"Alpha ({get_display_name('h2')}-{get_display_name('llm')})": compute_krippendorff_alpha(
                merged, criterion, ["h2", "llm"]
            ),
            f"Alpha ({get_display_name('h1')}-{get_display_name('gemini')})": compute_krippendorff_alpha(
                merged, criterion, ["h1", "gemini"]
            ),
            f"Alpha ({get_display_name('h2')}-{get_display_name('gemini')})": compute_krippendorff_alpha(
                merged, criterion, ["h2", "gemini"]
            ),
            f"Alpha ({get_display_name('llm')}-{get_display_name('gemini')})": compute_krippendorff_alpha(
                merged, criterion, ["llm", "gemini"]
            ),
            # Post-discussion and consolidated comparisons
            "Alpha (H1-H2 post)": compute_krippendorff_alpha(
                merged, criterion, ["h1_post", "h2_post"]
            ),
            f"Alpha ({get_display_name('consolidated')}-{get_display_name('llm')})": compute_krippendorff_alpha(
                merged, criterion, ["consolidated", "llm"]
            ),
            f"Alpha ({get_display_name('consolidated')}-{get_display_name('gemini')})": compute_krippendorff_alpha(
                merged, criterion, ["consolidated", "gemini"]
            ),
        }
        results.append(row)

    return pd.DataFrame(results)


# =============================================================================
# Phase 4: Percentage Agreement and Confusion Matrices
# =============================================================================


def compute_percentage_agreement(merged: pd.DataFrame, criterion: str) -> dict:
    """Compute percentage agreement for a criterion."""
    pairs = [
        ("h1", "h2"),
        ("h1", "llm"),
        ("h2", "llm"),
        ("h1", "gemini"),
        ("h2", "gemini"),
        ("llm", "gemini"),
        ("h1_post", "h2_post"),
        ("consolidated", "llm"),
        ("consolidated", "gemini"),
    ]

    results: dict[str, dict] = {}
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

    # 4-way agreement
    cols = [f"{r}_{criterion}" for r in RATERS]
    valid_all = merged[cols].dropna()
    total_all = len(valid_all)
    if total_all > 0:
        agree_all = (
            (valid_all.iloc[:, 0] == valid_all.iloc[:, 1])
            & (valid_all.iloc[:, 0] == valid_all.iloc[:, 2])
            & (valid_all.iloc[:, 0] == valid_all.iloc[:, 3])
        ).sum()
        results["4-way"] = {
            "agree": agree_all,
            "total": total_all,
            "pct": agree_all / total_all,
        }
    else:
        results["4-way"] = {"agree": 0, "total": 0, "pct": 0.0}

    return results


def compute_all_agreements(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute percentage agreement for all criteria."""
    results = []

    for criterion in CRITERIA:
        agreement = compute_percentage_agreement(merged, criterion)
        row = {
            "Criterion": criterion,
            f"{get_display_name('h1')}-{get_display_name('h2')} (%)": agreement["h1-h2"]["pct"] * 100,
            f"{get_display_name('h1')}-{get_display_name('llm')} (%)": agreement["h1-llm"]["pct"] * 100,
            f"{get_display_name('h2')}-{get_display_name('llm')} (%)": agreement["h2-llm"]["pct"] * 100,
            f"{get_display_name('h1')}-{get_display_name('gemini')} (%)": agreement["h1-gemini"]["pct"] * 100,
            f"{get_display_name('h2')}-{get_display_name('gemini')} (%)": agreement["h2-gemini"]["pct"] * 100,
            f"{get_display_name('llm')}-{get_display_name('gemini')} (%)": agreement["llm-gemini"]["pct"] * 100,
            "4-way (%)": agreement["4-way"]["pct"] * 100,
            "H1-H2 post (%)": agreement["h1_post-h2_post"]["pct"] * 100,
            f"{get_display_name('consolidated')}-{get_display_name('llm')} (%)": agreement["consolidated-llm"]["pct"] * 100,
            f"{get_display_name('consolidated')}-{get_display_name('gemini')} (%)": agreement["consolidated-gemini"]["pct"] * 100,
        }
        results.append(row)

    return pd.DataFrame(results)


def compute_confusion_matrices(
    merged: pd.DataFrame, criterion: str
) -> dict[str, np.ndarray]:
    """Compute confusion matrices for all rater pairs."""
    pairs = [
        ("h1", "h2"),
        ("h1", "llm"),
        ("h2", "llm"),
        ("h1", "gemini"),
        ("h2", "gemini"),
        ("llm", "gemini"),
    ]

    results = {}
    for r1, r2 in pairs:
        col1 = f"{r1}_{criterion}"
        col2 = f"{r2}_{criterion}"

        valid = merged[[col1, col2]].dropna()
        if len(valid) < 2:
            continue

        labels: list[object] = (
            ["Yes", "No", "Na"] if criterion != "Abstention" else [True, False]
        )
        cm = confusion_matrix(valid[col1], valid[col2], labels=labels)
        results[f"{r1}-{r2}"] = cm

    return results


# =============================================================================
# Phase 5: Spearman Correlations and Category Breakdown
# =============================================================================


def compute_spearman_correlations(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute Spearman correlations between raters for same criterion."""
    # Encode all criteria numerically for correlation
    encoded = pd.DataFrame()
    encoded["Question ID"] = merged["Question ID"]

    all_prefixes = RATERS + ["h1_post", "h2_post", "consolidated"]
    for prefix in all_prefixes:
        for criterion in CRITERIA:
            col = f"{prefix}_{criterion}"
            if col in merged.columns:
                encoded[col] = merged[col].apply(lambda x: encode_criterion(x, criterion))

    # Compute correlations between raters for same criterion
    results = []
    pairs = [
        ("h1", "h2"),
        ("h1", "llm"),
        ("h2", "llm"),
        ("h1", "gemini"),
        ("h2", "gemini"),
        ("llm", "gemini"),
        ("h1_post", "h2_post"),
        ("consolidated", "llm"),
        ("consolidated", "gemini"),
    ]

    for criterion in CRITERIA:
        row: dict[str, object] = {"Criterion": criterion}
        for r1, r2 in pairs:
            col1 = f"{r1}_{criterion}"
            col2 = f"{r2}_{criterion}"
            # Use display names, with special handling for post-discussion prefixes
            if r1 == "h1_post":
                pair_display = "H1_post-H2_post" if r2 == "h2_post" else f"H1_post-{get_display_name(r2)}"
            elif r1 == "consolidated":
                pair_display = f"{get_display_name('consolidated')}-{get_display_name(r2)}"
            else:
                pair_display = f"{get_display_name(r1)}-{get_display_name(r2)}"

            valid = encoded[[col1, col2]].dropna()
            if len(valid) >= 3:
                corr, pval = spearmanr(valid[col1], valid[col2])
                row[f"{pair_display} (rho)"] = corr
                row[f"{pair_display} (p)"] = pval
            else:
                row[f"{pair_display} (rho)"] = np.nan
                row[f"{pair_display} (p)"] = np.nan
        results.append(row)

    return pd.DataFrame(results)


def compute_inter_criteria_correlations(
    merged: pd.DataFrame, rater: str = "llm"
) -> pd.DataFrame:
    """Compute correlations between different criteria for a given rater.

    This shows whether criteria measure distinct aspects or are redundant.
    Low correlations = criteria capture different information (good).
    High correlations = criteria are redundant (consider removing).
    """
    # Encode criteria numerically
    encoded = pd.DataFrame()
    criteria_no_abstention = [c for c in CRITERIA if c != "Abstention"]

    for criterion in criteria_no_abstention:
        col = f"{rater}_{criterion}"
        encoded[criterion] = merged[col].apply(lambda x: encode_criterion(x, criterion))

    # Compute correlation matrix
    corr_matrix = encoded.corr(method="spearman")

    return corr_matrix


def compute_criteria_vs_binary(
    h1: pd.DataFrame,
    h2: pd.DataFrame,
    llm: pd.DataFrame,
    gemini: pd.DataFrame,
    valid_ids: set[int],
) -> pd.DataFrame:
    """Compare granular criteria against binary classification.

    Shows how well each criterion predicts the overall binary assessment
    and whether granular criteria add value beyond binary.
    """
    # Get H1's binary classification (ground truth for this analysis)
    s = h1[h1["Question ID"].isin(valid_ids)].copy()

    # Encode binary classification
    s["Binary"] = s["Binary Classification"].apply(
        lambda x: 1.0 if x == "correct" else 0.0 if x == "wrong" else np.nan
    )

    results = []
    criteria_no_abstention = [c for c in CRITERIA if c != "Abstention"]

    for criterion in criteria_no_abstention:
        # Encode criterion as binary (Yes=1, No/Na=0)
        s[f"{criterion}_binary"] = s[criterion].apply(
            lambda x: 1.0 if x == "Yes" else 0.0
        )

        # Correlation with binary
        valid = s[["Binary", f"{criterion}_binary"]].dropna()
        if len(valid) >= 3:
            corr, pval = spearmanr(valid["Binary"], valid[f"{criterion}_binary"])
        else:
            corr, pval = np.nan, np.nan

        # Agreement rate
        agree = (valid["Binary"] == valid[f"{criterion}_binary"]).mean() * 100

        results.append(
            {
                "Criterion": criterion,
                "Correlation with Binary (rho)": corr,
                "p-value": pval,
                "Agreement with Binary (%)": agree,
            }
        )

    return pd.DataFrame(results)


def compute_category_breakdown(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute IRR metrics broken down by question category."""
    results = []

    for cat in sorted(merged["Category"].unique()):
        cat_data = merged[merged["Category"] == cat]
        n = len(cat_data)

        # Compute Krippendorff's alpha for Faithfulness and Completeness
        alpha_faith = compute_krippendorff_alpha(cat_data, "Faithfulness", RATERS)
        alpha_complete = compute_krippendorff_alpha(cat_data, "Completeness", RATERS)

        # 4-way agreement for Faithfulness
        agreement = compute_percentage_agreement(cat_data, "Faithfulness")

        results.append(
            {
                "Category": cat,
                "N": n,
                "Alpha (Faithfulness)": alpha_faith,
                "Alpha (Completeness)": alpha_complete,
                "4-way Agreement (%)": agreement["4-way"]["pct"] * 100,
            }
        )

    return pd.DataFrame(results)


def compute_category_breakdown_all_criteria(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute IRR metrics broken down by question category for ALL criteria."""
    results = []

    for cat in sorted(merged["Category"].unique()):
        cat_data = merged[merged["Category"] == cat]
        n = len(cat_data)

        row = {"Category": cat, "N": n}

        # Compute Krippendorff's alpha for all criteria
        for criterion in CRITERIA:
            alpha = compute_krippendorff_alpha(cat_data, criterion, RATERS)
            row[f"Alpha ({criterion})"] = alpha

        results.append(row)

    return pd.DataFrame(results)


# =============================================================================
# Phase 6: Output Generation (CSV + LaTeX)
# =============================================================================


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


# =============================================================================
# Phase 7: Figure Generation with Mako Palette
# =============================================================================


def setup_style() -> None:
    """Setup matplotlib/seaborn style for academic figures."""
    plt.style.use("seaborn-v0_8-whitegrid")
    sns.set_palette("mako")
    plt.rcParams.update(
        {
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
        }
    )


def plot_krippendorff_heatmap(alpha_df: pd.DataFrame) -> None:
    """Plot Krippendorff's alpha as heatmap."""
    fig, ax = plt.subplots(figsize=(14, 5))

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
    fig, ax = plt.subplots(figsize=(12, 6))

    # Melt for plotting
    melted = agreement_df.melt(
        id_vars=["Criterion"], var_name="Comparison", value_name="Agreement (%)"
    )

    colors = sns.color_palette("mako", n_colors=10)

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
    ax.legend(title="", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=11)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "agreement_bars.png")
    plt.close()
    print(f"  Saved: {FIGURES_DIR / 'agreement_bars.png'}")


def plot_inter_criteria_correlation(corr_matrix: pd.DataFrame, rater: str) -> None:
    """Plot inter-criteria correlation matrix as heatmap.

    Low correlations indicate criteria measure distinct aspects (good).
    High correlations suggest redundancy.
    """
    fig, ax = plt.subplots(figsize=(7, 6))

    # Use diverging colormap centered at 0
    sns.heatmap(
        corr_matrix,
        annot=True,
        fmt=".2f",
        cmap="mako",
        vmin=0,
        vmax=1,
        ax=ax,
        square=True,
        cbar_kws={"label": "Spearman Correlation"},
    )

    display_name = get_display_name(rater)
    ax.set_title(f"Inter-Criteria Correlations ({display_name} ratings)\nLow = distinct measures, High = redundant")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / f"inter_criteria_correlation_{rater}.png")
    plt.close()
    print(f"  Saved: {FIGURES_DIR / f'inter_criteria_correlation_{rater}.png'}")


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


def plot_category_breakdown_all_criteria(cat_df: pd.DataFrame) -> None:
    """Plot category-level breakdown for ALL criteria."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    colors = sns.color_palette("mako", n_colors=5)

    # Alpha by category for all criteria
    alpha_cols = [f"Alpha ({c})" for c in CRITERIA]
    cat_df.plot(
        x="Category",
        y=alpha_cols,
        kind="bar",
        ax=axes[0],
        color=colors,
        width=0.8,
    )
    axes[0].set_title("Krippendorff's Alpha by Category (All Criteria)")
    axes[0].set_ylabel("Alpha")
    axes[0].set_ylim(-0.2, 1.0)  # Allow negative values (can happen with small samples)
    axes[0].axhline(y=0, color='gray', linestyle='--', linewidth=0.8)
    axes[0].legend(CRITERIA, loc='upper right', fontsize=8)
    axes[0].tick_params(axis="x", rotation=0)

    # Sample size by category
    axes[1].bar(cat_df["Category"], cat_df["N"], color=colors[2])
    axes[1].set_title("Sample Size by Category")
    axes[1].set_xlabel("Category")
    axes[1].set_ylabel("N")

    # Add sample size annotations
    for i, (_, row) in enumerate(cat_df.iterrows()):
        axes[1].text(row["Category"], row["N"] + 0.5, str(int(row["N"])),
                     ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "category_breakdown_all_criteria.png")
    plt.close()
    print(f"  Saved: {FIGURES_DIR / 'category_breakdown_all_criteria.png'}")


def plot_confusion_matrix(
    cm: np.ndarray, labels: list, title: str, filename: str
) -> None:
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


# =============================================================================
# Phase 9: Cross-System Discriminative Analysis
# =============================================================================


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

        rows.append(
            {
                "Question ID": question_id,
                "System": system_name,
                "Abstention": params.get("abstention") == "True",
                "Faithfulness": params.get("faithfulness", "Na"),
                "Completeness": params.get("completeness", "Na"),
                "Transparency": params.get("transparency", "Na"),
                "Relevance": params.get("relevance", "Na"),
            }
        )

    return pd.DataFrame(rows)


def load_all_systems() -> pd.DataFrame:
    """Load evaluations from all 3 systems."""
    # Agentic (Cobbie) from CSV
    llm_csv = pd.read_csv(LLM_FILE)
    agentic = llm_csv[
        [
            "Question ID",
            "Abstention",
            "Faithfulness",
            "Completeness",
            "Transparency",
            "Relevance",
        ]
    ].copy()
    agentic["System"] = "Agentic"

    # Static (Baseline) and Lightweight (Gemini-Flash) from MLflow
    static = extract_mlflow_evaluations(BASELINE_RUN_ID, "Static")
    lightweight = extract_mlflow_evaluations(GEMINI_RUN_ID, "Lightweight")

    # Combine
    all_systems = pd.concat([agentic, static, lightweight], ignore_index=True)
    return all_systems


def compute_criterion_entropy(df: pd.DataFrame, criterion: str) -> float:
    """Compute normalized entropy for a criterion (higher = more discriminative)."""
    counts = df[criterion].value_counts(normalize=True)
    n_categories = len(counts)
    if n_categories <= 1:
        return 0.0

    # Normalized entropy (0 = all same, 1 = uniform distribution)
    h = entropy(counts, base=n_categories)
    return float(h)


def compute_discriminative_power(all_systems: pd.DataFrame) -> pd.DataFrame:
    """Compute discriminative power metrics for each criterion across systems."""
    results = []

    for criterion in CRITERIA:
        row: dict[str, object] = {"Criterion": criterion}

        for system in SYSTEMS:
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
                for s in SYSTEMS
            ]
        else:
            yes_rates = [
                all_systems[all_systems["System"] == s][criterion].mean()
                for s in SYSTEMS
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

        for system in SYSTEMS:
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

            results.append(
                {
                    "Criterion": criterion,
                    "System": system,
                    "Yes%": yes_rate,
                    "No%": no_rate,
                    "Effect": effect,
                }
            )

    return pd.DataFrame(results)


def plot_cross_system_comparison(all_systems: pd.DataFrame) -> None:
    """Plot criterion distributions across systems."""
    fig, axes = plt.subplots(2, 3, figsize=(14, 9))
    axes = axes.flatten()

    colors = sns.color_palette("mako", n_colors=3)
    system_order = SYSTEMS

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
                plot_data.append(
                    {"System": system, "Value": "False", "Rate": false_rate}
                )
            else:
                # Yes/No/Na
                for val, label in [("Yes", "Yes"), ("No", "No"), ("Na", "N/A")]:
                    rate = (sys_data[criterion] == val).mean() * 100
                    plot_data.append({"System": system, "Value": label, "Rate": rate})

        plot_df = pd.DataFrame(plot_data)

        sns.barplot(
            data=plot_df,
            x="System",
            y="Rate",
            hue="Value",
            palette=colors[: len(plot_df["Value"].unique())],
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


def rename_csv_columns_for_systems(csv_path: Path) -> pd.DataFrame:
    """Load CSV and rename columns to use new system names."""
    old_to_new = {
        "Cobbie": "Agentic",
        "Baseline": "Static",
        "Gemini-Flash": "Lightweight",
    }

    df = pd.read_csv(csv_path)

    # Rename columns containing old system names
    new_columns = {}
    for col in df.columns:
        new_col = col
        for old, new in old_to_new.items():
            new_col = new_col.replace(old, new)
        if new_col != col:
            new_columns[col] = new_col

    if new_columns:
        df = df.rename(columns=new_columns)

    return df


def regenerate_cross_system_figures_from_csv(disc_csv_path: Path, ceiling_csv_path: Path) -> None:
    """Regenerate cross-system figures using existing CSV data with new names."""
    print("   Regenerating cross-system figures from CSV data...")

    # Load and rename discriminative power CSV
    disc_df = rename_csv_columns_for_systems(disc_csv_path)
    disc_df.to_csv(OUTPUT_DIR / "discriminative_power.csv", index=False)
    print(f"   Updated: {OUTPUT_DIR / 'discriminative_power.csv'}")

    # Load and rename ceiling/floor effects CSV
    ceiling_df = rename_csv_columns_for_systems(ceiling_csv_path)
    # Also rename System column values
    system_map = {"cobbie": "Agentic", "Cobbie": "Agentic",
                  "baseline": "Static", "Baseline": "Static",
                  "gemini-flash": "Lightweight", "Gemini-Flash": "Lightweight"}
    if "System" in ceiling_df.columns:
        ceiling_df["System"] = ceiling_df["System"].replace(system_map)
    ceiling_df.to_csv(OUTPUT_DIR / "ceiling_floor_effects.csv", index=False)
    print(f"   Updated: {OUTPUT_DIR / 'ceiling_floor_effects.csv'}")

    # Plot discriminative power figure
    plot_discriminative_power(disc_df)

    # For cross_system_comparison figure, we need raw data which isn't in CSV
    # So we skip that figure when regenerating from CSV
    print("   Note: cross_system_comparison.png requires raw data; skipping regeneration.")


# =============================================================================
# Phase 8: Main Function and CLI
# =============================================================================


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Compute EC3 Paper IRR Statistics")
    parser.add_argument(
        "--skip-figures",
        action="store_true",
        help="Skip figure generation",
    )
    parser.add_argument(
        "--skip-cross-system",
        action="store_true",
        help="Skip cross-system analysis (requires MLflow)",
    )
    parser.add_argument(
        "--regenerate-cross-system-from-csv",
        type=str,
        nargs=2,
        metavar=("DISC_CSV", "CEILING_CSV"),
        help="Regenerate cross-system figures from existing CSV files (skips MLflow)",
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
    h1, h2, llm, gemini, consolidated = load_and_clean_data()
    valid_ids = filter_valid_questions(h1, h2, llm, gemini, consolidated)
    merged = merge_ratings(h1, h2, llm, gemini, valid_ids)
    print(f"   Valid questions: {len(merged)}")

    # Augment with consolidated human judgment
    merged, n_agreed, n_disagreed = augment_with_consolidated(
        merged, h1, h2, consolidated, valid_ids,
    )
    discussed_ids = set(consolidated["Question ID"].unique()) & valid_ids
    print(f"   Discussed questions: {len(discussed_ids)}")
    print(f"   Originally agreed: {len(valid_ids) - len(discussed_ids)}")
    print(f"   Fully agreed (post-discussion): {n_agreed}")
    print(f"   Still disagreed: {n_disagreed}")

    # Krippendorff's alpha
    print("\n2. Computing Krippendorff's alpha...")
    alpha_df = compute_all_krippendorff(merged)
    save_results(
        alpha_df,
        "krippendorff_alpha",
        "Krippendorff's Alpha for Inter-Rater Reliability",
        "tab:krippendorff",
    )

    # Percentage agreement
    print("\n3. Computing percentage agreement...")
    agreement_df = compute_all_agreements(merged)
    save_results(
        agreement_df,
        "percentage_agreement",
        "Percentage Agreement by Criterion",
        "tab:agreement",
    )

    # Spearman correlations
    print("\n4. Computing Spearman correlations...")
    spearman_df = compute_spearman_correlations(merged)
    save_results(
        spearman_df,
        "spearman_correlations",
        "Spearman Rank Correlations Between Raters",
        "tab:spearman",
    )

    # Category breakdown
    print("\n5. Computing category breakdown...")
    cat_df = compute_category_breakdown(merged)
    save_results(
        cat_df,
        "category_breakdown",
        "IRR Metrics by Question Category",
        "tab:category",
    )

    # Category breakdown with ALL criteria
    cat_df_all = compute_category_breakdown_all_criteria(merged)
    save_results(
        cat_df_all,
        "category_breakdown_all_criteria",
        "IRR Metrics by Question Category (All Criteria)",
        "tab:category_all",
    )

    # Inter-criteria correlations
    print("\n6. Computing inter-criteria correlations...")
    for rater in RATERS:
        inter_corr = compute_inter_criteria_correlations(merged, rater)
        # Save correlation matrix with index (criteria names)
        inter_corr.to_csv(OUTPUT_DIR / f"inter_criteria_correlation_{rater}.csv")
        print(f"  Saved: {OUTPUT_DIR / f'inter_criteria_correlation_{rater}.csv'}")

    # Criteria vs Binary classification
    print("\n7. Computing criteria vs binary classification...")
    binary_df = compute_criteria_vs_binary(h1, h2, llm, gemini, valid_ids)
    save_results(
        binary_df,
        "criteria_vs_binary",
        "Granular Criteria vs Binary Classification",
        "tab:binary",
    )

    # Figures
    if not args.skip_figures:
        print("\n8. Generating figures...")
        plot_krippendorff_heatmap(alpha_df)
        plot_agreement_bars(agreement_df)
        plot_category_breakdown(cat_df)
        plot_category_breakdown_all_criteria(cat_df_all)

        # Inter-criteria correlation heatmaps
        for rater in RATERS:
            inter_corr = compute_inter_criteria_correlations(merged, rater)
            plot_inter_criteria_correlation(inter_corr, rater)

        # Confusion matrices for Faithfulness (most important criterion)
        cms = compute_confusion_matrices(merged, "Faithfulness")
        labels = ["Yes", "No", "Na"]
        for pair, cm in cms.items():
            pair_display = get_pair_display_name(pair)
            plot_confusion_matrix(
                cm,
                labels,
                f"Faithfulness: {pair_display}",
                f"confusion_faithfulness_{pair.replace('-', '_')}.png",
            )
            print(
                f"  Saved: {FIGURES_DIR / f'confusion_faithfulness_{pair.replace('-', '_')}.png'}"
            )

    # Cross-system analysis
    if args.regenerate_cross_system_from_csv:
        print("\n9. Regenerating cross-system figures from CSV...")
        disc_csv = Path(args.regenerate_cross_system_from_csv[0])
        ceiling_csv = Path(args.regenerate_cross_system_from_csv[1])
        regenerate_cross_system_figures_from_csv(disc_csv, ceiling_csv)
    elif not args.skip_cross_system:
        print("\n9. Cross-system discriminative analysis...")
        all_systems = load_all_systems()
        print(f"   Loaded {len(all_systems)} evaluations across 3 systems")

        disc_df = compute_discriminative_power(all_systems)
        save_results(
            disc_df,
            "discriminative_power",
            "Criterion Discriminative Power Across Systems",
            "tab:discriminative",
        )

        ceiling_df = identify_ceiling_floor_effects(all_systems)
        save_results(
            ceiling_df,
            "ceiling_floor_effects",
            "Ceiling and Floor Effects by Criterion and System",
            "tab:ceiling",
        )

        if not args.skip_figures:
            plot_cross_system_comparison(all_systems)
            plot_discriminative_power(disc_df)

    print("\n" + "=" * 60)
    print("Done! Results saved to:", OUTPUT_DIR)
    print("=" * 60)


if __name__ == "__main__":
    main()
