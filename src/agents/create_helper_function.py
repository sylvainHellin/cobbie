"""
Agent that creates new helper functions.
Extracts and implements reusable helper functions from successful Cobbie executions.
"""

import os
import time
from contextlib import nullcontext
from pathlib import Path
from typing import List, Optional, Tuple

import mlflow
from baml_py.baml_py import Collector
from loguru import logger

from baml_client.types import CodeAction, NewHelperFunction
from src.tools.initial import query_ifcopenshell_docs
from src.util import _execute_code_action, generate_tools_docs, setup_logger


# initialize logger
setup_logger()

def _helper_function_creator_iter(
    history: str,
    example_question: str,
    example_answer: str,
    example_bim_model: str,
    other_bim_models_for_testing: List[str],
    function_name: str,
    function_description: str,
    is_enhancement: bool = False,
    existing_implementation: Optional[str] = None,
    previous_attempts: Optional[str] = None,
    **kwargs,
) -> CodeAction | NewHelperFunction:
    """
    Execute a single iteration of the helper function creator.

    This function represents one iteration of the creation loop,
    calling the LLM to either generate code or provide a final implementation.

    Args:
        history: Complete execution history from Cobbie
        example_question: Question answered by Cobbie
        example_answer: Ground truth answer
        example_bim_model: Path to BIM model used in example
        other_bim_models_for_testing: List of other BIM models for testing
        function_name: Name of the function to create or enhance
        function_description: Description of the function (or enhancement)
        is_enhancement: True if enhancing existing tool, False if creating new
        existing_implementation: Current tool implementation (if enhancing)
        previous_attempts: Results from previous iterations
        **kwargs: Additional arguments for BAML function (including baml_options)

    Returns:
        CodeAction to continue development or NewHelperFunction when complete
    """
    from baml_client import b

    # Extract baml_options if provided for collector integration
    baml_options = kwargs.get("baml_options", {})

    # Create a clean copy of kwargs for the BAML call (remove baml_options)
    kwargs_copy = kwargs.copy()
    kwargs_copy.pop("baml_options", None)

    # Call BAML function with union return type
    try:
        if baml_options:
            result = b.with_options(**baml_options).HelperFunctionCreator(
                history=history,
                example_question=example_question,
                example_answer=example_answer,
                example_bim_model=example_bim_model,
                other_bim_models_for_testing=other_bim_models_for_testing,
                function_name=function_name,
                function_description=function_description,
                is_enhancement=is_enhancement,
                existing_implementation=existing_implementation,
                previous_attempts=previous_attempts,
                **kwargs_copy,
            )
        else:
            result = b.HelperFunctionCreator(
                history=history,
                example_question=example_question,
                example_answer=example_answer,
                example_bim_model=example_bim_model,
                other_bim_models_for_testing=other_bim_models_for_testing,
                function_name=function_name,
                function_description=function_description,
                is_enhancement=is_enhancement,
                existing_implementation=existing_implementation,
                previous_attempts=previous_attempts,
                **kwargs_copy,
            )
    except Exception as e:
        logger.error(f"Error in HelperFunctionCreator iteration: {e}")
        result = NewHelperFunction(
            thoughts=f"An Exception occurred when trying to create the helper function. Exception:\n{e}",
            function_implementation="",
            success=False,
        )

    return result


def _create_helper_function(
    history: str,
    example_question: str,
    example_answer: str,
    example_bim_model: str,
    function_name: str,
    function_description: str,
    is_enhancement: bool = False,
    existing_implementation: Optional[str] = None,
    other_bim_models_for_testing: Optional[List[str]] = None,
    max_iterations: int = 15,
    llm_name: str = "GLM-4.6",
    llm_provider: str = "zai",
    **kwargs,
) -> Tuple[NewHelperFunction, str]:
    """
    Main helper function creator orchestration with iteration loop.

    Orchestrates the CodeAct execution loop to create a reusable helper function
    by iteratively generating and executing Python code.

    Args:
        history: Complete execution history from Cobbie
        example_question: Question answered by Cobbie
        example_answer: Ground truth answer
        example_bim_model: Path to BIM model used in example
        function_name: Name of the function to create or enhance
        function_description: Description of the function (or enhancement)
        is_enhancement: True if enhancing existing tool, False if creating new
        existing_implementation: Current tool implementation (if enhancing)
        other_bim_models_for_testing: List of other BIM models for testing
        max_iterations: Maximum number of iterations (default: 15)
        llm_name: LLM model name (default: "GLM-4.6")
        llm_provider: LLM provider (default: "zai")
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (NewHelperFunction, execution_history) where execution_history contains
        the complete iteration-by-iteration trace of development
    """
    logger.info(f"Starting helper function creation for: {function_name}")

    # Prepare tools for code execution
    tools = {
        "query_ifcopenshell_docs": query_ifcopenshell_docs,
    }

    # Prepare the paths to the other BIM models if not provided
    if other_bim_models_for_testing is None:
        # Get the absolute path to the BIM models directory
        bim_models_dir = Path(__file__).parent.parent / "experiment" / "bim_models"

        if bim_models_dir.exists():
            # Find all .ifc files recursively in the directory
            ifc_files = []
            for root, _, files in os.walk(bim_models_dir):
                for file in files:
                    if file.endswith(".ifc"):
                        ifc_path = os.path.join(root, file)
                        # Exclude the current model being tested
                        if ifc_path != example_bim_model:
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

    # Initialize execution history
    previous_attempts = ""

    # Initialize counters
    llm_calls = 0

    # Main development loop
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
                        "history": history,
                        "function_name": function_name,
                        "function_description": function_description,
                        "example_question": example_question,
                        "example_bim_model": example_bim_model,
                        "previous_attempts": previous_attempts,
                    }
                )

                # Call the function and capture the full prompt from kwargs
                result = _helper_function_creator_iter(
                    history=history,
                    example_question=example_question,
                    example_answer=example_answer,
                    example_bim_model=example_bim_model,
                    other_bim_models_for_testing=other_bim_models_for_testing,
                    function_name=function_name,
                    function_description=function_description,
                    is_enhancement=is_enhancement,
                    existing_implementation=existing_implementation,
                    previous_attempts=previous_attempts,
                    **kwargs,
                )

                iteration_duration = time.time() - iteration_start
                llm_calls += 1

                # Get collector from kwargs to extract token usage and prompt
                baml_options = kwargs.get("baml_options", {})
                collector = baml_options.get("collector")

                # Extract the actual full prompt from collector
                full_prompt = ""
                if (
                    collector
                    and collector.last
                    and hasattr(collector.last, "calls")
                    and collector.last.calls
                ):
                    try:
                        last_call = collector.last.calls[-1]
                        if hasattr(last_call, "http_request") and hasattr(
                            last_call.http_request, "body"
                        ):
                            body = last_call.http_request.body
                            if hasattr(body, "json"):
                                request_json = body.json()
                                if "messages" in request_json:
                                    # Reconstruct the full prompt from messages
                                    message_parts = []
                                    for message in request_json["messages"]:
                                        if "content" in message:
                                            content = message["content"]
                                            if isinstance(content, str):
                                                message_parts.append(
                                                    f"{message.get('role', 'unknown')}: {content}"
                                                )
                                            elif isinstance(content, list):
                                                for part in content:
                                                    if "text" in part:
                                                        message_parts.append(
                                                            f"{message.get('role', 'unknown')}: {part['text']}"
                                                        )

                                    full_prompt = "\n\n".join(message_parts)
                                    logger.debug(
                                        f"Successfully extracted full prompt from collector: {len(full_prompt)} characters"
                                    )
                                else:
                                    logger.warning(
                                        "No messages found in collector request JSON"
                                    )
                            else:
                                logger.warning("HTTP body does not have json method")
                        else:
                            logger.warning(
                                "Last call does not have http_request or body"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error extracting full prompt from collector: {e}"
                        )
                else:
                    logger.warning("No collector data available for prompt extraction")

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

                # Log the full prompt as a span attribute if available
                if full_prompt:
                    llm_span.set_attribute("full_prompt", full_prompt)

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
                elif isinstance(result, NewHelperFunction):
                    llm_span.set_outputs(
                        {
                            "result_type": "NewHelperFunction",
                            "thoughts": result.thoughts,
                            "function_implementation": result.function_implementation,
                            "success": result.success,
                        }
                    )

            # Handle union type flow control
            if isinstance(result, NewHelperFunction):
                logger.info(
                    f"Helper function creation completed after {iteration + 1} iterations"
                )

                # Log final iteration metrics
                iteration_span.set_outputs(
                    {
                        "function_implementation": result.function_implementation,
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
                iteration_span.set_status("OK")

                return result, previous_attempts

            elif isinstance(result, CodeAction):
                # Execute the code action
                current_attempt = _execute_code_action(
                    code_action=result,
                    iteration=iteration,
                    tools=tools,
                    model_path=example_bim_model,
                    add_code_prefix=True,
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
        f"Helper function creator reached max iterations ({max_iterations}) without completion"
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

        final_result = NewHelperFunction(
            thoughts=f"Reached maximum iteration limit ({max_iterations}) without completing the function. "
            f"Summary:\n"
            f"- Total iterations: {max_iterations}\n"
            f"- LLM calls: {llm_calls}\n\n"
            f"Last 3 attempts:\n" + "\n".join(previous_attempts.split("\n")[-30:])
            if previous_attempts
            else "No previous attempts",
            function_implementation="",
            success=False,
        )

        final_span.set_outputs(
            {
                "function_implementation": final_result.function_implementation,
                "success": final_result.success,
                "termination_reason": "max_iterations_reached",
            }
        )
        final_span.set_status("OK")

        return final_result, previous_attempts


def create_helper_function(
    history: str,
    example_question: str,
    example_answer: str,
    example_bim_model: str,
    function_name: str,
    function_description: str,
    is_enhancement: bool = False,
    existing_implementation: Optional[str] = None,
    other_bim_models_for_testing: Optional[List[str]] = None,
    max_iterations: int = 15,
    llm_provider: str = "zai",
    llm_name: str = "GLM-4.6",
    **kwargs,
) -> Tuple[NewHelperFunction, Collector, str]:
    """
    Execute helper function creator with comprehensive metrics collection.

    Returns NewHelperFunction, Collector, and execution history for performance tracking.

    Args:
        history: Complete execution history from Cobbie
        example_question: Question answered by Cobbie
        example_answer: Ground truth answer
        example_bim_model: Path to BIM model used in example
        function_name: Name of the function to create or enhance
        function_description: Description of the function (or enhancement)
        is_enhancement: True if enhancing existing tool, False if creating new
        existing_implementation: Current tool implementation (if enhancing)
        other_bim_models_for_testing: List of other BIM models for testing
        max_iterations: Maximum number of iterations (default: 15)
        llm_provider: LLM provider (default: "zai")
        llm_name: LLM model name (default: "GLM-4.6")
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (NewHelperFunction, Collector, execution_history) where execution_history
        contains the complete iteration-by-iteration trace of development
    """
    # Create collector for token tracking
    collector = Collector(name="HelperFunctionCreator")

    # Add collector to kwargs for BAML calls
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    # Check if we're already in an MLflow run, if not start one
    active_run = mlflow.active_run()
    run_context_manager = (
        nullcontext()
        if active_run
        else mlflow.start_run(run_name="HelperFunctionCreator")
    )

    with run_context_manager:
        # Only log parameters if we created a new run (not when running in existing run)
        if not active_run:
            mlflow.log_params(
                {
                    "component": "HelperFunctionCreator",
                    "max_iterations": max_iterations,
                    "function_name": function_name,
                    "example_bim_model": example_bim_model,
                    "other_models_count": len(other_bim_models_for_testing)
                    if other_bim_models_for_testing is not None
                    else 0,
                    "llm_provider": llm_provider,
                    "llm_model": llm_name,
                }
            )

        # Start MLflow span for the entire execution
        with mlflow.start_span(
            name="HelperFunctionCreator", span_type="CHAIN"
        ) as creator_span:
            # Set span inputs
            creator_span.set_inputs(
                {
                    "function_name": function_name,
                    "function_description": function_description,
                    "example_question": example_question,
                    "example_bim_model": example_bim_model,
                    "max_iterations": max_iterations,
                }
            )

            # Execute helper function creator
            start_time = time.time()
            final_result, execution_history = _create_helper_function(
                history=history,
                example_question=example_question,
                example_answer=example_answer,
                example_bim_model=example_bim_model,
                other_bim_models_for_testing=other_bim_models_for_testing,
                function_name=function_name,
                function_description=function_description,
                is_enhancement=is_enhancement,
                existing_implementation=existing_implementation,
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

                    logger.debug(
                        f"Token tracking - Cumulative: {total_tokens} (in: {input_tokens}, out: {output_tokens}), Last call: {last_call_tokens}"
                    )

                except Exception as e:
                    logger.warning(f"Error extracting token usage from collector: {e}")

            # Log metrics to MLflow
            mlflow.log_metrics(
                {
                    "creator_input_tokens": input_tokens,
                    "creator_output_tokens": output_tokens,
                    "creator_total_tokens": total_tokens,
                    "creator_last_call_tokens": last_call_tokens,
                    "creator_execution_time": execution_time,
                    "creator_success": 1 if final_result.success else 0,
                    "creator_calls_count": len(collector.logs)
                    if collector and hasattr(collector, "logs")
                    else 0,
                }
            )

            # Set span outputs and attributes
            creator_span.set_outputs(
                {
                    "function_implementation": final_result.function_implementation,
                    "success": final_result.success,
                    "thoughts": final_result.thoughts,
                    "calls_count": len(collector.logs)
                    if collector and hasattr(collector, "logs")
                    else 0,
                    "execution_time": execution_time,
                }
            )

            creator_span.set_attributes(
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

            logger.debug(
                f"Helper function creator completed. Tokens: {total_tokens}, Time: {execution_time:.2f}s, Success: {final_result.success}"
            )

            return final_result, collector, execution_history


if __name__ == "__main__":
    import mlflow

    from src.agents.cobbie import cobbie
    from src.agents.identify_helper_function import identify_helper_function
    from src.config import TEST_IFC_PATH
    from src.tools.initial import (
        query_ifcopenshell_docs,
        web_search,
    )

    # Try to set up MLflow tracking
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("CreateHelperFunction")

    # Setup tools for Cobbie
    tools_dict = {
        "query_ifcopenshell_docs": query_ifcopenshell_docs,
        "web_search": web_search,
    }

    # Test question and model
    test_question = "How many doors are on the ground floor?"
    model_path = TEST_IFC_PATH
    ground_truth = "6 doors"  # Adjust based on actual model

    # Get list of available BIM models for testing
    import os

    bim_models_dir = "/Users/sylvainhellin/GitHub/4_phd/cobbie/src/db/bim_models"
    print("=" * 80)
    print("STEP 1: Running Cobbie to answer question")
    print("=" * 80)
    print(f"Question: {test_question}")
    print(f"Model: {model_path}\n")

    # Run Cobbie
    cobbie_result, cobbie_collector, execution_history = cobbie(
        user_input=test_question,
        tools=tools_dict,
        max_iterations=10,
        model_path=model_path,
        llm_provider="zai",
        llm_name="GLM-4.6",
    )

    print(f"Cobbie Answer: {cobbie_result.answer}\n")

    # Construct full history
    full_history = (
        execution_history
        + f"\n--- Final Answer ---\nThoughts: {cobbie_result.thoughts}\nAnswer: {cobbie_result.answer}"
    )

    print("=" * 80)
    print("STEP 2: Identifying helper function")
    print("=" * 80)

    # Get existing helper functions
    from src.util.generate_tools_docs import generate_tools_docs

    existing_helpers = generate_tools_docs(tools_dict)

    # Identify helper function
    tool_identified, identifier_collector = identify_helper_function(
        history=full_history,
        example_question=test_question,
        existing_helper_functions=existing_helpers,
        llm_provider="zai",
        llm_name="GLM-4.6",
    )

    print(f"Tool management action: {tool_identified.action}")
    print(f"Tool name: {tool_identified.tool_name}")
    print(f"Tool description: {tool_identified.tool_description}\n")

    if tool_identified.action == "create_new":
        print("=" * 80)
        print("STEP 3: Creating helper function")
        print("=" * 80)

        # Create the helper function
        result, creator_collector, creation_history = create_helper_function(
            history=full_history,
            example_question=test_question,
            example_answer=ground_truth,
            example_bim_model=model_path,
            function_name=tool_identified.tool_name,
            function_description=tool_identified.tool_description,
            max_iterations=15,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )

        print(f"\nCreation successful: {result.success}")
        print(f"\nThoughts:\n{result.thoughts}")
        print(f"\nFunction Implementation:\n{result.function_implementation}")

        # Extract metrics
        total_tokens = 0
        if (
            creator_collector
            and hasattr(creator_collector, "usage")
            and creator_collector.usage
        ):
            usage = creator_collector.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            total_tokens = input_tokens + output_tokens

        print(f"\nTotal Tokens: {total_tokens}")
        print(
            f"Number of LLM Calls: {len(creator_collector.logs) if hasattr(creator_collector, 'logs') else 'N/A'}"
        )
    else:
        print("No helper function needed based on analysis.")
