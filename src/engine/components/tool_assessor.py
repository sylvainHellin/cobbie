from typing import Literal, List, Callable

import dspy

from src.engine.components.code_agent import CodeAgent
from src.engine.schemas import ModuleOutput, Result
from src.engine.util import get_logger, _create_function_from_source_code


class ToolAssessmentSignature(dspy.Signature):
    """
    Assess whether a generated Python function meets requirements and works correctly.
    Note that the path_ifc_model is not loaded as a variable in the Python interpreter. Therefore, you must instantiate the variable if you want to use it.
    """

    # inputs
    function_name: str = dspy.InputField(
        desc="Name of the function to assess. This function is available as a tool."
    )
    function_requirements: str = dspy.InputField(
        desc="Original requirements and description of what the function should do"
    )
    path_ifc_model: str = dspy.InputField(
        desc="Path to an IFC file for testing the function."
    )

    # outputs
    assessment_status: Literal["ok", "needs_improvement"] = dspy.OutputField(
        desc="'ok' if the tool works as expected, 'needs_improvement' if issues were found"
    )
    assessment_details: str = dspy.OutputField(
        desc="Detailed explanation of the assessment. If the function crashed, include the error. If the output is wrong, explain why. Provide suggestions for correction."
    )


class ToolAssessor(dspy.Module):
    """Module to assess the quality and functionality of generated tools."""

    def __init__(
        self,
        tools: List[Callable],
        max_iters: int = 10,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
    ):
        super().__init__()
        # Combine base tools with the generated tool
        self.tools = tools
        self.max_iters = max_iters
        self.agent = CodeAgent(
            signature=ToolAssessmentSignature,
            tools=self.tools,
            max_iters=self.max_iters,
        )
        self.log_level = log_level
        self.logger = get_logger(name="ToolAssessor", log_level=self.log_level)

    def forward(
        self,
        function_name: str,
        function_requirements: str,
        path_ifc_model: str,
    ) -> ModuleOutput:
        output = self.agent(
            function_name=function_name,
            function_requirements=function_requirements,
            path_ifc_model=path_ifc_model,
        )

        if output.assessment_status and output.assessment_details:
            self.logger.debug("Tool assessment successfull")
            self.logger.debug(f"Assessment status: \n{output.assessment_status}")
            self.logger.debug(f"Assessment details: \n{output.assessment_details}")
            return ModuleOutput(
                result=Result(
                    assessment_status=output.assessment_status,
                    assessment_details=output.assessment_details,
                ),
                status="success",
            )
        else:
            self.logger.debug("Tool assessment failed")
            return ModuleOutput(status="error", error_msg="Tool assessment failed")


if __name__ == "__main__":
    import json
    import mlflow

    from src.config import LANGUAGE_MODELS, TEST_IFC_PATH
    from src.engine.tools.primordial import (
        query_ifcopenshell_documentation,
        web_search,
    )

    def main(
        function_requirements: str,
        function_name: str,
        python_code: str,
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
        mlflow.set_experiment("ToolAssessor")

        # setup the primordial tools
        primordial_tools = [web_search, query_ifcopenshell_documentation]

        # Create the function from source code (mocking up the implementation from tool_creator.py)
        try:
            new_tool = _create_function_from_source_code(
                function_name=function_name, code=python_code
            )
            print(f"✓ Successfully created function: {function_name}")
        except Exception as e:
            print(f"✗ Failed to create function: {str(e)}")
            return

        tools = primordial_tools + [new_tool]

        # setup the tool assessor
        tool_assessor = ToolAssessor(
            tools=tools,
            max_iters=4,
            log_level=log_level,
        )

        # assess the tool
        result = tool_assessor.forward(
            function_name=function_name,
            function_requirements=function_requirements,
            path_ifc_model=TEST_IFC_PATH,
        )

        print(f"Assessment result: {json.dumps(result.model_dump(), indent=2)}")

    ##########################################
    function_requirements = "To accurately determine the width of the emergency escape routes, we need a function that can identify which doors are designated as emergency exits based on their properties or other criteria. The function should be able to query the IFC model for doors with specific properties or classifications that indicate they are emergency exits."

    function_name = "get_emergency_exit_doors"
    python_code = (
        "import ifcopenshell\n"
        "import ifcopenshell.util.element\n"
        "from typing import List\n\n"
        "def get_emergency_exit_doors(path_ifc_model: str) -> List:\n"
        '    """\n'
        "    Retrieves a list of IfcDoor entities that are designated as emergency exits\n"
        "    based on the 'FireExit' property in 'Pset_DoorCommon'.\n\n"
        "    Args:\n"
        "    path_ifc_model (str): Path to the IFC file.\n\n"
        "    Returns:\n"
        "    List[ifcopenshell.entity_instance.entity_instance]: A list of IfcDoor entities representing emergency exits.\n"
        '    """\n'
        "    ifc_file = ifcopenshell.open(path_ifc_model)\n"
        "    all_doors = ifc_file.by_type('IfcDoor')\n"
        "    emergency_exit_doors = []\n\n"
        "    for door in all_doors:\n"
        "        door_common_pset = ifcopenshell.util.element.get_pset(door, 'Pset_DoorCommon')\n"
        "        if door_common_pset and 'FireExit' in door_common_pset:\n"
        "            fire_exit_value = door_common_pset['FireExit']\n"
        "            if (isinstance(fire_exit_value, bool) and fire_exit_value) or \\\n"
        "               (isinstance(fire_exit_value, str) and fire_exit_value.lower() == 'true'):\n"
        "                emergency_exit_doors.append(door)\n"
        "    return emergency_exit_doors"
    )

    main(
        function_requirements=function_requirements,
        function_name=function_name,
        python_code=python_code,
        log_level="INFO",
        lm_name="gemini-flash",
    )
