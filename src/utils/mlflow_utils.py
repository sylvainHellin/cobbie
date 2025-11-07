"""
MLflow utility functions for the Cobbie training system.

This module provides helper functions for managing MLflow runs,
particularly for continuing existing runs to mitigate memory leak issues.
"""

import mlflow
from typing import Optional
from src.util import get_logger


_logger = get_logger(name="MLflowUtils", log_level="INFO")


def get_most_recent_training_run() -> Optional[str]:
    """
    Find the most recent run in the "Training" experiment.

    Returns:
        The run_id of the most recent run, or None if no runs exist

    Raises:
        ValueError: If no runs exist in the Training experiment
    """
    try:
        # Get the experiment ID for the "Training" experiment
        experiment = mlflow.get_experiment_by_name("Training")
        if not experiment:
            raise ValueError("No 'Training' experiment found. Please create an initial run first.")

        experiment_id = experiment.experiment_id

        # Search for runs in the Training experiment, ordered by start time (most recent first)
        runs = mlflow.search_runs(
            experiment_ids=[experiment_id],
            order_by=["start_time DESC"],
            max_results=1
        )

        if runs.empty:
            raise ValueError(
                "No runs found in 'Training' experiment. "
                "Please create an initial run first using: "
                "uv run scripts/run_training_phase.py --start 0 --end 10"
            )

        most_recent_run_id = runs.iloc[0]['run_id']
        _logger.info(f"Found most recent training run: {most_recent_run_id}")
        return most_recent_run_id

    except Exception as e:
        _logger.error(f"Error finding most recent training run: {e}")
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
        _logger.info(f"Found specified run: {run_id} (status: {run.info.status})")
        return run_id

    except Exception as e:
        raise ValueError(
            f"Invalid or not found run ID: {run_id}. "
            f"Please check the run ID and try again. "
            f"Run IDs should be 32-character hexadecimal strings."
        ) from e


def determine_run_id(continue_flag: Optional[str]) -> Optional[str]:
    """
    Determine the appropriate run_id based on the --continue flag.

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
        _logger.info("Continuing most recent training run...")
        return get_most_recent_training_run()

    else:
        # --continue flag with specific run_id
        _logger.info(f"Continuing specific run: {continue_flag}")
        return get_run_by_id(continue_flag)