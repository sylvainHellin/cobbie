import re
from typing import Callable, List, Optional, cast

import dspy
import mlflow

from src.config.agents import (
    AGENT_CONFIGS,
    ToolCreatorConfig,
)
from src.engine.components.code_act import CodeAct
from src.engine.components.test_and_improve import TestAndImprove
from src.engine.schemas import ModuleOutput
from src.engine.tools.primordial import (
    query_ifcopenshell_documentation,
    web_search,
)
from src.engine.util import get_logger


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
        config: Optional[ToolCreatorConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.tool_creator
        self.lm = lm or self.config.llm.get_llm()
        self.tools = tools

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
        # Init the output
        self.output = ModuleOutput()

        with dspy.context(lm=self.lm):
            self.logger.info(f"Starting the creation of the tool: {function_name}")

            try:
                self.logger.info("Creating initial function")
                prediction = self.tool_creator(
                    function_requirements=function_requirements,
                    function_name=function_name,
                    path_ifc_model=path_ifc_model,
                    function_boilerplate=self.function_boilerplate,
                )

                self.output.result.function_implementation = getattr(
                    prediction, "function_implementation", None
                )

                if self.output.result.function_implementation is None:
                    self.output.error_msg = (
                        f"No valid code generated for function: {function_name}"
                    )
                    self.logger.error(self.output.error_msg)

            except Exception as e:
                self.output.error_msg = f"An Exception occured during the CodeAct forward pass:\nError:\n{e}"
                self.logger.error(self.output.error_msg)

            finally:
                self.output.update_cost(
                    lm=self.lm,
                    cost_input_tokens=self.config.llm.cost_input_token,
                    cost_output_tokens=self.config.llm.cost_output_token,
                )

            # Test and debug the new tool if necessary
            if self.output.result.function_implementation:
                # Clean the function implementation to remove any code block markers
                self.output.result.function_implementation = self._clean_code_blocks(
                    self.output.result.function_implementation
                )

                output_test_and_improve = cast(
                    ModuleOutput,
                    self.test_and_improve(
                        function_implementation=self.output.result.function_implementation,
                        function_requirements=function_requirements,
                        function_name=function_name,
                        path_ifc_model=path_ifc_model,
                    ),
                )
                if output_test_and_improve.status == "success":
                    self.output.status = "success"
                    self.output.result = output_test_and_improve.result
                    self.output.combine_cost(output=output_test_and_improve)

            return self.output


if __name__ == "__main__":
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
        output = cast(
            ModuleOutput,
            tool_creator(
                function_requirements=function_requirements,
                function_name=function_name,
                path_ifc_model=TEST_IFC_PATH,
            ),
        )

        print(f"Tool creation result: {output.model_dump_json(indent=2)}")

    ##########################################
    # Test data - creating a simple IFC analysis function
    function_requirements = "Function signature:\n`count_elements_by_property(ifc_file_path: str, ifc_type: str, property_set_name: str, property_name: str, property_value) -> int`\n\nDescription:\nThis function retrieves all elements of a specified IFC type from an IFC model, then counts how many of those elements have a specific property value within a given property set.\n\nRequirements:\n- Use IfcOpenShell to open the IFC file and retrieve elements of the specified type.\n- For each element, extract the property sets using `ifcopenshell.util.element.get_psets`.\n- Check if the specified property set exists for the element.\n- If it exists, check if the specified property has the desired value.\n- Count and return the number of elements that match the criteria.\n- Handle cases where the property set or property might not exist for an element.\n- The function should be flexible enough to handle different data types for `property_value` (e.g., bool, str, int)."

    function_name = "count_elements_by_property"

    main(
        function_requirements=function_requirements,
        function_name=function_name,
    )
