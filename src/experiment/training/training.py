from typing import Literal, Optional
import time

import dspy
import mlflow

from src.config import AGENT_CONFIGS, LANGUAGE_MODELS, LOG_LEVEL
from src.engine import IfcAnswerEngine, NameExtractor, ToolCreator
from src.engine.schemas import ModuleOutput
from src.engine.util import get_logger, save_new_tool
from src.experiment.evaluation.answer_verifier import AnswerVerifier

from .data_loader import Datapoint, load_train_dev_split


class TrainingModule(dspy.Module):
    def __init__(
        self,
        config=None,
        lm: Optional[dspy.LM] = None,  # Optional override
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.training_module

        # Use provided LLM or get from config
        self.lm = lm or self.config.llm.get_llm()
        self.log_level = self.config.log_level
        self.logger = get_logger(name="Training", log_level=self.log_level)
        self.training_size = self.config.training_size
        self.similarity_treshold = self.config.similarity_threshold
        self.tracking_uri = self.config.tracking_uri
        self.experiment_name = self.config.experiment_name
        self.correct_answer: Optional[bool] = None
        self.new_function_created: Optional[bool] = None
        self.function_name: Optional[str] = None
        self.function_code: Optional[str] = None
        self.function_requirements: Optional[str] = None
        self.answer_verifier = AnswerVerifier()

        self.engine = IfcAnswerEngine(
            config=self.config.engine,
        )

    def forward(self, datapoint: Datapoint) -> ModuleOutput:
        # Set-up MLflow and DSPy
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(self.experiment_name)
        dspy.configure(lm=self.lm)

        # Instantiate the original output
        output = ModuleOutput(
            status="error", error_msg="Initial error msg from Training Module."
        )

        now = time.time()
        with mlflow.start_span(str(now)):
            # Init and run engine
            output_engine = self.engine.forward(
                question=datapoint.question, path_ifc_model=datapoint.ifc_model_path
            )

            # Control flow
            if output_engine.status == "success":
                # Assert that our logic is sound.
                assert output_engine.result.need_new_function is not None, (
                    "Something is off: the status is set to 'success', but the field `need_new_function` is None. Should be True or False."
                )

                assert output_engine.result.answer is not None, (
                    "Something is off: the status is set to 'success', but the `answer` field is None. It should contain something."
                )

                # If the Engine could answer the question, let's check if it's correct
                if not output_engine.result.need_new_function:
                    self.logger.info("IfcAnswerEngine could answer the question.")
                    self.logger.debug(f"Answer: \n{output_engine.result.answer}")
                    self.logger.debug(f"Ground Truth: \n{datapoint.answer}")

                    # init AnswerVerifier
                    output_answer_verifier = self.answer_verifier.forward(
                        question=datapoint.question,
                        first_answer=datapoint.answer,
                        second_answer=output_engine.result.answer,
                    )
                    if output_answer_verifier.status == "error":
                        self.logger.error("There was an error with the AnswerVerifier")
                    else:
                        assert (
                            output_answer_verifier.result.similarity_score is not None
                        ), (
                            "Something is off: the status of AnswerVerifier is 'success', but the `similarity_score` field is None."
                        )
                        # Set the correct_answer state according to the provided treshold
                        correct_answer = (
                            True
                            if output_answer_verifier.result.similarity_score
                            >= self.similarity_treshold
                            else False
                        )

                        self.logger.info("AnswerVerifier could check the answer.")
                        self.logger.info(
                            f"Similarity score: \n{output_answer_verifier.result.similarity_score}\nCorrect answer: {correct_answer}"
                        )
                        # If the Engine created a new function, let's see if it's correctly implemented.
                        if correct_answer and output_engine.result.need_new_function:
                            new_function_name = output_engine.result.function_name
                            new_function_implementation = (
                                output_engine.result.function_implementation
                            )
                            assert new_function_name, (
                                "Logical Error: The output of the engine is a success, and it needs a new function, but the function name is None."
                            )
                            assert new_function_implementation, (
                                "Logical Error: the output of the engine is a success and it needed a new function, but the function implementation is None."
                            )

                            new_tool_saved = save_new_tool(
                                function_name=new_function_name,
                                function_implementation=new_function_implementation,
                            )
                            assert new_tool_saved, "Could not save the new tool."

            else:
                self.logger.error(
                    f"There was a problem. Error msg: {output_engine.error_msg or 'No error message available'}"
                )
            return output


def main(
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
    training_size: Optional[int] = 2,
    similarity_treshold: float = 0.8,
):
    # LLM configuration is now handled in the config system
    pass

    # setup mlflow
    mlflow.dspy.autolog()  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("Training")
    train, dev = load_train_dev_split()

    # setup the logger
    logger = get_logger(name="Training run", log_level=log_level)

    for datapoint in train[: training_size or -1]:
        # Log info
        logger.info(f"Try to answer new question: {datapoint.question}\n\n")
        mlflow.start_run(run_name=f"question_id_{datapoint.id}")
        training_module = TrainingModule()
        output = training_module.forward(datapoint=datapoint)
        print(output)


if __name__ == "__main__":
    main(training_size=1)
