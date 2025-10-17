"""
BAML-based ToolCreator implementation to replace DSPy version.
Uses CodeAct pattern with union types for clean flow control and direct token tracking.
"""

import re
import time
from typing import Dict, Any, Optional, Tuple, List

import mlflow
from baml_client import b
from baml_py import Collector
from baml_client.types import CodeAction, FunctionImplementation

from src.config.agents import FUNCTION_BOILERPLATE
from src.engine.schemas import ModuleOutput
from src.engine.util import get_logger
from src.engine.components.test_and_improve import TestAndImprove
from src.engine.util.baml_common import (
    BamlComponentBase,
    run_baml_function_with_metrics,
    log_code_execution_to_mlflow
)


class ToolCreatorBAML(BamlComponentBase):
    """
    BAML-based ToolCreator that generates Python functions using IfcOpenShell library.

    Follows CodeAct pattern with union types (CodeAction | FunctionImplementation) for
    clean flow control, replacing DSPy's complex state management.
    """

    def __init__(
        self,
        max_iterations: int = 10,
        log_level: str = "INFO",
        path_ifc_model: str = "",
        add_code_prefix: bool = False,
    ):
        super().__init__(
            log_level=log_level,
            max_iterations=max_iterations,
            path_ifc_model=path_ifc_model,
        )

        self.add_code_prefix = add_code_prefix
        self.function_boilerplate = FUNCTION_BOILERPLATE

        # Initialize TestAndImprove for validation
        self.test_and_improve = TestAndImprove()

    def _clean_code_blocks(self, code: str) -> str:
        """
        Remove code blocks wrapped in ```python ... ``` or ``` ... ``` from the code.

        Args:
            code: The code string that may contain code block markers

        Returns:
            Cleaned code string without code block markers
        """
        # Pattern to match code blocks with optional language specification
        # Matches ```python\n...``` or ```\n...``` patterns
        pattern = r"```(?:python)?\s*\n(.*?)\n```"

        # Find all code blocks
        matches = re.findall(pattern, code, re.DOTALL)

        if matches:
            # If code blocks are found, extract the content from the first/main block
            # Usually there's just one main code block containing the function
            cleaned_code = matches[0].strip()
            self.logger.info("Removed code block markers from function implementation")
            return cleaned_code

        # If no code blocks found, return original code
        return code

    def _execute_code_action(
        self,
        code_action: CodeAction,
        iteration: int
    ) -> Tuple[str, bool, Optional[str]]:
        """
        Execute a CodeAction and return the result.

        Args:
            code_action: The CodeAction containing Python code to execute
            iteration: Current iteration number for logging

        Returns:
            Tuple of (execution_result, is_final_error, error_message)
        """
        try:
            code_to_execute = code_action.python_code

            # Add code prefix if available
            code_prefix = self._prepare_code_prefix()
            if code_prefix and self.add_code_prefix:
                code_to_execute = f"{code_prefix}\n{code_to_execute}"

            self.logger.debug(f"Executing code (iteration {iteration}): {code_to_execute[:200]}...")
            self.logger.debug(f"Code reasoning: {code_action.thoughts}")

            execution_start = time.time()
            output = self.python_interpreter(code_to_execute)
            execution_time = time.time() - execution_start

            # Log successful execution to MLflow
            log_code_execution_to_mlflow(
                component_name="ToolCreator",
                code=code_to_execute,
                output=output or "No output",
                execution_time=execution_time,
                success=True
            )

            result_msg = f"Code: {code_action.python_code}\nResult: {output}"
            return result_msg, False, None

        except Exception as e:
            execution_time = time.time() - execution_start if 'execution_start' in locals() else 0
            error_msg = f"Code: {code_action.python_code}\nError: {str(e)}"

            # Log failed execution to MLflow
            log_code_execution_to_mlflow(
                component_name="ToolCreator",
                code=code_action.python_code,
                output="",
                execution_time=execution_time,
                success=False,
                error_msg=str(e)
            )

            self.logger.error(f"Code execution failed (iteration {iteration}): {str(e)}")
            return error_msg, True, str(e)

    def _extract_function_implementation(
        self,
        conversation_history: str,
        function_name: str
    ) -> Tuple[Optional[str], Collector]:
        """
        Extract function implementation from conversation history using BAML CodeExtractor.

        Args:
            conversation_history: The conversation history to extract from
            function_name: Name of the function to extract

        Returns:
            Tuple of (extracted_function_implementation, collector)
        """
        try:
            result, collector = run_baml_function_with_metrics(
                "CodeExtractor",
                b.CodeExtractor,
                function_name,
                conversation_history,
                mlflow_tags={
                    "extraction_method": "conversation_history",
                    "target_function": function_name
                }
            )

            if isinstance(result, FunctionImplementation):
                function_impl = self._clean_code_blocks(result.function_implementation)
                self.logger.info("Successfully extracted function implementation from conversation history")
                return function_impl, collector
            else:
                self.logger.warning("CodeExtractor returned unexpected type")
                return None, collector

        except Exception as e:
            self.logger.error(f"Failed to extract function from conversation history: {str(e)}")
            return None, Collector(name="failed-extraction")

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        path_ifc_model: str,
    ) -> ModuleOutput:
        """
        Main execution method for ToolCreator using BAML and CodeAct pattern.

        Args:
            function_requirements: Detailed description of what the function should do
            function_name: Name for the generated function
            path_ifc_model: Path to IFC file used for testing the generated function

        Returns:
            ModuleOutput containing the generated function or error information
        """
        # Initialize output
        output = ModuleOutput(status="error")

        run_start_time = time.time()
        tools_docs = self._generate_tools_docs()

        with mlflow.start_span(name="ToolCreator_BAML_Run", span_type="CHAIN") as run_span:
            # Set run-level metadata
            run_span.set_inputs({
                "function_requirements": function_requirements[:200] + "..." if len(function_requirements) > 200 else function_requirements,
                "function_name": function_name,
                "path_ifc_model": path_ifc_model,
                "max_iterations": self.max_iterations,
                "tools_count": len(self.additional_authorized_functions)
            })

            run_span.set_attributes({
                "component": "ToolCreator_BAML",
                "architecture": "CodeAct",
                "model_path": path_ifc_model or "no_model"
            })

            self.logger.info(f"Starting BAML ToolCreator for function: {function_name}")

            # Track all collectors for metrics aggregation
            collectors: List[Collector] = []
            conversation_history: List[str] = []

            try:
                # Main CodeAct loop
                for iteration in range(self.max_iterations):
                    with mlflow.start_span(name=f"Iteration_{iteration + 1}", span_type="CHAIN") as iteration_span:
                        self.logger.debug(f"Iteration {iteration + 1}/{self.max_iterations}")

                        # Prepare previous context
                        previous_context = "\n".join(conversation_history[-3:]) if conversation_history else None

                        # Call BAML ToolCreator
                        result, collector = run_baml_function_with_metrics(
                            "ToolCreator",
                            b.ToolCreator,
                            function_requirements=function_requirements,
                            function_name=function_name,
                            function_boilerplate=self.function_boilerplate,
                            path_ifc_model=path_ifc_model,
                            available_tools=tools_docs,
                            previous_attempts=previous_context,
                            mlflow_tags={
                                "iteration": iteration + 1,
                                "max_iterations": self.max_iterations,
                                "has_previous_context": previous_context is not None
                            }
                        )
                        collectors.append(collector)

                        # Process result based on type
                        if isinstance(result, FunctionImplementation):
                            # Tool creation complete
                            function_implementation = self._clean_code_blocks(result.function_implementation)
                            output.result.function_implementation = function_implementation
                            output.status = "success"

                            total_time = time.time() - run_start_time
                            self.logger.info(f"BAML ToolCreator completed in {iteration + 1} iterations")

                            # Log completion metrics
                            mlflow.log_metric("tool_creator_iterations_used", iteration + 1)
                            mlflow.log_metric("tool_creator_total_time", total_time)

                            # Set final outputs
                            run_span.set_outputs({
                                "status": "success",
                                "function_implementation": function_implementation[:300] + "..." if len(function_implementation) > 300 else function_implementation,
                                "iterations_used": iteration + 1,
                                "total_time_seconds": total_time
                            })

                            # Aggregate and log total token usage
                            total_input = sum(col.last.usage.input_tokens or 0 for col in collectors if col.last and col.last.usage)
                            total_output = sum(col.last.usage.output_tokens or 0 for col in collectors if col.last and col.last.usage)
                            mlflow.log_metric("tool_creator_total_input_tokens", total_input)
                            mlflow.log_metric("tool_creator_total_output_tokens", total_output)

                            break

                        elif isinstance(result, CodeAction):
                            # Execute code action
                            execution_result, is_final_error, error_msg = self._execute_code_action(
                                result, iteration
                            )
                            conversation_history.append(execution_result)

                            if is_final_error:
                                # Critical execution error
                                output.error_msg = f"Code execution failed: {error_msg}"
                                break

                        else:
                            # Unexpected result type
                            self.logger.warning(f"Unexpected result type: {type(result)}")
                            conversation_history.append(f"Unexpected result: {str(result)}")

                # If we completed the loop with a function implementation, run TestAndImprove
                if output.status == "success" and output.result.function_implementation:
                    with mlflow.start_span(name="TestAndImprove_Validation", span_type="CHAIN") as validation_span:
                        self.logger.info("Running TestAndImprove validation")

                        try:
                            test_result = self.test_and_improve(
                                function_implementation=output.result.function_implementation,
                                function_requirements=function_requirements,
                                function_name=function_name,
                                path_ifc_model=path_ifc_model,
                            )

                            if test_result.status == "success":
                                output.result = test_result.result
                                output.combine_lm_metrics(other_output=test_result)
                                self.logger.info("✓ TestAndImprove validation passed")
                            else:
                                self.logger.warning(f"TestAndImprove validation failed: {test_result.error_msg}")
                                output.error_msg = f"TestAndImprove validation failed: {test_result.error_msg}"
                                output.status = "error"

                            validation_span.set_outputs({
                                "validation_status": test_result.status,
                                "assessment_status": test_result.result.assessment_status,
                                "validation_error": test_result.error_msg
                            })

                        except Exception as e:
                            self.logger.error(f"TestAndImprove validation crashed: {str(e)}")
                            output.error_msg = f"TestAndImprove validation crashed: {str(e)}"
                            output.status = "error"

                # If we didn't succeed, try fallback extraction
                if output.status != "success" and conversation_history:
                    self.logger.info("Attempting fallback function extraction from conversation history")

                    extracted_function, extraction_collector = self._extract_function_implementation(
                        "\n".join(conversation_history),
                        function_name
                    )
                    collectors.append(extraction_collector)

                    if extracted_function:
                        output.result.function_implementation = extracted_function
                        output.status = "success"
                        self.logger.info("✓ Successfully extracted function using fallback method")

                        run_span.set_outputs({
                            "status": "success_fallback",
                            "extraction_method": "fallback",
                            "function_implementation": extracted_function[:300] + "..." if len(extracted_function) > 300 else extracted_function
                        })

                # Final error if still no success
                if output.status != "success":
                    output.error_msg = (
                        f"Failed to create function: {function_name}. "
                        f"Completed {self.max_iterations} iterations without success."
                    )
                    run_span.set_outputs({
                        "status": "error",
                        "error_message": output.error_msg,
                        "iterations_completed": self.max_iterations
                    })

            except Exception as e:
                output.error_msg = f"BAML ToolCreator crashed: {str(e)}"
                self.logger.error(f"BAML ToolCreator crashed: {str(e)}")
                run_span.set_outputs({
                    "status": "crashed",
                    "error_message": str(e),
                    "error_type": type(e).__name__
                })

        return output


if __name__ == "__main__":
    # Test the BAML ToolCreator
    import os
    from dotenv import load_dotenv
    from src.config.main import TEST_IFC_PATH

    # Load environment variables
    load_dotenv()

    # Setup MLflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("ToolCreator_BAML")

    # Test data
    function_requirements = """
    Create a function that counts the total number of doors in an IFC model.
    The function should:
    1. Take an IFC file path as input
    2. Open the IFC model using ifcopenshell
    3. Find all door elements (IfcDoor)
    4. Return the count as an integer (not as a string)

    The function should handle errors gracefully and return accurate counts.
    """

    function_name = "count_doors"

    # Initialize and test the BAML ToolCreator
    tool_creator = ToolCreatorBAML(
        max_iterations=5,
        log_level="INFO",
        path_ifc_model=TEST_IFC_PATH,
        add_code_prefix=True
    )

    print(f"Testing BAML ToolCreator for function: {function_name}")
    print(f"Requirements: {function_requirements[:100]}...")

    result = tool_creator(
        function_requirements=function_requirements,
        function_name=function_name,
        path_ifc_model=TEST_IFC_PATH,
    )

    print(f"\nResult:")
    print(f"Status: {result.status}")
    if result.status == "success" and result.result.function_implementation:
        print(f"Function Implementation:")
        print(result.result.function_implementation)
    else:
        print(f"Error: {result.error_msg}")