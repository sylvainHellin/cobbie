"""
COBBIE: COde-Based BIM Information Extraction

Functional implementation of BIM question answering using BAML and CodeAct pattern.
Replaces the object-oriented BIM_QAS class with a functional approach.
"""

import time
import logging
from contextlib import nullcontext
from typing import Dict, Callable, Optional, Tuple, Any

import mlflow
from baml_client import b
from baml_client.types import CodeAction, FinalAnswer
from baml_py.baml_py import Collector

from src.engine.schemas import ModuleOutput
from src.engine.util.python_executor import execute_python
from src.engine.util.generate_tools_docs import generate_tools_docs
from src.engine.util.create_code_prefix import create_code_prefix
# Removed metrics import - using Collector directly as in baml_common.py
from src.config import IfcAnswerEngineConfig

logger = logging.getLogger(__name__)


def cobbie(
    user_input: str,
    tools: Dict[str, Callable],
    max_iterations: int = 10,
    model_path: Optional[str] = None,
    add_code_prefix: bool = True,
    **kwargs
) -> FinalAnswer:
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
        FinalAnswer with the answer and reasoning
    """
    logger.info(f"Starting COBBIE execution for: {user_input[:100]}...")

    # Prepare execution context
    tools_docs = generate_tools_docs(tools)
    code_prefix = create_code_prefix(model_path) if add_code_prefix else ""
    previous_results = []

    # Combine code prefix with tools documentation
    full_tools_docs = code_prefix + "\n\n" + tools_docs if code_prefix else tools_docs

    logger.debug(f"Prepared execution context with {len(tools)} tools")

    # Initialize counters for comprehensive metrics
    code_execution_count = 0
    total_code_execution_time = 0
    llm_calls = 0

    # Main reasoning loop
    for iteration in range(max_iterations):
        iteration_start = time.time()

        logger.debug(f"Reasoning iteration {iteration + 1}/{max_iterations}")

        # Create MLflow span for this iteration
        with mlflow.start_span(name=f"Iteration_{iteration + 1}", span_type="CHAIN") as iteration_span:

            # Prepare previous context (last 3 attempts)
            previous_context = "\n".join(previous_results[-3:]) if previous_results else None

            # Extract token usage from collector for this iteration
            iteration_input_tokens = 0
            iteration_output_tokens = 0
            iteration_total_tokens = 0

            try:
                # BAML function call with tracing
                with mlflow.start_span(name=f"LLM_call_{iteration + 1}", span_type="MODULE") as llm_span:
                    llm_span.set_inputs({
                        "user_input": user_input,
                        "available_tools": full_tools_docs,
                        "has_previous_attempts": previous_context is not None,
                        "model_path": model_path or "None",
                    })

                    baml_start_time = time.time()
                    result = _reasoning_step(
                        user_input=user_input,
                        available_tools=full_tools_docs,
                        previous_results=previous_results,
                        model_path=model_path,
                        **kwargs
                    )
                    baml_latency = time.time() - baml_start_time
                    llm_calls += 1



                    # Get collector from kwargs to extract token usage
                    baml_options = kwargs.get("baml_options", {})
                    collector = baml_options.get("collector")

                    if collector and collector.last and collector.last.usage:
                        usage = collector.last.usage
                        iteration_input_tokens = usage.input_tokens or 0
                        iteration_output_tokens = usage.output_tokens or 0
                        iteration_total_tokens = iteration_input_tokens + iteration_output_tokens

                    # Log BAML call metrics
                    mlflow.log_metric(f"latency_llm_call_{iteration + 1}", baml_latency)
                    llm_span.set_attributes({
                        "llm.provider": "Z.AI",  # Could be made configurable
                        "llm.model": "GLM-4.6"  # Could be made configurable
                    })

                    # Log token usage to BAML span
                    if iteration_input_tokens > 0 or iteration_output_tokens > 0:
                        llm_span.set_attributes({
                            "token_usage.input_tokens": iteration_input_tokens,
                            "token_usage.output_tokens": iteration_output_tokens,
                            "token_usage.total_tokens": iteration_total_tokens
                        })

                    # Log usage metrics
                    llm_span.set_attributes({
                        "input_tokens": iteration_input_tokens,
                        "output_tokens": iteration_output_tokens,
                        "total_tokens": iteration_total_tokens,
                        "latency": baml_latency,
                    })
                    # Log BAML output with metrics
                    if isinstance(result, CodeAction):
                        llm_span.set_outputs({
                            "result_type": "CodeAction",
                            "thoughts": result.thoughts,
                            "python_code": result.python_code,
                                               })

                    elif isinstance(result, FinalAnswer):
                        llm_span.set_outputs({
                            "result_type": "FinalAnswer",
                            "thoughts": result.thoughts,
                            "answer": result.answer,
                        })

                # Handle union type flow control
                if isinstance(result, FinalAnswer):
                    logger.info(f"COBBIE completed successfully after {iteration + 1} iterations")

                    # Log final iteration metrics with token usage
                    iteration_span.set_outputs({
                        "final_answer": result.answer,
                        "final_reasoning": result.thoughts,
                        "total_iterations": iteration + 1,
                        "llm_calls": llm_calls,
                        "code_executions": code_execution_count,
                        "iteration_success": True,
                        "final_iteration_input_tokens": iteration_input_tokens,
                        "final_iteration_output_tokens": iteration_output_tokens,
                        "final_iteration_total_tokens": iteration_total_tokens
                    })
                    iteration_span.set_attributes({
                        "token_usage.final_iteration_input": iteration_input_tokens,
                        "token_usage.final_iteration_output": iteration_output_tokens,
                        "token_usage.final_iteration_total": iteration_total_tokens
                    })
                    iteration_span.set_status("OK")

                    return result

                elif isinstance(result, CodeAction):
                    # Code execution with tracing
                    code_execution_start = time.time()
                    with mlflow.start_span(name="Python_Code_Execution", span_type="MODULE") as exec_span:
                        try:
                            # Add code prefix if available
                            code_to_execute = result.python_code
                            if add_code_prefix and model_path:
                                from src.config import FUNCTION_BOILERPLATE
                                code_prefix = FUNCTION_BOILERPLATE + f"\npath_ifc_model = '{model_path}'"
                                code_to_execute = f"{code_prefix}\n{result.python_code}"

                            exec_span.set_inputs({
                                "has_code_prefix": bool(add_code_prefix and model_path),
                                "python_code": code_to_execute
                            })

                            logger.debug(f"Executing code: {code_to_execute[:200]}...")

                            # Execute the generated code
                            code_result = execute_python(
                                python_code=result.python_code,
                                tools=tools,
                                model_path=model_path
                            )

                            code_execution_time = time.time() - code_execution_start
                            code_execution_count += 1
                            total_code_execution_time += code_execution_time

                            # Store result for next iteration
                            iteration_result = f"""Iteration {iteration + 1}:
Thoughts: {result.thoughts}

Code:
{result.python_code}

Result:
{code_result}"""
                            previous_results.append(iteration_result)

                            # Log code execution metrics
                            mlflow.log_metric(f"code_execution_time_{iteration + 1}", code_execution_time)
                            exec_span.set_outputs({
                                "code_result": code_result,
                                "execution_time": code_execution_time,
                                "code_success": True
                            })
                            exec_span.set_status("OK")

                            # Log iteration completion with token usage
                            iteration_span.set_outputs({
                                "iteration_number": iteration + 1,
                                "code_executed": True,
                                "code_execution_time": code_execution_time,
                                "thoughts": result.thoughts,
                                "partial_results_count": len(previous_results),
                                "input_tokens": iteration_input_tokens,
                                "output_tokens": iteration_output_tokens,
                                "total_tokens": iteration_total_tokens
                            })
                            iteration_span.set_attributes({
                                "token_usage.input_tokens": iteration_input_tokens,
                                "token_usage.output_tokens": iteration_output_tokens,
                                "token_usage.total_tokens": iteration_total_tokens
                            })
                            iteration_span.set_status("OK")

                            logger.debug(f"Code execution completed in {code_execution_time:.2f}s")

                            # Continue to next iteration
                            continue

                        except Exception as e:
                            code_execution_time = time.time() - code_execution_start
                            error_msg = f"Code execution failed: {str(e)}"
                            logger.error(error_msg)

                            # Store error result for next iteration
                            iteration_result = f"Iteration {iteration + 1}: Error - {error_msg}"
                            previous_results.append(iteration_result)

                            # Log execution error
                            exec_span.set_outputs({
                                "error": error_msg,
                                "execution_time": code_execution_time,
                                "code_success": False
                            })
                            exec_span.set_status("ERROR")

                            iteration_span.set_outputs({
                                "iteration_number": iteration + 1,
                                "code_executed": False,
                                "execution_error": error_msg,
                                "input_tokens": iteration_input_tokens,
                                "output_tokens": iteration_output_tokens,
                                "total_tokens": iteration_total_tokens
                            })
                            iteration_span.set_attributes({
                                "token_usage.input_tokens": iteration_input_tokens,
                                "token_usage.output_tokens": iteration_output_tokens,
                                "token_usage.total_tokens": iteration_total_tokens
                            })
                            iteration_span.set_status("ERROR")

                            # Continue to next iteration despite error
                            continue

                else:
                    # Handle unexpected result type
                    error_msg = f"Unexpected result type: {type(result)}"
                    logger.error(error_msg)
                    previous_results.append(f"Iteration {iteration + 1}: Error - {error_msg}")

                    iteration_span.set_outputs({
                        "iteration_number": iteration + 1,
                        "unexpected_result_type": str(type(result)),
                        "error": error_msg,
                        "input_tokens": iteration_input_tokens,
                        "output_tokens": iteration_output_tokens,
                        "total_tokens": iteration_total_tokens
                    })
                    iteration_span.set_attributes({
                        "token_usage.input_tokens": iteration_input_tokens,
                        "token_usage.output_tokens": iteration_output_tokens,
                        "token_usage.total_tokens": iteration_total_tokens
                    })
                    iteration_span.set_status("ERROR")
                    continue

            except Exception as e:
                error_msg = f"Iteration {iteration + 1} failed: {str(e)}"
                logger.error(error_msg)

                iteration_span.set_outputs({
                    "iteration_number": iteration + 1,
                    "iteration_error": error_msg,
                    "input_tokens": iteration_input_tokens,
                    "output_tokens": iteration_output_tokens,
                    "total_tokens": iteration_total_tokens
                })
                iteration_span.set_attributes({
                    "token_usage.input_tokens": iteration_input_tokens,
                    "token_usage.output_tokens": iteration_output_tokens,
                    "token_usage.total_tokens": iteration_total_tokens
                })
                iteration_span.set_status("ERROR")
                continue

    # Max iterations reached - return incomplete result
    logger.warning(f"COBBIE reached max iterations ({max_iterations}) without completion")

    # Log final incomplete iteration span
    with mlflow.start_span(name="Max_Iterations_Reached", span_type="CHAIN") as final_span:
        final_span.set_inputs({
            "max_iterations": max_iterations,
            "total_iterations_completed": max_iterations,
            "llm_calls": llm_calls,
            "code_executions": code_execution_count,
            "total_code_execution_time": total_code_execution_time
        })

        final_answer = FinalAnswer(
            thoughts=f"Reached maximum iteration limit ({max_iterations}) without resolving the question. "
                    f"Summary:\n"
                    f"- Total iterations: {max_iterations}\n"
                    f"- LLM calls: {llm_calls}\n"
                    f"- Code executions: {code_execution_count}\n"
                    f"- Total code execution time: {total_code_execution_time:.2f}s\n\n"
                    f"Last 3 attempts:\n" + "\n".join(previous_results[-3:]) if previous_results else "No previous attempts",
            answer="Unable to complete the request due to iteration limit. The question may be too complex or required information may not be accessible with the available tools."
        )

        final_span.set_outputs({
            "final_answer": final_answer.answer,
            "final_reasoning": final_answer.thoughts,
            "termination_reason": "max_iterations_reached",
            "summary": {
                "max_iterations": max_iterations,
                "llm_calls": llm_calls,
                "code_executions": code_execution_count,
                "total_code_execution_time": total_code_execution_time,
                "partial_results_count": len(previous_results)
            }
        })
        final_span.set_status("OK")

        return final_answer


def cobbie_with_metrics(
    user_input: str,
    tools: Dict[str, Callable],
    max_iterations: int = 10,
    model_path: Optional[str] = None,
    add_code_prefix: bool = True,
    **kwargs
) -> Tuple[FinalAnswer, Collector]:
    """
    Execute COBBIE with comprehensive metrics collection.

    Returns FinalAnswer and Collector for performance tracking and analysis.

    Args:
        user_input: The question or task to address
        tools: Dictionary of available tools/functions
        max_iterations: Maximum number of reasoning iterations
        model_path: Optional path to IFC model file
        add_code_prefix: Whether to add boilerplate code prefix
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (FinalAnswer, Collector)
    """
    # Create collector for token tracking
    collector = Collector(name="COBBIE")

    # Add collector to kwargs for BAML calls
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    # Check if we're already in an MLflow run, if not start one
    active_run = mlflow.active_run()
    run_context_manager = nullcontext() if active_run else mlflow.start_run(run_name="COBBIE_Execution_Run")

    with run_context_manager as run:
        # Log parameters to MLflow (following run_evaluation.py pattern)
        params = {
            "component": "COBBIE",
            "engine_type": "baml",
            "max_iterations": max_iterations,
            "add_code_prefix": add_code_prefix,
            "model_path": model_path or "None",
            "tools_count": len(tools),
            "llm_provider": "Z.AI",  # Could be made configurable
            "llm_model": "GLM-4.6"   # Could be made configurable
        }

        # Add tool names as parameters for better traceability
        for i, tool_name in enumerate(tools.keys()):
            params[f"tool_{i+1}"] = tool_name

        mlflow.log_params(params)
        logger.info(f"Logged COBBIE parameters: {params}")

        # Start MLflow span for the entire execution
        with mlflow.start_span(name="COBBIE", span_type="CHAIN") as cobbie_span:
            # Set span inputs
            cobbie_span.set_inputs({
                "user_input": user_input,
                "max_iterations": max_iterations,
                "model_path": model_path or "None",
                "tools_count": len(tools)
            })

            # Execute COBBIE and measure time within the main span context
            start_time = time.time()
            final_answer = cobbie(
                user_input=user_input,
                tools=tools,
                max_iterations=max_iterations,
                model_path=model_path,
                add_code_prefix=add_code_prefix,
                **kwargs
            )
            execution_time = time.time() - start_time

            # Extract token usage from collector (following baml_common.py pattern)
            input_tokens = 0
            output_tokens = 0

            if collector and collector.last and collector.last.usage:
                usage = collector.last.usage
                input_tokens = usage.input_tokens or 0
                output_tokens = usage.output_tokens or 0

            total_tokens = input_tokens + output_tokens

            # Log metrics to MLflow
            mlflow.log_metrics({
                "cobbie_input_tokens": input_tokens,
                "cobbie_output_tokens": output_tokens,
                "cobbie_total_tokens": total_tokens,
                "cobbie_execution_time": execution_time,
                "cobbie_success": 1 if "iteration limit" not in final_answer.answer.lower() else 0
            })

            # Set span outputs and attributes
            cobbie_span.set_outputs({
                "final_answer": final_answer.answer,
                "reasoning": final_answer.thoughts,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "execution_time": execution_time,
                "success": "iteration limit" not in final_answer.answer.lower()
            })

            cobbie_span.set_attributes({
                "token_usage.input_tokens": input_tokens,
                "token_usage.output_tokens": output_tokens,
                "token_usage.total_tokens": total_tokens,
                "execution_time_seconds": execution_time
            })

            logger.info(f"COBBIE with metrics completed. Tokens: {total_tokens}, Time: {execution_time:.2f}s")

            return final_answer, collector


def cobbie_forward(
    question: str,
    path_ifc_model: str = "",
    config: Optional[IfcAnswerEngineConfig] = None,
    tools: Optional[list[Callable]] = None
) -> ModuleOutput:
    """
    Backward compatibility wrapper that returns ModuleOutput.

    This function provides compatibility with the existing IfcAnswerEngine interface.
    Can be removed when all calling code is updated to use FinalAnswer directly.

    Args:
        question: The question to answer
        path_ifc_model: Path to the IFC model file
        config: Optional engine configuration
        tools: Optional list of tools (if None, default tools will be used)

    Returns:
        ModuleOutput compatible with existing interface
    """
    # Use provided config or create default
    if config is None:
        config = IfcAnswerEngineConfig()

    # Setup tools if not provided
    if tools is None:
        from src.engine.tools.primordial import query_ifcopenshell_documentation, web_search
        tools = [query_ifcopenshell_documentation, web_search]

    # Convert tools list to dictionary for internal use
    tools_dict = {tool.__name__: tool for tool in tools if callable(tool)}

    # Execute COBBIE
    try:
        final_answer = cobbie(
            user_input=question,
            tools=tools_dict,
            max_iterations=config.max_iters,
            model_path=path_ifc_model or None,
            add_code_prefix=config.add_code_prefix
        )

        # Convert FinalAnswer to ModuleOutput for compatibility
        return _final_answer_to_module_output(final_answer)

    except Exception as e:
        # Handle errors gracefully
        logger.error(f"Error in cobbie_forward: {e}")
        output = ModuleOutput()
        output.status = "error"
        output.error_msg = f"COBBIE execution failed: {str(e)}"
        return output


def _reasoning_step(
    user_input: str,
    available_tools: str,
    previous_results: list[str],
    model_path: Optional[str] = None,
    **kwargs
) -> CodeAction | FinalAnswer:
    """
    Execute a single reasoning step using BAML.

    This function represents one iteration of the reasoning loop,
    calling the LLM to either generate code or provide a final answer.

    Args:
        user_input: The original question or task
        available_tools: Documentation of available tools
        previous_results: Results from previous iterations
        model_path: Optional path to IFC model file
        **kwargs: Additional arguments for BAML function (including baml_options)

    Returns:
        CodeAction to continue reasoning or FinalAnswer to stop
    """
    # Prepare previous attempts string
    previous_str = "\n".join(previous_results) if previous_results else None

    # Extract baml_options if provided for collector integration
    baml_options = kwargs.pop("baml_options", {})

    # Call BAML function with union return type and proper options handling
    if baml_options:
        result = b.with_options(**baml_options).BIMQAS(
            user_input=user_input,
            available_tools=available_tools,
            previous_attempts=previous_str,
            model_path=model_path
        )
    else:
        result = b.BIMQAS(
            user_input=user_input,
            available_tools=available_tools,
            previous_attempts=previous_str,
            model_path=model_path
        )

    return result


def _final_answer_to_module_output(final_answer: FinalAnswer) -> ModuleOutput:
    """
    Convert FinalAnswer to ModuleOutput for backward compatibility.

    Args:
        final_answer: The FinalAnswer result from COBBIE

    Returns:
        ModuleOutput compatible with existing interface
    """
    output = ModuleOutput()
    output.status = "success"
    output.result.answer = final_answer.answer
    output.result.reasoning = final_answer.thoughts
    return output
