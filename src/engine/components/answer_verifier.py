import dspy
import mlflow

from src.config import AGENT_CONFIGS, LOG_LEVEL
from src.engine.schemas import ModuleOutput
from src.engine.util.get_logger import get_logger


class AnswerVerifierSignature(dspy.Signature):
    """
    Compare two answers to the same question and give them a similarity score between 0 and 1, where 0 means the answers are completely different and 1 means they are identical.

    The tolerance threshold for numerical values (quantities, measurements, etc.) is up to 2%.

    If both answers state that the information is not available in the BIM model, the similarity score should be high (at least 0.85). This applies even if one answer provides additional relevant information that does not come directly from the BIM model. A lower score is only acceptable if the additional relevant information provided by the two answers completely diverges.
    """

    question: str = dspy.InputField()
    first_answer: str = dspy.InputField()
    second_answer: str = dspy.InputField()

    similarity_score: float = dspy.OutputField(
        desc="""
        The similarity score between the two answers to the same question. The result should be a number between 0 and 1. 0 means the answer is completely different, and 1 means they are the same. The tolerance thresholds for numerical values (quantities, measurements, etc.) are up to 2%. If the answers show more differences than this limit, the similarity score should reflect that.

    """
    )


class AnswerVerifier(dspy.Module):
    """
    Compare two answers with each other and compute a similarity score.
    """

    def __init__(self, config=None):
        super().__init__()
        # Use provided config or default to AGENT_CONFIGS.answer_verifier
        self.config = config or AGENT_CONFIGS.answer_verifier

        # Set up LLM from config
        self.lm = self.config.llm.get_llm()
        self.classifier = dspy.ChainOfThought(AnswerVerifierSignature)
        dspy.configure(lm=self.lm)

    def forward(
        self,
        question: str,
        first_answer: str,
        second_answer: str,
    ) -> ModuleOutput:
        """
        Check an answer to a given question against the ground truth to assess if it is correct.

        Args:
            question: The question being answered
            first_answer: The first answer to the question
            second_answer: The second answer to the question to compare

        Returns:
            dspy.Prediction containing similarity_score (float).
        """
        logger = get_logger(name="AnswerVerifier", log_level=LOG_LEVEL)
        logger.info("Starting the AnswerVerifier.")
        logger.debug(
            f"\nQuestion: {question}\nFirst answer: {first_answer}\nSecond answer: {second_answer}"
        )

        self.output = ModuleOutput(status="error")

        with dspy.context(lm=self.lm):
            try:
                prediction = self.classifier(
                    question=question,
                    first_answer=first_answer,
                    second_answer=second_answer,
                )
                self.output.result.similarity_score = getattr(
                    prediction, "similarity_score", None
                )
                self.output.result.reasoning = getattr(prediction, "reasoning", None)
                if (
                    self.output.result.similarity_score is not None
                    and self.output.result.reasoning is not None
                ):
                    self.output.status = "success"
                    logger.debug(
                        f"\nSimilarity score: {self.output.result.similarity_score}\nReasoning: {self.output.result.reasoning}"
                    )
            except Exception as e:
                error_msg = f"Encounter Exception during the forward pass of the AnswerClassifier\nException:{e}\nquestion:{question}\nfirst_answer:{first_answer}\nground truth:{second_answer}"
                logger.error(error_msg)
                self.output.error_msg = error_msg

            finally:
                self.output.update_cost(
                    lm=self.lm,
                    cost_input_tokens=self.config.llm.cost_input_token,
                    cost_output_tokens=self.config.llm.cost_output_token,
                )

        return self.output


if __name__ == "__main__":
    from typing import cast

    # Try to set up MLflow tracking, but don't fail if server is not available
    mlflow.dspy.autolog()  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("AnswerVerifier")

    dspy.configure_cache(enable_disk_cache=False)

    answer_verifier = AnswerVerifier()

    output = cast(
        ModuleOutput,
        answer_verifier(
            question="How many doors are there in this house ?",
            first_answer="I could count 123 doors.",
            second_answer="There are 120 doors in this house.",
        ),
    )

    print(output.model_dump_json(indent=2))
