from src.engine.components import AnswerVerifier
from src.engine.schemas import QA_Pair


def metric(qa_pair: QA_Pair, answer: str) -> float:
    """
    Evaluate the similarity between the ground truth of a QA pair and the provided answer.
    Output a float between 0 and 1.
    """
    answer_verifier = AnswerVerifier()
    output = answer_verifier.forward(
        question=qa_pair.question,
        first_answer=qa_pair.answer,
        second_answer=answer,
    )
    return output.result.similarity_score or 0
