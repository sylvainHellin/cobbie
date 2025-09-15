from typing import cast
from dspy import Example

from src.engine.components import AnswerVerifier
from src.engine.schemas import ModuleOutput


def metric(
    example: Example,
    output: ModuleOutput,
    trace=None,
) -> float:
    """
    Evaluate the similarity between the ground truth of a QA pair and the provided answer.
    Output a float between 0 and 1.
    """
    answer_verifier = AnswerVerifier()
    output = cast(
        ModuleOutput,
        answer_verifier(
            question=example.question or "",
            first_answer=example.answer or "",
            second_answer=output.result.answer or "",
        ),
    )
    return output.result.similarity_score or 0
