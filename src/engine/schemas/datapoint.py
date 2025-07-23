from pydantic import BaseModel


class QA_Pair(BaseModel):
    id: int
    question: str
    answer: str
    project_name: str
    ifc_model_name: str
    ifc_model_path: str
    ifc_model_description: str
