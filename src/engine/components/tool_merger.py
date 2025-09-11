from typing import Callable, List, Optional, cast

import dspy
import mlflow

from src.config.agents import (
    AGENT_CONFIGS,
    FUNCTION_BOILERPLATE,
    ToolMergerConfig,
)
from src.engine.components import CodeAct
from src.engine.components.test_and_improve import TestAndImprove
from src.engine.schemas import ModuleOutput
from src.engine.tools.primordial import query_ifcopenshell_documentation, web_search
from src.engine.util import create_code_prefix, get_logger


class SignatureMergeTools(dspy.Signature):
    """
    As a Python programming expert, you have been tasked with merging two Python functions with overlapping functionality.

    Your function implementation must:
        - Return proper data structures (e.g. lists and dictionaries) rather than formatted strings.
        - Be well documented with docstrings and type hints.
        - Be explicit regarding assumptions. For instance, if your function uses properties relating to particular BIM authoring software (e.g. PSet_Revit_Dimensions for an IFC model exported from Revit), this should be mentioned in the docstring.
    """

    # inputs
    function_requirements: str = dspy.InputField(
        desc="Detailed description of what the merged function should do and its requirements."
    )
    function_name: str = dspy.InputField()

    path_ifc_model: str = dspy.InputField(
        desc="Path to an IFC file for testing the function."
    )

    source_code_first_function: str = dspy.InputField(
        desc="The source code of the first function to be merged."
    )

    source_code_second_function: str = dspy.InputField(
        desc="The source code of the second function to be merged."
    )

    # outputs
    function_implementation: str = dspy.OutputField(
        desc="your implementation of the new Python function."
    )


class InitialMerger(dspy.Module):
    """Module to merge two existing Python functions into one (without refining)."""

    def __init__(
        self,
        tools: List[Callable] = [
            query_ifcopenshell_documentation,
            web_search,
        ],
        config: Optional[ToolMergerConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.tool_merger
        self.lm = lm or self.config.llm.get_llm()

        self.tools = tools
        self.max_iters = self.config.max_iters
        self.tools_merger = CodeAct(
            signature=SignatureMergeTools,
            tools=tools,
            max_iters=self.max_iters,
        )
        self.log_level = self.config.log_level
        self.logger = get_logger(name="InitialMerger", log_level=self.log_level)
        self.add_code_prefix = self.config.add_code_prefix

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        path_ifc_model: str,
        source_code_first_function: str,
        source_code_second_function: str,
    ) -> ModuleOutput:
        with dspy.context(lm=self.lm):
            self.logger.info(f"Starting ToolMerger for function: {function_name}")
            self.output = ModuleOutput()

            if self.add_code_prefix:
                code_prefix = create_code_prefix(
                    path_ifc_model=path_ifc_model,
                    imports_boilerplate=FUNCTION_BOILERPLATE,
                )
            else:
                code_prefix = None

            self.tools_merger._update_code_prefix(code_prefix=code_prefix)

            try:
                prediction = self.tools_merger(
                    function_name=function_name,
                    function_requirements=function_requirements,
                    path_ifc_model=path_ifc_model,
                    source_code_first_function=source_code_first_function,
                    source_code_second_function=source_code_second_function,
                )
                # Check if we got valid python code
                function_implementation = getattr(
                    prediction, "function_implementation", None
                )

                if function_implementation is not None:
                    self.logger.info(f"Function '{function_name}' created successfully")
                    self.logger.debug(f"function code:\n{function_implementation}\n")
                    self.output.status = "success"
                    self.output.result.function_implementation = function_implementation
                    self.output.result.function_name = function_name
                    self.output.result.function_requirements = function_requirements

                else:
                    self.output.error_msg = (
                        f"No valid code generated for function: {function_name}"
                    )
                    self.logger.error(self.output.error_msg)

            except Exception as e:
                self.output.error_msg = f"An Exception occured during the CodeAct forward pass:\nError:\n{e}"
                self.logger.error(self.output.error_msg)

            finally:
                self.output.update_lm_metrics(
                    lm=self.lm,
                    cost_input_tokens=self.config.llm.cost_input_token,
                    cost_output_tokens=self.config.llm.cost_output_token,
                )
        return self.output


class ToolsMerger(dspy.Module):
    """Module to merge two existing Python functions into one ; test and refine the output."""

    def __init__(
        self,
        tools: List[Callable] = [
            query_ifcopenshell_documentation,
            web_search,
        ],
        config: Optional[ToolMergerConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.tool_merger
        self.lm = lm or self.config.llm.get_llm()

        self.tools = tools
        self.max_iters = self.config.max_iters
        self.tools_merger = InitialMerger()
        self.test_and_improve = TestAndImprove()
        self.log_level = self.config.log_level
        self.logger = get_logger(name="ToolMerger", log_level=self.log_level)
        self.add_code_prefix = self.config.add_code_prefix

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        path_ifc_model: str,
        source_code_first_function: str,
        source_code_second_function: str,
    ) -> ModuleOutput:
        with dspy.context(lm=self.lm):
            self.logger.info(f"Starting ToolMerger for function: {function_name}")
            self.output = ModuleOutput()

            self.output = cast(
                ModuleOutput,
                self.tools_merger(
                    function_name=function_name,
                    function_requirements=function_requirements,
                    path_ifc_model=path_ifc_model,
                    source_code_first_function=source_code_first_function,
                    source_code_second_function=source_code_second_function,
                ),
            )

            # Test and debug the new tool if necessary
            if self.output.status == "success":
                assert self.output.result.function_implementation is not None, (
                    "Logical error: status of initial merger is a success, but the function_implementation is None."
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

                # Update the fields of the output
                self.output.result.assessment_details = (
                    output_test_and_improve.result.assessment_details
                )
                self.output.result.assessment_status = (
                    output_test_and_improve.result.assessment_status
                )
                self.output.combine_cost(output=output_test_and_improve)

                if output_test_and_improve.status == "success":
                    self.output.result.function_implementation = (
                        output_test_and_improve.result.function_implementation
                    )
                else:
                    self.output.status = "error"
                    self.output.error_msg = output_test_and_improve.error_msg

        return self.output


if __name__ == "__main__":
    from src.config import TEST_IFC_PATH

    def main():
        """Test the ToolMerger with sample functions."""
        # Setup MLflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("ToolMerger")

        # deactivate caching
        # dspy.configure_cache(enable_disk_cache=False)

        # Initialize the ToolMerger
        tool_merger = ToolsMerger()

        # Sample function implementations to merge
        function_name = "get_element_dimensions_by_type"

        function_requirements = """
        Create a function that combines element retrieval by type with dimensional property extraction.
        The merged function should:
        1. Retrieve all elements of a specified IFC type from the model
        2. Extract dimensional properties (width, height, length) from each element
        3. Return a comprehensive list with element details and their dimensions
        4. Handle cases where elements may not have dimensional properties
        5. Include element GUID, name, and confidence scores for dimension extraction
        """

        # First function: get elements by type
        source_code_first_function = '''def get_elements_by_type(
    ifc_file_path: str, ifc_type: str
) -> List[ifcopenshell.entity_instance]:
    """
    Retrieves elements of a specified IFC type from an IFC model.

    Args:
        ifc_file_path (str): The path to the IFC file.
        ifc_type (str): The IFC entity type to retrieve (e.g., 'IfcWall', 'IfcBeam', 'IfcDoor').

    Returns:
        List[ifcopenshell.entity_instance]: A list of IfcOpenShell entity instances
                                            of the specified type.
    """
    try:
        ifc_file = ifcopenshell.open(ifc_file_path)
        elements = ifc_file.by_type(ifc_type)
        return elements
    except Exception as e:
        print(f"Error opening IFC file or retrieving elements: {e}")
        return []'''

        # Second function: get element dimensions (simplified version)
        source_code_second_function = '''def get_element_dimensions(
    ifc_file_path: str,
    element_type: str,
    dimension_names: List[str] = ['Width', 'Height', 'Length']
) -> List[Dict[str, Any]]:
    """
    Extracts dimensional properties from IFC elements of a specified type.

    Args:
        ifc_file_path: Path to the IFC file
        element_type: IFC element type
        dimension_names: List of dimension names to extract

    Returns:
        List of dictionaries with element details and dimensions
    """
    try:
        ifc_file = ifcopenshell.open(ifc_file_path)
        elements = ifc_file.by_type(element_type)

        results = []
        for element in elements:
            element_name = getattr(element, 'Name', 'Unnamed')
            element_guid = getattr(element, 'GlobalId', 'Unknown')

            dimensions = {}
            for dim_name in dimension_names:
                try:
                    psets = ifcopenshell.util.element.get_psets(element)
                    dim_value = None
                    for pset_dict in psets.values():
                        if dim_name in pset_dict:
                            dim_value = pset_dict[dim_name]
                            break
                    dimensions[dim_name] = dim_value
                except:
                    dimensions[dim_name] = None

            results.append({
                'element_name': element_name,
                'element_guid': element_guid,
                'dimensions': dimensions
            })

        return results
    except Exception as e:
        print(f"Error processing elements: {e}")
        return []'''

        # Run the tool merger
        print(f"Testing ToolMerger with function: {function_name}")
        print("=" * 60)

        output = cast(
            ModuleOutput,
            tool_merger(
                function_name=function_name,
                function_requirements=function_requirements,
                path_ifc_model=TEST_IFC_PATH,
                source_code_first_function=source_code_first_function,
                source_code_second_function=source_code_second_function,
            ),
        )

        print(f"Tool merger result: {output.model_dump_json(indent=2)}")

    # Run the test
    main()
