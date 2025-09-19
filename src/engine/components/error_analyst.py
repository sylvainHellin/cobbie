from typing import Callable, List, Literal, Optional

import dspy

from src.config.agents import AGENT_CONFIGS, ErrorAnalystConfig
from src.engine.components.code_act import CodeAct
from src.engine.schemas import ModuleOutput
from src.engine.util import get_logger, get_tools_names


class ErrorAnalystSignature(dspy.Signature):
    """
    A system specializing in analyzing errors when the IFC Answer Engine provides incorrect answers to BIM/IFC model queries.

    The IFC Answer Engine is a CodeAct-based system that answers questions about BIM models by:
    1. Using a Python interpreter with access to custom-made functions for BIM data retrieval
    2. Dynamically creating new tools when existing functions are insufficient (training mode)
    3. Iteratively attempting to answer questions with available tools (max retry limit)

    This error analysis signature helps identify whether failures stem from:
    - **Faulty tools**: Existing functions returning incorrect results or behaving unexpectedly
    - **Missing tools**: Lack of necessary functions to access required BIM information
    - **Other issues**: Context problems, prompting errors, CodeAct iteration limits, or reasoning failures

    IMPORTANT
        1. In order to qualify as a missing tool, the potential tool must be:
            - Generic enough to be used for different questions, with no model-specific assumptions or hard-coded values.
            - Flexible, accepting appropriate parameters
            - Simple for the AI assistant to use in future interactions.
            - deterministically implementable with Python and IfcOpenShell without relying on any kind of regular expression tied to a specific language (such as English, German etc.)

        2. The function requirements should include:
            - A function signature with type hints
            - A clear description of the expected behaviour.

    The analysis focuses on understanding tool-related failures in the CodeAct execution loop
    to improve the system's capability for answering BIM model questions using Python code execution.
    """

    #################### Inputs ####################
    chat_history: str = dspy.InputField(
        desc="Complete chat history from the CodeAct-based IFC Answer Engine, including Python code execution attempts, tool calls, function outputs, and any error messages from the iterative process"
    )
    question: str = dspy.InputField(
        desc="The specific BIM/IFC model question that the system attempted to answer"
    )
    provided_answer: str = dspy.InputField(
        desc="The incorrect answer provided by the IFC Answer Engine"
    )
    correct_answer: str = dspy.InputField(
        desc="The ground truth or expected correct answer to the BIM question"
    )
    existing_tools: str = dspy.InputField(
        desc="A serialised list of the names of the available tools."
    )

    #################### Outputs ####################
    error_category: Literal["faulty_tool", "missing_tool", "other"] = dspy.OutputField(
        desc="The error category is 'faulty_tool' if an existing tool returns incorrect results; 'missing_tool' if the system lacks a necessary tool to access required information, or would benefit from having access to an additional tool; or 'other' if the error is not tool-related (e.g. CodeAct iteration limits, context issues or reasoning errors)."
    )
    tool_name: str = dspy.OutputField(
        desc="If the error category is either 'faulty_tool' or 'missing_tool', provide the name of the tool that is to be created or corrected. Use 'N/A' if not applicable (e.g., for 'other' category)."
    )
    error_analysis: str = dspy.OutputField(
        desc="Detailed error analysis based on error category: For 'faulty_tool' - describe the incorrect behavior in the Python function that needs correction; For 'missing_tool' - specify the function signature, parameters, and BIM data access requirements for creating a new tool; For 'other' - describe issues like CodeAct iteration limits, missing context about IFC structure, misleading prompts, or reasoning errors that could be addressed"
    )


class ErrorAnalyst(dspy.Module):
    """
    A module that analyzes errors in the CodeAct-based IFC Answer Engine to identify
    the root cause of incorrect responses to BIM/IFC model queries.

    This module helps improve the system by categorizing errors in the iterative
    Python code execution process and providing actionable mitigation strategies
    for tool development, system enhancement, and CodeAct optimization.
    """

    def __init__(
        self,
        tools: Optional[List[Callable]] = None,
        config: Optional[ErrorAnalystConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.error_analyst
        self.lm = lm or self.config.llm.get_llm()

        self.tools = tools or []
        self.max_iters = self.config.max_iters
        self.error_analyst = CodeAct(
            signature=ErrorAnalystSignature, tools=self.tools, max_iters=self.max_iters
        )
        self.log_level = self.config.log_level
        self.logger = get_logger(name="ErrorAnalyst", log_level=self.log_level)

    def forward(
        self,
        chat_history: str,
        question: str,
        provided_answer: str,
        correct_answer: str,
        existing_tools: Optional[str] = None,
    ) -> ModuleOutput:
        """
        Analyze an error from the IFC Answer Engine to categorize the failure and provide mitigation strategies.

        Args:
            chat_history: Complete execution history from the failed CodeAct session
            question: The original BIM/IFC question that was asked
            provided_answer: The incorrect answer that was provided
            correct_answer: The expected correct answer
            existing_tools (optional): This is a serialised list of the available tools. If None, it will load automatically.

        Returns:
            ModuleOutput containing:
            - result.error_category: "faulty_tool", "missing_tool", or "other"
            - result.error_analysis: Detailed analysis of the error
            - status: "success" or "error"
            - error_msg: Error description (if status is "error")
        """
        self.output = ModuleOutput(status="error")

        with dspy.context(lm=self.lm):
            self.logger.info("Starting error analysis")
            existing_tools = get_tools_names() if not existing_tools else existing_tools

            try:
                prediction = self.error_analyst(
                    chat_history=chat_history,
                    question=question,
                    provided_answer=provided_answer,
                    correct_answer=correct_answer,
                    existing_tools=existing_tools,
                )

                # Extract results
                self.output.result.error_category = getattr(
                    prediction, "error_category", None
                )
                self.output.result.error_analysis = getattr(
                    prediction, "error_analysis", None
                )
                tool_name = getattr(prediction, "tool_name", "N/A")
                # Convert "N/A" back to None for downstream processing
                self.output.result.function_name = (
                    None if tool_name == "N/A" else tool_name
                )

                # Log results
                self.logger.info("Error analysis completed successfully")
                self.logger.info(f"Error category: {self.output.result.error_category}")

                if (
                    self.output.result.error_analysis is not None
                    and self.output.result.error_category is not None
                ):
                    self.output.status = "success"
                else:
                    self.output.error_msg = (
                        "Error analysis failed: Missing required outputs"
                    )
                    self.logger.error(self.output.error_msg)

            except Exception as e:
                self.output.error_msg = f"Error during analysis: {str(e)}"
                self.logger.error(self.output.error_msg)

            finally:
                self.output.update(
                    lm=self.lm,
                    cost_input_tokens=self.config.llm.cost_input_token,
                    cost_output_tokens=self.config.llm.cost_output_token,
                )
            return self.output


if __name__ == "__main__":
    import mlflow

    def main(
        chat_history: str,
        question: str,
        provided_answer: str,
        correct_answer: str,
    ):
        # setup mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("ErrorAnalyst")

        dspy.configure_cache(
            enable_disk_cache=False,
        )

        # setup the error analyst
        error_analyst = ErrorAnalyst()

        # analyze the error
        from typing import cast

        output = cast(
            ModuleOutput,
            error_analyst(
                chat_history=chat_history,
                question=question,
                provided_answer=provided_answer,
                correct_answer=correct_answer,
            ),
        )

        print(f"Error analysis result: {output.model_dump_json(indent=2)}")

    ##########################################
    # Example usage with sample error scenario
    sample_chat_history = """
    ---[Step 1]---
    Thought: I need to count the number of doors in the IFC model. Let me use the available tools to get doors and count them.
    Code:
    ```python
    import ifcopenshell
    ifc_file = ifcopenshell.open('/path/to/model.ifc')
    doors = ifc_file.by_type('IfcDoor')
    print(f"Number of doors: {len(doors)}")
    final_answer({"door_count": len(doors)})
    ```
    Observation: Execution Logs:
    Number of doors: 15

    Output:
    {'door_count': 15}
    """

    sample_question = "How many emergency exit doors are in the building?"
    sample_provided_answer = "15"
    sample_correct_answer = "3"

    main(
        chat_history=sample_chat_history,
        question=sample_question,
        provided_answer=sample_provided_answer,
        correct_answer=sample_correct_answer,
    )
