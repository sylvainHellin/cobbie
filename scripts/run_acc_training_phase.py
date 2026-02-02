# Example usage:
#   uv run scripts/run_acc_training_phase.py --rules 304_3_1_circular_space
#   uv run scripts/run_acc_training_phase.py --start 0 --end 5
#   uv run scripts/run_acc_training_phase.py --start 0 --end 5 --max-retries 3

"""
ACC Training Phase v2 - GUID-Based Validation (Multi-Model)

This script implements the ACC training flow with direct GUID-based validation
instead of Cobbie-based Q&A verification.

Training Flow:
    START -> CREATE_TOOL -> VALIDATE_TOOL
        -> [F1=1.0] -> SAVE_TOOL -> TEST_TOOL -> END
        -> [F1<1.0] -> ASSESS_GENERALIZABILITY -> DECIDE_FATE
            -> [retry_with_hint & retries < max] -> CREATE_TOOL (loop)
            -> [retries exhausted] -> SAVE_BEST_TOOL -> TEST_TOOL -> END

Data Split (from acc/config/model_splits.json):
    - Training: all models from 'train' split (ground truth loaded per-model)
    - Validation: all models from 'validate' split (ground truth loaded per-model)
    - Test: all models from 'test' split (ground truth loaded per-model; optional)
    - Rules: from acc/config/rule_templates.json
"""

import argparse
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Tuple

import mlflow
from baml_py.baml_py import Collector
from loguru import logger
from src.baml.baml_client.types import ACCToolAssessment, NewHelperFunction
from src.agents.assess_acc_tool import assess_acc_tool
from src.agents.create_acc_function import create_helper_function
from src.acc.guid_comparison import (
    GUIDComparisonResult,
    compare_guids,
    get_rule_context,
    get_model_path,
    load_rule_templates,
    load_model_splits,
)
from src.config import ACC_TOOLS_PATH, get_boilerplate, get_library_docs
from src.tools.initial import classify_spaces, query_ifcopenshell_docs
from src.util import setup_logger, save_new_tool

# Tools available to ACC tools at execution time (same as during creation)
ACC_EXECUTION_TOOLS = {
    "query_ifcopenshell_docs": query_ifcopenshell_docs,
    "classify_spaces": classify_spaces,
}

# Initialize logger
setup_logger()


class ACCTrainingState(Enum):
    """State machine states for ACC training."""

    START = auto()
    LOAD_TOOLS = auto()
    CREATE_TOOL = auto()
    VALIDATE_TOOL = auto()
    ASSESS_GENERALIZABILITY = auto()
    DECIDE_FATE = auto()
    SAVE_TOOL = auto()
    TEST_TOOL = auto()
    END = auto()
    ERROR = auto()


@dataclass
class ACCContext:
    """Context object for ACC training state machine."""

    # Rule identification
    rule_title: str
    rule_idx: int  # Index in the rules list

    # Rule context from ground truth / templates
    rule_code: str = ""
    rule_description: str = ""
    question: str = ""
    parameters: str = ""

    # Training data (all train models)
    training_models: list[str] = field(default_factory=list)
    training_model_paths: dict[str, str] = field(default_factory=dict)  # name -> ifc path
    training_ground_truth: dict[str, list[dict]] = field(default_factory=dict)  # name -> list of issue dicts
    training_guids_per_model: dict[str, list[str]] = field(default_factory=dict)  # name -> required GUIDs
    primary_training_model: str = ""

    # Per-model training results
    training_results_per_model: dict[str, GUIDComparisonResult] = field(default_factory=dict)
    training_result_aggregated: Optional[GUIDComparisonResult] = None  # combined TP/FP/FN
    training_result_avg_f1: float = 0.0  # mean per-model F1

    # Validation data (all models from validate split)
    validation_models: list[str] = field(default_factory=list)
    validation_model_paths: dict[str, str] = field(default_factory=dict)  # name -> ifc path
    validation_guids_per_model: dict[str, list[str]] = field(default_factory=dict)  # name -> expected GUIDs
    validation_results_per_model: dict[str, GUIDComparisonResult] = field(default_factory=dict)
    validation_result_aggregated: Optional[GUIDComparisonResult] = None  # combined TP/FP/FN
    validation_result_avg_f1: float = 0.0  # mean per-model F1

    # Test data (all models from test split)
    test_models: list[str] = field(default_factory=list)
    test_model_paths: dict[str, str] = field(default_factory=dict)  # name -> ifc path
    test_guids_per_model: dict[str, list[str]] = field(default_factory=dict)  # name -> expected GUIDs
    test_results_per_model: dict[str, GUIDComparisonResult] = field(default_factory=dict)
    test_result_aggregated: Optional[GUIDComparisonResult] = None
    test_result_avg_f1: float = 0.0
    test_duration: float = 0.0

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
    max_iterations: int = 20

    # Best tool tracking
    best_tool_implementation: str = ""
    best_tool_f1: float = 0.0

    # Feature flags / boilerplate
    boilerplate: Optional[str] = None
    no_classification: bool = False
    available_tools_docs: Optional[str] = None
    available_library_docs: Optional[str] = None

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
        logger.warning(f"Error extracting token usage: {e}")

    return 0, 0, 0


# ============================================================================
# State Handlers
# ============================================================================


def handle_start(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Initialize context with rule data from ground truth across all train models."""
    logger.info(f"Starting ACC training for rule: {ctx.rule_title}")

    try:
        # Load ground truth from each train model for this rule
        for model_name in ctx.training_models:
            try:
                rule_data = get_rule_context(model_name, ctx.rule_title)
            except KeyError:
                logger.info(f"Rule '{ctx.rule_title}' not found in {model_name} — skipping")
                continue

            # Use rule metadata from first successful model (same across models)
            if not ctx.rule_code:
                ctx.rule_code = rule_data["rule_code"]
                ctx.rule_description = rule_data["rule_description"]
                ctx.question = rule_data["question"]
                ctx.parameters = rule_data["parameters"]

            # Store full issue list and extract required GUIDs
            ctx.training_ground_truth[model_name] = rule_data.get("issues", [])
            guids: list[str] = []
            for issue in ctx.training_ground_truth[model_name]:
                guids.extend(issue.get("required_guids", []))
            ctx.training_guids_per_model[model_name] = list(dict.fromkeys(guids))  # unique, order-preserving

            # Resolve IFC path
            model_path = get_model_path(model_name)
            if model_path:
                ctx.training_model_paths[model_name] = model_path
            else:
                logger.warning(f"Could not find IFC model for {model_name}")

        if not ctx.training_ground_truth:
            raise ValueError(f"Rule '{ctx.rule_title}' not found in any training model")

        # Pick primary model = one with the most issues
        ctx.primary_training_model = max(
            ctx.training_ground_truth,
            key=lambda m: len(ctx.training_ground_truth[m]),
        )

        # Load validation ground truth for all validate models (same pattern as training)
        for model_name in ctx.validation_models:
            try:
                rule_data = get_rule_context(model_name, ctx.rule_title)
            except KeyError:
                logger.info(f"Rule '{ctx.rule_title}' not found in validation model {model_name} — skipping")
                continue

            guids: list[str] = []
            for issue in rule_data.get("issues", []):
                guids.extend(issue.get("required_guids", []))
            ctx.validation_guids_per_model[model_name] = list(dict.fromkeys(guids))

            model_path = get_model_path(model_name)
            if model_path:
                ctx.validation_model_paths[model_name] = model_path
            else:
                logger.warning(f"Could not find IFC model for validation model {model_name}")

        if not ctx.validation_guids_per_model:
            raise ValueError(f"Rule '{ctx.rule_title}' not found in any validation model")

        # Load test ground truth for all test models (same pattern as validation; optional)
        for model_name in ctx.test_models:
            try:
                rule_data = get_rule_context(model_name, ctx.rule_title)
            except KeyError:
                logger.info(f"Rule '{ctx.rule_title}' not found in test model {model_name} — skipping")
                continue

            guids = []
            for issue in rule_data.get("issues", []):
                guids.extend(issue.get("required_guids", []))
            ctx.test_guids_per_model[model_name] = list(dict.fromkeys(guids))

            model_path = get_model_path(model_name)
            if model_path:
                ctx.test_model_paths[model_name] = model_path
            else:
                logger.warning(f"Could not find IFC model for test model {model_name}")

        if not ctx.test_guids_per_model:
            logger.warning("No test ground truth loaded — test phase will be skipped")

        # Generate tool name from rule title
        ctx.tool_name = f"check_{ctx.rule_title}"

        logger.info(f"Rule: {ctx.rule_code} - {ctx.rule_title}")
        logger.info(f"Primary training model: {ctx.primary_training_model}")
        for m in ctx.training_ground_truth:
            logger.info(f"  {m}: {len(ctx.training_ground_truth[m])} issues, "
                         f"{len(ctx.training_guids_per_model.get(m, []))} GUIDs")
        for m in ctx.validation_guids_per_model:
            logger.info(f"  Validation {m}: {len(ctx.validation_guids_per_model[m])} GUIDs")

        return ACCTrainingState.CREATE_TOOL, ctx

    except Exception as e:
        logger.error(f"Error in START state: {e}")
        ctx.error_message = str(e)
        return ACCTrainingState.ERROR, ctx


def _build_expected_answer(ctx: ACCContext) -> str:
    """Build per-model expected answer string with rich context for the LLM."""
    parts: list[str] = []

    for model_name in ctx.training_ground_truth:
        issues = ctx.training_ground_truth[model_name]
        is_primary = model_name == ctx.primary_training_model
        label = f"Model: {model_name}" + (" (primary)" if is_primary else "")
        parts.append(label)

        if not issues:
            parts.append("Issues (0): pass (no violations expected, tool should return [])")
        else:

            set_of_required_guids = ctx.training_guids_per_model[model_name]
            parts.append(f"Set of required GUIDs (tool must return these): {set_of_required_guids}")
            parts.append("Detailed description of the issues:")
            parts.append(f"Issues ({len(issues)}):")
            for issue in issues:
                title = issue.get("title", "")
                description = issue.get("description", "")
                all_guids = issue.get("all_guids", [])
                required_guids = issue.get("required_guids", [])
                parts.append(f'- "{title}": {description}')
                parts.append(f"  All GUIDs: {all_guids}")
                parts.append(f"  Required GUIDs: {required_guids}")

        parts.append("")  # blank line between models

    return "\n".join(parts)


def handle_create_tool(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Create or retry creating the ACC tool."""
    action = "Retrying" if ctx.retry_count > 0 else "Creating"
    logger.info(f"{action} tool: {ctx.tool_name} (attempt {ctx.retry_count + 1}/{ctx.max_retries + 1})")

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

        # Build per-model expected answer with rich context
        expected_answer = _build_expected_answer(ctx)

        # Primary model path for example_bim_model, others for testing
        primary_path = ctx.training_model_paths.get(ctx.primary_training_model, "")
        other_paths = [
            path for name, path in ctx.training_model_paths.items()
            if name != ctx.primary_training_model
        ]

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
            example_bim_model=primary_path,
            function_name=ctx.tool_name,
            function_description=full_question,
            other_bim_models_for_testing=other_paths,
            max_iterations=ctx.max_iterations,
            llm_provider="zai",
            llm_name="GLM-4.7",
            boilerplate=ctx.boilerplate,
            no_classification=ctx.no_classification,
            available_tools_docs=ctx.available_tools_docs,
            available_library_docs=ctx.available_library_docs,
        )

        ctx.create_tool_result = result
        ctx.create_tool_collector = collector
        ctx.create_tool_history = creation_history
        ctx.create_tool_duration = time.time() - start_time

        if result.function_implementation:
            ctx.tool_implementation = result.function_implementation
            if result.success:
                logger.info(f"Tool creation succeeded in {ctx.create_tool_duration:.1f}s")
            else:
                logger.info(
                    f"Tool creation did not converge in {ctx.create_tool_duration:.1f}s, "
                    f"proceeding with last extracted implementation"
                )

            # Pre-check: try executing on primary model before full validation
            _, exec_log = _execute_tool(ctx.tool_implementation, ctx.tool_name, primary_path, boilerplate=ctx.boilerplate)
            is_crash = exec_log.startswith("Failed to create function:") or exec_log.startswith("Execution error:")
            if is_crash:
                logger.warning("Pre-check failed, retrying CREATE_TOOL without consuming a retry")
                ctx.improvement_hint = f"The implementation crashed during execution:\n{exec_log}"
                if ctx.previous_hints:
                    ctx.previous_hints += f"\n\nPre-check failure:\n{exec_log}"
                else:
                    ctx.previous_hints = f"Pre-check failure:\n{exec_log}"
                return ACCTrainingState.CREATE_TOOL, ctx

            return ACCTrainingState.VALIDATE_TOOL, ctx
        else:
            logger.warning(f"Tool creation failed with no implementation: {result.thoughts}")
            ctx.error_message = f"Tool creation failed: {result.thoughts}"
            return ACCTrainingState.ERROR, ctx

    except Exception as e:
        logger.error(f"Error creating tool: {e}")
        ctx.error_message = str(e)
        ctx.create_tool_duration = time.time() - start_time
        return ACCTrainingState.ERROR, ctx


def _execute_tool(
    tool_implementation: str,
    function_name: str,
    model_path: str,
    boilerplate: Optional[str] = None,
    tools: Optional[dict] = None,
) -> Tuple[list[str], str]:
    """
    Execute an ACC tool and return predicted GUIDs and execution log.

    Uses InteractiveInterpreter (same as creation-time) so that helpers,
    constants, and the main function all share a single namespace.
    Tools (classify_spaces, query_ifcopenshell_docs) are injected so generated
    code can call them.

    Returns:
        Tuple of (predicted_guids, execution_log)
    """
    from src.util.python_executor import setup_interpreter, execute_python

    exec_tools = tools if tools is not None else ACC_EXECUTION_TOOLS

    try:
        interpreter = setup_interpreter(
            model_path=model_path, tools=exec_tools, boilerplate=boilerplate
        )

        # Load the full tool code (including helpers/constants) into the interpreter
        load_log = execute_python(
            tool_implementation, tools=exec_tools, interpreter=interpreter
        )

        # Call the main function with path_ifc_model (already set by setup_interpreter)
        call_code = f"_result = {function_name}(path_ifc_model)"
        call_log = execute_python(call_code, tools=exec_tools, interpreter=interpreter)

        log = load_log + "\n" + call_log

        # Retrieve result from the interpreter namespace
        if "_result" not in interpreter.locals:
            return [], f"Execution error: function did not produce a result\n{log}"

        result = interpreter.locals["_result"]

        if isinstance(result, list):
            predicted = [str(g) for g in result]
        else:
            predicted = []

        return predicted, log

    except Exception as e:
        return [], f"Execution error: {e}"


def handle_validate_tool(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Execute tool on all training models and validation model, compare GUIDs."""
    logger.info("Validating tool on training models and validation model...")

    start_time = time.time()

    try:
        # --- Training: run on all train models ---
        log_parts: list[str] = []
        total_tp, total_fp, total_fn = 0, 0, 0
        f1_scores: list[float] = []

        for model_name in ctx.training_ground_truth:
            model_path = ctx.training_model_paths.get(model_name, "")
            if not model_path:
                logger.warning(f"No IFC path for training model {model_name} — skipping validation")
                continue

            predicted, run_log = _execute_tool(ctx.tool_implementation, ctx.tool_name, model_path, boilerplate=ctx.boilerplate)
            expected = ctx.training_guids_per_model.get(model_name, [])
            result = compare_guids(set(predicted), set(expected))

            ctx.training_results_per_model[model_name] = result
            total_tp += result.tp
            total_fp += result.fp
            total_fn += result.fn
            f1_scores.append(result.f1)

            logger.info(
                f"  Training [{model_name}]: TP={result.tp}, FP={result.fp}, "
                f"FN={result.fn}, F1={result.f1:.3f}"
            )
            log_parts.append(f"=== Training ({model_name}) ===\n{run_log}")

        # Aggregated training result from summed TP/FP/FN
        agg_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else (1.0 if total_fn == 0 else 0.0)
        agg_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else (1.0 if total_fp == 0 else 0.0)
        agg_f1 = (2 * agg_precision * agg_recall / (agg_precision + agg_recall)
                  if (agg_precision + agg_recall) > 0 else 0.0)
        # Handle all-empty case (all models are pass rules)
        if total_tp == 0 and total_fp == 0 and total_fn == 0:
            agg_f1 = 1.0

        ctx.training_result_aggregated = GUIDComparisonResult(
            tp=total_tp, fp=total_fp, fn=total_fn,
            precision=agg_precision, recall=agg_recall, f1=agg_f1,
            is_perfect_match=(total_fp == 0 and total_fn == 0),
        )
        ctx.training_result_avg_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 0.0

        logger.info(
            f"Training aggregated: TP={total_tp}, FP={total_fp}, FN={total_fn}, "
            f"F1_agg={agg_f1:.3f}, F1_avg={ctx.training_result_avg_f1:.3f}"
        )

        # --- Validation: run on all validate models ---
        val_total_tp, val_total_fp, val_total_fn = 0, 0, 0
        val_f1_scores: list[float] = []

        for model_name in ctx.validation_guids_per_model:
            model_path = ctx.validation_model_paths.get(model_name, "")
            if not model_path:
                logger.warning(f"No IFC path for validation model {model_name} — skipping")
                continue

            predicted, run_log = _execute_tool(ctx.tool_implementation, ctx.tool_name, model_path, boilerplate=ctx.boilerplate)
            expected = ctx.validation_guids_per_model.get(model_name, [])
            result = compare_guids(set(predicted), set(expected))

            ctx.validation_results_per_model[model_name] = result
            val_total_tp += result.tp
            val_total_fp += result.fp
            val_total_fn += result.fn
            val_f1_scores.append(result.f1)

            logger.info(
                f"  Validation [{model_name}]: TP={result.tp}, FP={result.fp}, "
                f"FN={result.fn}, F1={result.f1:.3f}"
            )
            log_parts.append(f"=== Validation ({model_name}) ===\n{run_log}")

        # Aggregated validation result
        val_precision = val_total_tp / (val_total_tp + val_total_fp) if (val_total_tp + val_total_fp) > 0 else (1.0 if val_total_fn == 0 else 0.0)
        val_recall = val_total_tp / (val_total_tp + val_total_fn) if (val_total_tp + val_total_fn) > 0 else (1.0 if val_total_fp == 0 else 0.0)
        val_f1 = (2 * val_precision * val_recall / (val_precision + val_recall)
                  if (val_precision + val_recall) > 0 else 0.0)
        if val_total_tp == 0 and val_total_fp == 0 and val_total_fn == 0:
            val_f1 = 1.0

        ctx.validation_result_aggregated = GUIDComparisonResult(
            tp=val_total_tp, fp=val_total_fp, fn=val_total_fn,
            precision=val_precision, recall=val_recall, f1=val_f1,
            is_perfect_match=(val_total_fp == 0 and val_total_fn == 0),
        )
        ctx.validation_result_avg_f1 = sum(val_f1_scores) / len(val_f1_scores) if val_f1_scores else 0.0

        ctx.execution_log = "\n\n".join(log_parts)
        ctx.validate_duration = time.time() - start_time

        logger.info(
            f"Validation aggregated: TP={val_total_tp}, FP={val_total_fp}, FN={val_total_fn}, "
            f"F1_agg={val_f1:.3f}, F1_avg={ctx.validation_result_avg_f1:.3f}"
        )

        # Track best tool by aggregated validation F1
        if val_f1 > ctx.best_tool_f1:
            ctx.best_tool_f1 = val_f1
            ctx.best_tool_implementation = ctx.tool_implementation
            logger.info(f"New best tool! Aggregated validation F1={ctx.best_tool_f1:.3f}")

        # Check for perfect validation match
        if val_f1 == 1.0:
            logger.info("Perfect validation F1=1.0 - saving tool immediately")
            return ACCTrainingState.SAVE_TOOL, ctx

        # Not perfect - assess and potentially retry
        return ACCTrainingState.ASSESS_GENERALIZABILITY, ctx

    except Exception as e:
        logger.error(f"Error validating tool: {e}")
        ctx.error_message = str(e)
        ctx.validate_duration = time.time() - start_time
        return ACCTrainingState.ERROR, ctx


def handle_assess_generalizability(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Assess why the tool failed on validation and get improvement hints."""
    logger.info("Assessing tool generalizability...")

    start_time = time.time()

    try:
        assert ctx.training_result_aggregated is not None
        assert ctx.validation_result_aggregated is not None

        # Flatten training GUIDs across all models for the assessment API
        all_training_expected: list[str] = []
        for guids in ctx.training_guids_per_model.values():
            all_training_expected.extend(guids)

        # Compute aggregated validation expected/predicted counts
        val_expected_count = sum(len(g) for g in ctx.validation_guids_per_model.values())
        val_predicted_count = sum(r.tp + r.fp for r in ctx.validation_results_per_model.values())

        assessment, collector = assess_acc_tool(
            rule_title=ctx.rule_title,
            rule_code=ctx.rule_code,
            rule_description=ctx.rule_description,
            question=ctx.question,
            training_model_name=ctx.primary_training_model,
            training_expected_guids=all_training_expected,
            training_predicted_guids=[],  # not tracked per-model; aggregated metrics used
            training_tp=ctx.training_result_aggregated.tp,
            training_fp=ctx.training_result_aggregated.fp,
            training_fn=ctx.training_result_aggregated.fn,
            training_f1=ctx.training_result_aggregated.f1,
            validation_model_name=",".join(ctx.validation_results_per_model.keys()),
            validation_expected_count=val_expected_count,
            validation_predicted_count=val_predicted_count,
            validation_tp=ctx.validation_result_aggregated.tp,
            validation_fp=ctx.validation_result_aggregated.fp,
            validation_fn=ctx.validation_result_aggregated.fn,
            validation_f1=ctx.validation_result_aggregated.f1,
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

        logger.info(
            f"Assessment: diagnosis={assessment.diagnosis}, "
            f"recommendation={assessment.recommendation}, "
            f"confidence={assessment.confidence}"
        )
        logger.info(f"Improvement hint: {assessment.improvement_hint[:200]}...")

        return ACCTrainingState.DECIDE_FATE, ctx

    except Exception as e:
        logger.error(f"Error assessing tool: {e}")
        ctx.error_message = str(e)
        ctx.assessment_duration = time.time() - start_time
        return ACCTrainingState.ERROR, ctx


def handle_decide_fate(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Decide whether to retry or save the best tool."""
    logger.info(f"Deciding tool fate (retry {ctx.retry_count}/{ctx.max_retries})...")

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
        logger.info(f"Retrying with hint: {hint_preview}...")
        return ACCTrainingState.CREATE_TOOL, ctx

    else:
        # Max retries reached or assessment says keep - save best tool
        logger.info(
            f"Saving best tool (F1={ctx.best_tool_f1:.3f}, retries={ctx.retry_count})"
        )
        return ACCTrainingState.SAVE_TOOL, ctx


def handle_save_tool(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Save the best tool implementation."""
    logger.info(f"Saving tool: {ctx.tool_name}")

    try:
        # Use best tool if available, otherwise current
        implementation = ctx.best_tool_implementation or ctx.tool_implementation

        if not implementation:
            logger.warning("No tool implementation to save")
            return ACCTrainingState.TEST_TOOL, ctx

        # Save to ACC tools directory
        save_success = save_new_tool(
            function_name=ctx.tool_name,
            function_implementation=implementation,
            directory_path=f"{ACC_TOOLS_PATH}",
            global_question_num=ctx.rule_idx,
        )

        if save_success:
            ctx.tool_saved = True
            logger.info(f"Tool saved successfully: {ctx.tool_name}")
        else:
            logger.error(f"Failed to save tool: {ctx.tool_name}")

        return ACCTrainingState.TEST_TOOL, ctx

    except Exception as e:
        logger.error(f"Error saving tool: {e}")
        ctx.error_message = str(e)
        return ACCTrainingState.ERROR, ctx


def handle_test_tool(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Run final tool on all test models; always transition to END."""
    if not ctx.test_guids_per_model:
        logger.info("No test ground truth — skipping test phase")
        return ACCTrainingState.END, ctx

    implementation = ctx.best_tool_implementation or ctx.tool_implementation
    if not implementation:
        logger.info("No tool implementation saved — skipping test phase")
        return ACCTrainingState.END, ctx

    logger.info("Running tool on test split...")
    start_time = time.time()

    test_total_tp, test_total_fp, test_total_fn = 0, 0, 0
    test_f1_scores: list[float] = []

    for model_name in ctx.test_guids_per_model:
        model_path = ctx.test_model_paths.get(model_name, "")
        if not model_path:
            logger.warning(f"No IFC path for test model {model_name} — skipping")
            continue

        predicted, _ = _execute_tool(implementation, ctx.tool_name, model_path, boilerplate=ctx.boilerplate)
        expected = ctx.test_guids_per_model.get(model_name, [])
        result = compare_guids(set(predicted), set(expected))

        ctx.test_results_per_model[model_name] = result
        test_total_tp += result.tp
        test_total_fp += result.fp
        test_total_fn += result.fn
        test_f1_scores.append(result.f1)

        logger.info(
            f"  Test [{model_name}]: TP={result.tp}, FP={result.fp}, "
            f"FN={result.fn}, F1={result.f1:.3f}"
        )

    test_precision = (
        test_total_tp / (test_total_tp + test_total_fp)
        if (test_total_tp + test_total_fp) > 0
        else (1.0 if test_total_fn == 0 else 0.0)
    )
    test_recall = (
        test_total_tp / (test_total_tp + test_total_fn)
        if (test_total_tp + test_total_fn) > 0
        else (1.0 if test_total_fp == 0 else 0.0)
    )
    test_f1 = (
        2 * test_precision * test_recall / (test_precision + test_recall)
        if (test_precision + test_recall) > 0
        else 0.0
    )
    if test_total_tp == 0 and test_total_fp == 0 and test_total_fn == 0:
        test_f1 = 1.0

    ctx.test_result_aggregated = GUIDComparisonResult(
        tp=test_total_tp,
        fp=test_total_fp,
        fn=test_total_fn,
        precision=test_precision,
        recall=test_recall,
        f1=test_f1,
        is_perfect_match=(test_total_fp == 0 and test_total_fn == 0),
    )
    ctx.test_result_avg_f1 = sum(test_f1_scores) / len(test_f1_scores) if test_f1_scores else 0.0
    ctx.test_duration = time.time() - start_time

    logger.info(
        f"Test aggregated: TP={test_total_tp}, FP={test_total_fp}, FN={test_total_fn}, "
        f"F1_agg={test_f1:.3f}, F1_avg={ctx.test_result_avg_f1:.3f}"
    )

    return ACCTrainingState.END, ctx


def handle_error(ctx: ACCContext) -> Tuple[ACCTrainingState, ACCContext]:
    """Recover from infrastructure errors by retrying or saving best tool."""
    if ctx.retry_count < ctx.max_retries:
        ctx.retry_count += 1
        logger.warning(
            f"Error recovery: retrying CREATE_TOOL "
            f"(attempt {ctx.retry_count + 1}/{ctx.max_retries + 1}). "
            f"Error was: {ctx.error_message}"
        )
        ctx.error_message = None
        return ACCTrainingState.CREATE_TOOL, ctx

    logger.warning(
        f"Retries exhausted ({ctx.retry_count}/{ctx.max_retries}). "
        f"Error: {ctx.error_message}"
    )
    if ctx.best_tool_implementation:
        return ACCTrainingState.SAVE_TOOL, ctx
    return ACCTrainingState.END, ctx


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
        ACCTrainingState.TEST_TOOL: handle_test_tool,
        ACCTrainingState.ERROR: handle_error,
    }

    handler = handlers.get(state)
    if handler:
        return handler(ctx)
    else:
        logger.error(f"Unknown state: {state}")
        ctx.error_message = f"Unknown state: {state}"
        return ACCTrainingState.ERROR, ctx


def log_rule_metrics(ctx: ACCContext) -> dict:
    """Log metrics for a single rule to MLflow."""
    # Extract token metrics
    _, _, create_total = extract_token_metrics(ctx.create_tool_collector)
    _, _, assess_total = extract_token_metrics(ctx.assessment_collector)

    metrics: dict[str, float] = {
        "create_tool_duration": ctx.create_tool_duration,
        "create_tool_tokens": create_total,
        "validate_duration": ctx.validate_duration,
        "assessment_duration": ctx.assessment_duration,
        "assessment_tokens": assess_total,
        "test_duration": ctx.test_duration,
        "total_tokens": create_total + assess_total,
        "total_duration": ctx.create_tool_duration + ctx.validate_duration + ctx.assessment_duration + ctx.test_duration,
        "retry_count": ctx.retry_count,
        "tool_saved": 1 if ctx.tool_saved else 0,
        "error": 1 if ctx.error_message else 0,
    }

    # Add aggregated training metrics
    if ctx.training_result_aggregated:
        metrics.update({
            "training_f1_aggregated": ctx.training_result_aggregated.f1,
            "training_f1_avg": ctx.training_result_avg_f1,
            "training_tp": ctx.training_result_aggregated.tp,
            "training_fp": ctx.training_result_aggregated.fp,
            "training_fn": ctx.training_result_aggregated.fn,
            "training_precision": ctx.training_result_aggregated.precision,
            "training_recall": ctx.training_result_aggregated.recall,
        })

    # Per-model training metrics
    for model_name, result in ctx.training_results_per_model.items():
        metrics[f"training_f1_{model_name}"] = result.f1
        metrics[f"training_precision_{model_name}"] = result.precision
        metrics[f"training_recall_{model_name}"] = result.recall

    # Aggregated validation metrics
    if ctx.validation_result_aggregated:
        metrics.update({
            "validation_f1_aggregated": ctx.validation_result_aggregated.f1,
            "validation_precision_aggregated": ctx.validation_result_aggregated.precision,
            "validation_recall_aggregated": ctx.validation_result_aggregated.recall,
            "validation_f1_avg": ctx.validation_result_avg_f1,
            "validation_tp": ctx.validation_result_aggregated.tp,
            "validation_fp": ctx.validation_result_aggregated.fp,
            "validation_fn": ctx.validation_result_aggregated.fn,
        })

    # Per-model validation metrics
    for model_name, result in ctx.validation_results_per_model.items():
        metrics[f"validation_f1_{model_name}"] = result.f1
        metrics[f"validation_precision_{model_name}"] = result.precision
        metrics[f"validation_recall_{model_name}"] = result.recall

    # Aggregated test metrics
    if ctx.test_result_aggregated:
        metrics.update({
            "test_f1_aggregated": ctx.test_result_aggregated.f1,
            "test_precision_aggregated": ctx.test_result_aggregated.precision,
            "test_recall_aggregated": ctx.test_result_aggregated.recall,
            "test_f1_avg": ctx.test_result_avg_f1,
            "test_tp": ctx.test_result_aggregated.tp,
            "test_fp": ctx.test_result_aggregated.fp,
            "test_fn": ctx.test_result_aggregated.fn,
        })

    # Per-model test metrics
    for model_name, result in ctx.test_results_per_model.items():
        metrics[f"test_f1_{model_name}"] = result.f1
        metrics[f"test_precision_{model_name}"] = result.precision
        metrics[f"test_recall_{model_name}"] = result.recall

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
        "total_duration": ctx.create_tool_duration + ctx.validate_duration + ctx.assessment_duration + ctx.test_duration,
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
        "--max-retries", type=int, default=1,
        help="Maximum retry attempts per rule (default: 1)"
    )
    parser.add_argument(
        "--max-iterations", type=int, default=15,
        help="Maximum number of iterations per rule (default: 15)"
    )
    parser.add_argument(
        "--no-geometry", action="store_true",
        help="Disable both trimesh and shapely (shorthand for --no-trimesh --no-shapely)"
    )
    parser.add_argument(
        "--no-trimesh", action="store_true",
        help="Disable trimesh imports and documentation in tool creation"
    )
    parser.add_argument(
        "--no-shapely", action="store_true",
        help="Disable shapely imports and documentation in tool creation"
    )
    parser.add_argument(
        "--no-classification", action="store_true",
        help="Disable the classify_spaces tool during tool creation"
    )
    args = parser.parse_args()

    # Compute feature flags
    no_trimesh = args.no_geometry or args.no_trimesh
    no_shapely = args.no_geometry or args.no_shapely
    no_classification: bool = args.no_classification
    boilerplate = get_boilerplate(no_trimesh=no_trimesh, no_shapely=no_shapely)
    library_docs = get_library_docs(no_trimesh=no_trimesh, no_shapely=no_shapely)

    # Load splits and rule templates
    splits = load_model_splits()
    train_models = splits["train"]
    validate_models = splits["validate"]
    test_models = splits["test"]

    templates = load_rule_templates()
    all_rules = [tmpl["rule_title"] for tmpl in templates.values()]
    logger.info(f"Found {len(all_rules)} rules from rule_templates.json")
    logger.info(f"Train models: {train_models}")
    logger.info(f"Validation models: {validate_models}")
    logger.info(f"Test models: {test_models}")

    # Determine rules to process
    if args.rules:
        rules_to_process = [(all_rules.index(r), r) for r in args.rules if r in all_rules]
    else:
        end_idx = args.end if args.end else len(all_rules)
        rules_to_process = [(i, all_rules[i]) for i in range(args.start, end_idx)]

    logger.info(f"Processing {len(rules_to_process)} rules")

    # Setup MLflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("ACC_Training_v2")

    run_name = f"ACC_TRAIN_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"

    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({
            "training_models": ",".join(train_models),
            "validation_models": ",".join(validate_models),
            "test_models": ",".join(test_models),
            "max_retries": args.max_retries,
            "max_iterations": args.max_iterations,
            "rules_count": len(rules_to_process),
            "no_trimesh": no_trimesh,
            "no_shapely": no_shapely,
            "no_classification": no_classification,
        })

        results = []

        for rule_idx, rule_title in rules_to_process:
            logger.info(f"\n{'=' * 80}")
            logger.info(f"Processing rule {rule_idx + 1}/{len(rules_to_process)}: {rule_title}")
            logger.info(f"{'=' * 80}")

            # Create nested run for this rule
            with mlflow.start_run(run_name=f"rule_{rule_idx}_{rule_title}", nested=True):
                mlflow.log_params({
                    "rule_title": rule_title,
                    "rule_index": rule_idx,
                })

                # Initialize context with train/validate/test models
                ctx = ACCContext(
                    rule_title=rule_title,
                    rule_idx=rule_idx,
                    max_retries=args.max_retries,
                    training_models=train_models,
                    validation_models=validate_models,
                    test_models=test_models,
                    max_iterations=args.max_iterations,
                    boilerplate=boilerplate,
                    no_classification=no_classification,
                    available_tools_docs=None,
                    available_library_docs=library_docs if library_docs else None,
                )

                # Run state machine
                state = ACCTrainingState.START
                try:
                    with mlflow.start_span(name="ACCTraining", span_type="CHAIN"):
                        while state != ACCTrainingState.END:
                            state, ctx = process_state(state, ctx)

                    # Log metrics
                    result = log_rule_metrics(ctx)
                    results.append(result)

                    logger.info(f"Rule {rule_title} completed successfully")
                    mlflow.set_tag("status", "success")

                except Exception as e:
                    logger.error(f"Unexpected error processing {rule_title}: {e}", exc_info=True)
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

        logger.info(f"\n{'=' * 80}")
        logger.info("ACC Training Phase Complete")
        logger.info(f"{'=' * 80}")
        logger.info(f"Total rules: {aggregate.get('total_rules', 0)}")
        logger.info(f"Tools saved: {aggregate.get('tools_saved', 0)}")
        logger.info(f"Errors: {aggregate.get('errors', 0)}")
        logger.info(f"Average best F1: {aggregate.get('avg_best_f1', 0):.3f}")
        logger.info(f"Save rate: {aggregate.get('save_rate', 0):.2%}")


if __name__ == "__main__":
    main()
