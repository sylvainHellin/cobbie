#!/usr/bin/env python3
"""
Calculate Inter-Rater Reliability Metrics

This script computes IRR metrics between human evaluator(s) and LLM judge:
- Krippendorff's alpha per criterion
- Percentage agreement per criterion
- Confusion matrices for disagreements
- Category-level breakdown

Usage:
    uv run scripts/calculate_irr_metrics.py
"""

import sqlite3
from pathlib import Path

import krippendorff
import numpy as np
import pandas as pd

from src.config import DB_PATH

# Paths
EVAL_DIR = Path("src/db/eval")
SYLVAIN_FILE = EVAL_DIR / "sylvain (export).csv"
LLM_FILE = EVAL_DIR / "LLM_Judge (export).csv"

# Criteria to evaluate
CRITERIA = ["Abstention", "Faithfulness", "Completeness", "Transparency", "Relevance"]


def load_and_merge_data() -> pd.DataFrame:
    """Load both evaluation files and merge on Question ID."""
    # Load files
    sylvain_df = pd.read_csv(SYLVAIN_FILE)
    llm_df = pd.read_csv(LLM_FILE)

    # Rename columns to distinguish judges
    sylvain_cols = {col: f"human_{col}" for col in CRITERIA}
    sylvain_cols["Justification"] = "human_Justification"
    sylvain_df = sylvain_df.rename(columns=sylvain_cols)

    llm_cols = {col: f"llm_{col}" for col in CRITERIA}
    llm_cols["Justification"] = "llm_Justification"
    llm_df = llm_df.rename(columns=llm_cols)

    # Merge on Question ID
    merged = pd.merge(
        sylvain_df[["Question ID"] + [f"human_{c}" for c in CRITERIA] + ["human_Justification", "UPDATED", "Error"]],
        llm_df[["Question ID"] + [f"llm_{c}" for c in CRITERIA] + ["llm_Justification"]],
        on="Question ID",
        how="inner"
    )

    return merged


def filter_data(df: pd.DataFrame) -> pd.DataFrame:
    """Exclude Error=1 and UPDATED=x rows."""
    initial_count = len(df)

    # Exclude errors
    error_mask = df["Error"] == 1
    error_count = error_mask.sum()

    # Exclude updated ground truth
    updated_mask = df["UPDATED"] == "x"
    updated_count = updated_mask.sum()

    # Apply filters
    filtered = df[~error_mask & ~updated_mask].copy()

    print(f"Filtering: {initial_count} total → {len(filtered)} kept")
    print(f"  - Excluded {error_count} error rows")
    print(f"  - Excluded {updated_count} updated ground truth rows")

    return filtered


def normalize_values(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize values for consistent comparison."""
    df = df.copy()

    for judge in ["human", "llm"]:
        # Normalize Abstention to boolean
        abst_col = f"{judge}_Abstention"
        df[abst_col] = df[abst_col].apply(
            lambda x: True if str(x).upper() in ["TRUE", "1"] else False
        )

        # Normalize criteria to Yes/No/Na
        for crit in ["Faithfulness", "Completeness", "Transparency", "Relevance"]:
            col = f"{judge}_{crit}"
            df[col] = df[col].apply(
                lambda x: str(x).strip() if pd.notna(x) else "Na"
            )

    return df


def derive_binary(abstention: bool, faithfulness: str, completeness: str) -> str:
    """Derive binary classification from criteria."""
    if abstention:
        return "abstained"
    elif faithfulness == "Yes" and completeness == "Yes":
        return "correct"
    else:
        return "wrong"


def add_binary_classification(df: pd.DataFrame) -> pd.DataFrame:
    """Add binary classification columns."""
    df = df.copy()

    for judge in ["human", "llm"]:
        df[f"{judge}_Binary"] = df.apply(
            lambda row: derive_binary(
                row[f"{judge}_Abstention"],
                row[f"{judge}_Faithfulness"],
                row[f"{judge}_Completeness"]
            ),
            axis=1
        )

    return df


def fetch_question_categories(question_ids: list[int]) -> dict[int, int]:
    """Fetch question categories from database."""
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join("?" * len(question_ids))
    query = f"SELECT id, category FROM ifc_bench WHERE id IN ({placeholders})"
    cursor = conn.cursor()
    cursor.execute(query, question_ids)
    result = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return result


# =============================================================================
# Encoding Functions for Krippendorff's Alpha
# =============================================================================

def encode_abstention(value) -> float:
    """Encode abstention boolean: True=1, False=0."""
    if pd.isna(value):
        return np.nan
    return 1.0 if value else 0.0


def encode_criterion(value: str) -> float:
    """Encode Yes/No/Na criterion (ordinal): Yes=2, Na=1, No=0."""
    if pd.isna(value) or value is None:
        return np.nan
    mapping = {"Yes": 2.0, "Na": 1.0, "No": 0.0}
    return mapping.get(str(value).strip(), np.nan)


def encode_binary(value: str) -> float:
    """Encode binary classification (nominal): correct=2, abstained=1, wrong=0."""
    if pd.isna(value) or value is None:
        return np.nan
    mapping = {"correct": 2.0, "abstained": 1.0, "wrong": 0.0}
    return mapping.get(str(value).strip(), np.nan)


# =============================================================================
# Metric Calculation Functions
# =============================================================================

def calculate_krippendorff_alpha(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate Krippendorff's alpha for each criterion."""
    results = []

    # Abstention (nominal)
    human_abst = df["human_Abstention"].apply(encode_abstention).to_numpy()
    llm_abst = df["llm_Abstention"].apply(encode_abstention).to_numpy()
    alpha_abst = krippendorff.alpha([human_abst, llm_abst], level_of_measurement="nominal")
    results.append({"Criterion": "Abstention", "Alpha": alpha_abst, "Level": "nominal"})

    # Other criteria (ordinal)
    for crit in ["Faithfulness", "Completeness", "Transparency", "Relevance"]:
        human_vals = df[f"human_{crit}"].apply(encode_criterion).to_numpy()
        llm_vals = df[f"llm_{crit}"].apply(encode_criterion).to_numpy()
        alpha = krippendorff.alpha([human_vals, llm_vals], level_of_measurement="ordinal")
        results.append({"Criterion": crit, "Alpha": alpha, "Level": "ordinal"})

    # Binary classification (nominal)
    human_bin = df["human_Binary"].apply(encode_binary).to_numpy()
    llm_bin = df["llm_Binary"].apply(encode_binary).to_numpy()
    alpha_bin = krippendorff.alpha([human_bin, llm_bin], level_of_measurement="nominal")
    results.append({"Criterion": "Binary", "Alpha": alpha_bin, "Level": "nominal"})

    return pd.DataFrame(results)


def calculate_percentage_agreement(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate percentage agreement for each criterion."""
    results = []

    # Abstention
    agree_abst = (df["human_Abstention"] == df["llm_Abstention"]).sum()
    total = len(df)
    results.append({
        "Criterion": "Abstention",
        "Agree": agree_abst,
        "Total": total,
        "Percentage": agree_abst / total * 100
    })

    # Other criteria
    for crit in ["Faithfulness", "Completeness", "Transparency", "Relevance"]:
        agree = (df[f"human_{crit}"] == df[f"llm_{crit}"]).sum()
        results.append({
            "Criterion": crit,
            "Agree": agree,
            "Total": total,
            "Percentage": agree / total * 100
        })

    # Binary
    agree_bin = (df["human_Binary"] == df["llm_Binary"]).sum()
    results.append({
        "Criterion": "Binary",
        "Agree": agree_bin,
        "Total": total,
        "Percentage": agree_bin / total * 100
    })

    return pd.DataFrame(results)


def calculate_confusion_matrices(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Calculate confusion matrices for each criterion."""
    matrices = {}

    # Abstention
    matrices["Abstention"] = pd.crosstab(
        df["human_Abstention"].map({True: "TRUE", False: "FALSE"}),
        df["llm_Abstention"].map({True: "TRUE", False: "FALSE"}),
        rownames=["Human"],
        colnames=["LLM"]
    )

    # Other criteria
    for crit in ["Faithfulness", "Completeness", "Transparency", "Relevance"]:
        matrices[crit] = pd.crosstab(
            df[f"human_{crit}"],
            df[f"llm_{crit}"],
            rownames=["Human"],
            colnames=["LLM"]
        )

    # Binary
    matrices["Binary"] = pd.crosstab(
        df["human_Binary"],
        df["llm_Binary"],
        rownames=["Human"],
        colnames=["LLM"]
    )

    return matrices


def calculate_category_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate agreement metrics by question category."""
    # Fetch categories
    question_ids = df["Question ID"].tolist()
    categories = fetch_question_categories(question_ids)
    df = df.copy()
    df["Category"] = df["Question ID"].map(categories)

    category_names = {
        1: "Direct Property",
        2: "Aggregation",
        3: "Computation",
        4: "Estimation/Unavailable"
    }

    results = []
    for cat in sorted(df["Category"].unique()):
        cat_df = df[df["Category"] == cat]
        n = len(cat_df)

        # Binary agreement
        agree_bin = (cat_df["human_Binary"] == cat_df["llm_Binary"]).sum()

        # Krippendorff's alpha for binary
        human_bin = cat_df["human_Binary"].apply(encode_binary).to_numpy()
        llm_bin = cat_df["llm_Binary"].apply(encode_binary).to_numpy()
        try:
            alpha = krippendorff.alpha([human_bin, llm_bin], level_of_measurement="nominal")
        except Exception:
            alpha = np.nan

        results.append({
            "Category": cat,
            "Category Name": category_names.get(cat, "Unknown"),
            "N": n,
            "Binary Agreement": agree_bin,
            "Binary %": agree_bin / n * 100 if n > 0 else 0,
            "Binary Alpha": alpha
        })

    return pd.DataFrame(results)


def calculate_criteria_correlations(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Calculate Spearman correlations between criteria.

    Returns correlation matrices for:
    - Human ratings
    - LLM ratings
    - Combined (average of both raters)
    """
    from scipy.stats import spearmanr

    results = {}
    criteria = ["Faithfulness", "Completeness", "Transparency", "Relevance"]

    for judge in ["human", "llm"]:
        # Build numeric dataframe for this judge
        numeric_data = {}

        # Abstention as 0/1
        numeric_data["Abstention"] = df[f"{judge}_Abstention"].apply(
            lambda x: 1.0 if x else 0.0
        )

        # Other criteria as ordinal
        for crit in criteria:
            numeric_data[crit] = df[f"{judge}_{crit}"].apply(encode_criterion)

        # Binary as ordinal
        numeric_data["Binary"] = df[f"{judge}_Binary"].apply(encode_binary)

        judge_df = pd.DataFrame(numeric_data)

        # Calculate Spearman correlation matrix
        corr_matrix = judge_df.corr(method="spearman")
        results[judge.capitalize()] = corr_matrix

    # Combined: average of both raters' numeric values
    combined_data = {}
    combined_data["Abstention"] = (
        df["human_Abstention"].apply(lambda x: 1.0 if x else 0.0) +
        df["llm_Abstention"].apply(lambda x: 1.0 if x else 0.0)
    ) / 2

    for crit in criteria:
        combined_data[crit] = (
            df[f"human_{crit}"].apply(encode_criterion) +
            df[f"llm_{crit}"].apply(encode_criterion)
        ) / 2

    combined_data["Binary"] = (
        df["human_Binary"].apply(encode_binary) +
        df["llm_Binary"].apply(encode_binary)
    ) / 2

    combined_df = pd.DataFrame(combined_data)
    results["Combined"] = combined_df.corr(method="spearman")

    # Also compute p-values for combined correlations
    cols = list(combined_df.columns)
    n = len(cols)
    pval_matrix = pd.DataFrame(np.zeros((n, n)), index=cols, columns=cols)

    for i, col1 in enumerate(cols):
        for j, col2 in enumerate(cols):
            if i == j:
                pval_matrix.loc[col1, col2] = 0.0
            else:
                # Drop NaN for this pair
                mask = combined_df[[col1, col2]].notna().all(axis=1)
                if mask.sum() > 2:
                    _, pval = spearmanr(
                        combined_df.loc[mask, col1],
                        combined_df.loc[mask, col2]
                    )
                    pval_matrix.loc[col1, col2] = pval
                else:
                    pval_matrix.loc[col1, col2] = np.nan

    results["Combined_pvalues"] = pval_matrix

    return results


def print_disagreement_analysis(df: pd.DataFrame) -> None:
    """Print detailed analysis of disagreements."""
    print("\n" + "=" * 80)
    print("DISAGREEMENT ANALYSIS")
    print("=" * 80)

    # Binary disagreements
    disagree_mask = df["human_Binary"] != df["llm_Binary"]
    disagree_df = df[disagree_mask]

    print(f"\nTotal binary disagreements: {len(disagree_df)} / {len(df)} ({len(disagree_df)/len(df)*100:.1f}%)")

    if len(disagree_df) > 0:
        print("\nDisagreement patterns:")
        pattern_counts = disagree_df.groupby(["human_Binary", "llm_Binary"]).size().reset_index(name="Count")
        pattern_counts = pattern_counts.sort_values("Count", ascending=False)
        for _, row in pattern_counts.iterrows():
            print(f"  Human={row['human_Binary']}, LLM={row['llm_Binary']}: {row['Count']}")

        print("\nSample disagreements (first 10):")
        for _, row in disagree_df.head(10).iterrows():
            print(f"\n  Q{row['Question ID']}:")
            print(f"    Human: {row['human_Binary']} (F={row['human_Faithfulness']}, C={row['human_Completeness']})")
            print(f"    LLM:   {row['llm_Binary']} (F={row['llm_Faithfulness']}, C={row['llm_Completeness']})")
            if pd.notna(row.get("human_Justification")) and row["human_Justification"]:
                justification = str(row["human_Justification"])[:100]
                print(f"    Human note: {justification}...")


def interpret_alpha(alpha: float) -> str:
    """Return interpretation of Krippendorff's alpha value."""
    if np.isnan(alpha):
        return "N/A"
    elif alpha >= 0.800:
        return "Excellent"
    elif alpha >= 0.667:
        return "Good"
    elif alpha >= 0.500:
        return "Moderate"
    else:
        return "Poor"


# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 80)
    print("INTER-RATER RELIABILITY ANALYSIS")
    print("Human (Sylvain) vs. LLM Judge")
    print("=" * 80)

    # Load and process data
    print("\n1. Loading data...")
    df = load_and_merge_data()
    print(f"   Loaded {len(df)} questions")

    print("\n2. Filtering data...")
    df = filter_data(df)

    print("\n3. Normalizing values...")
    df = normalize_values(df)

    print("\n4. Adding binary classification...")
    df = add_binary_classification(df)

    # Calculate metrics
    print("\n" + "=" * 80)
    print("KRIPPENDORFF'S ALPHA")
    print("=" * 80)
    alpha_df = calculate_krippendorff_alpha(df)
    alpha_df["Interpretation"] = alpha_df["Alpha"].apply(interpret_alpha)
    print(alpha_df.to_string(index=False))

    print("\n" + "=" * 80)
    print("PERCENTAGE AGREEMENT")
    print("=" * 80)
    agreement_df = calculate_percentage_agreement(df)
    print(agreement_df.to_string(index=False))

    print("\n" + "=" * 80)
    print("CONFUSION MATRICES")
    print("=" * 80)
    matrices = calculate_confusion_matrices(df)
    for crit, matrix in matrices.items():
        print(f"\n{crit}:")
        print(matrix.to_string())

    print("\n" + "=" * 80)
    print("CATEGORY-LEVEL BREAKDOWN")
    print("=" * 80)
    category_df = calculate_category_breakdown(df)
    print(category_df.to_string(index=False))

    # Correlation analysis
    print("\n" + "=" * 80)
    print("CORRELATION ANALYSIS (Spearman)")
    print("=" * 80)
    correlations = calculate_criteria_correlations(df)

    print("\nCombined (average of Human + LLM ratings):")
    print(correlations["Combined"].round(3).to_string())

    print("\nP-values for Combined correlations:")
    print(correlations["Combined_pvalues"].round(4).to_string())

    print("\nHuman ratings only:")
    print(correlations["Human"].round(3).to_string())

    print("\nLLM ratings only:")
    print(correlations["Llm"].round(3).to_string())

    # Disagreement analysis
    print_disagreement_analysis(df)

    # Summary for paper
    print("\n" + "=" * 80)
    print("SUMMARY FOR PAPER")
    print("=" * 80)
    print(f"\nDataset: {len(df)} questions evaluated by both Human and LLM")
    print(f"\nOverall Binary Classification Agreement:")
    bin_agree = agreement_df[agreement_df["Criterion"] == "Binary"]["Percentage"].values[0]
    bin_alpha = alpha_df[alpha_df["Criterion"] == "Binary"]["Alpha"].values[0]
    print(f"  - Agreement: {bin_agree:.1f}%")
    print(f"  - Krippendorff's α: {bin_alpha:.3f} ({interpret_alpha(bin_alpha)})")

    print(f"\nPer-Criterion Krippendorff's α:")
    for _, row in alpha_df.iterrows():
        print(f"  - {row['Criterion']}: {row['Alpha']:.3f} ({row['Interpretation']})")

    # Save results to CSV
    output_dir = Path("reports")
    output_dir.mkdir(exist_ok=True)

    alpha_df.to_csv(output_dir / "irr_krippendorff_alpha.csv", index=False)
    agreement_df.to_csv(output_dir / "irr_percentage_agreement.csv", index=False)
    category_df.to_csv(output_dir / "irr_category_breakdown.csv", index=False)
    correlations["Combined"].to_csv(output_dir / "irr_correlations_combined.csv")
    correlations["Combined_pvalues"].to_csv(output_dir / "irr_correlations_pvalues.csv")

    print(f"\n✅ Results saved to {output_dir}/")


if __name__ == "__main__":
    main()
