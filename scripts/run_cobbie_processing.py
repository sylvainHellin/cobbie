#!/usr/bin/env python3
"""
COBBIE Dataset Processing Script

Processes the entire IfcBench dataset with COBBIE and stores results in the database.
Creates comprehensive MLflow traces with nested runs for each question.

Usage:
    # Process first 10 questions
    uv run python scripts/run_cobbie_processing.py --start 0 --nb-samples 10

    # Process all questions
    uv run python scripts/run_cobbie_processing.py

    # Resume from question 50
    uv run python scripts/run_cobbie_processing.py --start 50 --nb-samples 100

    # Skip already processed questions
    uv run python scripts/run_cobbie_processing.py --skip-processed
"""

import argparse
import logging
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

import mlflow
from sqlmodel import Session
from tqdm import tqdm

from src.agents.cobbie import cobbie
from src.tools.initial import query_ifcopenshell_docs, web_search
from src.engine.util import get_created_tools
from src.experiment.db import DB_ENGINE
from src.experiment.db.models import IfcBench
from src.experiment.db.query import get_dataset

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_database(session: Session, record_id: int, cobbie_result: str) -> bool:
    """
    Update the IfcBench record with COBBIE result.

    Args:
        session: SQLModel database session
        record_id: ID of the IfcBench record to update
        cobbie_result: Combined thought + answer string to store

    Returns:
        True if update successful, False otherwise
    """
    try:
        # Get existing record
        db_record = session.get(IfcBench, record_id)

        if db_record:
            # Update the cobbie field
            db_record.cobbie = cobbie_result

            # Add to session and commit
            session.add(db_record)
            session.commit()
            return True
        else:
            logger.error(f"Record with id {record_id} not found in database")
            return False

    except Exception as e:
        logger.error(f"Error updating record {record_id}: {e}")
        session.rollback()
        return False


def process_question(
    question_data: IfcBench,
    question_index: int,
    tools_dict: Dict[str, Callable],
    skip_processed: bool = False,
) -> Dict:
    """
    Process a single question with COBBIE and update the database.

    Args:
        question_data: IfcBench database record
        question_index: Index of the question for display
        tools_dict: Dictionary of available tools
        skip_processed: Whether to skip questions that already have COBBIE results

    Returns:
        Dictionary containing processing results
    """
    question = question_data.question
    ground_truth = question_data.ground_truth
    category = question_data.category
    question_id = question_data.id
    ifc_path = question_data.ifc.model_path if question_data.ifc else None

    # Skip if already processed
    if skip_processed and question_data.cobbie is not None:
        logger.info(f"Skipping question {question_id} (already processed)")
        return {
            "question_id": question_id,
            "status": "skipped",
            "reason": "already_processed",
            "execution_time": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    # Skip question if category is not provided
    if category is None:
        error_msg = f"ERROR: Question {question_id} missing required 'category' field. SKIPPING."
        logger.error(error_msg)
        return {
            "question_id": question_id,
            "status": "error",
            "error_message": "Missing required 'category' field",
            "execution_time": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
        }

    logger.info(f"Processing question {question_index + 1} (ID: {question_id}): {question[:100]}...")

    # Create nested MLflow run for this question
    run_name = f"question_{question_id}"

    with mlflow.start_run(run_name=run_name, nested=True) as question_run:
        # Log question parameters
        mlflow.log_params({
            "question": question,
            "ground_truth": ground_truth,
            "category": category,
            "question_id": question_id,
            "component": "COBBIE",
            "llm": "glm-4.6",
            "provider_name": "zai",
            "model_path": ifc_path or "None",
        })

        # Create main span for this question processing
        with mlflow.start_span(name="COBBIE_Processing", span_type="CHAIN") as question_span:
            question_span.set_inputs({
                "question": question,
                "question_id": question_id,
                "category": category,
                "question_index": question_index + 1,
                "model_path": ifc_path or "None",
            })

            start_time = time.time()

            try:
                # Run COBBIE with metrics
                final_answer, collector, execution_history = cobbie(
                    user_input=question,
                    tools=tools_dict,
                    model_path=ifc_path,
                )

                execution_time = time.time() - start_time

                # Extract token usage from collector
                input_tokens = 0
                output_tokens = 0
                total_tokens = 0

                if collector and hasattr(collector, 'usage') and collector.usage:
                    usage = collector.usage
                    input_tokens = usage.input_tokens or 0
                    output_tokens = usage.output_tokens or 0
                    total_tokens = input_tokens + output_tokens

                # Combine thought and answer into readable string
                cobbie_result = f"Thought: {final_answer.thoughts}\n\nAnswer: {final_answer.answer}"

                # Update database
                with Session(DB_ENGINE) as session:
                    update_success = update_database(session, question_id, cobbie_result)

                if not update_success:
                    raise Exception("Database update failed")

                # Log metrics
                mlflow.log_metrics({
                    "execution_time": execution_time,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "success": 1,
                    "db_update_success": 1,
                })

                # Set span outputs
                question_span.set_outputs({
                    "status": "success",
                    "execution_time": execution_time,
                    "answer": final_answer.answer,
                    "reasoning": final_answer.thoughts,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "db_updated": True,
                })

                question_span.set_attributes({
                    "question.status": "success",
                    "question.category": category,
                    "db.updated": True,
                })

                question_span.set_status("OK")

                logger.info(f"Question {question_id} completed: success in {execution_time:.2f}s")

                return {
                    "question_id": question_id,
                    "status": "success",
                    "answer": final_answer.answer,
                    "reasoning": final_answer.thoughts,
                    "execution_time": execution_time,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "db_updated": True,
                    "mlflow_run_id": question_run.info.run_id,
                }

            except Exception as e:
                execution_time = time.time() - start_time
                error_msg = str(e)
                logger.error(f"Error processing question {question_id}: {error_msg}")

                # Log error metrics
                mlflow.log_metrics({
                    "execution_time": execution_time,
                    "success": 0,
                    "db_update_success": 0,
                })

                mlflow.log_param("error_message", error_msg)

                # Set span outputs for error
                question_span.set_outputs({
                    "status": "error",
                    "error_message": error_msg,
                    "execution_time": execution_time,
                })

                question_span.set_attributes({
                    "question.status": "error",
                    "question.category": category,
                })

                question_span.set_status("ERROR")

                return {
                    "question_id": question_id,
                    "status": "error",
                    "error_message": error_msg,
                    "execution_time": execution_time,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "db_updated": False,
                    "mlflow_run_id": question_run.info.run_id,
                }


def main():
    """Main function to run COBBIE processing on the dataset."""
    parser = argparse.ArgumentParser(
        description="Process IfcBench dataset with COBBIE and store results in database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process first 10 questions
  uv run python scripts/run_cobbie_processing.py --start 0 --nb-samples 10

  # Process all questions
  uv run python scripts/run_cobbie_processing.py

  # Resume from question 50
  uv run python scripts/run_cobbie_processing.py --start 50 --nb-samples 100

  # Skip already processed questions
  uv run python scripts/run_cobbie_processing.py --skip-processed
        """
    )

    # Core parameters
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Start index of samples to process (default: 0)"
    )

    parser.add_argument(
        "--nb-samples",
        type=int,
        default=None,
        help="Number of samples to process (default: all remaining)"
    )

    parser.add_argument(
        "--skip-processed",
        action="store_true",
        help="Skip questions that already have COBBIE results"
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.start < 0:
        print("Error: --start must be non-negative")
        return 1

    if args.nb_samples is not None and args.nb_samples <= 0:
        print("Error: --nb-samples must be positive")
        return 1

    # Setup logging level
    logger.setLevel(getattr(logging, args.log_level))

    # Setup MLflow tracking URI and experiment
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("COBBIE_Processing")

    # Load full dataset
    logger.info("Loading full IfcBench dataset...")
    full_dataset = get_dataset(load_ifc_model=True)
    logger.info(f"Total dataset size: {len(full_dataset)}")

    # Apply start and limit
    if args.start >= len(full_dataset):
        print(f"Error: --start ({args.start}) exceeds dataset size ({len(full_dataset)})")
        return 1

    if args.nb_samples is not None:
        end_index = min(args.start + args.nb_samples, len(full_dataset))
    else:
        end_index = len(full_dataset)

    dataset = full_dataset[args.start:end_index]
    actual_samples = len(dataset)

    print(f"Processing {actual_samples} samples from index {args.start} to {end_index - 1}")

    # Prepare tools for COBBIE
    tools_dict = {
        "query_ifcopenshell_docs": query_ifcopenshell_docs,
        "web_search": web_search,
    }

    # Add all created tools from src.tools/created/
    try:
        created_tools = get_created_tools()
        tools_dict.update(created_tools)
        logger.info(f"Loaded {len(created_tools)} created tools for COBBIE")
    except Exception as e:
        logger.warning(f"Could not load created tools: {e}")

    # Start MLflow run
    run_name = f"COBBIE_Processing_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}_samples_{args.start}_{end_index-1}"
    logger.info(f"Starting MLflow run: {run_name}")

    with mlflow.start_run(run_name=run_name) as run:
        run_id = run.info.run_id
        logger.info(f"MLflow run started with ID: {run_id}")

        # Log parameters
        mlflow.log_params({
            "component": "COBBIE",
            "model_name": "glm-4.6",
            "provider_name": "zai",
            "start_index": args.start,
            "end_index": end_index,
            "num_samples": actual_samples,
            "skip_processed": args.skip_processed,
            "tools": ", ".join(tools_dict.keys()),
            "tools_count": len(tools_dict),
        })

        # Time the processing
        start_time = time.time()

        # Process each question (each creates its own nested MLflow run)
        results = []
        success_count = 0
        error_count = 0
        skipped_count = 0

        with tqdm(total=actual_samples, desc="Processing with COBBIE") as pbar:
            for i, question_data in enumerate(dataset):
                result = process_question(
                    question_data=question_data,
                    question_index=args.start + i,
                    tools_dict=tools_dict,
                    skip_processed=args.skip_processed,
                )
                results.append(result)

                # Update counters
                if result["status"] == "success":
                    success_count += 1
                elif result["status"] == "error":
                    error_count += 1
                elif result["status"] == "skipped":
                    skipped_count += 1

                pbar.update(1)

        end_time = time.time()
        total_time = end_time - start_time

        # Calculate metrics
        total_input_tokens = sum(r["input_tokens"] for r in results)
        total_output_tokens = sum(r["output_tokens"] for r in results)
        total_tokens = total_input_tokens + total_output_tokens
        total_execution_time = sum(r["execution_time"] for r in results)
        avg_execution_time = total_execution_time / actual_samples if actual_samples > 0 else 0.0

        # Log summary metrics
        mlflow.log_metrics({
            "total_questions": actual_samples,
            "success_count": success_count,
            "error_count": error_count,
            "skipped_count": skipped_count,
            "success_rate": success_count / actual_samples if actual_samples > 0 else 0.0,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "avg_tokens_per_question": total_tokens / actual_samples if actual_samples > 0 else 0.0,
            "total_execution_time": total_execution_time,
            "avg_execution_time": avg_execution_time,
            "total_wall_time": total_time,
        })

        # Set tags
        mlflow.set_tag("processing_status", "completed")
        mlflow.set_tag("component", "COBBIE")

        logger.info("Processing completed successfully")
        logger.info(f"Total questions: {actual_samples}")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Errors: {error_count}")
        logger.info(f"Skipped: {skipped_count}")
        logger.info(f"Total tokens: {total_tokens}")
        logger.info(f"Total wall time: {total_time:.1f}s")

        # Print summary
        print("\n" + "=" * 80)
        print("COBBIE PROCESSING SUMMARY")
        print("=" * 80)
        print(f"Total Questions: {actual_samples}")
        print(f"Successful: {success_count}")
        print(f"Errors: {error_count}")
        print(f"Skipped: {skipped_count}")
        print(f"Success Rate: {success_count / actual_samples * 100:.1f}%")
        print()
        print("Token Usage:")
        print(f"  Input Tokens: {total_input_tokens:,}")
        print(f"  Output Tokens: {total_output_tokens:,}")
        print(f"  Total Tokens: {total_tokens:,}")
        print(f"  Avg Tokens/Question: {total_tokens / actual_samples:.1f}" if actual_samples > 0 else "  Avg Tokens/Question: 0")
        print()
        print("Performance:")
        print(f"  Total Execution Time: {total_execution_time:.1f}s")
        print(f"  Total Wall Time: {total_time:.1f}s")
        print(f"  Avg Execution Time/Question: {avg_execution_time:.1f}s")
        print()
        print("MLflow Information:")
        print("  Experiment: COBBIE_Processing")
        print("  View details: http://127.0.0.1:5000")
        print("=" * 80)

    print("\nProcessing completed successfully!")
    return 0


if __name__ == "__main__":
    exit(main())
