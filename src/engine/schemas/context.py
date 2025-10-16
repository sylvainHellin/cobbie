from typing import Optional
from pydantic import BaseModel

from .outputs import ModuleOutput
from ...experiment.db.experiment_models import Dataset

from mlflow.entities import Span


class TrainingContext(BaseModel):
    """Context data shared between state machine steps in TrainingModule."""

    # Core data
    qa_pair: Optional[Dataset] = None
    span: Optional[Span] = None

    # Module outputs
    engine: ModuleOutput = ModuleOutput(status="error")
    answer_verifier: ModuleOutput = ModuleOutput(status="error")
    error_analyst: ModuleOutput = ModuleOutput(status="error")
    tool_debugger: ModuleOutput = ModuleOutput(status="error")
    tool_merger: ModuleOutput = ModuleOutput(status="error")
    tool_optimizer: ModuleOutput = ModuleOutput(status="error")
    tool_creator: ModuleOutput = ModuleOutput(status="error")

    class Config:
        # Allow OpenTelemetry span objects which aren't Pydantic models
        arbitrary_types_allowed = True

    def clear(self) -> None:
        """Clear all context data - equivalent to dict.clear()"""
        self.qa_pair = None
        self.span = None
        self.engine = ModuleOutput(status="error")
        self.answer_verifier = ModuleOutput(status="error")
        self.error_analyst = ModuleOutput(status="error")
        self.tool_debugger = ModuleOutput(status="error")
        self.tool_merger = ModuleOutput(status="error")
        self.tool_optimizer = ModuleOutput(status="error")
        self.tool_creator = ModuleOutput(status="error")
