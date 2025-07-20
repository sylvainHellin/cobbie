from typing import Literal, Optional
import time

import dspy
import mlflow

from src.config import LANGUAGE_MODELS, LOG_LEVEL
from src.engine import IfcAnswerEngine, NameExtractor, ToolCreator
from src.engine.schemas import ModuleOutput
from src.engine.util import get_logger, save_new_tool
from src.experiment.evaluation.answer_verifier import AnswerVerifier

from .data_loader import Datapoint, load_train_dev_split


class TrainingModule(dspy.Module):
    def __init__(
        self,
        lm: dspy.LM,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = LOG_LEVEL,
        training_size: Optional[int] = 2,
        similarity_treshold: float = 0.8,
        add_code_prefix = True,
        max_retry_engine: int = 2,
        max_iter_engine: int = 10,
        max_tokens_logs: int = 2**12,
        max_tokens_outputs: int = 2**12,
        import_all_created_tools: bool = True,
        tracking_uri: str = "http://127.0.0.1:5000",
        experiment_name: str = "Training"
    ):
        super().__init__()
        self.lm = lm
        self.log_level = log_level
        self.logger = get_logger(name="Training", log_level=log_level)
        self.training_size = training_size
        self.similarity_treshold = similarity_treshold
        self.add_code_prefix = add_code_prefix
        self.max_retry_engine = max_retry_engine
        self.max_iter_engine = max_iter_engine
        self.max_tokens_logs = max_tokens_logs
        self.max_tokens_outputs = max_tokens_outputs
        self.import_all_created_tools = import_all_created_tools
        self.tracking_uri = tracking_uri
        self.experiment_name = experiment_name
        self.correct_answer: Optional[bool] = None
        self.new_function_created: Optional[bool] = None
        self.function_name: Optional[str] = None
        self.function_code: Optional[str] = None
        self.function_requirements: Optional[str] = None
        self.answer_verifier = AnswerVerifier()

        self.engine = IfcAnswerEngine(
            llm=self.lm,
            max_retry=self.max_retry_engine,
            max_iters=self.max_iter_engine,
            log_level=self.log_level,
            max_tokens_logs=self.max_tokens_logs,
            max_tokens_output=self.max_tokens_outputs,
            import_all_created_tools=self.import_all_created_tools,
            add_code_prefix=self.add_code_prefix
            )

    def forward(self, datapoint: Datapoint) -> ModuleOutput:

        # Set-up MLflow and DSPy
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri(self.tracking_uri)
        mlflow.set_experiment(self.experiment_name)
        dspy.configure(lm=self.lm)

        # Instantiate the original output
        output = ModuleOutput(status="error", error_msg="Initial error msg from Training Module.")

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
                            new_function_implementation = output_engine.result.function_implementation
                            assert new_function_name, "Logical Error: The output of the engine is a success, and it needs a new function, but the function name is None."
                            assert(new_function_implementation), "Logical Error: the output of the engine is a success and it needed a new function, but the function implementation is None."

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
    lm_name: str = "kimi-k2",
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
        training_module = TrainingModule(lm=llm)
        output = training_module.forward(datapoint=datapoint)
        print(output)


if __name__ == "__main__":
    main(training_size=1)
