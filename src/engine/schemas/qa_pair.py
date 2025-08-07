from pydantic import BaseModel
from dspy import Example


class QA_Pair(BaseModel):
    id: int
    question: str
    answer: str
    project_name: str
    ifc_model_name: str
    ifc_model_path: str
    ifc_model_description: str

    def to_example(self) -> Example:
        """
        Transform the custom type into dspy.Example for dspy optimization.
        """
        example = Example(
            question=self.question,
            answer=self.answer,
            path_ifc_model=self.ifc_model_path,
            question_id=self.id,
        ).with_inputs(
            "question",
            "path_ifc_model",
        )

        return example
