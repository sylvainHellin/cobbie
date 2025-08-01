"""Request and response models for the IFC Answer Engine API."""

from typing import Optional
from pydantic import BaseModel, Field


class QuestionRequest(BaseModel):
    """Request model for asking questions about BIM models."""

    question: str = Field(..., description="The question to ask about the BIM model")
    model_id: int = Field(..., description="The ID of the BIM model to query", gt=0)


class QuestionResponse(BaseModel):
    """Response model for question answers."""

    status: str = Field(
        ..., description="Status of the operation ('success' or 'error')"
    )
    answer: Optional[str] = Field(
        None, description="The answer to the question if successful"
    )
    error_msg: Optional[str] = Field(
        None, description="Error message if status is 'error'"
    )
    model_info: Optional[dict] = Field(
        None, description="Information about the BIM model used"
    )
