"""
Agent that verify the provided answers align with the one from the dataset.
Provides classification, justification, and confidence for answer evaluation.
"""

import time
from typing import Literal, Tuple

import mlflow
from baml_py.baml_py import Collector

from src.baml.baml_client import b
from src.baml.baml_client.types import AnswerEvaluationResult, CriterionResult, QuestionCategory
from src.schemas.agent_error import AgentError
from src.util.baml_retry import call_baml_with_retry


def _map_category_to_baml(category: Literal[1, 2, 3, 4]) -> QuestionCategory:
    """Map category number to BAML QuestionCategory enum."""
    category_mapping = {
        1: QuestionCategory.Category1,
        2: QuestionCategory.Category2,
        3: QuestionCategory.Category3,
        4: QuestionCategory.Category4,
    }
    return category_mapping[category]


def derive_binary_classification(
    result: AnswerEvaluationResult,
) -> Literal["correct", "wrong", "abstained"]:
    """
    Derive binary classification from multi-criteria evaluation for backward compatibility.

    This function maps the 5-criterion evaluation (abstention, faithfulness, completeness,
    transparency, relevance) back to the legacy 3-class classification system used by
    training and evaluation scripts.

    Classification logic:
    - "abstained": System explicitly declined to answer (abstention = True)
    - "correct": Answer provided AND all 4 criteria satisfied (Yes)
    - "wrong": Answer provided but fails any criterion

    Args:
        result: AnswerEvaluationResult with 5-criterion evaluation

    Returns:
        Binary classification: "correct", "wrong", or "abstained"
    """
    if result.abstention:
        return "abstained"
    elif (
        result.faithfulness == CriterionResult.Yes
        and result.completeness == CriterionResult.Yes
        and result.transparency == CriterionResult.Yes
        and result.relevance == CriterionResult.Yes
    ):
        return "correct"
    else:
        return "wrong"


def verify_answer(
    question: str,
    category: Literal[1, 2, 3, 4],
    ground_truth: str,
    system_response: str,
    llm_provider: str = "zai",
    llm_name: str = "GLM-4.7",
    **kwargs,
) -> Tuple[AnswerEvaluationResult | AgentError, Collector]:
    """
    Evaluate an answer and return both result and usage metrics.

    Args:
        question: The question being answered
        category: Question category (1, 2, 3, or 4)
        ground_truth: The ground truth answer
        system_response: The system's answer to evaluate
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

    # Add collector to kwargs for BAML calls (merge with any caller-provided baml_options)
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
            }
        )

        # Map category to BAML enum
        baml_category = _map_category_to_baml(category)

        # Classify the answer
        baml_options = kwargs.pop("baml_options", {})
        answer_classification = call_baml_with_retry(
            lambda: b.with_options(**baml_options).EvaluateResponse(
                question=question,
                category=baml_category,
                ground_truth=ground_truth,
                system_response=system_response,
                **kwargs,
            ),
            context_name="EvaluateResponse",
        )

        if isinstance(answer_classification, AgentError):
            return answer_classification, collector

        # Log outputs
        verifier_span.set_outputs(
            {
                "abstention": answer_classification.abstention,
                "faithfulness": str(answer_classification.faithfulness),
                "completeness": str(answer_classification.completeness),
                "transparency": str(answer_classification.transparency),
                "relevance": str(answer_classification.relevance),
                "justification": answer_classification.justification,
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
    )

    print("BAML Answer Verifier Test Results:")
    if isinstance(result, AgentError):
        print(f"Error: {result.error_message}")
    else:
        print(f"Abstention: {result.abstention}")
        print(f"Faithfulness: {result.faithfulness}")
        print(f"Completeness: {result.completeness}")
        print(f"Transparency: {result.transparency}")
        print(f"Relevance: {result.relevance}")
        print(f"Justification: {result.justification}")
        print(f"Derived Classification: {derive_binary_classification(result)}")

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
    )

    print("\nBAML Answer Verifier with Metrics Test Results:")
    if isinstance(result_with_metrics, AgentError):
        print(f"Error: {result_with_metrics.error_message}")
    else:
        print(f"Abstention: {result_with_metrics.abstention}")
        print(f"Faithfulness: {result_with_metrics.faithfulness}")
        print(f"Completeness: {result_with_metrics.completeness}")
        print(f"Transparency: {result_with_metrics.transparency}")
        print(f"Relevance: {result_with_metrics.relevance}")
        print(f"Justification: {result_with_metrics.justification}")
        print(f"Derived Classification: {derive_binary_classification(result_with_metrics)}")
    print(f"Input Tokens: {input_tokens}")
    print(f"Output Tokens: {output_tokens}")
