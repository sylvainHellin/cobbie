from typing import Optional

import dspy

from src.config.agents import AGENT_CONFIGS, CodeCleanerConfig
from src.engine.schemas import ModuleOutput, AgentOutput
from src.engine.util import get_logger


class CodeCleanerSignature(dspy.Signature):
    """
    Fix syntax, compilation, or runtime errors in Python function source code.
    Analyze the error message and correct the faulty code to make it syntactically valid and executable.
    Preserve the original function's intent and logic while fixing issues like imports, syntax errors, or type issues.
    """

    faulty_code: str = dspy.InputField(
        desc="The Python source code that contains errors and needs to be fixed"
    )
    error_msg: str = dspy.InputField(
        desc="The error message describing what went wrong when trying to execute or compile the code"
    )
    reasoning: str = dspy.OutputField(
        desc="Step-by-step analysis of the error and explanation of the fixes applied"
    )
    corrected_code: str = dspy.OutputField(
        desc="The corrected Python source code that should compile and execute without errors"
    )


class CodeCleaner(dspy.Module):
    """
    A DSPy module that fixes syntax, compilation, and basic runtime errors in Python function source code.
    Uses a chain-of-thought approach to analyze error messages and apply appropriate corrections.
    """

    def __init__(
        self,
        config: Optional[CodeCleanerConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()

        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.code_cleaner
        self.lm = lm or self.config.llm.get_llm()

        # Use config for logging and other settings
        self.log_level = self.config.log_level
        self.logger = get_logger(name="CodeCleaner", log_level=self.log_level)

        self.cleaner = dspy.ChainOfThought(CodeCleanerSignature)

    def forward(
        self,
        faulty_code: str,
        error_msg: str,
    ) -> ModuleOutput:
        """
        Analyzes and fixes errors in Python function source code.

        Args:
            faulty_code (str): The Python source code that contains errors
            error_msg (str): The error message describing what went wrong

        Returns:
            ModuleOutput: An object containing the corrected code, reasoning, and status.
        """
        self.logger.info("Starting code cleaning process")
        self.output = ModuleOutput()
        self.output.llm = self.lm.model

        with dspy.context(lm=self.lm):
            try:
                prediction = self.cleaner(faulty_code=faulty_code, error_msg=error_msg)
                self.output.result = AgentOutput(
                    function_implementation=getattr(prediction, "corrected_code", None),
                    reasoning=getattr(prediction, "reasoning", None),
                )

                if (
                    self.output.result.function_implementation is not None
                    and self.output.result.reasoning is not None
                ):
                    self.output.status = "success"
                    self.logger.info("✓ Successfully cleaned code")
                else:
                    self.output.error_msg = (
                        "Code cleaner failed to generate valid output"
                    )
                    self.logger.error(self.output.error_msg)

            except Exception as e:
                self.output.error_msg = (
                    f"Error when trying to clean the faulty code. Error:\n{e}"
                )
                self.logger.error(self.output.error_msg)

            finally:
                self.output.lm_metrics.update(
                    lm=self.lm,
                    cost_input_tokens=self.config.llm.cost_input_token,
                    cost_output_tokens=self.config.llm.cost_output_token,
                )

        self.logger.info("Completed code cleaning process")
        return self.output


if __name__ == "__main__":
    import mlflow
    from typing import cast

    # setup mlflow
    mlflow.dspy.autolog()  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("CodeCleaner")

    # Example test with faulty code
    faulty_code = '''
def count_doors(ifc_file_path: str) -> int:
    """Count all doors in an IFC model."""
    model = ifcopenshell.open(ifc_file_path)  # Missing import
    doors = model.by_type("IfcDoor"  # Missing closing parenthesis
    return str(len(doors))  # Wrong return type
'''
    error_msg = "'(' was never closed (<string>, line 4)"

    print("🧪 Testing CodeCleaner...")
    print(f"Faulty code:\n{faulty_code}")
    print(f"Error message: {error_msg}")
    print("-" * 50)

    code_cleaner = CodeCleaner()
    output = cast(
        ModuleOutput, code_cleaner(faulty_code=faulty_code, error_msg=error_msg)
    )

    print(f"📊 Results:\n{output.model_dump_json(indent=2)}")
