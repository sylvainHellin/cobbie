from typing import Literal, Optional

import dspy
import mlflow

from src.config import LANGUAGE_MODELS, LOG_LEVEL
from src.engine import IfcAnswerEngine, NameExtractor, ToolCreator
from src.engine.schemas import ModuleOutput
from src.engine.util import get_logger
from src.experiment.evaluation.answer_verifier import AnswerVerifier

from .data_loader import Datapoint, load_train_dev_split


class TrainingModule(dspy.Module):
    def __init__(
        self,
        llm: dspy.LM,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = LOG_LEVEL,
        training_size: Optional[int] = 2,
        similarity_treshold: float = 0.8,
    ):
        super().__init__()
        self.llm = llm
        self.log_level = log_level
        self.logger = get_logger(name="TrainingModule", log_level=log_level)
        self.training_size = training_size
        self.similarity_treshold = similarity_treshold
        self.correct_answer: Optional[bool] = None
        self.new_function_created: Optional[bool] = None
        self.function_name: Optional[str] = None
        self.function_code: Optional[str] = None
        self.function_requirements: Optional[str] = None
        self.tool_creator = ToolCreator(llm=self.llm)
        self.answer_verifier = AnswerVerifier()
        self.engine = IfcAnswerEngine()

    def forward(self, datapoint: Datapoint) -> ModuleOutput:
        output = ModuleOutput(status="error")

        with mlflow.start_span("TrainingModule"):
            # Init and run engine
            output_engine = self.engine.forward(
                question=datapoint.question, path_ifc_model=datapoint.ifc_model_path
            )

            # Control flow
            if output_engine.status == "success":
                # Assert that our logic is sound.
                assert output_engine.result.need_new_function is not None, (
                    "Something is off: the status is set to 'success', but the field `need_new_function` is None."
                )

                assert output_engine.result.answer is not None, (
                    "Something is off: the status is set to 'success', but the `answer` field is None."
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
                        second_answer=output_engine.result.answer
                        or "No answer provided.",
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
                # If the Engine need a new function, let's try to create it!
                else:
                    self.function_requirements = output_engine.result.answer
                    self.logger.info("A new tool is needed to answer this question.")
                    self.logger.debug(
                        f"Requirements for the new tool:\n{self.function_requirements}"
                    )
                    # 1. Extract the name of the function
                    name_extractor = NameExtractor()
                    output_name_extractor = name_extractor.forward(
                        function_requirements=self.function_requirements
                    )

                    if output_name_extractor.status == "error":
                        self.logger.error(
                            f"Error when trying to extract the function's name: {output_name_extractor.error_msg}"
                        )
                    else:
                        assert output_name_extractor.result.function_name is not None, (
                            "Something is off: the status of NameExtractor is 'success', but the `function_name` field is None."
                        )
                        self.function_name = output_name_extractor.result.function_name
                        self.logger.info("Name of the function extracted successfully.")
                        self.logger.debug(f"Name of the function: {self.function_name}")

                        # Start the ToolCreator!
                        output_tool_creator = self.tool_creator.forward(
                            function_requirements=self.function_requirements,
                            function_name=self.function_name,
                            path_ifc_model=datapoint.ifc_model_path,
                        )

                        if output_tool_creator.status == "error":
                            self.logger.error(
                                f"Error during Tool Creation: {output_tool_creator.error_msg}"
                            )
                        else:
                            assert output_tool_creator.result.python_code is not None, (
                                "Something is off: the status of ToolCreator is 'success', but the `python_code` field is None."
                            )
                            self.function_code = output_tool_creator.result.python_code
                            self.logger.info("Tool was successfully created.")
                            self.logger.debug(
                                f"Python code of the function: {self.function_name}:\n{self.function_code}"
                            )

            else:
                self.logger.error(
                    f"There was a problem. Error msg: {output_engine.error_msg or 'No error message available'}"
                )
            return output


def main(
    lm_name: str = "llama4-maverick-groq",
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
    training_size: Optional[int] = 2,
    similarity_treshold: float = 0.8,
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
    mlflow.set_experiment("Training")
    train, dev = load_train_dev_split()

    # setup the logger
    logger = get_logger(name="Training run", log_level=log_level)

    for datapoint in train[: training_size or -1]:
        # Log info
        logger.info(f"Try to answer new question: {datapoint.question}\n\n")
        mlflow.start_run(run_name=f"question_id_{datapoint.id}")
        training_module = TrainingModule(llm=llm)
        output = training_module.forward(datapoint=datapoint)
        print(output)


if __name__ == "__main__":
    main(training_size=1)
