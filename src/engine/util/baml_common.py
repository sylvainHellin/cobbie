"""
Common utilities for BAML implementations, extracted from BIM_QAS patterns.
Provides reusable patterns for tool setup, interpreter configuration, and MLflow integration.
"""

import inspect
import time
import mlflow
from typing import Callable, Dict, Any, Optional, Tuple

from baml_client import b
from baml_py import Collector
from baml_client.types import CodeAction, FunctionImplementation

from src.engine.tools.primordial.python_interpreter import get_python_interpreter
from src.engine.util import get_logger, get_created_tools, create_code_prefix


class BamlComponentBase:
    """Base class for BAML components with common patterns extracted from BIM_QAS."""

    def __init__(
        self,
        log_level: str = "INFO",
        max_iterations: int = 10,
        path_ifc_model: str = "",
        max_tokens_logs: int = 2**12
    ):
        self.log_level = log_level
        self.max_iterations = max_iterations
        self.path_ifc_model = path_ifc_model
        self.max_tokens_logs = max_tokens_logs

        self.logger = get_logger(name=self.__class__.__name__, log_level=self.log_level)

        # Setup tools and interpreter using BIM_QAS patterns
        self.additional_authorized_functions: Dict[str, Callable] = {}
        self._setup_tools()
        self._setup_interpreter()

    def _setup_tools(self):
        """Setup available tools including primordial and created tools - BIM_QAS pattern."""
        # Add primordial tools
        from src.engine.tools.primordial import (
            query_ifcopenshell_docs,
            web_search,
        )

        self.additional_authorized_functions.update({
            "web_search": web_search,
            "query_ifcopenshell_docs": query_ifcopenshell_docs,
        })

        # Add created tools if they exist
        try:
            created_tools = get_created_tools()
            self.additional_authorized_functions.update(created_tools)
        except Exception as e:
            self.logger.warning(f"Could not load created tools: {e}")

    def _setup_interpreter(self):
        """Setup the Python interpreter with all available functions - BIM_QAS pattern."""
        self.python_interpreter = get_python_interpreter(
            additional_authorized_functions=self.additional_authorized_functions,
            max_tokens_logs=self.max_tokens_logs
        )

    def _generate_tools_docs(self) -> str:
        """Generate tool documentation for prompts - BIM_QAS pattern."""
        docs = []
        for name, tool in self.additional_authorized_functions.items():
            if callable(tool):
                try:
                    sig = inspect.signature(tool)
                    docstring = inspect.getdoc(tool) or "No documentation"
                    # Clean up docstring formatting
                    docstring_lines = []
                    in_code_block = False
                    for line in docstring.strip().split("\n"):
                        line = line.strip()
                        if line.startswith("```"):
                            in_code_block = not in_code_block
                            continue
                        if not in_code_block and line:
                            docstring_lines.append(line)

                    clean_docstring = " ".join(docstring_lines) if docstring_lines else "No documentation"
                    docs.append(f"def {name}{sig}:\n    '''{clean_docstring}'''")
                except Exception as e:
                    self.logger.warning(f"Could not get docs for {name}: {e}")
                    docs.append(f"def {name}():\n    '''No documentation available'''")

        return "\n\n".join(docs)

    def _prepare_code_prefix(self) -> Optional[str]:
        """Prepare code prefix if needed - BIM_QAS pattern."""
        if not self.path_ifc_model:
            return None

        from src.config.agents import FUNCTION_BOILERPLATE
        return create_code_prefix(
            path_ifc_model=self.path_ifc_model,
            imports_boilerplate=FUNCTION_BOILERPLATE
        )


def run_baml_function_with_metrics(
    component_name: str,
    baml_function: Callable,
    *args,
    mlflow_tags: Optional[Dict[str, str]] = None,
    **kwargs
) -> Tuple[Any, Collector]:
    """
    Execute a BAML function with automatic metrics collection and detailed MLflow logging.

    Args:
        component_name: Name of the function/component for tracking
        baml_function: The BAML function to call
        *args: Arguments to pass to the BAML function
        mlflow_tags: Optional tags to add to MLflow span
        **kwargs: Additional arguments (including baml_options)

    Returns:
        Tuple of (result, collector) where result is the BAML function output
        and collector contains the token usage information
    """
    # Create collector for tracking
    collector = Collector(name=component_name)

    # Add collector to baml_options if not already present
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    # Start MLflow span for the function call
    with mlflow.start_span(name=f"BAML_{component_name}", span_type="MODULE") as span:
        # Set tags if provided
        if mlflow_tags:
            span.set_attributes(mlflow_tags)

        # Set function-level attributes
        span.set_attributes({
            "component": component_name,
            "architecture": "BAML",
            "model_path": kwargs.get("path_ifc_model") or "no_model"
        })

        # Log actual input parameters
        input_params = {
            "component_name": component_name
        }

        # Add specific parameters from kwargs if they exist
        if "function_requirements" in kwargs:
            input_params["function_requirements"] = kwargs["function_requirements"]
        if "function_name" in kwargs:
            input_params["function_name"] = kwargs["function_name"]
        if "path_ifc_model" in kwargs:
            input_params["path_ifc_model"] = kwargs["path_ifc_model"]
        if "available_tools" in kwargs:
            input_params["available_tools"] = kwargs["available_tools"]
        if "previous_attempts" in kwargs:
            input_params["previous_attempts"] = kwargs["previous_attempts"]
        if "function_boilerplate" in kwargs:
            input_params["function_boilerplate"] = kwargs["function_boilerplate"]

        # Add any positional args (for functions like CodeExtractor)
        if args:
            input_params["positional_args"] = str(args)

        span.set_inputs(input_params)

        # Execute the BAML function
        start_time = time.time()
        result = baml_function(*args, **kwargs)
        execution_time = time.time() - start_time

        # Extract and log detailed LLM interaction information
        if collector.last:
            # Log token usage
            if collector.last.usage:
                usage = collector.last.usage
                input_tokens = usage.input_tokens or 0
                output_tokens = usage.output_tokens or 0
                total_tokens = input_tokens + output_tokens

                # Log token metrics to MLflow
                mlflow.log_metric(f"{component_name}_input_tokens", input_tokens)
                mlflow.log_metric(f"{component_name}_output_tokens", output_tokens)
                mlflow.log_metric(f"{component_name}_total_tokens", total_tokens)
                mlflow.log_metric(f"{component_name}_execution_time", execution_time)

                # Log usage information to span
                span.set_attributes({
                    "token_usage.input_tokens": input_tokens,
                    "token_usage.output_tokens": output_tokens,
                    "token_usage.total_tokens": total_tokens,
                    "execution_time_seconds": execution_time
                })

            # Log detailed LLM interaction if available
            if collector.last and hasattr(collector.last, 'raw_llm_response') and collector.last.raw_llm_response:
                # Log the final raw response from LLM
                raw_response = collector.last.raw_llm_response
                span.set_attributes({
                    "llm.raw_response_length": len(raw_response)
                })
                mlflow.log_text(raw_response, artifact_file=f"{component_name}_raw_llm_response.txt")

            # Log the final prompt sent to LLM if available
            if collector.last and hasattr(collector.last, 'calls') and collector.last.calls:
                last_call = collector.last.calls[-1]
                if hasattr(last_call, 'http_request') and last_call.http_request:
                    http_request = last_call.http_request
                    if hasattr(http_request, 'body') and http_request.body:
                        try:
                            # Get the request body as text (this contains the final prompt)
                            request_body = http_request.body.text()
                            span.set_attributes({
                                "llm.final_prompt_length": len(request_body)
                            })

                            # Parse JSON and extract key information as span attributes
                            import json
                            try:
                                prompt_data = json.loads(request_body)

                                # Log model information
                                if "model" in prompt_data:
                                    span.set_attribute("llm.model", prompt_data["model"])
                                if "temperature" in prompt_data:
                                    span.set_attribute("llm.temperature", prompt_data["temperature"])
                                if "max_tokens" in prompt_data:
                                    span.set_attribute("llm.max_tokens", prompt_data["max_tokens"])

                                # Extract system and user messages
                                if "messages" in prompt_data:
                                    messages = prompt_data["messages"]
                                    system_content = ""
                                    user_content = ""

                                    for message in messages:
                                        if message.get("role") == "system":
                                            content = message.get("content", [])
                                            if isinstance(content, list):
                                                for item in content:
                                                    if isinstance(item, dict) and item.get("type") == "text":
                                                        system_content += item.get("text", "")
                                            else:
                                                system_content = str(content)

                                        elif message.get("role") == "user":
                                            content = message.get("content", [])
                                            if isinstance(content, list):
                                                for item in content:
                                                    if isinstance(item, dict) and item.get("type") == "text":
                                                        user_content += item.get("text", "")
                                            else:
                                                user_content = str(content)

                                    # Log key message content as attributes
                                    if system_content:
                                        span.set_attribute("llm.system_prompt", system_content)
                                        span.set_attribute("llm.system_prompt_length", len(system_content))

                                    if user_content:
                                        span.set_attribute("llm.user_prompt", user_content)
                                        span.set_attribute("llm.user_prompt_length", len(user_content))

                            except json.JSONDecodeError:
                                # If JSON parsing fails, fall back to logging as text
                                self.logger.warning("Could not parse final prompt as JSON, logging as raw text")
                                mlflow.log_text(request_body, artifact_file=f"{component_name}_final_prompt.txt")

                            # Always log the raw request body as artifact for complete reference
                            mlflow.log_text(request_body, artifact_file=f"{component_name}_final_prompt.txt")

                        except Exception as e:
                            self.logger.warning(f"Could not log final prompt: {e}")

            # Log chat request details if available (for backward compatibility)
            if hasattr(collector.last, 'chat_request') and collector.last.chat_request:
                chat_request = collector.last.chat_request

                # Log system prompt
                if hasattr(chat_request, 'system') and chat_request.system:
                    system_prompt = chat_request.system
                    span.set_attributes({
                        "llm.system_prompt_length": len(system_prompt)
                    })
                    mlflow.log_text(system_prompt, artifact_file=f"{component_name}_system_prompt.txt")

                # Log user prompt
                if hasattr(chat_request, 'user') and chat_request.user:
                    user_prompt = chat_request.user
                    span.set_attributes({
                        "llm.user_prompt_length": len(user_prompt)
                    })
                    mlflow.log_text(user_prompt, artifact_file=f"{component_name}_user_prompt.txt")

            # Log LLM response details
            if hasattr(collector.last, 'chat_response') and collector.last.chat_response:
                chat_response = collector.last.chat_response

                # Log raw response
                if hasattr(chat_response, 'content') and chat_response.content:
                    raw_response = chat_response.content
                    span.set_attributes({
                        "llm.raw_response_length": len(raw_response)
                    })
                    mlflow.log_text(raw_response, artifact_file=f"{component_name}_raw_response.txt")

                # Log model information
                if hasattr(chat_response, 'model') and chat_response.model:
                    span.set_attributes({
                        "llm.model": chat_response.model
                    })
                    mlflow.log_param("llm_model", chat_response.model)

        # Log outputs based on result type with actual field values
        if isinstance(result, CodeAction):
            # Log actual CodeAction fields
            span.set_outputs({
                "result_type": "CodeAction",
                "python_code": result.python_code,
                "thought": result.thoughts
            })

            # Log code and reasoning as artifacts
            mlflow.log_text(result.python_code, artifact_file=f"{component_name}_generated_code.py")
            if result.thoughts:
                mlflow.log_text(result.thoughts, artifact_file=f"{component_name}_reasoning.txt")

            # Log structured data
            mlflow.log_dict({
                "result_type": "CodeAction",
                "python_code": result.python_code,
                "thought": result.thoughts
            }, artifact_file=f"{component_name}_result_summary.json")

        elif isinstance(result, FunctionImplementation):
            # Log actual FunctionImplementation fields
            span.set_outputs({
                "result_type": "FunctionImplementation",
                "function_implementation": result.function_implementation,
                "confidence": result.confidence,
                "needs_improvement": result.needs_improvement
            })

            # Log function implementation as artifact
            mlflow.log_text(result.function_implementation, artifact_file=f"{component_name}_function_implementation.py")

            # Log structured data
            mlflow.log_dict({
                "result_type": "FunctionImplementation",
                "function_implementation": result.function_implementation,
                "confidence": result.confidence,
                "needs_improvement": result.needs_improvement
            }, artifact_file=f"{component_name}_result_summary.json")

        else:
            # Log unknown result type
            span.set_outputs({
                "result_type": type(result).__name__,
                "result": str(result) if result else None
            })

            # Log result as artifact
            if result:
                mlflow.log_text(str(result), artifact_file=f"{component_name}_unknown_result.txt")

        return result, collector


def log_code_execution_to_mlflow(
    component_name: str,
    code: str,
    output: str,
    execution_time: float,
    success: bool,
    error_msg: Optional[str] = None
):
    """
    Log code execution results to MLflow with simplified inputs/outputs.

    Args:
        component_name: Name of the component executing the code
        code: The Python code that was executed
        output: The output from code execution
        execution_time: Time taken to execute the code
        success: Whether the execution was successful
        error_msg: Error message if execution failed
    """
    with mlflow.start_span(name=f"Python_Code_Execution_{component_name}", span_type="MODULE") as span:
        # Simplified input: only log the python_code
        span.set_inputs({
            "python_code": code
        })

        span.set_attributes({
            "execution.success": success,
            "execution.time_seconds": execution_time
        })

        # Simplified output: only log the result
        if success:
            span.set_outputs({
                "result": output
            })
            mlflow.log_metric(f"{component_name}_code_execution_success", 1)
        else:
            span.set_outputs({
                "result": error_msg or "Unknown error"
            })
            mlflow.log_metric(f"{component_name}_code_execution_success", 0)
