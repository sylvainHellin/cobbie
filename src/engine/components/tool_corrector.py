from typing import Callable, List, Optional

import dspy

from src.config.agents import AGENT_CONFIGS, ToolCorrectorConfig
from src.engine.components.code_act import CodeAct
from src.engine.schemas import ModuleOutput
from src.engine.util import create_code_prefix, get_logger


class ToolCorrectionSignature(dspy.Signature):
    """
    As an expert Python programmer, you have been tasked with correcting a given Python function implementation, which is not performing as expected.
    You are provided with the code of the current implementation, as well as a detailed assessment of the necessary improvements. Using this information, update the code of the current implementation.


    Your corrected function implementation must:
        - Return proper data structures (e.g., lists and dictionaries), not formatted strings.
        - Be well-documented with docstrings and type hints.
        - Be explicit regarding assumptions. For example, if your function involves using properties related to specific BIM authoring software, such as PSet_Revit_Dimensions for an IFC model exported from Revit, mention this in the docstring.
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
        config: Optional[ToolCorrectorConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.tool_corrector
        self.lm = lm or self.config.llm.get_llm()
        dspy.configure(lm=self.lm)

        self.tools = tools
        self.max_iters = self.config.max_iters
        self.tool_corrector = CodeAct(
            signature=ToolCorrectionSignature,
            tools=self.tools,
            max_iters=self.max_iters,
        )
        self.log_level = self.config.log_level
        self.logger = get_logger(name="ToolCorrector", log_level=self.log_level)
        self.add_code_prefix = self.config.add_code_prefix

    def forward(
        self,
        function_description: str,
        function_name: str,
        path_ifc_model: str,
        current_function_implementation: str,
        detailed_function_assessment: str,
    ) -> ModuleOutput:
        self.logger.info(f"Starting ToolCorrector for function: {function_name}")
        self.output = ModuleOutput()

        if self.add_code_prefix:
            code_prefix = create_code_prefix(
                path_ifc_model=path_ifc_model,
            )
        else:
            code_prefix = None
        self.tool_corrector._update_code_prefix(code_prefix=code_prefix)

        try:
            prediction = self.tool_corrector(
                function_description=function_description,
                function_name=function_name,
                path_ifc_model=path_ifc_model,
                current_function_implementation=current_function_implementation,
                detailed_function_assessment=detailed_function_assessment,
            )

            self.output.result.function_implementation = getattr(
                prediction, "new_function_implementation", None
            )

            if self.output.result.function_implementation:
                self.logger.info(
                    f"ToolCorrector result: success - function '{function_name}' updated successfully"
                )
                self.output.status = "success"

            else:
                self.output.error_msg = (
                    f"Failed to update the function: {function_name}"
                )
                self.logger.info(self.output.error_msg)
        except Exception as e:
            error_msg = f"An Exception occured during the CodeAct forward pass of the ToolCorrector:\nError:{e}\n"
            self.logger.error(error_msg)
        finally:
            self.output.update_cost(
                lm=self.lm,
                cost_input_tokens=self.config.llm.cost_input_token,
                cost_output_tokens=self.config.llm.cost_output_token,
            )
            return self.output


if __name__ == "__main__":
    import mlflow

    from src.config import TEST_IFC_PATH
    from src.engine.tools.primordial import (
        query_ifcopenshell_documentation,
        web_search,
    )

    def main(
        function_description: str,
        function_name: str,
        current_function_implementation: str,
        detailed_function_assessment: str,
        lm=None,
    ):
        # setup mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("ToolCorrector")

        dspy.configure_cache(enable_disk_cache=False, enable_memory_cache=False)

        # setup the primordial tools
        primordial_tools = [web_search, query_ifcopenshell_documentation]

        # setup the tool corrector
        tool_corrector = ToolCorrector(
            tools=primordial_tools,
            lm=lm,
        )

        # correct the tool
        result = tool_corrector(
            function_description=function_description,
            function_name=function_name,
            path_ifc_model=TEST_IFC_PATH,
            current_function_implementation=current_function_implementation,
            detailed_function_assessment=detailed_function_assessment,
        )

        print(f"Correction result: {result}")

    ##########################################
    # Test data - using similar example as in tool_assessor.py
    function_description = "\n            Create a function that counts the total number of doors in an IFC model.\n            The function should:\n            1. Take an IFC file path as input\n            2. Open the IFC model using ifcopenshell\n            3. Find all door elements (IfcDoor)\n            4. Return the count as an integer (not as a string)\n\n            The function should handle errors gracefully and return accurate counts.\n            "

    function_name = "count_doors"

    current_function_implementation = '\n    import ifcopenshell\n    def count_doors(ifc_file_path: str) -> int:\n        """Count all doors in an IFC model."""\n        model = ifcopenshell.open(ifc_file_path)\n        doors = model.by_type("IfcDoor")\n        return str(len(doors))\n    '

    detailed_function_assessment = "The function correctly counts the number of doors (14) in the IFC model, but it returns the count as a string instead of an integer, which violates requirement #4. The function signature indicates it should return an integer, and returning a string breaks type expectations. This could cause issues for code that consumes this function and expects an integer. The function should be modified to return an integer type instead of a string."

    main(
        function_description=function_description,
        function_name=function_name,
        current_function_implementation=current_function_implementation,
        detailed_function_assessment=detailed_function_assessment,
    )
