"""
Multi-agent tool creation system for generating and validating IFC-related functions.

This module provides a complete pipeline for creating, testing, and correcting Python functions
that work with IFC (Industry Foundation Classes) files using the IfcOpenShell library.

The system uses three CodeAct-based agents:
- ToolProgrammer: Generates initial function implementations based on requirements
- ToolAssessor: Tests and evaluates generated functions through code execution
- ToolCorrector: Improves functions based on assessment feedback

Key features:
- CodeAct-based agents that create and execute code iteratively
- Each agent manages its own Python interpreter internally
- Iterative improvement with up to max_iter correction cycles
- Direct testing and formal LLM-based assessment
- Integration with MLFlow for tracking and logging
- Support for various parameter types and default values
"""

# %% Imports
# =============== Imports and config =============== #
import sys
from typing import Callable, Dict, Optional

import dspy
import mlflow

from src.config import (
    AGENT_CONFIGS,
    ROOT_PATH,
)
from src.engine.components.tool_assessor import ToolAssessor
from src.engine.components.tool_corrector import ToolCorrector
from src.engine.components.tool_programmer import ToolProgrammer
from src.engine.schemas.module_output import ModuleOutput
from src.engine.tools.primordial import (
    query_ifcopenshell_documentation,
    web_search,
)
from src.engine.util import _create_function_from_source_code, get_logger

# Set up the path
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)


class ToolCreator(dspy.Module):
    def __init__(
        self,
        additional_authorized_functions: Dict[str, Callable] = {
            "web_search": web_search,
            "query_ifcopenshell_documentation": query_ifcopenshell_documentation,
        },
        config=None,
        callbacks=None,
        llm: Optional[dspy.LM] = None,  # Optional override
    ):
        super().__init__(callbacks)
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.tool_creator

        # Use provided LLM or get from config
        self.lm = llm or self.config.llm.get_llm()
        dspy.configure(lm=self.lm)
        self.log_level = self.config.log_level
        self.logger = get_logger(name="ToolCreator", log_level=self.log_level)
        self.max_iter = self.config.max_iter
        self.function_boilerplate = self.config.function_boilerplate
        self.add_code_prefix = self.config.add_code_prefix

        # Store authorized functions for use in assessor when needed
        self.additional_authorized_functions = additional_authorized_functions
        self.primordial_tools = [
            tool for name, tool in self.additional_authorized_functions.items()
        ]

        self.logger.debug(
            f"Primordial tools available for ToolCreator sub-agents: {', '.join([getattr(tool, '__name__', str(tool)) for tool in self.primordial_tools])}"
        )

        # Instantiate the sub agents - they use their own configs from AGENT_CONFIGS
        self.tool_programmer = ToolProgrammer(
            tools=self.primordial_tools,
            config=self.config.tool_programmer,
        )
        self.tool_corrector = ToolCorrector(
            tools=self.primordial_tools,
            config=self.config.tool_corrector,
        )

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        path_ifc_model: str,
    ) -> ModuleOutput:
        """
        Create a new tool using a multi-agent system with iterative improvement.

        This function implements a complete pipeline for generating, testing, and refining
        Python functions that work with IFC files. The system uses three specialized agents:

        The workflow:
        1. ToolProgrammer generates initial function code based on requirements
        2. Function is dynamically wrapped to create a testable tool
        3. ToolAssessor evaluates the function through direct testing and LLM assessment
        4. ToolCorrector improves the function based on assessment feedback
        5. Process repeats until success or max_iter limit is reached

        Args:
            function_requirements: Detailed description of what the function should do
            function_name: Name for the generated function
            path_ifc_model: Path to IFC file used for testing the generated function

        Returns:
            ModuleOutput containing:
            - result.python_code: Generated function code (if successful)
            - result.assessment_status: "ok" or "needs_improvement"
            - result.assessment_details: Detailed assessment feedback
            - status: "success" or "error"
            - error_msg: Error description (if status is "error")
        """

        with mlflow.start_span(
            name=f"tool_creation_{function_name}",
            span_type="TOOL_CREATION",
        ) as span:
            # --- Step 1: Set up the system --- #
            output = ModuleOutput(status="error")

            # Set initial span attributes
            span.set_attribute("function_name", function_name)
            span.set_attribute("path_ifc_model", path_ifc_model)
            span.set_attribute("function_requirements", function_requirements)

            self.logger.info(f"Starting the creation of the tool: {function_name}")

            # --- Step 2: Create initial function --- #
            with mlflow.start_span(name="ToolProgrammer", span_type="MODULE"):
                self.logger.info("Creating initial function")
                output_tool_programmer = self.tool_programmer.forward(
                    function_requirements=function_requirements,
                    function_name=function_name,
                    path_ifc_model=path_ifc_model,
                    function_boilerplate=self.function_boilerplate,
                )

                function_implementation: str = (
                    output_tool_programmer.result.function_implementation or ""
                )
                if output_tool_programmer.status == "error":
                    error_msg = (
                        output_tool_programmer.error_msg
                        or f"ToolProgrammer could not create the function. An Unknown error occurred while trying to create the tool: {function_name}."
                    )
                    self.logger.error(error_msg)
                    output.error_msg = error_msg
                    return output
                else:
                    self.logger.info("Initial function created successfully.")
                    self.logger.debug(
                        f"Initial function code: \n\n---\n{function_implementation}\n\n---"
                    )

            # Reset iteration counter before starting the new assess/correct loop
            self.iter = 0

            # --- Step 3: Iterative improvement loop --- #
            while self.iter < self.max_iter:
                self.iter += 1

                with mlflow.start_span(
                    name=f"tool_improvement_iter_{self.iter}",
                    span_type="CHAIN",
                ):
                    # Step 3.1: Create enhanced assessor with dynamic tool
                    self.logger.info("Assessing the generated code.")
                    try:
                        new_tool = _create_function_from_source_code(
                            function_name=function_name,
                            code=function_implementation,
                        )

                        # Create ToolAssessor with primordial tools and the generated tool
                        # The CodeAct-based assessor will create its own Python interpreter internally
                        tools = self.primordial_tools + [new_tool]
                        tool_assessor = ToolAssessor(
                            tools=tools, config=self.config.tool_assessor
                        )
                        self.logger.info(
                            "✓ ToolAssessor created with new tool to test."
                        )

                    except Exception as e:
                        self.logger.error(
                            f"✗ Failed to create ToolAssessor. Error: {str(e)}"
                        )
                        self.logger.error(
                            f"Code that failed: {function_implementation}"
                        )
                        continue

                    # Step 3.2: Assess if the function works properly
                    with mlflow.start_span(name="ToolAssessor", span_type="MODULE"):
                        try:
                            self.logger.info("Starting the tool assessment.")

                            output_tool_assessor = tool_assessor.forward(
                                function_name=function_name,
                                function_requirements=function_requirements,
                                path_ifc_model=path_ifc_model,
                            )
                            self.logger.debug(
                                f"✓ Assessment completed: {output_tool_assessor.result.assessment_status}"
                            )
                            self.logger.debug(
                                f"Assessment details: {output_tool_assessor.result.assessment_details}"
                            )
                        except Exception as e:
                            self.logger.error(f"✗ Assessment failed: {str(e)}")
                            continue

                    # Step 3.3: If the assessment is good, update the ouput and exit the loop
                    if output_tool_assessor.result.assessment_status == "ok":
                        self.logger.info(
                            f"🎉 Function passed assessment after {self.iter} iterations!"
                        )
                        output.result.function_implementation = function_implementation
                        output.status = "success"
                        output.result.assessment_status = (
                            output_tool_assessor.result.assessment_status
                        )
                        output.result.assessment_details = (
                            output_tool_assessor.result.assessment_details
                        )
                        break

                    # Step 3.4: If the assessment is not satisfactory, call the ToolCorrector
                    elif self.iter < self.max_iter:
                        with mlflow.start_span(
                            name="ToolCorrector",
                            span_type="MODULE",
                        ):
                            self.logger.debug(
                                "Code not good enough yet; trying to correct the function."
                            )

                            output_tool_corrector = self.tool_corrector.forward(
                                function_description=function_requirements,
                                function_name=function_name,
                                path_ifc_model=path_ifc_model,
                                current_function_implementation=function_implementation,
                                detailed_function_assessment=output_tool_assessor.result.assessment_details
                                or "No assessment available.",
                            )

                            if output_tool_corrector.status == "error":
                                self.logger.error("✗ Correction failed.")
                                continue
                            else:
                                function_implementation = (
                                    output_tool_corrector.result.function_implementation
                                    or ""
                                )
                                self.logger.info("✓ Function corrected")
                                self.logger.debug(
                                    f"New function implementation:\n{function_implementation}"
                                )
                    else:
                        self.logger.debug("⚠️  Maximum iterations reached")

            # Set final span outputs and attributes
            span.set_inputs(
                {
                    "function_name": function_name,
                    "function_requirements": function_requirements,
                    "path_ifc_model": path_ifc_model,
                }
            )
            span.set_outputs(
                {
                    "status": output.status,
                    "function_implementation": output.result.function_implementation
                    or "No implementation generated",
                    "assessment_status": output.result.assessment_status or "unknown",
                    "assessment_details": output.result.assessment_details
                    or "No assessment details",
                    "iterations_used": self.iter,
                    "max_iterations": self.max_iter,
                    "error_msg": output.error_msg or "",
                }
            )
            span.set_attributes(output.result.model_dump())
            span.set_attribute("iterations_used", self.iter)
            span.set_attribute("max_iterations", self.max_iter)

            # Set MLflow tags for easy filtering and analysis
            mlflow.update_current_trace(
                tags={
                    "status": output.status,
                    "function_name": function_name,
                    "assessment_status": output.result.assessment_status or "unknown",
                    "iterations_used": str(self.iter),
                    "max_iterations": str(self.max_iter),
                    "success": str(output.status == "success"),
                }
            )

            # Return the result (good or bad)
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
