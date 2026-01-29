"""
COBBIE: COde-Based BIM Information Extraction
Functional implementation using the BAML library and the CodeAct architecture.
"""

import logging
import time
from contextlib import nullcontext
from typing import Callable, Dict, Optional, Tuple

import mlflow
from baml_py.baml_py import Collector

from baml_client.types import CodeAction, FinalAnswer
from src.util.code_act_inner_loop import _code_act_iter, _execute_code_action
from src.util.generate_tools_docs import generate_tools_docs

logger = logging.getLogger(__name__)


def _cobbie(
    question: str,
    tools: Dict[str, Callable],
    max_iterations: int = 15,
    model_path: Optional[str] = None,
    add_code_prefix: bool = True,
    llm_name: str = "GLM-4.6",
    llm_provider: str = "zai",
    **kwargs,
) -> Tuple[FinalAnswer, str]:
    """
    Main COBBIE function for BIM question answering.

    Orchestrates the CodeAct execution loop to answer BIM questions by
    iteratively generating and executing Python code using available tools.

    Args:
        user_input: The question or task to address
        tools: Dictionary of available tools/functions for code execution
        max_iterations: Maximum number of reasoning iterations (default: 10)
        model_path: Optional path to IFC model file
        add_code_prefix: Whether to add boilerplate code prefix (default: True)
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (FinalAnswer, execution_history) where execution_history contains
        the complete iteration-by-iteration trace of thoughts, code, and results
    """
    logger.info(f"Starting COBBIE execution for: {question[:100]}...")

    # Prepare execution context
    tools_docs = generate_tools_docs(tools)
    previous_attempts = []

    # Initialize counters for comprehensive metrics
    code_execution_count = 0
    total_code_execution_time = 0
    llm_calls = 0

    # Initialize the previous_attempts
    previous_attempts = ""

    # Main reasoning loop
    for iteration in range(max_iterations):
        iteration_start = time.time()

        # mlflow Iteration Span
        with mlflow.start_span(
            name=f"Iteration_{iteration + 1}", span_type="CHAIN"
        ) as iteration_span:
            # Extract token usage from collector for this iteration
            iteration_input_tokens = 0
            iteration_output_tokens = 0
            iteration_total_tokens = 0

            # mlflow LLM call span
            with mlflow.start_span(
                name=f"LLM_call_{iteration + 1}", span_type="LLM"
            ) as llm_span:
                llm_span.set_inputs(
                    {
                        "question": question,
                        "available_tools": tools_docs,
                        "previous_attempts": previous_attempts,
                        "model_path": model_path or "None",
                    }
                )

                result = _code_act_iter(
                    user_input=question,
                    available_tools=tools_docs,
                    previous_attempts=previous_attempts,
                    model_path=model_path,
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

                elif isinstance(result, FinalAnswer):
                    llm_span.set_outputs(
                        {
                            "result_type": "FinalAnswer",
                            "thoughts": result.thoughts,
                            "answer": result.answer,
                            "ifc_guids": result.ifc_guids,
                        }
                    )

            # Handle union type flow control
            if isinstance(result, FinalAnswer):
                logger.info(
                    f"COBBIE completed successfully after {iteration + 1} iterations"
                )

                # Log final iteration metrics with token usage
                iteration_span.set_outputs(
                    {
                        "final_answer": result.answer,
                        "final_reasoning": result.thoughts,
                        "total_iterations": iteration + 1,
                        "llm_calls": llm_calls,
                        "code_executions": code_execution_count,
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
                # Update the previous results
                current_attempt = _execute_code_action(
                    code_action=result,
                    iteration=iteration,
                    tools=tools,
                    model_path=model_path,
                    add_code_prefix=add_code_prefix,
                )
                previous_attempts += f"/n{current_attempt}/n"

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
        f"COBBIE reached max iterations ({max_iterations}) without completion"
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
                "code_executions": code_execution_count,
                "total_code_execution_time": total_code_execution_time,
            }
        )

        final_answer = FinalAnswer(
            thoughts=f"Reached maximum iteration limit ({max_iterations}) without resolving the question. "
            f"Summary:\n"
            f"- Total iterations: {max_iterations}\n"
            f"- LLM calls: {llm_calls}\n"
            f"- Code executions: {code_execution_count}\n"
            f"- Total code execution time: {total_code_execution_time:.2f}s\n\n"
            f"Last 3 attempts:\n" + "\n".join(previous_attempts[-3:])
            if previous_attempts
            else "No previous attempts",
            answer="Unable to complete the request due to iteration limit. The question may be too complex or required information may not be accessible with the available tools.",
        )

        final_span.set_outputs(
            {
                "answer": final_answer.answer,
                "reasoning": final_answer.thoughts,
                "termination_reason": "max_iterations_reached",
                "summary": {
                    "max_iterations": max_iterations,
                    "llm_calls": llm_calls,
                    "code_executions": code_execution_count,
                    "total_code_execution_time": total_code_execution_time,
                    "partial_results_count": len(previous_attempts),
                },
            }
        )
        final_span.set_status("OK")

        return final_answer, previous_attempts


def cobbie(
    user_input: str,
    tools: Dict[str, Callable],
    max_iterations: int = 15,
    model_path: Optional[str] = None,
    add_code_prefix: bool = True,
    llm_provider: str = "zai",
    llm_name: str = "glm-4.7",
    mlflow_run_id: Optional[str] = None,
    **kwargs,
) -> Tuple[FinalAnswer, Collector, str]:
    """
    Execute COBBIE with comprehensive metrics collection.

    Returns FinalAnswer, Collector, and execution history for performance tracking and analysis.

    Args:
        user_input: The question or task to address
        tools: Dictionary of available tools/functions
        max_iterations: Maximum number of reasoning iterations
        model_path: Optional path to IFC model file
        add_code_prefix: Whether to add boilerplate code prefix
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (FinalAnswer, Collector, execution_history) where execution_history
        contains the complete iteration-by-iteration trace of thoughts, code, and results
    """
    # Create collector for token tracking
    collector = Collector(name="COBBIE")

    # Add collector to kwargs for BAML calls
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    # Check if we're already in an MLflow run, or if a run_id was provided
    active_run = mlflow.active_run()

    # If a run_id is provided, use that run; otherwise check for active run or create new one
    if mlflow_run_id:
        run_context_manager = mlflow.start_run(run_id=mlflow_run_id)
    elif active_run:
        run_context_manager = nullcontext()
    else:
        run_context_manager = mlflow.start_run(run_name="Cobbie")

    with run_context_manager:
        # Only log parameters if we created a new run (not when running in existing run)
        if not active_run:
            mlflow.log_params(
                {
                    "component": "COBBIE",
                    "max_iterations": max_iterations,
                    "add_code_prefix": add_code_prefix,
                    "model_path": model_path or "None",
                    "tools_count": len(tools),
                    "llm_provider": llm_provider,
                    "llm_model": llm_name,
                    "tools": ", ".join(tools.keys()),
                }
            )

        # Start MLflow span for the entire execution
        with mlflow.start_span(name="COBBIE", span_type="CHAIN") as cobbie_span:
            # Set span inputs
            cobbie_span.set_inputs(
                {
                    "user_input": user_input,
                    "max_iterations": max_iterations,
                    "model_path": model_path or "None",
                    "tools_count": len(tools),
                }
            )

            # Execute COBBIE and measure time within the main span context
            start_time = time.time()
            final_answer, execution_history = _cobbie(
                question=user_input,
                tools=tools,
                max_iterations=max_iterations,
                model_path=model_path,
                add_code_prefix=add_code_prefix,
                **kwargs,
            )
            execution_time = time.time() - start_time

            # Extract token usage from collector
            input_tokens = 0
            output_tokens = 0
            total_tokens = 0
            last_call_tokens = 0

            # Use collector.usage for cumulative total across ALL calls (not just the last one)
            if collector:
                try:
                    # Get cumulative usage across all calls
                    if hasattr(collector, "usage") and collector.usage:
                        usage = collector.usage
                        input_tokens = usage.input_tokens or 0
                        output_tokens = usage.output_tokens or 0
                        total_tokens = input_tokens + output_tokens

                    # Also get last call info for comparison (debugging purposes)
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
                    # Fallback to zero values
                    input_tokens = 0
                    output_tokens = 0
                    total_tokens = 0
            else:
                logger.warning("No collector available for token tracking")

            # Log metrics to MLflow
            mlflow.log_metrics(
                {
                    "cobbie_input_tokens": input_tokens,
                    "cobbie_output_tokens": output_tokens,
                    "cobbie_total_tokens": total_tokens,
                    "cobbie_last_call_tokens": last_call_tokens,  # For comparison/debugging
                    "cobbie_execution_time": execution_time,
                    "cobbie_success": 1
                    if "iteration limit" not in final_answer.answer.lower()
                    else 0,
                    "cobbie_calls_count": len(collector.logs)
                    if collector and hasattr(collector, "logs")
                    else 0,
                }
            )

            # Set span outputs and attributes
            cobbie_span.set_outputs(
                {
                    "answer": final_answer.answer,
                    "reasoning": final_answer.thoughts,
                    "calls_count": len(collector.logs)
                    if collector and hasattr(collector, "logs")
                    else 0,
                    "execution_time": execution_time,
                    "success": "iteration limit" not in final_answer.answer.lower(),
                }
            )

            cobbie_span.set_attributes(
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
                f"COBBIE with metrics completed. Tokens: {total_tokens}, Time: {execution_time:.2f}s"
            )

            return final_answer, collector, execution_history


if __name__ == "__main__":
    import mlflow
    import json
    from src.config import TEST_IFC_PATH, DEVSET_PATH
    from src.tools.initial import (
        query_ifcopenshell_docs,
        web_search,
    )

    # Try to set up MLflow tracking, but don't fail if server is not available
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("Cobbie_ACC")

    # Setup tools
    tools_dict = {
        "query_ifcopenshell_docs": query_ifcopenshell_docs,
        "web_search": web_search,
    }

    with open(DEVSET_PATH, "r") as f:
        dev_set = json.load(f)
    test_data = dev_set[0]
    test_question = f"""
{test_data['question']}
Underlying Rule: {test_data['rule']}
Additional Parameters: {test_data['parameters']}
    """
    ground_truth = test_data['ground_truth']
    if len(ground_truth) > 1:
        guids = [gt['ifc_guids'][0] for gt in ground_truth]
    else:
        guids = ground_truth[0]['ifc_guids']

    # Test question with IFC model
    # test_question = "How many walls are there in the BIM model?"
    model_path = TEST_IFC_PATH

    print("COBBIE Test Execution:")
    print(f"Question: {test_question}")
    print(f"Model Path: {model_path}\n")

    # Test cobbie_with_metrics for comprehensive tracking
    result, collector, execution_history = cobbie(
        user_input=test_question,
        tools=tools_dict,
        max_iterations=15,
        model_path=model_path,
        llm_provider="zai",
        llm_name="GLM-4.6",
    )

    print("COBBIE Test Results:")
    print(f"Answer: {result.answer}")
    print(f"\nReasoning: {result.thoughts}")
    print(f"\nIFC GUIDs: {result.ifc_guids}")
    print(f"\nExecution History:\n{execution_history}")

    # Extract metrics
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0

    if collector and hasattr(collector, "usage") and collector.usage:
        usage = collector.usage
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
        total_tokens = input_tokens + output_tokens

    print("\nMetrics:")
    print(f"Input Tokens: {input_tokens}")
    print(f"Output Tokens: {output_tokens}")
    print(f"Total Tokens: {total_tokens}")
    print(
        f"Number of LLM Calls: {len(collector.logs) if hasattr(collector, 'logs') else 'N/A'}"
    )
