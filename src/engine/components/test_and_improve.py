from typing import Callable, Dict, Optional, cast

import dspy
import mlflow

from src.config.agents import (
    AGENT_CONFIGS,
    TestAndImproveConfig,
)
from src.engine.components.tool_assessor import ToolAssessor
from src.engine.components.tool_corrector import ToolCorrector
from src.engine.schemas import ModuleOutput
from src.engine.tools.primordial import (
    query_ifcopenshell_documentation,
    web_search,
)
from src.engine.util import (
    _create_function_from_source_code,
    get_logger,
)


class TestAndImprove(dspy.Module):
    def __init__(
        self,
        additional_authorized_functions: Dict[str, Callable] = {
            "web_search": web_search,
            "query_ifcopenshell_documentation": query_ifcopenshell_documentation,
        },
        config: Optional[TestAndImproveConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()

        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.test_and_improve
        self.lm = lm or self.config.llm.get_llm()

        # Use provided LLM or get from config
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
            lm=self.lm,
        )
        self.tool_assessor = ToolAssessor(
            tools=self.primordial_tools,
            config=self.config.tool_assessor,
            lm=self.lm,
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

        # with mlflow.start_span(
        #     name="TestAndImprove",
        #     span_type="MODULE",
        # ) as span:
        if True:
            self.output = ModuleOutput(status="error")
            self.output.llm = self.lm.model
            self.output.result.function_implementation = function_implementation

            self.logger.info(
                f"Starting the testing and improvement of the tool: {function_name}"
            )

            try:
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
                                tools=tools,
                                config=self.config.tool_assessor,
                                lm=self.lm,
                            )
                            self.logger.info(
                                "✓ ToolAssessor created with new tool to test."
                            )

                        except Exception as e:
                            self.output.error_msg = (
                                f"✗ Failed to create ToolAssessor. Error: {str(e)}"
                            )
                            self.logger.error(self.output.error_msg)
                            self.logger.debug(
                                f"Code that failed: {function_implementation}"
                            )
                            continue

                        # Assess if the function works properly
                        with mlflow.start_span(name="ToolAssessor", span_type="MODULE"):
                            try:
                                output_tool_assessor = cast(
                                    ModuleOutput,
                                    self.tool_assessor(
                                        function_name=function_name,
                                        function_requirements=function_requirements,
                                        path_ifc_model=path_ifc_model,
                                    ),
                                )
                                self.output.combine_cost(output=output_tool_assessor)
                                self.output.result.assessment_status = (
                                    output_tool_assessor.result.assessment_status
                                )
                                self.output.result.assessment_details = (
                                    output_tool_assessor.result.assessment_details
                                )

                            except Exception as e:
                                self.logger.error(f"✗ Assessment failed: {str(e)}")
                                continue

                        # If the assessment is good, update the ouput and exit the loop
                        if output_tool_assessor.result.assessment_status == "ok":
                            self.logger.info(
                                f"🎉 Function passed assessment after {self.iter} iterations!"
                            )
                            self.output.status = "success"
                            break

                        # If the assessment is not satisfactory, call the ToolCorrector
                        else:
                            with mlflow.start_span(
                                name="ToolCorrector",
                                span_type="MODULE",
                            ):
                                output_tool_corrector = cast(
                                    ModuleOutput,
                                    self.tool_corrector(
                                        function_description=function_requirements,
                                        function_name=function_name,
                                        path_ifc_model=path_ifc_model,
                                        current_function_implementation=function_implementation,
                                        detailed_function_assessment=output_tool_assessor.result.assessment_details
                                        or "No assessment available.",
                                    ),
                                )
                                self.output.combine_cost(output=output_tool_corrector)

                                if output_tool_corrector.status == "success":
                                    self.output.result.function_implementation = output_tool_corrector.result.function_implementation
                                else:
                                    self.output.error_msg = (
                                        output_tool_corrector.error_msg
                                    )

            except Exception as e:
                self.output.error_msg = f"An Exception occured during the TestAndImprove forward pass:\nError:{e}\n"
                self.logger.error(self.output.error_msg)

            finally:
                # Return the result (good or bad)
                return self.output


if __name__ == "__main__":
    from src.config.main import TEST_IFC_PATH
    from typing import cast

    # setup mlflow
    mlflow.dspy.autolog()  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("TestAndImprove")

    # deactivate cache for dspy
    dspy.configure_cache(
        enable_disk_cache=False,
        enable_memory_cache=False,
    )

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
    path_ifc_model = TEST_IFC_PATH
    function_implementation = '''
    import ifcopenshell
    def count_doors(ifc_file_path: str) -> int:
        """Count all doors in an IFC model."""
        model = ifcopenshell.open(ifc_file_path)
        doors = model.by_type("IfcDoor")
        return str(len(doors))
    '''
    test_and_improve = TestAndImprove()
    output = cast(
        ModuleOutput,
        test_and_improve(
            function_name=function_name,
            function_requirements=function_requirements,
            path_ifc_model=path_ifc_model,
            function_implementation=function_implementation,
        ),
    )
    print(output.model_dump())
