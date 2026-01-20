"""
Agent that assesses helper function usage.
Analyzes Cobbie execution history to determine if a specific helper function was useful.
"""

import time
from typing import Literal, Tuple

import mlflow
from baml_py.baml_py import Collector
from loguru import logger

from src.baml.baml_client import b
from src.baml.baml_client.types import HelperFunctionAssessment

from src.util import setup_logger

setup_logger()

def assess_helper_function(
    execution_history: str,
    original_question: str,
    ground_truth_answer: str,
    tested_tool_name: str,
    tested_tool_description: str,
    final_answer: str,
    answer_correctness: Literal["correct", "wrong", "abstained"],
    llm_provider: str = "zai",
    llm_name: str = "GLM-4.6",
    **kwargs,
) -> Tuple[HelperFunctionAssessment, Collector]:
    """
    Assess whether a specific helper function was useful during execution.

    Similar to identify_faulty_tool but focuses on tool utility rather than faults.
    Analyzes execution history to determine if a newly created or debugged tool
    should be kept, discarded, or improved.

    Args:
        execution_history: Complete execution history from Cobbie (thoughts, code, results, final answer)
        original_question: The original question (without enhancement) that was being answered
        ground_truth_answer: The correct/expected answer to the question
        tested_tool_name: Name of the helper function being assessed
        tested_tool_description: Description of what the helper function is supposed to do
        final_answer: The final answer provided by Cobbie
        answer_correctness: Classification from answer verifier ("correct", "wrong", or "abstained")
        llm_provider: LLM provider name for logging (default: "zai")
        llm_name: LLM model name for logging (default: "GLM-4.6")
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (HelperFunctionAssessment, Collector) where HelperFunctionAssessment contains:
        - thoughts: Detailed analysis of tool usage
        - tool_was_used: Whether the tool was actually called
        - tool_usage_quality: helpful | not_used | ignored | misused | harmful
        - usage_details: Detailed explanation of usage patterns
        - recommendation: keep_tool | discard_tool | improve_tool | unclear
        - confidence: high | medium | low
    """
    # Start timer
    start = time.time()

    # Create collector for token tracking
    collector = Collector(name="HelperFunctionAssessor")

    # Add collector to kwargs for BAML calls
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    with mlflow.start_span(
        name="HelperFunctionAssessor", span_type="LLM"
    ) as assessor_span:
        assessor_span.set_inputs(
            {
                "original_question": original_question,
                "tested_tool_name": tested_tool_name,
                "tested_tool_description": tested_tool_description,
                "answer_correctness": answer_correctness,
            }
        )

        # Assess helper function usage
        try:
            assessment = b.with_options(
                **kwargs.pop("baml_options", {})
            ).HelperFunctionAssessor(
                execution_history=execution_history,
                original_question=original_question,
                ground_truth_answer=ground_truth_answer,
                tested_tool_name=tested_tool_name,
                tested_tool_description=tested_tool_description,
                final_answer=final_answer,
                answer_correctness=answer_correctness,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"Error assessing helper function: {e}")
            assessment = HelperFunctionAssessment(
                thoughts=f"An Exception occurred when trying to assess helper function. Exception:\n{e}",
                tool_was_used=False,
                tool_usage_quality="not_used",
                usage_details="Error occurred during assessment",
                recommendation="unclear",
                confidence="low",
            )

        # Log outputs
        assessor_span.set_outputs(
            {
                "thoughts": assessment.thoughts,
                "tool_was_used": assessment.tool_was_used,
                "tool_usage_quality": assessment.tool_usage_quality,
                "recommendation": assessment.recommendation,
                "confidence": assessment.confidence,
            }
        )

        # Calculate metrics
        duration = time.time() - start
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0

        if collector.last:
            usage = collector.last.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            total_tokens = input_tokens + output_tokens

        # Set span attributes
        assessor_span.set_attributes(
            {
                "llm_provider": llm_provider,
                "llm_name": llm_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "duration": duration,
            }
        )

        logger.info(
            f"Helper function assessment completed. Recommendation: {assessment.recommendation}, "
            f"Confidence: {assessment.confidence}, Tokens: {total_tokens}, Duration: {duration:.2f}s"
        )

        return assessment, collector


# Export for use in other modules
__all__ = ["assess_helper_function"]
