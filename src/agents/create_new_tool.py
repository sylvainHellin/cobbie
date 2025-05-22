# %% Imports
# =============== Imports and config =============== #
import os
import sys
from typing import Literal
from smolagents.local_python_executor import LocalPythonExecutor

import dspy

from config import LANGUAGE_MODELS, ROOT_PATH, LLM
from special_tools import query_ifcopenshell_documentation, web_search

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
    ifcopenshell_documentation_overview = file.read()
del doc_path


# %% DSPy
# =============== Define ToolMaker =============== #
class NewToolSignature(dspy.Signature):
    f"""
    Create a Python function that implements the requirements using the IfcOpenShell Python library.
    This function will be used as a "tool" by an LLM-based ReAct agent to answer some user's query related to a BIM model.

    The generated function should:
    - Take at least one argument: path_ifc_file: str, which is a path to the .ifc file the function should interact with.
    - Handle input validation
    - Include proper error handling
    - Be well-documented with docstrings
    - Return a serialized output
    - Ensure that the output is not too long (so as not to exceed the context window of the ReAct agent)

    Below is an overview of how the structure of the IfcOpenShell Python library. for details regarding the implementation of each available method, use the `query_ifcopenshell_documentation` tool.

    Overview:
    {ifcopenshell_documentation_overview}
    """

    # inputs
    function_description: str = dspy.InputField(
        desc="Detailed description of what the function should do and its requirements."
    )
    function_name: str = dspy.InputField(
        desc="Name of the function following Python naming conventions."
    )
    function_boilerplate: str = dspy.InputField(
        desc="Boilerplate to include at the beginning of your code."
    )

    # outputs
    python_code: str = dspy.OutputField(
        desc="Complete code implementation (including imports etc. from the boilerplate) of your Python function implementation including docstrings, type hints, and error handling."
    )
    implementation_status: Literal["success", "error"] = dspy.OutputField(
        desc="'success' if function implemented correctly, 'error' if implementation failed."
    )
    error_message: str = dspy.OutputField(
        desc="Detailed error message if implementation_status is 'error', empty string otherwise."
    )


class ToolCreator(dspy.Module):
    """Module to create a new Python function that meets the requirements."""

    def __init__(self, tools: list):
        super().__init__()
        self.tools = tools
        self.agent = dspy.ReAct(signature=NewToolSignature, tools=tools, max_iters=5)

    def forward(
        self,
        function_description: str,
        function_name: str,
        function_boilerplate: str,
    ):
        try:
            return self.agent(
                function_description=function_description,
                function_name=function_name,
                function_boilerplate=function_boilerplate,
            )
        except Exception as e:
            return dspy.Prediction(
                function_implementation=f"An error occurred during execution: {str(e)}",
                implementation_status="error",
            )


# =============== Define ToolAssessor =============== #
class ToolAssessmentSignature(dspy.Signature):
    """
    Assess whether a generated function meets requirements and works correctly.
    Tests the function with real IFC files and evaluates code quality and functionality.
    """

    # inputs
    function_name: str = dspy.InputField(desc="Name of the function to assess")
    function_code: str = dspy.InputField(
        desc="Source code of the function implementation"
    )
    function_requirements: str = dspy.InputField(
        desc="Original requirements and description of what the function should do"
    )
    path_ifc_model: str = dspy.InputField(
        desc="Path to an IFC file for testing the function"
    )

    # outputs
    assessment_status: Literal["ok", "needs_improvement"] = dspy.OutputField(
        desc="'ok' if the tool works as expected, 'needs_improvement' if issues were found"
    )
    assessment_details: str = dspy.OutputField(
        desc="Detailed explanation of the assessment, including any issues found and improvement suggestions"
    )


class ToolAssessor(dspy.Module):
    """Module to assess the quality and functionality of generated tools."""

    def __init__(self, tools: list):
        super().__init__()
        # Combine base tools with the generated tool
        self.tools = tools
        self.agent = dspy.ReAct(
            signature=ToolAssessmentSignature, tools=self.tools, max_iters=5
        )

    def forward(
        self,
        function_name: str,
        function_code: str,
        original_requirements: str,
        path_ifc_model: str,
    ):
        try:
            return self.agent(
                function_name=function_name,
                function_code=function_code,
                original_requirements=original_requirements,
                test_file_path=path_ifc_model,
            )
        except Exception as e:
            return dspy.Prediction(
                assessment_status="needs_improvement",
                assessment_details=f"Assessment failed due to error: {str(e)}",
            )


# =============== Define ToolCorrector =============== #
class ToolCorrectionSignature(dspy.Signature):
    """
    Update a Python function implementation to incorporate the provided feedback.
    An assessment was conducted on the current implementation and has assessed that it is not working properly. Details regarding what needs to be changed are provided.

    The generated function should:
    - Take at least one argument: path_ifc_file: str, which is a path to the .ifc file the function should interact with.
    - Handle input validation
    - Include proper error handling
    - Be well-documented with docstrings
    - Return a serialized output
    - Ensure that the output is not too long (so as not to exceed the context window of the ReAct agent)

    IMPORTANT:
    - Do not make assumptions about IFC schema or data structure.
    - Use the provided tools to research proper implementation details through documentation and web search.
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

    implementation_status: Literal["success", "error"] = dspy.OutputField(
        desc="'success' if function implemented correctly, 'error' if implementation failed."
    )


class ToolCorrector(dspy.Module):
    """Module to correct an existing Python function."""

    def __init__(self, tools):
        super().__init__()
        self.tools = tools
        self.agent = dspy.ReAct(
            signature=ToolCorrectionSignature, tools=tools, max_iters=5
        )

    # def forward(self, function_description, function_name, function_boilerplate, context):
    def forward(
        self,
        function_description: str,
        function_name: str,
        current_function_implementation: str,
        detailed_function_assessment: str,
    ):
        try:
            return self.agent(
                function_description=function_description,
                function_name=function_name,
                current_function_implementation=current_function_implementation,
                detailed_function_assessment=detailed_function_assessment,
            )
        except Exception as e:
            return dspy.Prediction(
                new_function_implementation=f"An error occurred during execution: {str(e)}",
                implementation_status="error",
            )


# =============== Define ToolMaker =============== #
idea_prompt_tool_creator = """
    You are an expect Python programmer and specialist of the Industry Foundation Class (IFC) format whose goal is to help people implement new Python functions using the IfcOpenShell Library.
    Given a list of
    """

# =============== Additional Python Executor tool =============== #


# TODO consider moving this to special tools
def python_interpreter(python_code: str) -> str:
    """
    Execute Python code and return both the result and any printed output.

    Args:
        code: The Python code to execute as a string

    Returns:
        A formatted string containing both the print outputs and return value
    """

    additional_authorized_imports = [
        "ifcopenshell",
        "ifcopenshell.util.element",
        "ifcopenshell.util.shape",
        "ifcopenshell.util.placement",
        "ifcopenshell.util.geolocation",
        "ifcopenshell.util.system",
        "ifcopenshell.geom",
        "ifcopenshell.file",
        "ifcopenshell.entity_instance",
        "math",
        "numpy",
        "pandas",
    ]
    interpreter = LocalPythonExecutor(
        additional_authorized_imports=additional_authorized_imports
    )
    returned_value, logs, is_final = interpreter(code_action=python_code)

    # format the response to include both printed output and the return value
    result = ""
    if logs:
        result += f"## Print output:\n{logs}\n\n"

    result += f"## Return value:\n{returned_value}"

    return result


def create_new_tool(
    requirements: str, path_ifc_model: str, llm_info: LLM = LANGUAGE_MODELS["claude"]
):
    lm = dspy.LM(model=llm_info.url, api_key=llm_info.api_key)
    dspy.configure(lm=lm)
    tools = [web_search, query_ifcopenshell_documentation]
    tool_creator = ToolCreator(tools=tools)
    tool_assessor = ToolAssessor(tools=tools)
    tool_corrector = ToolCorrector(tools=tools)
