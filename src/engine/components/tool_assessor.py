from typing import Callable, List, Literal, Optional

import dspy

from src.config.agents import AGENT_CONFIGS, ToolAssessorConfig
from src.engine.components.code_act import CodeAct
from src.engine.schemas import Err, ModuleOutput, Ok
from src.engine.util import (
    _create_function_from_source_code,
    create_code_prefix,
    get_logger,
)


class ToolAssessmentSignature(dspy.Signature):
    """
    Assess whether a Python function meets its requirements and functions correctly.
    Your role is simply to test the function and determine whether it works as intended; you are not responsible for its implementation.
    Ensure that you verify the accuracy of the type hints in the function signature.
    Do not import the function you are assessing; this will raise an error. This function has already been imported and can be used directly in your code.
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
        config: Optional[ToolAssessorConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.tool_assessor
        self.lm = lm or self.config.llm.get_llm()

        # Combine base tools with the generated tool
        self.tools = tools
        self.max_iters = self.config.max_iters
        self.tool_assessor = CodeAct(
            signature=ToolAssessmentSignature,
            tools=self.tools,
            max_iters=self.max_iters,
        )
        self.log_level = self.config.log_level
        self.logger = get_logger(name="ToolAssessor", log_level=self.log_level)
        self.add_code_prefix = self.config.add_code_prefix

    def forward(
        self,
        function_name: str,
        function_requirements: str,
        path_ifc_model: str,
    ) -> ModuleOutput:
        self.output = ModuleOutput()
        self.logger.info(f"Starting ToolAssessor for function: {function_name}")

        self.lm = self.config.llm.get_llm()
        with dspy.context(lm=self.lm, adapter=self.config.llm.adapter):
            if self.add_code_prefix:
                code_prefix = create_code_prefix(
                    path_ifc_model=path_ifc_model,
                )
            else:
                code_prefix = None
            self.tool_assessor._update_code_prefix(code_prefix=code_prefix)

            try:
                prediction = self.tool_assessor(
                    function_name=function_name,
                    function_requirements=function_requirements,
                    path_ifc_model=path_ifc_model,
                )
                self.output.result.assessment_status = getattr(
                    prediction, "assessment_status", None
                )
                self.output.result.assessment_details = getattr(
                    prediction, "assessment_details", None
                )

                if (
                    self.output.result.assessment_status
                    and self.output.result.assessment_details
                ):
                    self.output.status = "success"

                else:
                    self.output.error_msg = (
                        f"Tool assessment failed for funtion: {function_name}"
                    )
                    self.logger.error(self.output.error_msg)

            except Exception as e:
                self.output.error_msg = f"An Exception occured during the CodeAct forward pass of the ToolAssessor:\nError:{e}\n"
                self.logger.error(self.output.error_msg)

            finally:
                self.output.update(
                    lm=self.lm,
                    cost_input_tokens=self.config.llm.cost_input_token,
                    cost_output_tokens=self.config.llm.cost_output_token,
                )
                return self.output


if __name__ == "__main__":
    import mlflow

    from src.config import TEST_IFC_PATH
    from src.tools.initial import (
        query_ifcopenshell_docs,
        web_search,
    )

    def main(
        function_requirements: str,
        function_name: str,
        python_code: str,
    ):
        from typing import cast

        # setup mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("ToolAssessor")

        # setup the primordial tools
        primordial_tools = [web_search, query_ifcopenshell_docs]

        # Create the function from source code
        new_tool = _create_function_from_source_code(
            function_name=function_name, code=python_code
        )
        tools = primordial_tools
        if isinstance(new_tool, Ok):
            print(f"✓ Successfully created function: {function_name}")
            tools += [new_tool.value]

        elif isinstance(new_tool, Err):
            print(f"There was an error creating the new tool: {new_tool.error}")
            return

        # setup the tool assessor
        tool_assessor = ToolAssessor(
            tools=tools,
        )

        # assess the tool
        output = cast(
            ModuleOutput,
            tool_assessor(
                function_name=function_name,
                function_requirements=function_requirements,
                path_ifc_model=TEST_IFC_PATH,
            ),
        )
        print(f"Result:\n{output.model_dump_json(indent=2)}")

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
    )
