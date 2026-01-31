"""Streamlit app for interactive evaluation run analysis.

Launch with: uv run streamlit run scripts/eval_analysis_app.py
"""

import mlflow
import pandas as pd
import streamlit as st
from mlflow import MlflowClient

from src.analysis.data_extraction import (
    CATEGORY_NAMES,
    list_evaluation_runs,
    load_run_dataframe,
)
from src.config import MLFLOW_URI
from src.db.query import update_ifc_bench_rows

st.set_page_config(page_title="Cobbie Eval Analysis", layout="wide")
mlflow.set_tracking_uri(MLFLOW_URI)
client = MlflowClient()

# Shared state: list available runs
runs = list_evaluation_runs(client)
run_options = {f"{r['run_name']} ({r['start_time']:%Y-%m-%d %H:%M})": r["run_id"] for r in runs}

# Column order for display
DISPLAY_COLS = [
    "question_id", "project_name", "model_name", "category", "question",
    "ground_truth", "classification", "cobbie_answer", "justification",
    "faithfulness", "completeness", "transparency", "relevance",
    "num_iterations", "cobbie_duration",
]

COMPARISON_COLS = [
    "run_name", "question_id", "project_name", "category", "question",
    "ground_truth", "classification", "cobbie_answer", "justification",
    "faithfulness", "completeness", "transparency", "relevance",
]


@st.cache_data(show_spinner="Loading run data...")
def get_run_dataframe(_client: MlflowClient, run_id: str) -> pd.DataFrame:
    """Cached wrapper around load_run_dataframe."""
    return load_run_dataframe(_client, run_id)


def apply_filters(df: pd.DataFrame, classification_filter: list[str],
                  category_filter: list[int], project_filter: list[str]) -> pd.DataFrame:
    """Apply sidebar filters to a DataFrame."""
    filtered = df.copy()
    if classification_filter:
        filtered = filtered[filtered["classification"].isin(classification_filter)]
    if category_filter:
        filtered = filtered[filtered["category"].isin(category_filter)]
    if project_filter:
        filtered = filtered[filtered["project_name"].isin(project_filter)]
    return filtered


# --- Tabs ---
tab1, tab2, tab3 = st.tabs(["Single Run Analysis", "Run Comparison (Disagreements)", "Both Wrong"])


# === Tab 1: Single Run Analysis ===
with tab1:
    st.header("Single Run Analysis")

    if not run_options:
        st.warning("No evaluation runs found. Make sure MLflow is running and has evaluation data.")
    else:
        # Sidebar filters
        with st.sidebar:
            st.header("Filters (Tab 1)")
            selected_run_label = st.selectbox("Select Run", options=list(run_options.keys()), key="tab1_run")
            selected_run_id = run_options[selected_run_label] if selected_run_label else None

            classification_options = ["correct", "wrong", "abstained", "unknown"]
            classification_filter = st.multiselect(
                "Classification", options=classification_options, default=["wrong"], key="tab1_class"
            )
            category_filter = st.multiselect(
                "Category", options=[1, 2, 3, 4],
                format_func=lambda x: f"{x} - {CATEGORY_NAMES.get(x, 'Unknown')}",
                key="tab1_cat",
            )

        if selected_run_id:
            df = get_run_dataframe(client, selected_run_id)

            # Project filter (depends on loaded data)
            with st.sidebar:
                all_projects = sorted(df["project_name"].dropna().unique().tolist())
                project_filter = st.multiselect("Project", options=all_projects, key="tab1_proj")

            filtered = apply_filters(df, classification_filter, category_filter, project_filter)

            st.write(f"Showing {len(filtered)} of {len(df)} questions")

            if not filtered.empty:
                # Add update checkbox column
                display_df = filtered[DISPLAY_COLS].copy()
                display_df.insert(0, "update", False)

                # Column config
                column_config = {
                    "update": st.column_config.CheckboxColumn("Update", required=True),
                    "question": st.column_config.TextColumn("Question", width="large"),
                    "ground_truth": st.column_config.TextColumn("Ground Truth", width="large"),
                    "cobbie_answer": st.column_config.TextColumn("Cobbie Answer", width="large"),
                    "justification": st.column_config.TextColumn("Justification", width="large"),
                    "category": st.column_config.SelectboxColumn("Category", options=[1, 2, 3, 4]),
                }

                disabled_cols = [
                    "question_id", "project_name", "model_name", "classification",
                    "cobbie_answer", "justification", "faithfulness", "completeness",
                    "transparency", "relevance", "num_iterations", "cobbie_duration",
                ]

                edited_df = st.data_editor(
                    display_df,
                    column_config=column_config,
                    disabled=disabled_cols,
                    hide_index=True,
                    use_container_width=True,
                    key="tab1_editor",
                )

                # Apply Updates button
                if st.button("Apply Updates", type="primary"):
                    rows_to_update = edited_df[edited_df["update"]].to_dict("records")
                    if rows_to_update:
                        count = update_ifc_bench_rows(rows_to_update)
                        st.success(f"Updated {count} row(s) in the database.")
                        # Clear cache so next load reflects changes
                        get_run_dataframe.clear()
                    else:
                        st.info("No rows selected for update.")


# === Tab 2: Run Comparison (Disagreements) ===
with tab2:
    st.header("Run Comparison — Disagreements")

    if len(run_options) < 2:
        st.warning("Need at least 2 evaluation runs for comparison.")
    else:
        col_a, col_b = st.columns(2)
        run_labels = list(run_options.keys())
        with col_a:
            label_a = st.selectbox("Run A", options=run_labels, index=0, key="tab2_run_a")
        with col_b:
            label_b = st.selectbox("Run B", options=run_labels, index=min(1, len(run_labels) - 1), key="tab2_run_b")

        run_id_a = run_options[label_a]
        run_id_b = run_options[label_b]

        if run_id_a == run_id_b:
            st.info("Select two different runs to compare.")
        else:
            df_a = get_run_dataframe(client, run_id_a)
            df_b = get_run_dataframe(client, run_id_b)

            merged = df_a.merge(df_b, on="question_id", suffixes=("_a", "_b"))
            disagreements = merged[
                (merged["classification_a"] != merged["classification_b"])
                & ~((merged["classification_a"] == "wrong") & (merged["classification_b"] == "wrong"))
            ]

            # Filters
            filter_col1, filter_col2 = st.columns(2)
            with filter_col1:
                cat_filter = st.multiselect(
                    "Category", options=[1, 2, 3, 4],
                    format_func=lambda x: f"{x} - {CATEGORY_NAMES.get(x, 'Unknown')}",
                    key="tab2_cat",
                )
            with filter_col2:
                all_projects_merged = sorted(
                    set(merged["project_name_a"].dropna().tolist() + merged["project_name_b"].dropna().tolist())
                )
                proj_filter = st.multiselect("Project", options=all_projects_merged, key="tab2_proj")

            if cat_filter:
                disagreements = disagreements[
                    disagreements["category_a"].isin(cat_filter) | disagreements["category_b"].isin(cat_filter)
                ]
            if proj_filter:
                disagreements = disagreements[
                    disagreements["project_name_a"].isin(proj_filter) | disagreements["project_name_b"].isin(proj_filter)
                ]

            # Summary stats
            a_correct_b_wrong = len(disagreements[
                (disagreements["classification_a"] == "correct") & (disagreements["classification_b"] == "wrong")
            ])
            a_wrong_b_correct = len(disagreements[
                (disagreements["classification_a"] == "wrong") & (disagreements["classification_b"] == "correct")
            ])

            m1, m2, m3 = st.columns(3)
            m1.metric("Run A correct / Run B wrong", a_correct_b_wrong)
            m2.metric("Run A wrong / Run B correct", a_wrong_b_correct)
            m3.metric("Total disagreements", len(disagreements))

            # Build stacked rows
            if not disagreements.empty:
                stacked_rows = []
                name_a = df_a["parent_run_name"].iloc[0] if not df_a.empty else "Run A"
                name_b = df_b["parent_run_name"].iloc[0] if not df_b.empty else "Run B"

                for _, row in disagreements.iterrows():
                    row_a = {"run_name": name_a, "question_id": row["question_id"]}
                    row_b = {"run_name": name_b, "question_id": row["question_id"]}
                    for col in COMPARISON_COLS:
                        if col in ("run_name", "question_id"):
                            continue
                        row_a[col] = row.get(f"{col}_a", "")
                        row_b[col] = row.get(f"{col}_b", "")
                    stacked_rows.append(row_a)
                    stacked_rows.append(row_b)

                stacked_df = pd.DataFrame(stacked_rows)

                # Style with alternating pair backgrounds
                def highlight_pairs(df: pd.DataFrame) -> list[list[str]]:
                    styles = []
                    for i in range(len(df)):
                        pair_idx = i // 2
                        if pair_idx % 2 == 0:
                            styles.append(["background-color: #f0f2f6"] * len(df.columns))
                        else:
                            styles.append([""] * len(df.columns))
                    return styles

                styled = stacked_df.style.apply(lambda _: highlight_pairs(stacked_df)[_.name], axis=1)
                st.dataframe(styled, use_container_width=True, hide_index=True)
            else:
                st.info("No disagreements found between the selected runs (excluding both-wrong).")


# === Tab 3: Both Wrong ===
with tab3:
    st.header("Both Wrong")

    if len(run_options) < 2:
        st.warning("Need at least 2 evaluation runs for comparison.")
    else:
        col_a3, col_b3 = st.columns(2)
        run_labels = list(run_options.keys())
        with col_a3:
            label_a3 = st.selectbox("Run A", options=run_labels, index=0, key="tab3_run_a")
        with col_b3:
            label_b3 = st.selectbox("Run B", options=run_labels, index=min(1, len(run_labels) - 1), key="tab3_run_b")

        run_id_a3 = run_options[label_a3]
        run_id_b3 = run_options[label_b3]

        if run_id_a3 == run_id_b3:
            st.info("Select two different runs to compare.")
        else:
            df_a3 = get_run_dataframe(client, run_id_a3)
            df_b3 = get_run_dataframe(client, run_id_b3)

            merged3 = df_a3.merge(df_b3, on="question_id", suffixes=("_a", "_b"))
            both_wrong = merged3[
                (merged3["classification_a"] == "wrong") & (merged3["classification_b"] == "wrong")
            ]

            # Filters
            filter_col1_3, filter_col2_3 = st.columns(2)
            with filter_col1_3:
                cat_filter3 = st.multiselect(
                    "Category", options=[1, 2, 3, 4],
                    format_func=lambda x: f"{x} - {CATEGORY_NAMES.get(x, 'Unknown')}",
                    key="tab3_cat",
                )
            with filter_col2_3:
                all_projects_merged3 = sorted(
                    set(merged3["project_name_a"].dropna().tolist() + merged3["project_name_b"].dropna().tolist())
                )
                proj_filter3 = st.multiselect("Project", options=all_projects_merged3, key="tab3_proj")

            if cat_filter3:
                both_wrong = both_wrong[
                    both_wrong["category_a"].isin(cat_filter3) | both_wrong["category_b"].isin(cat_filter3)
                ]
            if proj_filter3:
                both_wrong = both_wrong[
                    both_wrong["project_name_a"].isin(proj_filter3) | both_wrong["project_name_b"].isin(proj_filter3)
                ]

            st.metric("Both wrong", len(both_wrong))

            if not both_wrong.empty:
                stacked_rows3 = []
                name_a3 = df_a3["parent_run_name"].iloc[0] if not df_a3.empty else "Run A"
                name_b3 = df_b3["parent_run_name"].iloc[0] if not df_b3.empty else "Run B"

                for _, row in both_wrong.iterrows():
                    row_a = {"run_name": name_a3, "question_id": row["question_id"]}
                    row_b = {"run_name": name_b3, "question_id": row["question_id"]}
                    for col in COMPARISON_COLS:
                        if col in ("run_name", "question_id"):
                            continue
                        row_a[col] = row.get(f"{col}_a", "")
                        row_b[col] = row.get(f"{col}_b", "")
                    stacked_rows3.append(row_a)
                    stacked_rows3.append(row_b)

                stacked_df3 = pd.DataFrame(stacked_rows3)

                def highlight_pairs3(df: pd.DataFrame) -> list[list[str]]:
                    styles = []
                    for i in range(len(df)):
                        pair_idx = i // 2
                        if pair_idx % 2 == 0:
                            styles.append(["background-color: #f0f2f6"] * len(df.columns))
                        else:
                            styles.append([""] * len(df.columns))
                    return styles

                styled3 = stacked_df3.style.apply(lambda _: highlight_pairs3(stacked_df3)[_.name], axis=1)
                st.dataframe(styled3, use_container_width=True, hide_index=True)
            else:
                st.info("No questions where both runs are wrong.")
