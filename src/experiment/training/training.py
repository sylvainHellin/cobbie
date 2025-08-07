from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional

import dspy
import mlflow
from pydantic import BaseModel

from src.config import AGENT_CONFIGS, OPTIMIZED_MODEL_PATH
from src.engine import (
    AnswerVerifier,
    ErrorAnalyst,
    IfcAnswerEngine,
    ToolCreator,
    ToolDebugger,
    ToolOptimizer,
    ToolsMerger,
)
from src.engine.schemas import (
    Chat,
    ModuleOutput,
    QA_Pair,
    TrainingContext,
)
from src.engine.util import (
    delete_tools,
    get_function_code,
    get_logger,
    get_usage_openrouter,
    save_new_tool,
)
from src.experiment.evaluation.evaluation import evaluate
from src.experiment.datasets import load_train_dev_split


class ToolsMetrics(BaseModel):
    nb_tools_created: float = 0
    nb_tools_updated: float = 0
    nb_tools_merged: float = 0
    cost: float = 0


class TrainingState(Enum):
    """States for the training module state machine."""

    START = "Start the agentic workflow"
    ENGINE = "IfcAnswerEngine"
    ANSWER_VERIFICATION = "AnswerVerifier"
    CORRECT_ANSWER = "ToolOptimizer"
    WRONG_ANSWER = "ErrorAnalyst"
    TOOL_CREATION = "ToolCreator"
    TOOL_CORRECTION = "ToolDebugger"
    TOOL_MERGER = "ToolMerger"
    END = "Agentic workflow completed"
    ERROR = "error"


class TrainingModule(dspy.Module):
    def __init__(
        self,
        config=None,
        lm: Optional[dspy.LM] = None,  # Optional override
        load_compiled: bool = True,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.training_module
        self.logger = get_logger(name="Training", log_level=self.config.log_level)
        self.evaluate = self.config.evaluate
        self.tools_metrics = ToolsMetrics()

        # Use provided LLM or get from config
        self.lm = lm or self.config.llm.get_llm()
        self.chat = Chat()
        self.current_usage = get_usage_openrouter()
        self.previous_usage = self.current_usage

        # Set-up the agents (using the default config for each agent)
        self.answer_verifier = AnswerVerifier()
        self.engine = IfcAnswerEngine()
        if load_compiled:
            self.engine.load(path=OPTIMIZED_MODEL_PATH)
        self.tool_creator = ToolCreator()
        self.error_analyst = ErrorAnalyst()
        self.tool_debugger = ToolDebugger()
        self.tool_merger = ToolsMerger()
        self.tool_optimizer = ToolOptimizer()

        # Set-up mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri(self.config.tracking_uri)
        mlflow.set_experiment(self.config.experiment_name)
        mlflow.start_run(run_name=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))

        # State machine attributes
        self.state = TrainingState.START
        self.context = TrainingContext()  # Typed context to pass data between states
        self.outputs: List[ModuleOutput] = []

    def _initialize_system(self, qa_pair: QA_Pair) -> TrainingState:
        """Initialize processing state and setup."""
        self.context = TrainingContext()
        self.context.qa_pair = qa_pair
        self.context.span = None
        self.chat = Chat()
        self.previous_usage = self.current_usage

        # Initialize default output
        self.output = ModuleOutput(
            status="error",
            error_msg="Default error message from initialization of TrainingModule.",
        )

        # Setup DSPy
        dspy.configure(lm=self.lm)
        self.lm.history.clear()

        return TrainingState.ENGINE

    def _handle_engine(self) -> TrainingState:
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
            return TrainingState.ANSWER_VERIFICATION
        else:
            self.output.status = "error"
            self.output.error_msg = output_engine.error_msg
            return TrainingState.ERROR

    def _handle_answer_verification(self) -> TrainingState:
        """Handle answer verification."""
        qa_pair = self.context.qa_pair
        assert qa_pair, "Error: QA pair is not defined."
        self.context.engine_output = self.context.engine_output

        self.logger.info("IfcAnswerEngine could answer the question.")
        self.logger.debug(f"Answer: \n{self.context.engine_output.result.answer}")
        self.logger.debug(f"Ground Truth: \n{qa_pair.answer}")

        # Verify if answer is correct
        assert self.context.engine_output.result.answer, (
            "Error: Answer in Engine Output is None. disn"
        )
        self.context.verifier_output = self.answer_verifier.forward(
            question=qa_pair.question,
            first_answer=qa_pair.answer,
            second_answer=self.context.engine_output.result.answer,
        )

        # Handle errors
        if self.context.verifier_output.status == "error":
            self.output.error_msg = (
                f"There was an error with the AnswerVerifier. "
                f"Error message: {self.context.verifier_output.error_msg or 'No error message provided'}"
            )
            self.logger.error(self.output.error_msg)
            return TrainingState.ERROR

        # Define next step depending on eval result
        self.context.engine_output = self.context.engine_output

        assert self.context.verifier_output.result.similarity_score is not None, (
            "Something is off: the status of AnswerVerifier is 'success', but the `similarity_score` field is None."
        )

        # Update output with verification results
        self.output.error_msg = None
        self.output.status = "success"
        self.output.result.similarity_score = (
            self.context.verifier_output.result.similarity_score
        )
        self.output.result.correct_answer = (
            self.context.verifier_output.result.similarity_score
            >= self.config.similarity_threshold
        )
        self.output.result.answer = self.context.engine_output.result.answer

        self.logger.info(
            f"AnswerVerifier could check the answer. Correct answer: {self.output.result.correct_answer}"
        )

        # Define the next step depending on whether the answer is correct or not.
        if self.output.result.correct_answer:
            return TrainingState.CORRECT_ANSWER
        else:
            return TrainingState.WRONG_ANSWER

    def _handle_correct_answer(self) -> TrainingState:
        """Try to identify optimization potential for existing tools."""
        self.context.tool_optimizer_output = self.tool_optimizer.forward(
            chat_history=self.chat.to_string()
        )
        if self.context.tool_optimizer_output.status == "error":
            self.output.error_msg = self.context.tool_optimizer_output.error_msg
            self.logger.error(self.output.error_msg)
            return TrainingState.ERROR

        assert self.context.tool_optimizer_output.result.improvement, (
            "Logical Error: the status of ToolOptimizer is success, but the improvement field is None."
        )

        # Update the output with the ouput of the ToolOptimizer
        self.output.result.function_name = (
            self.context.tool_optimizer_output.result.function_name
        )

        self.output.result.function_requirements = (
            self.context.tool_optimizer_output.result.function_requirements
        )

        self.output.result.existing_tool_names = (
            self.context.tool_optimizer_output.result.existing_tool_names
        )

        if self.context.tool_optimizer_output.result.improvement == "create_new_tool":
            self.output.result.function_name = (
                self.context.tool_optimizer_output.result.function_name
            )
            self.output.result.function_requirements = (
                self.context.tool_optimizer_output.result.function_requirements
            )
            self.logger.info(
                f"Result assessment: new tool needed ({self.output.result.function_name}"
            )
            return TrainingState.TOOL_CREATION

        elif (
            self.context.tool_optimizer_output.result.improvement
            == "merge_existing_tools"
        ):
            self.logger.info(
                f"Existing tools needs to be merged.\nExisting tools: {self.output.result.existing_tool_names}\nNew tool: {self.output.result.function_name}"
            )
            return TrainingState.TOOL_MERGER

        elif (
            self.context.tool_optimizer_output.result.improvement
            == "update_existing_tool"
        ):
            assert self.output.result.existing_tool_names, (
                "Result of assessment of ToolOptimizer is `update_existing_tool`, but the field `existing_tool_name` is None."
            )
            self.output.result.function_name = self.output.result.existing_tool_names[0]
            self.logger.info(
                f"Existing tool needs to be updated.\nExisting tool: {self.output.result.existing_tool_names}."
            )
            return TrainingState.TOOL_CORRECTION
        else:
            self.logger.info("No improvement needed.")
            return TrainingState.END

    def _handle_wrong_answer(self) -> TrainingState:
        """Analyse why the system provided a wrong answer and could we do to mitigate it."""
        assert self.output.result.answer, "Logical flaw: answer is None."
        assert self.context.qa_pair, "Logical flaw: no QA pair for analysis."

        error_analyst_output = self.error_analyst.forward(
            chat_history=self.chat.to_string(),
            question=self.context.qa_pair.question,
            provided_answer=self.output.result.answer,
            correct_answer=self.context.qa_pair.answer,
        )
        self.context.error_analyst_output = error_analyst_output

        if error_analyst_output.status == "success":
            self.output.result.error_category = (
                error_analyst_output.result.error_category
            )
            self.output.result.error_analysis = (
                error_analyst_output.result.error_analysis
            )
            self.output.result.assessment_details = (
                error_analyst_output.result.error_analysis
            )
            if self.output.result.error_category == "faulty_tool":
                self.output.result.function_name = (
                    error_analyst_output.result.function_name
                )
                return TrainingState.TOOL_CORRECTION
            elif self.output.result.error_category == "missing_tool":
                self.output.result.need_new_function = True
                self.output.result.function_name = (
                    error_analyst_output.result.function_name
                )
                self.output.result.function_requirements = (
                    error_analyst_output.result.error_analysis
                )
                return TrainingState.TOOL_CREATION

            else:
                self.output.status = "success"
                self.output.result.error_analysis = (
                    error_analyst_output.result.error_analysis
                )
                return TrainingState.END
        else:
            self.output.error_msg = error_analyst_output.error_msg
            self.output.status = "error"
            return TrainingState.ERROR

    def _handle_tool_creation(self) -> TrainingState:
        """Create a new tool based on identified requirements."""

        self.output.result.need_new_function = True

        # Ensure all needed information exist
        assert self.output.result.function_name, "ERROR: function name is missing."
        assert self.output.result.function_requirements, (
            "Error: function requirements is missing."
        )
        assert self.context.qa_pair, "Error: missing qa_pair"
        assert self.context.qa_pair.ifc_model_path, "Error: ifc_model_path is missing."

        # Try to generate a new tool
        output_tool_creator = self.tool_creator.forward(
            function_name=self.output.result.function_name,
            function_requirements=self.output.result.function_requirements,
            path_ifc_model=self.context.qa_pair.ifc_model_path,
        )

        if output_tool_creator.status == "success":
            assert output_tool_creator.result.function_implementation

            self.output.result.new_tool_created = True
            self.output.result.function_implementation = (
                output_tool_creator.result.function_implementation
            )

            new_tool_saved = save_new_tool(
                function_name=self.output.result.function_name,
                function_implementation=self.output.result.function_implementation,
            )

            if not new_tool_saved:
                self.output.error_msg = f"New tool named: {self.output.result.function_name} could not be saved"
                self.output.status = "error"
                return TrainingState.ERROR
            else:
                self.tools_metrics.nb_tools_created += 1
                return TrainingState.END
        else:
            self.output.status = "error"
            self.output.error_msg = output_tool_creator.error_msg
            self.logger.error(
                f"ToolCreator could not create a new tool. Error msg: \n{self.output.error_msg}"
            )
            return TrainingState.ERROR

    def _handle_tool_correction(self) -> TrainingState:
        """Correct the faulty tool according the the assessment."""
        assert (
            self.output.result.function_name
            and self.output.result.assessment_details
            and self.context.qa_pair
            and self.context.qa_pair.ifc_model_path
        ), (
            "Logical error: Tool correction required, but assessment or function name missing."
        )
        try:
            faulty_function_implementation = get_function_code(
                function_name=self.output.result.function_name
            )

            assert faulty_function_implementation, (
                "Error: could not load the source code of the faulty tool."
            )

            self.context.tool_debugger_output = self.tool_debugger.forward(
                function_name=self.output.result.function_name,
                faulty_function_implementation=faulty_function_implementation,
                initial_assessment=self.output.result.assessment_details,
                path_ifc_model=self.context.qa_pair.ifc_model_path,
            )

            if self.context.tool_debugger_output.status == "error":
                self.output.error_msg = self.context.tool_debugger_output.error_msg
                return TrainingState.ERROR
            else:
                assert (
                    self.context.tool_debugger_output.result.function_implementation
                ), (
                    "Logical flaw: ToolDebugger status is `success` but the function_implementation is empty."
                )
                corrected_tool_saved = save_new_tool(
                    function_name=self.output.result.function_name,
                    function_implementation=self.context.tool_debugger_output.result.function_implementation,
                )
                assert corrected_tool_saved, (
                    "CRITICAL ERROR: the corrected tool could not be saved"
                )
                self.output.result.function_implementation = (
                    self.context.tool_debugger_output.result.function_implementation
                )
                self.output.result.existing_tool_updated = True
                self.output.status = "success"
                self.tools_metrics.nb_tools_updated += 1
                return TrainingState.END

        except FileNotFoundError:
            self.output.error_msg = f"Could not find the file {self.output.result.function_name} to correct it."
            self.output.status = "error"
            self.logger.error(self.output.error_msg)
            return TrainingState.ERROR

    def handle_tools_merger(self) -> TrainingState:
        """Merge two existing tools if required"""
        assert (
            self.output.result.existing_tool_names
            and self.output.result.function_name
            and self.output.result.function_requirements
            and self.context.qa_pair
            and self.context.qa_pair.ifc_model_path
        ), "Logical Error in _handle_tool_merger: missing information."

        source_code_first_function = get_function_code(
            function_name=self.output.result.existing_tool_names[0]
        )

        source_code_second_function = get_function_code(
            function_name=self.output.result.existing_tool_names[1]
        )

        if source_code_first_function and source_code_second_function:
            self.context.tool_merger_output = self.tool_merger.forward(
                function_name=self.output.result.function_name,
                function_requirements=self.output.result.function_requirements,
                path_ifc_model=self.context.qa_pair.ifc_model_path,
                source_code_first_function=source_code_first_function,
                source_code_second_function=source_code_second_function,
            )
            self.context.tool_merger_output = self.context.tool_merger_output
        else:
            self.output.status = "error"
            self.output.error_msg = f"Could not retrieve the source codes for functions: {self.output.result.existing_tool_names}."
            self.logger.error(self.output.error_msg)

        if self.context.tool_merger_output.status == "success":
            self.output.result.new_tool_created = True
            self.output.result.function_implementation = (
                self.context.tool_merger_output.result.function_implementation
            )
            self.output.result.existing_tool_updated = True
            assert self.output.result.function_implementation, (
                "Logical Error: status of ToolMerger is 'success', but function_implementation is empty."
            )
            new_tool_saved = save_new_tool(
                function_name=self.output.result.function_name,
                function_implementation=self.output.result.function_implementation,
            )
            old_tools_deleted = delete_tools(
                first_function_name=self.output.result.existing_tool_names[0],
                second_function_name=self.output.result.existing_tool_names[1],
            )
            if new_tool_saved and old_tools_deleted:
                self.output.status = "success"
                self.tools_metrics.nb_tools_merged += 1
                return TrainingState.END
            else:
                self.output.error_msg = "Either new tool could not be saved of existing tools could not be deleted."
                self.logger.error(self.output.error_msg)
                return TrainingState.ERROR
        else:
            return TrainingState.ERROR

    def _process_state(self) -> TrainingState:
        """Process current state and return next state."""
        if self.state == TrainingState.START:
            qa_pair = self.context.qa_pair
            assert qa_pair
            return self._initialize_system(qa_pair)

        elif self.state == TrainingState.ENGINE:
            return self._handle_engine()

        elif self.state == TrainingState.ANSWER_VERIFICATION:
            return self._handle_answer_verification()

        elif self.state == TrainingState.CORRECT_ANSWER:
            return self._handle_correct_answer()

        elif self.state == TrainingState.WRONG_ANSWER:
            return self._handle_wrong_answer()

        elif self.state == TrainingState.TOOL_CREATION:
            return self._handle_tool_creation()

        elif self.state == TrainingState.TOOL_CORRECTION:
            return self._handle_tool_correction()

        elif self.state == TrainingState.TOOL_MERGER:
            return self.handle_tools_merger()

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
        self.current_usage = get_usage_openrouter()
        cost_of_span = self.current_usage - self.previous_usage

        mlflow.update_current_trace(
            tags={
                "correct_answer": str(self.output.result.correct_answer),
                "similarity_score": str(self.output.result.similarity_score),
                "error_category": str(self.output.result.error_category or None),
                "error_analysis": str(self.output.result.error_analysis or None),
                "input_tokens": str(total_input_tokens),
                "output_tokens": str(total_output_tokens),
                "need_new_tool": str(self.output.result.need_new_function or False),
                "new_tool_created": str(self.output.result.new_tool_created or False),
                "existing_tool_updated": str(
                    self.output.result.existing_tool_updated or False
                ),
                "tools_merged": str(self.output.result.tools_merged),
                "cost": str(cost_of_span),
            },
            state="OK" if self.output.status == "success" else "ERROR",
            request_preview=qa_pair.question,
            response_preview=self.output.result.answer or "",
        )
        mlflow.log_metrics(metrics=self.tools_metrics.model_dump())
        self.tools_metrics.cost += cost_of_span

    def _evaluation(
        self,
        mode: Literal["before", "after"],
        devset: List[QA_Pair],
    ):
        if self.evaluate:
            with mlflow.start_span(
                name="start_evaluation",
                span_type="CHAIN",
            ):
                # run eval
                eval = evaluate(
                    llm=self.lm,
                    start_run=False,
                    dataset=devset,
                )
            # Log the metrics
            mlflow.log_metrics(
                metrics={
                    f"mean_accuracy_{mode}_training": eval.mean_accuracy(),
                    f"nb_errors_{mode}_training": len(eval.errors),
                    f"mean_duration_{mode}_training": eval.mean_duration(),
                },
            )
            mlflow.log_param(key="model", value=self.lm.model)

        return

    def forward(
        self,
        devset: List[QA_Pair],
        trainset: List[QA_Pair],
    ) -> List[ModuleOutput]:
        """Process a QA pair using the state machine."""

        # Evaluate the accuracy of the engine before the training round.
        self._evaluation(mode="before", devset=devset)

        # Go through each examples in the training set
        for qa_pair in trainset:
            # Initialize state machine
            self.state = TrainingState.START
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
                try:
                    while self.state not in [
                        TrainingState.END,
                        TrainingState.ERROR,
                    ]:
                        next_state = self._process_state()
                        self.state = next_state
                except Exception as e:
                    self.output.error_msg = f"An error occured during the Training run for question_id: {qa_pair.id}.\nError:\n{e}"
                    self.logger.error(self.output.error_msg)
                    self.output.status = "error"

                # Finalize tracking and metrics
                self._finalize_span_and_tracking(span, qa_pair)

                # add the output to the final outputs
                self.outputs.append(self.output)

        # Evaluate the accuracy of the engine after the training round.
        self._evaluation(mode="after", devset=devset)
        mlflow.log_metric(key="cost", value=self.tools_metrics.cost)

        return self.outputs


def main(
    trainset: List[QA_Pair],
    devset: List[QA_Pair],
):
    # setup mlflow
    mlflow.dspy.autolog()  # type: ignore

    # setup the logger
    logger = get_logger(
        name="Training run", log_level=AGENT_CONFIGS.training_module.log_level
    )

    training_module = TrainingModule()

    logger.info("Starting the TrainingModule")

    output = training_module.forward(
        devset=devset,
        trainset=trainset,
    )

    return output


if __name__ == "__main__":
    devset, trainset = load_train_dev_split()

    outputs = main(devset=devset[10:20], trainset=trainset[15:35])
