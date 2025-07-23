from datetime import datetime
from typing import Optional

import dspy
import mlflow

from src.config import AGENT_CONFIGS
from src.engine import IfcAnswerEngine
from src.engine.schemas import ModuleOutput
from src.engine.util import get_logger, save_new_tool
from src.experiment.evaluation.answer_verifier import AnswerVerifier

from .data_loader import QA_Pair, load_train_dev_split


class TrainingModule(dspy.Module):
    def __init__(
        self,
        config=None,
        lm: Optional[dspy.LM] = None,  # Optional override
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.training_module
        self.logger = get_logger(name="Training", log_level=self.config.log_level)

        # Use provided LLM or get from config
        self.lm = lm or self.config.llm.get_llm()

        # Set-up the agents
        self.answer_verifier = AnswerVerifier()
        self.engine = IfcAnswerEngine(
            config=self.config.engine,
        )

    def forward(self, qa_pair: QA_Pair) -> ModuleOutput:
        # Set-up MLflow and DSPy
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri(self.config.tracking_uri)
        mlflow.set_experiment(self.config.experiment_name)
        mlflow.start_run(run_name=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))
        dspy.configure(lm=self.lm)
        self.lm.history.clear()
        self.lm.history.count()

        # Instantiate the original output
        self.output = ModuleOutput(
            status="error",
            error_msg="Default error message from initialization of TrainingModule.",
        )

        with mlflow.start_span(name=f"question_id_{qa_pair.id}") as span:
            # Init and run engine
            output_engine = self.engine.forward(
                question=qa_pair.question, path_ifc_model=qa_pair.ifc_model_path
            )

            # Control flow
            if output_engine.status == "success":
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
                    self.logger.debug(f"Ground Truth: \n{qa_pair.answer}")

                    # init AnswerVerifier
                    output_answer_verifier = self.answer_verifier.forward(
                        question=qa_pair.question,
                        first_answer=qa_pair.answer,
                        second_answer=output_engine.result.answer,
                    )

                    if output_answer_verifier.status == "error":
                        self.output.error_msg = f"There was an error with the AnswerVerifier. Error message: {output_answer_verifier.error_msg or 'No error message provided'}"
                        self.logger.error(self.output.error_msg)

                    else:
                        assert (
                            output_answer_verifier.result.similarity_score is not None
                        ), (
                            "Something is off: the status of AnswerVerifier is 'success', but the `similarity_score` field is None."
                        )
                        self.output.error_msg = None
                        self.output.status = "success"

                        # Set the correct_answer state according to the provided treshold
                        self.output.result.correct_answer = (
                            True
                            if output_answer_verifier.result.similarity_score
                            >= self.config.similarity_threshold
                            else False
                        )
                        self.output.result.answer = output_engine.result.answer

                        self.logger.info(
                            f"AnswerVerifier could check the answer. Status: {'correct' if self.output.result.correct_answer else 'wrong'}"
                        )
                        self.logger.debug(
                            f"Similarity score: \n{output_answer_verifier.result.similarity_score}\nCorrect answer: {self.output.result.correct_answer}"
                        )

                        # If the Engine created a new function, let's see if it's correctly implemented.
                        if self.output.result.correct_answer:
                            if output_engine.result.need_new_function:
                                self.output.result.need_new_function = True

                                self.output.result.function_name = (
                                    output_engine.result.function_name
                                )
                                self.output.result.function_implementation = (
                                    output_engine.result.function_implementation
                                )
                                assert self.output.result.function_name, (
                                    "Logical Error: The output of the engine is a success, and it needs a new function, but the function name is None."
                                )
                                assert self.output.result.function_implementation, (
                                    "Logical Error: the output of the engine is a success and it needed a new function, but the function implementation is None."
                                )

                                new_tool_saved = save_new_tool(
                                    function_name=self.output.result.function_name,
                                    function_implementation=self.output.result.function_implementation,
                                )
                                assert new_tool_saved, (
                                    "A new tool was created but could not be saved."
                                )

            else:
                self.output.error_msg = f"There was a problem with question ID: {qa_pair.id}.\n Error msg: {output_engine.error_msg or 'No error message available'}"
                self.logger.error(self.output.error_msg)

            span.set_inputs(
                {
                    "question_id": qa_pair.id,
                    "question": qa_pair.question,
                }
            )
            span.set_outputs(
                {
                    "correct_answer": self.output.result.correct_answer or False,
                    "answer": self.output.result.answer or "No Answer available.",
                    "need_new_tool": self.output.result.need_new_function or False,
                }
            )
            span.set_attributes(self.output.result.model_dump())

            mlflow.update_current_trace(
                tags={
                    "correct_answer": str(self.output.result.correct_answer or False),
                    "answer": self.output.result.answer or "",
                    "need_new_tool": str(self.output.result.need_new_function or False),
                }
            )
            if self.output.result.need_new_function:
                mlflow.set_tag(key="new_tool_created", value=True)

            return self.output


def main(start: int = 0, finish: int = -1):
    # setup mlflow
    mlflow.dspy.autolog()  # type: ignore
    train, dev = load_train_dev_split()

    # setup the logger
    logger = get_logger(
        name="Training run", log_level=AGENT_CONFIGS.training_module.log_level
    )

    for qa_pair in train[start:finish]:
        # Log info
        logger.info(f"Try to answer new question: {qa_pair.question}\n\n")
        training_module = TrainingModule()
        output = training_module.forward(qa_pair=qa_pair)
        print(output)


if __name__ == "__main__":
    main(start=1, finish=2)
