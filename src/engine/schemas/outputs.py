from typing import Any, Callable, Dict, List, Literal, Optional, Self

import dspy
from pydantic import BaseModel

from .chat import Chat


class AgentOutput(BaseModel):
    """Output model for agent responses containing assessment results and function management data.

    This class captures all possible outputs from various agents in the system,
    including assessments, answers, tool creation/modification status, and error analysis.
    """

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
    new_function_saved: Optional[bool] = None
    old_functions_deleted: Optional[bool] = None
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


class LM_Metrics(BaseModel):
    """Metrics for tracking language model usage and costs.

    This class tracks token usage (input/output), model information, and calculated costs
    for language model interactions.
    """

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    llm: Optional[str] = None
    cost: Optional[float] = None

    def update(
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

        self.cost = (
            (self.input_tokens or 0) * cost_input_tokens
            + (self.output_tokens or 0) * cost_output_tokens
        ) / 1000000

        self.llm = lm.model

    def combine(
        self,
        other_metrics: Self,
        history: Literal["self", "other"] = "self",
        llm: Literal["self", "other"] = "self",
    ):
        """Combine metrics from another LM_Metrics instance into this one.

        Adds the cost, input_tokens, and output_tokens from the provided metrics
        to this instance's metrics. Handles None values by treating them as 0.
        Choose which llm to keep, and if history also needs to be combined.

        Args:
            other_metrics: The LM_Metrics instance to combine with this one
            history: Which chat history to keep ("self" or "other")
            llm: Which LLM identifier to keep ("self" or "other")
        """
        self.cost = (self.cost or 0) + (other_metrics.cost or 0)
        self.input_tokens = (self.input_tokens or 0) + (other_metrics.input_tokens or 0)
        self.output_tokens = (self.output_tokens or 0) + (
            other_metrics.output_tokens or 0
        )

        # Handle LLM field when combining different models
        self.llm = other_metrics.llm if llm == "other" else self.llm


class Tools_Metrics(BaseModel):
    """Metrics for tracking tool creation, updates, and associated costs.

    This class maintains counters for various tool operations and their cumulative costs.
    """

    nb_tools_created: float = 0
    nb_tools_updated: float = 0
    nb_tools_merged: float = 0
    cost: float = 0

    def combine(self, metrics: Self) -> None:
        """Update this Tools_Metrics instance by adding values from another instance.

        Args:
            metrics: Another Tools_Metrics instance to add to this one
        """
        self.nb_tools_created += metrics.nb_tools_created
        self.nb_tools_updated += metrics.nb_tools_updated
        self.nb_tools_merged += metrics.nb_tools_merged
        self.cost += metrics.cost


class ModuleOutput(BaseModel):
    """Main output container for engine modules, combining results, metrics, and status.

    This class serves as the primary output format for all engine modules,
    containing chat history, agent results, execution status, error information,
    and both language model and tool metrics.
    """

    chat: Chat = Chat()
    result: AgentOutput = AgentOutput()
    status: Literal["error", "success"] = "error"
    error_msg: Optional[str] = None
    lm_metrics: LM_Metrics = LM_Metrics()
    tools_metrics: Tools_Metrics = Tools_Metrics()

    def combine_lm_metrics(
        self,
        other_output: Self,
        history: Literal["self", "other"] = "self",
        llm: Literal["self", "other"] = "self",
    ):
        """Combine language model metrics from another ModuleOutput into this one.

        Args:
            other_output: The ModuleOutput instance to combine metrics from
            history: Which chat history to keep ("self" or "other")
            llm: Which LLM identifier to keep ("self" or "other")
        """
        self.lm_metrics.combine(
            other_metrics=other_output.lm_metrics,
            history=history,
            llm=llm,
        )

    def combine_tools_metrics(self, output: Self):
        """Combine tool metrics from another ModuleOutput into this one.

        Args:
            output: The ModuleOutput instance to combine tool metrics from
        """
        self.tools_metrics.combine(metrics=output.tools_metrics)

    def update(
        self,
        lm: dspy.LM,
        cost_input_tokens: float,
        cost_output_tokens: float,
    ):
        self.chat.import_chat_messages(lm.history[-1].get("messages"))
        self.lm_metrics.update(
            lm=lm,
            cost_input_tokens=cost_input_tokens,
            cost_output_tokens=cost_output_tokens,
        )

        return


class TrainingOutputs(BaseModel):
    """Container for managing multiple ModuleOutput instances with aggregation capabilities.

    This class provides methods to collect, manage, and combine metrics from multiple
    ModuleOutput instances, useful for tracking cumulative results across multiple
    engine module executions.
    """

    outputs: List[ModuleOutput] = []
    lm_metrics: LM_Metrics = LM_Metrics()
    tools_metrics: Tools_Metrics = Tools_Metrics()

    def add(self, output: ModuleOutput, update: bool = True) -> None:
        """Add a ModuleOutput to the collection.

        Args:
            output: The ModuleOutput instance to add
            update: If the metrics of the List should be updated (optional)
        """
        self.outputs.append(output)
        if update:
            self.lm_metrics.combine(other_metrics=output.lm_metrics)
            self.tools_metrics.combine(metrics=output.tools_metrics)

    def __len__(self) -> int:
        """Return the number of stored outputs."""
        return len(self.outputs)

    def __getitem__(self, index: int) -> ModuleOutput:
        """Allow indexing into stored outputs."""
        return self.outputs[index]
