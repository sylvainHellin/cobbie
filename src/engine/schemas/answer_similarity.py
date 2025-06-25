from typing import Optional, Literal

from pydantic import BaseModel


class AnswerSimilarity(BaseModel):
    correct: Optional[bool] = None
    similarity_score: Optional[float] = None
    reasoning: Optional[str] = None
    status: Optional[Literal["success", "error"]] = None
    error_msg: Optional[str] = None
