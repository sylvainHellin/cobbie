"""
BAML-based answer verification functions.
Provides classification, justification, and confidence for answer evaluation.
"""

import time
from typing import Literal, Optional, Tuple

import mlflow
from baml_py.baml_py import Collector

from baml_client import b
from baml_client.types import AnswerEvaluationResult, QuestionCategory
from src.config import LOG_LEVEL
from src.engine.util import get_logger

# Initialize logger for the functional approach
_logger = get_logger(name="baml_answer_verifier", log_level=LOG_LEVEL)


def _map_category_to_baml(category: Literal[1, 2, 3, 4]) -> QuestionCategory:
    """Map category number to BAML QuestionCategory enum."""
    category_mapping = {
        1: QuestionCategory.Category1,
        2: QuestionCategory.Category2,
        3: QuestionCategory.Category3,
        4: QuestionCategory.Category4,
    }
    return category_mapping[category]


def verify_answer(
    question: str,
    category: Literal[1, 2, 3, 4],
    ground_truth: str,
    system_response: str,
    bim_context: Optional[str] = "BIM model containing building information",
    llm_provider: str = "zai",
    llm_name: str = "GLM-4.6",
    **kwargs,
) -> Tuple[AnswerEvaluationResult, Collector]:
    """
    Evaluate an answer and return both result and usage metrics.

    Args:
        question: The question being answered
        category: Question category (1, 2, 3, or 4)
        ground_truth: The ground truth answer
        system_response: The system's answer to evaluate
        bim_context: Optional context about the BIM model
        mlflow: Whether to create MLflow orchestration spans (default: True)

    Returns:
        Tuple of (AnswerEvaluationResult, LM_Metrics) where LM_Metrics contains:
        - input_tokens: Input token usage
        - output_tokens: Output token usage
        - llm: Model identifier
        - cost: Calculated cost (if available)
    """
    # Start timer
    start = time.time()

    # Create collector for token tracking
    collector = Collector(name="AnswerVerifier")

    # Add collector to kwargs for BAML calls
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
        kwargs["baml_options"]["collector"] = collector

    with mlflow.start_span(name="AnswerVerifier", span_type="LLM") as verifier_span:
        verifier_span.set_inputs(
            {
                "question": question,
                "category": category,
                "ground_truth": ground_truth,
                "system_response": system_response,
                "bim_context": bim_context,
            }
        )

        # Map category to BAML enum
        baml_category = _map_category_to_baml(category)

        # Classify the answer
        try:
            answer_classification = b.with_options(
                **kwargs.pop("baml_options", {})
            ).EvaluateResponse(
                question=question,
                category=baml_category,
                ground_truth=ground_truth,
                system_response=system_response,
                bim_context=bim_context,
                **kwargs,
            )
        except Exception as e:
            answer_classification = AnswerEvaluationResult(
                classification="abstained",
                justification=f"An Exception occured when trying to classify this answer. Exception:\n{e}",
                confidence="low",
            )

        # Log outputs
        verifier_span.set_outputs(
            {
                "classification": answer_classification.classification,
                "justification": answer_classification.justification,
                "confidence": answer_classification.confidence,
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

        # Log metrics
        verifier_span.set_attributes(
            {
                "duration": duration,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "llm_provider": llm_provider,
                "llm_name": llm_name,
            }
        )

        return answer_classification, collector


if __name__ == "__main__":
    import mlflow

    # Try to set up MLflow tracking, but don't fail if server is not available
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("AnswerVerifier")

    # Test the functional answer verifier
    result, collector = verify_answer(
        question="How many doors are there in this house?",
        category=1,
        ground_truth="There are 120 doors in this house.",
        system_response="I could count 123 doors.",
        bim_context="Residential building model with door and window elements",
    )

    print("BAML Answer Verifier Test Results:")
    print(f"Classification: {result.classification}")
    print(f"Justification: {result.justification}")
    print(f"Confidence: {result.confidence}")

    # Extract metrics
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0

    if collector and hasattr(collector, "usage") and collector.usage:
        usage = collector.usage
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
        total_tokens = input_tokens + output_tokens

    # Test the functional answer verifier with metrics
    result_with_metrics, metrics = verify_answer(
        question="How many doors are there in this house?",
        category=1,
        ground_truth="There are 120 doors in this house.",
        system_response="I could count 123 doors.",
        bim_context="Residential building model with door and window elements",
    )

    print("\nBAML Answer Verifier with Metrics Test Results:")
    print(f"Classification: {result_with_metrics.classification}")
    print(f"Justification: {result_with_metrics.justification}")
    print(f"Confidence: {result_with_metrics.confidence}")
    print(f"Input Tokens: {input_tokens}")
    print(f"Output Tokens: {output_tokens}")
