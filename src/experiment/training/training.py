from datetime import datetime
from enum import Enum
from typing import Optional

import dspy
import mlflow

from src.config import AGENT_CONFIGS
from src.engine import IfcAnswerEngine, ToolIdentifier, ToolCreator, ErrorAnalyst
from src.engine.schemas import ModuleOutput, Chat, TrainingContext
from src.engine.util import get_logger, save_new_tool
from src.experiment.evaluation.answer_verifier import AnswerVerifier

from .data_loader import QA_Pair, load_train_dev_split


class TrainingState(Enum):
    """States for the training module state machine."""

    START_FORWARD_PASS = "started"
    PROCESS_QUESTION = "engine_success"
    ENGINE_FAILED = "engine_failed"
    ANSWER_VERIFICATION = "answer_verification"
    VERIFICATION_COMPLETED = "verification_completed"
    ANALYSIS_CORRECT_ANSWER = "tool_identification_needed"
    ANALYSIS_WRONG_ANSWER = "error_analyst"
    TOOL_CREATION_NEEDED = "tool_creation_needed"
    NEW_TOOL_CREATED = "new_function_ready"
    COMPLETED_FORWARD_PASS = "completed"
    ERROR = "error"


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
        self.chat = Chat()

        # Set-up the agents (using the default config for each agent)
        self.answer_verifier = AnswerVerifier()
        self.engine = IfcAnswerEngine()
        self.tool_identifier = ToolIdentifier()
        self.tool_creator = ToolCreator()
        self.error_analyst = ErrorAnalyst()

        # Set-up mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri(self.config.tracking_uri)
        mlflow.set_experiment(self.config.experiment_name)
        mlflow.start_run(run_name=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))

        # State machine attributes
        self.state = TrainingState.START_FORWARD_PASS
        self.context = TrainingContext()  # Typed context to pass data between states

    def _initialize_processing(self, qa_pair: QA_Pair) -> TrainingState:
        """Initialize processing state and setup."""
        self.context.clear()
        self.context.qa_pair = qa_pair
        self.context.span = None

        # Initialize default output
        self.output = ModuleOutput(
            status="error",
            error_msg="Default error message from initialization of TrainingModule.",
        )

        # Setup DSPy
        dspy.configure(lm=self.lm)
        self.lm.history.clear()

        return TrainingState.PROCESS_QUESTION

    def _handle_engine_processing(self) -> TrainingState:
        """Run the engine and determine next state."""
        assert self.context.qa_pair
        qa_pair = self.context.qa_pair

        # Run the engine
        output_engine = self.engine.forward(
            question=qa_pair.question, path_ifc_model=qa_pair.ifc_model_path
        )
        self.chat.import_chat_messages(self.lm.history[-1].get("messages"))
        self.context.engine_output = output_engine

        if output_engine.status == "success":
            # Validate engine output
            assert output_engine.result.need_new_function is not None, (
                "Something is off: the status is set to 'success', but the field `need_new_function` is None."
            )
            assert output_engine.result.answer is not None, (
                "Something is off: the status is set to 'success', but the `answer` field is None."
            )

            if output_engine.result.need_new_function:
                return TrainingState.NEW_TOOL_CREATED
            else:
                return TrainingState.ANSWER_VERIFICATION
        else:
            return TrainingState.ENGINE_FAILED

    def _handle_engine_failure(self) -> TrainingState:
        """Handle engine failure."""
        assert self.context.qa_pair, "QA pair missing in context."
        qa_pair = self.context.qa_pair
        engine_output = self.context.engine_output

        self.output.error_msg = (
            f"There was a problem with question ID: {qa_pair.id}.\n"
            f"Error msg: {engine_output.error_msg or 'No error message available'}"
        )
        self.logger.error(self.output.error_msg)
        return TrainingState.ERROR

    def _handle_answer_verification(self) -> TrainingState:
        """Handle answer verification."""
        qa_pair = self.context.qa_pair
        assert qa_pair, "Error: QA pair is not defined."
        engine_output = self.context.engine_output

        self.logger.info("IfcAnswerEngine could answer the question.")
        self.logger.debug(f"Answer: \n{engine_output.result.answer}")
        self.logger.debug(f"Ground Truth: \n{qa_pair.answer}")

        # Verify if answer is correct
        assert engine_output.result.answer, (
            "Error: Answer in Engine Output is None. disn"
        )
        output_answer_verifier = self.answer_verifier.forward(
            question=qa_pair.question,
            first_answer=qa_pair.answer,
            second_answer=engine_output.result.answer,
        )
        self.context.verifier_output = output_answer_verifier

        if output_answer_verifier.status == "error":
            self.output.error_msg = (
                f"There was an error with the AnswerVerifier. "
                f"Error message: {output_answer_verifier.error_msg or 'No error message provided'}"
            )
            self.logger.error(self.output.error_msg)
            return TrainingState.ERROR
        else:
            return TrainingState.VERIFICATION_COMPLETED

    def _handle_answer_verification_completed(self) -> TrainingState:
        """Process verification results."""
        engine_output = self.context.engine_output
        verifier_output = self.context.verifier_output

        assert verifier_output.result.similarity_score is not None, (
            "Something is off: the status of AnswerVerifier is 'success', but the `similarity_score` field is None."
        )

        # Update output with verification results
        self.output.error_msg = None
        self.output.status = "success"
        self.output.result.correct_answer = (
            verifier_output.result.similarity_score >= self.config.similarity_threshold
        )
        self.output.result.answer = engine_output.result.answer

        status = "correct" if self.output.result.correct_answer else "wrong"
        self.logger.info(f"AnswerVerifier could check the answer. Status: {status}")
        self.logger.debug(
            f"Similarity score: {verifier_output.result.similarity_score}\n"
            f"Correct answer: {self.output.result.correct_answer}"
        )

        if self.output.result.correct_answer:
            # Check if the engine already created a new function
            if engine_output.result.need_new_function:
                return TrainingState.NEW_TOOL_CREATED
            else:
                return TrainingState.ANALYSIS_CORRECT_ANSWER
        else:
            return TrainingState.ANALYSIS_WRONG_ANSWER

    def _handle_new_function_ready(self) -> TrainingState:
        """Handle case where engine created a new function."""
        engine_output = self.context.engine_output

        self.output.result.need_new_function = True
        self.output.result.function_name = engine_output.result.function_name
        self.output.result.function_implementation = (
            engine_output.result.function_implementation
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
        assert new_tool_saved, "A new tool was created but could not be saved."

        return TrainingState.COMPLETED_FORWARD_PASS

    def _handle_correct_answer(self) -> TrainingState:
        """Try to identify useful new tools."""
        output_tool_identifier = self.tool_identifier.forward(
            chat_history=self.chat.to_string()
        )
        self.context.tool_identifier_output = output_tool_identifier

        if output_tool_identifier.status == "success":
            assert output_tool_identifier.result.need_new_function is not None

            if output_tool_identifier.result.need_new_function:
                assert (
                    output_tool_identifier.result.function_name is not None
                    and output_tool_identifier.result.function_requirements is not None
                )
                return TrainingState.TOOL_CREATION_NEEDED

        return TrainingState.COMPLETED_FORWARD_PASS

    def _handle_analysis_wrong_answer(self) -> TrainingState:
        """Analyse why the system provided a wrong answer and could we do to mitigate it."""
        assert self.output.result.error_category, (
            "Logical flaw: error category is None."
        )
        assert self.output.result.answer, "Logical flaw: answer is None."
        assert self.context.qa_pair
        output_error_analyst = self.error_analyst.forward(
            chat_history=self.chat.to_string(),
            question=self.context.qa_pair.question,
            provided_answer=self.output.result.answer,
            correct_answer=self.context.qa_pair.answer,
        )

        if output_error_analyst.status == "success":
            self.output.result.error_category = (
                output_error_analyst.result.error_category
            )
            if self.output.result.error_category == "faulty_tool":
                self.output.result.assessment_details = (
                    output_error_analyst.result.error_analysis
                )
                self.output.result.function_name = (
                    output_error_analyst.result.function_name
                )
                return (
                    TrainingState.COMPLETED_FORWARD_PASS
                )  # TODO Update this state: handle the correction of faulty tools
            elif self.output.result.error_category == "missing_tool":
                self.output.result.need_new_function = True
                self.output.result.function_name = (
                    output_error_analyst.result.function_name
                )
                self.output.result.function_requirements = (
                    output_error_analyst.result.error_analysis
                )
                return TrainingState.TOOL_CREATION_NEEDED

            else:
                self.output.status = "success"
                self.output.result.error_analysis = (
                    output_error_analyst.result.error_analysis
                )
                return TrainingState.COMPLETED_FORWARD_PASS
        else:
            self.output.error_msg = output_error_analyst.error_msg
            self.output.status = "error"
            return TrainingState.ERROR

    def _handle_tool_creation_needed(self) -> TrainingState:
        """Create a new tool based on identified requirements."""
        tool_identifier_output = self.context.tool_identifier_output

        self.output.result.need_new_function = True
        self.output.result.function_name = tool_identifier_output.result.function_name
        self.output.result.function_requirements = (
            tool_identifier_output.result.function_requirements
        )

        assert (
            self.output.result.function_name
            and self.output.result.function_requirements
            and self.context.qa_pair
            and self.context.qa_pair.ifc_model_path
        ), "Error in the handling of tool_creation."

        # Try to generate a new tool
        output_tool_creator = self.tool_creator.forward(
            function_name=self.output.result.function_name,
            function_requirements=self.output.result.function_requirements,
            path_ifc_model=self.context.qa_pair.ifc_model_path,
        )

        if output_tool_creator.status == "success":
            assert output_tool_creator.result.function_implementation
            self.output.result.function_implementation = (
                output_tool_creator.result.function_implementation
            )

            new_tool_saved = save_new_tool(
                function_name=self.output.result.function_name,
                function_implementation=self.output.result.function_implementation,
            )
            assert new_tool_saved, "A new tool was created but could not be saved."

        return TrainingState.COMPLETED_FORWARD_PASS

    def _process_state(self) -> TrainingState:
        """Process current state and return next state."""
        if self.state == TrainingState.START_FORWARD_PASS:
            qa_pair = self.context.qa_pair
            assert qa_pair
            return self._initialize_processing(qa_pair)

        elif self.state == TrainingState.PROCESS_QUESTION:
            return self._handle_engine_processing()

        elif self.state == TrainingState.ENGINE_FAILED:
            return self._handle_engine_failure()

        elif self.state == TrainingState.ANSWER_VERIFICATION:
            return self._handle_answer_verification()

        elif self.state == TrainingState.VERIFICATION_COMPLETED:
            return self._handle_answer_verification_completed()

        elif self.state == TrainingState.NEW_TOOL_CREATED:
            return self._handle_new_function_ready()

        elif self.state == TrainingState.ANALYSIS_CORRECT_ANSWER:
            return self._handle_correct_answer()

        elif self.state == TrainingState.ANALYSIS_WRONG_ANSWER:
            return self._handle_analysis_wrong_answer()

        elif self.state == TrainingState.TOOL_CREATION_NEEDED:
            return self._handle_tool_creation_needed()

        else:
            return TrainingState.ERROR

    def _calculate_tokens(self) -> tuple[int, int]:
        """Calculate total input and output tokens from LM history."""
        total_input_tokens = 0
        total_output_tokens = 0

        if self.lm.history:
            for call in self.lm.history:
                usage = call.get("usage", {})
                total_input_tokens += usage.get("prompt_tokens", 0)
                total_output_tokens += usage.get("completion_tokens", 0)

        return total_input_tokens, total_output_tokens

    def _finalize_span_and_tracking(self, span, qa_pair: QA_Pair):
        """Finalize MLFlow span and tracking."""
        total_input_tokens, total_output_tokens = self._calculate_tokens()

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
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "chat": self.chat.model_dump_json(indent=2) or "",
            }
        )
        if not self.output.result.correct_answer:
            span.set_outputs(
                {
                    "error_category": self.output.result.error_category,
                    "error_analysis": self.output.result.error_analysis,
                }
            )

        span.set_attributes(self.output.result.model_dump())
        span.set_attribute("input_tokens", total_input_tokens)
        span.set_attribute("output_tokens", total_output_tokens)

        mlflow.update_current_trace(
            tags={
                "correct_answer": str(self.output.result.correct_answer or False),
                "answer": self.output.result.answer or "",
                "need_new_tool": str(self.output.result.need_new_function or False),
                "input_tokens": str(total_input_tokens),
                "output_tokens": str(total_output_tokens),
            }
        )

        if self.output.result.need_new_function:
            mlflow.set_tag(key="new_tool_created", value=True)

    def forward(self, qa_pair: QA_Pair) -> ModuleOutput:
        """Process a QA pair using the state machine."""
        # Initialize state machine
        self.state = TrainingState.START_FORWARD_PASS
        self.context.qa_pair = qa_pair

        with mlflow.start_span(
            name=f"question_id_{qa_pair.id}",
            span_type="QUESTION",
        ) as span:
            span.set_attribute("question_id", qa_pair.id)
            span.set_attribute("question", qa_pair.question)
            span.set_attribute("ground_truth", qa_pair.answer)
            self.context.span = span

            # State machine loop
            while self.state not in [
                TrainingState.COMPLETED_FORWARD_PASS,
                TrainingState.ERROR,
            ]:
                next_state = self._process_state()
                self.state = next_state

            # Finalize tracking and metrics
            self._finalize_span_and_tracking(span, qa_pair)

            return self.output


def main(start: int = 0, finish: int = -1):
    # setup mlflow
    mlflow.dspy.autolog()  # type: ignore
    train, dev = load_train_dev_split()

    # setup the logger
    logger = get_logger(
        name="Training run", log_level=AGENT_CONFIGS.training_module.log_level
    )

    training_module = TrainingModule()

    output = None
    for qa_pair in train[start:finish]:
        # Log info
        logger.info(f"Try to answer new question: {qa_pair.question}\n\n")
        output = training_module.forward(qa_pair=qa_pair)
        print(output)

    return output


if __name__ == "__main__":
    output = main(start=3, finish=4)
