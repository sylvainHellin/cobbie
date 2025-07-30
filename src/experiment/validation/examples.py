from typing import List
from src.engine.schemas import QA_Pair
from src.engine.util import load_train_dev_split
from dspy import Example


def create_examples(qa_pairs: List[QA_Pair]) -> List[Example]:
    """
    transform the custom type into example for dspy optimization.
    """
    examples: List[Example] = []
    for qa in qa_pairs:
        example = Example(
            question=qa.question,
            answer=qa.answer,
            path_ifc_model=qa.ifc_model_path,
        ).with_inputs(
            "question",
            "path_ifc_model",
        )
        examples.append(example)

    return examples


train, dev = load_train_dev_split()
TRAINSET = create_examples(train)
DEVSET = create_examples(dev)
