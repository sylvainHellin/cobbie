"""
The orchestration of the multi-agent system that generates, updates and prunes the tools
for extracting information from BIM models. These tools are then used by Cobbie at inference time.
"""

import argparse
import os
import time
from datetime import datetime
from enum import Enum, auto
from typing import Callable, Dict, List, Literal, Optional, Tuple, cast

import mlflow
from baml_py.baml_py import Collector
from pydantic import BaseModel, ConfigDict

from baml_client.types import (
    AnswerEvaluationResult,
    FaultyToolAnalysis,
    FinalAnswer,
    HelperFunctionAssessment,
    NewHelperFunction,
    NewToolAnalysis,
    UpdatedHelperFunction,
)
from src.agents import (
    assess_helper_function,
    cobbie,
    create_helper_function,
    debug_helper_function,
    identify_faulty_tool,
    identify_helper_function,
    verify_answer,
)
from src.config import LOG_LEVEL, ROOT_PATH
from src.engine.util import (
    generate_tools_docs,
    get_created_tools,
    get_function_code,
    get_logger,
    save_new_tool,
)
from src.experiment.datasets import load_train_dev_split
from src.experiment.db.models import IfcBench

# Initialize logger
_logger = get_logger(name="TrainingPhase", log_level=LOG_LEVEL)


# Enum to implement the state machine pattern for orchestrating the control flow of the training phase
class TrainingState(Enum):
    START = auto()
    RUN_COBBIE = auto()
    VERIFY_ANSWER = auto()

    # Path A: Correct answer
    IDENTIFY_NEW_TOOL = auto()
    CREATE_NEW_TOOL = auto()

    # Path B: Wrong answer
    IDENTIFY_FAULTY_TOOL = auto()
    DEBUG_FAULTY_TOOL = auto()

    # Tool testing (both paths)
    TEST_TOOL_WITH_COBBIE = auto()
    ASSESS_TOOL_USAGE = auto()
    DECIDE_TOOL_FATE = auto()

    # Terminal states
    END = auto()
    ERROR = auto()


# Object to handle the context added by each agent for each qa_pair processing
class Context(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Core data
    qa_pair: IfcBench
    tools: Dict[str, Callable] = {}

    # Cobbie agent results
    cobbie_result: Optional[FinalAnswer] = None
    cobbie_collector: Optional[Collector] = None
    cobbie_history: str = ""
    cobbie_duration: float = 0.0

    # Answer verifier results
    verify_result: Optional[AnswerEvaluationResult] = None
    verify_collector: Optional[Collector] = None
    verify_duration: float = 0.0

    # Identify helper function results (Path A)
    identify_tool_result: Optional[NewToolAnalysis] = None
    identify_tool_collector: Optional[Collector] = None
    identify_tool_duration: float = 0.0

    # Create helper function results (Path A)
    create_tool_result: Optional[NewHelperFunction] = None
    create_tool_collector: Optional[Collector] = None
    create_tool_history: str = ""
    create_tool_duration: float = 0.0

    # Identify faulty tool results (Path B)
    identify_faulty_result: Optional[FaultyToolAnalysis] = None
    identify_faulty_collector: Optional[Collector] = None
    identify_faulty_duration: float = 0.0

    # Debug helper function results (Path B)
    debug_tool_result: Optional[UpdatedHelperFunction] = None
    debug_tool_collector: Optional[Collector] = None
    debug_tool_history: str = ""
    debug_tool_duration: float = 0.0

    # Tool testing results (both paths)
    test_cobbie_result: Optional[FinalAnswer] = None
    test_cobbie_collector: Optional[Collector] = None
    test_cobbie_history: str = ""
    test_cobbie_duration: float = 0.0
    test_verify_result: Optional[AnswerEvaluationResult] = None
    test_verify_collector: Optional[Collector] = None
    test_verify_duration: float = 0.0

    # Tool assessment results (both paths)
    tool_assessment: Optional[HelperFunctionAssessment] = None
    tool_assessment_collector: Optional[Collector] = None
    tool_assessment_duration: float = 0.0

    # Tracking metadata
    error_message: Optional[str] = None
    tool_created: bool = False
    tool_updated: bool = False
    tool_saved: bool = False
    tool_name: Optional[str] = None
    path_taken: Optional[str] = None  # "correct" or "wrong" or "abstained"


# ============================================================================
# Helper Functions
# ============================================================================


def extract_token_metrics(collector: Optional[Collector]) -> Tuple[int, int, int]:
    """
    Safely extract token metrics from collector.

    Args:
        collector: BAML Collector object with token usage info

    Returns:
        Tuple of (input_tokens, output_tokens, total_tokens)
    """
    if not collector:
        return 0, 0, 0

    try:
        if hasattr(collector, "usage") and collector.usage:
            usage = collector.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            total_tokens = input_tokens + output_tokens
            return input_tokens, output_tokens, total_tokens
    except Exception as e:
        _logger.warning(f"Error extracting token usage: {e}")

    return 0, 0, 0


def calculate_aggregate_metrics(qa_results: List[dict]) -> dict:
    """
    Calculate aggregate metrics across all QA pairs.

    Args:
        qa_results: List of dictionaries with per-QA metrics

    Returns:
        Dictionary with aggregate metrics
    """
    total_count = len(qa_results)
    if total_count == 0:
        return {}

    correct_count = sum(1 for r in qa_results if r.get("classification") == "correct")
    wrong_count = sum(1 for r in qa_results if r.get("classification") == "wrong")
    abstained_count = sum(
        1 for r in qa_results if r.get("classification") == "abstained"
    )

    tools_created = sum(1 for r in qa_results if r.get("tool_created"))
    tools_updated = sum(1 for r in qa_results if r.get("tool_updated"))
    tools_saved = sum(1 for r in qa_results if r.get("tool_saved"))  # NEW
    tools_tested = sum(1 for r in qa_results if r.get("tool_was_tested"))  # NEW
    tools_kept = sum(
        1 for r in qa_results if r.get("tool_recommendation") == "keep_tool"
    )  # NEW
    tools_discarded = sum(
        1 for r in qa_results if r.get("tool_recommendation") == "discard_tool"
    )  # NEW
    errors = sum(1 for r in qa_results if r.get("error"))

    total_tokens = sum(r.get("total_tokens", 0) for r in qa_results)
    total_duration = sum(r.get("total_duration", 0) for r in qa_results)

    return {
        "total_qa_pairs": total_count,
        "correct_answers": correct_count,
        "wrong_answers": wrong_count,
        "abstained_answers": abstained_count,
        "tools_created": tools_created,
        "tools_updated": tools_updated,
        "tools_saved": tools_saved,  # NEW
        "tools_tested": tools_tested,  # NEW
        "tools_kept": tools_kept,  # NEW
        "tools_discarded": tools_discarded,  # NEW
        "errors": errors,
        "success_rate": correct_count / total_count if total_count > 0 else 0,
        "tool_creation_rate": tools_created / correct_count if correct_count > 0 else 0,
        "tool_update_rate": tools_updated / wrong_count if wrong_count > 0 else 0,
        "tool_save_rate": tools_saved / tools_tested if tools_tested > 0 else 0,  # NEW
        "tool_keep_rate": tools_kept / tools_tested if tools_tested > 0 else 0,  # NEW
        "avg_tokens_per_qa": total_tokens / total_count if total_count > 0 else 0,
        "avg_duration_per_qa": total_duration / total_count if total_count > 0 else 0,
        "total_tokens": total_tokens,
        "total_duration": total_duration,
    }


def log_qa_metrics(context: Context) -> dict:
    """
    Extract and log metrics for a single QA pair to MLflow.

    Args:
        context: Context object with all agent results

    Returns:
        Dictionary with metrics for aggregate calculation
    """
    # Extract token metrics from all collectors
    cobbie_input, cobbie_output, cobbie_total = extract_token_metrics(
        context.cobbie_collector
    )
    verify_input, verify_output, verify_total = extract_token_metrics(
        context.verify_collector
    )
    identify_tool_input, identify_tool_output, identify_tool_total = (
        extract_token_metrics(context.identify_tool_collector)
    )
    create_tool_input, create_tool_output, create_tool_total = extract_token_metrics(
        context.create_tool_collector
    )
    identify_faulty_input, identify_faulty_output, identify_faulty_total = (
        extract_token_metrics(context.identify_faulty_collector)
    )
    debug_tool_input, debug_tool_output, debug_tool_total = extract_token_metrics(
        context.debug_tool_collector
    )

    # NEW: Extract test and assessment metrics
    test_cobbie_input, test_cobbie_output, test_cobbie_total = extract_token_metrics(
        context.test_cobbie_collector
    )
    test_verify_input, test_verify_output, test_verify_total = extract_token_metrics(
        context.test_verify_collector
    )
    tool_assess_input, tool_assess_output, tool_assess_total = extract_token_metrics(
        context.tool_assessment_collector
    )

    # Calculate totals (including new components)
    total_tokens = (
        cobbie_total
        + verify_total
        + identify_tool_total
        + create_tool_total
        + identify_faulty_total
        + debug_tool_total
        + test_cobbie_total
        + test_verify_total
        + tool_assess_total
    )
    total_duration = (
        context.cobbie_duration
        + context.verify_duration
        + context.identify_tool_duration
        + context.create_tool_duration
        + context.identify_faulty_duration
        + context.debug_tool_duration
        + context.test_cobbie_duration
        + context.test_verify_duration
        + context.tool_assessment_duration
    )

    # Get classification
    classification = (
        context.verify_result.classification if context.verify_result else "unknown"
    )

    # Build metrics dictionary
    metrics = {
        "cobbie_duration": context.cobbie_duration,
        "cobbie_input_tokens": cobbie_input,
        "cobbie_output_tokens": cobbie_output,
        "cobbie_total_tokens": cobbie_total,
        "verify_duration": context.verify_duration,
        "verify_input_tokens": verify_input,
        "verify_output_tokens": verify_output,
        "verify_total_tokens": verify_total,
        "total_tokens": total_tokens,
        "total_duration": total_duration,
        "answer_correct": 1 if classification == "correct" else 0,
        "answer_wrong": 1 if classification == "wrong" else 0,
        "answer_abstained": 1 if classification == "abstained" else 0,
        "tool_created": 1 if context.tool_created else 0,
        "tool_updated": 1 if context.tool_updated else 0,
        "tool_saved": 1 if context.tool_saved else 0,  # NEW
        "error": 1 if context.error_message else 0,
    }

    # Add Path A metrics if applicable
    if context.identify_tool_result:
        metrics.update(
            {
                "identify_tool_duration": context.identify_tool_duration,
                "identify_tool_input_tokens": identify_tool_input,
                "identify_tool_output_tokens": identify_tool_output,
                "identify_tool_total_tokens": identify_tool_total,
            }
        )

    if context.create_tool_result:
        metrics.update(
            {
                "create_tool_duration": context.create_tool_duration,
                "create_tool_input_tokens": create_tool_input,
                "create_tool_output_tokens": create_tool_output,
                "create_tool_total_tokens": create_tool_total,
            }
        )

    # Add Path B metrics if applicable
    if context.identify_faulty_result:
        metrics.update(
            {
                "identify_faulty_duration": context.identify_faulty_duration,
                "identify_faulty_input_tokens": identify_faulty_input,
                "identify_faulty_output_tokens": identify_faulty_output,
                "identify_faulty_total_tokens": identify_faulty_total,
            }
        )

    if context.debug_tool_result:
        metrics.update(
            {
                "debug_tool_duration": context.debug_tool_duration,
                "debug_tool_input_tokens": debug_tool_input,
                "debug_tool_output_tokens": debug_tool_output,
                "debug_tool_total_tokens": debug_tool_total,
            }
        )

    # NEW: Add tool testing metrics if applicable
    if context.test_cobbie_result:
        metrics.update(
            {
                "test_cobbie_duration": context.test_cobbie_duration,
                "test_cobbie_input_tokens": test_cobbie_input,
                "test_cobbie_output_tokens": test_cobbie_output,
                "test_cobbie_total_tokens": test_cobbie_total,
                "test_verify_duration": context.test_verify_duration,
                "test_verify_input_tokens": test_verify_input,
                "test_verify_output_tokens": test_verify_output,
                "test_verify_total_tokens": test_verify_total,
            }
        )

    # NEW: Add tool assessment metrics if applicable
    if context.tool_assessment:
        metrics.update(
            {
                "tool_assessment_duration": context.tool_assessment_duration,
                "tool_assessment_input_tokens": tool_assess_input,
                "tool_assessment_output_tokens": tool_assess_output,
                "tool_assessment_total_tokens": tool_assess_total,
                "tool_was_used": 1 if context.tool_assessment.tool_was_used else 0,
                "tool_usage_helpful": 1
                if context.tool_assessment.tool_usage_quality == "helpful"
                else 0,
                "tool_usage_harmful": 1
                if context.tool_assessment.tool_usage_quality == "harmful"
                else 0,
                "tool_recommendation_keep": 1
                if context.tool_assessment.recommendation == "keep_tool"
                else 0,
                "tool_recommendation_discard": 1
                if context.tool_assessment.recommendation == "discard_tool"
                else 0,
            }
        )

    # Log to MLflow
    mlflow.log_metrics(metrics)

    # Return dictionary for aggregate calculation
    return {
        "question_id": context.qa_pair.id,
        "classification": classification,
        "tool_created": context.tool_created,
        "tool_updated": context.tool_updated,
        "tool_saved": context.tool_saved,  # NEW
        "error": bool(context.error_message),
        "total_tokens": total_tokens,
        "total_duration": total_duration,
        # NEW: Tool assessment data
        "tool_was_tested": bool(context.tool_assessment),
        "tool_recommendation": context.tool_assessment.recommendation
        if context.tool_assessment
        else None,
        "tool_usage_quality": context.tool_assessment.tool_usage_quality
        if context.tool_assessment
        else None,
    }


# ============================================================================
# State Handler Functions
# ============================================================================


def handle_start_state(context: Context) -> Tuple[TrainingState, Context]:
    """
    Initialize tools for this QA pair.

    Actions:
    1. Load all created tools with get_created_tools()
    2. Store in context
    3. Log initial tool count

    Returns:
        Next state: RUN_COBBIE
    """
    # Load all available tools
    context.tools = get_created_tools()

    _logger.info(f"Loaded {len(context.tools)} tools for question {context.qa_pair.id}")

    return TrainingState.RUN_COBBIE, context


def handle_run_cobbie(context: Context) -> Tuple[TrainingState, Context]:
    """
    Run Cobbie agent to answer the question.

    Actions:
    1. Generate tools documentation
    2. Call cobbie() with tools
    3. Store result, collector, history in context
    4. Log metrics to MLflow span

    Returns:
        Next state: VERIFY_ANSWER
    """
    # Get IFC model path
    ifc_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

    _logger.info(f"Running Cobbie for question: {context.qa_pair.question}")

    start_time = time.time()

    try:
        result, collector, history = cobbie(
            user_input=context.qa_pair.question,
            tools=context.tools,
            max_iterations=10,
            model_path=ifc_path,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )

        context.cobbie_result = result
        context.cobbie_collector = collector
        context.cobbie_history = history
        context.cobbie_duration = time.time() - start_time

        _logger.info(f"Cobbie completed in {context.cobbie_duration:.2f}s")
        _logger.info(f"Cobbie answer: {result.answer}")

        return TrainingState.VERIFY_ANSWER, context

    except Exception as e:
        _logger.error(f"Error running Cobbie: {e}")
        context.error_message = f"Cobbie error: {e}"
        context.cobbie_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_verify_answer(context: Context) -> Tuple[TrainingState, Context]:
    """
    Verify if Cobbie's answer is correct.

    Actions:
    1. Call verify_answer() with question, ground truth, system response
    2. Store result in context
    3. Branch based on classification

    Returns:
        Next state:
        - IDENTIFY_NEW_TOOL if classification == "correct"
        - IDENTIFY_FAULTY_TOOL if classification == "wrong"
        - END if classification == "abstained"
    """
    _logger.info("Verifying answer...")

    start_time = time.time()

    try:
        if not context.cobbie_result:
            raise ValueError("Cobbie result is None")

        # Category must be an integer between 1-4
        category = context.qa_pair.category if context.qa_pair.category else 1

        result, collector = verify_answer(
            question=context.qa_pair.question,
            category=category,  # type: ignore
            ground_truth=context.qa_pair.ground_truth,
            system_response=context.cobbie_result.answer,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )

        context.verify_result = result
        context.verify_collector = collector
        context.verify_duration = time.time() - start_time

        _logger.info(
            f"Verification result: {result.classification} (confidence: {result.confidence})"
        )
        _logger.info(f"Justification: {result.justification}")

        # Log the answer and the justification as parameter for later access for evaluation
        mlflow.log_params(
            {
                "justification": result.justification,
                "cobbie_answer": context.cobbie_result.answer,
            }
        )

        # Determine next state based on classification
        if result.classification == "correct":
            context.path_taken = "correct"
            _logger.info("Answer CORRECT - Following Path A (identify new tool)")
            return TrainingState.IDENTIFY_NEW_TOOL, context
        elif result.classification == "wrong":
            context.path_taken = "wrong"
            _logger.info("Answer WRONG - Following Path B (identify faulty tool)")
            return TrainingState.IDENTIFY_FAULTY_TOOL, context
        else:  # "abstained"
            context.path_taken = "abstained"
            _logger.info("Answer ABSTAINED - Skipping both paths")
            return TrainingState.END, context

    except Exception as e:
        _logger.error(f"Error verifying answer: {e}")
        context.error_message = f"Answer verification error: {e}"
        context.verify_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_identify_new_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Identify if a new helper function should be created (Path A: Correct answer).

    Actions:
    1. Generate existing tools documentation
    2. Call identify_helper_function() with history and question
    3. Store result in context
    4. Decide if tool creation is needed

    Returns:
        Next state:
        - CREATE_NEW_TOOL if new_tool == True
        - END if new_tool == False
    """
    _logger.info("Identifying potential new tool...")

    start_time = time.time()

    try:
        if not context.cobbie_result:
            raise ValueError("Cobbie result is None")

        # Generate existing tools docs
        existing_tools_docs = generate_tools_docs(context.tools)

        # Construct full history with final answer
        full_history = (
            f"{context.cobbie_history}\n\n"
            f"--- Final Answer ---\n"
            f"Thoughts: {context.cobbie_result.thoughts}\n"
            f"Answer: {context.cobbie_result.answer}"
        )

        result, collector = identify_helper_function(
            history=full_history,
            example_question=context.qa_pair.question,
            existing_helper_functions=existing_tools_docs,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )

        context.identify_tool_result = result
        context.identify_tool_collector = collector
        context.identify_tool_duration = time.time() - start_time

        _logger.info(f"New tool needed: {result.new_tool}")
        if result.new_tool:
            _logger.info(f"Tool name: {result.new_tool_name}")
            _logger.info(f"Tool description: {result.new_tool_description}")

        # Decide next state
        if result.new_tool:
            if not result.new_tool_name:
                raise ValueError("New tool name is None")
            context.tool_name = result.new_tool_name
            return TrainingState.CREATE_NEW_TOOL, context
        else:
            return TrainingState.END, context

    except Exception as e:
        _logger.error(f"Error identifying new tool: {e}")
        context.error_message = f"Identify new tool error: {e}"
        context.identify_tool_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_create_new_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Create a new helper function (Path A: Correct answer).

    CHANGED: No longer saves the tool immediately.
    Instead, transitions to TEST_TOOL_WITH_COBBIE for validation.

    Actions:
    1. Get IFC model path from QA pair
    2. Get other BIM models for testing
    3. Call create_helper_function()
    4. If success: Mark as created, transition to testing
    5. If failure: Log error

    Returns:
        Next state:
        - TEST_TOOL_WITH_COBBIE if success
        - ERROR if failure
    """
    _logger.info(f"Creating new tool: {context.tool_name}...")

    start_time = time.time()

    try:
        if not context.cobbie_result:
            raise ValueError("Cobbie result is None")
        if not context.identify_tool_result:
            raise ValueError("Identify tool result is None")
        if not context.tool_name:
            raise ValueError("Tool name is None")

        # Get IFC model path from the QA pair (same model used for answering)
        ifc_model_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

        if not ifc_model_path:
            raise ValueError("No IFC model path available for tool creation")

        # Get other BIM models for testing (from bim_models directory)
        bim_models_dir = os.path.join(ROOT_PATH, "src/experiment/bim_models")
        other_models = []
        if os.path.exists(bim_models_dir):
            other_models = [
                os.path.join(bim_models_dir, f)
                for f in os.listdir(bim_models_dir)
                if f.endswith(".ifc")
                and os.path.join(bim_models_dir, f) != ifc_model_path
            ][:3]  # Limit to 3 other models

        # Construct full history
        full_history = (
            f"{context.cobbie_history}\n\n"
            f"--- Final Answer ---\n"
            f"Thoughts: {context.cobbie_result.thoughts}\n"
            f"Answer: {context.cobbie_result.answer}"
        )

        result, collector, creation_history = create_helper_function(
            history=full_history,
            example_question=context.qa_pair.question,
            example_answer=context.qa_pair.ground_truth,
            example_bim_model=ifc_model_path,
            other_bim_models_for_testing=other_models,
            function_name=context.identify_tool_result.new_tool_name,
            function_description=context.identify_tool_result.new_tool_description,
            max_iterations=15,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )

        context.create_tool_result = result
        context.create_tool_collector = collector
        context.create_tool_history = creation_history
        context.create_tool_duration = time.time() - start_time

        _logger.info(f"Tool creation success: {result.success}")

        if result.success:
            # Don't save immediately - proceed to testing first
            _logger.info(
                f"New tool created: {context.tool_name}, proceeding to testing"
            )
            context.tool_created = True

            return TrainingState.TEST_TOOL_WITH_COBBIE, context
        else:
            _logger.warning(f"Tool creation was not successful: {result.thoughts}")
            context.error_message = f"Tool creation failed: {result.thoughts}"
            return TrainingState.ERROR, context

    except Exception as e:
        _logger.error(f"Error creating new tool: {e}")
        context.error_message = f"Create tool error: {e}"
        context.create_tool_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_identify_faulty_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Identify if a faulty helper function caused the wrong answer (Path B: Wrong answer).

    Actions:
    1. Generate existing tools documentation
    2. Call identify_faulty_tool() with history, answers, and justification
    3. Store result in context
    4. Decide if tool debugging is needed

    Returns:
        Next state:
        - DEBUG_FAULTY_TOOL if faulty_tool == True
        - END if faulty_tool == False
    """
    _logger.info("Identifying faulty tool...")

    start_time = time.time()

    try:
        if not context.cobbie_result:
            raise ValueError("Cobbie result is None")
        if not context.verify_result:
            raise ValueError("Verify result is None")

        # Generate existing tools docs
        existing_tools_docs = generate_tools_docs(context.tools)

        # Construct full history with final answer
        full_history = (
            f"{context.cobbie_history}\n\n"
            f"--- Final Answer ---\n"
            f"Thoughts: {context.cobbie_result.thoughts}\n"
            f"Answer: {context.cobbie_result.answer}"
        )

        result, collector = identify_faulty_tool(
            history=full_history,
            question=context.qa_pair.question,
            ground_truth=context.qa_pair.ground_truth,
            provided_answer=context.cobbie_result.answer,
            justification=context.verify_result.justification,
            existing_helper_functions=existing_tools_docs,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )

        context.identify_faulty_result = result
        context.identify_faulty_collector = collector
        context.identify_faulty_duration = time.time() - start_time

        _logger.info(f"Faulty tool identified: {result.faulty_tool}")
        if result.faulty_tool:
            _logger.info(f"Faulty tool name: {result.faulty_tool_name}")
            _logger.info(f"Error description: {result.error_description}")
            _logger.info(f"Confidence: {result.confidence}")

        # Decide next state
        if result.faulty_tool:
            context.tool_name = result.faulty_tool_name
            return TrainingState.DEBUG_FAULTY_TOOL, context
        else:
            _logger.info("No faulty tool identified - error was due to other reasons")
            return TrainingState.END, context

    except Exception as e:
        _logger.error(f"Error identifying faulty tool: {e}")
        context.error_message = f"Identify faulty tool error: {e}"
        context.identify_faulty_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_debug_faulty_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Debug and fix a faulty helper function (Path B: Wrong answer).

    CHANGED: No longer saves the tool immediately.
    Instead, transitions to TEST_TOOL_WITH_COBBIE for validation.

    Actions:
    1. Get faulty tool source code with get_function_code()
    2. Get IFC model path from QA pair
    3. Call debug_helper_function()
    4. If success: Mark as updated, transition to testing
    5. If failure: Log error

    Returns:
        Next state:
        - TEST_TOOL_WITH_COBBIE if success
        - ERROR if failure
    """
    _logger.info(f"Debugging faulty tool: {context.tool_name}...")

    start_time = time.time()

    try:
        if not context.cobbie_result:
            raise ValueError("Cobbie result is None")
        if not context.identify_faulty_result:
            raise ValueError("Identify faulty result is None")
        if not context.tool_name:
            raise ValueError("Tool name is None")

        # Get the faulty tool's source code
        faulty_code_result = get_function_code(context.tool_name)

        if faulty_code_result.is_err():
            raise ValueError(
                f"Could not retrieve faulty tool code: {faulty_code_result.unwrap_err()}"
            )

        faulty_implementation = faulty_code_result.unwrap()

        # Get IFC model path from the QA pair (same model used for answering)
        ifc_model_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

        if not ifc_model_path:
            raise ValueError("No IFC model path available for tool debugging")

        # Construct full history
        full_history = (
            f"{context.cobbie_history}\n\n"
            f"--- Final Answer ---\n"
            f"Thoughts: {context.cobbie_result.thoughts}\n"
            f"Answer: {context.cobbie_result.answer}"
        )

        result, collector, debug_history = debug_helper_function(
            faulty_function_name=context.tool_name,
            faulty_function_implementation=faulty_implementation,
            error_description=context.identify_faulty_result.error_description,
            history_faulty_tool_use=full_history,
            ifc_model_path=ifc_model_path,
            max_iterations=15,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )

        context.debug_tool_result = result
        context.debug_tool_collector = collector
        context.debug_tool_history = debug_history
        context.debug_tool_duration = time.time() - start_time

        _logger.info(f"Tool debugging success: {result.success}")

        if result.success:
            # Don't save immediately - proceed to testing first
            _logger.info(
                f"Faulty tool debugged: {context.tool_name}, proceeding to testing"
            )
            _logger.info(f"Changes summary: {result.changes_summary}")
            context.tool_updated = True

            return TrainingState.TEST_TOOL_WITH_COBBIE, context
        else:
            _logger.warning(f"Tool debugging was not successful: {result.thoughts}")
            context.error_message = f"Tool debugging failed: {result.thoughts}"
            return TrainingState.ERROR, context

    except Exception as e:
        _logger.error(f"Error debugging faulty tool: {e}")
        context.error_message = f"Debug tool error: {e}"
        context.debug_tool_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_test_tool_with_cobbie(context: Context) -> Tuple[TrainingState, Context]:
    """
    Re-run Cobbie with enhanced question to test the new/updated tool.

    Actions:
    1. Temporarily add the new/updated tool to the tools dictionary
    2. Enhance the question to encourage using the tool
    3. Run Cobbie with the enhanced question
    4. Store test results in context
    5. Transition to assessment

    Returns:
        Next state: ASSESS_TOOL_USAGE
    """
    _logger.info(f"Testing tool with Cobbie: {context.tool_name}...")

    start_time = time.time()

    try:
        # Assert tool_name is not None (should be set by previous states)
        assert context.tool_name is not None, "tool_name should be set before testing"

        # Get the tool implementation
        if context.create_tool_result:
            tool_implementation = context.create_tool_result.function_implementation
            _logger.info(f"Testing newly created tool: {context.tool_name}")
        elif context.debug_tool_result:
            tool_implementation = context.debug_tool_result.fixed_implementation
            _logger.info(f"Testing debugged tool: {context.tool_name}")
        else:
            raise ValueError("No tool implementation available for testing")

        # Temporarily add the tool to the tools dictionary
        from src.engine.util import _create_function_from_source_code

        creation_result = _create_function_from_source_code(
            function_name=context.tool_name,
            code=tool_implementation,
        )

        if creation_result.is_err():
            error_msg = (
                f"Failed to create function for testing: {creation_result.unwrap_err()}"
            )
            _logger.error(error_msg)
            context.error_message = error_msg
            return TrainingState.ERROR, context

        new_tool = creation_result.unwrap()

        # Create a copy of tools with the new tool added
        test_tools = context.tools.copy()
        test_tools[context.tool_name] = new_tool

        _logger.info(
            f"Tool '{context.tool_name}' added to test environment. Total tools: {len(test_tools)}"
        )

        # Enhance the question to guide tool usage
        enhanced_question = (
            f"{context.qa_pair.question}\n\n"
            f"NOTE: A helper function `{context.tool_name}` was recently created. "
            f"If it seems relevant, consider using it to help answer this question."
        )

        # Get IFC model path
        ifc_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

        # Run Cobbie with enhanced question and test tools
        result, collector, history = cobbie(
            user_input=enhanced_question,
            tools=test_tools,
            max_iterations=10,
            model_path=ifc_path,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )

        context.test_cobbie_result = result
        context.test_cobbie_collector = collector
        context.test_cobbie_history = history
        context.test_cobbie_duration = time.time() - start_time

        _logger.info(f"Tool testing Cobbie run completed: {result.answer[:100]}...")
        return TrainingState.ASSESS_TOOL_USAGE, context

    except Exception as e:
        _logger.error(f"Error testing tool with Cobbie: {e}")
        context.error_message = f"Tool testing error: {e}"
        context.test_cobbie_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_assess_tool_usage(context: Context) -> Tuple[TrainingState, Context]:
    """
    Analyze if the tested tool was helpful during Cobbie's execution.

    Actions:
    1. Verify the test answer with verify_answer agent
    2. Get tool description from creation/debugging context
    3. Call assess_helper_function to analyze tool usage
    4. Store assessment in context
    5. Transition to decision state

    Returns:
        Next state: DECIDE_TOOL_FATE
    """
    _logger.info(f"Assessing tool usage: {context.tool_name}...")

    start_time = time.time()

    try:
        # Assert tool_name is not None (should be set by previous states)
        assert context.tool_name is not None, (
            "tool_name should be set before assessment"
        )

        # Assert category is valid (1-4)
        assert context.qa_pair.category is not None and context.qa_pair.category in [
            1,
            2,
            3,
            4,
        ], "category must be 1-4"
        category = cast(Literal[1, 2, 3, 4], context.qa_pair.category)

        # Verify the test answer
        verify_start = time.time()
        assert context.test_cobbie_result is not None, (
            "The test_cobbie_result in context cannot be None at this step."
        )
        verify_result, verify_collector = verify_answer(
            question=context.qa_pair.question,
            category=category,
            ground_truth=context.qa_pair.ground_truth,
            system_response=context.test_cobbie_result.answer,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )
        context.test_verify_result = verify_result
        context.test_verify_collector = verify_collector
        context.test_verify_duration = time.time() - verify_start

        _logger.info(
            f"Test answer verified: {verify_result.classification} (confidence: {verify_result.confidence})"
        )

        # Get tool description based on path
        if context.create_tool_result:
            assert context.identify_tool_result is not None
            tool_description = context.identify_tool_result.new_tool_description
        elif context.debug_tool_result:
            assert context.identify_faulty_result is not None
            tool_description = context.identify_faulty_result.error_description
        else:
            raise ValueError("No tool context available for assessment")

        # Construct full test history with final answer
        full_test_history = (
            f"{context.test_cobbie_history}\n\n"
            f"--- Final Answer ---\n"
            f"Thoughts: {context.test_cobbie_result.thoughts}\n"
            f"Answer: {context.test_cobbie_result.answer}"
        )

        # Assess tool usage
        assess_start = time.time()
        assessment, assessment_collector = assess_helper_function(
            execution_history=full_test_history,
            original_question=context.qa_pair.question,
            ground_truth_answer=context.qa_pair.ground_truth,
            tested_tool_name=context.tool_name,
            tested_tool_description=tool_description,
            final_answer=context.test_cobbie_result.answer,
            answer_correctness=verify_result.classification,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )
        context.tool_assessment = assessment
        context.tool_assessment_collector = assessment_collector
        context.tool_assessment_duration = time.time() - assess_start

        _logger.info(
            f"Tool assessment completed: {assessment.recommendation} "
            f"(quality: {assessment.tool_usage_quality}, confidence: {assessment.confidence})"
        )

        context.tool_assessment_duration = time.time() - start_time
        return TrainingState.DECIDE_TOOL_FATE, context

    except Exception as e:
        _logger.error(f"Error assessing tool usage: {e}")
        context.error_message = f"Tool assessment error: {e}"
        context.tool_assessment_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_decide_tool_fate(context: Context) -> Tuple[TrainingState, Context]:
    """
    Decide whether to keep, discard, or flag the tool based on assessment.

    Actions:
    1. Examine the assessment recommendation
    2. Make final decision on tool fate
    3. Save tool if recommended (keep_tool)
    4. Log decision and rationale
    5. Update context metadata

    Returns:
        Next state: END
    """
    _logger.info(f"Deciding fate of tool: {context.tool_name}...")

    try:
        # Assert tool_name is not None (should be set by previous states)
        assert context.tool_name is not None, (
            "tool_name should be set before deciding fate"
        )

        assessment = context.tool_assessment
        assert assessment is not None

        # Get tool implementation
        if context.create_tool_result:
            tool_implementation = context.create_tool_result.function_implementation
        elif context.debug_tool_result:
            tool_implementation = context.debug_tool_result.fixed_implementation
        else:
            raise ValueError("No tool implementation available")

        # Decision logic based on recommendation
        if assessment.recommendation == "keep_tool":
            # Tool is helpful, save it permanently
            save_success = save_new_tool(
                function_name=context.tool_name,
                function_implementation=tool_implementation,
            )

            if save_success:
                context.tool_saved = True
                _logger.info(
                    f"✅ Tool '{context.tool_name}' validated and saved permanently\n"
                    f"   Quality: {assessment.tool_usage_quality}\n"
                    f"   Confidence: {assessment.confidence}\n"
                    f"   Details: {assessment.usage_details[:200]}..."
                )

                # Reload tools to include the new one
                context.tools = get_created_tools()
                _logger.info(f"Tools reloaded. Now have {len(context.tools)} tools")

                return TrainingState.END, context
            else:
                _logger.error(f"Failed to save tool: {context.tool_name}")
                context.error_message = f"Failed to save tool: {context.tool_name}"
                return TrainingState.ERROR, context

        elif assessment.recommendation == "discard_tool":
            # Tool is not useful or harmful, discard it
            context.tool_saved = False
            _logger.info(
                f"❌ Tool '{context.tool_name}' discarded\n"
                f"   Quality: {assessment.tool_usage_quality}\n"
                f"   Confidence: {assessment.confidence}\n"
                f"   Reason: {assessment.usage_details[:200]}..."
            )
            return TrainingState.END, context

        elif assessment.recommendation == "improve_tool":
            # Tool has potential but needs work
            context.tool_saved = False
            _logger.info(
                f"⚠️  Tool '{context.tool_name}' needs improvement (not saved)\n"
                f"   Quality: {assessment.tool_usage_quality}\n"
                f"   Confidence: {assessment.confidence}\n"
                f"   Issues: {assessment.usage_details[:200]}..."
            )
            return TrainingState.END, context

        else:  # unclear
            # Conservative: keep it tentatively with low confidence
            save_success = save_new_tool(
                function_name=context.tool_name,
                function_implementation=tool_implementation,
            )

            if save_success:
                context.tool_saved = True
                _logger.info(
                    f"❓ Tool '{context.tool_name}' assessment unclear, saved tentatively\n"
                    f"   Quality: {assessment.tool_usage_quality}\n"
                    f"   Confidence: {assessment.confidence}\n"
                    f"   Note: {assessment.usage_details[:200]}..."
                )

                # Reload tools
                context.tools = get_created_tools()
                return TrainingState.END, context
            else:
                _logger.error(f"Failed to save tool: {context.tool_name}")
                context.error_message = f"Failed to save tool: {context.tool_name}"
                return TrainingState.ERROR, context

    except Exception as e:
        _logger.error(f"Error deciding tool fate: {e}")
        context.error_message = f"Tool fate decision error: {e}"
        return TrainingState.ERROR, context


# ============================================================================
# State Machine Dispatcher
# ============================================================================


def process_state(
    state: TrainingState, context: Context
) -> Tuple[TrainingState, Context]:
    """
    Dispatcher function that routes to the appropriate state handler.

    Args:
        state: Current training state
        context: Context with all agent results and metadata

    Returns:
        Tuple of (next_state, updated_context)
    """
    if state == TrainingState.START:
        return handle_start_state(context)
    elif state == TrainingState.RUN_COBBIE:
        return handle_run_cobbie(context)
    elif state == TrainingState.VERIFY_ANSWER:
        return handle_verify_answer(context)
    elif state == TrainingState.IDENTIFY_NEW_TOOL:
        return handle_identify_new_tool(context)
    elif state == TrainingState.CREATE_NEW_TOOL:
        return handle_create_new_tool(context)
    elif state == TrainingState.IDENTIFY_FAULTY_TOOL:
        return handle_identify_faulty_tool(context)
    elif state == TrainingState.DEBUG_FAULTY_TOOL:
        return handle_debug_faulty_tool(context)
    elif state == TrainingState.TEST_TOOL_WITH_COBBIE:
        return handle_test_tool_with_cobbie(context)
    elif state == TrainingState.ASSESS_TOOL_USAGE:
        return handle_assess_tool_usage(context)
    elif state == TrainingState.DECIDE_TOOL_FATE:
        return handle_decide_tool_fate(context)
    else:
        _logger.error(f"Unknown state: {state}")
        context.error_message = f"Unknown state: {state}"
        return TrainingState.ERROR, context


# ============================================================================
# Main Training Loop
# ============================================================================


def main():
    """Main training loop."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Run training phase")
    parser.add_argument("--start", type=int, default=0, help="Start index")
    parser.add_argument("--end", type=int, default=None, help="End index")
    args = parser.parse_args()

    # Load dataset
    devset, trainset = load_train_dev_split()
    end_index = args.end if args.end else len(trainset)
    dataset = trainset[args.start : end_index]

    _logger.info(f"Starting training phase with {len(dataset)} QA pairs")
    _logger.info(f"Dataset range: {args.start} to {end_index - 1}")

    # Setup MLflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("Training")

    run_name = f"TRAINING_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}_samples_{args.start}_{end_index - 1}"

    # Main MLflow run
    with mlflow.start_run(run_name=run_name):
        # Log main-level parameters
        initial_tools = get_created_tools()
        mlflow.log_params(
            {
                "model_name": "glm-4.6",
                "provider_name": "zai",
                "component": "Training",
                "start_index": args.start,
                "end_index": end_index,
                "num_samples": len(dataset),
                "initial_tools_count": len(initial_tools),
            }
        )

        # Track results for aggregate metrics
        qa_results = []

        # Process each QA pair
        for idx, qa_pair in enumerate(dataset):
            _logger.info(f"\n{'=' * 80}")
            _logger.info(f"Processing QA {idx + 1}/{len(dataset)}: {qa_pair.id}")
            _logger.info(f"Question: {qa_pair.question}")
            _logger.info(f"Ground truth: {qa_pair.ground_truth}")
            _logger.info(f"{'=' * 80}")

            # Create nested run for this QA pair
            qa_run_name = f"question_{qa_pair.id}"

            with mlflow.start_run(run_name=qa_run_name, nested=True):
                # Log QA-level parameters
                mlflow.log_params(
                    {
                        "question_id": qa_pair.id,
                        "question": qa_pair.question,
                        "ground_truth": qa_pair.ground_truth,
                        "category": qa_pair.category,
                        "ifc_model_path": qa_pair.ifc.model_path
                        if qa_pair.ifc
                        else None,
                    }
                )

                # Initialize context and state
                context = Context(qa_pair=qa_pair)
                state = TrainingState.START

                # State machine loop with single main span
                try:
                    with mlflow.start_span(name="TrainingQA", span_type="CHAIN"):
                        while state not in [TrainingState.END, TrainingState.ERROR]:
                            state, context = process_state(state, context)

                    # Log QA-level metrics
                    qa_result = log_qa_metrics(context)
                    qa_results.append(qa_result)

                    if state == TrainingState.ERROR:
                        _logger.error(
                            f"QA {qa_pair.id} ended with error: {context.error_message}"
                        )
                        mlflow.set_tag("status", "ERROR")
                    else:
                        _logger.info(f"QA {qa_pair.id} completed successfully")
                        mlflow.set_tag("status", "success")

                except Exception as e:
                    _logger.error(
                        f"Unexpected error processing QA {qa_pair.id}: {e}",
                        exc_info=True,
                    )
                    qa_results.append(
                        {
                            "question_id": qa_pair.id,
                            "classification": "unknown",
                            "tool_created": False,
                            "tool_updated": False,
                            "error": True,
                            "total_tokens": 0,
                            "total_duration": 0,
                        }
                    )
                    mlflow.set_tag("status", "exception")
                    # Continue to next QA pair

        # Calculate and log aggregate metrics
        aggregate_metrics = calculate_aggregate_metrics(qa_results)
        if aggregate_metrics:
            mlflow.log_metrics(aggregate_metrics)

        _logger.info(f"\n{'=' * 80}")
        _logger.info("Training Phase Complete")
        _logger.info(f"{'=' * 80}")
        _logger.info(f"Total QA pairs: {aggregate_metrics.get('total_qa_pairs', 0)}")
        _logger.info(f"Correct answers: {aggregate_metrics.get('correct_answers', 0)}")
        _logger.info(f"Wrong answers: {aggregate_metrics.get('wrong_answers', 0)}")
        _logger.info(f"Abstained: {aggregate_metrics.get('abstained_answers', 0)}")
        _logger.info(f"Tools created: {aggregate_metrics.get('tools_created', 0)}")
        _logger.info(f"Tools updated: {aggregate_metrics.get('tools_updated', 0)}")
        _logger.info(f"Errors: {aggregate_metrics.get('errors', 0)}")
        _logger.info(f"Success rate: {aggregate_metrics.get('success_rate', 0):.2%}")

        # Get final tool count
        final_tools = get_created_tools()
        _logger.info(
            f"Final tool count: {len(final_tools)} (started with {len(initial_tools)})"
        )


if __name__ == "__main__":
    main()
