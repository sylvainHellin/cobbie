from typing import Literal, Optional

from pydantic import BaseModel

from src.engine.schemas.result import Result


class ModuleOutput(BaseModel):
    result: Result = Result()
    status: Literal["error", "success"]
    error_msg: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    llm: Optional[str] = None
