from pydantic import BaseModel
from typing import Optional, Literal


class Result(BaseModel):
    python_code: Optional[str] = None
    assessment_status: Optional[Literal["ok", "needs_improvement"]] = None
    assessment_details: Optional[str] = None
