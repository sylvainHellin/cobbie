from pydantic import BaseModel
from typing import Optional, Literal, Dict, Any, Callable, List


class Result(BaseModel):
    assessment_status: Optional[Literal["ok", "needs_improvement"]] = None
    assessment_details: Optional[str] = None
    answer: Optional[str] = None
    correct_answer: Optional[bool] = None
    reasoning: Optional[str] = None
    trajectory: Optional[Dict[str, Any]] = None
    similarity_score: Optional[float] = None
    need_new_function: Optional[bool] = None
    new_tool_created: Optional[bool] = None
    existing_tool_updated: Optional[bool] = None
    function_requirements: Optional[str] = None
    function_name: Optional[str] = None
    function_implementation: Optional[str] = None
    new_function: Optional[Callable] = None
    error_category: Optional[Literal["faulty_tool", "missing_tool", "other"]] = None
    error_analysis: Optional[str] = None
    improvement: Optional[
        Literal[
            "create_new_tool",
            "merge_existing_tools",
            "update_existing_tool",
            "no_action_needed",
        ]
    ] = None
    existing_tool_names: Optional[List[str]] = None
