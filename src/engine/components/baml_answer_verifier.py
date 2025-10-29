"""
BAML-based answer verification functions.
Provides classification, justification, and confidence for answer evaluation.
"""

from typing import Literal, Optional, Tuple

from baml_client import b
from baml_client.types import AnswerEvaluationResult, QuestionCategory

from src.config import LOG_LEVEL
from src.engine.schemas.outputs import LM_Metrics
from src.engine.util import get_logger
from src.engine.util.baml_common import run_baml_function_with_metrics

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
    bim_context: Optional[str] = "BIM model containing building information"
) -> AnswerEvaluationResult:
    """
    Evaluate an answer against ground truth using BAML EvaluateResponse function.

    Args:
        question: The question being answered
        category: Question category (1, 2, 3, or 4)
        ground_truth: The ground truth answer
        system_response: The system's answer to evaluate
        bim_context: Optional context about the BIM model

    Returns:
        AnswerEvaluationResult containing classification, justification, and confidence
    """
    _logger.info("Starting BAML answer verification")
    _logger.debug(
        f"\nQuestion: {question}\nCategory: {category}\nGround truth: {ground_truth}\nSystem response: {system_response}"
    )

    try:
        # Map category to BAML enum
        baml_category = _map_category_to_baml(category)

        # Call BAML EvaluateResponse function with metrics collection
        baml_result, collector = run_baml_function_with_metrics(
            component_name="AnswerVerifier",
            baml_function=b.EvaluateResponse,
            question=question,
            category=baml_category,
            ground_truth=ground_truth,
            system_response=system_response,
            bim_context=bim_context
        )

        _logger.info(
            f"BAML answer verification completed: classification={baml_result.classification}, "
            f"confidence={baml_result.confidence}"
        )

        return baml_result

    except Exception as e:
        error_msg = f"Exception during BAML answer verification: {e}"
        _logger.error(error_msg)
        raise


def verify_answer_with_metrics(
    question: str,
    category: Literal[1, 2, 3, 4],
    ground_truth: str,
    system_response: str,
    bim_context: Optional[str] = "BIM model containing building information",
    mlflow: bool = True
) -> Tuple[AnswerEvaluationResult, LM_Metrics]:
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
    _logger.info("Starting BAML answer verification with metrics")
    _logger.debug(
        f"\nQuestion: {question}\nCategory: {category}\nGround truth: {ground_truth}\nSystem response: {system_response}"
    )

    try:
        # Create MLflow orchestration span if requested
        if mlflow:
            import mlflow
            with mlflow.start_span(name="BamlAnswerVerifier", span_type="CHAIN") as verifier_span:
                verifier_span.set_inputs({
                    "question": question,
                    "category": category,
                    "ground_truth": ground_truth,
                    "system_response": system_response,
                    "bim_context": bim_context
                })

                try:
                    # Map category to BAML enum
                    baml_category = _map_category_to_baml(category)

                    # Call BAML EvaluateResponse function with metrics collection
                    baml_result, collector = run_baml_function_with_metrics(
                        component_name="AnswerVerifier",
                        baml_function=b.EvaluateResponse,
                        question=question,
                        category=baml_category,
                        ground_truth=ground_truth,
                        system_response=system_response,
                        bim_context=bim_context
                    )

                    # Extract token usage from collector
                    usage = collector.last.usage if collector.last else None
                    input_tokens = usage.input_tokens if usage else 0
                    output_tokens = usage.output_tokens if usage else 0

                    # Create LM_Metrics instance
                    lm_metrics = LM_Metrics(
                        input_tokens=input_tokens or 0,
                        output_tokens=output_tokens or 0,
                        llm="zai-glm-4.6",  # TODO: Extract this from collector or config
                        cost=None  # Cost calculation not available from BAML collector
                    )

                    _logger.info(
                        f"BAML answer verification with metrics completed: classification={baml_result.classification}, "
                        f"confidence={baml_result.confidence}, input_tokens={input_tokens}, output_tokens={output_tokens}"
                    )

                    # Set MLflow span outputs and status
                    verifier_span.set_outputs({
                        "classification": baml_result.classification,
                        "justification": baml_result.justification,
                        "confidence": baml_result.confidence,
                        "input_tokens": lm_metrics.input_tokens,
                        "output_tokens": lm_metrics.output_tokens,
                        "status": "success"
                    })
                    verifier_span.set_status("OK")

                    return baml_result, lm_metrics

                except Exception as inner_e:
                    # Set MLflow span error status
                    verifier_span.set_outputs({
                        "error": str(inner_e),
                        "status": "error"
                    })
                    verifier_span.set_status("ERROR")
                    raise inner_e
        else:
            # Run without MLflow orchestration span
            # Map category to BAML enum
            baml_category = _map_category_to_baml(category)

            # Call BAML EvaluateResponse function with metrics collection
            baml_result, collector = run_baml_function_with_metrics(
                component_name="AnswerVerifier",
                baml_function=b.EvaluateResponse,
                question=question,
                category=baml_category,
                ground_truth=ground_truth,
                system_response=system_response,
                bim_context=bim_context
            )

            # Extract token usage from collector
            usage = collector.last.usage if collector.last else None
            input_tokens = usage.input_tokens if usage else 0
            output_tokens = usage.output_tokens if usage else 0

            # Create LM_Metrics instance
            lm_metrics = LM_Metrics(
                input_tokens=input_tokens or 0,
                output_tokens=output_tokens or 0,
                llm="zai-glm-4.6",  # TODO: Extract this from collector or config
                cost=None  # Cost calculation not available from BAML collector
            )

            _logger.info(
                f"BAML answer verification with metrics completed: classification={baml_result.classification}, "
                f"confidence={baml_result.confidence}, input_tokens={input_tokens}, output_tokens={output_tokens}"
            )

            return baml_result, lm_metrics

    except Exception as e:
        error_msg = f"Exception during BAML answer verification with metrics: {e}"
        _logger.error(error_msg)
        raise


if __name__ == "__main__":
    import mlflow

    # Try to set up MLflow tracking, but don't fail if server is not available
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("BamlAnswerVerifier")

    # Test the functional answer verifier
    result = verify_answer(
        question="How many doors are there in this house?",
        category=1,
        ground_truth="There are 120 doors in this house.",
        system_response="I could count 123 doors.",
        bim_context="Residential building model with door and window elements"
    )

    print("BAML Answer Verifier Test Results:")
    print(f"Classification: {result.classification}")
    print(f"Justification: {result.justification}")
    print(f"Confidence: {result.confidence}")

    # Test the functional answer verifier with metrics
    result_with_metrics, metrics = verify_answer_with_metrics(
        question="How many doors are there in this house?",
        category=1,
        ground_truth="There are 120 doors in this house.",
        system_response="I could count 123 doors.",
        bim_context="Residential building model with door and window elements"
    )

    print("\nBAML Answer Verifier with Metrics Test Results:")
    print(f"Classification: {result_with_metrics.classification}")
    print(f"Justification: {result_with_metrics.justification}")
    print(f"Confidence: {result_with_metrics.confidence}")
    print(f"Input Tokens: {metrics.input_tokens}")
    print(f"Output Tokens: {metrics.output_tokens}")
    print(f"LLM: {metrics.llm}")