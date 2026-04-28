#!/usr/bin/env python3
"""
Compute IRR between Consolidated Human Judgment and LLM Judges.

After H1 and H2 discussed all disagreements, this script:
1. Builds the full post-discussion dataset (original agreements + discussed disagreements)
2. Computes H1 vs H2 alpha after discussion (showing improvement)
3. For questions where humans now agree: computes consolidated vs LLM₁ and LLM₂
4. For questions where humans still disagree: reports each human vs LLM separately
5. Compares everything against pre-discussion baselines

Usage:
    uv run scripts/compute_consolidated_irr.py
"""

from pathlib import Path

import krippendorff
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import spearmanr

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
EVAL_DIR = Path("src/db/eval")
H1_FILE = EVAL_DIR / "EC3-2026 - H1 (H1) 2026-01-20_21-07.csv"
H2_FILE = EVAL_DIR / "EC3-2026 - H2 (H2) 2026-01-20_21-07.csv"
LLM_FILE = EVAL_DIR / "EC3-2026 - LLM_Judge (LLM_Judge) 2026-01-20_21-08.csv"
GEMINI_FILE = EVAL_DIR / "EC3-2026 - Gemini_Judge (Gemini_Judge) 2026-01-21_16-00.csv"
CONSOLIDATED_FILE = EVAL_DIR / "EC3-2026 - human-human final agreement.csv"

OUTPUT_DIR = Path("outputs/ec3")
FIGURES_DIR = OUTPUT_DIR / "figures"

CRITERIA = ["Abstention", "Faithfulness", "Completeness", "Transparency", "Relevance"]

DISPLAY_NAMES = {
    "h1": "H1",
    "h2": "H2",
    "consolidated": "H_cons",
    "llm": "LLM₁",
    "gemini": "LLM₂",
}


def display(name: str) -> str:
    return DISPLAY_NAMES.get(name, name)


# ---------------------------------------------------------------------------
# Encoding (reused from main script)
# ---------------------------------------------------------------------------

def encode_criterion(value: object, criterion: str) -> float:
    if pd.isna(value):
        return np.nan
    if criterion == "Abstention":
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        return 1.0 if str(value).strip().lower() == "true" else 0.0
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


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_original_ratings() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load the 4 original rating files (pre-discussion)."""
    h1 = pd.read_csv(H1_FILE)
    h2 = pd.read_csv(H2_FILE)
    llm = pd.read_csv(LLM_FILE)
    gemini = pd.read_csv(GEMINI_FILE)

    h2 = h2.dropna(subset=["Question ID"])

    for df in [h1, h2, llm, gemini]:
        df["Question ID"] = df["Question ID"].astype(int)
        df["Abstention"] = df["Abstention"].apply(normalise_abstention)

    return h1, h2, llm, gemini


def load_consolidated() -> pd.DataFrame:
    """Load the post-discussion CSV and return it cleaned."""
    df = pd.read_csv(CONSOLIDATED_FILE)
    # Drop empty rows
    df = df.dropna(subset=["Question ID"])
    df["Question ID"] = df["Question ID"].astype(int)
    df["Abstention"] = df["Abstention"].apply(normalise_abstention)
    return df


def filter_valid_ids(
    h1: pd.DataFrame,
    h2: pd.DataFrame,
    llm: pd.DataFrame,
    gemini: pd.DataFrame,
) -> set[int]:
    """Return question IDs valid across all 4 original raters."""
    h1_valid = h1[(h1["Error"] == 0) & (h1["UPDATED"] != "x")]
    h2_valid = h2[
        (h2["Error"] == 0)
        & (h2["UPDATED"] != "x")
        & h2["Abstention"].notna()
    ]
    return (
        set(h1_valid["Question ID"])
        & set(h2_valid["Question ID"])
        & set(llm["Question ID"])
        & set(gemini["Question ID"])
    )


# ---------------------------------------------------------------------------
# Build post-discussion dataset
# ---------------------------------------------------------------------------

def build_post_discussion_dataset(
    h1: pd.DataFrame,
    h2: pd.DataFrame,
    consolidated: pd.DataFrame,
    valid_ids: set[int],
) -> tuple[pd.DataFrame, pd.DataFrame, set[int], set[int]]:
    """Build the full post-discussion dataset.

    Returns:
        merged: DataFrame with columns {rater}_{criterion} for h1_post, h2_post
        consolidated_df: DataFrame with consolidated_{criterion} (only agreed questions)
        agreed_ids: question IDs where humans agree on ALL criteria after discussion
        disagreed_ids: question IDs where at least one criterion still differs
    """
    # Questions that were discussed (in consolidation CSV)
    discussed_ids = set(consolidated["Question ID"].unique()) & valid_ids

    # Questions where they originally agreed (not discussed)
    originally_agreed_ids = valid_ids - discussed_ids

    # --- Build post-discussion ratings ---
    rows = []
    agreed_ids: set[int] = set()
    disagreed_ids: set[int] = set()

    # 1) Originally agreed questions: use original ratings directly
    for qid in originally_agreed_ids:
        s_row = h1[h1["Question ID"] == qid].iloc[0]
        st_row = h2[h2["Question ID"] == qid].iloc[0]

        row: dict[str, object] = {
            "Question ID": qid,
            "Category": s_row.get("Category", np.nan),
        }

        all_agree = True
        for c in CRITERIA:
            sv = s_row[c]
            stv = st_row[c]
            row[f"h1_post_{c}"] = sv
            row[f"h2_post_{c}"] = stv

            # They originally agreed, so set consolidated
            row[f"consolidated_{c}"] = sv

            # Double-check (they should agree, but be safe)
            if encode_criterion(sv, c) != encode_criterion(stv, c):
                all_agree = False

        if all_agree:
            agreed_ids.add(qid)
        else:
            # Edge case: should not happen for "originally agreed" questions,
            # but if it does treat as disagreement
            disagreed_ids.add(qid)

        rows.append(row)

    # 2) Discussed questions: use post-discussion ratings from consolidation CSV
    for qid in discussed_ids:
        q_rows = consolidated[consolidated["Question ID"] == qid]
        if len(q_rows) < 2:
            continue  # need both evaluators

        h1_post = q_rows[q_rows["Evaluator"].str.lower().str.strip() == "h1"]
        h2_post = q_rows[q_rows["Evaluator"].str.lower().str.strip() == "h2"]

        if h1_post.empty or h2_post.empty:
            continue

        s_row = h1_post.iloc[0]
        st_row = h2_post.iloc[0]

        row = {
            "Question ID": qid,
            "Category": s_row.get("Category", np.nan),
        }

        all_agree = True
        for c in CRITERIA:
            sv = s_row[c]
            stv = st_row[c]
            row[f"h1_post_{c}"] = sv
            row[f"h2_post_{c}"] = stv

            if encode_criterion(sv, c) == encode_criterion(stv, c):
                row[f"consolidated_{c}"] = sv
            else:
                row[f"consolidated_{c}"] = np.nan  # no consensus
                all_agree = False

        if all_agree:
            agreed_ids.add(qid)
        else:
            disagreed_ids.add(qid)

        rows.append(row)

    merged = pd.DataFrame(rows).sort_values("Question ID").reset_index(drop=True)

    # Consolidated only for fully agreed questions
    consolidated_df = merged[merged["Question ID"].isin(agreed_ids)].copy()

    return merged, consolidated_df, agreed_ids, disagreed_ids


# ---------------------------------------------------------------------------
# IRR computation helpers
# ---------------------------------------------------------------------------

def compute_alpha(
    df: pd.DataFrame,
    criterion: str,
    col_names: list[str],
) -> float:
    """Compute Krippendorff's alpha for given columns."""
    reliability_data = []
    for col in col_names:
        values = df[col].apply(lambda x: encode_criterion(x, criterion))
        reliability_data.append(values.to_numpy())

    level = "nominal" if criterion == "Abstention" else "ordinal"
    try:
        alpha = krippendorff.alpha(reliability_data, level_of_measurement=level)
        return alpha if not np.isnan(alpha) else np.nan
    except Exception:
        return np.nan


def compute_pct_agreement(
    df: pd.DataFrame,
    criterion: str,
    col1: str,
    col2: str,
) -> float:
    """Compute percentage agreement between two columns."""
    valid = df[[col1, col2]].dropna()
    if len(valid) == 0:
        return 0.0
    enc1 = valid[col1].apply(lambda x: encode_criterion(x, criterion))
    enc2 = valid[col2].apply(lambda x: encode_criterion(x, criterion))
    return float((enc1 == enc2).mean() * 100)


def compute_spearman(
    df: pd.DataFrame,
    criterion: str,
    col1: str,
    col2: str,
) -> tuple[float, float]:
    """Compute Spearman correlation between two columns."""
    encoded = pd.DataFrame()
    encoded["a"] = df[col1].apply(lambda x: encode_criterion(x, criterion))
    encoded["b"] = df[col2].apply(lambda x: encode_criterion(x, criterion))
    valid = encoded.dropna()
    if len(valid) < 3:
        return np.nan, np.nan
    rho, p = spearmanr(valid["a"], valid["b"])
    return float(rho), float(p)


# ---------------------------------------------------------------------------
# Main analyses
# ---------------------------------------------------------------------------

def compute_post_discussion_h1h2_alpha(
    merged: pd.DataFrame,
) -> pd.DataFrame:
    """H1 vs H2 after discussion (all questions, including still-disagreed)."""
    results = []
    for c in CRITERIA:
        alpha = compute_alpha(merged, c, [f"h1_post_{c}", f"h2_post_{c}"])
        pct = compute_pct_agreement(merged, c, f"h1_post_{c}", f"h2_post_{c}")
        rho, p = compute_spearman(merged, c, f"h1_post_{c}", f"h2_post_{c}")
        results.append({
            "Criterion": c,
            "Alpha (H1-H2 post)": alpha,
            "Agreement (H1-H2 post) (%)": pct,
            "Spearman rho (H1-H2 post)": rho,
            "p-value": p,
        })
    return pd.DataFrame(results)


def compute_consolidated_vs_llm(
    consolidated_df: pd.DataFrame,
    llm: pd.DataFrame,
    gemini: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Consolidated human vs each LLM (only questions with full consensus)."""
    # Merge with LLM data
    qids = set(consolidated_df["Question ID"])
    llm_sub = llm[llm["Question ID"].isin(qids)].copy()
    gem_sub = gemini[gemini["Question ID"].isin(qids)].copy()

    # Add LLM columns to consolidated_df
    df = consolidated_df.copy()
    for c in CRITERIA:
        llm_map = llm_sub.set_index("Question ID")[c].to_dict()
        gem_map = gem_sub.set_index("Question ID")[c].to_dict()
        df[f"llm_{c}"] = df["Question ID"].map(llm_map)
        df[f"gemini_{c}"] = df["Question ID"].map(gem_map)
        # Normalise LLM abstention
        if c == "Abstention":
            df[f"llm_{c}"] = df[f"llm_{c}"].apply(normalise_abstention)
            df[f"gemini_{c}"] = df[f"gemini_{c}"].apply(normalise_abstention)

    comparisons = [
        ("consolidated", "llm", f"{display('consolidated')}-{display('llm')}"),
        ("consolidated", "gemini", f"{display('consolidated')}-{display('gemini')}"),
        ("llm", "gemini", f"{display('llm')}-{display('gemini')}"),
    ]

    results = []
    for c in CRITERIA:
        row: dict[str, object] = {"Criterion": c}
        for r1_prefix, r2_prefix, label in comparisons:
            col1 = f"{r1_prefix}_{c}"
            col2 = f"{r2_prefix}_{c}"
            alpha = compute_alpha(df, c, [col1, col2])
            pct = compute_pct_agreement(df, c, col1, col2)
            rho, p = compute_spearman(df, c, col1, col2)
            row[f"Alpha ({label})"] = alpha
            row[f"Agree ({label}) (%)"] = pct
            row[f"Spearman ({label})"] = rho
        results.append(row)

    return pd.DataFrame(results), df


def compute_disagreed_vs_llm(
    merged: pd.DataFrame,
    disagreed_ids: set[int],
    llm: pd.DataFrame,
    gemini: pd.DataFrame,
) -> pd.DataFrame:
    """For questions where humans still disagree: each human vs LLM."""
    df = merged[merged["Question ID"].isin(disagreed_ids)].copy()
    if df.empty:
        return pd.DataFrame()

    llm_sub = llm[llm["Question ID"].isin(disagreed_ids)].copy()
    gem_sub = gemini[gemini["Question ID"].isin(disagreed_ids)].copy()

    for c in CRITERIA:
        llm_map = llm_sub.set_index("Question ID")[c].to_dict()
        gem_map = gem_sub.set_index("Question ID")[c].to_dict()
        df[f"llm_{c}"] = df["Question ID"].map(llm_map)
        df[f"gemini_{c}"] = df["Question ID"].map(gem_map)
        if c == "Abstention":
            df[f"llm_{c}"] = df[f"llm_{c}"].apply(normalise_abstention)
            df[f"gemini_{c}"] = df[f"gemini_{c}"].apply(normalise_abstention)

    comparisons = [
        ("h1_post", "llm", f"{display('h1')}_post-{display('llm')}"),
        ("h1_post", "gemini", f"{display('h1')}_post-{display('gemini')}"),
        ("h2_post", "llm", f"{display('h2')}_post-{display('llm')}"),
        ("h2_post", "gemini", f"{display('h2')}_post-{display('gemini')}"),
    ]

    results = []
    for c in CRITERIA:
        row: dict[str, object] = {"Criterion": c}
        for r1_prefix, r2_prefix, label in comparisons:
            col1 = f"{r1_prefix}_{c}"
            col2 = f"{r2_prefix}_{c}"
            pct = compute_pct_agreement(df, c, col1, col2)
            row[f"Agree ({label}) (%)"] = pct
        results.append(row)

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Pre-discussion baseline (recomputed for comparison)
# ---------------------------------------------------------------------------

def compute_pre_discussion_baseline(
    h1: pd.DataFrame,
    h2: pd.DataFrame,
    llm: pd.DataFrame,
    gemini: pd.DataFrame,
    valid_ids: set[int],
) -> pd.DataFrame:
    """Recompute H1-H2 pre-discussion alpha for direct comparison."""
    s = h1[h1["Question ID"].isin(valid_ids)].set_index("Question ID")
    st = h2[h2["Question ID"].isin(valid_ids)].set_index("Question ID")
    ll = llm[llm["Question ID"].isin(valid_ids)].set_index("Question ID")
    gm = gemini[gemini["Question ID"].isin(valid_ids)].set_index("Question ID")

    # Align indices
    common = s.index.intersection(st.index).intersection(ll.index).intersection(gm.index)
    s = s.loc[common]
    st = st.loc[common]
    ll = ll.loc[common]
    gm = gm.loc[common]

    results = []
    for c in CRITERIA:
        # H1-H2 pre
        data_h1h2 = [
            s[c].apply(lambda x: encode_criterion(x, c)).to_numpy(),
            st[c].apply(lambda x: encode_criterion(x, c)).to_numpy(),
        ]
        level = "nominal" if c == "Abstention" else "ordinal"
        try:
            alpha_h1h2 = krippendorff.alpha(data_h1h2, level_of_measurement=level)
        except Exception:
            alpha_h1h2 = np.nan

        # H1-LLM1 pre
        data_h1l1 = [
            s[c].apply(lambda x: encode_criterion(x, c)).to_numpy(),
            ll[c].apply(lambda x: encode_criterion(x, c)).to_numpy(),
        ]
        try:
            alpha_h1l1 = krippendorff.alpha(data_h1l1, level_of_measurement=level)
        except Exception:
            alpha_h1l1 = np.nan

        # H2-LLM1 pre
        data_h2l1 = [
            st[c].apply(lambda x: encode_criterion(x, c)).to_numpy(),
            ll[c].apply(lambda x: encode_criterion(x, c)).to_numpy(),
        ]
        try:
            alpha_h2l1 = krippendorff.alpha(data_h2l1, level_of_measurement=level)
        except Exception:
            alpha_h2l1 = np.nan

        # H1-LLM2 pre
        data_h1l2 = [
            s[c].apply(lambda x: encode_criterion(x, c)).to_numpy(),
            gm[c].apply(lambda x: encode_criterion(x, c)).to_numpy(),
        ]
        try:
            alpha_h1l2 = krippendorff.alpha(data_h1l2, level_of_measurement=level)
        except Exception:
            alpha_h1l2 = np.nan

        # H2-LLM2 pre
        data_h2l2 = [
            st[c].apply(lambda x: encode_criterion(x, c)).to_numpy(),
            gm[c].apply(lambda x: encode_criterion(x, c)).to_numpy(),
        ]
        try:
            alpha_h2l2 = krippendorff.alpha(data_h2l2, level_of_measurement=level)
        except Exception:
            alpha_h2l2 = np.nan

        # Pct agreement H1-H2 pre
        enc_s = s[c].apply(lambda x: encode_criterion(x, c))
        enc_st = st[c].apply(lambda x: encode_criterion(x, c))
        valid_mask = enc_s.notna() & enc_st.notna()
        pct_h1h2 = float((enc_s[valid_mask] == enc_st[valid_mask]).mean() * 100)

        results.append({
            "Criterion": c,
            f"Alpha ({display('h1')}-{display('h2')} pre)": alpha_h1h2,
            f"Alpha ({display('h1')}-{display('llm')} pre)": alpha_h1l1,
            f"Alpha ({display('h2')}-{display('llm')} pre)": alpha_h2l1,
            f"Alpha ({display('h1')}-{display('gemini')} pre)": alpha_h1l2,
            f"Alpha ({display('h2')}-{display('gemini')} pre)": alpha_h2l2,
            f"Agree ({display('h1')}-{display('h2')} pre) (%)": pct_h1h2,
        })

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Summary comparison table
# ---------------------------------------------------------------------------

def build_comparison_table(
    pre_df: pd.DataFrame,
    post_h1h2_df: pd.DataFrame,
    cons_vs_llm_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build a side-by-side comparison table."""
    rows = []
    for c in CRITERIA:
        pre_row = pre_df[pre_df["Criterion"] == c].iloc[0]
        post_row = post_h1h2_df[post_h1h2_df["Criterion"] == c].iloc[0]
        cons_row = cons_vs_llm_df[cons_vs_llm_df["Criterion"] == c].iloc[0]

        rows.append({
            "Criterion": c,
            # Pre-discussion
            "α H1-H2 (pre)": pre_row[f"Alpha ({display('h1')}-{display('h2')} pre)"],
            "α H1-LLM₁ (pre)": pre_row[f"Alpha ({display('h1')}-{display('llm')} pre)"],
            "α H2-LLM₁ (pre)": pre_row[f"Alpha ({display('h2')}-{display('llm')} pre)"],
            "α H1-LLM₂ (pre)": pre_row[f"Alpha ({display('h1')}-{display('gemini')} pre)"],
            "α H2-LLM₂ (pre)": pre_row[f"Alpha ({display('h2')}-{display('gemini')} pre)"],
            # Post-discussion
            "α H1-H2 (post)": post_row["Alpha (H1-H2 post)"],
            # Consolidated vs LLM
            "α H_cons-LLM₁": cons_row[f"Alpha ({display('consolidated')}-{display('llm')})"],
            "α H_cons-LLM₂": cons_row[f"Alpha ({display('consolidated')}-{display('gemini')})"],
            "α LLM₁-LLM₂": cons_row[f"Alpha ({display('llm')}-{display('gemini')})"],
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Figure generation
# ---------------------------------------------------------------------------

def setup_style() -> None:
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


def plot_comparison_heatmap(comparison_df: pd.DataFrame) -> None:
    """Heatmap comparing alpha values across all comparisons."""
    fig, ax = plt.subplots(figsize=(12, 5))

    data = comparison_df.set_index("Criterion")
    sns.heatmap(
        data.astype(float),
        annot=True,
        fmt=".3f",
        cmap="mako",
        vmin=0,
        vmax=1,
        ax=ax,
        cbar_kws={"label": "Krippendorff's α"},
    )

    ax.set_title("IRR Comparison: Pre-Discussion vs Post-Discussion vs Consolidated-LLM")
    ax.set_ylabel("Criterion")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "comparison_heatmap.png")
    plt.savefig(FIGURES_DIR / "comparison_heatmap.pdf")
    plt.close()
    print(f"  Saved: {FIGURES_DIR / 'comparison_heatmap.png'}")


def plot_alpha_bar_comparison(comparison_df: pd.DataFrame) -> None:
    """Grouped bar chart: pre H1-H2, post H1-H2, consolidated-LLM₁, consolidated-LLM₂."""
    cols_to_plot = [
        "α H1-H2 (pre)",
        "α H1-H2 (post)",
        "α H_cons-LLM₁",
        "α H_cons-LLM₂",
        "α LLM₁-LLM₂",
    ]

    melted = comparison_df.melt(
        id_vars=["Criterion"],
        value_vars=cols_to_plot,
        var_name="Comparison",
        value_name="Alpha",
    )

    fig, ax = plt.subplots(figsize=(12, 6))
    colors = sns.color_palette("mako", n_colors=len(cols_to_plot))

    sns.barplot(
        data=melted,
        x="Criterion",
        y="Alpha",
        hue="Comparison",
        palette=colors,
        ax=ax,
    )

    ax.set_title("Krippendorff's α: Pre-Discussion → Post-Discussion → Consolidated vs LLM")
    ax.set_ylim(0, 1)
    ax.axhline(y=0.667, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax.text(4.5, 0.675, "Good (0.667)", fontsize=8, color="gray", ha="right")
    ax.legend(title="", bbox_to_anchor=(1.02, 1), loc="upper left")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "alpha_bar_comparison.png")
    plt.savefig(FIGURES_DIR / "alpha_bar_comparison.pdf")
    plt.close()
    print(f"  Saved: {FIGURES_DIR / 'alpha_bar_comparison.png'}")


def plot_agreement_bar_comparison(
    pre_df: pd.DataFrame,
    post_h1h2_df: pd.DataFrame,
    cons_vs_llm_df: pd.DataFrame,
) -> None:
    """Grouped bar chart for percentage agreement."""
    rows = []
    for c in CRITERIA:
        pre_row = pre_df[pre_df["Criterion"] == c].iloc[0]
        post_row = post_h1h2_df[post_h1h2_df["Criterion"] == c].iloc[0]
        cons_row = cons_vs_llm_df[cons_vs_llm_df["Criterion"] == c].iloc[0]

        rows.append({
            "Criterion": c,
            "H1-H2 (pre)": pre_row[f"Agree ({display('h1')}-{display('h2')} pre) (%)"],
            "H1-H2 (post)": post_row["Agreement (H1-H2 post) (%)"],
            "H_cons-LLM₁": cons_row[f"Agree ({display('consolidated')}-{display('llm')}) (%)"],
            "H_cons-LLM₂": cons_row[f"Agree ({display('consolidated')}-{display('gemini')}) (%)"],
        })

    agree_df = pd.DataFrame(rows)
    cols_to_plot = ["H1-H2 (pre)", "H1-H2 (post)", "H_cons-LLM₁", "H_cons-LLM₂"]

    melted = agree_df.melt(
        id_vars=["Criterion"],
        value_vars=cols_to_plot,
        var_name="Comparison",
        value_name="Agreement (%)",
    )

    fig, ax = plt.subplots(figsize=(12, 6))
    colors = sns.color_palette("mako", n_colors=len(cols_to_plot))

    sns.barplot(
        data=melted,
        x="Criterion",
        y="Agreement (%)",
        hue="Comparison",
        palette=colors,
        ax=ax,
    )

    ax.set_title("Percentage Agreement: Pre → Post → Consolidated vs LLM")
    ax.set_ylim(0, 100)
    ax.legend(title="", bbox_to_anchor=(1.02, 1), loc="upper left")

    plt.tight_layout()
    plt.savefig(FIGURES_DIR / "agreement_bar_comparison.png")
    plt.savefig(FIGURES_DIR / "agreement_bar_comparison.pdf")
    plt.close()
    print(f"  Saved: {FIGURES_DIR / 'agreement_bar_comparison.png'}")


# ---------------------------------------------------------------------------
# LaTeX helpers
# ---------------------------------------------------------------------------

def df_to_latex(df: pd.DataFrame, caption: str, label: str) -> str:
    formatted = df.copy()
    for col in formatted.columns:
        if formatted[col].dtype in [np.float64, float]:
            formatted[col] = formatted[col].apply(
                lambda x: f"{x:.3f}" if pd.notna(x) else "N/A"
            )
    latex = formatted.to_latex(index=False, escape=True)
    return f"""\\begin{{table}}[htbp]
\\centering
\\caption{{{caption}}}
\\label{{{label}}}
{latex}
\\end{{table}}
"""


def save_results(df: pd.DataFrame, name: str, caption: str, label: str) -> None:
    csv_path = OUTPUT_DIR / f"{name}.csv"
    tex_path = OUTPUT_DIR / f"{name}.tex"

    df.to_csv(csv_path, index=False)
    latex = df_to_latex(df, caption, label)
    with open(tex_path, "w") as f:
        f.write(latex)

    print(f"  Saved: {csv_path}")
    print(f"  Saved: {tex_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("Consolidated Human Judgment vs LLM Judges — IRR Analysis")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    setup_style()

    # 1. Load data
    print("\n1. Loading data...")
    h1, h2, llm, gemini = load_original_ratings()
    consolidated = load_consolidated()
    valid_ids = filter_valid_ids(h1, h2, llm, gemini)
    print(f"   Valid question IDs (4-way): {len(valid_ids)}")

    discussed_ids = set(consolidated["Question ID"].unique()) & valid_ids
    print(f"   Questions discussed: {len(discussed_ids)}")
    print(f"   Questions originally agreed: {len(valid_ids - discussed_ids)}")

    # 2. Build post-discussion dataset
    print("\n2. Building post-discussion dataset...")
    merged, consolidated_df, agreed_ids, disagreed_ids = build_post_discussion_dataset(
        h1, h2, consolidated, valid_ids,
    )
    print(f"   Total questions: {len(merged)}")
    print(f"   Fully agreed (post-discussion): {len(agreed_ids)}")
    print(f"   Still disagreed: {len(disagreed_ids)}")

    # 3. Pre-discussion baseline
    print("\n3. Computing pre-discussion baseline...")
    pre_df = compute_pre_discussion_baseline(h1, h2, llm, gemini, valid_ids)
    save_results(
        pre_df,
        "pre_discussion_baseline",
        "Pre-Discussion IRR Baseline",
        "tab:pre_baseline",
    )

    # 4. Post-discussion H1-H2
    print("\n4. Computing post-discussion H1 vs H2...")
    post_h1h2_df = compute_post_discussion_h1h2_alpha(merged)
    save_results(
        post_h1h2_df,
        "post_discussion_h1h2",
        "Post-Discussion H1-H2 Agreement",
        "tab:post_h1h2",
    )

    # 5. Consolidated vs LLM
    print("\n5. Computing consolidated human vs LLM judges...")
    cons_vs_llm_df, cons_merged = compute_consolidated_vs_llm(
        consolidated_df, llm, gemini,
    )
    save_results(
        cons_vs_llm_df,
        "consolidated_vs_llm",
        "Consolidated Human vs LLM Judges",
        "tab:cons_llm",
    )

    # 6. Still-disagreed questions: each human vs LLM
    print("\n6. Computing disagreed questions: each human vs LLM...")
    if disagreed_ids:
        disagree_df = compute_disagreed_vs_llm(merged, disagreed_ids, llm, gemini)
        save_results(
            disagree_df,
            "disagreed_questions_vs_llm",
            "Still-Disagreed Questions: Individual Human vs LLM",
            "tab:disagree_llm",
        )
    else:
        print("   No disagreed questions — skipping.")

    # 7. Comparison table
    print("\n7. Building comparison table...")
    comparison_df = build_comparison_table(pre_df, post_h1h2_df, cons_vs_llm_df)
    save_results(
        comparison_df,
        "comparison_table",
        "IRR Comparison: Pre vs Post vs Consolidated-LLM",
        "tab:comparison",
    )

    # 8. Figures
    print("\n8. Generating figures...")
    plot_comparison_heatmap(comparison_df)
    plot_alpha_bar_comparison(comparison_df)
    plot_agreement_bar_comparison(pre_df, post_h1h2_df, cons_vs_llm_df)

    # 9. Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nTotal questions analysed: {len(merged)}")
    print(f"  Fully agreed after discussion: {len(agreed_ids)} ({len(agreed_ids)/len(merged)*100:.1f}%)")
    print(f"  Still disagreed: {len(disagreed_ids)} ({len(disagreed_ids)/len(merged)*100:.1f}%)")

    print("\nKrippendorff's α comparison (key metrics):")
    for _, row in comparison_df.iterrows():
        c = row["Criterion"]
        pre = row["α H1-H2 (pre)"]
        post = row["α H1-H2 (post)"]
        cons_l1 = row["α H_cons-LLM₁"]
        cons_l2 = row["α H_cons-LLM₂"]
        print(f"  {c:15s}  pre={pre:.3f}  post={post:.3f}  "
              f"cons-LLM₁={cons_l1:.3f}  cons-LLM₂={cons_l2:.3f}")

    print(f"\nResults saved to: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
