from typing import Optional
from pydantic import BaseModel

from src.engine.schemas import ModuleOutput
from src.engine.schemas.datapoint import QA_Pair

from mlflow.entities import Span


class TrainingContext(BaseModel):
    """Context data shared between state machine steps in TrainingModule."""

    # Core data
    qa_pair: Optional[QA_Pair] = None
    span: Optional[Span] = None

    # Module outputs
    engine_output: ModuleOutput = ModuleOutput(status="error")
    verifier_output: ModuleOutput = ModuleOutput(status="error")
    tool_identifier_output: ModuleOutput = ModuleOutput(status="error")

    class Config:
        # Allow OpenTelemetry span objects which aren't Pydantic models
        arbitrary_types_allowed = True

    def clear(self) -> None:
        """Clear all context data - equivalent to dict.clear()"""
        self.qa_pair = None
        self.span = None
        self.engine_output = ModuleOutput(status="error")
        self.verifier_output = ModuleOutput(status="error")
        self.tool_identifier_output = ModuleOutput(status="error")
