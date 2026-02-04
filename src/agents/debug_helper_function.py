"""
Agent that debugs existing faulty helper functions.
Test and fix faulty helper functions from Cobbie executions resulting in a wrong answer.
"""

import os
import time
from contextlib import nullcontext
from pathlib import Path
from typing import List, Optional, Tuple

import mlflow
from baml_py.baml_py import Collector
from loguru import logger

from src.baml.baml_client.types import CodeAction, UpdatedHelperFunction
from src.config import DIRECTORY_IFC_MODELS_PATH
from src.schemas.agent_error import AgentError
from src.tools.initial import query_ifcopenshell_docs
from src.util import _execute_code_action, generate_tools_docs, setup_logger
from src.util.baml_retry import call_baml_with_retry
from src.util.python_executor import setup_interpreter
from src.agents import derive_binary_classification

setup_logger()


def _helper_function_debugger_iter(
    faulty_function_name: str,
    faulty_function_implementation: str,
    error_description: str,
    ifc_model_path: str,
    history_faulty_tool_use: Optional[str] = None,
    other_bim_models_for_testing: Optional[List[str]] = None,
    previous_attempts: Optional[str] = None,
    **kwargs,
) -> CodeAction | UpdatedHelperFunction | AgentError:
    """
    Execute a single iteration of the helper function debugger.

    This function represents one iteration of the debugging loop,
    calling the LLM to either generate test code or provide a fixed implementation.

    Args:
        faulty_function_name: Name of the identified faulty function
        faulty_function_implementation: Current (faulty) implementation of the function
        error_description: Detailed description of what's wrong with the function
        history_faulty_tool_use: History of iterations with the thought, code, result pattern of Cobbie, where the faulty tool was used to produce a wrong answer.
        other_bim_models_for_testing: Path to other BIM models for testing generalization
        ifc_model_path: Path to the IFC model where the failure occurred
        previous_attempts: Results from previous iterations
        **kwargs: Additional arguments for BAML function (including baml_options)

    Returns:
        CodeAction to continue debugging, UpdatedHelperFunction when complete, or AgentError on failure.
    """
    from src.baml.baml_client import b

    # Extract baml_options if provided for collector integration
    baml_options = kwargs.pop("baml_options", {})

    if baml_options:
        return call_baml_with_retry(
            lambda: b.with_options(**baml_options).HelperFunctionDebugger(
                faulty_function_name=faulty_function_name,
                faulty_function_implementation=faulty_function_implementation,
                history_faulty_tool_use=history_faulty_tool_use,
                other_bim_models_for_testing=other_bim_models_for_testing,
                error_description=error_description,
                ifc_model_path=ifc_model_path,
                previous_attempts=previous_attempts,
            ),
            context_name="HelperFunctionDebugger",
        )
    else:
        return call_baml_with_retry(
            lambda: b.HelperFunctionDebugger(
                faulty_function_name=faulty_function_name,
                faulty_function_implementation=faulty_function_implementation,
                history_faulty_tool_use=history_faulty_tool_use,
                other_bim_models_for_testing=other_bim_models_for_testing,
                error_description=error_description,
                ifc_model_path=ifc_model_path,
                previous_attempts=previous_attempts,
            ),
            context_name="HelperFunctionDebugger",
        )


def _debug_helper_function(
    faulty_function_name: str,
    faulty_function_implementation: str,
    error_description: str,
    ifc_model_path: str,
    other_bim_models_for_testing: Optional[List[str]] = None,
    history_faulty_tool_use: Optional[str] = None,
    max_iterations: int = 15,
    llm_name: str = "GLM-4.6",
    llm_provider: str = "zai",
    **kwargs,
) -> Tuple[UpdatedHelperFunction, str]:
    """
    Main helper function debugger orchestration with iteration loop.

    Orchestrates the CodeAct execution loop to debug and fix a faulty helper function
    by iteratively generating and executing Python code for testing and validation.

    Args:
        faulty_function_name: Name of the identified faulty function
        faulty_function_implementation: Current (faulty) implementation of the function
        error_description: Detailed description of what's wrong with the function
        ifc_model_path: Path to the IFC model where the failure occurred
        history_faulty_tool_use: the history of thoughts, code, results iteration of Cobbie
        other_bim_models_for_testing: Path to other IFC models for testing generalization
        max_iterations: Maximum number of iterations (default: 15)
        llm_name: LLM model name (default: "GLM-4.6")
        llm_provider: LLM provider (default: "zai")
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (UpdatedHelperFunction, execution_history) where execution_history contains
        the complete iteration-by-iteration trace of debugging
    """
    logger.info(f"Starting helper function debugging for: {faulty_function_name}")

    # Prepare tools for code execution
    tools = {
        "query_ifcopenshell_docs": query_ifcopenshell_docs,
    }

    # Prepare the paths to the other BIM models
    if other_bim_models_for_testing is None:
        # Get the absolute path to the BIM models directory
        bim_models_dir = Path(DIRECTORY_IFC_MODELS_PATH)

        if bim_models_dir.exists():
            # Find all .ifc files recursively in the directory
            ifc_files = []
            for root, _, files in os.walk(bim_models_dir):
                for file in files:
                    if file.endswith(".ifc"):
                        ifc_path = os.path.join(root, file)
                        # Exclude the current model being tested
                        if ifc_path != ifc_model_path:
                            ifc_files.append(ifc_path)

            if ifc_files:
                other_bim_models_for_testing = ifc_files
                logger.info(f"Found {len(ifc_files)} other BIM models for testing")
            else:
                other_bim_models_for_testing = []
                logger.warning("No other BIM models found in bim_models directory")
        else:
            other_bim_models_for_testing = []
            logger.warning(f"BIM models directory not found at {bim_models_dir}")

    # Setup stateful interpreter (persists across iterations)
    interpreter = setup_interpreter(ifc_model_path, tools)

    # Initialize execution history
    previous_attempts = ""

    # Initialize counters
    llm_calls = 0

    # Main debugging loop
    for iteration in range(max_iterations):
        iteration_start = time.time()

        # MLflow Iteration Span
        with mlflow.start_span(
            name=f"Iteration_{iteration + 1}", span_type="CHAIN"
        ) as iteration_span:
            # Extract token usage from collector for this iteration
            iteration_input_tokens = 0
            iteration_output_tokens = 0
            iteration_total_tokens = 0

            # MLflow LLM call span
            with mlflow.start_span(
                name=f"LLM_call_{iteration + 1}", span_type="LLM"
            ) as llm_span:
                llm_span.set_inputs(
                    {
                        "faulty_function_name": faulty_function_name,
                        "faulty_function_implementation": faulty_function_implementation,
                        "history_faulty_tool_use": history_faulty_tool_use,
                        "other_bim_models_for_testing": other_bim_models_for_testing,
                        "error_description": error_description,
                        "ifc_model_path": ifc_model_path,
                        "previous_attempts": previous_attempts,
                    }
                )

                result = _helper_function_debugger_iter(
                    faulty_function_name=faulty_function_name,
                    faulty_function_implementation=faulty_function_implementation,
                    error_description=error_description,
                    history_faulty_tool_use=history_faulty_tool_use,
                    other_bim_models_for_testing=other_bim_models_for_testing,
                    ifc_model_path=ifc_model_path,
                    previous_attempts=previous_attempts,
                    **kwargs,
                )

                iteration_duration = time.time() - iteration_start
                llm_calls += 1

                # Get collector from kwargs to extract token usage
                baml_options = kwargs.get("baml_options", {})
                collector = baml_options.get("collector")

                if collector and collector.last and collector.last.usage:
                    usage = collector.last.usage
                    iteration_input_tokens = usage.input_tokens or 0
                    iteration_output_tokens = usage.output_tokens or 0
                    iteration_total_tokens = (
                        iteration_input_tokens + iteration_output_tokens
                    )

                # Log BAML call metrics
                mlflow.log_metric(
                    f"latency_llm_call_{iteration + 1}", iteration_duration
                )

                llm_span.set_attributes(
                    {
                        "llm.provider": llm_provider,
                        "llm.model": llm_name,
                    }
                )

                # Log usage metrics
                llm_span.set_attributes(
                    {
                        "input_tokens": iteration_input_tokens,
                        "output_tokens": iteration_output_tokens,
                        "total_tokens": iteration_total_tokens,
                        "latency": iteration_duration,
                    }
                )

                # Log output with metrics
                if isinstance(result, CodeAction):
                    llm_span.set_outputs(
                        {
                            "result_type": "CodeAction",
                            "thoughts": result.thoughts,
                            "python_code": result.python_code,
                        }
                    )
                elif isinstance(result, UpdatedHelperFunction):
                    llm_span.set_outputs(
                        {
                            "result_type": "UpdatedHelperFunction",
                            "thoughts": result.thoughts,
                            "fixed_implementation": result.fixed_implementation,
                            "changes_summary": result.changes_summary,
                            "success": result.success,
                        }
                    )

            # Handle union type flow control
            if isinstance(result, UpdatedHelperFunction):
                logger.info(
                    f"Helper function debugging completed after {iteration + 1} iterations"
                )

                # Log final iteration metrics
                iteration_span.set_outputs(
                    {
                        "fixed_implementation": result.fixed_implementation,
                        "changes_summary": result.changes_summary,
                        "success": result.success,
                        "total_iterations": iteration + 1,
                        "llm_calls": llm_calls,
                        "iteration_success": True,
                        "final_iteration_input_tokens": iteration_input_tokens,
                        "final_iteration_output_tokens": iteration_output_tokens,
                        "final_iteration_total_tokens": iteration_total_tokens,
                    }
                )
                iteration_span.set_attributes(
                    {
                        "token_usage.final_iteration_input": iteration_input_tokens,
                        "token_usage.final_iteration_output": iteration_output_tokens,
                        "token_usage.final_iteration_total": iteration_total_tokens,
                    }
                )
                iteration_span.set_status("OK" if result.success else "ERROR")

                return result, previous_attempts

            elif isinstance(result, CodeAction):
                # Execute the code action
                current_attempt = _execute_code_action(
                    code_action=result,
                    iteration=iteration,
                    tools=tools,
                    model_path=ifc_model_path,
                    add_code_prefix=False,
                    interpreter=interpreter,
                )
                previous_attempts += f"\n{current_attempt}\n"

                iteration_span.set_attributes(
                    {
                        "token_usage.input_tokens": iteration_input_tokens,
                        "token_usage.output_tokens": iteration_output_tokens,
                        "token_usage.total_tokens": iteration_total_tokens,
                    }
                )

                iteration_span.set_status("OK")

                # Continue to next iteration
                continue

            else:
                # Handle unexpected result type
                error_msg = f"Unexpected result type: {type(result)}"
                logger.error(error_msg)
                previous_attempts += (
                    f"\n--- Iteration {iteration + 1} ---\nError:\n{error_msg}"
                )

                iteration_span.set_outputs(
                    {
                        "error_msg": error_msg,
                    }
                )
                iteration_span.set_attributes(
                    {
                        "token_usage.input_tokens": iteration_input_tokens,
                        "token_usage.output_tokens": iteration_output_tokens,
                        "token_usage.total_tokens": iteration_total_tokens,
                    }
                )
                iteration_span.set_status("ERROR")
                continue

    # Max iterations reached - return incomplete result
    logger.warning(
        f"Helper function debugger reached max iterations ({max_iterations}) without completion"
    )

    # Log final incomplete iteration span
    with mlflow.start_span(
        name="Max_Iterations_Reached", span_type="CHAIN"
    ) as final_span:
        final_span.set_inputs(
            {
                "max_iterations": max_iterations,
                "total_iterations_completed": max_iterations,
                "llm_calls": llm_calls,
            }
        )

        final_result = UpdatedHelperFunction(
            thoughts=f"Reached maximum iteration limit ({max_iterations}) without completing the fix. "
            f"Summary:\n"
            f"- Total iterations: {max_iterations}\n"
            f"- LLM calls: {llm_calls}\n\n"
            f"Last 3 attempts:\n" + "\n".join(previous_attempts.split("\n")[-30:])
            if previous_attempts
            else "No previous attempts",
            fixed_implementation="",
            changes_summary="Max iterations reached without successful fix",
            success=False,
            test_cases_provided="",
        )

        final_span.set_outputs(
            {
                "fixed_implementation": final_result.fixed_implementation,
                "success": final_result.success,
                "termination_reason": "max_iterations_reached",
            }
        )
        final_span.set_status("ERROR")

        return final_result, previous_attempts


def debug_helper_function(
    faulty_function_name: str,
    faulty_function_implementation: str,
    error_description: str,
    ifc_model_path: str,
    history_faulty_tool_use: Optional[str] = None,
    other_bim_models_for_testing: Optional[List[str]] = None,
    max_iterations: int = 15,
    llm_provider: str = "zai",
    llm_name: str = "GLM-4.6",
    **kwargs,
) -> Tuple[UpdatedHelperFunction, Collector, str]:
    """
    Execute helper function debugger with comprehensive metrics collection.

    Returns UpdatedHelperFunction, Collector, and execution history for performance tracking.

    Args:
        faulty_function_name: Name of the identified faulty function
        faulty_function_implementation: Current (faulty) implementation of the function
        error_description: Detailed description of what's wrong with the function
        ifc_model_path: Path to the IFC model where the failure occurred
        max_iterations: Maximum number of iterations (default: 15)
        other_bim_models_for_testing: Path to other BIM models for testing generalization
        history_faulty_tool_use: history of iteration with the thoughts, code, result pattern from Cobbie
        llm_provider: LLM provider (default: "zai")
        llm_name: LLM model name (default: "GLM-4.6")
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (UpdatedHelperFunction, Collector, execution_history) where execution_history
        contains the complete iteration-by-iteration trace of debugging
    """
    # Create collector for token tracking
    collector = Collector(name="HelperFunctionDebugger")

    # Add collector to kwargs for BAML calls
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    # Check if we're already in an MLflow run, if not start one
    active_run = mlflow.active_run()
    run_context_manager = (
        nullcontext()
        if active_run
        else mlflow.start_run(run_name="HelperFunctionDebugger")
    )

    with run_context_manager:
        # Log parameters to MLflow only if we created a new run
        if not active_run:
            mlflow.log_params(
                {
                    "component": "HelperFunctionDebugger",
                    "max_iterations": max_iterations,
                    "faulty_function_name": faulty_function_name,
                    "ifc_model_path": ifc_model_path,
                    "other_models_count": len(other_bim_models_for_testing)
                    if other_bim_models_for_testing
                    else 0,
                    "llm_provider": llm_provider,
                    "llm_model": llm_name,
                }
            )

        # Start MLflow span for the entire execution
        with mlflow.start_span(
            name="HelperFunctionDebugger", span_type="CHAIN"
        ) as debugger_span:
            # Set span inputs
            debugger_span.set_inputs(
                {
                    "faulty_function_name": faulty_function_name,
                    "faulty_function_implementation": faulty_function_implementation,
                    "history_faulty_tool_use": history_faulty_tool_use,
                    "error_description": error_description,
                    "ifc_model_path": ifc_model_path,
                    "max_iterations": max_iterations,
                }
            )

            # Execute helper function debugger
            start_time = time.time()
            final_result, execution_history = _debug_helper_function(
                faulty_function_name=faulty_function_name,
                faulty_function_implementation=faulty_function_implementation,
                history_faulty_tool_use=history_faulty_tool_use,
                other_bim_models_for_testing=other_bim_models_for_testing,
                error_description=error_description,
                ifc_model_path=ifc_model_path,
                max_iterations=max_iterations,
                llm_name=llm_name,
                llm_provider=llm_provider,
                **kwargs,
            )
            execution_time = time.time() - start_time

            # Extract token usage from collector
            input_tokens = 0
            output_tokens = 0
            total_tokens = 0
            last_call_tokens = 0

            if collector:
                try:
                    # Get cumulative usage across all calls
                    if hasattr(collector, "usage") and collector.usage:
                        usage = collector.usage
                        input_tokens = usage.input_tokens or 0
                        output_tokens = usage.output_tokens or 0
                        total_tokens = input_tokens + output_tokens

                    # Also get last call info
                    if (
                        hasattr(collector, "last")
                        and collector.last
                        and hasattr(collector.last, "usage")
                        and collector.last.usage
                    ):
                        last_usage = collector.last.usage
                        last_call_tokens = (last_usage.input_tokens or 0) + (
                            last_usage.output_tokens or 0
                        )

                    logger.info(
                        f"Token tracking - Cumulative: {total_tokens} (in: {input_tokens}, out: {output_tokens}), Last call: {last_call_tokens}"
                    )

                except Exception as e:
                    logger.warning(f"Error extracting token usage from collector: {e}")

            # Log metrics to MLflow
            mlflow.log_metrics(
                {
                    "debugger_input_tokens": input_tokens,
                    "debugger_output_tokens": output_tokens,
                    "debugger_total_tokens": total_tokens,
                    "debugger_last_call_tokens": last_call_tokens,
                    "debugger_execution_time": execution_time,
                    "debugger_success": 1 if final_result.success else 0,
                    "debugger_calls_count": len(collector.logs)
                    if collector and hasattr(collector, "logs")
                    else 0,
                }
            )

            # Set span outputs and attributes
            debugger_span.set_outputs(
                {
                    "fixed_implementation": final_result.fixed_implementation,
                    "changes_summary": final_result.changes_summary,
                    "success": final_result.success,
                    "thoughts": final_result.thoughts,
                    "test_cases_provided": final_result.test_cases_provided,
                    "calls_count": len(collector.logs)
                    if collector and hasattr(collector, "logs")
                    else 0,
                    "execution_time": execution_time,
                }
            )

            debugger_span.set_attributes(
                {
                    "token_usage.input_tokens": input_tokens,
                    "token_usage.output_tokens": output_tokens,
                    "token_usage.total_tokens": total_tokens,
                    "token_usage.last_call_tokens": last_call_tokens,
                    "execution_time_seconds": execution_time,
                    "collector.calls_count": len(collector.logs)
                    if collector and hasattr(collector, "logs")
                    else 0,
                }
            )

            logger.info(
                f"Helper function debugger completed. Tokens: {total_tokens}, Time: {execution_time:.2f}s, Success: {final_result.success}"
            )

            return final_result, collector, execution_history


if __name__ == "__main__":
    import ifcopenshell
    import mlflow

    from src.agents.answer_verifier import verify_answer
    from src.agents.cobbie import cobbie
    from src.agents.faulty_tool_identifier import identify_faulty_tool
    from src.config import TEST_IFC_PATH
    from src.tools.initial import query_ifcopenshell_docs

    # Define a FAULTY helper function for testing purposes
    # BUG: This function ignores the floor_name parameter and returns ALL doors
    def count_doors_by_floor(ifc_file_path: str, floor_name: str) -> int:
        """
        Count the number of doors on a specific building floor.

        Args:
            ifc_file_path: Path to the IFC file
            floor_name: Name of the floor/storey (e.g., 'Level 1', 'Ground Floor')

        Returns:
            Number of doors on the specified floor
        """
        ifc_file = ifcopenshell.open(ifc_file_path)
        doors = ifc_file.by_type("IfcDoor")  # type: ignore

        # BUG: Returns ALL doors instead of filtering by floor_name
        return len(doors)

    # Get the faulty function's source code
    import inspect

    faulty_implementation = inspect.getsource(count_doors_by_floor)

    # Try to set up MLflow tracking
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("HelperFunctionDebugger")

    # Setup tools for Cobbie - INCLUDING THE FAULTY TOOL
    tools_dict = {
        "query_ifcopenshell_docs": query_ifcopenshell_docs,
        "count_doors_by_floor": count_doors_by_floor,  # This tool has a bug!
    }

    # Test question that will produce wrong answer due to faulty tool
    test_question = "How many doors are on the ground floor?"
    model_path = TEST_IFC_PATH
    ground_truth = "There are 6 doors on the ground floor."

    print("=" * 80)
    print("STEP 1: Running Cobbie with faulty tool")
    print("=" * 80)
    print(f"Question: {test_question}")
    print(f"Model: {model_path}")
    print(f"Ground Truth: {ground_truth}\n")

    with mlflow.start_run(run_name="HelperFunctionDebugger_Test"):
        # Run Cobbie (will get wrong answer due to faulty tool)
        cobbie_response = cobbie(
            user_input=test_question,
            tools=tools_dict,
            max_iterations=10,
            model_path=model_path,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )

        print(f"Cobbie Answer: {cobbie_response.answer.answer if cobbie_response.answer else 'No answer'}\n")

        # Construct full history
        full_history = (
            cobbie_response.history
            + f"\n--- Final Answer ---\nThoughts: {cobbie_response.answer.thoughts if cobbie_response.answer else 'No thoughts'}\nAnswer: {cobbie_response.answer.answer if cobbie_response.answer else 'No answer'}"
        )

        print("=" * 80)
        print("STEP 2: Verifying answer")
        print("=" * 80)

        # Verify the answer
        verification, v_collector = verify_answer(
            question=test_question,
            category=1,
            ground_truth=ground_truth,
            system_response=cobbie_response.answer.answer if cobbie_response.answer else "",
        )

        if isinstance(verification, AgentError):
            print(f"Error: {verification.error_message}")
            classification = "abstained"
        else:
            classification = derive_binary_classification(result=verification)
        print(f"Classification: {classification}")
        if not isinstance(verification, AgentError):
            print(f"Justification: {verification.justification}\n")

        if classification == "wrong":
            print("=" * 80)
            print("STEP 3: Identifying faulty tool")
            print("=" * 80)

            # Get existing helper functions documentation
            existing_helpers = generate_tools_docs(tools_dict)

            # Identify the faulty tool
            faulty_analysis, f_collector = identify_faulty_tool(
                history=full_history,
                question=test_question,
                ground_truth=ground_truth,
                provided_answer=cobbie_response.answer.answer if cobbie_response.answer else "",
                justification=verification.justification if not isinstance(verification, AgentError) else "",
                existing_helper_functions=existing_helpers,
            )

            if isinstance(faulty_analysis, AgentError):
                print(f"Error: {faulty_analysis.error_message}")
            else:
                print(f"Faulty Tool Identified: {faulty_analysis.faulty_tool}")
                if faulty_analysis.faulty_tool:
                    print(f"Tool Name: {faulty_analysis.faulty_tool_name}")
                    print(f"Confidence: {faulty_analysis.confidence}")
                    print(f"\nError Description:\n{faulty_analysis.error_description}\n")

            if not isinstance(faulty_analysis, AgentError) and faulty_analysis.faulty_tool:
                print("=" * 80)
                print("STEP 4: Debugging faulty tool")
                print("=" * 80)

                # Debug the faulty tool
                fixed_result, debugger_collector, debug_history = debug_helper_function(
                    faulty_function_name=faulty_analysis.faulty_tool_name,
                    faulty_function_implementation=faulty_implementation,
                    error_description=faulty_analysis.error_description,
                    history_faulty_tool_use=full_history,
                    ifc_model_path=model_path,
                    max_iterations=15,
                    llm_provider="zai",
                    llm_name="GLM-4.6",
                )

                print(f"\nDebugging successful: {fixed_result.success}")
                print(f"\nChanges Summary:\n{fixed_result.changes_summary}")
                print(f"\nThoughts:\n{fixed_result.thoughts}")
                print(f"\nFixed Implementation:\n{fixed_result.fixed_implementation}")
                if fixed_result.test_cases_provided:
                    print(f"\nTest Cases:\n{fixed_result.test_cases_provided}")

                # Extract metrics
                total_tokens = 0
                if (
                    debugger_collector
                    and hasattr(debugger_collector, "usage")
                    and debugger_collector.usage
                ):
                    usage = debugger_collector.usage
                    input_tokens = usage.input_tokens or 0
                    output_tokens = usage.output_tokens or 0
                    total_tokens = input_tokens + output_tokens

                print(f"\nTotal Tokens Used: {total_tokens}")
                print(
                    f"Number of LLM Calls: {len(debugger_collector.logs) if hasattr(debugger_collector, 'logs') else 'N/A'}"
                )
        else:
            print(
                "Answer was not wrong - skipping faulty tool identification and debugging."
            )
