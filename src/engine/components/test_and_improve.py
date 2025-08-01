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
from src.engine.util import _create_function_from_source_code, get_logger


class TestAndImprove(dspy.Module):
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
        self.config = config or AGENT_CONFIGS.test_and_improve

        # Use provided LLM or get from config
        self.lm = self.config.llm.get_llm()
        dspy.configure(lm=self.lm)
        self.log_level = self.config.log_level
        self.logger = get_logger(name="TestAndImprove", log_level=self.log_level)
        self.max_iter = self.config.max_iter
        self.add_code_prefix = self.config.add_code_prefix

        # Store authorized functions for use in assessor when needed
        self.additional_authorized_functions = additional_authorized_functions
        self.primordial_tools = [
            tool for _, tool in self.additional_authorized_functions.items()
        ]

        self.logger.debug(
            f"Primordial tools available for ToolCreator sub-agents: {', '.join([getattr(tool, '__name__', str(tool)) for tool in self.primordial_tools])}"
        )
        self.tool_corrector = ToolCorrector(
            tools=self.primordial_tools,
            config=self.config.tool_corrector,
        )
        self.tool_assessor = ToolAssessor(
            tools=self.primordial_tools,
            config=self.config.tool_assessor,
        )

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        path_ifc_model: str,
        function_implementation: str,
    ) -> ModuleOutput:
        """
        This function implements a complete pipeline for testing, and refining
        Python functions, given it's source code, name and requirements.

        Args:
            function_requirements: Detailed description of what the function should do
            function_name: Name for the generated function
            path_ifc_model: Path to IFC file used for testing the generated function
            function_implementation: The source code of this function

        Returns:
            ModuleOutput containing:
            - result.python_code: Generated function code (if successful)
            - result.assessment_status: "ok" or "needs_improvement"
            - result.assessment_details: Detailed assessment feedback
            - status: "success" or "error"
            - error_msg: Error description (if status is "error")
        """

        # Reset iteration counter before starting the new assess/correct loop
        self.iter = 0

        with mlflow.start_span(
            name="TestAndImprove",
            span_type="MODULE",
        ) as span:
            output = ModuleOutput(status="error")

            # Set initial span attributes
            span.set_attribute("function_name", function_name)
            span.set_attribute("path_ifc_model", path_ifc_model)
            span.set_attribute("function_requirements", function_requirements)
            span.set_attribute("function_implementation", function_implementation)

            self.logger.info(
                f"Starting the testing and improvement of the tool: {function_name}"
            )

            # --- Iterative improvement loop --- #
            while self.iter < self.max_iter:
                self.iter += 1

                with mlflow.start_span(
                    name=f"iter_{self.iter}",
                    span_type="CHAIN",
                ):
                    # Create enhanced assessor with dynamic tool
                    self.logger.info("Assessing the generated code.")
                    try:
                        new_tool = _create_function_from_source_code(
                            function_name=function_name,
                            code=function_implementation,
                        )

                        # Create ToolAssessor with primordial tools and the generated tool
                        # The CodeAct-based assessor will create its own Python interpreter internally
                        tools = self.primordial_tools + [new_tool]
                        self.tool_assessor = ToolAssessor(
                            tools=tools, config=self.config.tool_assessor
                        )
                        self.logger.info(
                            "✓ ToolAssessor created with new tool to test."
                        )

                    except Exception as e:
                        self.logger.error(
                            f"✗ Failed to create ToolAssessor. Error: {str(e)}"
                        )
                        self.logger.debug(
                            f"Code that failed: {function_implementation}"
                        )
                        continue

                    # Assess if the function works properly
                    with mlflow.start_span(name="ToolAssessor", span_type="MODULE"):
                        try:
                            self.logger.info("Starting the tool assessment.")

                            output_tool_assessor = self.tool_assessor.forward(
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

                    # If the assessment is good, update the ouput and exit the loop
                    if output_tool_assessor.result.assessment_status == "ok":
                        self.logger.info(
                            f"🎉 Function passed assessment after {self.iter} iterations!"
                        )
                        output.result.function_implementation = function_implementation
                        output.status = "success"
                        output.result.assessment_status = (
                            output_tool_assessor.result.assessment_status
                        )
                        output.result.assessment_details = (
                            output_tool_assessor.result.assessment_details
                        )
                        break

                    # If the assessment is not satisfactory, call the ToolCorrector
                    else:
                        with mlflow.start_span(
                            name="ToolCorrector",
                            span_type="MODULE",
                        ):
                            self.logger.info("Starting the ToolCorrector")

                            output_tool_corrector = self.tool_corrector.forward(
                                function_description=function_requirements,
                                function_name=function_name,
                                path_ifc_model=path_ifc_model,
                                current_function_implementation=function_implementation,
                                detailed_function_assessment=output_tool_assessor.result.assessment_details
                                or "No assessment available.",
                            )

                            if output_tool_corrector.status == "error":
                                self.logger.error("✗ Correction failed.")
                                continue
                            else:
                                function_implementation = (
                                    output_tool_corrector.result.function_implementation
                                    or ""
                                )
                                self.logger.info("✓ Function corrected")
                                self.logger.debug(
                                    f"New function implementation:\n{function_implementation}"
                                )
            # Set final span outputs and attributes
            span.set_inputs(
                {
                    "function_name": function_name,
                    "function_requirements": function_requirements,
                    "path_ifc_model": path_ifc_model,
                }
            )
            span.set_outputs(
                {
                    "status": output.status,
                    "error_msg": output.error_msg or "",
                    "function_implementation": output.result.function_implementation,
                    "assessment_status": output.result.assessment_status,
                    "assessment_details": output.result.assessment_details,
                }
            )

            # Return the result (good or bad)
            return output


if __name__ == "__main__":
    """
    Test module for TestAndImprove component.

    This test demonstrates the complete pipeline for testing and improving
    a Python function implementation.
    """
    import os

    from src.config.agents import AGENT_CONFIGS, LLMConfig
    from src.config.main import TEST_IFC_PATH

    def main():
        """Test the TestAndImprove module with a sample function."""
        # Setup MLflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("TestAndImprove")

        # Test function implementation that needs improvement
        test_function_implementation = '''
def count_doors(ifc_file_path: str) -> int:
    """Count all doors in an IFC model."""
    # This is an intentionally flawed implementation for testing
    import ifcopenshell
    model = ifcopenshell.open(ifc_file_path)
    doors = model.by_type("IfcDoor")
    # Bug: returning a string instead of int
    return str(len(doors))
'''

        # Test configuration
        test_config = {
            "function_requirements": """
        Create a function that counts the total number of doors in an IFC model.
        The function should:
        1. Take an IFC file path as input
        2. Open the IFC model using ifcopenshell
        3. Find all door elements (IfcDoor)
        4. Return the count as an integer

        The function should handle errors gracefully and return accurate counts.
        """,
            "function_name": "count_doors",
            "path_ifc_model": TEST_IFC_PATH,
            "function_implementation": test_function_implementation.strip(),
        }

        print("=" * 80)
        print("TESTING TestAndImprove MODULE")
        print("=" * 80)

        # Check if IFC file exists
        if not os.path.exists(test_config["path_ifc_model"]):
            print(f"❌ Test IFC file not found: {test_config['path_ifc_model']}")
            print("Please ensure the test IFC file exists before running tests.")
            exit(1)

        print(f"✅ Test IFC file found: {test_config['path_ifc_model']}")

        try:
            # Initialize TestAndImprove with test configuration
            print("\n📋 Initializing TestAndImprove module...")

            # Use a lightweight LLM config for testing
            test_llm_config = LLMConfig(model_name="qwen3-coder", max_tokens=4096)
            test_agent_config = AGENT_CONFIGS.test_and_improve
            test_agent_config.llm = test_llm_config
            test_agent_config.max_iter = 2  # Limit iterations for testing

            test_and_improve = TestAndImprove(config=test_agent_config)
            print("✅ TestAndImprove module initialized successfully")

            # Test the forward method
            print(f"\n🔧 Testing function: {test_config['function_name']}")
            print(
                f"📝 Function requirements: {test_config['function_requirements'][:100]}..."
            )
            print("🏗️  Initial implementation has intentional bugs for testing")

            print("\n🚀 Starting test and improvement process...")
            result = test_and_improve.forward(
                function_requirements=test_config["function_requirements"],
                function_name=test_config["function_name"],
                path_ifc_model=test_config["path_ifc_model"],
                function_implementation=test_config["function_implementation"],
            )

            # Analyze results
            print("\n" + "=" * 60)
            print("TEST RESULTS")
            print("=" * 60)

            print(f"Status: {result.status}")
            if result.error_msg:
                print(f"Error: {result.error_msg}")

            if hasattr(result.result, "assessment_status"):
                print(f"Assessment Status: {result.result.assessment_status}")

            if hasattr(result.result, "assessment_details"):
                print(f"Assessment Details: {result.result.assessment_details}")

            if (
                hasattr(result.result, "function_implementation")
                and result.result.function_implementation
            ):
                print("\nImproved Function Implementation:")
                print("-" * 40)
                print(result.result.function_implementation)
                print("-" * 40)

            # Test success criteria
            if result.status == "success":
                print(
                    "\n✅ TEST PASSED: Function was successfully tested and improved!"
                )
            else:
                print(
                    "\n⚠️  TEST COMPLETED: Function improvement process completed with issues"
                )

        except Exception as e:
            print(f"\n❌ TEST FAILED: {str(e)}")
            import traceback

            traceback.print_exc()

        print("\n" + "=" * 80)
        print("TEST COMPLETED")
        print("=" * 80)

    # Run the test
    main()
