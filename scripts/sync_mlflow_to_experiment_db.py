#!/usr/bin/env python3
"""
MLflow to Experiment Database Sync Script

This script synchronizes MLflow experiments, runs, traces, and spans to the experiment database.
It focuses on "Training" and "Evaluation" experiments with configurable filtering.

Usage:
    python scripts/sync_mlflow_to_experiment_db.py [--experiments Training Evaluation] [--skip-existing-runs] [--dry-run] [--verbose]
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
import urllib3

import mlflow
from mlflow import MlflowClient
from sqlmodel import Session, select

from src.config import MLFLOW_URI
from src.experiment.db import EXPERIMENT_DB_ENGINE, MLFLOW_DB_ENGINE
from src.experiment.db.experiment_models import Experiment, Run, Trace, Span
from src.experiment.db.mlflow_models import (
    Experiments,
    Runs,
    TraceInfo,
    TraceRequestMetadata,
    TraceTags,
    Metrics,
)
from src.engine.util.query_mlflow import CustomMLFlowClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
TARGET_EXPERIMENTS = ["Training", "Evaluation"]
MLFLOW_TRACKING_URI = MLFLOW_URI
ALLOWED_TOOLS = ['created', 'merged', 'updated', 'deleted', 'none']

# Retry and timeout configuration
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0  # Base delay in seconds for exponential backoff
HTTP_TIMEOUT = 30  # HTTP request timeout in seconds
BATCH_SIZE = 10  # Number of traces to process in each batch

# Progress tracking
PROGRESS_FILE = "sync_progress.json"


class SyncStats:
    """Track synchronization statistics."""
    def __init__(self):
        self.experiments_added = 0
        self.runs_added = 0
        self.runs_updated = 0
        self.traces_added = 0
        self.spans_added = 0
        self.errors = []

    def add_error(self, error_msg: str):
        """Add an error to the stats."""
        self.errors.append(error_msg)
        logger.error(error_msg)

    def print_summary(self):
        """Print synchronization summary."""
        logger.info("=== Synchronization Summary ===")
        logger.info(f"Experiments added: {self.experiments_added}")
        logger.info(f"Runs added: {self.runs_added}")
        logger.info(f"Runs updated: {self.runs_updated}")
        logger.info(f"Traces added: {self.traces_added}")
        logger.info(f"Spans added: {self.spans_added}")
        if self.errors:
            logger.error(f"Errors encountered: {len(self.errors)}")
            for error in self.errors:
                logger.error(f"  - {error}")


def retry_with_backoff(max_retries: int = MAX_RETRIES, delay_base: float = RETRY_DELAY_BASE):
    """Decorator for retrying MLflow operations with exponential backoff."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (urllib3.exceptions.HTTPError, mlflow.exceptions.MlflowException,
                        ConnectionError, TimeoutError) as e:
                    if attempt == max_retries:
                        raise

                    delay = delay_base * (2 ** attempt)
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
                except Exception as e:
                    # Don't retry on non-connection errors
                    raise
            return None
        return wrapper
    return decorator


def save_progress(progress_data: Dict):
    """Save progress to allow resuming from checkpoints."""
    try:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(progress_data, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save progress: {e}")


def load_progress() -> Dict:
    """Load progress from checkpoint file."""
    try:
        if not os.path.exists(PROGRESS_FILE):
            return {}
        with open(PROGRESS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load progress: {e}")
        return {}


def setup_mlflow_client_with_timeout() -> CustomMLFlowClient:
    """Setup MLflow client with proper timeout configuration."""
    # Configure urllib3 for better connection handling
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = CustomMLFlowClient()

    # Set timeout on the underlying HTTP client if available
    try:
        # MLflow uses requests internally, we can configure the session
        if hasattr(client, '_tracking_client') and hasattr(client._tracking_client, '_store'):
            store = client._tracking_client._store
            if hasattr(store, '_request_headers'):
                # This is a bit of a hack but helps with timeouts
                import requests
                session = requests.Session()
                session.timeout = HTTP_TIMEOUT
    except Exception as e:
        logger.debug(f"Could not configure MLflow client timeout: {e}")

    return client


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Sync MLflow data to experiment database'
    )
    parser.add_argument(
        '--experiments',
        nargs='+',
        default=TARGET_EXPERIMENTS,
        help='Experiments to sync (default: Training Evaluation)'
    )
    parser.add_argument(
        '--skip-existing-runs',
        action='store_true',
        help='Skip runs that already exist in experiment database'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume from last checkpoint (ignores processed runs)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be imported without making changes'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    return parser.parse_args()


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


def get_experiment_mapping(session: Session, target_experiments: List[str]) -> Dict[str, int]:
    """Get mapping from experiment name to experiment_id for target experiments."""
    statement = select(Experiments).where(Experiments.name.in_(target_experiments))
    mlflow_experiments = {exp.name: exp.experiment_id for exp in session.exec(statement).all()}

    if not mlflow_experiments:
        logger.warning(f"No target experiments found in MLflow: {target_experiments}")

    return mlflow_experiments


def sync_experiments(target_experiments: List[str], dry_run: bool = False) -> Set[str]:
    """
    Sync experiments from MLflow to experiment database.
    Reuses existing import_mlflow_experiments() function.
    """
    logger.info("Syncing experiments...")

    try:
        if dry_run:
            # For dry run, just discover what experiments would be synced
            with Session(MLFLOW_DB_ENGINE) as mlflow_session:
                statement = select(Experiments).where(Experiments.name.in_(target_experiments))
                mlflow_experiments = {str(exp.experiment_id) for exp in mlflow_session.exec(statement).all()}
            logger.info(f"[DRY RUN] Would sync {len(mlflow_experiments)} experiments")
            return mlflow_experiments

        # Import existing function
        from src.experiment.db.query import import_mlflow_experiments

        import_mlflow_experiments()

        # Get the experiment IDs that were synced
        with Session(EXPERIMENT_DB_ENGINE) as db_session:
            statement = select(Experiment).where(Experiment.name.in_(target_experiments))
            synced_experiments = {exp.id for exp in db_session.exec(statement).all()}

        logger.info(f"Synced {len(synced_experiments)} experiments")
        return synced_experiments

    except Exception as e:
        raise Exception(f"Failed to sync experiments: {e}")


def sync_runs(
    target_experiment_ids: Set[str],
    skip_existing: bool = False,
    dry_run: bool = False,
    stats: Optional[SyncStats] = None
) -> Set[str]:
    """
    Sync runs from MLflow to experiment database.
    Enhanced version of existing import_mlflow_runs() function.
    """
    if stats is None:
        stats = SyncStats()

    logger.info("Syncing runs...")

    with Session(EXPERIMENT_DB_ENGINE) as db_session:
        with Session(MLFLOW_DB_ENGINE) as mlflow_session:
            # Get existing run IDs from experiment DB
            existing_run_ids = {run.id for run in db_session.exec(select(Run)).all()}
            logger.debug(f"Found {len(existing_run_ids)} existing runs in experiment DB")

            # Convert string experiment IDs to integers for MLflow query
            target_experiment_int_ids = []
            for exp_id in target_experiment_ids:
                try:
                    target_experiment_int_ids.append(int(exp_id))
                except ValueError:
                    logger.warning(f"Invalid experiment ID format: {exp_id}")

            # Get runs from MLflow for target experiments
            statement = select(Runs).where(Runs.experiment_id.in_(target_experiment_int_ids))
            mlflow_runs = [run for run in mlflow_session.exec(statement).all()]
            logger.debug(f"Found {len(mlflow_runs)} runs in MLflow for target experiments")

            runs_to_process = []
            for mlflow_run in mlflow_runs:
                if mlflow_run.run_uuid is None:
                    continue

                if skip_existing and mlflow_run.run_uuid in existing_run_ids:
                    logger.debug(f"Skipping existing run: {mlflow_run.run_uuid}")
                    continue

                runs_to_process.append(mlflow_run)

            logger.info(f"Processing {len(runs_to_process)} runs")

            if dry_run:
                logger.info(f"[DRY RUN] Would process {len(runs_to_process)} runs")
                return {run.run_uuid for run in runs_to_process if run.run_uuid}

            # Process runs
            synced_run_ids = set()
            for mlflow_run in runs_to_process:
                try:
                    # Extract metrics
                    metrics = {metric.key: metric.value for metric in mlflow_run.metrics}

                    # Calculate timestamp and duration
                    timestamp = (
                        datetime.fromtimestamp(mlflow_run.start_time / 1000)
                        if mlflow_run.start_time is not None
                        else datetime.now()
                    )

                    duration = (
                        mlflow_run.end_time - mlflow_run.start_time
                        if (mlflow_run.end_time and mlflow_run.start_time)
                        else 0
                    )

                    # Extract fields
                    run_id = mlflow_run.run_uuid
                    experiment_id = str(mlflow_run.experiment_id)
                    name = mlflow_run.name or "Unknown Run"
                    url = f"http://127.0.0.1:5000/#/experiments/{mlflow_run.experiment_id}/runs/{mlflow_run.run_uuid}"

                    cost = metrics.get("cost")
                    accuracy = metrics.get("accuracy")
                    input_tokens = int(metrics.get("input_tokens", 0))
                    output_tokens = int(metrics.get("output_tokens", 0))

                    # Check if run exists
                    existing_run = db_session.get(Run, run_id)

                    if existing_run is None:
                        # Create new run
                        run = Run(
                            id=run_id,
                            experiment_id=experiment_id,
                            name=name,
                            url=url,
                            duration=duration,
                            cost=cost,
                            accuracy=accuracy,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            timestamp=timestamp,
                        )
                        db_session.add(run)
                        stats.runs_added += 1
                        logger.debug(f"Added run: {run_id}")
                    else:
                        # Update existing run
                        existing_run.name = name
                        existing_run.url = url
                        existing_run.duration = duration
                        existing_run.cost = cost
                        existing_run.accuracy = accuracy
                        existing_run.input_tokens = input_tokens
                        existing_run.output_tokens = output_tokens
                        existing_run.timestamp = timestamp
                        stats.runs_updated += 1
                        logger.debug(f"Updated run: {run_id}")

                    synced_run_ids.add(run_id)

                except Exception as e:
                    stats.add_error(f"Failed to process run {mlflow_run.run_uuid}: {e}")
                    if not dry_run:
                        raise

            # Commit all runs
            if not dry_run:
                db_session.commit()
                logger.info(f"Synced {len(synced_run_ids)} runs")

            return synced_run_ids


def extract_tools_from_trace_tags(trace_tags: List[TraceTags]) -> str:
    """
    Extract tool classification from trace tags based on training pipeline logic.

    Based on training_pipeline.py:84-94 tool classification logic.
    """
    tag_dict = {tag.key: tag.value for tag in trace_tags}

    # Tool classification logic from training pipeline
    if "tool merged" in tag_dict:
        return "updated"  # Note: pipeline uses "merged" tag but sets "updated"
    elif "tool created" in tag_dict:
        return "created"
    elif "tools merged" in tag_dict:
        return "merged"
    else:
        return "none"


def extract_question_id_from_trace(trace_name: Optional[str], trace_metadata: Dict) -> Optional[int]:
    """
    Extract question ID from trace name, metadata, or trace inputs.

    Based on training_pipeline.py:71-73 pattern: "train_question_id_{qa_pair.id}"
    Also extracts 'id' field from mlflow.traceInputs JSON data.
    """
    if trace_name:
        # Try to extract from trace name pattern (for training traces)
        if "train_question_id_" in trace_name:
            try:
                parts = trace_name.split("train_question_id_")
                if len(parts) > 1:
                    return int(parts[1].split()[0])  # Get the number after the prefix
            except (ValueError, IndexError):
                pass

        # Try to extract from evaluation trace name pattern
        elif "eval_question_id_" in trace_name:
            try:
                parts = trace_name.split("eval_question_id_")
                if len(parts) > 1:
                    return int(parts[1].split()[0])  # Get the number after the prefix
            except (ValueError, IndexError):
                pass

    # Try to extract from metadata
    if "question_id" in trace_metadata:
        try:
            return int(trace_metadata["question_id"])
        except (ValueError, TypeError):
            pass

    # Try to extract from trace inputs JSON (most common case for evaluation traces)
    if "mlflow.traceInputs" in trace_metadata:
        try:
            inputs_data = json.loads(trace_metadata["mlflow.traceInputs"])
            if isinstance(inputs_data, dict) and "id" in inputs_data:
                return int(inputs_data["id"])
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    return None


def sync_traces(
    target_experiment_ids: Set[str],
    synced_run_ids: Set[str],
    dry_run: bool = False,
    stats: Optional[SyncStats] = None
) -> Dict[str, str]:
    """
    Sync traces from MLflow trace_info table to experiment database.
    """
    if stats is None:
        stats = SyncStats()

    logger.info("Syncing traces...")

    trace_id_to_run_id = {}

    with Session(EXPERIMENT_DB_ENGINE) as db_session:
        with Session(MLFLOW_DB_ENGINE) as mlflow_session:
            # Get existing trace IDs
            existing_trace_ids = {trace.id for trace in db_session.exec(select(Trace)).all()}
            logger.debug(f"Found {len(existing_trace_ids)} existing traces in experiment DB")

            # Convert string experiment IDs to integers for MLflow query
            target_experiment_int_ids = []
            for exp_id in target_experiment_ids:
                try:
                    target_experiment_int_ids.append(int(exp_id))
                except ValueError:
                    logger.warning(f"Invalid experiment ID format: {exp_id}")

            # Get trace_info from MLflow for target experiments
            statement = select(TraceInfo).where(
                TraceInfo.experiment_id.in_(target_experiment_int_ids)
            )
            mlflow_traces = [trace for trace in mlflow_session.exec(statement).all()]
            logger.debug(f"Found {len(mlflow_traces)} traces in MLflow for target experiments")

            # Get all runs from target experiments for mapping
            run_mapping = {}
            if synced_run_ids:
                # Create mapping from experiment_id to list of run_uuids
                runs_statement = select(Runs).where(
                    Runs.experiment_id.in_(target_experiment_int_ids),
                    Runs.run_uuid.in_(synced_run_ids)
                )
                runs = mlflow_session.exec(runs_statement).all()
                for run in runs:
                    exp_id = str(run.experiment_id)
                    if exp_id not in run_mapping:
                        run_mapping[exp_id] = []
                    run_mapping[exp_id].append(run.run_uuid)

            traces_to_process = []
            for mlflow_trace in mlflow_traces:
                # Get the actual run_id from trace metadata (mlflow.sourceRun)
                trace_run_id = None

                # Get trace metadata to find the source run
                metadata_statement = select(TraceRequestMetadata).where(
                    TraceRequestMetadata.request_id == mlflow_trace.request_id,
                    TraceRequestMetadata.key == "mlflow.sourceRun"
                )
                metadata_record = mlflow_session.exec(metadata_statement).first()

                if metadata_record:
                    trace_run_id = metadata_record.value
                    # Check if this run exists in our synced runs
                    if trace_run_id not in synced_run_ids:
                        logger.debug(f"Trace {mlflow_trace.request_id} source run {trace_run_id} not in synced runs, skipping")
                        continue
                else:
                    # Fallback: if no sourceRun found, try to find any run from this experiment
                    logger.warning(f"No sourceRun found for trace {mlflow_trace.request_id}")
                    experiment_id_str = str(mlflow_trace.experiment_id)
                    if experiment_id_str in run_mapping and run_mapping[experiment_id_str]:
                        trace_run_id = run_mapping[experiment_id_str][0]
                    else:
                        run_statement = select(Runs).where(
                            Runs.experiment_id == mlflow_trace.experiment_id
                        ).limit(1)
                        matching_run = mlflow_session.exec(run_statement).first()
                        if matching_run and matching_run.run_uuid in synced_run_ids:
                            trace_run_id = matching_run.run_uuid
                        else:
                            logger.warning(f"No suitable run found for trace {mlflow_trace.request_id}")
                            continue

                # Build mapping for existing traces
                if mlflow_trace.request_id in existing_trace_ids:
                    logger.debug(f"Building mapping for existing trace: {mlflow_trace.request_id} -> run {trace_run_id}")
                    trace_id_to_run_id[mlflow_trace.request_id] = trace_run_id
                    continue

                traces_to_process.append((mlflow_trace, trace_run_id))

            logger.info(f"Processing {len(traces_to_process)} traces")

            if dry_run:
                logger.info(f"[DRY RUN] Would process {len(traces_to_process)} traces")
                return trace_id_to_run_id

            # Process traces
            for mlflow_trace, run_id in traces_to_process:
                try:
                    # Get trace metadata and tags
                    metadata_statement = select(TraceRequestMetadata).where(
                        TraceRequestMetadata.request_id == mlflow_trace.request_id
                    )
                    metadata_records = mlflow_session.exec(metadata_statement).all()
                    trace_metadata = {rec.key: rec.value for rec in metadata_records}

                    tags_statement = select(TraceTags).where(
                        TraceTags.request_id == mlflow_trace.request_id
                    )
                    trace_tags = mlflow_session.exec(tags_statement).all()

                    # Extract trace name from tags
                    trace_name = None
                    for tag in trace_tags:
                        if tag.key == "mlflow.traceName":
                            trace_name = tag.value
                            break

                    # Extract data from trace metadata
                    answer = None
                    if "mlflow.traceOutputs" in trace_metadata:
                        try:
                            outputs = json.loads(trace_metadata["mlflow.traceOutputs"])
                            answer = json.dumps(outputs) if outputs else None
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse trace outputs for {mlflow_trace.request_id}")

                    # Extract metrics from tags
                    accuracy = None
                    try:
                        accuracy_str = trace_metadata.get("similarity_score")
                        if accuracy_str:
                            accuracy = float(accuracy_str)
                    except (ValueError, TypeError):
                        pass

                    # Extract tool classification
                    tools = extract_tools_from_trace_tags(trace_tags)

                    # Extract question ID
                    question_id = extract_question_id_from_trace(
                        trace_name, trace_metadata
                    )

                    # Skip traces without question ID (as they are required to be non-null)
                    if question_id is None:
                        logger.debug(f"Skipping trace {mlflow_trace.request_id} without question ID")
                        continue

                    # Create trace record
                    status = "OK" if mlflow_trace.status == "OK" else "ERROR"
                    timestamp = datetime.fromtimestamp(mlflow_trace.timestamp_ms / 1000)

                    trace = Trace(
                        id=mlflow_trace.request_id,
                        run_id=run_id,
                        question_id=question_id,
                        answer=answer,
                        status=status,
                        tools=tools,
                        accuracy=accuracy,
                        duration=mlflow_trace.execution_time_ms or 0,
                        timestamp=timestamp,
                        url=f"http://127.0.0.1:5000/#/experiments/{mlflow_trace.experiment_id}/traces:~:text={mlflow_trace.request_id}"
                    )

                    db_session.add(trace)
                    trace_id_to_run_id[mlflow_trace.request_id] = run_id
                    stats.traces_added += 1
                    logger.debug(f"Added trace: {mlflow_trace.request_id}")

                except Exception as e:
                    stats.add_error(f"Failed to process trace {mlflow_trace.request_id}: {e}")
                    if not dry_run:
                        raise

            # Commit all traces
            if not dry_run:
                db_session.commit()
                logger.info(f"Synced {len(trace_id_to_run_id)} traces")

            return trace_id_to_run_id


@retry_with_backoff()
def get_mlflow_experiment_with_retry(client: CustomMLFlowClient, exp_id_int: int):
    """Get MLflow experiment with retry logic."""
    return client.get_experiment(experiment_id=exp_id_int)


@retry_with_backoff()
def get_mlflow_runs_with_retry(client: CustomMLFlowClient):
    """Get MLflow runs with retry logic."""
    return client.get_runs()


@retry_with_backoff()
def setup_mlflow_run_with_retry(client: CustomMLFlowClient, run_id: str):
    """Setup MLflow run with retry logic."""
    client.setup_by_run_id(run_id)


def identify_corrupted_traces(target_experiment_ids: Set[str]) -> Set[str]:
    """
    Identify traces that have database records but missing artifact files.
    These traces will cause HTTP 500 errors when accessed via MLflow API.
    """
    logger.info("Identifying corrupted traces...")
    corrupted_traces = set()

    with Session(MLFLOW_DB_ENGINE) as mlflow_session:
        # Get trace info for target experiments
        target_experiment_int_ids = []
        for exp_id in target_experiment_ids:
            try:
                target_experiment_int_ids.append(int(exp_id))
            except ValueError:
                logger.warning(f"Invalid experiment ID format: {exp_id}")

        # Get all traces in target experiments
        statement = select(TraceInfo).where(
            TraceInfo.experiment_id.in_(target_experiment_int_ids)
        )
        traces = mlflow_session.exec(statement).all()
        logger.debug(f"Checking {len(traces)} traces for corruption")

        # Base path for MLflow artifacts
        artifact_base_path = "./mlartifacts"

        for trace in traces:
            trace_id = trace.request_id
            experiment_id = trace.experiment_id

            # Expected artifact path
            expected_path = f"{artifact_base_path}/{experiment_id}/traces/{trace_id}/artifacts/traces.json"

            # Check if artifact file exists
            if not os.path.exists(expected_path):
                logger.debug(f"Corrupted trace found: {trace_id} (missing artifact file)")
                corrupted_traces.add(trace_id)
            else:
                # Check if file is empty or corrupted
                try:
                    with open(expected_path, 'r') as f:
                        content = f.read().strip()
                    if not content or len(content) < 10:  # Too short to be valid JSON
                        logger.debug(f"Corrupted trace found: {trace_id} (empty or invalid artifact file)")
                        corrupted_traces.add(trace_id)
                except Exception as e:
                    logger.debug(f"Corrupted trace found: {trace_id} (error reading artifact file: {e})")
                    corrupted_traces.add(trace_id)

    logger.info(f"Found {len(corrupted_traces)} corrupted traces that will be skipped")
    return corrupted_traces


@retry_with_backoff()
def safe_get_mlflow_traces_with_retry(client: CustomMLFlowClient, experiment_id: int, run_id: str,
                                     corrupted_traces: Set[str]) -> List:
    """
    Safely get MLflow traces with corrupted trace filtering.
    """
    try:
        # Setup the run to get traces
        client.setup_by_run_id(run_id)

        if not client.traces:
            return []

        # Filter out corrupted traces
        valid_traces = []
        for trace in client.traces:
            if trace.info.request_id not in corrupted_traces:
                valid_traces.append(trace)
            else:
                logger.debug(f"Skipping corrupted trace: {trace.info.request_id}")

        return valid_traces

    except Exception as e:
        # Check if this is related to corrupted traces
        if "500" in str(e) or "trace" in str(e).lower():
            logger.warning(f"Likely corrupted traces causing error for run {run_id}: {e}")
            return []  # Return empty list to skip this run
        raise


def sync_spans(
    trace_id_to_run_id: Dict[str, str],
    target_experiment_ids: Set[str],
    dry_run: bool = False,
    stats: Optional[SyncStats] = None
):
    """
    Sync spans from MLflow Python API to experiment database.

    Enhanced with corrupted trace detection, retry logic, batch processing, and proper error handling.
    """
    if stats is None:
        stats = SyncStats()

    logger.info("Syncing spans...")
    logger.debug(f"trace_id_to_run_id mapping contains {len(trace_id_to_run_id)} entries")

    if dry_run:
        logger.info("[DRY RUN] Would sync spans via MLflow API")
        return

    # Identify corrupted traces before starting
    corrupted_traces = identify_corrupted_traces(target_experiment_ids)

    # Load progress to resume from failures
    progress = load_progress()
    processed_runs = progress.get("processed_runs", [])

    # Setup MLflow client with proper timeout
    client = setup_mlflow_client_with_timeout()

    with Session(EXPERIMENT_DB_ENGINE) as db_session:
        # Get existing span IDs for deduplication
        existing_span_ids = {span.id for span in db_session.exec(select(Span)).all()}
        logger.debug(f"Found {len(existing_span_ids)} existing spans in experiment DB")

        spans_processed = 0
        total_experiments = len(target_experiment_ids)
        current_experiment_idx = 0
        skipped_runs_for_corruption = 0

        # Process each experiment
        for experiment_id in target_experiment_ids:
            current_experiment_idx += 1
            logger.info(f"Processing experiment {current_experiment_idx}/{total_experiments}: {experiment_id}")

            try:
                # Convert string ID to integer for MLflow API
                exp_id_int = int(experiment_id)

                # Get experiment with retry logic
                try:
                    client.experiment = get_mlflow_experiment_with_retry(client, exp_id_int)
                except Exception as e:
                    stats.add_error(f"Failed to get experiment {experiment_id} after retries: {e}")
                    continue

                if client.experiment is None:
                    logger.warning(f"Experiment {experiment_id} not found in MLflow")
                    continue

                # Get all runs for this experiment with retry logic
                try:
                    runs = get_mlflow_runs_with_retry(client)
                except Exception as e:
                    stats.add_error(f"Failed to get runs for experiment {experiment_id} after retries: {e}")
                    continue

                logger.debug(f"Found {len(runs)} runs for experiment {experiment_id}")

                # Filter runs that were synced and not yet processed
                target_runs = [run for run in runs if run.info.run_id in trace_id_to_run_id.values()
                             and run.info.run_id not in processed_runs]

                logger.info(f"Processing {len(target_runs)} unprocessed runs out of {len(runs)} total runs")

                for run_idx, run in enumerate(target_runs):
                    run_id = run.info.run_id
                    logger.info(f"Processing run {run_idx + 1}/{len(target_runs)}: {run_id}")

                    try:
                        # Get traces for this run with corruption-safe retry logic
                        traces = safe_get_mlflow_traces_with_retry(
                            client, exp_id_int, run_id, corrupted_traces
                        )

                        if not traces:
                            if len(corrupted_traces) > 0:
                                # Likely skipped due to corruption
                                skipped_runs_for_corruption += 1
                                logger.debug(f"Skipping run {run_id} due to corrupted traces")
                            else:
                                logger.debug(f"No traces found for run {run_id}")

                            # Mark this run as processed
                            processed_runs.append(run_id)
                            save_progress({"processed_runs": processed_runs})
                            continue

                        logger.debug(f"Processing {len(traces)} traces for run {run_id}")

                        # Process traces in batches
                        trace_batches = [traces[i:i + BATCH_SIZE]
                                       for i in range(0, len(traces), BATCH_SIZE)]

                        for batch_idx, trace_batch in enumerate(trace_batches):
                            logger.debug(f"Processing trace batch {batch_idx + 1}/{len(trace_batches)} "
                                       f"({len(trace_batch)} traces)")

                            # Process each trace and its spans in this batch
                            for trace in trace_batch:
                                trace_id = trace.info.request_id

                                if trace_id not in trace_id_to_run_id:
                                    logger.debug(f"Skipping trace {trace_id} - not in trace_id_to_run_id mapping")
                                    continue

                                # Get spans from this trace
                                spans = trace.data.spans if hasattr(trace.data, 'spans') else []
                                if not spans:
                                    continue

                                logger.debug(f"Trace {trace_id} has {len(spans)} spans")

                                # Process spans for this trace
                                for span in spans:
                                    try:
                                        # Generate unique span ID
                                        span_id = f"{trace_id}_{span.name}_{span.start_time_ns}"

                                        if span_id in existing_span_ids:
                                            continue

                                        # Extract span data safely
                                        span_type = span.attributes.get("mlflow.spanType", "UNKNOWN")
                                        llm = span.attributes.get("model", None)

                                        # Parse input/output data with error handling
                                        input_data = None
                                        output_data = None

                                        try:
                                            if "mlflow.spanInputs" in span.attributes:
                                                input_data = json.dumps(span.attributes["mlflow.spanInputs"])
                                        except (TypeError, ValueError) as e:
                                            logger.debug(f"Failed to serialize span inputs for {span_id}: {e}")

                                        try:
                                            if "mlflow.spanOutputs" in span.attributes:
                                                output_data = json.dumps(span.attributes["mlflow.spanOutputs"])
                                        except (TypeError, ValueError) as e:
                                            logger.debug(f"Failed to serialize span outputs for {span_id}: {e}")

                                        # Calculate timing safely
                                        start_time = span.start_time_ns / 1_000_000_000 if span.start_time_ns else None
                                        end_time = span.end_time_ns / 1_000_000_000 if span.end_time_ns else None
                                        duration = ((span.end_time_ns - span.start_time_ns) / 1_000_000
                                                  if span.end_time_ns and span.start_time_ns else 0)

                                        # Create span record
                                        span_record = Span(
                                            id=span_id,
                                            trace_id=trace_id,
                                            start_time=start_time,
                                            end_time=end_time,
                                            duration=duration,
                                            type=span_type,
                                            llm=llm,
                                            input_data=input_data,
                                            output_data=output_data,
                                            input_tokens=0,
                                            output_tokens=0,
                                            cost=0.0
                                        )

                                        db_session.add(span_record)
                                        existing_span_ids.add(span_id)
                                        spans_processed += 1
                                        stats.spans_added += 1

                                    except Exception as e:
                                        logger.debug(f"Failed to process span {span.name} in trace {trace_id}: {e}")
                                        continue

                                # Update trace span count
                                try:
                                    db_trace = db_session.get(Trace, trace_id)
                                    if db_trace:
                                        db_trace.nb_spans = len(spans)
                                except Exception as e:
                                    logger.debug(f"Failed to update trace span count for {trace_id}: {e}")

                            # Commit spans for this batch
                            try:
                                db_session.commit()
                                logger.debug(f"Committed spans for trace batch {batch_idx + 1}")
                            except Exception as e:
                                db_session.rollback()
                                stats.add_error(f"Failed to commit spans batch {batch_idx + 1}: {e}")
                                raise

                        # Mark this run as processed
                        processed_runs.append(run_id)
                        save_progress({"processed_runs": processed_runs})
                        logger.info(f"Completed run {run_id} with {spans_processed} total spans processed so far")

                    except Exception as e:
                        stats.add_error(f"Failed to process run {run_id}: {e}")
                        # Mark this run as processed to avoid getting stuck
                        processed_runs.append(run_id)
                        save_progress({"processed_runs": processed_runs})
                        continue

            except Exception as e:
                stats.add_error(f"Failed to process experiment {experiment_id}: {e}")
                continue

        # Clean up progress file on successful completion
        try:
            if os.path.exists(PROGRESS_FILE):
                os.remove(PROGRESS_FILE)
        except Exception as e:
            logger.warning(f"Failed to remove progress file: {e}")

        logger.info(f"Synced {spans_processed} spans across {len(processed_runs)} runs")
        if skipped_runs_for_corruption > 0:
            logger.info(f"Skipped {skipped_runs_for_corruption} runs due to corrupted traces")


def main():
    """Main synchronization function."""
    # Parse arguments
    args = parse_arguments()

    # Setup logging
    setup_logging(args.verbose)

    # Validate arguments
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")

    if args.resume:
        logger.info("RESUME MODE - Will continue from last checkpoint")

    # Check for existing progress file
    if os.path.exists(PROGRESS_FILE) and not args.resume and not args.dry_run:
        logger.warning(f"Progress file {PROGRESS_FILE} exists. Use --resume to continue or delete it to start fresh.")
        response = input("Continue anyway? This will overwrite existing progress. (y/N): ")
        if response.lower() != 'y':
            logger.info("Aborted synchronization.")
            return

    # Initialize statistics
    stats = SyncStats()

    try:
        logger.info("Starting MLflow to Experiment Database synchronization...")
        logger.info(f"Target experiments: {args.experiments}")
        logger.info(f"Skip existing runs: {args.skip_existing_runs}")
        logger.info(f"Resume mode: {args.resume}")

        # Phase 1: Sync experiments
        logger.info("=== Phase 1: Syncing Experiments ===")
        synced_experiment_ids = sync_experiments(args.experiments, args.dry_run)
        stats.experiments_added = len(synced_experiment_ids)

        if not synced_experiment_ids and not args.dry_run:
            logger.warning("No experiments were synced. Exiting.")
            return

        # Phase 2: Sync runs
        logger.info("=== Phase 2: Syncing Runs ===")
        synced_run_ids = sync_runs(
            target_experiment_ids=synced_experiment_ids,
            skip_existing=args.skip_existing_runs,
            dry_run=args.dry_run,
            stats=stats
        )

        if not synced_run_ids and not args.dry_run:
            logger.warning("No runs were synced. Exiting.")
            return

        # Phase 3: Sync traces
        logger.info("=== Phase 3: Syncing Traces ===")
        trace_id_to_run_id = sync_traces(
            target_experiment_ids=synced_experiment_ids,
            synced_run_ids=synced_run_ids,
            dry_run=args.dry_run,
            stats=stats
        )

        # Phase 4: Sync spans
        logger.info("=== Phase 4: Syncing Spans ===")
        sync_spans(
            trace_id_to_run_id=trace_id_to_run_id,
            target_experiment_ids=synced_experiment_ids,
            dry_run=args.dry_run,
            stats=stats
        )

        # Print summary
        logger.info("=== Final Summary ===")
        stats.print_summary()

        if stats.errors and not args.dry_run:
            logger.error("Synchronization completed with errors")
            sys.exit(1)
        else:
            logger.info("Synchronization completed successfully")

    except KeyboardInterrupt:
        logger.info("Synchronization interrupted by user")
        if not args.dry_run:
            logger.info(f"Progress saved to {PROGRESS_FILE}. Use --resume to continue.")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Synchronization failed: {e}")
        if not args.dry_run:
            logger.info(f"Progress saved to {PROGRESS_FILE}. Use --resume to continue.")
            sys.exit(1)
        else:
            logger.error("(This error occurred during dry run)")


if __name__ == "__main__":
    main()