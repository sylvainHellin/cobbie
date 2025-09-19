from typing import Callable, Dict, cast, Optional

import dspy

from src.config.agents import AGENT_CONFIGS, ToolDebuggerConfig
from src.engine.components.test_and_improve import TestAndImprove
from src.engine.schemas import ModuleOutput
from src.engine.tools.primordial import (
    query_ifcopenshell_documentation,
    web_search,
)
from src.engine.util import (
    _extract_function_metadata,
    get_logger,
)


class ToolDebugger(dspy.Module):
    def __init__(
        self,
        additional_authorized_functions: Dict[str, Callable] = {
            "web_search": web_search,
            "query_ifcopenshell_documentation": query_ifcopenshell_documentation,
        },
        config: Optional[ToolDebuggerConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.tool_debugger

        # Use provided LLM or get from config
        self.lm = lm or self.config.llm.get_llm()
        self.log_level = self.config.log_level
        self.logger = get_logger(name="ToolDebugger", log_level=self.log_level)
        self.max_iter = self.config.max_iter
        self.add_code_prefix = self.config.add_code_prefix

        # Store authorized functions for use in TestAndImprove
        self.additional_authorized_functions = additional_authorized_functions

        self.logger.debug(
            f"Primordial tools available for ToolDebugger sub-agents: {', '.join([getattr(tool, '__name__', str(tool)) for tool in self.additional_authorized_functions.values()])}"
        )

        # Instantiate the TestAndImprove module
        self.test_and_improve = TestAndImprove(
            additional_authorized_functions=self.additional_authorized_functions,
        )

    def _build_function_requirements(self, metadata) -> str:
        """
        Build function requirements from extracted metadata.

        Args:
            metadata: PythonFunctionMetadata object containing function details

        Returns:
            String describing the function requirements
        """
        requirements = []

        # Add function signature
        args_str = ", ".join([f"{arg}" for arg in metadata.args])
        signature = f"`{metadata.name}({args_str})"
        if metadata.return_type:
            signature += f" -> {metadata.return_type}"
        signature += "`"

        requirements.append(f"Function signature:\n{signature}")

        # Add docstring if available
        if metadata.docstring and metadata.docstring.strip():
            requirements.append(f"\nDescription:\n{metadata.docstring.strip()}")
        else:
            requirements.append(
                f"\nDescription:\nFunction {metadata.name} - requirements should be inferred from the function signature and context."
            )

        # Add argument details if available
        if metadata.args:
            requirements.append("\nArguments:")
            for i, arg in enumerate(metadata.args):
                default_info = ""
                if i >= len(metadata.args) - len(metadata.defaults):
                    default_idx = i - (len(metadata.args) - len(metadata.defaults))
                    default_info = f" (default: {metadata.defaults[default_idx]})"
                requirements.append(f"- {arg}{default_info}")

        # Add return type if available
        if metadata.return_type:
            requirements.append(f"\nReturn type: {metadata.return_type}")

        return "\n".join(requirements)

    def forward(
        self,
        function_name: str,
        faulty_function_implementation: str,
        initial_assessment: str,
        path_ifc_model: str,
    ) -> ModuleOutput:
        """
        Debug and fix a faulty tool using TestAndImprove module.

        This function implements a complete pipeline for debugging, correcting, and testing
        Python functions that work with IFC files using the TestAndImprove module.

        The workflow:
        1. Extract function requirements from the faulty function's signature and docstring
        2. Use TestAndImprove to iteratively correct and assess the function
        3. Return the corrected function or error details

        Args:
            function_name: Name of the function being debugged
            faulty_function_implementation: Current faulty function code (should include signature and docstring)
            initial_assessment: Initial assessment describing what's wrong with the function
            path_ifc_model: Path to IFC file used for testing the corrected function

        Returns:
            ModuleOutput containing:
            - result.function_implementation: Corrected function code (if successful)
            - result.assessment_status: "ok" or "needs_improvement"
            - result.assessment_details: Detailed assessment feedback
            - status: "success" or "error"
            - error_msg: Error description (if status is "error")
        """
        # Init the output
        self.output = ModuleOutput()

        self.logger.info(f"Starting debugging the tool: {function_name}")

        try:
            # Extract function requirements from signature and docstring
            function_metadata = _extract_function_metadata(
                faulty_function_implementation, function_name
            )

            # Build function requirements from metadata
            function_requirements = self._build_function_requirements(function_metadata)

            self.logger.info("The function requirements were successfully extracted.")
            self.logger.debug(
                f"Extracted function requirements: {function_requirements}"
            )

            # Use TestAndImprove to debug and fix the function
            self.logger.info(
                "Starting TestAndImprove for function debugging, starting with the initial assessment."
            )
            self.output = cast(
                ModuleOutput,
                self.test_and_improve(
                    function_requirements=function_requirements,
                    function_name=function_name,
                    path_ifc_model=path_ifc_model,
                    function_implementation=faulty_function_implementation,
                    initial_assessment=initial_assessment,
                ),
            )

        except Exception as e:
            self.output.error_msg = (
                f"An Exception occurred during the debugging process:\nError:\n{e}"
            )
            self.logger.error(self.output.error_msg)

        return self.output


if __name__ == "__main__":
    import mlflow
    from src.config import TEST_IFC_PATH

    def main(
        function_name: str,
        faulty_function_implementation: str,
        initial_assessment: str,
    ):
        # setup mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("ToolDebugger")

        dspy.configure_cache(enable_disk_cache=False)
        # setup the tool debugger
        tool_debugger = ToolDebugger()

        # debug the tool
        output = cast(
            ModuleOutput,
            tool_debugger(
                function_name=function_name,
                faulty_function_implementation=faulty_function_implementation,
                initial_assessment=initial_assessment,
                path_ifc_model=TEST_IFC_PATH,
            ),
        )

        print(f"Tool debugging result: {output.model_dump_json(indent=2)}")

        ##########################################

    # Test data - debugging a faulty IFC analysis function
    function_name = "get_room_count"

    faulty_function_implementation = '''def get_room_count(ifc_file_path: str) -> int:
    """
    Count the total number of IfcSpace entities in an IFC model that represent rooms.

    Args:
        ifc_file_path: Path to the IFC file

    Returns:
        Number of spaces/rooms found in the model
    """
    import ifcopenshell

    model = ifcopenshell.open(ifc_file_path)
    # Bug: using wrong entity type - should be IfcSpace, not IfcRoom
    rooms = model.by_type("IfcRoom")
    return len(rooms)
'''

    initial_assessment = """
The function has a critical bug: it's looking for 'IfcRoom' entities instead of 'IfcSpace' entities.
In IFC schema, rooms are typically represented as IfcSpace entities, not IfcRoom entities.
This will likely return 0 for most IFC files even when they contain spaces/rooms.
The function should use model.by_type("IfcSpace") instead of model.by_type("IfcRoom").
"""

    main(
        function_name=function_name,
        faulty_function_implementation=faulty_function_implementation,
        initial_assessment=initial_assessment,
    )
