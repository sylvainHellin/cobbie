"""
Multi-agent tool creation system for generating and validating IFC-related functions.

This module provides a complete pipeline for creating, testing, and correcting Python functions
that work with IFC (Industry Foundation Classes) files using the IfcOpenShell library.

The system uses three main agents:
- ToolProgrammer: Generates initial function implementations based on requirements
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
import sys
from typing import Callable, Dict, Literal

import dspy
import mlflow

from src.config import (
    FUNCTION_BOILERPLATE,
    IFCOPENSHELL_DOCUMENTATION_OVERVIEW,
    ROOT_PATH,
)
from src.engine.schemas.module_output import ModuleOutput
from src.engine.schemas.result import Result
from src.engine.tools.primordial import (
    format_restrictions_info,
    get_python_interpreter,
    query_ifcopenshell_documentation,
    web_search,
)
from src.engine.util import _create_function_from_source_code, get_logger

# Set up the path
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)


# %% DSPy
# =============== Define ToolMaker =============== #
class NewToolSignature(dspy.Signature):
    f"""
    Create a Python function that implements the requirements using the IfcOpenShell Python library.
    Your goal is to be an action-oriented programmer. Write code, test it, and refine it.

    **Programming Strategy:**
    1.  **Act First:** Start by writing a minimal amount of code to tackle a small part of the problem.
    2.  **Test Incrementally:** Use the `python_interpreter` tool to execute your code snippets and verify your assumptions. This is your primary way of learning how to solve the problem.
    3.  **Research as Needed:** If your code fails, use `query_ifcopenshell_documentation` or `web_search` to find specific answers, then go back to writing and testing code. Do not spend too much time researching upfront.
    4.  **Build the Final Function:** Once you have working snippets, assemble them into the final function.

    ⚠️  CRITICAL REQUIREMENTS - The final function MUST:
    - Accept path_ifc_file: str as the FIRST and ONLY parameter.
    - Load the IFC file internally: `ifc_file = ifcopenshell.open(path_ifc_file)`
    - Return data structures (e.g., lists, dicts), not formatted strings.
    - Be well-documented with docstrings and type hints.

    🔥 MANDATORY IMPLEMENTATION PATTERN (DO NOT DEVIATE):
    ```python
    def your_function_name(path_ifc_file: str) -> list[any]:
        '''Your docstring here'''
        # Load the IFC file from the provided path
        ifc_file = ifcopenshell.open(path_ifc_file)

        # ... your logic here ...
        results = ifc_file.by_type("IfcSpace")  # Example

        # Return actual data, not strings
        return list(results)
    ```

    {format_restrictions_info()}

    Below is an overview of the IfcOpenShell library. Use it for a general understanding, but rely on testing code for specifics.

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


class ToolProgrammer(dspy.Module):
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
        self.logger = get_logger(name="ToolProgrammer", log_level=self.log_level)

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

    CRITICAL: The function being tested MUST accept path_ifc_file: str as its first parameter.

    To perform the assessment, you MUST:
    1. Call the function DIRECTLY with the provided IFC file path (do NOT load the model first)
    2. The function should handle loading the IFC file internally
    3. Examine the return value or any errors
    4. Compare the result with the original 'function_requirements'
    5. Verify the function signature matches: function_name(path_ifc_file: str) -> ReturnType

    ASSESSMENT CRITERIA:
    - Function must accept a string file path as first parameter
    - Function must load IFC file internally using ifcopenshell.open()
    - Function must return appropriate data structures (not strings)
    - Function must work without errors on the test file
    - Function must meet the original requirements

    If the function doesn't accept a file path as first parameter, mark as 'needs_improvement'.
    """

    # inputs
    function_name: str = dspy.InputField(
        desc="Name of the function to assess. This function is available as a tool."
    )
    function_requirements: str = dspy.InputField(
        desc="Original requirements and description of what the function should do"
    )
    path_ifc_model: str = dspy.InputField(
        desc="Path to an IFC file for testing the function. Pass this DIRECTLY to the function as the first argument."
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
    """
    Correct a Python function based on assessment feedback.

    Your primary goal is to fix the provided code, not to rewrite it from scratch.
    Analyze the 'current_function_implementation' and 'detailed_function_assessment' to understand the error.
    Then, produce a 'new_function_implementation' with the necessary corrections.

    ⚠️ KEY CORRECTION GUIDELINES:
    - **Focus on the fix:** Directly address the issues described in the assessment.
    - **Minimize changes:** Only alter the parts of the code that are broken.
    - **Do not research:** Avoid using tools like 'web_search' or 'query_ifcopenshell_documentation'. The goal is to fix the existing code with the information at hand.
    - **Handle syntax errors first:** If the assessment mentions a syntax error, fix that first. This is often a simple typo or mistake.
    - **Maintain signature:** Ensure the corrected function still adheres to the required signature: `def function_name(path_ifc_file: str) -> ...:`

    An assessment was conducted on the current implementation and has assessed that it is not working properly. Details regarding what needs to be changed are provided.

    Here is the implementation pattern to follow:

    🔥 MANDATORY IMPLEMENTATION PATTERN (DO NOT DEVIATE):
    ```python
    def your_function_name(path_ifc_file: str) -> list[any]:
        '''Your docstring here'''
        # Load the IFC file from the provided path
        ifc_file = ifcopenshell.open(path_ifc_file)

        # Work with the loaded ifc_file object
        results = ifc_file.by_type("YourEntityType")

        # Return actual data, not strings
        return list(results)
    ```

    Now, fix the provided function.
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


class ToolCreator(dspy.Module):
    def __init__(
        self,
        llm: dspy.LM,
        max_iter: int = 3,
        max_iter_sub_agents: int = 10,
        function_boilerplate=FUNCTION_BOILERPLATE,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
        additional_authorized_functions: Dict[str, Callable] = {
            "web_search": web_search,
            "query_ifcopenshell_documentation": query_ifcopenshell_documentation,
        },
        callbacks=None,
    ):
        super().__init__(callbacks)
        self.lm = llm
        dspy.configure(lm=self.lm)
        self.log_level = log_level
        self.logger = get_logger(name="ToolCreator", log_level=log_level)
        self.max_iter = max_iter
        self.max_iter_sub_agents = max_iter_sub_agents
        self.function_boilerplate = function_boilerplate

        # Handle the special tools and the python interpreter
        self.additional_authorized_functions = additional_authorized_functions
        self.primordial_tools = [
            tool for name, tool in self.additional_authorized_functions.items()
        ]
        self.python_interpreter = get_python_interpreter(
            additional_authorized_functions=self.additional_authorized_functions
        )
        self.base_tools = self.primordial_tools + [self.python_interpreter]

        self.logger.debug(
            f"Tools allowed for the ToolCreator: {'\n    -'.join([getattr(tool, '__name__', str(tool)) for tool in self.base_tools])}"
        )

        # Instantiate the static sub agents
        self.tool_programmer = ToolProgrammer(
            tools=self.base_tools,
            max_iters=self.max_iter_sub_agents,
            log_level=self.log_level,
        )
        self.tool_corrector = ToolCorrector(
            tools=self.base_tools,
            max_iters=self.max_iter_sub_agents,
            log_level=self.log_level,
        )

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        path_ifc_model: str,
    ) -> ModuleOutput:
        """
        Create a new tool using a multi-agent system with iterative improvement.

        This function implements a complete pipeline for generating, testing, and refining
        Python functions that work with IFC files. The system uses three specialized agents:

        The workflow:
        1. ToolProgrammer generates initial function code based on requirements
        2. Function is dynamically wrapped to create a testable tool
        3. ToolAssessor evaluates the function through direct testing and LLM assessment
        4. ToolCorrector improves the function based on assessment feedback
        5. Process repeats until success or max_iter limit is reached

        Args:
            function_requirements: Detailed description of what the function should do
            function_name: Name for the generated function
            path_ifc_model: Path to IFC file used for testing the generated function

        Returns:
            ModuleOutput containing:
            - result.python_code: Generated function code (if successful)
            - result.assessment_status: "ok" or "needs_improvement"
            - result.assessment_details: Detailed assessment feedback
            - status: "success" or "error"
            - error_msg: Error description (if status is "error")
        """

        with mlflow.start_span(name="ToolCreator"):
            # --- Step 1: Set up the system --- #
            output = ModuleOutput(status="error")

            self.logger.info(f"Starting the creation of the tool: {function_name}")

            # --- Step 2: Create initial function --- #
            with mlflow.start_span(name="ToolProgrammer"):
                self.logger.info("Creating initial function")
                output_tool_programmer = self.tool_programmer.forward(
                    function_requirements=function_requirements,
                    function_name=function_name,
                    function_boilerplate=self.function_boilerplate,
                )

                code: str = output_tool_programmer.result.python_code or ""
                if output_tool_programmer.status == "error":
                    error_msg = (
                        output_tool_programmer.error_msg
                        or f"Unknown error occurred  while trying to create the tool: {function_name}."
                    )
                    self.logger.error(error_msg)
                    output.error_msg = error_msg
                else:
                    self.logger.info("Initial function created successfully.")
                    self.logger.debug(f"Initial function code: \n\n---\n{code}\n\n---")

            # Reset iteration counter before starting the new assess/correct loop
            self.iter = 0

            # --- Step 3: Iterative improvement loop --- #
            while self.iter < self.max_iter:
                self.iter += 1
                print(f"\n--- Iteration: {self.iter} ---")

                with mlflow.start_span(name=f"iteration_{self.iter}"):
                    # Step 3.1: Create enhanced assessor with dynamic tool
                    with mlflow.start_span(name="create_assessor"):
                        self.logger.info("Assessing the generated code.")
                        try:
                            new_tool = _create_function_from_source_code(
                                function_name=function_name, code=code
                            )

                            # Create new python interpreter with the generated tool included
                            authorized_functions = (
                                self.additional_authorized_functions.copy()
                            )
                            authorized_functions[function_name] = new_tool
                            python_interpreter = get_python_interpreter(
                                additional_authorized_functions=authorized_functions
                            )
                            tools = self.primordial_tools + [
                                new_tool,
                                python_interpreter,
                            ]
                            tool_assessor = ToolAssessor(tools=tools)
                            self.logger.info(
                                "✓ ToolAssessor created with new tool to test."
                            )

                        except Exception as e:
                            self.logger.error(
                                f"✗ Failed to create ToolAssessor. Error: {str(e)}"
                            )
                            self.logger.error(f"Code that failed: {code}")
                            continue

                    # Step 3.2: Assess if the function works properly
                    with mlflow.start_span(name="ToolAssessor"):
                        try:
                            self.logger.info("Starting the tool assessment.")

                            output_tool_assessor = tool_assessor.forward(
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

                    # Step 3.3: If the assessment is good, update the ouput and exit the loop
                    if output_tool_assessor.result.assessment_status == "ok":
                        self.logger.info(
                            f"🎉 Function passed assessment after {self.iter} iterations!"
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

                    # Step 3.4: If the assessment is not satisfactory, call the ToolCorrector
                    elif self.iter < self.max_iter:
                        with mlflow.start_span(name="ToolCorrector"):
                            self.logger.debug(
                                "Code not good enough yet; trying to correct the function."
                            )

                            output_tool_corrector = self.tool_corrector.forward(
                                function_description=function_requirements,
                                function_name=function_name,
                                current_function_implementation=code,
                                detailed_function_assessment=output_tool_assessor.result.assessment_details
                                or "No assessment available.",
                            )

                            if output_tool_corrector.status == "error":
                                self.logger.error("✗ Correction failed.")
                                continue
                            else:
                                code = output_tool_corrector.result.python_code or ""
                                self.logger.info("✓ Function corrected")
                                self.logger.debug(f"New code:\n{code}")
                    else:
                        self.logger.debug("⚠️  Maximum iterations reached")

            # Return the result (good or bad)
            return output
