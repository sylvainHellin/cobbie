"""
BAML-based AnswerVerifier that directly uses the EvaluateResponse function.
Provides classification, justification, and confidence for answer evaluation.
"""

from typing import Literal, Optional

from baml_client import b
from baml_client.types import AnswerEvaluationResult, QuestionCategory

from src.config import AGENT_CONFIGS, LOG_LEVEL
from src.engine.util import get_logger
from src.engine.util.baml_common import run_baml_function_with_metrics


class BamlAnswerVerifier:
    """
    BAML-based answer verifier that uses the EvaluateResponse function directly.
    Returns classification, justification, and confidence from the BAML evaluation.
    """

    def __init__(self, config=None):
        # Use provided config or default to AGENT_CONFIGS.answer_verifier
        self.config = config or AGENT_CONFIGS.answer_verifier
        self.logger = get_logger(name="BamlAnswerVerifier", log_level=LOG_LEVEL)

    def _map_category_to_baml(self, category: Literal[1, 2, 3, 4]) -> QuestionCategory:
        """Map category number to BAML QuestionCategory enum."""
        category_mapping = {
            1: QuestionCategory.Category1,
            2: QuestionCategory.Category2,
            3: QuestionCategory.Category3,
            4: QuestionCategory.Category4,
        }
        return category_mapping[category]

    def forward(
        self,
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
        self.logger.info("Starting BamlAnswerVerifier evaluation")
        self.logger.debug(
            f"\nQuestion: {question}\nCategory: {category}\nGround truth: {ground_truth}\nSystem response: {system_response}"
        )

        try:
            # Map category to BAML enum
            baml_category = self._map_category_to_baml(category)

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

            self.logger.info(
                f"BamlAnswerVerifier completed: classification={baml_result.classification}, "
                f"confidence={baml_result.confidence}"
            )

            return baml_result

        except Exception as e:
            error_msg = f"Exception during BamlAnswerVerifier evaluation: {e}"
            self.logger.error(error_msg)
            raise


if __name__ == "__main__":
    import mlflow

    # Try to set up MLflow tracking, but don't fail if server is not available
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("BamlAnswerVerifier")

    # Create BAML answer verifier
    answer_verifier = BamlAnswerVerifier()

    # Test the answer verifier
    result = answer_verifier(
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