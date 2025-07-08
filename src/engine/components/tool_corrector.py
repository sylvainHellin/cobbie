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


if __name__ == "__main__":
    import json
    import mlflow

    from src.config import LANGUAGE_MODELS, TEST_IFC_PATH
    from src.engine.tools.primordial import (
        query_ifcopenshell_documentation,
        web_search,
    )

    def main(
        function_description: str,
        function_name: str,
        current_function_implementation: str,
        detailed_function_assessment: str,
        lm_name: str = "llama4-maverick-groq",
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
    ):
        # configure dspy
        lm_info = LANGUAGE_MODELS[lm_name]
        llm = dspy.LM(
            model=lm_info.url,
            api_key=lm_info.api_key,
            max_tokens=5000,
        )
        dspy.configure(lm=llm)

        # setup mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("ToolCorrector")

        # setup the primordial tools
        primordial_tools = [web_search, query_ifcopenshell_documentation]

        # setup the tool corrector
        tool_corrector = ToolCorrector(
            tools=primordial_tools,
            max_iters=4,
            log_level=log_level,
        )

        # correct the tool
        result = tool_corrector.forward(
            function_description=function_description,
            function_name=function_name,
            path_ifc_model=TEST_IFC_PATH,
            current_function_implementation=current_function_implementation,
            detailed_function_assessment=detailed_function_assessment,
        )

        print(f"Correction result: {json.dumps(result.model_dump(), indent=2)}")

    ##########################################
    # Test data - using similar example as in tool_assessor.py
    function_description = "To accurately determine the width of the emergency escape routes, we need a function that can identify which doors are designated as emergency exits based on their properties or other criteria. The function should be able to query the IFC model for doors with specific properties or classifications that indicate they are emergency exits."

    function_name = "get_emergency_exit_doors"

    # A deliberately flawed implementation that needs correction
    current_function_implementation = (
        "import ifcopenshell\n"
        "from typing import List\n\n"
        "def get_emergency_exit_doors(path_ifc_model: str) -> List:\n"
        '    """\n'
        "    Retrieves emergency exit doors from IFC model.\n"
        '    """\n'
        "    ifc_file = ifcopenshell.open(path_ifc_model)\n"
        "    all_doors = ifc_file.by_type('IfcDoor')\n"
        "    # This is a flawed implementation - returns all doors instead of just emergency exits\n"
        "    return all_doors"
    )

    detailed_function_assessment = (
        "The current implementation has a critical flaw: it returns ALL doors in the IFC model "
        "instead of filtering for emergency exit doors specifically. The function needs to:\n"
        "1. Check for 'FireExit' property in 'Pset_DoorCommon' property set\n"
        "2. Only return doors where FireExit is True\n"
        "3. Handle both boolean and string representations of the FireExit value\n"
        "4. Use ifcopenshell.util.element.get_pset() to access property sets correctly"
    )

    main(
        function_description=function_description,
        function_name=function_name,
        current_function_implementation=current_function_implementation,
        detailed_function_assessment=detailed_function_assessment,
        log_level="INFO",
        lm_name="gemini-flash",
    )
