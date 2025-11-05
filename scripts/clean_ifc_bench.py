#!/usr/bin/env python3
"""
IFC-Bench Dataset Cleaning Script

This script processes the IFC-Bench dataset by:
1. Aligning questions and answers for structural consistency
2. Validating question categories according to the 4-category taxonomy
3. Optionally updating the database with cleaned data
4. Generating a detailed report of all changes

Usage:
    # Test run (10 samples, no database update)
    uv run python scripts/clean_ifc_bench.py --nb-samples 10

    # Full run (all samples, with database update)
    uv run python scripts/clean_ifc_bench.py --nb-samples 1000 --update

    # Full dataset (no database update)
    uv run python scripts/clean_ifc_bench.py
"""

import argparse
import csv
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import mlflow
from sqlmodel import Session
from tqdm import tqdm

from src.agents.category_validator import validate_category
from src.agents.qa_pair_aligner import align_qa_pair
from src.config import LOG_LEVEL
from src.engine.util import get_logger
from src.experiment.db import DB_ENGINE
from src.experiment.db.models import IfcBench
from src.experiment.db.query import get_dataset

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = get_logger(name="clean_ifc_bench", log_level=LOG_LEVEL)


def process_qa_pair(
    qa_pair: IfcBench,
    question_index: int,
) -> Dict:
    """
    Process a single QA pair through alignment and validation.

    Args:
        qa_pair: The IfcBench QA pair to process
        question_index: Index of the question for logging

    Returns:
        Dictionary containing processing results and changes
    """
    logger.info(f"Processing QA pair {qa_pair.id} (index {question_index})")

    # Store original values
    original_question = qa_pair.question
    original_answer = qa_pair.ground_truth
    original_category = qa_pair.category

    # Initialize result tracking
    result = {
        "id": qa_pair.id,
        "original_question": original_question,
        "aligned_question": original_question,
        "question_changed": False,
        "original_answer": original_answer,
        "aligned_answer": original_answer,
        "answer_changed": False,
        "original_category": original_category,
        "validated_category": original_category,
        "category_changed": False,
        "status": "success",
        "error_message": "",
        "alignment_error": False,
        "validation_error": False,
    }

    # Create nested MLflow run for this QA pair
    run_name = f"qa_pair_{qa_pair.id}"

    with mlflow.start_run(run_name=run_name, nested=True) as qa_run:
        # Log original parameters
        mlflow.log_params({
            "qa_pair_id": qa_pair.id,
            "question_index": question_index,
            "original_category": original_category,
        })

        # Phase 1: Align question and answer
        try:
            aligned_qa_pair = align_qa_pair(qa_pair)

            # Check if changes were made
            result["aligned_question"] = aligned_qa_pair.question
            result["aligned_answer"] = aligned_qa_pair.ground_truth
            result["question_changed"] = original_question != aligned_qa_pair.question
            result["answer_changed"] = original_answer != aligned_qa_pair.ground_truth

            logger.info(
                f"  Alignment: question_changed={result['question_changed']}, "
                f"answer_changed={result['answer_changed']}"
            )

        except Exception as e:
            logger.error(f"  Error during alignment for QA pair {qa_pair.id}: {e}")
            result["alignment_error"] = True
            result["error_message"] = f"Alignment error: {str(e)}"
            aligned_qa_pair = qa_pair  # Use original on error

        # Phase 2: Validate category (using aligned values)
        try:
            validated_qa_pair = validate_category(aligned_qa_pair)

            # Check if category was changed
            result["validated_category"] = validated_qa_pair.category
            result["category_changed"] = original_category != validated_qa_pair.category

            logger.info(
                f"  Validation: category_changed={result['category_changed']} "
                f"(original={original_category}, validated={validated_qa_pair.category})"
            )

        except Exception as e:
            logger.error(f"  Error during validation for QA pair {qa_pair.id}: {e}")
            result["validation_error"] = True
            if result["error_message"]:
                result["error_message"] += f"; Validation error: {str(e)}"
            else:
                result["error_message"] = f"Validation error: {str(e)}"
            validated_qa_pair = aligned_qa_pair  # Use aligned values on validation error

        # Determine overall status
        if result["alignment_error"] or result["validation_error"]:
            result["status"] = "error"

        # Log summary metrics
        mlflow.log_metrics({
            "question_changed": 1 if result["question_changed"] else 0,
            "answer_changed": 1 if result["answer_changed"] else 0,
            "category_changed": 1 if result["category_changed"] else 0,
            "alignment_error": 1 if result["alignment_error"] else 0,
            "validation_error": 1 if result["validation_error"] else 0,
        })

        # Log final values
        mlflow.log_params({
            "final_category": validated_qa_pair.category,
            "status": result["status"],
        })

        # Return result with final QA pair
        result["cleaned_qa_pair"] = validated_qa_pair
        return result


def update_database(results: List[Dict]) -> int:
    """
    Update the database with cleaned QA pairs.

    Args:
        results: List of processing results containing cleaned QA pairs

    Returns:
        Number of records successfully updated
    """
    logger.info("Updating database with cleaned data...")
    updated_count = 0

    with Session(DB_ENGINE) as session:
        for result in results:
            if result["status"] == "success":
                try:
                    # Get existing record
                    db_record = session.get(IfcBench, result["id"])

                    if db_record:
                        # Update fields with cleaned values
                        cleaned_qa_pair = result["cleaned_qa_pair"]
                        db_record.question = cleaned_qa_pair.question
                        db_record.ground_truth = cleaned_qa_pair.ground_truth
                        db_record.category = cleaned_qa_pair.category

                        # Add to session
                        session.add(db_record)
                        updated_count += 1
                    else:
                        logger.warning(f"Record with id {result['id']} not found in database")

                except Exception as e:
                    logger.error(f"Error updating record {result['id']}: {e}")

        # Commit all changes
        session.commit()
        logger.info(f"Successfully updated {updated_count} records in database")

    return updated_count


def save_report(results: List[Dict], report_path: Path):
    """
    Save cleaning results to a CSV report.

    Args:
        results: List of processing results
        report_path: Path to save the report
    """
    logger.info(f"Saving report to {report_path}")

    # Ensure reports directory exists
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # Define CSV columns
    fieldnames = [
        "id",
        "original_question",
        "aligned_question",
        "question_changed",
        "original_answer",
        "aligned_answer",
        "answer_changed",
        "original_category",
        "validated_category",
        "category_changed",
        "status",
        "error_message",
    ]

    # Write CSV
    with open(report_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for result in results:
            # Create row with only the fields we want in the CSV
            row = {key: result.get(key, "") for key in fieldnames}
            writer.writerow(row)

    logger.info(f"Report saved successfully: {report_path}")


def print_summary(results: List[Dict], duration: float, updated: bool, report_path: Path):
    """
    Print a summary of the cleaning results.

    Args:
        results: List of processing results
        duration: Total processing time in seconds
        updated: Whether the database was updated
        report_path: Path where the report was saved
    """
    total_records = len(results)
    successful_records = sum(1 for r in results if r["status"] == "success")
    error_records = sum(1 for r in results if r["status"] == "error")

    questions_aligned = sum(1 for r in results if r["question_changed"])
    answers_aligned = sum(1 for r in results if r["answer_changed"])
    categories_updated = sum(1 for r in results if r["category_changed"])

    alignment_errors = sum(1 for r in results if r["alignment_error"])
    validation_errors = sum(1 for r in results if r["validation_error"])

    print("\n" + "=" * 80)
    print("IFC-BENCH DATASET CLEANING SUMMARY")
    print("=" * 80)
    print(f"Total records processed: {total_records}")
    print(f"Successful: {successful_records} ({successful_records/total_records*100:.1f}%)")
    print(f"Errors: {error_records} ({error_records/total_records*100:.1f}%)")
    print()

    print("Changes Applied:")
    print(f"  Questions aligned: {questions_aligned} ({questions_aligned/total_records*100:.1f}%)")
    print(f"  Answers aligned: {answers_aligned} ({answers_aligned/total_records*100:.1f}%)")
    print(f"  Categories updated: {categories_updated} ({categories_updated/total_records*100:.1f}%)")
    print()

    print("Errors Encountered:")
    print(f"  Alignment errors: {alignment_errors}")
    print(f"  Validation errors: {validation_errors}")
    print()

    print(f"Processing time: {duration:.1f}s ({duration/total_records:.2f}s per record)")
    print(f"Database updated: {'Yes' if updated else 'No (use --update flag to update)'}")
    print()

    print(f"Report saved to: {report_path}")
    print("MLflow experiment: http://127.0.0.1:5000 (IFCBenchCleaning)")
    print("=" * 80)


def main():
    """Main function to run the IFC-Bench cleaning script."""
    parser = argparse.ArgumentParser(
        description="Clean IFC-Bench dataset by aligning QA pairs and validating categories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test run (10 samples, no database update)
  uv run python scripts/clean_ifc_bench.py --nb-samples 10

  # Full run (all samples, with database update)
  uv run python scripts/clean_ifc_bench.py --nb-samples 1000 --update

  # Process entire dataset without updating
  uv run python scripts/clean_ifc_bench.py
        """
    )

    parser.add_argument(
        "--nb-samples",
        type=int,
        default=None,
        help="Number of samples to process (default: all samples in dataset)"
    )

    parser.add_argument(
        "--update",
        action="store_true",
        help="Update the database with cleaned data (default: False for safety)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.nb_samples is not None and args.nb_samples <= 0:
        print("Error: --nb-samples must be positive")
        return 1

    # Setup MLflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("IFCBenchCleaning")

    # Load dataset
    logger.info(f"Loading dataset (limit={args.nb_samples or 'all'})...")
    dataset = get_dataset(limit=args.nb_samples)

    if not dataset:
        print("Error: No data found in dataset")
        return 1

    print(f"\nLoaded {len(dataset)} QA pairs from IFC-Bench dataset")
    print(f"Database update: {'ENABLED' if args.update else 'DISABLED (dry run)'}")
    print()

    # Create timestamp for report
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_path = Path(f"reports/ifc_bench_cleaning_{timestamp}.csv")

    # Start main MLflow run
    run_name = f"IFCBenchCleaning_{timestamp}_samples_{len(dataset)}"
    logger.info(f"Starting MLflow run: {run_name}")

    with mlflow.start_run(run_name=run_name) as run:
        # Log parameters
        mlflow.log_params({
            "num_samples": len(dataset),
            "update_database": args.update,
            "timestamp": timestamp,
        })

        # Process all QA pairs
        start_time = time.time()
        results = []

        with tqdm(total=len(dataset), desc="Cleaning IFC-Bench dataset") as pbar:
            for i, qa_pair in enumerate(dataset):
                result = process_qa_pair(qa_pair, question_index=i)
                results.append(result)
                pbar.update(1)

        duration = time.time() - start_time

        # Calculate summary metrics
        total_records = len(results)
        successful_records = sum(1 for r in results if r["status"] == "success")
        questions_aligned = sum(1 for r in results if r["question_changed"])
        answers_aligned = sum(1 for r in results if r["answer_changed"])
        categories_updated = sum(1 for r in results if r["category_changed"])
        alignment_errors = sum(1 for r in results if r["alignment_error"])
        validation_errors = sum(1 for r in results if r["validation_error"])

        # Log summary metrics
        mlflow.log_metrics({
            "total_records": total_records,
            "successful_records": successful_records,
            "error_records": total_records - successful_records,
            "questions_aligned": questions_aligned,
            "answers_aligned": answers_aligned,
            "categories_updated": categories_updated,
            "alignment_errors": alignment_errors,
            "validation_errors": validation_errors,
            "processing_time": duration,
            "avg_time_per_record": duration / total_records if total_records > 0 else 0,
            "question_alignment_rate": questions_aligned / total_records if total_records > 0 else 0,
            "answer_alignment_rate": answers_aligned / total_records if total_records > 0 else 0,
            "category_update_rate": categories_updated / total_records if total_records > 0 else 0,
        })

        # Update database if requested
        if args.update:
            updated_count = update_database(results)
            mlflow.log_metric("records_updated", updated_count)
            mlflow.set_tag("database_updated", "true")
        else:
            mlflow.set_tag("database_updated", "false")

        # Save report
        save_report(results, report_path)
        mlflow.log_artifact(str(report_path))

        # Print summary
        print_summary(results, duration, args.update, report_path)

        # Set completion status
        mlflow.set_tag("status", "completed")

    logger.info("Cleaning completed successfully")
    return 0


if __name__ == "__main__":
    exit(main())
