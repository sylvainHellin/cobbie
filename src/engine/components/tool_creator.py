from typing import Callable, List
import re

import dspy
import mlflow

from src.config import (
    AGENT_CONFIGS,
)
from src.engine.components import CodeAct
from src.engine.schemas.module_output import ModuleOutput
from src.engine.tools.primordial import (
    query_ifcopenshell_documentation,
    web_search,
)
from src.engine.util import get_logger

from .test_and_improve import TestAndImprove


class SignatureToolCreator(dspy.Signature):
    """
    As an expert Python programmer, you have been tasked with creating a new Python function using the IfcOpenShell library.

    Your function implementation must:
        - Return proper data structures (e.g., lists and dictionaries), not formatted strings.
        - Be well-documented with docstrings and type hints.
        - Be explicit regarding assumptions. For example, if your function involves using properties related to specific BIM authoring software, such as PSet_Revit_Dimensions for an IFC model exported from Revit, mention this in the docstring.
    """

    # inputs
    function_requirements: str = dspy.InputField(
        desc="Detailed description of what the function should do and its requirements."
    )
    function_name: str = dspy.InputField()

    function_boilerplate: str = dspy.InputField(
        desc="This boilerplate must be included at the beginning of your code. Otherwise, it will not work properly."
    )

    path_ifc_model: str = dspy.InputField(
        desc="Path to an IFC file for testing the function."
    )

    # outputs
    function_implementation: str = dspy.OutputField(
        desc="Python code (including imports from the boilerplate, any necessary helper functions, etc.) of your Python function implementation."
    )


class ToolCreator(dspy.Module):
    def __init__(
        self,
        tools: List[Callable] = [
            query_ifcopenshell_documentation,
            web_search,
        ],
        config=None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.tool_creator
        self.tools = tools

        # Use provided LLM or get from config
        self.lm = self.config.llm.get_llm()
        dspy.configure(lm=self.lm)
        self.log_level = self.config.log_level
        self.logger = get_logger(name="ToolCreator", log_level=self.log_level)
        self.max_iters = self.config.max_iters
        self.function_boilerplate = self.config.function_boilerplate
        self.add_code_prefix = self.config.add_code_prefix

        # Instantiate the sub agents - they use their own configs from AGENT_CONFIGS
        self.tool_creator = CodeAct(
            signature=SignatureToolCreator,
            tools=tools,
            max_iters=self.max_iters,
        )
        self.test_and_improve = TestAndImprove()

    def _clean_code_blocks(self, code: str) -> str:
        """
        Remove code blocks wrapped in ```python ... ``` or ``` ... ``` from the code.

        Args:
            code: The code string that may contain code block markers

        Returns:
            Cleaned code string without code block markers
        """
        # Pattern to match code blocks with optional language specification
        # Matches ```python\n...``` or ```\n...``` patterns
        pattern = r"```(?:python)?\s*\n(.*?)\n```"

        # Find all code blocks
        matches = re.findall(pattern, code, re.DOTALL)

        if matches:
            # If code blocks are found, extract the content from the first/main block
            # Usually there's just one main code block containing the function
            cleaned_code = matches[0].strip()
            self.logger.info("Removed code block markers from function implementation")
            return cleaned_code

        # If no code blocks found, return original code
        return code

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        path_ifc_model: str,
    ) -> ModuleOutput:
        with mlflow.start_span(
            name="ToolCreator",
            span_type="MODULE",
        ) as creator_span:
            # --- Set up the system --- #
            output = ModuleOutput(status="error")

            # Set initial creator_span inputs
            creator_span.set_inputs(
                {
                    "function_name": function_name,
                    "path_ifc_model": path_ifc_model,
                    "function_requirements": function_requirements,
                }
            )

            self.logger.info(f"Starting the creation of the tool: {function_name}")

            # --- Create initial function --- #
            with mlflow.start_span(
                name="InitialCodeGeneration", span_type="MODULE"
            ) as code_generation_span:
                code_generation_span.set_inputs(
                    {
                        "function_name": function_name,
                        "path_ifc_model": path_ifc_model,
                        "function_requirements": function_requirements,
                    }
                )
                try:
                    self.logger.info("Creating initial function")
                    prediction = self.tool_creator.forward(
                        function_requirements=function_requirements,
                        function_name=function_name,
                        path_ifc_model=path_ifc_model,
                        function_boilerplate=self.function_boilerplate,
                    )

                    if (
                        hasattr(prediction, "function_implementation")
                        and prediction.function_implementation
                    ):
                        output.result.function_implementation = (
                            prediction.function_implementation
                        )
                    else:
                        output.error_msg = (
                            f"No valid code generated for function: {function_name}"
                        )
                        self.logger.error(output.error_msg)

                except Exception as e:
                    output.error_msg = f"An Exception occured during the CodeAct forward pass:\nError:\n{e}"
                    self.logger.error(output.error_msg)

                finally:
                    code_generation_span.set_outputs(
                        {
                            "function_implementation": output.result.function_implementation,
                            "status": output.status,
                            "error_msg": output.error_msg,
                        }
                    )

            # Test and debug the new tool if necessary
            if output.result.function_implementation:
                # Clean the function implementation to remove any code block markers
                output.result.function_implementation = self._clean_code_blocks(
                    output.result.function_implementation
                )

                output = self.test_and_improve.forward(
                    function_implementation=output.result.function_implementation,
                    function_requirements=function_requirements,
                    function_name=function_name,
                    path_ifc_model=path_ifc_model,
                )

            creator_span.set_outputs(
                {
                    "status": output.status,
                    "error_msg": output.error_msg,
                    "function_implementation": output.result.function_implementation,
                }
            )

            return output


if __name__ == "__main__":
    import json

    from src.config import TEST_IFC_PATH

    def main(
        function_requirements: str,
        function_name: str,
    ):
        # setup mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("ToolCreator")

        # setup the tool creator
        tool_creator = ToolCreator()

        # create the tool
        result = tool_creator.forward(
            function_requirements=function_requirements,
            function_name=function_name,
            path_ifc_model=TEST_IFC_PATH,
        )

        print(f"Tool creation result: {json.dumps(result.model_dump(), indent=2)}")

    ##########################################
    # Test data - creating a simple IFC analysis function
    function_requirements = "Function signature:\n`count_elements_by_property(ifc_file_path: str, ifc_type: str, property_set_name: str, property_name: str, property_value) -> int`\n\nDescription:\nThis function retrieves all elements of a specified IFC type from an IFC model, then counts how many of those elements have a specific property value within a given property set.\n\nRequirements:\n- Use IfcOpenShell to open the IFC file and retrieve elements of the specified type.\n- For each element, extract the property sets using `ifcopenshell.util.element.get_psets`.\n- Check if the specified property set exists for the element.\n- If it exists, check if the specified property has the desired value.\n- Count and return the number of elements that match the criteria.\n- Handle cases where the property set or property might not exist for an element.\n- The function should be flexible enough to handle different data types for `property_value` (e.g., bool, str, int)."

    function_name = "count_elements_by_property"

    main(
        function_requirements=function_requirements,
        function_name=function_name,
    )
