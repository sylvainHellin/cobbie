from typing import Callable, List, Dict, Any, Optional
import mlflow
import inspect
import time

from baml_client import b
from baml_client.types import CodeAction, FinalAnswer

from src.engine.schemas import ModuleOutput
from src.engine.tools.primordial.python_interpreter import get_python_interpreter
from src.engine.util import get_logger, get_created_tools, create_code_prefix
from src.config.agents import FUNCTION_BOILERPLATE, IfcAnswerEngineConfig

# BAML result types
from baml_client.types import CodeAction, FinalAnswer
from pydantic import BaseModel


class BIMQASResult(BaseModel):
    """Typed result for BIM_QAS execution."""

    status: str  # "success", "incomplete", "error"
    answer: Optional[str] = None
    reasoning: Optional[str] = None
    iterations: int
    previous_results: List[str]
    total_execution_time: float
    baml_calls_made: int
    code_executions: int
    error: Optional[str] = None


class BIM_QAS:
    """BAML-based alternative to DSPy Engine"""

    def __init__(
        self,
        additional_authorized_functions: Optional[Dict[str, Callable]] = {
            "web_search": None,  # Will be set in _setup_tools
            "query_ifcopenshell_documentation": None,  # Will be set in _setup_tools
        },
        additional_authorized_imports: Optional[List[str]] = None,
        config: Optional[IfcAnswerEngineConfig] = None,
        llm: Optional[Any] = None,  # For compatibility with IfcAnswerEngine interface
        tools: Optional[List[Callable]] = None,
        max_iterations: Optional[int] = None,
        add_code_prefix: Optional[bool] = None,
        path_ifc_model: str = "",
        max_tokens_logs: Optional[int] = None,
        log_level: Optional[str] = None
    ):
        # Use provided config or default
        if config:
            self.config = config
        else:
            # Create a config-like object for BAML
            self.config = type('Config', (), {
                'max_iters': max_iterations or 10,
                'log_level': log_level or "INFO",
                'max_tokens_logs': max_tokens_logs or 2**12,
                'add_code_prefix': add_code_prefix if add_code_prefix is not None else False,
                'import_all_created_tools': True
            })()

        # Initialize attributes from config or direct parameters
        self.max_iterations = self.config.max_iters
        self.log_level = self.config.log_level
        self.max_tokens_logs = self.config.max_tokens_logs
        self.add_code_prefix = self.config.add_code_prefix
        self.path_ifc_model = path_ifc_model

        # Tools and functions
        self.tools = tools or []
        self.additional_authorized_functions = additional_authorized_functions or {}
        self.additional_authorized_imports = additional_authorized_imports or []

        self.logger = get_logger(name="BIM_QAS", log_level=self.log_level)

        # Setup tools including primordial ones
        self._setup_tools()

        # Setup interpreter
        self._setup_interpreter()

    def _setup_tools(self):
        """Setup available tools including primordial and created tools"""
        # Add primordial tools
        from src.engine.tools.primordial import (
            query_ifcopenshell_documentation,
            web_search,
        )

        self.additional_authorized_functions.update({
            "web_search": web_search,
            "query_ifcopenshell_documentation": query_ifcopenshell_documentation,
        })

        # Add custom tools
        for tool in self.tools:
            self.additional_authorized_functions[tool.__name__] = tool

        # Add created tools if they exist
        try:
            created_tools = get_created_tools()
            self.additional_authorized_functions.update(created_tools)
        except Exception as e:
            self.logger.warning(f"Could not load created tools: {e}")

    def _setup_interpreter(self):
        """Setup the Python interpreter with all available functions"""
        self.python_interpreter = get_python_interpreter(
            additional_authorized_functions=self.additional_authorized_functions,
            max_tokens_logs=self.max_tokens_logs
        )

    def _generate_tools_docs(self) -> str:
        """Generate tool documentation for prompts"""
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
        """Prepare code prefix if needed"""
        if not self.add_code_prefix or not self.path_ifc_model:
            return None

        return create_code_prefix(
            path_ifc_model=self.path_ifc_model,
            imports_boilerplate=FUNCTION_BOILERPLATE
        )

    def run(self, user_input: str) -> BIMQASResult:
        """Orchestration layer for the CodeAct logic using BAML with MLflow tracing"""

        run_start_time = time.time()

        with mlflow.start_span(name="BIMQAS_BAML_Run", span_type="CHAIN") as run_span:
            # Log run-level inputs and metadata
            run_span.set_inputs({
                "user_input": user_input,
                "available_tools_count": len(self.additional_authorized_functions),
                "model_path": self.path_ifc_model or "None",
                "max_iterations": self.max_iterations,
                "has_code_prefix": self.add_code_prefix,
                "log_level": self.log_level
            })

            # Set run-level attributes for categorization
            run_span.set_attributes({
                "component": "BIMQAS_BAML",
                "architecture": "CodeAct",
                "model_path": self.path_ifc_model or "no_model"
            })

            previous_results = []
            tools_docs = self._generate_tools_docs()
            code_prefix = self._prepare_code_prefix()

            # Log metrics about tools and configuration
            mlflow.log_metric("tools_available", len(self.additional_authorized_functions))
            mlflow.log_metric("tools_docs_length", len(tools_docs))
            if code_prefix:
                mlflow.log_metric("code_prefix_length", len(code_prefix))

            # Initialize counters for comprehensive metrics
            code_execution_count = 0
            total_code_execution_time = 0
            baml_call_count = 0

            self.logger.info(f"Starting BAML CodeAct execution for: {user_input[:100]}...")

            for iteration in range(self.max_iterations):
                iteration_start_time = time.time()

                with mlflow.start_span(name=f"Iteration_{iteration + 1}", span_type="CHAIN") as iteration_span:
                    self.logger.debug(f"Iteration {iteration + 1}/{self.max_iterations}")

                    # Log iteration context
                    iteration_span.set_inputs({
                        "iteration_number": iteration + 1,
                        "max_iterations": self.max_iterations,
                        "previous_attempts_count": len(previous_results),
                        "previous_context_length": len("\n".join(previous_results[-3:])) if previous_results else 0
                    })

                    # Prepare previous context
                    previous_context = "\n".join(previous_results[-3:]) if previous_results else None

                    try:
                        # BAML function call with tracing
                        with mlflow.start_span(name="BAML_BIMQAS_Call", span_type="MODULE") as baml_span:
                            baml_span.set_inputs({
                                "user_input": user_input,
                                "has_previous_attempts": previous_context is not None,
                                "model_path": self.path_ifc_model or "None",
                                "tools_docs_length": len(tools_docs)
                            })

                            baml_start_time = time.time()
                            result = b.BIMQAS(
                                user_input=user_input,
                                available_tools=tools_docs,
                                previous_attempts=previous_context,
                                model_path=self.path_ifc_model if self.path_ifc_model else None
                            )
                            baml_call_time = time.time() - baml_start_time
                            baml_call_count += 1

                            # Log BAML call metrics
                            mlflow.log_metric(f"baml_call_time_iteration_{iteration + 1}", baml_call_time)
                            baml_span.set_attributes({
                                "llm.provider": "Z.AI",  # Could be made configurable
                                "llm.model": "GLM-4.6"  # Could be made configurable
                            })

                            # Log BAML output with metrics
                            if isinstance(result, CodeAction):
                                baml_span.set_outputs({
                                    "result_type": "CodeAction",
                                    "thoughts": result.thoughts,
                                    "python_code": result.python_code,
                                    "python_code_length": len(result.python_code),
                                    "baml_call_time_seconds": baml_call_time
                                })
                                # Log metrics for code action
                                mlflow.log_metric(f"code_generated_length_iteration_{iteration + 1}", len(result.python_code))
                                mlflow.log_metric(f"has_thoughts", 1 if result.thoughts else 0)

                            elif isinstance(result, FinalAnswer):
                                baml_span.set_outputs({
                                    "result_type": "FinalAnswer",
                                    "thoughts": result.thoughts,
                                    "answer": result.answer,
                                    "answer_length": len(result.answer),
                                    "baml_call_time_seconds": baml_call_time
                                })
                                # Log metrics for final answer
                                mlflow.log_metric(f"final_answer_length", len(result.answer))
                                mlflow.log_metric(f"has_reasoning", 1 if result.thoughts else 0)

                        # Process the result
                        if isinstance(result, CodeAction):
                            # Code execution with tracing

                            execution_start = time.time()
                            with mlflow.start_span(name="Python_Code_Execution", span_type="MODULE") as exec_span:
                                try:
                                    code_to_execute = result.python_code

                                    # Add code prefix if available
                                    if code_prefix:
                                        code_to_execute = f"{code_prefix}\n{code_to_execute}"

                                    exec_span.set_inputs({
                                        "code_length": len(code_to_execute),
                                        "has_code_prefix": bool(code_prefix),
                                        "code_prefix_length": len(code_prefix) if code_prefix else 0,
                                        "code_preview": code_to_execute[:300] + "..." if len(code_to_execute) > 300 else code_to_execute
                                    })

                                    self.logger.debug(f"Executing code: {code_to_execute[:200]}...")
                                    output = self.python_interpreter(code_to_execute)
                                    execution_time = time.time() - execution_start
                                    code_execution_count += 1
                                    total_code_execution_time += execution_time

                                    result_msg = f"Code: {result.python_code}\nResult: {output}"
                                    previous_results.append(result_msg)
                                    self.logger.debug(f"Code execution successful: {output[:100]}...")

                                    # Log execution results with metrics
                                    exec_span.set_outputs({
                                        "execution_successful": True,
                                        "execution_time_seconds": execution_time,
                                        "output_length": len(output),
                                        "output_preview": output[:200] + "..." if len(output) > 200 else output,
                                        "code_execution_number": code_execution_count
                                    })
                                    exec_span.set_attributes({"execution.status": "success"})

                                    # Log iteration-level metrics
                                    mlflow.log_metric(f"code_execution_time_iteration_{iteration + 1}", execution_time)
                                    mlflow.log_metric(f"output_length_iteration_{iteration + 1}", len(output))

                                except Exception as e:
                                    execution_time = time.time() - execution_start
                                    error_msg = f"Code: {result.python_code}\nError: {str(e)}"
                                    previous_results.append(error_msg)
                                    self.logger.error(f"Code execution failed: {str(e)}")

                                    # Log execution error with metrics
                                    exec_span.set_outputs({
                                        "execution_successful": False,
                                        "execution_time_seconds": execution_time,
                                        "error_message": str(e),
                                        "error_type": type(e).__name__,
                                        "code_execution_number": code_execution_count + 1
                                    })
                                    exec_span.set_attributes({
                                        "execution.status": "error",
                                        "error.type": type(e).__name__
                                    })

                                    # Log error metrics
                                    mlflow.log_metric(f"code_execution_error_iteration_{iteration + 1}", 1)

                        elif isinstance(result, FinalAnswer):
                            # Done! Type checking tells us we're finished
                            total_execution_time = time.time() - run_start_time
                            self.logger.info(f"BAML CodeAct completed in {iteration + 1} iterations")

                            final_result = BIMQASResult(
                                status="success",
                                answer=result.answer,
                                reasoning=result.thoughts,
                                iterations=iteration + 1,
                                previous_results=previous_results,
                                total_execution_time=total_execution_time,
                                baml_calls_made=baml_call_count,
                                code_executions=code_execution_count
                            )

                            # Log final result and comprehensive metrics
                            run_span.set_outputs(final_result.model_dump())
                            iteration_span.set_outputs({
                                "iteration_completed": True,
                                "final_answer_found": True,
                                "iteration_time_seconds": time.time() - iteration_start_time
                            })

                            # Run-level metrics
                            mlflow.log_metric("total_execution_time_seconds", total_execution_time)
                            mlflow.log_metric("iterations_used", iteration + 1)
                            mlflow.log_metric("baml_calls_total", baml_call_count)
                            mlflow.log_metric("code_executions_total", code_execution_count)
                            mlflow.log_metric("avg_code_execution_time", total_code_execution_time / max(code_execution_count, 1))
                            mlflow.log_metric("success_status", 1)
                            mlflow.log_metric("efficiency_score", (iteration + 1) / self.max_iterations)  # Lower is better

                            # Set final attributes
                            run_span.set_attributes({
                                "run.status": "success",
                                "completion.iteration": iteration + 1
                            })

                            return final_result

                    except Exception as e:
                        self.logger.error(f"BAML function call failed: {str(e)}")
                        previous_results.append(f"BAML Error: {str(e)}")

                        # Log error at iteration level
                        iteration_span.set_attributes({
                            "iteration.status": "error",
                            "error.type": type(e).__name__
                        })
                        iteration_span.set_outputs({
                            "iteration_completed": False,
                            "error_message": str(e),
                            "iteration_time_seconds": time.time() - iteration_start_time
                        })

                        # Log error metrics
                        mlflow.log_metric(f"baml_error_iteration_{iteration + 1}", 1)

            # Max iterations reached
            total_execution_time = time.time() - run_start_time
            self.logger.warning(f"BAML CodeAct reached max iterations ({self.max_iterations})")
            incomplete_result = BIMQASResult(
                status="incomplete",
                answer=None,
                reasoning=None,
                iterations=self.max_iterations,
                previous_results=previous_results,
                error="Maximum iterations reached without completion",
                total_execution_time=total_execution_time,
                baml_calls_made=baml_call_count,
                code_executions=code_execution_count
            )

            # Log incomplete result and metrics
            run_span.set_outputs(incomplete_result.model_dump())
            run_span.set_attributes({
                "run.status": "incomplete",
                "completion.reason": "max_iterations_reached"
            })

            # Run-level metrics for incomplete runs
            mlflow.log_metric("total_execution_time_seconds", total_execution_time)
            mlflow.log_metric("iterations_used", self.max_iterations)
            mlflow.log_metric("baml_calls_total", baml_call_count)
            mlflow.log_metric("code_executions_total", code_execution_count)
            mlflow.log_metric("success_status", 0)
            mlflow.log_metric("completion_rate", self.max_iterations / self.max_iterations)  # Always 1.0 for max iterations

            return incomplete_result

    def forward(self, question: str, path_ifc_model: str = "") -> ModuleOutput:
        """
        Interface-compatible method matching IfcAnswerEngine.forward()

        Args:
            question: The question to answer
            path_ifc_model: Path to the IFC model file

        Returns:
            ModuleOutput: Compatible output format
        """
        self.logger.info("Starting forward pass with BAML engine.")

        # Update path_ifc_model if provided
        if path_ifc_model:
            original_path = self.path_ifc_model
            self.path_ifc_model = path_ifc_model
            # Re-setup interpreter with new model path
            self._setup_interpreter()

        # Initialize ModuleOutput
        output = ModuleOutput()

        try:
            # Run the BAML engine
            baml_result = self.run(user_input=question)

            # Convert BIMQASResult to ModuleOutput
            output = self._baml_result_to_module_output(baml_result)

            self.logger.info(f"BAML engine completed with status: {output.status}")

        except Exception as e:
            output.status = "error"
            output.error_msg = f"Error during BAML engine forward pass: {str(e)}"
            self.logger.error(output.error_msg)

        # Restore original path if we changed it
        if path_ifc_model and 'original_path' in locals():
            self.path_ifc_model = original_path
            self._setup_interpreter()

        return output

    def __call__(self, question: str, path_ifc_model: str = "") -> ModuleOutput:
        """
        Alternative interface for direct calling compatibility
        """
        return self.forward(question=question, path_ifc_model=path_ifc_model)

    def _baml_result_to_module_output(self, result: BIMQASResult) -> ModuleOutput:
        """
        Convert BAML engine BIMQASResult to ModuleOutput format

        Args:
            result: BIMQASResult from BAML engine

        Returns:
            ModuleOutput: Compatible output format
        """
        output = ModuleOutput()

        # Map status
        if result.status == "success":
            output.status = "success"
        elif result.status == "incomplete":
            output.status = "error"
            output.error_msg = result.error or "Maximum iterations reached"
        else:
            output.status = "error"
            output.error_msg = result.error or "Unknown error occurred"

        # Set answer if available
        if result.answer:
            output.result.answer = result.answer

        # Set reasoning if available
        if result.reasoning:
            output.result.reasoning = result.reasoning

        # Create mock LM metrics for BAML (since we don't have DSPy LM history)
        output.lm_metrics.llm = "BAML/Z.AI-GLM-4.6"  # Could be made configurable
        output.lm_metrics.input_tokens = result.baml_calls_made * 1000  # Estimate
        output.lm_metrics.output_tokens = result.code_executions * 500  # Estimate
        output.lm_metrics.cost = result.total_execution_time * 0.001  # Estimate

        # Set tools metrics if any tools were used/created
        if result.code_executions > 0:
            output.tools_metrics.nb_tools_created = 0  # BAML doesn't create tools in the same way
            output.tools_metrics.nb_tools_updated = 0
            output.tools_metrics.nb_tools_merged = 0
            output.tools_metrics.cost = 0.0

        return output


if __name__ == "__main__":
    # Test the BAML implementation
    import os
    from dotenv import load_dotenv

    # Load environment variables
    load_dotenv()

    # Setup MLflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("BIMQAS_BAML")

    # Test with a simple question
    test_question = "What is the total number of walls in the building?"

    # Initialize the BAML agent
    agent = BIM_QAS(
        max_iterations=5,
        log_level="INFO"
    )

    # Run the test
    print(f"Testing BAML agent with question: {test_question}")
    result = agent.run(test_question)

    print("Result:")
    print(result)
