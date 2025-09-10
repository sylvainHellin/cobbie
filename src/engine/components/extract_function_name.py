from typing import Literal

import dspy

from src.config import LOG_LEVEL
from src.engine.schemas import ModuleOutput, Result
from src.engine.util import get_logger


class ExtractFunctionNameSignature(dspy.Signature):
    """
    Based on the requirements for a new Python function, determine what the function should be called.
    If a name is provided in the function signature, use that. If none is provided, suggest a meaningful alternative.
    """

    function_requirements: str = dspy.InputField()
    reasoning: str = dspy.OutputField()
    function_name: str = dspy.OutputField()


class NameExtractor(dspy.Module):
    """
    A DSPy module that extracts or suggests a function name based on provided requirements for a new Python function.
    Utilizes a chain-of-thought approach to determine the most appropriate function name, either by extracting it from a given signature or by generating a meaningful alternative.
    """

    def __init__(
        self,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = LOG_LEVEL,
    ):
        super().__init__()
        self.extractor = dspy.ChainOfThought(ExtractFunctionNameSignature)
        self.logger = get_logger(name="NameExtractor", log_level=log_level)

    def forward(self, function_requirements: str) -> ModuleOutput:
        """
        Extracts or suggests a function name based on the provided requirements for a new Python function.

        Args:
            function_requirements (str): The requirements or description for the new function.

        Returns:
            ModuleOutput: An object containing the extracted or suggested function name, reasoning, and status.
        """
        self.logger.info("Starting forward pass")
        self.output = ModuleOutput()

        try:
            prediction = self.extractor(function_requirements=function_requirements)
            self.output.result = Result(
                function_name=getattr(prediction, "function_name", None),
                reasoning=getattr(prediction, "reasoning", None),
            )
            if (
                self.output.result.function_name is not None
                and self.output.result.reasoning is not None
            ):
                self.output.status = "success"

        except Exception as e:
            self.output.error_msg = (
                f"Error when trying to extract the name of the function. Error:\n{e}"
            )
            self.logger.error(self.output.error_msg)

        self.logger.info("Completed forward pass")

        return self.output
