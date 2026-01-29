"""
ACC Training Phase v2 - GUID-Based Validation

This script implements the new ACC training flow with direct GUID-based validation
instead of Cobbie-based Q&A verification.

Training Flow:
    START -> LOAD_TOOLS -> CREATE_TOOL -> VALIDATE_TOOL
        -> [F1=1.0] -> SAVE_TOOL -> END
        -> [F1<1.0] -> ASSESS_GENERALIZABILITY -> DECIDE_FATE
            -> [retry_with_hint & retries < max] -> CREATE_TOOL (loop)
            -> [retries exhausted] -> SAVE_BEST_TOOL -> END

Data Split:
    - Training: duplex model (acc/res/duplex/ground_truth.json)
    - Validation: dental_clinic model (acc/res/dental_clinic/ground_truth.json)
"""

import argparse
import io
import time
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Tuple

import mlflow
from baml_py.baml_py import Collector

from baml_client.types import ACCToolAssessment, NewHelperFunction
from src.agents.assess_acc_tool import assess_acc_tool
from src.agents.create_acc_function import create_helper_function
from src.acc.guid_comparison import (
    GUIDComparisonResult,
    compare_guids,
    get_rule_context,
    get_available_rules,
    get_model_path,
)
from src.config import LOG_LEVEL, ACC_TOOLS_PATH
from src.util import get_logger, save_new_tool, _create_function_from_source_code

# Initialize logger
_logger = get_logger(name="ACCTrainingPhase", log_level=LOG_LEVEL)

# Constants for training/validation models
TRAINING_MODEL = "duplex"
VALIDATION_MODEL = "dental_clinic"


class ACCTrainingState(Enum):
    """State machine states for ACC training."""

    START = auto()
    LOAD_TOOLS = auto()
    CREATE_TOOL = auto()
    VALIDATE_TOOL = auto()
    ASSESS_GENERALIZABILITY = auto()
    DECIDE_FATE = auto()
    SAVE_TOOL = auto()
    END = auto()
    ERROR = auto()


@dataclass
class ACCContext:
    """Context object for ACC training state machine."""

    # Rule identification
    rule_title: str
    rule_idx: int  # Index in the rules list

    # Rule context from ground truth
    rule_code: str = ""
    rule_description: str = ""
    question: str = ""
    parameters: str = ""

    # Training data (duplex)
    training_model_name: str = TRAINING_MODEL
    training_model_path: str = ""
    training_expected_guids: list[str] = field(default_factory=list)
    training_predicted_guids: list[str] = field(default_factory=list)
    training_result: Optional[GUIDComparisonResult] = None

    # Validation data (dental_clinic)
    validation_model_name: str = VALIDATION_MODEL
    validation_model_path: str = ""
    validation_expected_guids: list[str] = field(default_factory=list)
    validation_predicted_guids: list[str] = field(default_factory=list)
    validation_result: Optional[GUIDComparisonResult] = None

    # Tool creation
    tool_name: str = ""
    tool_implementation: str = ""
    create_tool_result: Optional[NewHelperFunction] = None
    create_tool_collector: Optional[Collector] = None
    create_tool_history: str = ""
    create_tool_duration: float = 0.0

    # Validation execution
    execution_log: str = ""
    validate_duration: float = 0.0

    # Assessment
    assessment: Optional[ACCToolAssessment] = None
    assessment_collector: Optional[Collector] = None
    assessment_duration: float = 0.0

    # Retry tracking
    retry_count: int = 0
    max_retries: int = 2
    improvement_hint: Optional[str] = None
    previous_hints: str = ""

    # Best tool tracking
    best_tool_implementation: str = ""
    best_tool_f1: float = 0.0

    # Status
    error_message: Optional[str] = None
    tool_saved: bool = False


def extract_token_metrics(collector: Optional[Collector]) -> Tuple[int, int, int]:
    """Extract token metrics from BAML collector."""
    if not collector:
        return 0, 0, 0

    try:
        if hasattr(collector, "usage") and collector.usage:
            usage = collector.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            return input_tokens, output_tokens, input_tokens + output_tokens
    except Exception as e:
        _logger.warning(f"Error extracting token usage: {e}")

    return 0, 0, 0


# ============================================================================
# State Handlers
# ============================================================================


def handle_start(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Initialize context with rule data from ground truth."""
    _logger.info(f"Starting ACC training for rule: {ctx.rule_title}")

    try:
        # Load training context
        training_context = get_rule_context(ctx.training_model_name, ctx.rule_title)
        ctx.rule_code = training_context["rule_code"]
        ctx.rule_description = training_context["rule_description"]
        ctx.question = training_context["question"]
        ctx.parameters = training_context["parameters"]
        ctx.training_expected_guids = training_context["expected_guids"]

        # Get training model path
        ctx.training_model_path = get_model_path(ctx.training_model_name) or ""
        if not ctx.training_model_path:
            raise ValueError(f"Could not find IFC model for {ctx.training_model_name}")

        # Load validation context
        validation_context = get_rule_context(ctx.validation_model_name, ctx.rule_title)
        ctx.validation_expected_guids = validation_context["expected_guids"]

        # Get validation model path
        ctx.validation_model_path = get_model_path(ctx.validation_model_name) or ""
        if not ctx.validation_model_path:
            raise ValueError(f"Could not find IFC model for {ctx.validation_model_name}")

        # Generate tool name from rule title
        ctx.tool_name = f"check_{ctx.rule_title}"

        _logger.info(f"Rule: {ctx.rule_code} - {ctx.rule_title}")
        _logger.info(f"Training expected GUIDs: {len(ctx.training_expected_guids)}")
        _logger.info(f"Validation expected GUIDs: {len(ctx.validation_expected_guids)}")

        return ACCTrainingState.CREATE_TOOL, ctx

    except Exception as e:
        _logger.error(f"Error in START state: {e}")
        ctx.error_message = str(e)
        return ACCTrainingState.ERROR, ctx


def handle_create_tool(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Create or retry creating the ACC tool."""
    action = "Retrying" if ctx.retry_count > 0 else "Creating"
    _logger.info(f"{action} tool: {ctx.tool_name} (attempt {ctx.retry_count + 1}/{ctx.max_retries + 1})")

    start_time = time.time()

    try:
        # Build the question with rule context
        full_question = (
            f"Rule: {ctx.rule_code} {ctx.rule_title}\n"
            f"{ctx.rule_description}\n\n"
            f"Parameters: {ctx.parameters}\n\n"
            f"Question: {ctx.question}\n\n"
            f"Return a list of IFC GUIDs of all elements that violate this rule."
        )

        # Build expected answer as GUID list string
        expected_answer = str(ctx.training_expected_guids)

        # Include improvement hint if retrying
        history = ""
        if ctx.improvement_hint:
            history = (
                f"PREVIOUS ATTEMPT FEEDBACK:\n"
                f"The previous implementation had issues. Here's guidance for improvement:\n"
                f"{ctx.improvement_hint}\n\n"
                f"Previous hints given:\n{ctx.previous_hints}\n\n"
                f"Please create an improved version that addresses these issues.\n"
                f"---\n"
            )

        result, collector, creation_history = create_helper_function(
            history=history,
            example_question=full_question,
            example_answer=expected_answer,
            example_bim_model=ctx.training_model_path,
            function_name=ctx.tool_name,
            function_description=full_question,
            other_bim_models_for_testing=[],
            max_iterations=15,
            llm_provider="zai",
            llm_name="GLM-4.7",
        )

        ctx.create_tool_result = result
        ctx.create_tool_collector = collector
        ctx.create_tool_history = creation_history
        ctx.create_tool_duration = time.time() - start_time

        if result.success and result.function_implementation:
            ctx.tool_implementation = result.function_implementation
            _logger.info(f"Tool creation succeeded in {ctx.create_tool_duration:.1f}s")
            return ACCTrainingState.VALIDATE_TOOL, ctx
        else:
            _logger.warning(f"Tool creation failed: {result.thoughts}")
            ctx.error_message = f"Tool creation failed: {result.thoughts}"
            return ACCTrainingState.ERROR, ctx

    except Exception as e:
        _logger.error(f"Error creating tool: {e}")
        ctx.error_message = str(e)
        ctx.create_tool_duration = time.time() - start_time
        return ACCTrainingState.ERROR, ctx


def _execute_tool(tool_implementation: str, function_name: str, model_path: str) -> Tuple[list[str], str]:
    """
    Execute an ACC tool and return predicted GUIDs and execution log.

    Returns:
        Tuple of (predicted_guids, execution_log)
    """
    # Create callable from source code
    result = _create_function_from_source_code(
        code=tool_implementation,
        function_name=function_name,
    )

    if result.is_err():
        error_msg = f"Failed to create function: {result.unwrap_err()}"
        return [], error_msg

    tool_fn = result.unwrap()

    # Capture stdout/stderr during execution
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    try:
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            guids = tool_fn(model_path)

        # Process result
        if isinstance(guids, list):
            predicted = [str(g) for g in guids]
        else:
            predicted = []

        log = stdout_capture.getvalue()
        if stderr_capture.getvalue():
            log += f"\nSTDERR:\n{stderr_capture.getvalue()}"

        return predicted, log

    except Exception as e:
        error_log = f"Execution error: {e}\n"
        error_log += f"STDOUT:\n{stdout_capture.getvalue()}\n"
        error_log += f"STDERR:\n{stderr_capture.getvalue()}"
        return [], error_log


def handle_validate_tool(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Execute tool on validation model and compare GUIDs."""
    _logger.info(f"Validating tool on {ctx.validation_model_name}...")

    start_time = time.time()

    try:
        # Execute on training model first (for completeness)
        training_predicted, training_log = _execute_tool(
            ctx.tool_implementation, ctx.tool_name, ctx.training_model_path
        )
        ctx.training_predicted_guids = training_predicted
        ctx.training_result = compare_guids(
            set(training_predicted), set(ctx.training_expected_guids)
        )

        _logger.info(
            f"Training: TP={ctx.training_result.tp}, FP={ctx.training_result.fp}, "
            f"FN={ctx.training_result.fn}, F1={ctx.training_result.f1:.3f}"
        )

        # Execute on validation model
        validation_predicted, validation_log = _execute_tool(
            ctx.tool_implementation, ctx.tool_name, ctx.validation_model_path
        )
        ctx.validation_predicted_guids = validation_predicted
        ctx.validation_result = compare_guids(
            set(validation_predicted), set(ctx.validation_expected_guids)
        )

        ctx.execution_log = f"=== Training ({ctx.training_model_name}) ===\n{training_log}\n\n"
        ctx.execution_log += f"=== Validation ({ctx.validation_model_name}) ===\n{validation_log}"
        ctx.validate_duration = time.time() - start_time

        _logger.info(
            f"Validation: TP={ctx.validation_result.tp}, FP={ctx.validation_result.fp}, "
            f"FN={ctx.validation_result.fn}, F1={ctx.validation_result.f1:.3f}"
        )

        # Track best tool
        if ctx.validation_result.f1 > ctx.best_tool_f1:
            ctx.best_tool_f1 = ctx.validation_result.f1
            ctx.best_tool_implementation = ctx.tool_implementation
            _logger.info(f"New best tool! F1={ctx.best_tool_f1:.3f}")

        # Check for perfect match
        if ctx.validation_result.f1 == 1.0:
            _logger.info("Perfect validation F1=1.0 - saving tool immediately")
            return ACCTrainingState.SAVE_TOOL, ctx

        # Not perfect - assess and potentially retry
        return ACCTrainingState.ASSESS_GENERALIZABILITY, ctx

    except Exception as e:
        _logger.error(f"Error validating tool: {e}")
        ctx.error_message = str(e)
        ctx.validate_duration = time.time() - start_time
        return ACCTrainingState.ERROR, ctx


def handle_assess_generalizability(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Assess why the tool failed on validation and get improvement hints."""
    _logger.info("Assessing tool generalizability...")

    start_time = time.time()

    try:
        assert ctx.training_result is not None
        assert ctx.validation_result is not None

        assessment, collector = assess_acc_tool(
            rule_title=ctx.rule_title,
            rule_code=ctx.rule_code,
            rule_description=ctx.rule_description,
            question=ctx.question,
            training_model_name=ctx.training_model_name,
            training_expected_guids=ctx.training_expected_guids,
            training_predicted_guids=ctx.training_predicted_guids,
            training_tp=ctx.training_result.tp,
            training_fp=ctx.training_result.fp,
            training_fn=ctx.training_result.fn,
            training_f1=ctx.training_result.f1,
            validation_model_name=ctx.validation_model_name,
            validation_expected_count=len(ctx.validation_expected_guids),
            validation_predicted_count=len(ctx.validation_predicted_guids),
            validation_tp=ctx.validation_result.tp,
            validation_fp=ctx.validation_result.fp,
            validation_fn=ctx.validation_result.fn,
            validation_f1=ctx.validation_result.f1,
            tool_name=ctx.tool_name,
            tool_implementation=ctx.tool_implementation,
            execution_log=ctx.execution_log,
            retry_count=ctx.retry_count,
            previous_hints=ctx.previous_hints if ctx.previous_hints else None,
            llm_provider="zai",
            llm_name="GLM-4.7",
        )

        ctx.assessment = assessment
        ctx.assessment_collector = collector
        ctx.assessment_duration = time.time() - start_time

        _logger.info(
            f"Assessment: diagnosis={assessment.diagnosis}, "
            f"recommendation={assessment.recommendation}, "
            f"confidence={assessment.confidence}"
        )
        _logger.info(f"Improvement hint: {assessment.improvement_hint[:200]}...")

        return ACCTrainingState.DECIDE_FATE, ctx

    except Exception as e:
        _logger.error(f"Error assessing tool: {e}")
        ctx.error_message = str(e)
        ctx.assessment_duration = time.time() - start_time
        return ACCTrainingState.ERROR, ctx


def handle_decide_fate(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Decide whether to retry or save the best tool."""
    _logger.info(f"Deciding tool fate (retry {ctx.retry_count}/{ctx.max_retries})...")

    assert ctx.assessment is not None

    if ctx.assessment.recommendation == "retry_with_hint" and ctx.retry_count < ctx.max_retries:
        # Retry with the improvement hint
        ctx.retry_count += 1
        ctx.improvement_hint = ctx.assessment.improvement_hint

        # Accumulate hints for context
        if ctx.previous_hints:
            ctx.previous_hints += f"\n\nAttempt {ctx.retry_count}:\n{ctx.improvement_hint}"
        else:
            ctx.previous_hints = f"Attempt {ctx.retry_count}:\n{ctx.improvement_hint}"

        hint_preview = ctx.improvement_hint[:100] if ctx.improvement_hint else "No hint"
        _logger.info(f"Retrying with hint: {hint_preview}...")
        return ACCTrainingState.CREATE_TOOL, ctx

    else:
        # Max retries reached or assessment says keep - save best tool
        _logger.info(
            f"Saving best tool (F1={ctx.best_tool_f1:.3f}, retries={ctx.retry_count})"
        )
        return ACCTrainingState.SAVE_TOOL, ctx


def handle_save_tool(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Save the best tool implementation."""
    _logger.info(f"Saving tool: {ctx.tool_name}")

    try:
        # Use best tool if available, otherwise current
        implementation = ctx.best_tool_implementation or ctx.tool_implementation

        if not implementation:
            _logger.warning("No tool implementation to save")
            return ACCTrainingState.END, ctx

        # Save to ACC tools directory
        save_success = save_new_tool(
            function_name=ctx.tool_name,
            function_implementation=implementation,
            directory_path=f"{ACC_TOOLS_PATH}",
            global_question_num=ctx.rule_idx,
        )

        if save_success:
            ctx.tool_saved = True
            _logger.info(f"Tool saved successfully: {ctx.tool_name}")
        else:
            _logger.error(f"Failed to save tool: {ctx.tool_name}")

        return ACCTrainingState.END, ctx

    except Exception as e:
        _logger.error(f"Error saving tool: {e}")
        ctx.error_message = str(e)
        return ACCTrainingState.ERROR, ctx


# ============================================================================
# State Machine Dispatcher
# ============================================================================


def process_state(state: ACCTrainingState, ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Route to appropriate state handler."""
    handlers = {
        ACCTrainingState.START: handle_start,
        ACCTrainingState.CREATE_TOOL: handle_create_tool,
        ACCTrainingState.VALIDATE_TOOL: handle_validate_tool,
        ACCTrainingState.ASSESS_GENERALIZABILITY: handle_assess_generalizability,
        ACCTrainingState.DECIDE_FATE: handle_decide_fate,
        ACCTrainingState.SAVE_TOOL: handle_save_tool,
    }

    handler = handlers.get(state)
    if handler:
        return handler(ctx)
    else:
        _logger.error(f"Unknown state: {state}")
        ctx.error_message = f"Unknown state: {state}"
        return ACCTrainingState.ERROR, ctx


def log_rule_metrics(ctx: ACCContext) -> dict:
    """Log metrics for a single rule to MLflow."""
    # Extract token metrics
    create_in, create_out, create_total = extract_token_metrics(ctx.create_tool_collector)
    assess_in, assess_out, assess_total = extract_token_metrics(ctx.assessment_collector)

    metrics = {
        "create_tool_duration": ctx.create_tool_duration,
        "create_tool_tokens": create_total,
        "validate_duration": ctx.validate_duration,
        "assessment_duration": ctx.assessment_duration,
        "assessment_tokens": assess_total,
        "total_tokens": create_total + assess_total,
        "total_duration": ctx.create_tool_duration + ctx.validate_duration + ctx.assessment_duration,
        "retry_count": ctx.retry_count,
        "tool_saved": 1 if ctx.tool_saved else 0,
        "error": 1 if ctx.error_message else 0,
    }

    # Add validation metrics if available
    if ctx.training_result:
        metrics.update({
            "training_tp": ctx.training_result.tp,
            "training_fp": ctx.training_result.fp,
            "training_fn": ctx.training_result.fn,
            "training_precision": ctx.training_result.precision,
            "training_recall": ctx.training_result.recall,
            "training_f1": ctx.training_result.f1,
        })

    if ctx.validation_result:
        metrics.update({
            "validation_tp": ctx.validation_result.tp,
            "validation_fp": ctx.validation_result.fp,
            "validation_fn": ctx.validation_result.fn,
            "validation_precision": ctx.validation_result.precision,
            "validation_recall": ctx.validation_result.recall,
            "validation_f1": ctx.validation_result.f1,
        })

    # Best tool F1
    metrics["best_f1"] = ctx.best_tool_f1

    # Assessment diagnosis if available
    if ctx.assessment:
        mlflow.set_tag("assessment_diagnosis", ctx.assessment.diagnosis)
        mlflow.set_tag("assessment_recommendation", ctx.assessment.recommendation)

    mlflow.log_metrics(metrics)

    return {
        "rule_title": ctx.rule_title,
        "tool_saved": ctx.tool_saved,
        "best_f1": ctx.best_tool_f1,
        "retry_count": ctx.retry_count,
        "error": bool(ctx.error_message),
        "total_tokens": create_total + assess_total,
        "total_duration": ctx.create_tool_duration + ctx.validate_duration + ctx.assessment_duration,
    }


def calculate_aggregate_metrics(results: list[dict]) -> dict:
    """Calculate aggregate metrics across all rules."""
    if not results:
        return {}

    total = len(results)
    saved = sum(1 for r in results if r.get("tool_saved"))
    errors = sum(1 for r in results if r.get("error"))
    total_retries = sum(r.get("retry_count", 0) for r in results)
    avg_f1 = sum(r.get("best_f1", 0) for r in results) / total if total > 0 else 0
    total_tokens = sum(r.get("total_tokens", 0) for r in results)
    total_duration = sum(r.get("total_duration", 0) for r in results)

    return {
        "total_rules": total,
        "tools_saved": saved,
        "errors": errors,
        "total_retries": total_retries,
        "avg_retries_per_rule": total_retries / total if total > 0 else 0,
        "avg_best_f1": avg_f1,
        "save_rate": saved / total if total > 0 else 0,
        "total_tokens": total_tokens,
        "total_duration": total_duration,
        "avg_tokens_per_rule": total_tokens / total if total > 0 else 0,
        "avg_duration_per_rule": total_duration / total if total > 0 else 0,
    }


# ============================================================================
# Main
# ============================================================================


def main():
    """Main ACC training loop."""
    parser = argparse.ArgumentParser(description="ACC Training Phase v2")
    parser.add_argument(
        "--start", type=int, default=0, help="Start rule index"
    )
    parser.add_argument(
        "--end", type=int, default=None, help="End rule index (exclusive)"
    )
    parser.add_argument(
        "--rules", type=str, nargs="+", default=None,
        help="Specific rule titles to train (overrides --start/--end)"
    )
    parser.add_argument(
        "--max-retries", type=int, default=2,
        help="Maximum retry attempts per rule (default: 2)"
    )
    args = parser.parse_args()

    # Get available rules from training ground truth
    all_rules = get_available_rules(TRAINING_MODEL)
    _logger.info(f"Found {len(all_rules)} rules in {TRAINING_MODEL} ground truth")

    # Determine rules to process
    if args.rules:
        rules_to_process = [(all_rules.index(r), r) for r in args.rules if r in all_rules]
    else:
        end_idx = args.end if args.end else len(all_rules)
        rules_to_process = [(i, all_rules[i]) for i in range(args.start, end_idx)]

    _logger.info(f"Processing {len(rules_to_process)} rules")

    # Setup MLflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("ACC_Training_v2")

    run_name = f"ACC_TRAIN_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"

    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({
            "training_model": TRAINING_MODEL,
            "validation_model": VALIDATION_MODEL,
            "max_retries": args.max_retries,
            "rules_count": len(rules_to_process),
        })

        results = []

        for rule_idx, rule_title in rules_to_process:
            _logger.info(f"\n{'=' * 80}")
            _logger.info(f"Processing rule {rule_idx + 1}/{len(rules_to_process)}: {rule_title}")
            _logger.info(f"{'=' * 80}")

            # Create nested run for this rule
            with mlflow.start_run(run_name=f"rule_{rule_idx}_{rule_title}", nested=True):
                mlflow.log_params({
                    "rule_title": rule_title,
                    "rule_index": rule_idx,
                })

                # Initialize context
                ctx = ACCContext(
                    rule_title=rule_title,
                    rule_idx=rule_idx,
                    max_retries=args.max_retries,
                )

                # Run state machine
                state = ACCTrainingState.START
                try:
                    with mlflow.start_span(name="ACCTraining", span_type="CHAIN"):
                        while state not in [ACCTrainingState.END, ACCTrainingState.ERROR]:
                            state, ctx = process_state(state, ctx)

                    # Log metrics
                    result = log_rule_metrics(ctx)
                    results.append(result)

                    if state == ACCTrainingState.ERROR:
                        _logger.error(f"Rule {rule_title} ended with error: {ctx.error_message}")
                        mlflow.set_tag("status", "ERROR")
                    else:
                        _logger.info(f"Rule {rule_title} completed successfully")
                        mlflow.set_tag("status", "success")

                except Exception as e:
                    _logger.error(f"Unexpected error processing {rule_title}: {e}", exc_info=True)
                    results.append({
                        "rule_title": rule_title,
                        "tool_saved": False,
                        "best_f1": 0,
                        "retry_count": 0,
                        "error": True,
                        "total_tokens": 0,
                        "total_duration": 0,
                    })
                    mlflow.set_tag("status", "exception")

        # Log aggregate metrics
        aggregate = calculate_aggregate_metrics(results)
        if aggregate:
            mlflow.log_metrics(aggregate)

        _logger.info(f"\n{'=' * 80}")
        _logger.info("ACC Training Phase Complete")
        _logger.info(f"{'=' * 80}")
        _logger.info(f"Total rules: {aggregate.get('total_rules', 0)}")
        _logger.info(f"Tools saved: {aggregate.get('tools_saved', 0)}")
        _logger.info(f"Errors: {aggregate.get('errors', 0)}")
        _logger.info(f"Average best F1: {aggregate.get('avg_best_f1', 0):.3f}")
        _logger.info(f"Save rate: {aggregate.get('save_rate', 0):.2%}")


if __name__ == "__main__":
    main()
