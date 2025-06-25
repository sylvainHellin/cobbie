import dspy
from src.config import LANGUAGE_MODELS, LLM
from datetime import datetime
import time
from src.experiment.db.db import LogRow, insert_new_log
from src.engine.schemas.module_output import ModuleOutput
from src.engine.schemas.answer_similarity import AnswerSimilarity
from src.engine.util.get_logger import get_logger
from src.config import LOG_LEVEL
import mlflow


class AnswerVerifierSignature(dspy.Signature):
    """
    Compare two answers to the same question and give them a similarity score from 0 to 1 (0 meaning the answers are completely different, 1 meaning they are identical).
    Tolerance thresholds for numerical values (quantities, measurements, etc.): up to 2%.
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

    def __init__(self):
        super().__init__()
        self.classifier = dspy.ChainOfThought(AnswerVerifierSignature)

    def forward(
        self, question: str, first_answer: str, second_answer: str
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

        module_output = ModuleOutput(status="error")

        with mlflow.start_span(name="AnswerVerifier"):
            try:
                prediction = self.classifier(
                    question=question,
                    first_answer=first_answer,
                    second_answer=second_answer,
                )
                module_output.status = "success"
                module_output.result = prediction
                logger.debug(
                    f"\nSimilarity score: {prediction.similarity_score}\nReasoning: {prediction.reasoning}"
                )
            except Exception as e:
                error_msg = f"Encounter Exception during the forward pass of the AnswerClassifier\nException:{e}\nquestion:{question}\nfirst_answer:{first_answer}\nground truth:{second_answer}"
                logger.error(error_msg)
                module_output.error_msg = error_msg

        return module_output


def verify_answer(
    question: str,
    first_answer: str,
    second_answer: str,
    threshold: float,
    run_id: int = 0,
    llm_info: LLM = LANGUAGE_MODELS["llama4-scout-cerebras"],
) -> AnswerSimilarity:
    """
    Compare two answers to the same question and compute their similarity.

    Args:
        question (str): The question being answered
        first_answer (str): The first answer to compare
        second_answer (str): The second answer to compare
        threshold (float): The similarity threshold above which answers are considered correct
        run_id (int, optional): Identifier for the verification run. Defaults to 0.
        llm_info (LLM, optional): Language model configuration. Defaults to llama4-scout-cerebras.

    Returns:
        AnswerSimilarity: Object containing:
            - correct (bool): Whether the similarity score meets or exceeds the threshold
            - similarity (float): Similarity score (0-1) between the two answers
    """
    lm = dspy.LM(model=llm_info.url, api_key=llm_info.api_key)
    dspy.configure(lm=lm)

    start_time = time.time()
    logger = get_logger("verify_answer")

    try:
        answer_verifier = AnswerVerifier()
        answer_verification: ModuleOutput = answer_verifier.forward(
            question=question,
            first_answer=first_answer,
            second_answer=second_answer,
        )
    except Exception as e:
        logger.error(f"MLflow not available. Exception: {e}")
        # If MLflow is not available, run without it
        answer_verifier = AnswerVerifier()
        answer_verification: ModuleOutput = answer_verifier.forward(
            question=question,
            first_answer=first_answer,
            second_answer=second_answer,
        )

    # Extract similarity score from the result
    if answer_verification.status == "success" and answer_verification.result:
        similarity_score = getattr(answer_verification.result, "similarity_score", 0.0)
        reasoning = getattr(
            answer_verification.result, "reasoning", "No reasoning trace available."
        )

        # Determine if answers are correct based on threshold
        correct = similarity_score >= threshold

        # Calculate duration and get token counts from LM history
        duration = time.time() - start_time

        # Get token counts from the last LM call in history
        history: list[dict] = lm.history or [{}]
        input_tokens = history[-1].get("usage", {}).get("prompt_tokens", 0)
        output_tokens = history[-1].get("usage", {}).get("completion_tokens", 0)

        # Create and insert log entry
        log_entry = LogRow(
            run_id=run_id,
            agent_name="AnswerVerifier",
            step_number=-1,
            timestamp=datetime.now(),
            model_output=f"Answer similarity result: {correct} with similarity score {similarity_score}",
            action_input_code=f"Question: {question}\nFirst Answer: {first_answer}\nSecond Answer: {second_answer}",
            action_output=str(
                AnswerSimilarity(
                    correct=correct,
                    similarity_score=similarity_score,
                    reasoning=reasoning,
                )
            ),
            duration=duration,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        insert_new_log(log_entry)

        return AnswerSimilarity(
            correct=correct,
            similarity_score=similarity_score,
            reasoning=reasoning,
        )
    else:
        return AnswerSimilarity(status="error", error_msg=answer_verification.error_msg)


if __name__ == "__main__":
    # Try to set up MLflow tracking, but don't fail if server is not available
    try:
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("AnswerVerifier")
        print("MLflow tracking enabled")
    except Exception as e:
        print(f"MLflow tracking not available: {e}")
        print("Continuing without MLflow tracking...")

    result = verify_answer(
        question="How many doors are there in this house ?",
        first_answer="I could count 123 doors in this house.",
        second_answer="There are 120 doors in this house.",
        threshold=0.8,
        # llm_info=LANGUAGE_MODELS["qwen3-30b-ollama"],
    )
    print(
        f"Answer is correct: {result.correct}\nSimilarity score: {result.similarity_score}\n"
    )

    print("END")
