# Implementation of the IfcAnswerEngine
# The engine is not in charge of saving new tools ; this is handle at the `training` level

## Signature
# input: question, path ifc model
# output: answer
# state:
#   new_function: bool
#   new_function_implementation: Optional[str]
#   new_function_name: Optional[str]

## Module
# The engine is a dspy.Module based on CodeAct that tried to answer the question, and call the ToolCreator if a new tool is needed.
# it should have an argument to decide which tools to include (e.g. `query_ifc_documentation` and `web_search`)
# also an argument to decide between inference and training mode (2 different signatures -> can call the ToolCreator or not)

from typing import Callable, Dict, List, Literal, Optional

import dspy
import mlflow

from src.engine.schemas import ModuleOutput
from src.engine.tools import get_created_tools
from src.engine.util import (
    get_logger,
    _create_function_from_source_code,
    create_code_prefix,
)
from src.engine.components import CodeAct, ToolCreator, NameExtractor

from src.config import AGENT_CONFIGS, LANGUAGE_MODELS, FUNCTION_BOILERPLATE


class IfcAnwerEngineSignature(dspy.Signature):
    """
    Answer any questions users have about the BIM model in .ifc format.

    You have access to a Python interpreter that can retrieve information from the model. The interpreter provides access to custom-made functions created specifically to retrieve information from BIM models. Note that the provided Python interpreter is stateless and any variable you want to use must be defined and instantiated inside the provided code. For example, the provided path_ifc_model is not loaded in the Python interpreter and would raise an error if it is not defined in the generated code snippet.

    If you lack a specialised function to enable you to answer the question properly, indicate this using the 'need_new_function' boolean output field and describe what the new function should be able to do in the 'answer' output field. Be as precise as possible when describing your requirements for this new tool (at a minimum, provide the function signature and a basic explanation of the expected output). This information will be passed to an expert software engineer who will implement the function for you.

    If you can answer the question using the interpreter and the provided tools, set 'need_new_function' to false and provide the answer in the 'answer' field.

    Keep in mind that the person asking the questions may not be a BIM expert. They may not have the .ifc model open in other software, so they may ask you questions using names for entities (e.g., room, material) that don't exactly match those used in the BIM model. You will need to determine the exact name/ID of any corresponding components yourself.
    """

    # Inputs
    question: str = dspy.InputField()
    path_ifc_model: str = dspy.InputField(
        desc="The path to the .ifc file of the BIM model."
    )

    # Outputs
    need_new_function: bool = dspy.OutputField(
        desc="Can you answer the question with the given tools?"
    )
    answer: str = dspy.OutputField(
        desc="The answer to the user's question OR the requirement for the additional tool needed to answer the question."
    )


class IfcAnswerEngine(dspy.Module):
    """
    This is an engine that can answer questions in natural language related to a BIM model in .ifc format.
    The engine has an 'inference' and a 'training' mode.
        In training mode, the engine has access to the ground truth and can dynamically generate new functions to try to answer the question.
        In inference mode, the engine does not have access to the ground truth and attempts to answer the question using the available tools.
    """

    def __init__(
        self,
        additional_authorized_functions: Optional[Dict[str, Callable]] = None,
        additional_authorized_imports: Optional[List[str]] = None,
        config=None,
        llm: Optional[dspy.LM] = None,  # Optional override
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.ifc_answer_engine

        self.max_iters = self.config.max_iters
        self.max_retry: int = self.config.max_retry
        self.iter: int = 0
        self.log_level = self.config.log_level
        # Use provided LLM or get from config
        self.lm = llm or self.config.llm.get_llm()
        self.logger = get_logger(name="IfcAnswerEngine", log_level=self.log_level)
        self.additional_authorized_functions = additional_authorized_functions or {}
        self.additional_authorized_imports = additional_authorized_imports or []
        self.max_tokens_logs = self.config.max_tokens_logs
        self.max_tokens_output = self.config.max_tokens_output
        self.created_tools: Dict[str, Callable] = {}
        self.add_code_prefix = self.config.add_code_prefix
        self.tool_creator: ToolCreator = ToolCreator(
            config=self.config.tool_creator,
        )
        self.name_extractor = NameExtractor(log_level=self.log_level)
        dspy.configure(lm=self.lm)

        if self.config.import_all_created_tools:
            self.created_tools = get_created_tools()
            self.additional_authorized_functions = (
                self.additional_authorized_functions | self.created_tools
            )

        self.engine = CodeAct(
            signature=IfcAnwerEngineSignature,
            tools=[fn for _, fn in self.additional_authorized_functions.items()],
            max_iters=self.max_iters,
        )
        self.logger.info("IfcAnswerEngine initialized.")

    def forward(self, question: str, path_ifc_model: str = "") -> ModuleOutput:
        self.iter = 0
        self.logger.info("Starting forward pass.")

        self.output = ModuleOutput(
            status="error", error_msg="IfcAnswerEngine could not answer the question."
        )
        if self.add_code_prefix:
            code_prefix = create_code_prefix(
                path_ifc_model=path_ifc_model, imports_boilerplate=FUNCTION_BOILERPLATE
            )
        else:
            code_prefix = None

        self.engine._update_code_prefix(code_prefix=code_prefix)

        with mlflow.start_span("IfcAnswerEngine"):
            # Start the loop: try to answer the question with existing tool
            while self.iter < self.max_retry:
                with mlflow.start_span(f"iter Nr. {self.iter + 1}"):
                    self.logger.info(
                        f"\n\n### Strarting iter Nr. {self.iter + 1} ###\n\n"
                    )
                    try:
                        prediction = self.engine.forward(
                            question=question,
                            path_ifc_model=path_ifc_model,
                        )
                        # If no new fn is needed, extract the answer, and exit the loop to return the output
                        if not prediction.need_new_function:
                            self.output.status = "success"
                            self.output.error_msg = None
                            self.output.result.answer = prediction.answer
                            self.output.result.need_new_function = False
                            self.iter = self.max_retry
                            break

                        # If a new function is needed: call the toolCreator
                        # Check if the requirements for the new function are present
                        elif prediction.answer is None:
                            self.output.status = "error"
                            self.output.error_msg = "LOGICAL FLAW: New function is set to True, but no answer with the function requirements is available."
                            self.logger.error(self.output.error_msg)

                        else:
                            self.output.result.need_new_function = True
                            self.logger.info(
                                "Forward pass completed with status: 'success'"
                            )
                            self.logger.debug(f"Answer: {prediction.answer}")
                            self.output.result.function_requirements = (
                                prediction.answer or ""
                            )
                            # Try to extract the fn name from requirements
                            output_name_extractor = self.name_extractor.forward(
                                function_requirements=self.output.result.function_requirements
                            )
                            # If fn name could be extracted, try to create the new fn
                            if (
                                output_name_extractor.status == "success"
                                and output_name_extractor.result.function_name
                                is not None
                            ):
                                self.output.result.function_name = (
                                    output_name_extractor.result.function_name
                                )

                                output_tool_creator = self.tool_creator.forward(
                                    function_requirements=self.output.result.function_requirements,
                                    function_name=self.output.result.function_name,
                                    path_ifc_model=path_ifc_model,
                                )

                                # If the new fn could be created, create a new tool
                                if output_tool_creator.status == "success":
                                    if (
                                        output_tool_creator.result.function_implementation
                                        is None
                                    ):
                                        self.output.error_msg = "Logical error: status of ToolCreator is 'success', but function_implementation is None"
                                        self.logger.error(self.output.error_msg)
                                    else:
                                        self.function_implementation = output_tool_creator.result.function_implementation
                                        self.output.result.new_function = _create_function_from_source_code(
                                            function_name=self.output.result.function_name,
                                            code=self.function_implementation,
                                        )
                                        self.additional_authorized_functions[
                                            self.output.result.function_name
                                        ] = self.output.result.new_function

                                        # Update the tools available to the engine to include the new one.
                                        self.engine._update_tools(
                                            tools=[
                                                fn
                                                for _, fn in self.additional_authorized_functions.items()
                                            ],
                                        )
                            else:
                                self.output.error_msg = f"An Error occured while trying to extract the function's name. Error: {output_name_extractor.error_msg}"
                                self.logger.error(self.output.error_msg)

                    except Exception as e:
                        msg = f"Error during the forward pass of the IfcAnswerEngine.\nError: {e}"
                        self.output.error_msg = msg
                        self.logger.error(msg)

                    finally:
                        self.iter += 1

            return self.output


if __name__ == "__main__":
    # Test the IfcAnswerEngine
    ifc_model_path = "/Users/sylvainhellin/GitHub/ifcAnswerEngineV3/src/experiment/bim_models/duplex/arc.ifc"
    question = "What is the height of the living room?"

    mlflow.dspy.autolog()  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("IfcAnswerEngine")

    # Initialize the engine - LLM comes from config now!
    engine = IfcAnswerEngine()

    # Run the test
    try:
        output = engine.forward(question=question, path_ifc_model=ifc_model_path)
        print(output.model_dump_json(indent=2))
    except Exception as e:
        print(f"Exception: \n{e}")

    print("END")
