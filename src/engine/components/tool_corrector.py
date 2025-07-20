from typing import Callable, List, Literal

import dspy

from src.engine.schemas import ModuleOutput, Result
from src.engine.util import get_logger, create_code_prefix

from .code_act import CodeAct


class ToolCorrectionSignature(dspy.Signature):
    """
    As an expert Python programmer, you have been tasked with correcting a given Python function implementation, which is not performing as expected.
    You are provided with the code of the current implementation, as well as a detailed assessment of the necessary improvements. Using this information, update the code of the current implementation.

    You are an action-oriented programmer. You write code, test it, and refine it. You have access to a Python interpreter and tools to query information from the Internet or the IfcOpenShell documentation.

    Your corrected function implementation must:
        - Return proper data structures (e.g., lists and dictionaries), not formatted strings.
        - Be well-documented with docstrings and type hints.
        - Be explicit regarding assumptions. For example, if your function involves using properties related to specific BIM authoring software, such as PSet_Revit_Dimensions for an IFC model exported from Revit, mention this in the docstring.

    Final recommendations:
        - The provided Python interpreter does not have a state, so you need to declare all the variables you need (e.g. the path to the ifc model).
        - When calling python_interpreter, format JSON arguments as single-line strings. Do NOT use triple quotes in JSON. Use escaped newlines instead.
        Example: {"python_code": "import ifcopenshell\\nprint('hello')"}
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
        add_boilerplate: bool = True,
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
        self.add_boilerplate = add_boilerplate

    def forward(
        self,
        function_description: str,
        function_name: str,
        path_ifc_model: str,
        current_function_implementation: str,
        detailed_function_assessment: str,
    ) -> ModuleOutput:
        if self.add_boilerplate:
            code_prefix = create_code_prefix(
                path_ifc_model=path_ifc_model,
            )
        else:
            code_prefix = None
        self.agent._update_code_prefix(code_prefix=code_prefix)

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
                result=Result(
                    function_implementation=output.new_function_implementation
                ),
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
            max_iters=10,
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
    function_description = "Create a function that calculates the total floor area of all spaces in an IFC model. The function should iterate through all IfcSpace entities and sum up their floor areas. It should handle cases where area information might be missing and return the total area in square meters."

    function_name = "calculate_total_floor_area"

    # A deliberately flawed implementation that needs correction
    current_function_implementation = "\nimport ifcopenshell\nimport ifcopenshell.util.element\nimport ifcopenshell.util.shape\nimport ifcopenshell.util.placement\nimport ifcopenshell.util.geolocation\nimport ifcopenshell.util.system\nimport ifcopenshell.geom\nimport math\nimport json\nfrom typing import Union, List, Dict, Any\n\ndef calculate_total_floor_area(path_ifc_model: str) -> float:\n    \"\"\"\n    Calculates the total floor area of all IfcSpace entities in an IFC model.\n\n    The function iterates through all IfcSpace entities, attempts to retrieve their\n    area from associated quantity sets (specifically 'BaseQuantities' or 'PSet_SpaceCommon'),\n    and sums them up. It handles cases where area information might be missing\n    by treating the area as 0 for that specific space.\n\n    Args:\n        path_ifc_model (str): The file path to the IFC model.\n\n    Returns:\n        float: The total floor area of all spaces in square meters.\n\n    Assumptions:\n        - Area information for IfcSpace entities is typically stored as 'IfcQuantityArea'\n          within a 'IfcQuantitySet' named 'BaseQuantities' or 'PSet_SpaceCommon'.\n        - The specific quantity names for area are commonly 'NetPlannedArea' or 'GrossPlannedArea'.\n          If these are not found, the function will attempt to find any 'IfcQuantityArea'\n          within the associated quantity sets.\n        - If no area quantity is found for a space, its area is considered 0.\n    \"\"\"\n    try:\n        ifc_file = ifcopenshell.open(path_ifc_model)\n    except Exception as e:\n        # Log the error and return 0.0 if the file cannot be opened\n        print(f\"Error opening IFC file: {e}\")\n        return 0.0\n\n    total_area = 0.0\n    spaces = ifc_file.by_type('IfcSpace')\n\n    if not spaces:\n        # No IfcSpace entities found, return 0.0\n        return 0.0\n\n    for space in spaces:\n        space_area = 0.0\n        \n        # Retrieve quantities associated with the space\n        quantities = ifcopenshell.util.element.get_quantities(space)\n        \n        # Prioritize 'BaseQuantities' as it's a common location for space areas\n        if 'BaseQuantities' in quantities:\n            for q_name, q_value in quantities['BaseQuantities'].items():\n                # Check if the quantity is an IfcQuantityArea and has a value\n                if isinstance(q_value, dict) and q_value.get('type') == 'IfcQuantityArea':\n                    # Prioritize specific area names like NetPlannedArea or GrossPlannedArea\n                    if q_name in ['NetPlannedArea', 'GrossPlannedArea']:\n                        space_area = q_value.get('value', 0.0)\n                        break # Found a specific area, no need to check others in this set\n                    elif space_area == 0.0: \n                        # If no specific area name found yet, take the first IfcQuantityArea\n                        space_area = q_value.get('value', 0.0)\n\n        # If area not found in 'BaseQuantities' or specific names,\n        # iterate through all other quantity sets to find any IfcQuantityArea\n        if space_area == 0.0:\n            for q_set_name, q_set_values in quantities.items():\n                if q_set_name == 'BaseQuantities': # Skip BaseQuantities as it was already checked\n                    continue\n                for q_name, q_value in q_set_values.items():\n                    if isinstance(q_value, dict) and q_value.get('type') == 'IfcQuantityArea':\n                        space_area = q_value.get('value', 0.0)\n                        break # Found an area in another quantity set\n                if space_area != 0.0:\n                    break # Stop searching if area is found\n\n        total_area += space_area\n\n    return total_area\n"

    detailed_function_assessment = "The function did not return a valid float for the total area. Received: Error executing calculate_total_floor_area: 'str' object has no attribute 'is_a'. This indicates a potential issue with calculation or return type."

    main(
        function_description=function_description,
        function_name=function_name,
        current_function_implementation=current_function_implementation,
        detailed_function_assessment=detailed_function_assessment,
        log_level="INFO",
        lm_name="gemini-flash",
    )
