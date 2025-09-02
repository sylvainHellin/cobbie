from typing import Callable, Dict

import dspy
import mlflow

from src.config import (
    AGENT_CONFIGS,
)
from src.engine.components.tool_assessor import ToolAssessor
from src.engine.components.tool_corrector import ToolCorrector
from src.engine.schemas.module_output import ModuleOutput
from src.engine.tools.primordial import (
    query_ifcopenshell_documentation,
    web_search,
)
from src.engine.util import (
    _create_function_from_source_code,
    _extract_function_metadata,
    get_logger,
)


class ToolDebugger(dspy.Module):
    def __init__(
        self,
        additional_authorized_functions: Dict[str, Callable] = {
            "web_search": web_search,
            "query_ifcopenshell_documentation": query_ifcopenshell_documentation,
        },
        config=None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.tool_debugger

        # Use provided LLM or get from config
        self.lm = self.config.llm.get_llm()
        dspy.configure(lm=self.lm)
        self.log_level = self.config.log_level
        self.logger = get_logger(name="ToolDebugger", log_level=self.log_level)
        self.max_iter = self.config.max_iter
        self.add_code_prefix = self.config.add_code_prefix

        # Store authorized functions for use in assessor when needed
        self.additional_authorized_functions = additional_authorized_functions
        self.primordial_tools = [
            tool for name, tool in self.additional_authorized_functions.items()
        ]

        self.logger.debug(
            f"Primordial tools available for ToolDebugger sub-agents: {', '.join([getattr(tool, '__name__', str(tool)) for tool in self.primordial_tools])}"
        )

        # Instantiate the sub agents - they use their own configs from AGENT_CONFIGS
        self.tool_corrector = ToolCorrector(
            tools=self.primordial_tools,
            config=self.config.tool_corrector,
        )

    def _build_function_requirements(self, metadata) -> str:
        """
        Build function requirements from extracted metadata.

        Args:
            metadata: PythonFunctionMetadata object containing function details

        Returns:
            String describing the function requirements
        """
        requirements = []

        # Add function signature
        args_str = ", ".join([f"{arg}" for arg in metadata.args])
        signature = f"`{metadata.name}({args_str})"
        if metadata.return_type:
            signature += f" -> {metadata.return_type}"
        signature += "`"

        requirements.append(f"Function signature:\n{signature}")

        # Add docstring if available
        if metadata.docstring and metadata.docstring.strip():
            requirements.append(f"\nDescription:\n{metadata.docstring.strip()}")
        else:
            requirements.append(
                f"\nDescription:\nFunction {metadata.name} - requirements should be inferred from the function signature and context."
            )

        # Add argument details if available
        if metadata.args:
            requirements.append("\nArguments:")
            for i, arg in enumerate(metadata.args):
                default_info = ""
                if i >= len(metadata.args) - len(metadata.defaults):
                    default_idx = i - (len(metadata.args) - len(metadata.defaults))
                    default_info = f" (default: {metadata.defaults[default_idx]})"
                requirements.append(f"- {arg}{default_info}")

        # Add return type if available
        if metadata.return_type:
            requirements.append(f"\nReturn type: {metadata.return_type}")

        return "\n".join(requirements)

    def _build_comprehensive_assessment(
        self, original_assessment: str, all_issues_found: list, iteration: int
    ) -> str:
        """
        Build a comprehensive assessment that tracks the original issue and any new issues found.

        Args:
            original_assessment: The initial assessment describing the original bug
            all_issues_found: List of all assessment details found across iterations
            iteration: Current iteration number

        Returns:
            Comprehensive assessment string that preserves original context
        """
        assessment_parts = []

        # Always start with the original issue context
        assessment_parts.append(f"ORIGINAL ISSUE TO FIX:\n{original_assessment}")

        # Add any additional issues discovered during debugging
        if len(all_issues_found) > 1:
            assessment_parts.append("\nADDITIONAL ISSUES DISCOVERED DURING DEBUGGING:")
            for i, issue in enumerate(all_issues_found[1:], 1):
                assessment_parts.append(f"{i}. {issue}")

        # Add iteration context
        assessment_parts.append(
            f"\nITERATION {iteration}: Ensure BOTH the original issue and any new issues are addressed."
        )
        assessment_parts.append(
            "Priority: The original issue MUST be fixed. Additional issues should also be addressed if possible."
        )

        return "\n".join(assessment_parts)

    def _build_final_assessment_summary(
        self, original_assessment: str, all_issues_found: list, max_iterations: int
    ) -> str:
        """
        Build a final assessment summary for failed debugging attempts.

        Args:
            original_assessment: The initial assessment describing the original bug
            all_issues_found: List of all assessment details found across iterations
            max_iterations: Maximum iterations that were attempted

        Returns:
            Final assessment summary preserving all discovered issues
        """
        summary_parts = []

        summary_parts.append(f"DEBUGGING FAILED AFTER {max_iterations} ITERATIONS")
        summary_parts.append(
            f"\nORIGINAL ISSUE (still needs to be fixed):\n{original_assessment}"
        )

        if len(all_issues_found) > 1:
            summary_parts.append("\nADDITIONAL ISSUES DISCOVERED:")
            for i, issue in enumerate(all_issues_found[1:], 1):
                summary_parts.append(f"{i}. {issue}")

        summary_parts.append(
            "\nNEXT STEPS: Ensure the original issue is addressed first, then tackle additional issues."
        )

        return "\n".join(summary_parts)

    def forward(
        self,
        function_name: str,
        faulty_function_implementation: str,
        initial_assessment: str,
        path_ifc_model: str,
    ) -> ModuleOutput:
        """
        Debug and fix a faulty tool using a multi-agent system with iterative improvement.

        This function implements a complete pipeline for debugging, correcting, and testing
        Python functions that work with IFC files. The system uses two specialized agents:

        The workflow:
        1. Extract function requirements from the faulty function's signature and docstring
        2. Start with a faulty function implementation and initial assessment
        3. ToolCorrector attempts to fix the function based on the assessment feedback
        4. Function is dynamically wrapped to create a testable tool
        5. ToolAssessor evaluates the corrected function through direct testing and LLM assessment
        6. Process repeats until success or max_iter limit is reached

        Args:
            function_name: Name of the function being debugged
            faulty_function_implementation: Current faulty function code (should include signature and docstring)
            initial_assessment: Initial assessment describing what's wrong with the function
            path_ifc_model: Path to IFC file used for testing the corrected function

        Returns:
            ModuleOutput containing:
            - result.function_implementation: Corrected function code (if successful)
            - result.assessment_status: "ok" or "needs_improvement"
            - result.assessment_details: Detailed assessment feedback
            - status: "success" or "error"
            - error_msg: Error description (if status is "error")
        """

        with mlflow.start_span(
            name=f"ToolDebugger_{function_name}",
            span_type="MODULE",
        ) as span:
            # --- Step 1: Set up the system --- #
            output = ModuleOutput(status="error")

            # --- Step 1.1: Extract function requirements from signature and docstring --- #
            try:
                function_metadata = _extract_function_metadata(
                    faulty_function_implementation, function_name
                )

                # Build function requirements from metadata
                function_requirements = self._build_function_requirements(
                    function_metadata
                )

                self.logger.info(
                    "The function requirements were successfully extracted."
                )
                self.logger.debug(
                    f"Extracted function requirements: {function_requirements}"
                )

            except Exception as e:
                error_msg = f"Failed to extract function metadata: {str(e)}"
                self.logger.error(error_msg)
                output.error_msg = error_msg
                return output

            # Set initial span attributes
            span.set_attribute("function_name", function_name)
            span.set_attribute("path_ifc_model", path_ifc_model)
            span.set_attribute("function_requirements", function_requirements)
            span.set_attribute("initial_assessment", initial_assessment)
            span.set_attribute(
                "faulty_function_implementation", faulty_function_implementation
            )

            self.logger.info(f"Starting the debugging of the tool: {function_name}")

            # Start with the faulty implementation
            current_function_implementation = faulty_function_implementation
            original_assessment = initial_assessment
            current_assessment = initial_assessment
            all_issues_found = [initial_assessment]  # Track all issues discovered

            # Reset iteration counter before starting the correction loop
            self.iter = 0

            # --- Step 2: Iterative improvement loop --- #
            while self.iter < self.max_iter:
                self.iter += 1

                with mlflow.start_span(
                    name=f"tool_debug_iter_{self.iter}",
                    span_type="CHAIN",
                ):
                    # Step 2.1: Correct the function based on current assessment
                    with mlflow.start_span(
                        name="ToolCorrector",
                        span_type="MODULE",
                    ):
                        self.logger.info(
                            f"Iteration {self.iter}: Correcting the function based on assessment"
                        )

                        prediction = self.tool_corrector(
                            function_description=function_requirements,
                            function_name=function_name,
                            path_ifc_model=path_ifc_model,
                            current_function_implementation=current_function_implementation,
                            detailed_function_assessment=current_assessment,
                        )

                        status = getattr(prediction, "status", None)
                        error_msg = getattr(prediction, "error_msg", None)

                        if status == "error":
                            error_msg = (
                                error_msg
                                or f"ToolCorrector failed during iteration {self.iter}."
                            )
                            self.logger.error(error_msg)
                            output.error_msg = error_msg
                            continue
                        else:
                            current_function_implementation = (
                                result.function_implementation
                                if (result := getattr(prediction, "result", None))
                                else None
                            )
                            if current_function_implementation is None:
                                output.status = "error"
                                output.error_msg = "Could not extract the current function implementation from the output."
                                self.logger.error(output.error_msg)
                                continue
                            else:
                                self.logger.info("✓ Function corrected")
                                self.logger.debug(
                                    f"Corrected function implementation:\n{current_function_implementation}"
                                )

                    # Step 2.2: Create enhanced assessor with dynamic tool
                    self.logger.info("Assessing the corrected code.")
                    try:
                        new_tool = _create_function_from_source_code(
                            function_name=function_name,
                            code=current_function_implementation,
                        )

                        # Create ToolAssessor with primordial tools and the corrected tool
                        # The CodeAct-based assessor will create its own Python interpreter internally
                        tools = self.primordial_tools + [new_tool]
                        tool_assessor = ToolAssessor(
                            tools=tools, config=self.config.tool_assessor
                        )
                        self.logger.info(
                            "✓ ToolAssessor created with corrected tool to test."
                        )

                    except Exception as e:
                        self.logger.error(
                            f"✗ Failed to create ToolAssessor. Error: {str(e)}"
                        )
                        self.logger.error(
                            f"Code that failed: {current_function_implementation}"
                        )
                        continue

                    # Step 2.3: Assess if the corrected function works properly
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

                    # Step 2.4: If the assessment is good, update the output and exit the loop
                    if output_tool_assessor.result.assessment_status == "ok":
                        self.logger.info(
                            f"🎉 Function debugging successful after {self.iter} iterations!"
                        )
                        output.result.function_implementation = (
                            current_function_implementation
                        )
                        output.status = "success"
                        output.result.assessment_status = (
                            output_tool_assessor.result.assessment_status
                        )
                        output.result.assessment_details = (
                            output_tool_assessor.result.assessment_details
                        )
                        break

                    # Step 2.5: If the assessment is not satisfactory and we haven't reached max iterations
                    elif self.iter < self.max_iter:
                        self.logger.debug(
                            "Code still needs improvement; will try another correction iteration."
                        )
                        # Track new issues while preserving original assessment context
                        new_issues = (
                            output_tool_assessor.result.assessment_details
                            or "No assessment available."
                        )
                        if new_issues not in all_issues_found:
                            all_issues_found.append(new_issues)

                        # Build comprehensive assessment that includes original issue and any new findings
                        current_assessment = self._build_comprehensive_assessment(
                            original_assessment, all_issues_found, self.iter
                        )
                    else:
                        self.logger.debug(
                            "⚠️  Maximum iterations reached without success"
                        )
                        output.result.function_implementation = (
                            current_function_implementation
                        )
                        output.result.assessment_status = (
                            output_tool_assessor.result.assessment_status
                        )
                        output.result.assessment_details = (
                            output_tool_assessor.result.assessment_details
                        )

            # If we exited the loop without success, still record what we have
            if output.status == "error" and not output.error_msg:
                output.error_msg = (
                    f"Failed to fix function after {self.max_iter} iterations"
                )
                output.result.function_implementation = current_function_implementation
                output.result.assessment_status = "needs_improvement"
                # Provide comprehensive assessment including original issue
                final_assessment = self._build_final_assessment_summary(
                    original_assessment, all_issues_found, self.max_iter
                )
                output.result.assessment_details = final_assessment

            # Set final span outputs and attributes
            span.set_inputs(
                {
                    "function_name": function_name,
                    "faulty_function_implementation": faulty_function_implementation,
                    "initial_assessment": initial_assessment,
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

            # Return the result (good or bad)
            return output


if __name__ == "__main__":
    from src.config import TEST_IFC_PATH

    def main(
        function_name: str,
        faulty_function_implementation: str,
        initial_assessment: str,
    ):
        # setup mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("ToolDebugger")

        # setup the tool debugger
        tool_debugger = ToolDebugger()

        # debug the tool
        result = tool_debugger(
            function_name=function_name,
            faulty_function_implementation=faulty_function_implementation,
            initial_assessment=initial_assessment,
            path_ifc_model=TEST_IFC_PATH,
        )

        print(f"Tool debugging result: {result}")

        ##########################################

    # Test data - debugging a faulty IFC analysis function
    function_name = "get_room_count"

    faulty_function_implementation = '''def get_room_count(ifc_file_path: str) -> int:
    """
    Count the total number of IfcSpace entities in an IFC model that represent rooms.

    Args:
        ifc_file_path: Path to the IFC file

    Returns:
        Number of spaces/rooms found in the model
    """
    import ifcopenshell

    model = ifcopenshell.open(ifc_file_path)
    # Bug: using wrong entity type - should be IfcSpace, not IfcRoom
    rooms = model.by_type("IfcRoom")
    return len(rooms)
'''

    initial_assessment = """
The function has a critical bug: it's looking for 'IfcRoom' entities instead of 'IfcSpace' entities.
In IFC schema, rooms are typically represented as IfcSpace entities, not IfcRoom entities.
This will likely return 0 for most IFC files even when they contain spaces/rooms.
The function should use model.by_type("IfcSpace") instead of model.by_type("IfcRoom").
"""

    main(
        function_name=function_name,
        faulty_function_implementation=faulty_function_implementation,
        initial_assessment=initial_assessment,
    )
