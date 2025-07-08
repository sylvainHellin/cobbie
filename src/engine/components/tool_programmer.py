from typing import Callable, List, Literal

import dspy

from src.config import (
    FUNCTION_BOILERPLATE,
)
from src.engine.schemas import ModuleOutput, Result
from src.engine.util import get_logger
from .code_agent import CodeAgent


class NewToolSignature(dspy.Signature):
    """
    Create a Python function that implements the requirements using the IfcOpenShell Python library.
    Your goal is to be an action-oriented programmer. Write code, test it, and refine it.

    **Programming Strategy:**
    1. Act First: Start by writing a minimal amount of code to tackle a small part of the problem.
    2. Test Incrementally: Use the python_interpreter tool to execute your code snippets and verify your assumptions.
    3. Research as Needed: If your code fails, use query_ifcopenshell_documentation or web_search to find specific answers.
    4. Build the Final Function: Once you have working snippets, assemble them into the final function.

    **CRITICAL JSON FORMATTING RULE FOR TOOL CALLS:**
    When calling python_interpreter, format JSON arguments as single-line strings.
    Do NOT use triple quotes in JSON. Use escaped newlines instead.
    Example: {"python_code": "import ifcopenshell\\nprint('hello')"}

    **CRITICAL REQUIREMENTS - The final function MUST:**
    - Accept path_ifc_model: str as the FIRST and ONLY parameter.
    - Load the IFC file internally: ifc_file = ifcopenshell.open(path_ifc_model)
    - Return data structures (e.g., lists, dicts), not formatted strings.
    - Be well-documented with docstrings and type hints.

    **MANDATORY IMPLEMENTATION PATTERN:**
    def your_function_name(path_ifc_model: str) -> list:
        # Load the IFC file from the provided path
        ifc_file = ifcopenshell.open(path_ifc_model)
        # ... your logic here ...
        return list(results)

    """

    # Below is an overview of the IfcOpenShell library. Use it for a general understanding, but rely on testing code for specifics.

    # Overview:
    # {IFCOPENSHELL_DOCUMENTATION_OVERVIEW}
    # """

    # inputs
    function_requirements: str = dspy.InputField(
        desc="Detailed description of what the function should do and its requirements."
    )
    function_name: str = dspy.InputField()

    function_boilerplate: str = dspy.InputField(
        desc="This boilerplate must be included at the beginning of your code; otherwise, it will not work properly."
    )

    path_ifc_model: str = dspy.InputField(
        desc="Path to an IFC file for testing the function."
    )

    # outputs
    python_code: str = dspy.OutputField(
        desc="Complete code implementation (including imports from the boilerplate, any necessary helper functions, etc.) of your Python function implementation."
    )


class ToolProgrammer(dspy.Module):
    """Module to create a new Python function that meets the requirements."""

    def __init__(
        self,
        tools: List[Callable],
        max_iters: int = 10,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
    ):
        super().__init__()
        self.tools = tools
        self.max_iters = max_iters
        self.agent = CodeAgent(
            signature=NewToolSignature, tools=tools, max_iters=self.max_iters
        )
        self.log_level = log_level
        self.logger = get_logger(name="ToolProgrammer", log_level=self.log_level)

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        path_ifc_model: str,
        function_boilerplate: str = FUNCTION_BOILERPLATE,
    ) -> ModuleOutput:
        result = self.agent(
            function_requirements=function_requirements,
            function_name=function_name,
            path_ifc_model=path_ifc_model,
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


if __name__ == "__main__":
    import json

    import mlflow

    from src.config import LANGUAGE_MODELS, TEST_IFC_PATH
    from src.engine.tools.primordial import (
        query_ifcopenshell_documentation,
        web_search,
    )

    def main(
        function_requirements: str,
        function_name: str,
        lm_name: str = "gemini-flash",
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
    ):
        # configure dspy
        lm_info = LANGUAGE_MODELS[lm_name]
        llm = dspy.LM(
            model=lm_info.url,
            api_key=lm_info.api_key,
            max_tokens=5000,
        )
        dspy.configure(lm=llm)

        # setup mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("ToolProgrammer")

        # setup the primordial tools
        # Note: CodeAgent handles python_interpreter internally, so we only pass external tools
        tools = [web_search, query_ifcopenshell_documentation]

        # setup the tool programmer
        tool_programmer = ToolProgrammer(tools=tools, max_iters=10, log_level=log_level)

        # try to create the tool
        result = tool_programmer.forward(
            function_name=function_name,
            function_requirements=function_requirements,
            path_ifc_model=TEST_IFC_PATH,
        )

        print(f"results: {json.dumps(result.model_dump_json(), indent=2)}")

    ##########################################
    function_requirements = """"To accurately determine the width of the emergency escape routes, we need a function that can identify which doors are designated as emergency exits based on their properties or other criteria. The function should be able to query the IFC model for doors with specific properties or classifications that indicate they are emergency exits. \n\nThe required function signature could be:\n```python\ndef get_emergency_exit_doors(ifc_file_path: str) -> List[IfcDoor]:\n    \"\"\"\n    Retrieves a list of IfcDoor entities that are designated as emergency exits.\n\n    Args:\n    ifc_file_path (str): Path to the IFC file.\n\n    Returns:\n    List[IfcDoor]: A list of IfcDoor entities representing emergency exits.\n    \"\"\"\n```\n\nThis function would allow us to identify the emergency exit doors and then extract their widths."""
    function_name = "get_emergency_exit_doors"
    lm_name = ""
    main(
        function_requirements=function_requirements,
        function_name=function_name,
        log_level="INFO",
        lm_name="gemini-flash",
    )
