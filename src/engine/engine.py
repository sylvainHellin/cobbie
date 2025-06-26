from typing import Callable, Dict, List, Literal, Optional

import dspy
import mlflow

from src.engine.schemas import ModuleOutput, Result
from src.engine.tools import get_created_tools
from src.engine.tools.primordial.python_interpreter import get_python_interpreter
from src.engine.util import get_logger


class EngineSignature(dspy.Signature):
    """
    Answer any questions users have about a BIM model in .ifc format.
    You have access to a Python interpreter to retrieve information from the BIM model. This interpreter allows you to call several custom-made functions that were created specifically to retrieve information from a BIM model.

    If you lack a specialised function to enable you to answer the question properly, indicate this using the 'need_new_function' boolean output field and describe what the new function should be able to do in the 'answer' output field. Be as precise as possible when describing your requirements for this new tool (at a minimum, provide the function signature and a basic explanation of the expected output). This information will be passed to an expert software engineer who will implement the function for you.

    If you can answer the question using the interpreter and the provided tools, set 'need_new_function' to false and provide the answer in the 'answer' field.
    """

    # Inputs
    question: str = dspy.InputField()
    path_ifc_model: str = dspy.InputField(
        desc="The path to the .ifc file of the BIM model."
    )
    available_functions: Dict[str, str] = dspy.InputField(
        desc="This is a list of all the available function names and their corresponding docstrings. These functions can be used within the Python interpreter."
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
        max_iters: int = 10,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
        max_tokens_logs: int = 2**12,
        max_tokens_output: int = 2**12,
        import_all_created_tools: bool = True,
    ):
        super().__init__()
        self.max_iters = max_iters
        self.log_level = log_level
        self.logger = get_logger(name="ToolProgrammer", log_level=self.log_level)
        self.additional_authorized_functions = additional_authorized_functions or {}
        self.additional_authorized_imports = additional_authorized_imports
        self.max_tokens_logs = max_tokens_logs
        self.max_tokens_output = max_tokens_output
        if import_all_created_tools:
            tools = get_created_tools() or {}
            self.additional_authorized_functions = (
                self.additional_authorized_functions | tools
            )
        self.available_functions: Dict[str, str] = {}
        for name, fn in self.additional_authorized_functions.items():
            self.available_functions[name] = fn.__doc__ or "no Docstring available"
        self.interpreter = get_python_interpreter(
            additional_authorized_functions=self.additional_authorized_functions,
            additional_authorized_imports=self.additional_authorized_imports,
            max_tokens_logs=self.max_tokens_logs,
            max_tokens_output=self.max_tokens_output,
        )
        self.engine = dspy.ReAct(signature=EngineSignature, tools=[self.interpreter])
        self.logger.info("Agent initialized.")

    def forward(self, question: str, path_ifc_model: str) -> ModuleOutput:
        self.logger.info("Starting forward pass.")
        self.logger.debug(
            f"\nquestion: {question}\npath_ifc_models: {path_ifc_model}\navailable tools: \n -{' -'.join([name for name, fn in self.available_functions.items()])}"
        )

        output = ModuleOutput(
            status="error", error_msg="IfcAnswerEngine could not answer the question."
        )
        with mlflow.start_span("IfcAnswerEngine"):
            try:
                prediction = self.engine(
                    question=question,
                    path_ifc_model=path_ifc_model,
                    available_functions=self.available_functions,
                )
                output.result = Result(
                    answer=prediction.answer,
                    need_new_function=prediction.need_new_function,
                    reasoning=prediction.reasoning,
                    trajectory=prediction.trajectory,
                )
                output.status = "success"
                output.error_msg = None
                self.logger.info("Forward pass completed with status: 'success'")
                self.logger.debug(f"Answer: {prediction.answer}")

            except Exception as e:
                msg = (
                    f"Error during the forward pass of the IfcAnswerEngine.\nError: {e}"
                )
                output.error_msg = msg
                self.logger.error(msg)

            return output


if __name__ == "__main__":
    # Test the IfcAnswerEngine
    ifc_model_path = "/Users/sylvainhellin/GitHub/ifcAnswerEngineV3/src/experiment/bim_models/duplex/arc.ifc"
    question = "What is the height of the living room?"
    from src.config import LANGUAGE_MODELS

    lm_info = LANGUAGE_MODELS["claude"]
    lm = dspy.LM(lm_info.url, api_key=lm_info.api_key)
    dspy.configure(lm=lm)
    mlflow.dspy.autolog()  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("Testing IfcAnswerEngine")
    print("MLflow tracking enabled")

    print("Testing IfcAnswerEngine with:")
    print(f"IFC Model: {ifc_model_path}")
    print(f"Question: {question}")
    print("-" * 50)

    # Initialize the engine
    engine = IfcAnswerEngine(log_level="INFO", import_all_created_tools=True)

    # Run the test
    try:
        result = engine.forward(question=question, path_ifc_model=ifc_model_path)

        print(f"Status: {result.status}")
        if result.status == "success" and result.result:
            print(f"Need new function: {result.result.need_new_function}")
            print(f"Answer: {result.result.answer}")
            if hasattr(result.result, "reasoning") and result.result.reasoning:
                print(f"Reasoning: {result.result.reasoning}")
        else:
            print(f"Error: {result.error_msg}")

    except Exception as e:
        print(f"Test failed with exception: {e}")

    print("END")
