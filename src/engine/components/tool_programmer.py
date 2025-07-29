from typing import Callable, List, Literal

import dspy

from src.config import AGENT_CONFIGS, FUNCTION_BOILERPLATE
from src.engine.schemas import ModuleOutput, Result
from src.engine.util import get_logger, create_code_prefix
from .code_act import CodeAct


class NewToolSignature(dspy.Signature):
    """
    As an expert Python programmer, you have been tasked with creating a new Python function using the IfcOpenShell library.
    You are an action-oriented programmer. You write code, test it, and refine it. You have access to a Python interpreter and tools to query information from the Internet or the IfcOpenShell documentation.

    Programming Strategy:
        1. Act first. Start by writing a minimal amount of code to solve a small part of the problem.
        2. Test incrementally. Use the Python interpreter tool to execute your code snippets and verify your assumptions.
        3. Research as needed. If your code fails, use Query IFCOPSHELL Documentation or Web Search to find specific answers.
        4. Build the final function. Once you have working snippets, assemble them into the final function.

    Your function implementation must:
        - Return proper data structures (e.g., lists and dictionaries), not formatted strings.
        - Be well-documented with docstrings and type hints.
        - Be explicit regarding assumptions. For example, if your function involves using properties related to specific BIM authoring software, such as PSet_Revit_Dimensions for an IFC model exported from Revit, mention this in the docstring.

    Final recommendations:
        - The provided Python interpreter does not have a state, so you need to declare all the variables you need.
        - When calling python_interpreter, format JSON arguments as single-line strings. Do NOT use triple quotes in JSON. Use escaped newlines instead.
        Example: {"python_code": "import ifcopenshell\\nprint('hello')"}
    """

    # **MANDATORY IMPLEMENTATION PATTERN:**
    # def your_function_name(path_ifc_model: str) -> list:
    #     # Load the IFC file from the provided path
    #     ifc_file = ifcopenshell.open(path_ifc_model)
    #     # ... your logic here ...
    #     return list(results)

    # """

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
        desc="This boilerplate must be included at the beginning of your code. Otherwise, it will not work properly."
    )

    path_ifc_model: str = dspy.InputField(
        desc="Path to an IFC file for testing the function."
    )

    # outputs
    function_implementation: str = dspy.OutputField(
        desc="Python code (including imports from the boilerplate, any necessary helper functions, etc.) of your Python function implementation."
    )


class ToolProgrammer(dspy.Module):
    """Module to create a new Python function that meets the requirements."""

    def __init__(
        self,
        tools: List[Callable],
        config=None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.tool_programmer

        self.tools = tools
        self.max_iters = self.config.max_iters
        self.agent = CodeAct(
            signature=NewToolSignature, tools=tools, max_iters=self.max_iters
        )
        self.log_level = self.config.log_level
        self.logger = get_logger(name="ToolProgrammer", log_level=self.log_level)
        self.add_code_prefix = self.config.add_code_prefix

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        path_ifc_model: str,
        function_boilerplate: str = FUNCTION_BOILERPLATE,
    ) -> ModuleOutput:
        self.logger.info(f"Starting ToolProgrammer for function: {function_name}")

        if self.add_code_prefix:
            code_prefix = create_code_prefix(
                path_ifc_model=path_ifc_model, imports_boilerplate=FUNCTION_BOILERPLATE
            )
        else:
            code_prefix = None

        self.agent._update_code_prefix(code_prefix=code_prefix)

        prediction = self.agent(
            function_requirements=function_requirements,
            function_name=function_name,
            path_ifc_model=path_ifc_model,
            function_boilerplate=function_boilerplate,
        )

        # Check if we got valid python code
        if (
            hasattr(prediction, "function_implementation")
            and prediction.function_implementation
        ):
            self.logger.info(
                f"ToolProgrammer result: success - function '{function_name}' created successfully"
            )
            self.logger.debug(f"function code:\n{prediction.function_implementation}\n")
            return ModuleOutput(
                result=Result(
                    function_implementation=prediction.function_implementation
                ),
                status="success",
            )
        else:
            self.logger.info(
                f"ToolProgrammer result: error - failed to generate code for function '{function_name}'"
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
        lm_name: str = "kimi-k2",
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
    function_requirements = """To accurately determine the width of the emergency escape routes, we need a function that can identify which doors are designated as emergency exits based on their properties or other criteria. The function should be able to query the IFC model for doors with specific properties or classifications that indicate they are emergency exits. \n\nThe required function signature could be:\n```python\ndef get_emergency_exit_doors(ifc_file_path: str) -> List[IfcDoor]:\n    \"\"\"\n    Retrieves a list of IfcDoor entities that are designated as emergency exits.\n\n    Args:\n    ifc_file_path (str): Path to the IFC file.\n\n    Returns:\n    List[IfcDoor]: A list of IfcDoor entities representing emergency exits.\n    \"\"\"\n```\n\nThis function would allow us to identify the emergency exit doors and then extract their widths."""
    function_name = "get_emergency_exit_doors"
    lm_name = ""
    main(
        function_requirements=function_requirements,
        function_name=function_name,
        log_level="INFO",
        lm_name="kimi-k2",
    )
