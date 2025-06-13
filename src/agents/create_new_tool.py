"""
Next step:
    - Update the implementation of the PythonInterpreter: currently, it does not allow the ToolAssessor to use the newly created tool.
    OR
    I might be worth considering replacing this agent by a CodeAgent from smolagent with structured output, and only take the output of this agent to feed it to the next one. Maybe with an intermediate that could process the answer of the CodeAgent into a structured output.
    OR
    Alternatively: look at the python interpreter from dspy (might need installing deno): dspy/primitives/python_interpreter.py (https://www.perplexity.ai/search/does-dspy-have-a-pythoninterpr-TmupTM3BQaKhqJyvFqyKzg#0)
    OR
    consider getting rid of the python_interpreter all together. Maybe it is enough for the ToolAssessor to use the new tool as 'a tool' using the classic ReAct pattern ; without having to write python code. This might be limiting when the
    - Test this coumpound system for creating a couple of tools
    - Decide on a tracing system (MLFlow, sqlite) and implement it to better follow the interaction of the system
    - Test how well the main CodeAgent can use this tool.

"""

# %% Imports
# =============== Imports and config =============== #
import os
import sys
from typing import Literal, Optional

import dspy
from pydantic import BaseModel

from src import FUNCTION_BOILERPLATE, LANGUAGE_MODELS, LLM, ROOT_PATH
from src.special_tools import (
    query_ifcopenshell_documentation,
    web_search,
    python_interpreter,
)
from src.agents import (
    _create_function_from_source_code,
    get_logger,
)

# Set up the path
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)

# Set up the LLM for dspy
llm_info = LANGUAGE_MODELS["claude"]
lm = dspy.LM(model=llm_info.url, api_key=llm_info.api_key)
dspy.configure(lm=lm)

# Define the tools
TOOLS = [web_search, query_ifcopenshell_documentation]

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
    {IFCOPENSHELL_DOCUMENTATION_OVERVIEW}k
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
    Create a new tool using a multi-agent system with unbiased testing.

    The workflow:
    1. ToolCreator generates the function code
    2. A new function with the source code is created in this thread
    3. ToolAssessor tests it as a tool without seeing the code
    4. ToolCorrector fixes issues if needed
    5. Repeat until satisfactory or max iterations reached
    """
    # --- Step 1: Set up the system --- #
    output = ModuleOutput(status="error")
    base_tools = [web_search, query_ifcopenshell_documentation, python_interpreter]

    lm = dspy.LM(model=llm_info.url, api_key=llm_info.api_key)
    dspy.configure(lm=lm)

    tool_creator = ToolCreator(tools=base_tools)
    tool_corrector = ToolCorrector(tools=base_tools)

    logger = get_logger(name="create_new_tool", log_level=log_level)
    logger.info(f"Starting the creation of the tool: {function_name}")

    # --- Step 2: Create initial function --- #
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

        # Step 3.1: Create enhanced assessor with dynamic tool
        logger.info("Assessing the generated code.")
        try:
            new_tool = _create_function_from_source_code(
                function_name=function_name, code=code
            )
            tools = base_tools + [new_tool]
            tool_assessor = ToolAssessor(tools=tools)
            logger.info("✓ ToolAssessor created with new tool to test.")
        except Exception as e:
            logger.error(f"✗ Failed to create ToolAssessor. Error: {str(e)}")
            continue

        # Step 3.2: Assess if the function works properly
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
            logger.debug("Code not good enough yet; trying to correct the function.")
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


def example_usage():
    """
    Example demonstrating how to use the multi-agent tool creation system.
    """
    # Define requirements for a new tool
    function_requirements = """
    Create a function that extracts all wall elements from an IFC file and returns
    their basic properties including name, type, height, and thickness."""
    function_name = "get_wall_elements_properties"
    # Path to an IFC file for testing
    path_ifc_model = (
        "/Users/sylvainhellin/GitHub/ifcAnswerEngineV3/src/bim_models/duplex/arc.ifc"
    )
    logger = get_logger(name="test")

    logger.info(f"Creating tool with requirements: {function_requirements}")
    logger.info(f"Using test IFC file: {path_ifc_model}")

    # Create the tool
    result = create_new_tool(
        function_requirements=function_requirements,
        path_ifc_model=path_ifc_model,
        function_name=function_name,
        llm_info=LANGUAGE_MODELS["llama4-maverick-groq"],
        max_iter=2,
    )
    for key, value in result.result.model_dump().items():
        logger.info(f"{key} : {value}")


if __name__ == "__main__":
    example_usage()
