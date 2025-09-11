from typing import Literal, Optional, Self, Callable, Dict, List, Any
import json

import dspy
from pydantic import BaseModel


class AgentOutput(BaseModel):
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
    tools_merged: Optional[bool] = None


class ModuleOutput(BaseModel):
    history: Optional[List] = None
    result: AgentOutput = AgentOutput()
    status: Literal["error", "success"] = "error"
    error_msg: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    llm: Optional[str] = None
    cost: Optional[float] = None

    def _make_json_serializable(self, obj):
        """Convert an object to a JSON-serializable format."""
        try:
            # Try to serialize the object directly
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            # If it fails, convert to string representation or handle specific types
            if hasattr(obj, "__dict__"):
                # For objects with __dict__, try to serialize their attributes
                try:
                    return {
                        k: self._make_json_serializable(v)
                        for k, v in obj.__dict__.items()
                        if not k.startswith("_")
                    }
                except:
                    return str(obj)
            elif isinstance(obj, (list, tuple)):
                return [self._make_json_serializable(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: self._make_json_serializable(v) for k, v in obj.items()}
            else:
                # For other non-serializable objects, convert to string
                return str(obj)

    def update_lm_metrics(
        self,
        lm: dspy.LM,
        cost_input_tokens: float,
        cost_output_tokens: float,
    ):
        """Update the cost calculation for this module output.

        Calculates token usage from the language model and computes the total cost
        based on the provided input and output token rates.

        Args:
            lm: The DSPy language model instance to get token counts from
            cost_input_tokens: Cost per input token
            cost_output_tokens: Cost per output token
        """
        self.input_tokens = 0
        self.output_tokens = 0

        if hasattr(lm, "history") and lm.history:
            for call in lm.history:
                usage = call.get("usage", {})
                self.input_tokens += usage.get("prompt_tokens", 0)
                self.output_tokens += usage.get("completion_tokens", 0)
            # Make history JSON-serializable
            self.history = self._make_json_serializable(lm.history)

        self.cost = (
            (self.input_tokens or 0) * cost_input_tokens
            + (self.output_tokens or 0) * cost_output_tokens
        ) / 1000000

        self.llm = lm.model

    def combine_lm_metrics(
        self,
        right_output: Self,
        combine_history: bool = False,
        update_llm: Literal["right", "left"] = "left",
    ):
        """Combine some metrics from another ModuleOutput into this one.

        Adds the cost, input_tokens, and output_tokens from the provided output
        to this ModuleOutput's metrics. Handles None values by treating them as 0.
        Chose which llm to keep, and if history also needs to be combined.
        """
        self.cost = (self.cost or 0) + (right_output.cost or 0)
        self.input_tokens = (self.input_tokens or 0) + (right_output.input_tokens or 0)
        self.output_tokens = (self.output_tokens or 0) + (
            right_output.output_tokens or 0
        )

        # Handle LLM field when combining different models
        self.llm = right_output.llm if update_llm == "right" else self.llm

        # update LM history
        if combine_history:
            if self.history is None:
                self.history = []
            if right_output.history is not None:
                self.history.extend(right_output.history)
