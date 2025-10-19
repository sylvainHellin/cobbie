"""
BAML-based TestAndImprove implementation to replace DSPy version.
Maintains the exact workflow architecture while using clean BAML union types.

Key Architecture Preservation:
- ToolAssessor: Tests function WITHOUT seeing implementation (black-box testing)
- ToolCorrector: Improves function based on assessment feedback
- CodeCleaner: Fixes syntax errors when function creation fails
- Iterative loop: Multiple assessment/correction cycles up to max_iter
"""

import re
import time
from typing import Dict, Any, Optional, List, Callable, Union

import mlflow
from baml_client import b
from baml_client.types import (
    CodeAction,
    AssessmentResult,
    ImprovedImplementation,
    CleanedCode,
    TestAndImproveSuccess,
    TestAndImproveError
)

from src.config.agents import TestAndImproveConfig
from src.engine.util import (
    _create_function_from_source_code,
    get_logger
)
from src.engine.util.baml_common import (
    BamlComponentBase,
    run_baml_function_with_metrics,
    log_code_execution_to_mlflow
)


class TestAndImproveBAML(BamlComponentBase):
    """
    BAML-based TestAndImprove that assesses and iteratively improves Python functions.

    Maintains the exact same workflow as the DSPy version:
    1. ToolAssessor tests function without seeing implementation
    2. ToolCorrector improves based on assessment feedback
    3. CodeCleaner fixes syntax errors when needed
    4. Iterative assessment/correction loop

    Returns:
        - TestAndImproveSuccess: Function successfully tested and improved
        - TestAndImproveError: Process failed or couldn't achieve success
    """

    def __init__(
        self,
        config: Optional[TestAndImproveConfig] = None,
        log_level: str = "INFO",
        max_iterations: int = 2,
    ):
        # Initialize base component with tools and interpreter
        super().__init__(
            log_level=log_level,
            max_iterations=max_iterations,
        )

        # Store configuration
        self.config = config

        # Initialize iteration counter
        self.iter = 0

        self.logger.info("BAML TestAndImprove initialized")

    def add_function_to_interpreter(self, function_name: str, function_obj: Callable):
        """
        Dynamically add a new function to the Python interpreter.

        This is needed when functions are created during test execution
        and need to be made available to the CodeAct execution environment.

        Args:
            function_name: Name of the function to add
            function_obj: The function object to add
        """
        self.additional_authorized_functions[function_name] = function_obj

        # Reinitialize the Python interpreter with the updated functions
        self._setup_interpreter()

        self.logger.info(f"Added function '{function_name}' to Python interpreter")

    def _clean_code_blocks(self, code: str) -> str:
        """
        Remove code blocks wrapped in ```python ... ``` or ``` ... ``` from the code.

        Args:
            code: The code string that may contain code block markers

        Returns:
            Cleaned code string without code block markers
        """
        # Pattern to match code blocks with optional language specification
        pattern = r"```(?:python)?\s*\n(.*?)\n```"

        # Find all code blocks
        matches = re.findall(pattern, code, re.DOTALL)

        if matches:
            # If code blocks are found, extract the content from the first/main block
            cleaned_code = matches[0].strip()
            self.logger.info("Removed code block markers from function implementation")
            return cleaned_code

        # If no code blocks found, return original code
        return code

    def _handle_code_cleaning(
        self,
        faulty_code: str,
        error_msg: str
    ) -> tuple[str, bool]:
        """
        Handle code cleaning using BAML CodeCleaner.

        Args:
            faulty_code: The code that needs cleaning
            error_msg: The error message describing the issue

        Returns:
            Tuple of (cleaned_code, success)
        """
        try:
            self.logger.info("Attempting to clean faulty code with BAML CodeCleaner")

            result, collector = run_baml_function_with_metrics(
                "CodeCleaner",
                b.CodeCleaner,
                faulty_code=faulty_code,
                error_message=error_msg,
                mlflow_tags={
                    "operation": "code_cleaning",
                    "error_type": "syntax_or_compilation"
                }
            )

            if isinstance(result, CleanedCode) and result.success:
                cleaned_code = self._clean_code_blocks(result.function_implementation)
                self.logger.info("✓ Code cleaned successfully by BAML CodeCleaner")
                self.logger.debug(f"Cleaning reasoning: {result.reasoning}")
                return cleaned_code, True
            else:
                self.logger.warning("BAML CodeCleaner failed to clean the code")
                return faulty_code, False

        except Exception as e:
            self.logger.error(f"BAML CodeCleaner crashed: {str(e)}")
            return faulty_code, False

    def _create_function_and_setup_assessor(
        self,
        function_name: str,
        function_implementation: str
    ) -> tuple[Any, bool]:
        """
        Create function from source code and setup ToolAssessor with dynamic tools.

        Args:
            function_name: Name of the function to create
            function_implementation: Source code of the function

        Returns:
            Tuple of (tool_assessor, success) where tool_assessor is the configured assessor
        """
        try:
            # Create function from source code
            creation_result = _create_function_from_source_code(
                function_name=function_name,
                code=function_implementation,
            )

            if creation_result.is_err():
                return None, False

            new_tool = creation_result.unwrap()

            # Add the new function to additional_authorized_functions so it's available in the interpreter
            # Use a unique name that includes iteration to avoid conflicts
            unique_function_name = f"{function_name}_iter_{self.iter}"
            self.additional_authorized_functions[unique_function_name] = new_tool
            self.additional_authorized_functions[function_name] = new_tool  # Keep original name for backward compatibility

            # Force clear any existing Python interpreter instance to ensure fresh namespace
            if hasattr(self, 'python_interpreter'):
                delattr(self, 'python_interpreter')

            # Reinitialize the Python interpreter to include the new function
            self._setup_interpreter()

            # Verify the function is properly available in the interpreter
            try:
                # Test that the function is accessible
                test_result = self.python_interpreter(f"print('Function {function_name} available:', callable({function_name}))")
                self.logger.debug(f"Function availability test: {test_result}")
            except Exception as verify_error:
                self.logger.warning(f"Function verification failed: {verify_error}")

            # Create tools list combining primordial tools with the generated tool
            tools = list(self.additional_authorized_functions.values())

            # Generate tool documentation for BAML
            tools_docs = self._generate_tools_docs_for_list(tools)

            # Create simple assessor configuration
            assessor_config = {
                "tools": tools_docs,
                "function_name": function_name
            }

            self.logger.info("✓ Function created and ToolAssessor setup completed")
            return assessor_config, True

        except Exception as e:
            self.logger.error(f"Failed to create function and setup ToolAssessor: {str(e)}")
            return None, False

    def _generate_tools_docs_for_list(self, tools: List) -> str:
        """
        Generate tool documentation for a specific list of tools.

        Args:
            tools: List of tool functions

        Returns:
            Formatted documentation string
        """
        docs = []
        for tool in tools:
            try:
                import inspect
                sig = inspect.signature(tool)
                docstring = inspect.getdoc(tool) or "No documentation"

                # Clean up docstring formatting
                clean_docstring = docstring.strip().replace('\n', ' ')
                docs.append(f"def {tool.__name__}{sig}:\n    '''{clean_docstring}'''")
            except Exception as e:
                self.logger.warning(f"Could not get docs for {getattr(tool, '__name__', 'unknown')}: {e}")
                docs.append(f"def {getattr(tool, '__name__', 'unknown')}():\n    '''No documentation available'''")

        return "\n\n".join(docs)

    def _perform_assessment(
        self,
        function_name: str,
        function_requirements: str,
        path_ifc_model: str,
        assessor_config: Dict[str, Any]
    ) -> tuple[Optional[AssessmentResult], bool]:
        """
        Perform function assessment using BAML ToolAssessor with CodeAct pattern.

        Args:
            function_name: Name of the function to assess
            function_requirements: Requirements for the function
            path_ifc_model: Path to IFC model for testing
            assessor_config: Configuration including available tools

        Returns:
            Tuple of (assessment_result, success)
        """
        try:
            self.logger.info(f"Starting assessment for function: {function_name}")

            # Initialize assessment loop
            previous_attempts = []
            max_assessor_iterations = 10  # Configurable limit for assessment iterations

            for iteration in range(max_assessor_iterations):
                self.logger.debug(f"Assessor iteration {iteration + 1}/{max_assessor_iterations}")

                # Prepare previous context
                previous_context = "\n".join(previous_attempts[-3:]) if previous_attempts else None

                result, collector = run_baml_function_with_metrics(
                    "ToolAssessor",
                    b.ToolAssessor,
                    function_name=function_name,
                    function_requirements=function_requirements,
                    path_ifc_model=path_ifc_model,
                    available_tools=assessor_config["tools"],
                    previous_attempts=previous_context,
                    mlflow_tags={
                        "operation": "function_assessment",
                        "iteration": self.iter,
                        "assessor_iteration": iteration + 1
                    }
                )

                # Process result based on type
                if isinstance(result, AssessmentResult):
                    # Assessment complete
                    self.logger.info(f"✅ Assessment completed: {result.assessment_status}")
                    if result.test_execution_log:
                        self.logger.debug(f"Test execution log: {result.test_execution_log}")
                    return result, True

                elif isinstance(result, CodeAction):
                    # Execute test code and continue
                    try:
                        execution_start = time.time()
                        output = self.python_interpreter(result.python_code)
                        execution_time = time.time() - execution_start

                        # Log code execution
                        log_code_execution_to_mlflow(
                            component_name="ToolAssessor",
                            code=result.python_code,
                            output=output or "No output",
                            execution_time=execution_time,
                            success=True
                        )

                        # Add to previous attempts
                        execution_result = f"Code: {result.python_code}\nResult: {output}"
                        previous_attempts.append(execution_result)
                        self.logger.debug(f"Executed assessment code, continuing to next iteration")

                    except Exception as e:
                        execution_time = time.time() - execution_start if 'execution_start' in locals() else 0
                        error_msg = f"Code: {result.python_code}\nError: {str(e)}"

                        # Log failed execution
                        log_code_execution_to_mlflow(
                            component_name="ToolAssessor",
                            code=result.python_code,
                            output="",
                            execution_time=execution_time,
                            success=False,
                            error_msg=str(e)
                        )

                        self.logger.error(f"Assessment code execution failed: {str(e)}")
                        previous_attempts.append(error_msg)

                        # Continue with error information as context
                        continue

                else:
                    self.logger.error(f"ToolAssessor returned unexpected result type: {type(result)}")
                    return None, False

            # Max iterations reached without final assessment
            self.logger.warning(f"ToolAssessor reached max iterations ({max_assessor_iterations}) without final assessment")
            return None, False

        except Exception as e:
            self.logger.error(f"ToolAssessor crashed: {str(e)}")
            return None, False

    def _perform_correction(
        self,
        function_requirements: str,
        function_name: str,
        current_function_implementation: str,
        detailed_assessment: str,
        path_ifc_model: str
    ) -> tuple[Optional[str], bool]:
        """
        Perform function correction using BAML ToolCorrector with CodeAct pattern.

        Args:
            function_requirements: Requirements for the function
            function_name: Name of the function
            current_function_implementation: Current source code
            detailed_assessment: Assessment feedback
            path_ifc_model: Path to IFC model for testing

        Returns:
            Tuple of (improved_implementation, success)
        """
        try:
            self.logger.info(f"Starting correction for function: {function_name}")

            # Generate tool documentation for correction
            tools_docs = self._generate_tools_docs()

            # Initialize correction loop
            previous_attempts = []
            max_corrector_iterations = 10  # Configurable limit for correction iterations

            for iteration in range(max_corrector_iterations):
                self.logger.debug(f"Corrector iteration {iteration + 1}/{max_corrector_iterations}")

                # Prepare previous context
                previous_context = "\n".join(previous_attempts[-3:]) if previous_attempts else None

                result, collector = run_baml_function_with_metrics(
                    "ToolCorrector",
                    b.ToolCorrector,
                    function_requirements=function_requirements,
                    function_name=function_name,
                    current_function_implementation=current_function_implementation,
                    detailed_assessment=detailed_assessment,
                    path_ifc_model=path_ifc_model,
                    available_tools=tools_docs,
                    previous_attempts=previous_context,
                    mlflow_tags={
                        "operation": "function_correction",
                        "iteration": self.iter,
                        "corrector_iteration": iteration + 1
                    }
                )

                # Process result based on type
                if isinstance(result, ImprovedImplementation):
                    # Correction complete
                    improved_implementation = self._clean_code_blocks(result.function_implementation)
                    self.logger.info(f"✅ Function corrected successfully")
                    if result.changes_summary:
                        self.logger.debug(f"Changes summary: {result.changes_summary}")
                    return improved_implementation, True

                elif isinstance(result, CodeAction):
                    # Execute correction code and continue
                    try:
                        execution_start = time.time()
                        output = self.python_interpreter(result.python_code)
                        execution_time = time.time() - execution_start

                        # Log code execution
                        log_code_execution_to_mlflow(
                            component_name="ToolCorrector",
                            code=result.python_code,
                            output=output or "No output",
                            execution_time=execution_time,
                            success=True
                        )

                        # Add to previous attempts
                        execution_result = f"Code: {result.python_code}\nResult: {output}"
                        previous_attempts.append(execution_result)
                        self.logger.debug(f"Executed correction code, continuing to next iteration")

                    except Exception as e:
                        execution_time = time.time() - execution_start if 'execution_start' in locals() else 0
                        error_msg = f"Code: {result.python_code}\nError: {str(e)}"

                        # Log failed execution
                        log_code_execution_to_mlflow(
                            component_name="ToolCorrector",
                            code=result.python_code,
                            output="",
                            execution_time=execution_time,
                            success=False,
                            error_msg=str(e)
                        )

                        self.logger.error(f"Correction code execution failed: {str(e)}")
                        previous_attempts.append(error_msg)

                        # Continue with error information as context
                        continue

                else:
                    self.logger.error(f"ToolCorrector returned unexpected result type: {type(result)}")
                    return None, False

            # Max iterations reached without final correction
            self.logger.warning(f"ToolCorrector reached max iterations ({max_corrector_iterations}) without final correction")
            return None, False

        except Exception as e:
            self.logger.error(f"ToolCorrector crashed: {str(e)}")
            return None, False

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        path_ifc_model: str,
        function_implementation: str,
        initial_assessment: Optional[str] = None,
    ) -> TestAndImproveSuccess | TestAndImproveError:
        """
        Main execution method for TestAndImprove using BAML patterns.

        Args:
            function_requirements: Detailed description of what the function should do
            function_name: Name for the generated function
            path_ifc_model: Path to IFC file used for testing the generated function
            function_implementation: The source code of this function
            initial_assessment: Optional initial assessment describing known issues to fix

        Returns:
            TestAndImproveSuccess: Function successfully tested and improved
            TestAndImproveError: Process failed or couldn't achieve success
        """
        # Reset iteration counter and initialize state
        self.iter = 0
        current_function_implementation = function_implementation
        final_assessment_status = None

        run_start_time = time.time()

        with mlflow.start_span(name="TestAndImprove_BAML_Run", span_type="CHAIN") as run_span:
            # Set run-level metadata
            run_span.set_inputs({
                "function_requirements": function_requirements[:200] + "..." if len(function_requirements) > 200 else function_requirements,
                "function_name": function_name,
                "path_ifc_model": path_ifc_model,
                "max_iterations": self.max_iterations,
                "has_initial_assessment": initial_assessment is not None
            })

            run_span.set_attributes({
                "component": "TestAndImprove_BAML",
                "architecture": "BAML_Union_Types",
                "model_path": path_ifc_model or "no_model"
            })

            self.logger.info(f"Starting BAML TestAndImprove for function: {function_name}")

            # Track all collectors for metrics aggregation
            collectors: List = []

            try:
                # --- Handle initial assessment if provided --- #
                if initial_assessment:
                    self.logger.info("Initial assessment provided, starting with correction phase")
                    self.iter += 1

                    with mlflow.start_span(name=f"{self.iter}_initial_correction", span_type="CHAIN"):
                        improved_implementation, success = self._perform_correction(
                            function_requirements=function_requirements,
                            function_name=function_name,
                            current_function_implementation=current_function_implementation,
                            detailed_assessment=initial_assessment,
                            path_ifc_model=path_ifc_model
                        )

                        if success and improved_implementation:
                            current_function_implementation = improved_implementation
                            self.logger.info("✓ Initial correction completed")
                        else:
                            return TestAndImproveError(
                                error_message="Initial correction failed",
                                iterations_completed=self.iter,
                                final_assessment_status="initial_correction_failed"
                            )

                # --- Iterative improvement loop --- #
                while self.iter < self.max_iterations:
                    self.iter += 1

                    with mlflow.start_span(name=f"{self.iter}_pass", span_type="CHAIN") as iteration_span:
                        self.logger.info(f"Starting iteration {self.iter}")

                        # Step 1: Create function and setup ToolAssessor
                        assessor_config, setup_success = self._create_function_and_setup_assessor(
                            function_name=function_name,
                            function_implementation=current_function_implementation
                        )

                        if not setup_success:
                            # Try to clean the code if function creation failed
                            cleaned_code, cleaning_success = self._handle_code_cleaning(
                                faulty_code=current_function_implementation,
                                error_msg="Function creation failed"
                            )

                            if cleaning_success:
                                current_function_implementation = cleaned_code
                                # Retry function creation with cleaned code
                                assessor_config, setup_success = self._create_function_and_setup_assessor(
                                    function_name=function_name,
                                    function_implementation=cleaned_code
                                )

                            if not setup_success:
                                return TestAndImproveError(
                                    error_message=f"✗ Failed to create function and setup ToolAssessor in iteration {self.iter}",
                                    iterations_completed=self.iter,
                                    final_assessment_status=final_assessment_status,
                                    partial_function_implementation=current_function_implementation
                                )

                        # Step 2: Perform assessment
                        assessment_result, assessment_success = self._perform_assessment(
                            function_name=function_name,
                            function_requirements=function_requirements,
                            path_ifc_model=path_ifc_model,
                            assessor_config=assessor_config
                        )

                        if not assessment_success or not assessment_result:
                            return TestAndImproveError(
                                error_message=f"Assessment failed in iteration {self.iter}",
                                iterations_completed=self.iter,
                                final_assessment_status=final_assessment_status,
                                partial_function_implementation=current_function_implementation
                            )

                        # Store assessment status for potential error reporting
                        final_assessment_status = assessment_result.assessment_status

                        # Step 3: Check if assessment passed
                        if assessment_result.assessment_status == "ok":
                            self.logger.info(f"🎉 Function passed assessment after {self.iter} iterations!")

                            total_time = time.time() - run_start_time
                            mlflow.log_metric("test_and_improve_iterations_used", self.iter)
                            mlflow.log_metric("test_and_improve_total_time", total_time)

                            run_span.set_outputs({
                                "status": "success",
                                "assessment_status": assessment_result.assessment_status,
                                "iterations_used": self.iter,
                                "total_time_seconds": total_time
                            })

                            return TestAndImproveSuccess(
                                function_implementation=current_function_implementation,
                                assessment_details=assessment_result.assessment_details,
                                iterations_used=self.iter,
                                total_time_seconds=total_time
                            )

                        # Step 4: Perform correction if assessment failed
                        self.logger.info("Function needs improvement, attempting correction")

                        # Build comprehensive assessment for correction
                        assessment_for_correction = assessment_result.assessment_details or "No assessment available."

                        # If we had an initial assessment, ensure it's still addressed
                        if initial_assessment and self.iter <= 2:  # First few iterations
                            assessment_for_correction = f"ORIGINAL ISSUE TO FIX:\n{initial_assessment}\n\nCURRENT ASSESSMENT FINDINGS:\n{assessment_for_correction}\n\nPRIORITY: Ensure the original issue is addressed while also fixing any new issues discovered."

                        improved_implementation, correction_success = self._perform_correction(
                            function_requirements=function_requirements,
                            function_name=function_name,
                            current_function_implementation=current_function_implementation,
                            detailed_assessment=assessment_for_correction,
                            path_ifc_model=path_ifc_model
                        )

                        if correction_success and improved_implementation:
                            current_function_implementation = improved_implementation
                            self.logger.info(f"✓ Correction completed in iteration {self.iter}")
                        else:
                            self.logger.error(f"Correction failed in iteration {self.iter}")

                # Max iterations reached without success
                total_time = time.time() - run_start_time
                self.logger.warning(f"TestAndImprove reached max iterations ({self.max_iterations}) without success")

                return TestAndImproveError(
                    error_message=(
                        f"Failed to improve function: {function_name}. "
                        f"Completed {self.iter} iterations without success."
                    ),
                    iterations_completed=self.iter,
                    final_assessment_status=final_assessment_status,
                    partial_function_implementation=current_function_implementation
                )

            except Exception as e:
                self.logger.error(f"BAML TestAndImprove crashed: {str(e)}")
                run_span.set_outputs({
                    "status": "crashed",
                    "error_message": str(e),
                    "error_type": type(e).__name__
                })

                return TestAndImproveError(
                    error_message=f"BAML TestAndImprove crashed: {str(e)}",
                    iterations_completed=self.iter,
                    final_assessment_status=final_assessment_status,
                    partial_function_implementation=current_function_implementation
                )
