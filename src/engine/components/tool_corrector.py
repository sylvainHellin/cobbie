from typing import Callable, List, Literal

import dspy

from src.engine.schemas import ModuleOutput, Result
from src.engine.util import get_logger

from .code_act import CodeAct


class ToolCorrectionSignature(dspy.Signature):
    """
    Correct a Python function based on assessment feedback.

    The current implementation was tested and found to be faulty.

    You are provided with the code of the current implementation, as well as a detailed assessment of the necessary improvements. Using this information, update the code of the current implementation.
    """

    # inputs
    function_description: str = dspy.InputField(
        desc="Detailed description of what the function should do and its requirements."
    )

    function_name: str = dspy.InputField(desc="Name of the function.")

    current_function_implementation: str = dspy.InputField(
        desc="Current implementation of the function that needs to be updated."
    )

    detailed_function_assessment: str = dspy.InputField(
        desc="The detailed assessment of the current implementation of the function."
    )

    path_ifc_model: str = dspy.InputField(
        desc="Path to an IFC file for testing the function."
    )

    # outputs
    new_function_implementation: str = dspy.OutputField(
        desc="The updated implementation of the required function, mitigating the issues identified in the detailed assessment."
    )


class ToolCorrector(dspy.Module):
    """Module to correct an existing Python function."""

    def __init__(
        self,
        tools: List[Callable],
        max_iters: int = 10,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
    ):
        super().__init__()
        self.tools = tools
        self.max_iters = max_iters
        self.agent = CodeAct(
            signature=ToolCorrectionSignature,
            tools=self.tools,
            max_iters=self.max_iters,
        )
        self.log_level = log_level
        self.logger = get_logger(name="ToolCorrector", log_level=self.log_level)

    def forward(
        self,
        function_description: str,
        function_name: str,
        path_ifc_model: str,
        current_function_implementation: str,
        detailed_function_assessment: str,
    ) -> ModuleOutput:
        output = self.agent(
            function_description=function_description,
            function_name=function_name,
            path_ifc_model=path_ifc_model,
            current_function_implementation=current_function_implementation,
            detailed_function_assessment=detailed_function_assessment,
        )

        if output.new_function_implementation:
            self.logger.info("ToolCorrector updated the implementation successfully")
            self.logger.debug(
                f"New implementation: {output.new_function_implementation}"
            )
            return ModuleOutput(
                result=Result(python_code=output.new_function_implementation),
                status="success",
            )
        else:
            self.logger.info("ToolCorrector failed to update the function.")
            return ModuleOutput(
                status="error", error_msg="ToolCorrector failed to update the function."
            )
