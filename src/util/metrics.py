from typing import List, Optional, Tuple

import mlflow
from baml_py.baml_py import Collector

from src.agents.answer_verifier import derive_binary_classification
from src.config import LOG_LEVEL
from src.schemas.training_context import Context
from src.util import get_logger

# Initialize logger
_logger = get_logger(name="TrainingPhase", log_level=LOG_LEVEL)


def extract_token_metrics(collector: Optional[Collector]) -> Tuple[int, int, int]:
    """
    Safely extract token metrics from collector.

    Args:
        collector: BAML Collector object with token usage info

    Returns:
        Tuple of (input_tokens, output_tokens, total_tokens)
    """
    if not collector:
        return 0, 0, 0

    try:
        if hasattr(collector, "usage") and collector.usage:
            usage = collector.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            total_tokens = input_tokens + output_tokens
            return input_tokens, output_tokens, total_tokens
    except Exception as e:
        _logger.warning(f"Error extracting token usage: {e}")

    return 0, 0, 0


def log_qa_metrics(context: Context) -> dict:
    """
    Extract and log metrics for a single QA pair to MLflow.

    Args:
        context: Context object with all agent results

    Returns:
        Dictionary with metrics for aggregate calculation
    """
    # Extract token metrics from all collectors
    cobbie_input, cobbie_output, cobbie_total = extract_token_metrics(
        context.cobbie_collector
    )
    verify_input, verify_output, verify_total = extract_token_metrics(
        context.verify_collector
    )
    identify_tool_input, identify_tool_output, identify_tool_total = (
        extract_token_metrics(context.identify_tool_collector)
    )
    create_tool_input, create_tool_output, create_tool_total = extract_token_metrics(
        context.create_tool_collector
    )
    identify_faulty_input, identify_faulty_output, identify_faulty_total = (
        extract_token_metrics(context.identify_faulty_collector)
    )
    debug_tool_input, debug_tool_output, debug_tool_total = extract_token_metrics(
        context.debug_tool_collector
    )

    # NEW: Extract test and assessment metrics
    test_cobbie_input, test_cobbie_output, test_cobbie_total = extract_token_metrics(
        context.test_cobbie_collector
    )
    test_verify_input, test_verify_output, test_verify_total = extract_token_metrics(
        context.test_verify_collector
    )
    tool_assess_input, tool_assess_output, tool_assess_total = extract_token_metrics(
        context.tool_assessment_collector
    )

    # Calculate totals (including new components)
    total_tokens = (
        cobbie_total
        + verify_total
        + identify_tool_total
        + create_tool_total
        + identify_faulty_total
        + debug_tool_total
        + test_cobbie_total
        + test_verify_total
        + tool_assess_total
    )
    total_duration = (
        context.cobbie_duration
        + context.verify_duration
        + context.identify_tool_duration
        + context.create_tool_duration
        + context.identify_faulty_duration
        + context.debug_tool_duration
        + context.test_cobbie_duration
        + context.test_verify_duration
        + context.tool_assessment_duration
    )

    # Get classification (derive from multi-criteria evaluation)
    classification = (
        derive_binary_classification(context.verify_result)
        if context.verify_result
        else "unknown"
    )

    # Build metrics dictionary
    metrics = {
        "cobbie_duration": context.cobbie_duration,
        "cobbie_input_tokens": cobbie_input,
        "cobbie_output_tokens": cobbie_output,
        "cobbie_total_tokens": cobbie_total,
        "verify_duration": context.verify_duration,
        "verify_input_tokens": verify_input,
        "verify_output_tokens": verify_output,
        "verify_total_tokens": verify_total,
        "total_tokens": total_tokens,
        "total_duration": total_duration,
        "answer_correct": 1 if classification == "correct" else 0,
        "answer_wrong": 1 if classification == "wrong" else 0,
        "answer_abstained": 1 if classification == "abstained" else 0,
        "tool_created": 1 if context.tool_created else 0,
        "tool_updated": 1 if context.tool_updated else 0,
        "tool_saved": 1 if context.tool_saved else 0,  # NEW
        "error": 1 if context.error_message else 0,
    }

    # Add Path A metrics if applicable
    if context.identify_tool_result:
        metrics.update(
            {
                "identify_tool_duration": context.identify_tool_duration,
                "identify_tool_input_tokens": identify_tool_input,
                "identify_tool_output_tokens": identify_tool_output,
                "identify_tool_total_tokens": identify_tool_total,
            }
        )

    if context.create_tool_result:
        metrics.update(
            {
                "create_tool_duration": context.create_tool_duration,
                "create_tool_input_tokens": create_tool_input,
                "create_tool_output_tokens": create_tool_output,
                "create_tool_total_tokens": create_tool_total,
            }
        )

    # Add Path B metrics if applicable
    if context.identify_faulty_result:
        metrics.update(
            {
                "identify_faulty_duration": context.identify_faulty_duration,
                "identify_faulty_input_tokens": identify_faulty_input,
                "identify_faulty_output_tokens": identify_faulty_output,
                "identify_faulty_total_tokens": identify_faulty_total,
            }
        )

    if context.debug_tool_result:
        metrics.update(
            {
                "debug_tool_duration": context.debug_tool_duration,
                "debug_tool_input_tokens": debug_tool_input,
                "debug_tool_output_tokens": debug_tool_output,
                "debug_tool_total_tokens": debug_tool_total,
            }
        )

    # NEW: Add tool testing metrics if applicable
    if context.test_cobbie_result:
        metrics.update(
            {
                "test_cobbie_duration": context.test_cobbie_duration,
                "test_cobbie_input_tokens": test_cobbie_input,
                "test_cobbie_output_tokens": test_cobbie_output,
                "test_cobbie_total_tokens": test_cobbie_total,
                "test_verify_duration": context.test_verify_duration,
                "test_verify_input_tokens": test_verify_input,
                "test_verify_output_tokens": test_verify_output,
                "test_verify_total_tokens": test_verify_total,
            }
        )

    # NEW: Add tool assessment metrics if applicable
    if context.tool_assessment:
        metrics.update(
            {
                "tool_assessment_duration": context.tool_assessment_duration,
                "tool_assessment_input_tokens": tool_assess_input,
                "tool_assessment_output_tokens": tool_assess_output,
                "tool_assessment_total_tokens": tool_assess_total,
                "tool_was_used": 1 if context.tool_assessment.tool_was_used else 0,
                "tool_usage_helpful": 1
                if context.tool_assessment.tool_usage_quality == "helpful"
                else 0,
                "tool_usage_harmful": 1
                if context.tool_assessment.tool_usage_quality == "harmful"
                else 0,
                "tool_recommendation_keep": 1
                if context.tool_assessment.recommendation == "keep_tool"
                else 0,
                "tool_recommendation_discard": 1
                if context.tool_assessment.recommendation == "discard_tool"
                else 0,
            }
        )

    # Log to MLflow
    mlflow.log_metrics(metrics)

    # Return dictionary for aggregate calculation
    result_dict = {
        "question_id": context.qa_pair.id,
        "classification": classification,
        "tool_created": context.tool_created,
        "tool_updated": context.tool_updated,
        "tool_saved": context.tool_saved,
        "error": bool(context.error_message),
        "total_tokens": total_tokens,
        "total_duration": total_duration,
        # Tool assessment data
        "tool_was_tested": bool(context.tool_assessment),
        "tool_recommendation": context.tool_assessment.recommendation
        if context.tool_assessment
        else None,
        "tool_usage_quality": context.tool_assessment.tool_usage_quality
        if context.tool_assessment
        else None,
    }

    # Add 5-criterion evaluation data
    if context.verify_result:
        result_dict.update(
            {
                "abstention": context.verify_result.abstention,
                "faithfulness": str(context.verify_result.faithfulness),
                "completeness": str(context.verify_result.completeness),
                "transparency": str(context.verify_result.transparency),
                "relevance": str(context.verify_result.relevance),
            }
        )

    return result_dict


def calculate_aggregate_metrics(qa_results: List[dict]) -> dict:
    """
    Calculate aggregate metrics across all QA pairs.

    Args:
        qa_results: List of dictionaries with per-QA metrics

    Returns:
        Dictionary with aggregate metrics
    """
    total_count = len(qa_results)
    if total_count == 0:
        return {}

    correct_count = sum(1 for r in qa_results if r.get("classification") == "correct")
    wrong_count = sum(1 for r in qa_results if r.get("classification") == "wrong")
    abstained_count = sum(
        1 for r in qa_results if r.get("classification") == "abstained"
    )

    tools_created = sum(1 for r in qa_results if r.get("tool_created"))
    tools_updated = sum(1 for r in qa_results if r.get("tool_updated"))
    tools_saved = sum(1 for r in qa_results if r.get("tool_saved"))
    tools_tested = sum(1 for r in qa_results if r.get("tool_was_tested"))
    tools_kept = sum(
        1 for r in qa_results if r.get("tool_recommendation") == "keep_tool"
    )
    tools_discarded = sum(
        1 for r in qa_results if r.get("tool_recommendation") == "discard_tool"
    )
    errors = sum(1 for r in qa_results if r.get("error"))

    total_tokens = sum(r.get("total_tokens", 0) for r in qa_results)
    total_duration = sum(r.get("total_duration", 0) for r in qa_results)

    # Calculate criterion-level aggregates
    abstention_count = sum(1 for r in qa_results if r.get("abstention"))

    faithfulness_yes = sum(1 for r in qa_results if r.get("faithfulness") == "Yes")
    faithfulness_no = sum(1 for r in qa_results if r.get("faithfulness") == "No")
    faithfulness_na = sum(1 for r in qa_results if r.get("faithfulness") == "Na")

    completeness_yes = sum(1 for r in qa_results if r.get("completeness") == "Yes")
    completeness_no = sum(1 for r in qa_results if r.get("completeness") == "No")
    completeness_na = sum(1 for r in qa_results if r.get("completeness") == "Na")

    transparency_yes = sum(1 for r in qa_results if r.get("transparency") == "Yes")
    transparency_no = sum(1 for r in qa_results if r.get("transparency") == "No")
    transparency_na = sum(1 for r in qa_results if r.get("transparency") == "Na")

    relevance_yes = sum(1 for r in qa_results if r.get("relevance") == "Yes")
    relevance_no = sum(1 for r in qa_results if r.get("relevance") == "No")
    relevance_na = sum(1 for r in qa_results if r.get("relevance") == "Na")

    return {
        "total_qa_pairs": total_count,
        "correct_answers": correct_count,
        "wrong_answers": wrong_count,
        "abstained_answers": abstained_count,
        "tools_created": tools_created,
        "tools_updated": tools_updated,
        "tools_saved": tools_saved,
        "tools_tested": tools_tested,
        "tools_kept": tools_kept,
        "tools_discarded": tools_discarded,
        "errors": errors,
        "success_rate": correct_count / total_count if total_count > 0 else 0,
        "tool_creation_rate": tools_created / correct_count if correct_count > 0 else 0,
        "tool_update_rate": tools_updated / wrong_count if wrong_count > 0 else 0,
        "tool_save_rate": tools_saved / tools_tested if tools_tested > 0 else 0,
        "tool_keep_rate": tools_kept / tools_tested if tools_tested > 0 else 0,
        "avg_tokens_per_qa": total_tokens / total_count if total_count > 0 else 0,
        "avg_duration_per_qa": total_duration / total_count if total_count > 0 else 0,
        "total_tokens": total_tokens,
        "total_duration": total_duration,
        # Criterion-level counts
        "abstention_count": abstention_count,
        "faithfulness_yes_count": faithfulness_yes,
        "faithfulness_no_count": faithfulness_no,
        "faithfulness_na_count": faithfulness_na,
        "completeness_yes_count": completeness_yes,
        "completeness_no_count": completeness_no,
        "completeness_na_count": completeness_na,
        "transparency_yes_count": transparency_yes,
        "transparency_no_count": transparency_no,
        "transparency_na_count": transparency_na,
        "relevance_yes_count": relevance_yes,
        "relevance_no_count": relevance_no,
        "relevance_na_count": relevance_na,
        # Criterion-level rates (yes / (yes + no))
        "abstention_rate": abstention_count / total_count if total_count > 0 else 0,
        "faithfulness_rate": faithfulness_yes / (faithfulness_yes + faithfulness_no)
        if (faithfulness_yes + faithfulness_no) > 0
        else 0,
        "completeness_rate": completeness_yes / (completeness_yes + completeness_no)
        if (completeness_yes + completeness_no) > 0
        else 0,
        "transparency_rate": transparency_yes / (transparency_yes + transparency_no)
        if (transparency_yes + transparency_no) > 0
        else 0,
        "relevance_rate": relevance_yes / (relevance_yes + relevance_no)
        if (relevance_yes + relevance_no) > 0
        else 0,
    }
