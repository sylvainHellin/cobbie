#!/usr/bin/env python3
"""
Simplified Evaluation Script for BIM QAS System

Functional approach using BAML COBBIE component for evaluation.
Replaces the complex OOP implementation with a clean, functional design.

Usage:
    # Basic evaluation
    uv run scripts/run_evaluation.py --start 0 --nb-samples 5

    # Evaluate with different range
    uv run scripts/run_evaluation.py --start 10 --nb-samples 10
"""

import argparse
import logging
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

import mlflow
from tqdm import tqdm

from src.agents.answer_verifier import verify_answer
from src.agents.cobbie import cobbie
from src.util import get_created_tools
from src.util.extract_tool_usage import extract_tools_used
from src.db import DEVSET
from src.db.query import (
    increment_eval_tool_inclusion,
    update_eval_tool_usage,
    get_all_eval_tool_stats,
    clear_eval_tool_stats,
)
from src.tools.initial import query_ifcopenshell_docs, web_search
from src.utils.mlflow_utils import determine_evaluation_run_id

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def calculate_and_log_metrics(
    question_results: List[Dict], previous_metrics: Optional[Dict] = None
) -> Dict:
    """Calculate comprehensive evaluation metrics and log to MLflow.

    Args:
        question_results: List of results from current batch
        previous_metrics: Metrics from previous batches (if continuing)

    Returns:
        Dictionary containing calculated cumulative metrics
    """
    # Calculate current batch metrics
    total_questions = len(question_results)
    successful_results = [r for r in question_results if r["status"] == "success"]

    # Basic success metrics for current batch
    success_rate = (
        len(successful_results) / total_questions if total_questions > 0 else 0.0
    )

    # Classification metrics for current batch
    classifications = [
        r["classification"]
        for r in successful_results
        if r["classification"] is not None
    ]
    batch_correct_count = sum(1 for c in classifications if c == "correct")
    batch_wrong_count = sum(1 for c in classifications if c == "wrong")
    batch_abstained_count = sum(1 for c in classifications if c == "abstained")

    # Performance metrics for current batch
    batch_execution_time = sum(r["execution_time"] for r in question_results)

    # Token metrics for current batch
    batch_input_tokens = sum(r["input_tokens"] for r in question_results)
    batch_output_tokens = sum(r["output_tokens"] for r in question_results)

    # Accumulate with previous metrics if continuing
    if previous_metrics:
        cumulative_total_questions = previous_metrics["total_questions"] + total_questions
        cumulative_correct_count = previous_metrics["correct_count"] + batch_correct_count
        cumulative_wrong_count = previous_metrics["wrong_count"] + batch_wrong_count
        cumulative_abstained_count = previous_metrics["abstained_count"] + batch_abstained_count
        cumulative_input_tokens = previous_metrics["total_input_tokens"] + batch_input_tokens
        cumulative_output_tokens = previous_metrics["total_output_tokens"] + batch_output_tokens
        cumulative_execution_time = previous_metrics["total_execution_time"] + batch_execution_time
    else:
        cumulative_total_questions = total_questions
        cumulative_correct_count = batch_correct_count
        cumulative_wrong_count = batch_wrong_count
        cumulative_abstained_count = batch_abstained_count
        cumulative_input_tokens = batch_input_tokens
        cumulative_output_tokens = batch_output_tokens
        cumulative_execution_time = batch_execution_time

    # Calculate derived metrics from cumulative totals
    cumulative_total_tokens = cumulative_input_tokens + cumulative_output_tokens
    cumulative_total_evaluated = cumulative_correct_count + cumulative_wrong_count + cumulative_abstained_count

    cumulative_accuracy = (
        cumulative_correct_count / (cumulative_correct_count + cumulative_wrong_count)
        if (cumulative_correct_count + cumulative_wrong_count) > 0
        else 0.0
    )
    cumulative_abstainance_rate = (
        cumulative_abstained_count / cumulative_total_evaluated
        if cumulative_total_evaluated > 0
        else 0.0
    )
    cumulative_avg_execution_time = (
        cumulative_execution_time / cumulative_total_questions
        if cumulative_total_questions > 0
        else 0.0
    )
    cumulative_avg_tokens_per_question = (
        cumulative_total_tokens / cumulative_total_questions
        if cumulative_total_questions > 0
        else 0.0
    )
    cumulative_tokens_per_second = (
        cumulative_output_tokens / cumulative_execution_time
        if cumulative_execution_time > 0
        else 0.0
    )

    # Create cumulative metrics dictionary
    metrics = {
        # Success metrics (current batch)
        "success_rate": success_rate,
        "successful_answers": len(successful_results),
        "failed_answers": total_questions - len(successful_results),
        # Classification metrics (cumulative)
        "total_questions": cumulative_total_questions,
        "accuracy": cumulative_accuracy,
        "abstainance_rate": cumulative_abstainance_rate,
        "correct_count": cumulative_correct_count,
        "wrong_count": cumulative_wrong_count,
        "abstained_count": cumulative_abstained_count,
        "total_evaluated": cumulative_total_evaluated,
        # Performance metrics (cumulative)
        "total_execution_time": cumulative_execution_time,
        "avg_execution_time": cumulative_avg_execution_time,
        # Token metrics (cumulative)
        "total_input_tokens": cumulative_input_tokens,
        "total_output_tokens": cumulative_output_tokens,
        "total_tokens": cumulative_total_tokens,
        "avg_tokens_per_question": cumulative_avg_tokens_per_question,
        "tokens_per_second": cumulative_tokens_per_second,
    }

    # Log comprehensive metrics to MLflow
    mlflow.log_metrics(metrics)

    # Prepare results summary by extending base metrics with engine info
    results_summary = {
        "model_name": "glm-4.6",
        "provider_name": "zai",
        "num_samples": total_questions,
        **metrics,
    }

    return results_summary


def print_results(results_summary: Dict):
    """Print formatted evaluation results.

    Args:
        results_summary: Dictionary containing evaluation results
    """
    print("\n" + "=" * 80)
    print("EVALUATION RESULTS")
    print("=" * 80)

    print(
        f"Model: {results_summary['model_name']} ({results_summary['provider_name']})"
    )
    print(f"Samples: {results_summary['num_samples']}")
    print()

    print("Classification Metrics:")
    print(f"  Accuracy: {results_summary['accuracy']:.3f}")
    print(f"  Abstainance Rate: {results_summary['abstainance_rate']:.3f}")
    print(f"  Correct Answers: {results_summary['correct_count']}")
    print(f"  Wrong Answers: {results_summary['wrong_count']}")
    print(f"  Abstained Answers: {results_summary['abstained_count']}")
    print(f"  Total Evaluated: {results_summary['total_evaluated']}")
    print()

    print("Token Usage:")
    print(f"  Input Tokens: {results_summary['total_input_tokens']:,}")
    print(f"  Output Tokens: {results_summary['total_output_tokens']:,}")
    print(f"  Total Tokens: {results_summary['total_tokens']:,}")
    print(f"  Avg Tokens/Question: {results_summary['avg_tokens_per_question']:.1f}")
    print()

    print("Performance:")
    print(f"  Total Execution Time: {results_summary['total_execution_time']:.1f}s")
    print(
        f"  Avg Execution Time/Question: {results_summary['avg_execution_time']:.1f}s"
    )
    print(f"  Tokens/Second: {results_summary['tokens_per_second']:.1f}")
    print()

    print("MLflow Information:")
    print("  Experiment: Evaluation")
    print("  View details: http://127.0.0.1:5000")
    print("=" * 80)


def process_question(
    question_data,
    question_index: int,
    tools_dict: Dict[str, Callable],
    args,
) -> Dict:
    """Process a single question with COBBIE and verification.

    Args:
        question_data: Dataset question object
        question_index: Index of the question
        tools_dict: Dictionary of available tools
        start_time: Start time for the evaluation

    Returns:
        Dictionary containing question processing results
    """
    question = question_data.question
    ground_truth = getattr(question_data, "answer", "") or getattr(
        question_data, "ground_truth", ""
    )
    category = getattr(question_data, "category", None)
    question_id = getattr(question_data, "id", f"q_{question_index + 1}")
    ifc_path = question_data.ifc.model_path if question_data.ifc else None

    # Skip question if category is not provided
    if category is None:
        error_msg = f"ERROR: Question {question_id} missing required 'category' field. SKIPPING this question."
        logger.error(error_msg)
        print(f"\n{error_msg}")

        return {
            "question": question,
            "ground_truth": ground_truth,
            "category": None,
            "status": "error",
            "error_message": "Missing required 'category' field",
            "execution_time": 0.0,
            "classification": None,
            "justification": None,
            "confidence": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "mlflow_run_id": "skipped_no_category",
        }

    logger.info(f"Processing question {question_index + 1}: {question[:100]}...")

    # Create individual MLflow run (nested run) for this question
    run_name = f"question_{question_index}_{question_id}"

    with mlflow.start_run(run_name=run_name, nested=True) as question_run:
        # Log question parameters
        mlflow.log_params(
            {
                "question": question,
                "ground_truth": ground_truth,
                "category": category,
                "question_id": question_id,
                "llm": "glm-4.6",
                "provider_name": "zai",
                "model_path": ifc_path or "None",
            }
        )

        # Create main span for this question processing
        with mlflow.start_span(name="COBBIE", span_type="CHAIN") as question_span:
            question_span.set_inputs(
                {
                    "question": question,
                    "ground_truth": ground_truth,
                    "category": category,
                    "question_index": question_index + 1,
                    "model_path": ifc_path or "None",
                }
            )
            question_span.set_attributes(
                {
                    "engine": "baml",
                    "model": "glm-4.6",
                    "provider": "zai",
                }
            )

            start_time_cobbie = time.time()

            # Run COBBIE with metrics
            final_answer, collector, execution_history = cobbie(
                user_input=question,
                tools=tools_dict,
                model_path=ifc_path,
            )
            cobbie_duration = time.time() - start_time_cobbie

            # extract token usage from collector
            cobbie_input_tokens = 0
            cobbie_output_tokens = 0
            cobbie_total_tokens = 0

            if collector and hasattr(collector, "usage") and collector.usage:
                usage = collector.usage
                cobbie_input_tokens = usage.input_tokens or 0
                cobbie_output_tokens = usage.output_tokens or 0
                cobbie_total_tokens = cobbie_input_tokens + cobbie_output_tokens

            # Now run AnswerVerifier if we have a successful answer
            classification = None
            justification = None
            confidence = None
            verifier_input_tokens = 0
            verifier_output_tokens = 0
            verifier_duration = 0

            if final_answer.answer and ground_truth:
                verifier_start = time.time()
                verifier_result, verifier_collector = verify_answer(
                    question=question,
                    category=category,
                    ground_truth=ground_truth,
                    system_response=final_answer.answer,
                )

                verifier_duration = time.time() - verifier_start
                classification = verifier_result.classification
                justification = verifier_result.justification
                confidence = verifier_result.confidence
                verifier_input_tokens = 0
                verifier_output_tokens = 0
                if collector.last:
                    verifier_input_tokens = collector.usage.input_tokens or 0
                    verifier_output_tokens = collector.usage.output_tokens or 0

            # Track tool usage (after answer verification)
            if args.track_tools:
                # Track tools that were available for this question
                available_tools = list(tools_dict.keys())
                increment_eval_tool_inclusion(available_tools)

                # Track tools that were actually used
                tools_used = extract_tools_used(execution_history)
                is_correct = classification == "correct"
                update_eval_tool_usage(tools_used, is_correct)

                # Log to MLflow
                mlflow.log_metric("num_tools_used", len(tools_used))
                logger.info(f"Tracked usage of {len(tools_used)} tools: {tools_used}")

            # Log question-level metrics
            mlflow.log_metrics(
                {
                    "cobbie_duration": cobbie_duration,
                    "verifier_duration": verifier_duration,
                    "cobbie_input_tokens": cobbie_input_tokens,
                    "cobbie_output_tokens": cobbie_output_tokens,
                    "verifier_input_tokens": verifier_input_tokens,
                    "verifier_output_tokens": verifier_output_tokens,
                    "total_input_tokens": cobbie_input_tokens + verifier_input_tokens,
                    "total_output_tokens": cobbie_output_tokens
                    + verifier_output_tokens,
                    "success": 1,
                }
            )

            # Prepare question span outputs
            question_outputs = {
                "status": "success",
                "execution_time": cobbie_duration,
                "answer": final_answer.answer,
                "reasoning": final_answer.thoughts,
                "reasoning_length": len(final_answer.thoughts),
                "cobbie_input_tokens": cobbie_input_tokens,
                "cobbie_output_tokens": cobbie_output_tokens,
                "cobbie_total_tokens": cobbie_total_tokens,
                "verifier_input_tokens": verifier_input_tokens,
                "verifier_output_tokens": verifier_output_tokens,
                "total_input_tokens": cobbie_input_tokens + verifier_input_tokens,
                "total_output_tokens": cobbie_output_tokens + verifier_output_tokens,
                "classification": classification,
                "justification": justification,
                "confidence": confidence,
            }

            question_span.set_outputs(question_outputs)
            question_span.set_status("OK")
            question_span.set_attributes(
                {
                    "question.status": "success",
                    "question.category": category,
                    "classification": classification or "not_evaluated",
                }
            )

            logger.info(
                f"Question {question_index + 1} completed: success in {cobbie_duration:.2f}s, classification: {classification}"
            )

            # Log LLM outputs as parameters
            mlflow.log_params(
                {
                    "answer": final_answer.answer,
                    "classification": classification or "not_evaluated",
                    "justification": justification or "not_evaluated",
                    "confidence": confidence or "not_evaluated",
                }
            )

            return {
                "question": question,
                "ground_truth": ground_truth,
                "category": category,
                "status": "success",
                "answer": final_answer.answer,
                "reasoning": final_answer.thoughts,
                "execution_time": cobbie_duration,
                "classification": classification,
                "justification": justification,
                "confidence": confidence,
                "input_tokens": cobbie_input_tokens + verifier_input_tokens,
                "output_tokens": cobbie_output_tokens + verifier_output_tokens,
                "cobbie_input_tokens": cobbie_input_tokens,
                "cobbie_output_tokens": cobbie_output_tokens,
                "verifier_input_tokens": verifier_input_tokens,
                "verifier_output_tokens": verifier_output_tokens,
                "mlflow_run_id": question_run.info.run_id,
            }


def print_tool_metrics_summary():
    """Print summary of tool usage metrics from evaluation."""
    eval_stats = get_all_eval_tool_stats()

    if not eval_stats:
        print("\nNo tool usage metrics available.")
        return

    print("\n" + "=" * 90)
    print("TOOL USAGE METRICS (EVALUATION)")
    print("=" * 90)

    # Sort by usage frequency
    sorted_stats = sorted(
        eval_stats,
        key=lambda s: s.questions_when_called or 0,
        reverse=True
    )

    # Calculate column widths
    max_tool_name_len = max(len(stat.tool_name or "N/A") for stat in eval_stats)
    max_tool_name_len = max(max_tool_name_len, 20)  # Minimum width for header
    tool_col_width = max_tool_name_len + 2

    # Print header with proper alignment
    header = f"{'Tool Name':<{tool_col_width}} │ {'Included':>8} │ {'Called':>7} │ {'Correct':>8} │ {'Wrong':>7} │ {'Call Rate':>9}"
    print(header)
    print("─" * len(header))

    # Print each tool's statistics
    for stat in sorted_stats:
        tool_name = stat.tool_name or "N/A"
        included = stat.questions_when_included or 0
        called = stat.questions_when_called or 0
        correct = stat.questions_correct_contribution or 0
        wrong = stat.questions_wrong_contribution or 0
        call_rate = (called / included * 100) if included > 0 else 0

        row = f"{tool_name:<{tool_col_width}} │ {included:>8} │ {called:>7} │ {correct:>8} │ {wrong:>7} │ {call_rate:>8.1f}%"
        print(row)

    # Summary statistics
    total_included = sum(s.questions_when_included or 0 for s in eval_stats)
    total_called = sum(s.questions_when_called or 0 for s in eval_stats)
    total_correct = sum(s.questions_correct_contribution or 0 for s in eval_stats)
    total_wrong = sum(s.questions_wrong_contribution or 0 for s in eval_stats)

    print("─" * len(header))
    print(f"{'TOTAL':<{tool_col_width}} │ {total_included:>8} │ {total_called:>7} │ {total_correct:>8} │ {total_wrong:>7} │ {'':>9}")
    print("=" * 90)


def main():
    """Main function to run the evaluation."""
    parser = argparse.ArgumentParser(
        description="Run evaluation experiments on BIM QAS System using BAML COBBIE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic evaluation with first 5 samples
  uv run scripts/run_evaluation.py --start 0 --nb-samples 5

  # Evaluate samples 10-20
  uv run scripts/run_evaluation.py --start 10 --nb-samples 10

  # Evaluate with debug logging
  uv run scripts/run_evaluation.py --start 0 --nb-samples 3 --log-level DEBUG
        """,
    )

    # Core parameters
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Start index of samples to process (default: 0)",
    )

    parser.add_argument(
        "--nb-samples",
        type=int,
        default=10,
        help="Number of samples to process (default: 10)",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--continue",
        dest="continue_run",
        nargs="?",
        const=True,
        help="Continue most recent evaluation run or specific run ID",
    )

    parser.add_argument(
        "--track-tools",
        type=lambda x: x.lower() == "true",
        default=True,
        help="Enable/disable tool usage tracking (default: true)",
    )

    parser.add_argument(
        "--reset-tool-metrics",
        action="store_true",
        help="Clear all evaluation tool metrics before starting",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.start < 0:
        print("Error: --start must be non-negative")
        return 1

    if args.nb_samples <= 0:
        print("Error: --nb-samples must be positive")
        return 1

    if args.start >= len(DEVSET):
        print(f"Error: --start ({args.start}) exceeds dataset size ({len(DEVSET)})")
        return 1

    end_index = min(args.start + args.nb_samples, len(DEVSET))
    actual_samples = end_index - args.start

    print(
        f"Processing {actual_samples} samples from index {args.start} to {end_index - 1}"
    )

    # Setup logging level
    logger.setLevel(getattr(logging, args.log_level))

    # Handle tool metrics reset
    if args.reset_tool_metrics:
        deleted_count = clear_eval_tool_stats()
        logger.info(f"Cleared {deleted_count} evaluation tool metric entries")

    # Setup MLflow tracking URI and experiment
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("Evaluation")

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

    # Prepare dataset
    dataset = DEVSET[args.start : end_index]
    logger.info(f"Using {len(dataset)} samples for evaluation")

    # Determine run_id based on --continue flag
    run_id = determine_evaluation_run_id(args.continue_run)

    if run_id:
        logger.info(f"Continuing existing MLflow run: {run_id}")
        run_name = None  # Don't set a new name when continuing
    else:
        run_name = f"Evaluation_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
        logger.info(f"Creating new MLflow run: {run_name}")

    # Start MLflow run
    with mlflow.start_run(run_id=run_id, run_name=run_name) as run:
        current_run_id = run.info.run_id
        logger.info(f"MLflow run started with ID: {current_run_id}")

        # Log immutable configuration parameters (only for new runs)
        if run_id is None:
            mlflow.log_params(
                {
                    "model_name": "glm-4.6",
                    "provider_name": "zai",
                    "component": "COBBIE",
                    "tools": ", ".join(tools_dict.keys()),
                    "tools_count": len(tools_dict),
                }
            )

        # Get previous metrics if continuing
        previous_metrics: Optional[Dict] = None
        if run_id is not None:
            active_run = mlflow.active_run()
            if active_run:
                previous_metrics = {
                    "total_questions": int(active_run.data.metrics.get("total_questions", 0)),
                    "correct_count": int(active_run.data.metrics.get("correct_count", 0)),
                    "wrong_count": int(active_run.data.metrics.get("wrong_count", 0)),
                    "abstained_count": int(active_run.data.metrics.get("abstained_count", 0)),
                    "total_input_tokens": int(active_run.data.metrics.get("total_input_tokens", 0)),
                    "total_output_tokens": int(active_run.data.metrics.get("total_output_tokens", 0)),
                    "total_execution_time": float(active_run.data.metrics.get("total_execution_time", 0.0)),
                }
                logger.info(f"Continuing run with previous metrics: {previous_metrics}")

        # Time the evaluation
        start_time = time.time()

        # Process each question (each creates its own MLflow run)
        question_results = []
        with tqdm(total=len(dataset), desc="Evaluating BAML COBBIE glm-4.6") as pbar:
            for i, question_data in enumerate(dataset):
                result = process_question(
                    question_data=question_data,
                    question_index=args.start + i,
                    tools_dict=tools_dict,
                    args=args,
                )
                question_results.append(result)
                pbar.update(1)

        end_time = time.time()
        total_evaluation_time = end_time - start_time

        # Calculate and log metrics for the main evaluation run
        results_summary = calculate_and_log_metrics(question_results, previous_metrics)
        results_summary["total_evaluation_time"] = total_evaluation_time

        # Log batch tracking metrics
        batch_metrics = {
            "batch_start_index": args.start,
            "batch_end_index": end_index - 1,
            "batch_size": len(dataset),
        }
        mlflow.log_metrics(batch_metrics)

        # Log additional info to main run
        mlflow.set_tag("evaluation_status", "completed")
        mlflow.set_tag("component", "COBBIE")
        mlflow.set_tag("total_evaluation_time", total_evaluation_time)
        mlflow.set_tag("individual_question_traces", "true")

        logger.info("Evaluation completed successfully")
        logger.info(f"Success rate: {results_summary['success_rate']:.3f}")
        logger.info(f"Accuracy: {results_summary['accuracy']:.3f}")
        logger.info(f"Total evaluation time: {total_evaluation_time:.1f}s")
        logger.info(f"Individual question traces created: {len(question_results)}")

        # Print results
        print_results(results_summary)

        # Print tool metrics summary
        if args.track_tools:
            print_tool_metrics_summary()

    print("\nEvaluation completed successfully!")
    return 0


if __name__ == "__main__":
    exit(main())
