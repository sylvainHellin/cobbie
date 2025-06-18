"""
Multi-agent tool creation system for generating and validating IFC-related functions.

This module provides a complete pipeline for creating, testing, and correcting Python functions
that work with IFC (Industry Foundation Classes) files using the IfcOpenShell library.

The system uses three main agents:
- ToolCreator: Generates initial function implementations based on requirements
- ToolAssessor: Tests and evaluates generated functions
- ToolCorrector: Improves functions based on assessment feedback

Key features:
- Dynamic function signature support (single or multiple parameters)
- Iterative improvement with up to max_iter correction cycles
- Direct testing and formal LLM-based assessment
- Integration with MLFlow for tracking and logging
- Support for various parameter types and default values
"""

# %% Imports
# =============== Imports and config =============== #
import os
import sys
from typing import Literal, Optional, Callable

import dspy
import mlflow
from pydantic import BaseModel

from src import FUNCTION_BOILERPLATE, LANGUAGE_MODELS, LLM, ROOT_PATH
from src.special_tools import (
    query_ifcopenshell_documentation,
    web_search,
    get_python_interpreter,
)
from src.agents import (
    _create_function_from_source_code,
)
from src.util import get_logger

# Set up the path
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)

# Note: LLM configuration is done per-function call in create_new_tool() to allow flexibility

# Load the overview of the documentation of IfcOpenShell
doc_path = os.path.join(ROOT_PATH, "src/special_tools/ifcopenshell_api_overview_v2.md")
with open(doc_path, "r") as file:
    IFCOPENSHELL_DOCUMENTATION_OVERVIEW = file.read()
del doc_path


# %% Types
# =============== Define Datatypes =============== #
class Result(BaseModel):
    python_code: Optional[str] = None
    assessment_status: Optional[Literal["ok", "needs_improvement"]] = None
    assessment_details: Optional[str] = None


class ModuleOutput(BaseModel):
    result: Result = Result()
    status: Literal["error", "success"]
    error_msg: Optional[str] = None


# %% DSPy
# =============== Define ToolMaker =============== #
class NewToolSignature(dspy.Signature):
    f"""
    Create a Python function that implements the requirements using the IfcOpenShell Python library.
    This function will be used as a "tool" by an LLM-based ReAct agent to answer some user's query related to a BIM model.

    The generated function should:
    - Take at least one argument: path_ifc_file: str, which is a path to the .ifc file the function should interact with.
    - Be well-documented with docstrings and type hints

    IMPORTANT:
    - Do not make assumptions about IFC schema or data structure.
    - Use the provided tools to research proper implementation details through documentation and web search.

    Below is an overview of how the structure of the IfcOpenShell Python library. For details regarding the implementation of each available method, use the `query_ifcopenshell_documentation` tool.

    Overview:
    {IFCOPENSHELL_DOCUMENTATION_OVERVIEW}
    """

    # inputs
    function_requirements: str = dspy.InputField(
        desc="Detailed description of what the function should do and its requirements."
    )
    function_name: str = dspy.InputField()

    function_boilerplate: str = dspy.InputField(
        desc="This boilerplate must be included at the beginning of your code; otherwise, it will not work properly."
    )

    # outputs
    python_code: str = dspy.OutputField(
        desc="Complete code implementation (including imports from the boilerplate, any necessary helper functions, etc.) of your Python function implementation."
    )


class ToolCreator(dspy.Module):
    """Module to create a new Python function that meets the requirements."""

    def __init__(
        self,
        tools: list,
        max_iters: int = 10,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
    ):
        super().__init__()
        self.tools = tools
        self.max_iters = max_iters
        self.agent = dspy.ReAct(
            signature=NewToolSignature, tools=tools, max_iters=self.max_iters
        )
        self.log_level = log_level
        self.logger = get_logger(name="ToolCreator", log_level=self.log_level)

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        function_boilerplate: str = FUNCTION_BOILERPLATE,
    ) -> ModuleOutput:
        result = self.agent(
            function_requirements=function_requirements,
            function_name=function_name,
            function_boilerplate=function_boilerplate,
        )

        # Check if we got valid python code
        if hasattr(result, "python_code") and result.python_code:
            self.logger.info(f"function: {function_name} created successfully.")
            self.logger.debug(f"function code:\n{result.python_code}\n")
            return ModuleOutput(
                result=Result(python_code=result.python_code), status="success"
            )
        else:
            self.logger.error(
                f"Error when trying to generate code for function: {function_name}"
            )
            return ModuleOutput(
                status="error",
                error_msg=f"No valid code generated for function: {function_name}",
            )


# =============== Define ToolAssessor =============== #
class ToolAssessmentSignature(dspy.Signature):
    """
    Assess whether a generated Python function meets requirements and works correctly.

    To perform the assessment, you MUST call the function, which is available to you as a tool.
    The function's name and the path to a test IFC file are provided as inputs.

    1. Call the function with the provided IFC file path.
    2. Examine the return value or any errors.
    3. Compare the result with the original 'function_requirements'.
    4. Based on your findings, provide an assessment 'status' and 'details'.
    """

    # inputs
    function_name: str = dspy.InputField(
        desc="Name of the function to assess. This function is available as a tool."
    )
    function_requirements: str = dspy.InputField(
        desc="Original requirements and description of what the function should do"
    )
    path_ifc_model: str = dspy.InputField(
        desc="Path to an IFC file for testing the function. Use this as an argument when calling the function."
    )

    # outputs
    assessment_status: Literal["ok", "needs_improvement"] = dspy.OutputField(
        desc="'ok' if the tool works as expected, 'needs_improvement' if issues were found"
    )
    assessment_details: str = dspy.OutputField(
        desc="Detailed explanation of the assessment. If the function crashed, include the error. If the output is wrong, explain why. Provide suggestions for correction."
    )


class ToolAssessor(dspy.Module):
    """Module to assess the quality and functionality of generated tools."""

    def __init__(
        self,
        tools: list,
        max_iters: int = 10,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
    ):
        super().__init__()
        # Combine base tools with the generated tool
        self.tools = tools
        self.max_iters = max_iters
        self.agent = dspy.ReAct(
            signature=ToolAssessmentSignature,
            tools=self.tools,
            max_iters=self.max_iters,
        )
        self.log_level = log_level
        self.logger = get_logger(name="ToolAssessor", log_level=self.log_level)

    def forward(
        self,
        function_name: str,
        function_requirements: str,
        path_ifc_model: str,
    ) -> ModuleOutput:
        output = self.agent(
            function_name=function_name,
            function_requirements=function_requirements,
            path_ifc_model=path_ifc_model,
        )

        if output.assessment_status and output.assessment_details:
            self.logger.debug("Tool assessment successfull")
            self.logger.debug(f"Assessment status: \n{output.assessment_status}")
            self.logger.debug(f"Assessment details: \n{output.assessment_details}")
            return ModuleOutput(
                result=Result(
                    assessment_status=output.assessment_status,
                    assessment_details=output.assessment_details,
                ),
                status="success",
            )
        else:
            self.logger.debug("Tool assessment failed")
            return ModuleOutput(status="error", error_msg="Tool assessment failed")


# =============== Define ToolCorrector =============== #
class ToolCorrectionSignature(dspy.Signature):
    f"""
    Update a Python function implementation to incorporate the provided feedback.
    An assessment was conducted on the current implementation and has assessed that it is not working properly. Details regarding what needs to be changed are provided.

    The generated function should:
    - Take at least one argument: path_ifc_file: str, which is a path to the .ifc file the function should interact with.
    - Be well-documented with docstrings and type hints

    IMPORTANT:
    - Do not make assumptions about IFC schema or data structure.
    - Use the provided tools to research proper implementation details through documentation and web search.

    Below is an overview of how the structure of the IfcOpenShell Python library. For details regarding the implementation of each available method, use the `query_ifcopenshell_documentation` tool.

    Overview:
    {IFCOPENSHELL_DOCUMENTATION_OVERVIEW}
    """

    # inputs
    function_description: str = dspy.InputField(
        desc="Detailed description of what the function should do and its requirements."
    )

    function_name: str = dspy.InputField(desc="Name of the function.")

    current_function_implementation: str = dspy.InputField(
        desc="Current implementation of the function that needs to be updated."
    )

    detailed_function_assessment: str = dspy.InputField(
        desc="The detailed assessment of the current implementation of the function."
    )

    # outputs
    new_function_implementation: str = dspy.OutputField(
        desc="The updated implementation of the required function, mitigating the issues identified in the detailed assessment."
    )


class ToolCorrector(dspy.Module):
    """Module to correct an existing Python function."""

    def __init__(
        self,
        tools: list,
        max_iters: int = 10,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
    ):
        super().__init__()
        self.tools = tools
        self.max_iters = max_iters
        self.agent = dspy.ReAct(
            signature=ToolCorrectionSignature, tools=tools, max_iters=self.max_iters
        )
        self.log_level = log_level
        self.logger = get_logger(name="ToolCorrector", log_level=self.log_level)

    def forward(
        self,
        function_description: str,
        function_name: str,
        current_function_implementation: str,
        detailed_function_assessment: str,
    ) -> ModuleOutput:
        result = self.agent(
            function_description=function_description,
            function_name=function_name,
            current_function_implementation=current_function_implementation,
            detailed_function_assessment=detailed_function_assessment,
        )

        if result.new_function_implementation:
            self.logger.info("ToolCorrector updated the implementation successfully")
            self.logger.debug(
                f"New implementation: {result.new_function_implementation}"
            )
            return ModuleOutput(
                result=Result(python_code=result.new_function_implementation),
                status="success",
            )
        else:
            self.logger.info("ToolCorrector failed to update the function.")
            return ModuleOutput(
                status="error", error_msg="ToolCorrector failed to update the function."
            )


def new_tool_pre_check(
    new_tool: Callable, path_ifc_model: str, logger
) -> tuple[bool, str]:
    """
    Check that a newly created tool works properly before submitting it to the ToolAssessor for further investigation.

    Args:
        new_tool: The dynamically created function to test
        path_ifc_model: Path to IFC file for testing
        logger: Logger instance for debug output

    Returns:
        tuple: (test_passed: bool, test_result: str)
    """
    try:
        import inspect

        sig = inspect.signature(new_tool)
        params = list(sig.parameters.keys())

        if len(params) == 1:
            # Single parameter function (like the original)
            test_result = new_tool(path_ifc_model)
            logger.debug(f"Single-parameter function test result: {test_result}")
        else:
            # Multi-parameter function - provide basic test with minimal args
            logger.debug(f"Function has {len(params)} parameters: {params}")
            logger.debug(
                "Multi-parameter function detected. Skipping direct test to avoid parameter mismatch."
            )
            test_result = f"Multi-parameter function with signature: {sig}. Formal assessment required."

    except TypeError as e:
        # If the function requires more parameters, that's okay for now
        test_result = f"Function requires additional parameters: {str(e)}"
        logger.debug(f"TypeError during direct test: {str(e)}")

    logger.debug(f"Direct tool test result: {test_result}")

    # Check if the direct test shows a successful result (for single-parameter functions)
    test_passed = (
        "Error executing" not in str(test_result)
        and str(test_result) not in ["No items found", "None"]
        and "Multi-parameter function" not in str(test_result)
        and "Function requires additional parameters" not in str(test_result)
    )

    if test_passed:
        logger.debug(f"Pre-check of {function_name} passed! Result: {test_result}")
    else:
        logger.debug(
            f"Pre-check of {function_name} did not pass or was inconclusive. Result: {test_result}"
        )

    return test_passed, str(test_result)


def create_new_tool(
    function_requirements: str,
    function_name: str,
    path_ifc_model: str,
    llm_info: LLM = LANGUAGE_MODELS["claude"],
    max_iter: int = 3,
    function_boilerplate: str = FUNCTION_BOILERPLATE,
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
) -> ModuleOutput:
    """
    Create a new tool using a multi-agent system with iterative improvement.

    This function implements a complete pipeline for generating, testing, and refining
    Python functions that work with IFC files. The system uses three specialized agents:

    The workflow:
    1. ToolCreator generates initial function code based on requirements
    2. Function is dynamically wrapped to create a testable tool
    3. ToolAssessor evaluates the function through direct testing and LLM assessment
    4. ToolCorrector improves the function based on assessment feedback
    5. Process repeats until success or max_iter limit is reached

    Args:
        function_requirements: Detailed description of what the function should do
        function_name: Name for the generated function
        path_ifc_model: Path to IFC file used for testing the generated function
        llm_info: Language model configuration to use for all agents
        max_iter: Maximum number of correction iterations (default: 3)
        function_boilerplate: Code template to include in generated functions
        log_level: Logging verbosity level

    Returns:
        ModuleOutput containing:
        - result.python_code: Generated function code (if successful)
        - result.assessment_status: "ok" or "needs_improvement"
        - result.assessment_details: Detailed assessment feedback
        - status: "success" or "error"
        - error_msg: Error description (if status is "error")
    """
    with mlflow.start_span(name="create_new_tool"):
        # --- Step 1: Set up the system --- #
        output = ModuleOutput(status="error")
        python_interpreter = get_python_interpreter(
            authorized_functions={
                "web_search": web_search,
                "query_ifcopenshell_documentation": query_ifcopenshell_documentation,
            }
        )
        special_tools = [
            web_search,
            query_ifcopenshell_documentation,
        ]
        base_tools = special_tools + [python_interpreter]

        lm = dspy.LM(model=llm_info.url, api_key=llm_info.api_key)
        dspy.configure(lm=lm)

        tool_creator = ToolCreator(tools=base_tools)
        tool_corrector = ToolCorrector(tools=base_tools)

        logger = get_logger(name="create_new_tool", log_level=log_level)
        logger.info(f"Starting the creation of the tool: {function_name}")

        # --- Step 2: Create initial function --- #
        with mlflow.start_span(name="initial_function_creation"):
            logger.info("Creating initial function")
            output_tool_creator = tool_creator.forward(
                function_requirements=function_requirements,
                function_name=function_name,
                function_boilerplate=function_boilerplate,
            )

            code: str = output_tool_creator.result.python_code or ""
            if output_tool_creator.status == "error":
                error_msg = (
                    output_tool_creator.error_msg
                    or f"Unknown error occurred  while trying to create the tool: {function_name}."
                )
                logger.error(error_msg)
                output.error_msg = error_msg
            else:
                logger.info("Initial function created successfully.")
                logger.debug(f"Initial function code: \n\n---\n{code}\n\n---")

        current_iteration = 0

        # --- Step 3: Iterative improvement loop --- #
        while current_iteration < max_iter:
            current_iteration += 1
            print(f"\n--- Iteration: {current_iteration} ---")

            with mlflow.start_span(name=f"iteration_{current_iteration}"):
                # Step 3.1: Create enhanced assessor with dynamic tool
                with mlflow.start_span(name="create_assessor"):
                    logger.info("Assessing the generated code.")
                    try:
                        new_tool = _create_function_from_source_code(
                            function_name=function_name, code=code
                        )

                        # Test the tool directly first to ensure it works (only work if it only have ifc_file_path as a required argument)
                        # This does not influence the control flow ; it is here to help debug the program
                        test_passed, test_result = new_tool_pre_check(
                            new_tool, path_ifc_model, logger
                        )

                        # Create new python interpreter with the generated tool included
                        authorized_functions = {
                            "web_search": web_search,
                            "query_ifcopenshell_documentation": query_ifcopenshell_documentation,
                            f"{function_name}": new_tool,
                        }

                        python_interpreter = get_python_interpreter(
                            authorized_functions=authorized_functions
                        )
                        tools = special_tools + [new_tool, python_interpreter]
                        tool_assessor = ToolAssessor(tools=tools)
                        logger.info("✓ ToolAssessor created with new tool to test.")

                    except Exception as e:
                        logger.error(
                            f"✗ Failed to create ToolAssessor. Error: {str(e)}"
                        )
                        logger.error(f"Code that failed: {code}")
                        continue

                # Step 3.2: Assess if the function works properly
                with mlflow.start_span(name="assess_function"):
                    try:
                        logger.info("Starting the tool assessment.")

                        output_tool_assessor = tool_assessor.forward(
                            function_name=function_name,
                            function_requirements=function_requirements,
                            path_ifc_model=path_ifc_model,
                        )
                        logger.debug(
                            f"✓ Assessment completed: {output_tool_assessor.result.assessment_status}"
                        )
                        logger.debug(
                            f"Assessment details: {output_tool_assessor.result.assessment_details}"
                        )
                    except Exception as e:
                        logger.error(f"✗ Assessment failed: {str(e)}")
                        continue

                # Step 3.3: If the assessment is good, update the ouput and exit the loop
                if output_tool_assessor.result.assessment_status == "ok":
                    logger.info(
                        f"🎉 Function passed assessment after {current_iteration} iterations!"
                    )
                    output.result.python_code = code
                    output.status = "success"
                    output.result.assessment_status = (
                        output_tool_assessor.result.assessment_status
                    )
                    output.result.assessment_details = (
                        output_tool_assessor.result.assessment_details
                    )
                    break

                # Step 3.4: If the assessment is not satisfactory, try to correct the function
                elif current_iteration < max_iter:
                    with mlflow.start_span(name="correct_function"):
                        logger.debug(
                            "Code not good enough yet; trying to correct the function."
                        )
                        output_tool_corrector = tool_corrector.forward(
                            function_description=function_requirements,
                            function_name=function_name,
                            current_function_implementation=code,
                            detailed_function_assessment=output_tool_assessor.result.assessment_details
                            or "No assessment available.",
                        )

                        if output_tool_corrector.status == "error":
                            logger.error("✗ Correction failed.")
                            continue
                        else:
                            code = output_tool_corrector.result.python_code or ""
                            logger.info("✓ Function corrected")
                            logger.debug(f"New code:\n{code}")
                else:
                    logger.debug("⚠️  Maximum iterations reached")

        # Return the result (good or bad)
        return output


# %% Example Usage
# =============== Example Usage =============== #


def example_usage(
    function_name: str,
    function_requirements: str,
    path_ifc_model: str = "/Users/sylvainhellin/GitHub/ifcAnswerEngineV3/src/bim_models/duplex/arc.ifc",
    llm_name: str = "claude",
):
    """
    Example demonstrating how to use the multi-agent tool creation system.

    Args:
        function_name: Name for the function to create
        function_requirements: Description of what the function should do
        path_ifc_model: Path to test IFC file
        llm_name: Name of language model to use (from LANGUAGE_MODELS config)
    """
    logger = get_logger(name=function_name)

    logger.info(f"Creating tool with requirements: {function_requirements}")
    logger.info(f"Using test IFC file: {path_ifc_model}")
    logger.info(f"Using LLM: {llm_name}")

    # Create the tool
    result = create_new_tool(
        function_requirements=function_requirements,
        path_ifc_model=path_ifc_model,
        function_name=function_name,
        llm_info=LANGUAGE_MODELS[llm_name],
        max_iter=3,
    )

    # Log results
    logger.info("=== RESULT ===")
    for key, value in result.result.model_dump().items():
        if value is not None:
            if key == "python_code" and len(str(value)) > 200:
                logger.info(f"{key}: {str(value)[:200]}...")
            else:
                logger.info(f"{key}: {value}")

    return result


if __name__ == "__main__":
    import mlflow

    # Example 1: Simple single-parameter function
    function_name = "get_list_ifc_spaces"
    function_requirements = "Return a list of the IfcSpace from an ifc model."

    # Initialize MLFlow
    mlflow.dspy.autolog()  # type: ignore
    mlflow.set_tracking_uri("http://localhost:5000")
    mlflow.set_experiment(function_name)

    with mlflow.start_run():
        result = example_usage(
            function_name=function_name,
            function_requirements=function_requirements,
            llm_name="claude",
        )
        print(f"\nResult status: {result.status}")

    # Example 2: Multi-parameter function (commented out for demo)
    # function_name_2 = "get_spaces_by_min_area"
    # function_requirements_2 = """
    # Create a function that returns IFC spaces with net floor area above a threshold.
    # The function should accept:
    # - ifc_file_path: str (required) - path to the IFC file
    # - min_nfa: float (required) - minimum net floor area in square meters
    # """
    #
    # mlflow.set_experiment(function_name_2)
    # with mlflow.start_run():
    #     result_2 = example_usage(
    #         function_name=function_name_2,
    #         function_requirements=function_requirements_2,
    #         llm_name="claude"
    #     )
