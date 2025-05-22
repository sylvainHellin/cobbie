import dspy
from config import LANGUAGE_MODELS, LLM
from datetime import datetime
import time
from db.db import LogRow, insert_new_log


class AnswerVerifierSignature(dspy.Signature):
    """
    Compare a given answer with the ground truth and assess if it is correct.
    Tolerance thresholds for numerical values (quantities, measurements, etc.): up to 2%.
    """

    question: str = dspy.InputField(desc="A user's question related to IFC models.")
    answer: str = dspy.InputField(desc="The answer to verify.")
    ground_truth: str = dspy.InputField(
        desc="The ground truth to compare the answer to."
    )

    answer_is_correct: bool = dspy.OutputField(
        desc="""
    Compare the given answer with the ground truth and judge whether it is correct:
    - True -> The answer provided is close enough to the ground truth and doesnot contain conflicting factual information.
    - False -> The answer provided differs too much from the ground truth or contains incorrect factual information.
    """
    )
    confidence: float = dspy.OutputField(
        desc="Confidence score between 0 and 1 for the judgement's correctness."
    )


class AnswerVerifier(dspy.Module):
    """
    Check an answer to a given question against the ground truth to assess if it is correct.
    """

    def __init__(self):
        super().__init__()
        self.classifier = dspy.ChainOfThought(AnswerVerifierSignature)

    def forward(self, question: str, answer: str, ground_truth: str) -> dspy.Prediction:
        """
        Check an answer to a given question against the ground truth to assess if it is correct.

        Args:
            question: The question being answered
            answer: The answer to verify
            ground_truth: The ground truth for this question

        Returns:
            dspy.Prediction containing answer_is_correct and confidence
        """
        try:
            return self.classifier(
                question=question, answer=answer, ground_truth=ground_truth
            )
        except Exception as e:
            print(
                f"Encounter Exception during the forward pass of the AnswerClassifier\nException:{e}\nquestion:{question}\nanswe:{answer}\nground truth:{ground_truth}"
            )
            return dspy.Prediction(
                answer_classification=False,
                confidence=0.0,
            )


def verify_answer(
    question: str,
    answer: str,
    ground_truth: str,
    run_id: int = 0,
    llm_info: LLM = LANGUAGE_MODELS["llama4-scout-cerebras"],
) -> tuple[bool, float]:
    """
    Verify if an answer matches the ground truth for a given question.

    Args:
        question (str): The question being answered
        answer (str): The answer to verify
        ground_truth (str): The correct answer to compare against
        run_id (int, optional): Identifier for the verification run. Defaults to 0.
        llm_info (LLM, optional): Language model configuration. Defaults to gemini-flash.

    Returns:
        tuple[bool, float]: A tuple containing:
            - bool: Whether the answer is considered correct
            - float: Confidence score (0-1) for the verification
    """
    start_time = time.time()

    lm = dspy.LM(model=llm_info.url, api_key=llm_info.api_key)
    dspy.configure(lm=lm)

    answer_verifier = AnswerVerifier()
    answer_verification: dspy.Prediction = answer_verifier.forward(
        question=question, answer=answer, ground_truth=ground_truth
    )

    answer_is_correct: bool = answer_verification.get("answer_is_correct") or False
    verification_confidence = answer_verification.get("confidence") or 0.0

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
        model_output=f"Answer verification result: {answer_is_correct} with confidence {verification_confidence}",
        action_input_code=f"Question: {question}\nAnswer: {answer}\nGround Truth: {ground_truth}",
        action_output=str((answer_is_correct, verification_confidence)),
        duration=duration,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    insert_new_log(log_entry)

    return (answer_is_correct, verification_confidence)


if __name__ == "__main__":
    (answer_is_correct, verification_confidence) = verify_answer(
        question="How many doors are there in this house ?",
        answer="I could count 13 doors in this house.",
        ground_truth="There are 12 doors in this house.",
    )

    print(
        f"Answer is correct: {answer_is_correct}\nConfidence score:{verification_confidence}\n"
    )
