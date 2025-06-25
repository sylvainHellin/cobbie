from pydantic import BaseModel


class Datapoint(BaseModel):
    id: int
    question: str
    answer: str
    project_name: str
    ifc_model_name: str
    ifc_model_path: str
    ifc_model_description: str
