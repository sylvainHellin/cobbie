from typing import Callable, List, Dict, Any, Optional
import mlflow
import inspect

from baml_client import b
from baml_client.types import CodeAction, FinalAnswer

from src.engine.tools.primordial.python_interpreter import get_python_interpreter
from src.engine.util import get_logger, get_created_tools, create_code_prefix
from src.config.agents import FUNCTION_BOILERPLATE


class BIMQASBaml:
    """BAML-based alternative to DSPy Engine"""

    def __init__(
        self,
        tools: Optional[List[Callable]] = None,
        max_iterations: int = 10,
        additional_authorized_functions: Optional[Dict[str, Callable]] = None,
        add_code_prefix: bool = False,
        path_ifc_model: str = "",
        max_tokens_logs: int = 2**12,
        log_level: str = "INFO"
    ):
        self.tools = tools or []
        self.max_iterations = max_iterations
        self.additional_authorized_functions = additional_authorized_functions or {}
        self.add_code_prefix = add_code_prefix
        self.path_ifc_model = path_ifc_model
        self.max_tokens_logs = max_tokens_logs
        self.log_level = log_level

        self.logger = get_logger(name="BIMQASBaml", log_level=self.log_level)

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

    def run(self, user_input: str) -> Dict[str, Any]:
        """Orchestration layer for the CodeAct logic using BAML"""

        previous_results = []
        tools_docs = self._generate_tools_docs()
        code_prefix = self._prepare_code_prefix()

        self.logger.info(f"Starting BAML CodeAct execution for: {user_input[:100]}...")

        for iteration in range(self.max_iterations):
            self.logger.debug(f"Iteration {iteration + 1}/{self.max_iterations}")

            # Prepare previous context
            previous_context = "\n".join(previous_results[-3:]) if previous_results else None

            try:
                # Call BAML function
                result = b.BIMQAS(
                    user_input=user_input,
                    available_tools=tools_docs,
                    previous_attempts=previous_context,
                    model_path=self.path_ifc_model if self.path_ifc_model else None
                )

                # Check the returned type to determine action
                if isinstance(result, CodeAction):
                    # Execute code and continue
                    try:
                        code_to_execute = result.python_code

                        # Add code prefix if available
                        if code_prefix:
                            code_to_execute = f"{code_prefix}\n{code_to_execute}"

                        self.logger.debug(f"Executing code: {code_to_execute[:200]}...")
                        output = self.python_interpreter(code_to_execute)

                        result_msg = f"Code: {result.python_code}\nResult: {output}"
                        previous_results.append(result_msg)
                        self.logger.debug(f"Code execution successful: {output[:100]}...")

                    except Exception as e:
                        error_msg = f"Code: {result.python_code}\nError: {str(e)}"
                        previous_results.append(error_msg)
                        self.logger.error(f"Code execution failed: {str(e)}")

                elif isinstance(result, FinalAnswer):
                    # Done! Type checking tells us we're finished
                    self.logger.info(f"BAML CodeAct completed in {iteration + 1} iterations")
                    return {
                        "status": "success",
                        "answer": result.answer,
                        "iterations": iteration + 1,
                        "reasoning": result.thoughts,
                        "previous_results": previous_results
                    }

            except Exception as e:
                self.logger.error(f"BAML function call failed: {str(e)}")
                previous_results.append(f"BAML Error: {str(e)}")

        # Max iterations reached
        self.logger.warning(f"BAML CodeAct reached max iterations ({self.max_iterations})")
        return {
            "status": "incomplete",
            "iterations": self.max_iterations,
            "last_result": previous_results[-1] if previous_results else "No results",
            "previous_results": previous_results,
            "error": "Maximum iterations reached without completion"
        }

  

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
    agent = BIMQASBaml(
        max_iterations=5,
        log_level="INFO"
    )

    # Run the test
    print(f"Testing BAML agent with question: {test_question}")
    result = agent.run(test_question)

    print("Result:")
    print(result)