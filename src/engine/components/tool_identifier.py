import dspy
from typing import Optional

from src.config.agents import AGENT_CONFIGS, ToolIdentifierConfig
from src.engine.schemas import ModuleOutput, AgentOutput
from src.engine.util import get_logger, get_tools_description


class ToolIdentifierSignature(dspy.Signature):
    """
    Analyze a chat history between a user and a helpful AI assistant specialized in BIM/IFC models to identify if a new Python function could be created to answer similar questions in the future.

    A useful function should be:
        - Generic enough for different questions (no model-specific assumptions or hard-coded values)
        - Flexible by accepting appropriate parameters
        - Simple to use by the AI assistant in future interactions
        - Be distinct from already available functions

    Function requirements should include:
        - Function signature with type hints
        - Clear expected behavior description
        - Implementation feasibility with Python and IfcOpenShell library

    IMPORTANT: When providing function_requirements, give the complete detailed specification as plain text, not JSON schema or type annotations. Provide the actual requirements content, not metadata about the field type.
    """

    # Input fields
    chat_history: str = dspy.InputField(
        desc="Chat history between user and AI assistant about BIM/IFC model queries"
    )
    available_functions: str = dspy.InputField(
        desc="The list of function already available."
    )

    # Output fields
    reasoning: str = dspy.OutputField(
        desc="Step-by-step analysis of whether a new function could be useful"
    )
    new_function_identified: bool = dspy.OutputField(
        desc="Whether a potentially useful new function was identified"
    )
    function_name: str = dspy.OutputField(
        desc="Suggested name for the new function, if identified. Else, just enter ''."
    )
    function_requirements: str = dspy.OutputField(
        desc="Detailed requirements and specifications for the new function, if identified. Provide the complete function specification including signature, behavior description, and implementation details. Else, just enter ''."
    )


class ToolIdentifier(dspy.Module):
    """
    A DSPy module that identifies potentially useful new Python functions from chat history.
    """

    def __init__(
        self,
        config: Optional[ToolIdentifierConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.function_identifier
        self.lm = lm or self.config.llm.get_llm()

        self.tool_identifier = dspy.ChainOfThought(ToolIdentifierSignature)
        self.log_level = self.config.log_level
        self.logger = get_logger(name="FunctionIdentifier", log_level=self.log_level)

    def forward(
        self,
        chat_history: str,
        available_functions: Optional[str] = None,
    ) -> ModuleOutput:
        """
        Analyze a chat history to identify potentially useful new Python functions.

        Args:
            chat_history: A string containing the conversation between the user and the AI assistant.
            available_functions (Optional): A serialised list of existing tools and their descriptions. If this is set to None, a description will be created for all existing tools.

        Returns:
            ModuleOutput containing:
            - result.reasoning: Step-by-step analysis
            - result.new_function_identified: Boolean indicating if a function was identified
            - result.function_name: Suggested function name (if identified)
            - result.function_requirements: Detailed requirements (if identified)
            - status: "success" or "error"
            - error_msg: Error description (if status is "error")
        """

        self.lm = self.config.llm.get_llm()
        with dspy.context(lm=self.lm, adapter=self.config.llm.adapter):
            self.logger.info("Starting function identification analysis")
            self.output = ModuleOutput()

            try:
                self.logger.debug(
                    f"Analyzing chat history of length: {len(chat_history)}"
                )
                available_functions = (
                    available_functions
                    if available_functions
                    else get_tools_description()
                )

                prediction = self.tool_identifier(
                    chat_history=chat_history,
                    available_functions=available_functions,
                )

                # Extract fields from the prediction if available
                new_function_identified = getattr(
                    prediction, "new_function_identified", False
                )
                function_name = getattr(prediction, "function_name", None)
                function_requirements = getattr(
                    prediction, "function_requirements", None
                )
                reasoning = getattr(prediction, "reasoning", None)

                self.logger.info(
                    f"Function identification completed. New function identified: {new_function_identified}"
                )

                if new_function_identified:
                    self.logger.info(f"Suggested function name: {function_name}")
                    self.logger.debug(f"Function requirements: {function_requirements}")

                self.output.result = AgentOutput(
                    reasoning=reasoning,
                    need_new_function=new_function_identified,
                    function_name=function_name,
                    function_requirements=function_requirements,
                )
                self.output.status = "success"

                self.logger.info(
                    "Function identification analysis completed successfully"
                )

            except Exception as e:
                error_msg = f"Error during function identification analysis: {str(e)}"
                self.logger.error(error_msg)
                self.output.error_msg = error_msg

            finally:
                self.output.update(
                    lm=self.lm,
                    cost_input_tokens=self.config.llm.cost_input_token,
                    cost_output_tokens=self.config.llm.cost_output_token,
                )

            return self.output
