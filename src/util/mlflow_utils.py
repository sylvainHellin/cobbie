"""
MLflow utility functions for the Cobbie training system.

This module provides helper functions for managing MLflow runs,
particularly for continuing existing runs to mitigate memory leak issues.
"""

from typing import Optional

import mlflow
from loguru import logger


def get_most_recent_training_run() -> Optional[str]:
    """
    Find the most recent PARENT run in the "Training" experiment.

    Returns:
        The run_id of the most recent parent run, or None if no runs exist

    Raises:
        ValueError: If no runs exist in the Training experiment
    """
    try:
        # Get the experiment ID for the "Training" experiment
        experiment = mlflow.get_experiment_by_name("Training")
        if not experiment:
            raise ValueError("No 'Training' experiment found. Please create an initial run first.")

        experiment_id = experiment.experiment_id

        # First, get all runs sorted by start time (most recent first)
        all_runs = mlflow.search_runs(
            experiment_ids=[experiment_id],
            order_by=["start_time DESC"],
            max_results=100  # Get more runs to filter through
        )

        if all_runs.empty:
            raise ValueError(
                "No runs found in 'Training' experiment. "
                "Please create an initial run first using: "
                "uv run scripts/run_training_phase.py --start 0 --end 10"
            )

        # Filter for parent runs by checking if they don't have mlflow.parentRunId tag
        # Convert to pandas DataFrame and filter
        import pandas as pd

        # Convert to DataFrame if it's not already
        runs_df = pd.DataFrame(all_runs) if not isinstance(all_runs, pd.DataFrame) else all_runs

        # Filter for parent runs - look for rows where mlflow.parentRunId is NaN/None
        if 'tags.mlflow.parentRunId' in runs_df.columns:
            parent_runs = runs_df[runs_df['tags.mlflow.parentRunId'].isna()]
        else:
            # If the column doesn't exist, all runs are parent runs
            parent_runs = runs_df

        if parent_runs.empty:
            raise ValueError(
                "No parent runs found in 'Training' experiment. "
                "Please create an initial run first using: "
                "uv run scripts/run_training_phase.py --start 0 --end 10"
            )

        most_recent_run_id = parent_runs.iloc[0]['run_id']
        logger.info(f"Found most recent parent training run: {most_recent_run_id}")
        return most_recent_run_id

    except Exception as e:
        logger.error(f"Error finding most recent parent training run: {e}")
        raise


def get_run_by_id(run_id: str) -> str:
    """
    Validate and return a specific run ID.

    Args:
        run_id: The MLflow run ID to validate

    Returns:
        The validated run_id

    Raises:
        ValueError: If the run_id is invalid or not found
    """
    try:
        # Try to get the run to validate it exists
        run = mlflow.get_run(run_id)
        logger.info(f"Found specified run: {run_id} (status: {run.info.status})")
        return run_id

    except Exception as e:
        raise ValueError(
            f"Invalid or not found run ID: {run_id}. "
            f"Please check the run ID and try again. "
            f"Run IDs should be 32-character hexadecimal strings."
        ) from e


def get_most_recent_evaluation_run() -> Optional[str]:
    """
    Find the most recent PARENT run in the "Evaluation" experiment.

    Returns:
        The run_id of the most recent parent run, or None if no runs exist

    Raises:
        ValueError: If no runs exist in the Evaluation experiment
    """
    try:
        # Get the experiment ID for the "Evaluation" experiment
        experiment = mlflow.get_experiment_by_name("Evaluation")
        if not experiment:
            raise ValueError("No 'Evaluation' experiment found. Please create an initial run first.")

        experiment_id = experiment.experiment_id

        # First, get all runs sorted by start time (most recent first)
        all_runs = mlflow.search_runs(
            experiment_ids=[experiment_id],
            order_by=["start_time DESC"],
            max_results=100  # Get more runs to filter through
        )

        if all_runs.empty:
            raise ValueError(
                "No runs found in 'Evaluation' experiment. "
                "Please create an initial run first using: "
                "uv run scripts/run_evaluation.py --start 0 --nb-samples 10"
            )

        # Filter for parent runs by checking if they don't have mlflow.parentRunId tag
        # Convert to pandas DataFrame and filter
        import pandas as pd

        # Convert to DataFrame if it's not already
        runs_df = pd.DataFrame(all_runs) if not isinstance(all_runs, pd.DataFrame) else all_runs

        # Filter for parent runs - look for rows where mlflow.parentRunId is NaN/None
        if 'tags.mlflow.parentRunId' in runs_df.columns:
            parent_runs = runs_df[runs_df['tags.mlflow.parentRunId'].isna()]
        else:
            # If the column doesn't exist, all runs are parent runs
            parent_runs = runs_df

        if parent_runs.empty:
            raise ValueError(
                "No parent runs found in 'Evaluation' experiment. "
                "Please create an initial run first using: "
                "uv run scripts/run_evaluation.py --start 0 --nb-samples 10"
            )

        most_recent_run_id = parent_runs.iloc[0]['run_id']
        logger.info(f"Found most recent parent evaluation run: {most_recent_run_id}")
        return most_recent_run_id

    except Exception as e:
        logger.error(f"Error finding most recent parent evaluation run: {e}")
        raise


def determine_run_id(continue_flag: Optional[str]) -> Optional[str]:
    """
    Determine the appropriate run_id based on the --continue flag for Training experiment.

    Args:
        continue_flag: Value from args.continue_run - can be True, None, or a run_id string

    Returns:
        The run_id to use, or None if creating a new run

    Raises:
        ValueError: If there are issues with the continuation request
    """
    if continue_flag is None:
        # No --continue flag, create new run
        return None

    elif continue_flag is True:
        # --continue flag without run_id, find most recent run
        logger.info("Continuing most recent training run...")
        return get_most_recent_training_run()

    else:
        # --continue flag with specific run_id
        logger.info(f"Continuing specific run: {continue_flag}")
        return get_run_by_id(continue_flag)


def determine_evaluation_run_id(continue_flag: Optional[str]) -> Optional[str]:
    """
    Determine the appropriate run_id based on the --continue flag for Evaluation experiment.

    Args:
        continue_flag: Value from args.continue_run - can be True, None, or a run_id string

    Returns:
        The run_id to use, or None if creating a new run

    Raises:
        ValueError: If there are issues with the continuation request
    """
    if continue_flag is None:
        # No --continue flag, create new run
        return None

    elif continue_flag is True:
        # --continue flag without run_id, find most recent run
        logger.info("Continuing most recent evaluation run...")
        return get_most_recent_evaluation_run()

    else:
        # --continue flag with specific run_id
        logger.info(f"Continuing specific run: {continue_flag}")
        return get_run_by_id(continue_flag)