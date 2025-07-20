from typing import Callable, List, Literal

import dspy

from src.engine.components.code_act import CodeAct
from src.engine.schemas import ModuleOutput, Result
from src.engine.util import (
    _create_function_from_source_code,
    create_code_prefix,
    get_logger,
)


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
        add_code_prefix: bool = True,
    ):
        super().__init__()
        # Combine base tools with the generated tool
        self.tools = tools
        self.max_iters = max_iters
        self.agent = CodeAct(
            signature=ToolAssessmentSignature,
            tools=self.tools,
            max_iters=self.max_iters,
        )
        self.log_level = log_level
        self.logger = get_logger(name="ToolAssessor", log_level=self.log_level)
        self.add_code_prefix = add_code_prefix

    def forward(
        self,
        function_name: str,
        function_requirements: str,
        path_ifc_model: str,
    ) -> ModuleOutput:
        if self.add_code_prefix:
            code_prefix = create_code_prefix(
                path_ifc_model=path_ifc_model,
            )
        else:
            code_prefix = None
        self.agent._update_code_prefix(code_prefix=code_prefix)
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
    python_code = '''
    import ifcopenshell
    import ifcopenshell.util.element
    import ifcopenshell.util.shape
    import ifcopenshell.util.placement
    import ifcopenshell.util.geolocation
    import ifcopenshell.util.system
    import ifcopenshell.geom
    import math
    import json
    from typing import Union, List, Dict, Any

    def get_emergency_exit_doors(ifc_file_path: str) -> List[ifcopenshell.entity_instance]:
        """
        Retrieves a list of IfcDoor entities that are designated as emergency exits.

        Assumptions:
        - An emergency exit door is identified by the presence of a property named "IsFireExit"
          within any of its associated property sets (e.g., PSet_Revit_Type_Other).
        - If the "IsFireExit" property exists, its value is considered to indicate an emergency exit,
          unless it is explicitly False or "No" (case-insensitive). In the provided model,
          the value is a placeholder string 'IsFireExit', which is treated as an affirmative
          indication of an emergency exit.

        Args:
        ifc_file_path (str): Path to the IFC file.

        Returns:
        List[ifcopenshell.entity_instance]: A list of IfcDoor entities representing emergency exits.
        """
        emergency_exit_doors = []
        try:
            ifc_file = ifcopenshell.open(ifc_file_path)
            doors = ifc_file.by_type('IfcDoor')

            for door in doors:
                is_emergency_exit = False
                # Iterate through relationships to find property sets
                for rel_def in door.IsDefinedBy:
                    if rel_def.is_a('IfcRelDefinesByProperties'):
                        property_set = rel_def.RelatingPropertyDefinition
                        if property_set.is_a('IfcPropertySet'):
                            for prop in property_set.HasProperties:
                                if prop.is_a('IfcPropertySingleValue') and prop.Name == 'IsFireExit':
                                    value = prop.NominalValue.wrappedValue if prop.NominalValue else None
                                    # Check if the value indicates an emergency exit
                                    # Treat non-False/non-"No" values as affirmative, including placeholder strings
                                    if value is True or (isinstance(value, str) and value.lower() not in ['false', 'no']):
                                        is_emergency_exit = True
                                        break # Found the property, no need to check other properties in this set
                            if is_emergency_exit:
                                break # Found the property in this property set, no need to check other property sets

                if is_emergency_exit:
                    emergency_exit_doors.append(door)

        except Exception as e:
            # In a production environment, you might want to log this error
            # print(f"An error occurred while processing the IFC file: {e}")
            return [] # Return empty list on error

        return emergency_exit_doors

    '''
    main(
        function_requirements=function_requirements,
        function_name=function_name,
        python_code=python_code,
        log_level="INFO",
        lm_name="gemini-flash",
    )
