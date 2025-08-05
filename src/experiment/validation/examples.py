from typing import List
from src.engine.schemas import QA_Pair
from src.engine.util import load_train_dev_split
from dspy import Example


class QA_Example(Example):
    question: str
    answer: str
    path_ifc_model: str
    question_id: int


def create_examples(qa_pairs: List[QA_Pair]) -> List[QA_Example]:
    """
    transform the custom type into example for dspy optimization.
    """
    examples: List[QA_Example] = []
    for qa in qa_pairs:
        example = QA_Example(
            question=qa.question,
            answer=qa.answer,
            path_ifc_model=qa.ifc_model_path,
            question_id=qa.id,
        ).with_inputs(
            "question",
            "path_ifc_model",
        )
        examples.append(example)

    return examples


train, dev = load_train_dev_split()
TRAINSET = create_examples(train)
DEVSET = create_examples(dev)
