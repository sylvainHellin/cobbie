from pydantic import BaseModel, ConfigDict
from src.db.models import IfcBench
from typing import Optional, Dict, Callable, Literal
from baml_py.baml_py import Collector
from src.baml.baml_client.types import (
    FinalAnswer,
    AnswerEvaluationResult,
    NewToolAnalysis,
    NewHelperFunction,
    FaultyToolAnalysis,
    UpdatedHelperFunction,
    HelperFunctionAssessment,
)


# Object to handle the context added by each agent for each qa_pair processing
class Context(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Core data
    qa_pair: IfcBench
    global_question_num: int  # Global question number across all training runs
    tools: Dict[str, Callable] = {}

    # Tool management configuration
    max_tools: int = 16
    grace_period: int = 8

    # Cobbie agent results
    cobbie_result: Optional[FinalAnswer] = None
    cobbie_collector: Optional[Collector] = None
    cobbie_history: str = ""
    cobbie_duration: float = 0.0

    # Answer verifier results
    verify_result: Optional[AnswerEvaluationResult] = None
    verify_collector: Optional[Collector] = None
    verify_duration: float = 0.0

    # Identify helper function results (Path A)
    identify_tool_result: Optional[NewToolAnalysis] = None
    identify_tool_collector: Optional[Collector] = None
    identify_tool_duration: float = 0.0

    # Create helper function results (Path A)
    create_tool_result: Optional[NewHelperFunction] = None
    create_tool_collector: Optional[Collector] = None
    create_tool_history: str = ""
    create_tool_duration: float = 0.0

    # Identify faulty tool results (Path B)
    identify_faulty_result: Optional[FaultyToolAnalysis] = None
    identify_faulty_collector: Optional[Collector] = None
    identify_faulty_duration: float = 0.0

    # Debug helper function results (Path B)
    debug_tool_result: Optional[UpdatedHelperFunction] = None
    debug_tool_collector: Optional[Collector] = None
    debug_tool_history: str = ""
    debug_tool_duration: float = 0.0

    # Tool testing results (both paths)
    test_cobbie_result: Optional[FinalAnswer] = None
    test_cobbie_collector: Optional[Collector] = None
    test_cobbie_history: str = ""
    test_cobbie_duration: float = 0.0
    test_verify_result: Optional[AnswerEvaluationResult] = None
    test_verify_collector: Optional[Collector] = None
    test_verify_duration: float = 0.0

    # Tool assessment results (both paths)
    tool_assessment: Optional[HelperFunctionAssessment] = None
    tool_assessment_collector: Optional[Collector] = None
    tool_assessment_duration: float = 0.0

    # Tracking metadata
    error_message: Optional[str] = None
    tool_created: bool = False
    tool_updated: bool = False
    tool_saved: bool = False
    tool_name: Optional[str] = None
    is_enhancement: bool = False  # Track if current operation is enhancement
    path_taken: Optional[Literal["correct", "wrong", "abstained"]] = None
