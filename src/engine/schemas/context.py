from typing import Optional
from pydantic import BaseModel

from .outputs import ModuleOutput
from .qa_pair import QA_Pair

from mlflow.entities import Span


class TrainingContext(BaseModel):
    """Context data shared between state machine steps in TrainingModule."""

    # Core data
    qa_pair: Optional[QA_Pair] = None
    span: Optional[Span] = None

    # Module outputs
    engine_output: ModuleOutput = ModuleOutput(status="error")
    verifier_output: ModuleOutput = ModuleOutput(status="error")
    error_analyst_output: ModuleOutput = ModuleOutput(status="error")
    tool_debugger_output: ModuleOutput = ModuleOutput(status="error")
    tool_merger_output: ModuleOutput = ModuleOutput(status="error")
    tool_optimizer_output: ModuleOutput = ModuleOutput(status="error")
    tool_creator_output: ModuleOutput = ModuleOutput(status="error")

    class Config:
        # Allow OpenTelemetry span objects which aren't Pydantic models
        arbitrary_types_allowed = True

    def clear(self) -> None:
        """Clear all context data - equivalent to dict.clear()"""
        self.qa_pair = None
        self.span = None
        self.engine_output = ModuleOutput(status="error")
        self.verifier_output = ModuleOutput(status="error")
        self.error_analyst_output = ModuleOutput(status="error")
        self.tool_debugger_output = ModuleOutput(status="error")
        self.tool_merger_output = ModuleOutput(status="error")
        self.tool_optimizer_output = ModuleOutput(status="error")
        self.tool_creator_output = ModuleOutput(status="error")
