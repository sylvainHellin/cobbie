from pydantic import BaseModel
from typing import Optional, Literal, Dict, Any


class Result(BaseModel):
    function_implementation: Optional[str] = None
    assessment_status: Optional[Literal["ok", "needs_improvement"]] = None
    assessment_details: Optional[str] = None
    need_new_function: Optional[bool] = None
    answer: Optional[str] = None
    reasoning: Optional[str] = None
    trajectory: Optional[Dict[str, Any]] = None
    similarity_score: Optional[float] = None
    function_name: Optional[str] = None
