from typing import Literal, Optional, Self

import dspy
from pydantic import BaseModel

from src.engine.schemas.result import Result


class ModuleOutput(BaseModel):
    result: Result = Result()
    status: Literal["error", "success"] = "error"
    error_msg: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    llm: Optional[str] = None
    cost: Optional[float] = None

    def update_cost(
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

    def combine_cost(self, output: Self):
        """Combine cost metrics from another ModuleOutput into this one.

        Adds the cost, input_tokens, and output_tokens from the provided output
        to this ModuleOutput's metrics. Handles None values by treating them as 0.
        Updates the llm field to indicate mixed models if different models were used.

        Args:
            output: Another ModuleOutput instance whose costs will be added to this one
        """
        self.cost = (self.cost or 0) + (output.cost or 0)
        self.input_tokens = (self.input_tokens or 0) + (output.input_tokens or 0)
        self.output_tokens = (self.output_tokens or 0) + (output.output_tokens or 0)

        # Handle LLM field when combining different models
        if self.llm and output.llm and self.llm != output.llm:
            self.llm = f"{self.llm}+{output.llm}"
        elif not self.llm and output.llm:
            self.llm = output.llm
