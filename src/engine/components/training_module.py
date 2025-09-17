from enum import Enum
from typing import Optional, cast

import dspy
import mlflow

from src.config import AGENT_CONFIGS, PATH_COMPILED_MODEL
from src.config.agents import TrainingModuleConfig
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
    save_new_tool,
)


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
        config: Optional[TrainingModuleConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.training_module
        self.logger = get_logger(name="TrainingModule", log_level=self.config.log_level)

        # Use provided LLM or get from config
        self.lm = lm or self.config.llm.get_llm()
        self.chat = Chat()

        # Set-up the agents (using the default config for each agent)
        self.answer_verifier = AnswerVerifier()
        self.engine = IfcAnswerEngine()
        self.tool_creator = ToolCreator()
        self.error_analyst = ErrorAnalyst()
        self.tool_debugger = ToolDebugger()
        self.tool_merger = ToolsMerger()
        self.tool_optimizer = ToolOptimizer()

        # Use compile module if configured
        if self.config.load_optimized_module:
            self.engine.load(path=PATH_COMPILED_MODEL)

        # Set-up mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri(self.config.tracking_uri)
        mlflow.set_experiment(self.config.experiment_name)

        # State machine attributes
        self.state = TrainingState.START
        self.context = TrainingContext()

    def _initialize_system(self, qa_pair: QA_Pair) -> TrainingState:
        """Initialize processing state and setup."""
        self.context = TrainingContext()
        self.context.qa_pair = qa_pair
        self.context.span = None
        self.chat = Chat()

        # Initialize default output
        self.output = ModuleOutput()

        return TrainingState.ENGINE

    def _handle_engine(self) -> TrainingState:
        """Run the engine and determine next state."""
        assert self.context.qa_pair, (
            "Logical Error: self.context.qa_pair is None in _handle_engine"
        )
        qa_pair = self.context.qa_pair

        # Run the engine
        self.context.engine = cast(
            ModuleOutput,
            self.engine(
                question=qa_pair.question,
                path_ifc_model=qa_pair.ifc_model_path,
            ),
        )
        self.output.combine_lm_metrics(other_output=self.context.engine)

        self.chat = self.context.engine.chat
        assert len(self.chat.messages) > 0, (
            "Logical error: no messages in chat in _handle_engine"
        )

        if self.context.engine.status == "success":
            self.output.result.answer = self.context.engine.result.answer
            return TrainingState.ANSWER_VERIFICATION

        else:
            self.output.error_msg = self.context.engine.error_msg
            return TrainingState.ERROR

    def _handle_answer_verification(self) -> TrainingState:
        """Handle answer verification."""
        assert self.context.qa_pair and self.context.engine.result.answer, (
            "Logical error: self.context.qa_pair or self.context.engine.result.answer is None in _handle_answer_verification"
        )

        self.logger.info("IfcAnswerEngine could answer the question.")

        self.context.answer_verifier = cast(
            ModuleOutput,
            self.answer_verifier(
                question=self.context.qa_pair.question,
                first_answer=self.context.qa_pair.answer,
                second_answer=self.context.engine.result.answer,
            ),
        )
        self.output.combine_lm_metrics(self.context.answer_verifier)

        # Handle errors
        if self.context.answer_verifier.status == "error":
            self.output.error_msg = (
                f"There was an error with the AnswerVerifier. "
                f"Error message: {self.context.answer_verifier.error_msg or 'No error message provided'}"
            )
            return TrainingState.ERROR

        assert self.context.answer_verifier.result.similarity_score, (
            "Logical error: self.context.answer_verifier.result.similarity_score is None in _handle_answer_verification"
        )

        # Update output with verification results
        self.output.result.similarity_score = (
            self.context.answer_verifier.result.similarity_score
        )
        self.output.result.correct_answer = (
            self.context.answer_verifier.result.similarity_score
            >= self.config.similarity_threshold
        )

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
        self.context.tool_optimizer = cast(
            ModuleOutput,
            self.tool_optimizer(
                chat_history=self.chat.to_string(),
            ),
        )
        self.output.combine_lm_metrics(self.context.tool_optimizer)

        if self.context.tool_optimizer.status == "error":
            self.output.error_msg = self.context.tool_optimizer.error_msg
            return TrainingState.ERROR

        assert self.context.tool_optimizer.result.improvement, (
            "Logical error: self.context.tool_optimizer.result.improvement in _handle_correct_answer"
        )

        # Update the output with the ouput of the ToolOptimizer
        self.output.result.function_name = (
            self.context.tool_optimizer.result.function_name
        )

        self.output.result.function_requirements = (
            self.context.tool_optimizer.result.function_requirements
        )

        self.output.result.existing_tool_names = (
            self.context.tool_optimizer.result.existing_tool_names
        )

        if self.context.tool_optimizer.result.improvement == "create_new_tool":
            self.output.result.function_name = (
                self.context.tool_optimizer.result.function_name
            )
            self.output.result.function_requirements = (
                self.context.tool_optimizer.result.function_requirements
            )
            self.logger.info(
                f"Result assessment: new tool needed ({self.output.result.function_name}"
            )
            return TrainingState.TOOL_CREATION

        elif self.context.tool_optimizer.result.improvement == "merge_existing_tools":
            self.logger.info(
                f"Existing tools needs to be merged.\nExisting tools: {self.output.result.existing_tool_names}\nNew tool: {self.output.result.function_name}"
            )
            return TrainingState.TOOL_MERGER

        elif self.context.tool_optimizer.result.improvement == "update_existing_tool":
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
        assert self.output.result.answer and self.context.qa_pair, (
            "Logical error: self.output.result.answer or self.context.qa_pair is None in _handle_wrong_answer"
        )

        self.context.error_analyst = cast(
            ModuleOutput,
            self.error_analyst(
                chat_history=self.chat.to_string(),
                question=self.context.qa_pair.question,
                provided_answer=self.output.result.answer,
                correct_answer=self.context.qa_pair.answer,
            ),
        )
        self.output.combine_lm_metrics(self.context.error_analyst)

        if self.context.error_analyst.status == "success":
            self.output.result.error_category = (
                self.context.error_analyst.result.error_category
            )
            self.output.result.error_analysis = (
                self.context.error_analyst.result.error_analysis
            )
            self.output.result.assessment_details = (
                self.context.error_analyst.result.error_analysis
            )
            if self.output.result.error_category == "faulty_tool":
                self.output.result.function_name = (
                    self.context.error_analyst.result.function_name
                )
                return TrainingState.TOOL_CORRECTION
            elif self.output.result.error_category == "missing_tool":
                self.output.result.need_new_function = True
                self.output.result.function_name = (
                    self.context.error_analyst.result.function_name
                )
                self.output.result.function_requirements = (
                    self.context.error_analyst.result.error_analysis
                )
                return TrainingState.TOOL_CREATION

            else:
                self.output.result.error_analysis = (
                    self.context.error_analyst.result.error_analysis
                )
                return TrainingState.END
        else:
            self.output.error_msg = self.context.error_analyst.error_msg
            return TrainingState.ERROR

    def _handle_tool_creation(self) -> TrainingState:
        """Create a new tool based on identified requirements."""

        self.output.result.need_new_function = True

        # Ensure all needed information exist
        assert (
            self.output.result.function_name
            and self.output.result.function_requirements
            and self.context.qa_pair
            and self.context.qa_pair.ifc_model_path
        ), "Logical error: missing input in _handle_tool_creation"

        # Call the ToolCreator
        self.context.tool_creator = cast(
            ModuleOutput,
            self.tool_creator(
                function_name=self.output.result.function_name,
                function_requirements=self.output.result.function_requirements,
                path_ifc_model=self.context.qa_pair.ifc_model_path,
            ),
        )
        self.output.combine_lm_metrics(self.context.tool_creator)

        if self.context.tool_creator.status == "success":
            self.logger.info("ToolCreator could create the new tool.")
            assert self.context.tool_creator.result.function_implementation, (
                "Logical error: self.context.tool_creator.result.function_implementation is None in _handle_tool_creation"
            )

            self.output.result.new_tool_created = True
            self.output.result.function_implementation = (
                self.context.tool_creator.result.function_implementation
            )

            self.output.result.new_function_saved = save_new_tool(
                function_name=self.output.result.function_name,
                function_implementation=self.output.result.function_implementation,
            )

            if not self.output.result.new_function_saved:
                self.output.error_msg = f"New tool named: {self.output.result.function_name} could not be saved"
                return TrainingState.ERROR
            else:
                self.output.tools_metrics.nb_tools_created += 1
                return TrainingState.END
        else:
            self.output.error_msg = f"ToolCreator could not create a new tool.\nError msg:\n{self.context.tool_creator.error_msg}"
            return TrainingState.ERROR

    def _handle_tool_correction(self) -> TrainingState:
        """Correct the faulty tool according the the assessment."""
        assert (
            self.output.result.function_name
            and self.output.result.function_requirements
            and self.context.qa_pair
            and self.context.qa_pair.ifc_model_path
        ), (
            "Logical error in _handle_tool_creation: Tool correction required, but assessment or function name missing."
        )
        try:
            extracted_fn_code = get_function_code(
                function_name=self.output.result.function_name
            )

            assert extracted_fn_code, (
                "Logical error: faulty_function_implementation is missing in _handle_tool_correction"
            )

            if extracted_fn_code.is_err():
                self.output.error_msg = extracted_fn_code.unwrap_err()
                return TrainingState.ERROR
            else:
                faulty_function_implementation = extracted_fn_code.unwrap()

            self.context.tool_debugger = cast(
                ModuleOutput,
                self.tool_debugger(
                    function_name=self.output.result.function_name,
                    faulty_function_implementation=faulty_function_implementation,
                    initial_assessment=self.output.result.assessment_details,
                    path_ifc_model=self.context.qa_pair.ifc_model_path,
                ),
            )
            self.output.combine_lm_metrics(self.context.tool_debugger)

            if self.context.tool_debugger.status == "error":
                self.output.error_msg = self.context.tool_debugger.error_msg
                return TrainingState.ERROR

            else:
                assert self.context.tool_debugger.result.function_implementation, (
                    "Logical error: self.context.tool_debugger.result.function_implementation"
                )
                corrected_tool_saved = save_new_tool(
                    function_name=self.output.result.function_name,
                    function_implementation=self.context.tool_debugger.result.function_implementation,
                )
                if corrected_tool_saved:
                    self.output.tools_metrics.nb_tools_updated += 1
                    self.output.result.function_implementation = (
                        self.context.tool_debugger.result.function_implementation
                    )
                    self.output.result.existing_tool_updated = True
                    return TrainingState.END
                else:
                    self.output.error_msg = f"Updated tool: {self.output.result.function_name} could not be saved"
                    return TrainingState.ERROR

        except FileNotFoundError:
            self.output.error_msg = f"Could not find the file {self.output.result.function_name} to correct it."
            return TrainingState.ERROR

    def _handle_tools_merger(self) -> TrainingState:
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

        if source_code_first_function.is_err():
            self.output.error_msg = f"Error when trying to load the source code of the first function: {source_code_first_function}"
            return TrainingState.ERROR

        elif source_code_second_function.is_err():
            self.output.error_msg = f"Error when trying to load the source code of the second function: {source_code_second_function}"
            return TrainingState.ERROR

        else:
            self.context.tool_merger = cast(
                ModuleOutput,
                self.tool_merger(
                    function_name=self.output.result.function_name,
                    function_requirements=self.output.result.function_requirements,
                    path_ifc_model=self.context.qa_pair.ifc_model_path,
                    source_code_first_function=source_code_first_function.unwrap(),
                    source_code_second_function=source_code_second_function.unwrap(),
                ),
            )
            self.output.combine_lm_metrics(self.context.tool_merger)

            if self.context.tool_merger.status == "success":
                self.output.result.new_tool_created = True
                self.output.result.function_implementation = (
                    self.context.tool_merger.result.function_implementation
                )
                self.output.result.existing_tool_updated = True
                assert self.output.result.function_implementation, (
                    "Logical Error: self.output.result.function_implementation is missing in _handle_tool_merger although status is 'success'"
                )
                self.output.result.new_function_saved = save_new_tool(
                    function_name=self.output.result.function_name,
                    function_implementation=self.output.result.function_implementation,
                )
                self.output.result.old_functions_deleted = delete_tools(
                    first_function_name=self.output.result.existing_tool_names[0],
                    second_function_name=self.output.result.existing_tool_names[1],
                )
                if (
                    self.output.result.new_function_saved
                    and self.output.result.old_functions_deleted
                ):
                    self.output.tools_metrics.nb_tools_merged += 1
                    return TrainingState.END
                else:
                    self.output.error_msg = "Either new tool could not be saved of existing tools could not be deleted."
                    return TrainingState.ERROR
            else:
                self.output.error_msg = self.context.tool_merger.error_msg
                return TrainingState.ERROR

    def _process_state(self) -> TrainingState:
        """Process current state and return next state."""
        if self.state == TrainingState.START:
            qa_pair = self.context.qa_pair
            assert qa_pair, "Logical error: qa_pair is missing in _process_state"
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
            return self._handle_tools_merger()

        else:
            return TrainingState.ERROR

    def forward(
        self,
        qa_pair: QA_Pair,
    ) -> ModuleOutput:
        """Process a QA pair using the state machine. Return a ModuleOutput."""

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
                self.state = TrainingState.ERROR

            # handle finish scenarii
            if self.state == TrainingState.END:
                self.output.status = "success"
            elif self.state == TrainingState.ERROR:
                self.logger.error(self.output.error_msg)

        return self.output


if __name__ == "__main__":

    def main(qa_pair: QA_Pair):
        # setup the logger
        logger = get_logger(
            name="Training run", log_level=AGENT_CONFIGS.training_module.log_level
        )

        training_module = TrainingModule()

        logger.info("Starting the TrainingModule")

        output = cast(
            ModuleOutput,
            training_module(
                qa_pair=qa_pair,
            ),
        )
        return output

    from src.experiment.datasets import load_train_dev_split

    devset, trainset = load_train_dev_split()

    output = main(trainset[0])
    print(f"Output:\n{output.model_dump()}")
    print("\n---\n")
