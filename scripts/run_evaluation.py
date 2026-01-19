#!/usr/bin/env python3
"""
Simplified Evaluation Script for BIM QAS System

Functional approach using COBBIE component for evaluation.
Replaces the complex OOP implementation with a clean, functional design.

Usage:
    # Basic evaluation (default: initial + created tools)
    uv run scripts/run_evaluation.py --start 0 --nb-samples 5

    # Evaluate with different range
    uv run scripts/run_evaluation.py --start 10 --nb-samples 10

    # Evaluate with specific tool directories
    uv run scripts/run_evaluation.py --start 0 --nb-samples 5 --tools manual

    # Evaluate with all tool directories
    uv run scripts/run_evaluation.py --start 0 --nb-samples 5 --tools initial created manual

    # Merge mode: run cobbie twice (initial, created) then consolidate
    uv run scripts/run_evaluation.py --start 0 --nb-samples 5 --merge
"""

import argparse
import sys
import time
from datetime import datetime
from typing import Callable, cast, Dict, List, Literal, Optional

import mlflow
from loguru import logger
from tqdm import tqdm

from src.agents.answer_verifier import verify_answer, derive_binary_classification
from src.agents.cobbie import cobbie
from src.config import ROOT_PATH
from src.db import DEVSET
from src.db.query import (
    clear_eval_tool_stats,
    get_all_eval_tool_stats,
    increment_eval_tool_inclusion,
    update_eval_tool_usage,
)
from src.util.extract_tool_usage import extract_tools_used
from src.util.get_tools import get_tools
from src.util.mlflow_utils import determine_evaluation_run_id
from src.util.setup_logger import setup_logger

# Initialize logger
setup_logger()

# Mapping from BAML client names to model/provider info for logging
CLIENT_INFO: Dict[str, Dict[str, str]] = {
    "GLM_4_7": {"model": "glm-4.7", "provider": "zai"},
    "GLM_4_5_air": {"model": "glm-4.5-air", "provider": "zai"},
    "Devstral": {"model": "devstral-small-2", "provider": "ollama"},
    "Gemini_2_5_Flash_Lite": {"model": "gemini-2.5-flash-lite", "provider": "google"},
}


def calculate_and_log_metrics(
    question_results: List[Dict],
    client: str,
    previous_metrics: Optional[Dict] = None,
) -> Dict:
    """Calculate comprehensive evaluation metrics and log to MLflow.

    Args:
        question_results: List of results from current batch
        client: BAML client name used for evaluation
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
        cumulative_total_questions = (
            previous_metrics["total_questions"] + total_questions
        )
        cumulative_correct_count = (
            previous_metrics["correct_count"] + batch_correct_count
        )
        cumulative_wrong_count = previous_metrics["wrong_count"] + batch_wrong_count
        cumulative_abstained_count = (
            previous_metrics["abstained_count"] + batch_abstained_count
        )
        cumulative_input_tokens = (
            previous_metrics["total_input_tokens"] + batch_input_tokens
        )
        cumulative_output_tokens = (
            previous_metrics["total_output_tokens"] + batch_output_tokens
        )
        cumulative_execution_time = (
            previous_metrics["total_execution_time"] + batch_execution_time
        )
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
    cumulative_total_evaluated = (
        cumulative_correct_count + cumulative_wrong_count + cumulative_abstained_count
    )

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

    # Calculate criterion-level metrics for current batch
    batch_abstention_count = sum(1 for r in successful_results if r.get("abstention"))
    batch_faithfulness_yes = sum(1 for r in successful_results if r.get("faithfulness") == "Yes")
    batch_faithfulness_no = sum(1 for r in successful_results if r.get("faithfulness") == "No")
    batch_faithfulness_na = sum(1 for r in successful_results if r.get("faithfulness") == "Na")
    batch_completeness_yes = sum(1 for r in successful_results if r.get("completeness") == "Yes")
    batch_completeness_no = sum(1 for r in successful_results if r.get("completeness") == "No")
    batch_completeness_na = sum(1 for r in successful_results if r.get("completeness") == "Na")
    batch_transparency_yes = sum(1 for r in successful_results if r.get("transparency") == "Yes")
    batch_transparency_no = sum(1 for r in successful_results if r.get("transparency") == "No")
    batch_transparency_na = sum(1 for r in successful_results if r.get("transparency") == "Na")
    batch_relevance_yes = sum(1 for r in successful_results if r.get("relevance") == "Yes")
    batch_relevance_no = sum(1 for r in successful_results if r.get("relevance") == "No")
    batch_relevance_na = sum(1 for r in successful_results if r.get("relevance") == "Na")

    # Accumulate criterion metrics with previous if continuing
    if previous_metrics:
        cumulative_abstention_count = previous_metrics.get("abstention_count", 0) + batch_abstention_count
        cumulative_faithfulness_yes = previous_metrics.get("faithfulness_yes_count", 0) + batch_faithfulness_yes
        cumulative_faithfulness_no = previous_metrics.get("faithfulness_no_count", 0) + batch_faithfulness_no
        cumulative_faithfulness_na = previous_metrics.get("faithfulness_na_count", 0) + batch_faithfulness_na
        cumulative_completeness_yes = previous_metrics.get("completeness_yes_count", 0) + batch_completeness_yes
        cumulative_completeness_no = previous_metrics.get("completeness_no_count", 0) + batch_completeness_no
        cumulative_completeness_na = previous_metrics.get("completeness_na_count", 0) + batch_completeness_na
        cumulative_transparency_yes = previous_metrics.get("transparency_yes_count", 0) + batch_transparency_yes
        cumulative_transparency_no = previous_metrics.get("transparency_no_count", 0) + batch_transparency_no
        cumulative_transparency_na = previous_metrics.get("transparency_na_count", 0) + batch_transparency_na
        cumulative_relevance_yes = previous_metrics.get("relevance_yes_count", 0) + batch_relevance_yes
        cumulative_relevance_no = previous_metrics.get("relevance_no_count", 0) + batch_relevance_no
        cumulative_relevance_na = previous_metrics.get("relevance_na_count", 0) + batch_relevance_na
    else:
        cumulative_abstention_count = batch_abstention_count
        cumulative_faithfulness_yes = batch_faithfulness_yes
        cumulative_faithfulness_no = batch_faithfulness_no
        cumulative_faithfulness_na = batch_faithfulness_na
        cumulative_completeness_yes = batch_completeness_yes
        cumulative_completeness_no = batch_completeness_no
        cumulative_completeness_na = batch_completeness_na
        cumulative_transparency_yes = batch_transparency_yes
        cumulative_transparency_no = batch_transparency_no
        cumulative_transparency_na = batch_transparency_na
        cumulative_relevance_yes = batch_relevance_yes
        cumulative_relevance_no = batch_relevance_no
        cumulative_relevance_na = batch_relevance_na

    # Calculate criterion rates (yes / (yes + no))
    cumulative_abstention_rate = (
        cumulative_abstention_count / cumulative_total_evaluated
        if cumulative_total_evaluated > 0
        else 0.0
    )
    cumulative_faithfulness_rate = (
        cumulative_faithfulness_yes / (cumulative_faithfulness_yes + cumulative_faithfulness_no)
        if (cumulative_faithfulness_yes + cumulative_faithfulness_no) > 0
        else 0.0
    )
    cumulative_completeness_rate = (
        cumulative_completeness_yes / (cumulative_completeness_yes + cumulative_completeness_no)
        if (cumulative_completeness_yes + cumulative_completeness_no) > 0
        else 0.0
    )
    cumulative_transparency_rate = (
        cumulative_transparency_yes / (cumulative_transparency_yes + cumulative_transparency_no)
        if (cumulative_transparency_yes + cumulative_transparency_no) > 0
        else 0.0
    )
    cumulative_relevance_rate = (
        cumulative_relevance_yes / (cumulative_relevance_yes + cumulative_relevance_no)
        if (cumulative_relevance_yes + cumulative_relevance_no) > 0
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
        # Criterion-level counts (cumulative)
        "abstention_count": cumulative_abstention_count,
        "faithfulness_yes_count": cumulative_faithfulness_yes,
        "faithfulness_no_count": cumulative_faithfulness_no,
        "faithfulness_na_count": cumulative_faithfulness_na,
        "completeness_yes_count": cumulative_completeness_yes,
        "completeness_no_count": cumulative_completeness_no,
        "completeness_na_count": cumulative_completeness_na,
        "transparency_yes_count": cumulative_transparency_yes,
        "transparency_no_count": cumulative_transparency_no,
        "transparency_na_count": cumulative_transparency_na,
        "relevance_yes_count": cumulative_relevance_yes,
        "relevance_no_count": cumulative_relevance_no,
        "relevance_na_count": cumulative_relevance_na,
        # Criterion-level rates (cumulative)
        "abstention_rate": cumulative_abstention_rate,
        "faithfulness_rate": cumulative_faithfulness_rate,
        "completeness_rate": cumulative_completeness_rate,
        "transparency_rate": cumulative_transparency_rate,
        "relevance_rate": cumulative_relevance_rate,
    }

    # Log comprehensive metrics to MLflow
    mlflow.log_metrics(metrics)

    # Prepare results summary by extending base metrics with engine info
    client_info = CLIENT_INFO.get(client, {"model": client, "provider": "unknown"})
    results_summary = {
        "model_name": client_info["model"],
        "provider_name": client_info["provider"],
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

    print("Classification Metrics (Derived):")
    print(f"  Accuracy: {results_summary['accuracy']:.3f}")
    print(f"  Correct Answers: {results_summary['correct_count']}")
    print(f"  Wrong Answers: {results_summary['wrong_count']}")
    print(f"  Abstained Answers: {results_summary['abstained_count']}")
    print(f"  Total Evaluated: {results_summary['total_evaluated']}")
    print()

    print("Criterion-Level Metrics:")
    print(f"  Abstention Rate: {results_summary['abstention_rate']:.3f}")
    print(f"    - Abstained: {results_summary['abstention_count']}")
    print()
    print(f"  Faithfulness Rate: {results_summary['faithfulness_rate']:.3f}")
    print(f"    - Yes: {results_summary['faithfulness_yes_count']}")
    print(f"    - No: {results_summary['faithfulness_no_count']}")
    print(f"    - N/A: {results_summary['faithfulness_na_count']}")
    print()
    print(f"  Completeness Rate: {results_summary['completeness_rate']:.3f}")
    print(f"    - Yes: {results_summary['completeness_yes_count']}")
    print(f"    - No: {results_summary['completeness_no_count']}")
    print(f"    - N/A: {results_summary['completeness_na_count']}")
    print()
    print(f"  Transparency Rate: {results_summary['transparency_rate']:.3f}")
    print(f"    - Yes: {results_summary['transparency_yes_count']}")
    print(f"    - No: {results_summary['transparency_no_count']}")
    print(f"    - N/A: {results_summary['transparency_na_count']}")
    print()
    print(f"  Relevance Rate: {results_summary['relevance_rate']:.3f}")
    print(f"    - Yes: {results_summary['relevance_yes_count']}")
    print(f"    - No: {results_summary['relevance_no_count']}")
    print(f"    - N/A: {results_summary['relevance_na_count']}")
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
        client_info = CLIENT_INFO.get(args.client, {"model": args.client, "provider": "unknown"})
        mlflow.log_params(
            {
                "question": question,
                "ground_truth": ground_truth,
                "category": category,
                "question_id": question_id,
                "llm": client_info["model"],
                "provider_name": client_info["provider"],
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
                    "model": client_info["model"],
                    "provider": client_info["provider"],
                }
            )

            start_time_cobbie = time.time()

            # Run COBBIE with metrics
            final_answer, collector, execution_history = cobbie(
                user_input=question,
                tools=tools_dict,
                model_path=ifc_path,
                client=args.client,
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
            abstention = None
            faithfulness = None
            completeness = None
            transparency = None
            relevance = None
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

                # Derive binary classification from 5-criterion evaluation
                classification = derive_binary_classification(verifier_result)

                # Extract all 5 criteria
                abstention = verifier_result.abstention
                faithfulness = verifier_result.faithfulness.value
                completeness = verifier_result.completeness.value
                transparency = verifier_result.transparency.value
                relevance = verifier_result.relevance.value
                justification = verifier_result.justification

                verifier_input_tokens = 0
                verifier_output_tokens = 0
                if collector.last:
                    verifier_input_tokens = collector.usage.input_tokens or 0
                    verifier_output_tokens = collector.usage.output_tokens or 0

            # Track tool usage (after answer verification)
            if args.track_tools:
                # Track tools that were available for this question
                available_tool_names = list(tools_dict.keys())
                increment_eval_tool_inclusion(available_tool_names)

                # Track tools that were actually used
                tools_used = extract_tools_used(execution_history, available_tool_names)
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
                "abstention": abstention,
                "faithfulness": faithfulness,
                "completeness": completeness,
                "transparency": transparency,
                "relevance": relevance,
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
                    "abstention": str(abstention) if abstention is not None else "not_evaluated",
                    "faithfulness": faithfulness or "not_evaluated",
                    "completeness": completeness or "not_evaluated",
                    "transparency": transparency or "not_evaluated",
                    "relevance": relevance or "not_evaluated",
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
                "abstention": abstention,
                "faithfulness": faithfulness,
                "completeness": completeness,
                "transparency": transparency,
                "relevance": relevance,
                "input_tokens": cobbie_input_tokens + verifier_input_tokens,
                "output_tokens": cobbie_output_tokens + verifier_output_tokens,
                "cobbie_input_tokens": cobbie_input_tokens,
                "cobbie_output_tokens": cobbie_output_tokens,
                "verifier_input_tokens": verifier_input_tokens,
                "verifier_output_tokens": verifier_output_tokens,
                "mlflow_run_id": question_run.info.run_id,
            }


# ============================================================================
# BASELINE MODE FUNCTION
# ============================================================================


def process_question_baseline(
    question_data,
    question_index: int,
    args,
) -> Dict:
    """Process a single question using the baseline (static summary) approach.

    Args:
        question_data: Dataset question object
        question_index: Index of the question
        args: Command line arguments

    Returns:
        Dictionary containing question processing results
    """
    from analysis.baseline_qa.baseline_bim_qas import baseline_bim_qas

    question = question_data.question
    ground_truth = getattr(question_data, "answer", "") or getattr(
        question_data, "ground_truth", ""
    )
    category = getattr(question_data, "category", None)
    question_id = getattr(question_data, "id", f"q_{question_index + 1}")
    ifc_path = question_data.ifc.model_path if question_data.ifc else None

    # Skip question if category is not provided
    if category is None:
        error_msg = f"ERROR: Question {question_id} missing required 'category' field. SKIPPING."
        logger.error(error_msg)
        return {
            "question": question,
            "ground_truth": ground_truth,
            "category": None,
            "status": "error",
            "error_message": "Missing required 'category' field",
            "execution_time": 0.0,
            "classification": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "mlflow_run_id": "skipped_no_category",
        }

    # Skip if no IFC path
    if ifc_path is None:
        error_msg = f"ERROR: Question {question_id} has no associated IFC model. SKIPPING."
        logger.error(error_msg)
        return {
            "question": question,
            "ground_truth": ground_truth,
            "category": category,
            "status": "error",
            "error_message": "No IFC model associated",
            "execution_time": 0.0,
            "classification": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "mlflow_run_id": "skipped_no_ifc",
        }

    logger.info(f"[BASELINE] Processing question {question_index + 1}: {question[:80]}...")

    run_name = f"question_{question_index}_{question_id}_baseline"

    with mlflow.start_run(run_name=run_name, nested=True) as question_run:
        client_info = CLIENT_INFO.get(args.client, {"model": args.client, "provider": "unknown"})
        mlflow.log_params(
            {
                "question": question,
                "ground_truth": ground_truth,
                "category": category,
                "question_id": question_id,
                "llm": client_info["model"],
                "provider_name": client_info["provider"],
                "model_path": ifc_path,
                "system": "baseline",
            }
        )

        with mlflow.start_span(name="BaselineQA", span_type="CHAIN") as question_span:
            question_span.set_attributes(
                {
                    "system": "baseline",
                    "model": client_info["model"],
                    "provider": client_info["provider"],
                }
            )

            start_time_baseline = time.time()

            # Get model summary for logging (before calling baseline_bim_qas)
            from analysis.baseline_qa.ifc_summary import get_or_create_summary
            model_summary = get_or_create_summary(ifc_path)

            # Log the summary in the span inputs for debugging
            question_span.set_inputs(
                {
                    "question": question,
                    "ground_truth": ground_truth,
                    "category": category,
                    "question_index": question_index + 1,
                    "model_path": ifc_path,
                    "model_summary": model_summary,  # Full summary for debugging
                }
            )

            # Run baseline QA
            final_answer, collector, execution_history = baseline_bim_qas(
                user_input=question,
                model_path=ifc_path,
                client=args.client,
            )
            baseline_duration = time.time() - start_time_baseline

            # Extract token usage from collector
            baseline_input_tokens = 0
            baseline_output_tokens = 0

            if collector and hasattr(collector, "usage") and collector.usage:
                usage = collector.usage
                baseline_input_tokens = usage.input_tokens or 0
                baseline_output_tokens = usage.output_tokens or 0

            # Run AnswerVerifier if we have a successful answer
            classification = None
            justification = None
            abstention = None
            faithfulness = None
            completeness = None
            transparency = None
            relevance = None
            verifier_input_tokens = 0
            verifier_output_tokens = 0
            verifier_duration = 0.0

            if final_answer.answer and ground_truth:
                verifier_start = time.time()
                verifier_result, verifier_collector = verify_answer(
                    question=question,
                    category=category,
                    ground_truth=ground_truth,
                    system_response=final_answer.answer,
                )
                verifier_duration = time.time() - verifier_start

                classification = derive_binary_classification(verifier_result)
                abstention = verifier_result.abstention
                faithfulness = verifier_result.faithfulness.value
                completeness = verifier_result.completeness.value
                transparency = verifier_result.transparency.value
                relevance = verifier_result.relevance.value
                justification = verifier_result.justification

                if verifier_collector and hasattr(verifier_collector, "usage") and verifier_collector.usage:
                    verifier_input_tokens = verifier_collector.usage.input_tokens or 0
                    verifier_output_tokens = verifier_collector.usage.output_tokens or 0

            # Log question-level metrics
            mlflow.log_metrics(
                {
                    "baseline_duration": baseline_duration,
                    "verifier_duration": verifier_duration,
                    "baseline_input_tokens": baseline_input_tokens,
                    "baseline_output_tokens": baseline_output_tokens,
                    "verifier_input_tokens": verifier_input_tokens,
                    "verifier_output_tokens": verifier_output_tokens,
                    "total_input_tokens": baseline_input_tokens + verifier_input_tokens,
                    "total_output_tokens": baseline_output_tokens + verifier_output_tokens,
                    "success": 1,
                }
            )

            question_outputs = {
                "status": "success",
                "execution_time": baseline_duration,
                "answer": final_answer.answer,
                "reasoning": final_answer.thoughts,
                "baseline_input_tokens": baseline_input_tokens,
                "baseline_output_tokens": baseline_output_tokens,
                "verifier_input_tokens": verifier_input_tokens,
                "verifier_output_tokens": verifier_output_tokens,
                "classification": classification,
            }

            question_span.set_outputs(question_outputs)
            question_span.set_status("OK")

            logger.info(
                f"[BASELINE] Question {question_index + 1} completed: classification={classification}, "
                f"duration={baseline_duration:.2f}s"
            )

            mlflow.log_params(
                {
                    "answer": final_answer.answer,
                    "classification": classification or "not_evaluated",
                    "justification": justification or "not_evaluated",
                    "abstention": str(abstention) if abstention is not None else "not_evaluated",
                    "faithfulness": faithfulness or "not_evaluated",
                    "completeness": completeness or "not_evaluated",
                    "transparency": transparency or "not_evaluated",
                    "relevance": relevance or "not_evaluated",
                }
            )

            return {
                "question": question,
                "ground_truth": ground_truth,
                "category": category,
                "status": "success",
                "answer": final_answer.answer,
                "reasoning": final_answer.thoughts,
                "execution_time": baseline_duration,
                "classification": classification,
                "justification": justification,
                "abstention": abstention,
                "faithfulness": faithfulness,
                "completeness": completeness,
                "transparency": transparency,
                "relevance": relevance,
                "input_tokens": baseline_input_tokens + verifier_input_tokens,
                "output_tokens": baseline_output_tokens + verifier_output_tokens,
                "baseline_input_tokens": baseline_input_tokens,
                "baseline_output_tokens": baseline_output_tokens,
                "verifier_input_tokens": verifier_input_tokens,
                "verifier_output_tokens": verifier_output_tokens,
                "mlflow_run_id": question_run.info.run_id,
            }


# ============================================================================
# MERGE MODE FUNCTIONS
# ============================================================================

# Easy to change: modify this list to experiment with different tool sets for the merger
MERGER_TOOL_DIRECTORIES: List[Literal["initial", "created", "manual"]] = ["initial", "created"]


def build_merge_prompt(
    original_question: str,
    answer_initial: str,
    thoughts_initial: str,
    answer_created: str,
    thoughts_created: str,
) -> str:
    """Build the prompt for the merger cobbie instance.

    Args:
        original_question: The original user question
        answer_initial: Answer from cobbie with initial tools only
        thoughts_initial: Reasoning from cobbie with initial tools only
        answer_created: Answer from cobbie with created tools
        thoughts_created: Reasoning from cobbie with created tools

    Returns:
        A formatted prompt for the merger to consolidate the answers
    """
    return f"""You are tasked with consolidating answers from two different system configurations.

## Original Question
{original_question}

## Answer A (from configuration with initial tools only)
**Reasoning:**
{thoughts_initial}

**Answer:**
{answer_initial}

## Answer B (from configuration with initial + created tools)
**Reasoning:**
{thoughts_created}

**Answer:**
{answer_created}

## Your Task
1. Compare both answers carefully, examining their reasoning chains
2. If the answers agree, confirm the consensus answer
3. If the answers disagree, use the available tools to verify which claims are correct
4. Provide the most accurate answer based on your analysis

Important: If both answers seem uncertain or contradictory and you cannot verify which is correct, you may indicate uncertainty. Focus on accuracy over confidence.

Now, please provide your consolidated answer to the original question."""


def process_question_merged(
    question_data,
    question_index: int,
    tools_initial: Dict[str, Callable],
    tools_created: Dict[str, Callable],
    tools_merger: Dict[str, Callable],
    args,
) -> Dict:
    """Process a single question using the merge flow with 3 cobbie calls.

    Flow:
    1. Run cobbie with initial tools only -> answer_initial
    2. Run cobbie with initial + created tools -> answer_created
    3. Run merger cobbie with all tools + consolidated prompt -> merged_answer
    4. Verify merged_answer against ground truth

    Args:
        question_data: Dataset question object
        question_index: Index of the question
        tools_initial: Dictionary of initial tools only
        tools_created: Dictionary of initial + created tools
        tools_merger: Dictionary of tools for the merger (typically all tools)
        args: Command line arguments

    Returns:
        Dictionary containing question processing results with merge metadata
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
        return {
            "question": question,
            "ground_truth": ground_truth,
            "category": None,
            "status": "error",
            "error_message": "Missing required 'category' field",
            "execution_time": 0.0,
            "classification": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "mlflow_run_id": "skipped_no_category",
            "merge_mode": True,
        }

    logger.info(f"[MERGE] Processing question {question_index + 1}: {question[:80]}...")

    run_name = f"question_{question_index}_{question_id}_merged"

    with mlflow.start_run(run_name=run_name, nested=True) as question_run:
        # Log question parameters
        client_info = CLIENT_INFO.get(args.client, {"model": args.client, "provider": "unknown"})
        mlflow.log_params(
            {
                "question": question,
                "ground_truth": ground_truth,
                "category": category,
                "question_id": question_id,
                "llm": client_info["model"],
                "provider_name": client_info["provider"],
                "model_path": ifc_path or "None",
                "merge_mode": True,
            }
        )

        # Initialize tracking variables
        total_input_tokens = 0
        total_output_tokens = 0
        total_duration = 0.0

        # ----------------------------------------------------------------
        # STEP 1: Run cobbie with initial tools only
        # ----------------------------------------------------------------
        with mlflow.start_span(name="config_initial", span_type="CHAIN") as span_initial:
            span_initial.set_inputs({"config": "initial", "question": question})
            start_initial = time.time()

            try:
                answer_initial_obj, collector_initial, history_initial = cobbie(
                    user_input=question,
                    tools=tools_initial,
                    model_path=ifc_path,
                    client=args.client,
                )
                duration_initial = time.time() - start_initial

                answer_initial = answer_initial_obj.answer
                thoughts_initial = answer_initial_obj.thoughts

                tokens_in_initial = 0
                tokens_out_initial = 0
                if collector_initial and hasattr(collector_initial, "usage") and collector_initial.usage:
                    tokens_in_initial = collector_initial.usage.input_tokens or 0
                    tokens_out_initial = collector_initial.usage.output_tokens or 0

                span_initial.set_outputs({
                    "answer": answer_initial,
                    "duration": duration_initial,
                    "input_tokens": tokens_in_initial,
                    "output_tokens": tokens_out_initial,
                })
                span_initial.set_status("OK")

                total_input_tokens += tokens_in_initial
                total_output_tokens += tokens_out_initial
                total_duration += duration_initial

                logger.info(f"[MERGE] Config initial completed in {duration_initial:.1f}s")

            except Exception as e:
                logger.error(f"[MERGE] Config initial failed: {e}")
                span_initial.set_status("ERROR")
                answer_initial = f"ERROR: {e}"
                thoughts_initial = ""
                duration_initial = time.time() - start_initial
                tokens_in_initial = 0
                tokens_out_initial = 0

        # ----------------------------------------------------------------
        # STEP 2: Run cobbie with initial + created tools
        # ----------------------------------------------------------------
        with mlflow.start_span(name="config_created", span_type="CHAIN") as span_created:
            span_created.set_inputs({"config": "initial+created", "question": question})
            start_created = time.time()

            try:
                answer_created_obj, collector_created, history_created = cobbie(
                    user_input=question,
                    tools=tools_created,
                    model_path=ifc_path,
                    client=args.client,
                )
                duration_created = time.time() - start_created

                answer_created = answer_created_obj.answer
                thoughts_created = answer_created_obj.thoughts

                tokens_in_created = 0
                tokens_out_created = 0
                if collector_created and hasattr(collector_created, "usage") and collector_created.usage:
                    tokens_in_created = collector_created.usage.input_tokens or 0
                    tokens_out_created = collector_created.usage.output_tokens or 0

                span_created.set_outputs({
                    "answer": answer_created,
                    "duration": duration_created,
                    "input_tokens": tokens_in_created,
                    "output_tokens": tokens_out_created,
                })
                span_created.set_status("OK")

                total_input_tokens += tokens_in_created
                total_output_tokens += tokens_out_created
                total_duration += duration_created

                logger.info(f"[MERGE] Config created completed in {duration_created:.1f}s")

            except Exception as e:
                logger.error(f"[MERGE] Config created failed: {e}")
                span_created.set_status("ERROR")
                answer_created = f"ERROR: {e}"
                thoughts_created = ""
                duration_created = time.time() - start_created
                tokens_in_created = 0
                tokens_out_created = 0

        # ----------------------------------------------------------------
        # STEP 3: Run merger cobbie to consolidate answers
        # ----------------------------------------------------------------
        with mlflow.start_span(name="merger", span_type="CHAIN") as span_merger:
            merge_prompt = build_merge_prompt(
                original_question=question,
                answer_initial=answer_initial,
                thoughts_initial=thoughts_initial,
                answer_created=answer_created,
                thoughts_created=thoughts_created,
            )
            span_merger.set_inputs({
                "config": "merger",
                "merge_prompt_length": len(merge_prompt),
                "answer_initial": answer_initial[:200],
                "answer_created": answer_created[:200],
            })
            start_merger = time.time()

            try:
                merged_answer_obj, collector_merger, history_merger = cobbie(
                    user_input=merge_prompt,
                    tools=tools_merger,
                    model_path=ifc_path,
                    client=args.client,
                )
                duration_merger = time.time() - start_merger

                merged_answer = merged_answer_obj.answer
                merged_thoughts = merged_answer_obj.thoughts

                tokens_in_merger = 0
                tokens_out_merger = 0
                if collector_merger and hasattr(collector_merger, "usage") and collector_merger.usage:
                    tokens_in_merger = collector_merger.usage.input_tokens or 0
                    tokens_out_merger = collector_merger.usage.output_tokens or 0

                span_merger.set_outputs({
                    "answer": merged_answer,
                    "duration": duration_merger,
                    "input_tokens": tokens_in_merger,
                    "output_tokens": tokens_out_merger,
                })
                span_merger.set_status("OK")

                total_input_tokens += tokens_in_merger
                total_output_tokens += tokens_out_merger
                total_duration += duration_merger

                logger.info(f"[MERGE] Merger completed in {duration_merger:.1f}s")

            except Exception as e:
                logger.error(f"[MERGE] Merger failed: {e}")
                span_merger.set_status("ERROR")
                merged_answer = f"ERROR: {e}"
                merged_thoughts = ""
                duration_merger = time.time() - start_merger
                tokens_in_merger = 0
                tokens_out_merger = 0

        # ----------------------------------------------------------------
        # STEP 4: Verify merged answer
        # ----------------------------------------------------------------
        classification = None
        justification = None
        abstention = None
        faithfulness = None
        completeness = None
        transparency = None
        relevance = None
        verifier_input_tokens = 0
        verifier_output_tokens = 0
        verifier_duration = 0.0

        if merged_answer and not merged_answer.startswith("ERROR:") and ground_truth:
            verifier_start = time.time()
            verifier_result, verifier_collector = verify_answer(
                question=question,
                category=category,
                ground_truth=ground_truth,
                system_response=merged_answer,
            )
            verifier_duration = time.time() - verifier_start

            classification = derive_binary_classification(verifier_result)
            abstention = verifier_result.abstention
            faithfulness = verifier_result.faithfulness.value
            completeness = verifier_result.completeness.value
            transparency = verifier_result.transparency.value
            relevance = verifier_result.relevance.value
            justification = verifier_result.justification

            if verifier_collector and hasattr(verifier_collector, "usage") and verifier_collector.usage:
                verifier_input_tokens = verifier_collector.usage.input_tokens or 0
                verifier_output_tokens = verifier_collector.usage.output_tokens or 0

            total_input_tokens += verifier_input_tokens
            total_output_tokens += verifier_output_tokens
            total_duration += verifier_duration

        # Check if answers agreed
        answers_agreed = answer_initial.strip() == answer_created.strip()

        # Log all metrics
        mlflow.log_metrics({
            # Per-config metrics
            "config_initial_duration": duration_initial,
            "config_initial_input_tokens": tokens_in_initial,
            "config_initial_output_tokens": tokens_out_initial,
            "config_created_duration": duration_created,
            "config_created_input_tokens": tokens_in_created,
            "config_created_output_tokens": tokens_out_created,
            "merger_duration": duration_merger,
            "merger_input_tokens": tokens_in_merger,
            "merger_output_tokens": tokens_out_merger,
            # Verifier metrics
            "verifier_duration": verifier_duration,
            "verifier_input_tokens": verifier_input_tokens,
            "verifier_output_tokens": verifier_output_tokens,
            # Totals
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "cobbie_duration": total_duration - verifier_duration,
            "success": 1,
            "answers_agreed": 1 if answers_agreed else 0,
        })

        # Log answers as params
        mlflow.log_params({
            "answer_initial": answer_initial[:500] if answer_initial else "N/A",
            "answer_created": answer_created[:500] if answer_created else "N/A",
            "answer": merged_answer[:500] if merged_answer else "N/A",
            "classification": classification or "not_evaluated",
            "justification": justification[:500] if justification else "not_evaluated",
            "answers_agreed": str(answers_agreed),
        })

        logger.info(
            f"[MERGE] Question {question_index + 1} completed: "
            f"classification={classification}, agreed={answers_agreed}, "
            f"duration={total_duration:.1f}s"
        )

        return {
            "question": question,
            "ground_truth": ground_truth,
            "category": category,
            "status": "success",
            "answer": merged_answer,
            "reasoning": merged_thoughts,
            "execution_time": total_duration,
            "classification": classification,
            "justification": justification,
            "abstention": abstention,
            "faithfulness": faithfulness,
            "completeness": completeness,
            "transparency": transparency,
            "relevance": relevance,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "mlflow_run_id": question_run.info.run_id,
            # Merge-specific fields
            "merge_mode": True,
            "answers_agreed": answers_agreed,
            "answer_initial": answer_initial,
            "answer_created": answer_created,
            "config_initial_duration": duration_initial,
            "config_created_duration": duration_created,
            "merger_duration": duration_merger,
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
        eval_stats, key=lambda s: s.questions_when_called or 0, reverse=True
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
    print(
        f"{'TOTAL':<{tool_col_width}} │ {total_included:>8} │ {total_called:>7} │ {total_correct:>8} │ {total_wrong:>7} │ {'':>9}"
    )
    print("=" * 90)


def main():
    """Main function to run the evaluation."""
    parser = argparse.ArgumentParser(
        description="Run evaluation experiments on Cobbie",
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

    parser.add_argument(
        "--client",
        type=str,
        default="GLM_4_7",
        choices=["GLM_4_7", "GLM_4_5_air", "Devstral", "Gemini_2_5_Flash_Lite"],
        help="Client to use for evaluation (default: GLM_4_7)",
    )

    parser.add_argument(
        "--tools",
        nargs="+",
        choices=["initial", "created", "manual"],
        default=["initial", "created"],
        help="Tool directories to load (space-separated). Options: initial, created, manual. Default: initial created"
    )

    parser.add_argument(
        "--system",
        choices=["cobbie", "baseline"],
        default="cobbie",
        help="QA system to evaluate: 'cobbie' (agentic, default) or 'baseline' (static summary)"
    )

    parser.add_argument(
        "--no-tools",
        action="store_true",
        help="Run evaluation without any tools (baseline test)"
    )

    parser.add_argument(
        "--merge",
        action="store_true",
        help="Enable merging mode: run cobbie with initial tools, then with created tools, then consolidate answers"
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

    # Validate mutually exclusive options
    if args.merge and args.no_tools:
        print("Error: --merge and --no-tools are mutually exclusive")
        return 1

    if args.system == "baseline" and args.merge:
        print("Error: --system baseline and --merge are mutually exclusive")
        return 1

    if args.system == "baseline" and args.no_tools:
        print("Note: --no-tools is ignored when --system baseline (baseline doesn't use tools)")
        args.no_tools = False

    # Validate and deduplicate tools argument
    if args.merge:
        # In merge mode, we use both initial and created tools (hardcoded)
        args.tools = ["initial", "created"]
        logger.info("Merge mode: using initial and created tool directories")
    elif args.no_tools:
        args.tools = []
    elif not args.tools:
        print("Error: At least one tool directory must be specified (or use --no-tools)")
        return 1
    else:
        # Remove duplicates while preserving order
        seen = set()
        unique_tools = []
        for tool_dir in args.tools:
            if tool_dir not in seen:
                seen.add(tool_dir)
                unique_tools.append(tool_dir)
        args.tools = unique_tools

    end_index = min(args.start + args.nb_samples, len(DEVSET))
    actual_samples = end_index - args.start

    print(
        f"Processing {actual_samples} samples from index {args.start} to {end_index - 1}"
    )
    if args.no_tools:
        logger.info("Running in no-tools mode (baseline test)")
    else:
        logger.info(f"Loading tools from directories: {', '.join(args.tools)}")

    # Setup logging level - reconfigure loguru if non-default level specified
    if args.log_level != "INFO":
        from pathlib import Path

        logger.remove()  # Remove default handlers
        # Re-add console handler with new level
        logger.add(
            sys.stderr,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            level=args.log_level,
            colorize=True,
        )
        # Re-add file handler with new level
        log_dir = Path(ROOT_PATH) / "src" / "db" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "cobbie.log",
            rotation="10 MB",
            retention=5,
            level=args.log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        )

    # Handle tool metrics reset
    if args.reset_tool_metrics:
        deleted_count = clear_eval_tool_stats()
        logger.info(f"Cleared {deleted_count} evaluation tool metric entries")

    # Setup MLflow tracking URI and experiment
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("Evaluation")

    # Prepare tools for COBBIE based on mode
    if args.system == "baseline":
        # Baseline mode: no tools needed
        tools_dict = {}
        tools_initial = {}
        tools_created = {}
        tools_merger = {}
        logger.info("[BASELINE] No tools loaded (static summary mode)")
    elif args.merge:
        # Merge mode: load separate tool sets for each config
        try:
            tools_initial = get_tools(
                directories=["initial"],
                allow_created_deletion=True
            )
            tools_created = get_tools(
                directories=["initial", "created"],
                allow_created_deletion=True
            )
            tools_merger = get_tools(
                directories=MERGER_TOOL_DIRECTORIES,
                allow_created_deletion=True
            )
            logger.info(f"[MERGE] Loaded tools - initial: {len(tools_initial)}, created: {len(tools_created)}, merger: {len(tools_merger)}")
            # For compatibility with non-merge code paths
            tools_dict = tools_merger
        except Exception as e:
            logger.error(f"Failed to load tools for merge mode: {e}")
            return 1
    elif args.no_tools:
        tools_dict = {}
        tools_initial = {}
        tools_created = {}
        tools_merger = {}
        logger.info("No tools loaded (baseline mode)")
    else:
        try:
            # Cast is safe here because argparse choices ensures valid values
            tools_dirs = cast(List[Literal["initial", "created", "manual"]], args.tools)
            tools_dict = get_tools(
                directories=tools_dirs,
                allow_created_deletion=True
            )
            logger.info(f"Loaded {len(tools_dict)} total tools from directories: {', '.join(args.tools)}")
            # Not used in non-merge mode, but set for type consistency
            tools_initial = tools_dict
            tools_created = tools_dict
            tools_merger = tools_dict
        except Exception as e:
            logger.error(f"Failed to load tools: {e}")
            return 1

    # Prepare dataset
    dataset = DEVSET[args.start : end_index]
    logger.info(f"Using {len(dataset)} samples for evaluation")

    # Determine run_id based on --continue flag
    run_id = determine_evaluation_run_id(args.continue_run)

    if run_id:
        logger.info(f"Continuing existing MLflow run: {run_id}")
        run_name = None  # Don't set a new name when continuing
    else:
        if args.system == "baseline":
            mode_suffix = "_BASELINE"
        elif args.merge:
            mode_suffix = "_MERGE"
        else:
            mode_suffix = ""
        run_name = f"Evaluation{mode_suffix}_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
        logger.info(f"Creating new MLflow run: {run_name}")

    # Start MLflow run
    with mlflow.start_run(run_id=run_id, run_name=run_name) as run:
        current_run_id = run.info.run_id
        logger.info(f"MLflow run started with ID: {current_run_id}")

        # Log immutable configuration parameters (only for new runs)
        if run_id is None:
            component_name = "BaselineQA" if args.system == "baseline" else "COBBIE"
            client_info = CLIENT_INFO.get(args.client, {"model": args.client, "provider": "unknown"})
            params = {
                "model_name": client_info["model"],
                "provider_name": client_info["provider"],
                "component": component_name,
                "system": args.system,
                "tools": ", ".join(tools_dict.keys()) if tools_dict else "none",
                "tools_count": len(tools_dict),
                "merge_mode": str(args.merge),
            }
            if args.merge:
                params["tools_initial_count"] = len(tools_initial)
                params["tools_created_count"] = len(tools_created)
                params["tools_merger_count"] = len(tools_merger)
            mlflow.log_params(params)

        # Get previous metrics if continuing
        previous_metrics: Optional[Dict] = None
        if run_id is not None:
            active_run = mlflow.active_run()
            if active_run:
                previous_metrics = {
                    "total_questions": int(
                        active_run.data.metrics.get("total_questions", 0)
                    ),
                    "correct_count": int(
                        active_run.data.metrics.get("correct_count", 0)
                    ),
                    "wrong_count": int(active_run.data.metrics.get("wrong_count", 0)),
                    "abstained_count": int(
                        active_run.data.metrics.get("abstained_count", 0)
                    ),
                    "total_input_tokens": int(
                        active_run.data.metrics.get("total_input_tokens", 0)
                    ),
                    "total_output_tokens": int(
                        active_run.data.metrics.get("total_output_tokens", 0)
                    ),
                    "total_execution_time": float(
                        active_run.data.metrics.get("total_execution_time", 0.0)
                    ),
                    # Criterion-level counts
                    "abstention_count": int(
                        active_run.data.metrics.get("abstention_count", 0)
                    ),
                    "faithfulness_yes_count": int(
                        active_run.data.metrics.get("faithfulness_yes_count", 0)
                    ),
                    "faithfulness_no_count": int(
                        active_run.data.metrics.get("faithfulness_no_count", 0)
                    ),
                    "faithfulness_na_count": int(
                        active_run.data.metrics.get("faithfulness_na_count", 0)
                    ),
                    "completeness_yes_count": int(
                        active_run.data.metrics.get("completeness_yes_count", 0)
                    ),
                    "completeness_no_count": int(
                        active_run.data.metrics.get("completeness_no_count", 0)
                    ),
                    "completeness_na_count": int(
                        active_run.data.metrics.get("completeness_na_count", 0)
                    ),
                    "transparency_yes_count": int(
                        active_run.data.metrics.get("transparency_yes_count", 0)
                    ),
                    "transparency_no_count": int(
                        active_run.data.metrics.get("transparency_no_count", 0)
                    ),
                    "transparency_na_count": int(
                        active_run.data.metrics.get("transparency_na_count", 0)
                    ),
                    "relevance_yes_count": int(
                        active_run.data.metrics.get("relevance_yes_count", 0)
                    ),
                    "relevance_no_count": int(
                        active_run.data.metrics.get("relevance_no_count", 0)
                    ),
                    "relevance_na_count": int(
                        active_run.data.metrics.get("relevance_na_count", 0)
                    ),
                }
                logger.info(f"Continuing run with previous metrics: {previous_metrics}")

        # Time the evaluation
        start_time = time.time()

        # Process each question (each creates its own MLflow run)
        question_results = []
        model_name = CLIENT_INFO.get(args.client, {"model": args.client})["model"]
        if args.system == "baseline":
            desc = f"Evaluating Baseline QA {model_name}"
        elif args.merge:
            desc = f"Evaluating COBBIE {model_name} [MERGE]"
        else:
            desc = f"Evaluating COBBIE {model_name}"

        with tqdm(total=len(dataset), desc=desc) as pbar:
            for i, question_data in enumerate(dataset):
                if args.system == "baseline":
                    result = process_question_baseline(
                        question_data=question_data,
                        question_index=args.start + i,
                        args=args,
                    )
                elif args.merge:
                    result = process_question_merged(
                        question_data=question_data,
                        question_index=args.start + i,
                        tools_initial=tools_initial,
                        tools_created=tools_created,
                        tools_merger=tools_merger,
                        args=args,
                    )
                else:
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
        results_summary = calculate_and_log_metrics(question_results, args.client, previous_metrics)
        results_summary["total_evaluation_time"] = total_evaluation_time

        # Log batch tracking metrics
        batch_metrics = {
            "batch_start_index": args.start,
            "batch_end_index": end_index - 1,
            "batch_size": len(dataset),
        }
        mlflow.log_metrics(batch_metrics)

        # Log additional info to main run
        component_tag = "BaselineQA" if args.system == "baseline" else "COBBIE"
        mlflow.set_tag("evaluation_status", "completed")
        mlflow.set_tag("component", component_tag)
        mlflow.set_tag("system", args.system)
        mlflow.set_tag("total_evaluation_time", total_evaluation_time)
        mlflow.set_tag("individual_question_traces", "true")
        mlflow.set_tag("merge_mode", str(args.merge))

        logger.info("Evaluation completed successfully")
        logger.info(f"Success rate: {results_summary['success_rate']:.3f}")
        logger.info(f"Accuracy: {results_summary['accuracy']:.3f}")
        logger.info(f"Total evaluation time: {total_evaluation_time:.1f}s")
        logger.info(f"Individual question traces created: {len(question_results)}")

        # Print results
        print_results(results_summary)

        # Print tool metrics summary (not applicable for baseline)
        if args.track_tools and args.system != "baseline":
            print_tool_metrics_summary()

    print("\nEvaluation completed successfully!")
    return 0


if __name__ == "__main__":
    exit(main())
