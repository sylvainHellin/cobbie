#!/usr/bin/env python3
"""
Single batch processor for IFC training.
Processes exactly one batch of QA pairs with full dependency reloading.
"""

import argparse
import sys
import time
from datetime import datetime
from typing import List

# Full imports - each process starts fresh
import dspy
import mlflow
import mlflow.dspy
from tqdm import tqdm

from src.config.agents import TrainingPipelineConfig
from src.config.llm import LLM
from src.engine import TrainingModule
from src.engine.schemas import OutputsCollection, QA_Pair
from src.engine.util import get_logger
from src.experiment.datasets import load_train_dev_split


def setup_logger(name: str = "TrainingBatch"):
    """Setup logger for batch processing."""
    return get_logger(name=name, log_level="INFO")


def validate_mlflow_connection(experiment_name: str):
    """Validate MLflow server connection and experiment existence."""
    try:
        mlflow.set_tracking_uri("http://127.0.0.1:5000")

        # Test connection by getting experiment
        experiment = mlflow.get_experiment_by_name(experiment_name)
        if experiment is None:
            raise ValueError(f"Experiment '{experiment_name}' not found in MLflow")

        return True
    except Exception as e:
        raise RuntimeError(f"MLflow connection validation failed: {e}")


def process_single_batch(batch: List[QA_Pair], run_id: str, experiment_name: str,
                        model: str, provider: str, batch_num: int, total_batches: int,
                        logger) -> OutputsCollection:
    """Process a single batch of QA pairs with full MLflow tracking."""

    # Setup MLflow context
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment(experiment_name)

    # Configure DSPy
    lm_config = LLM(model=model, provider=provider)
    lm = lm_config.get_llm()
    dspy.configure(lm=lm)
    dspy.configure_cache(enable_disk_cache=True, enable_memory_cache=True)

    with mlflow.start_run(run_id=run_id) as run_context:
        logger.info(f"Processing batch {batch_num}/{total_batches} with {len(batch)} questions")

        training = TrainingModule()
        outputs = OutputsCollection()

        batch_start_time = datetime.now()

        for qa_pair in batch:
            with mlflow.start_span(
                name=f"train_question_id_{qa_pair.id}",
                span_type="MODULE",
            ) as trace:
                question_start = datetime.now()

                try:
                    # Process individual question
                    output = training(qa_pair=qa_pair)
                    status = "OK" if output.status == "success" else "ERROR"

                    # Log detailed metrics and traces
                    tools = "none"
                    if output.tools_metrics.nb_tools_updated > 0:
                        mlflow.update_current_trace(tags={"tool merged": "true"})
                        tools = "updated"
                    elif output.tools_metrics.nb_tools_created > 0:
                        mlflow.update_current_trace(tags={"tool created": "true"})
                        tools = "created"
                    elif output.tools_metrics.nb_tools_merged > 0:
                        mlflow.update_current_trace(tags={"tools merged": "true"})
                        tools = "merged"

                    mlflow.update_current_trace(
                        tags={
                            "input tokens": str(output.lm_metrics.input_tokens),
                            "output tokens": str(output.lm_metrics.output_tokens),
                            "accuracy": str(output.result.similarity_score),
                            "tools": tools,
                            "status": status,
                        }
                    )

                    outputs.add(output=output, update=True)

                    question_duration = (datetime.now() - question_start).total_seconds()
                    logger.info(f"Processed question_id {qa_pair.id} in {question_duration:.2f}s - Status: {status}")

                except Exception as e:
                    logger.error(f"Failed to process question_id {qa_pair.id}: {e}")
                    mlflow.update_current_trace(
                        tags={
                            "status": "ERROR",
                            "error": str(e),
                        }
                    )
                    continue

        # Calculate batch duration
        batch_duration = (datetime.now() - batch_start_time).total_seconds()

        # Log batch-level metrics
        mlflow.log_metrics({
            "batch_accuracy": outputs.mean_acc(),
            "batch_total_input_tokens": outputs.lm_metrics.input_tokens or 0,
            "batch_total_output_tokens": outputs.lm_metrics.output_tokens or 0,
            "batch_total_cost": outputs.lm_metrics.cost or 0.0,
            "batch_questions_processed": len(batch),
            "batch_duration_seconds": batch_duration,
            "batch_tools_created": outputs.tools_metrics.nb_tools_created,
            "batch_tools_updated": outputs.tools_metrics.nb_tools_updated,
            "batch_tools_merged": outputs.tools_metrics.nb_tools_merged,
        }, step=batch_num)

        logger.info(f"Batch {batch_num} completed in {batch_duration:.2f}s")
        logger.info(f"Batch metrics - Accuracy: {outputs.mean_acc():.3f}, Cost: ${outputs.lm_metrics.cost or 0:.4f}")
        logger.info(f"Tools - Created: {outputs.tools_metrics.nb_tools_created}, Updated: {outputs.tools_metrics.nb_tools_updated}, Merged: {outputs.tools_metrics.nb_tools_merged}")

        return outputs


def main():
    """Main entry point for batch processing."""
    parser = argparse.ArgumentParser(description="Process a single training batch")
    parser.add_argument("--run-id", required=True, help="MLflow run ID to continue")
    parser.add_argument("--experiment-name", required=True, help="MLflow experiment name")
    parser.add_argument("--model", required=True, help="Model name")
    parser.add_argument("--provider", required=True, help="Provider name")
    parser.add_argument("--start-index", type=int, required=True, help="Start index in trainset")
    parser.add_argument("--batch-size", type=int, default=30, help="Batch size")
    parser.add_argument("--total-samples", type=int, required=True, help="Total training samples")
    parser.add_argument("--batch-num", type=int, required=True, help="Current batch number")
    parser.add_argument("--total-batches", type=int, required=True, help="Total number of batches")

    args = parser.parse_args()

    # Setup logger
    logger = setup_logger()

    try:
        # Validate MLflow connection
        validate_mlflow_connection(args.experiment_name)
        logger.info(f"MLflow connection validated for experiment '{args.experiment_name}'")

        # Load dataset
        _, trainset_full = load_train_dev_split()

        # Extract batch
        end_index = min(args.start_index + args.batch_size, args.total_samples)
        batch = trainset_full[args.start_index:end_index]

        if not batch:
            logger.warning(f"No questions to process in batch {args.batch_num} (indices {args.start_index}-{end_index-1})")
            return

        logger.info(f"Starting batch {args.batch_num}/{args.total_batches}")
        logger.info(f"Processing questions {args.start_index} to {end_index-1} (total: {len(batch)})")

        # Process the batch
        outputs = process_single_batch(
            batch=batch,
            run_id=args.run_id,
            experiment_name=args.experiment_name,
            model=args.model,
            provider=args.provider,
            batch_num=args.batch_num,
            total_batches=args.total_batches,
            logger=logger
        )

        logger.info(f"Successfully completed batch {args.batch_num}")
        sys.exit(0)

    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()