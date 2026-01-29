"""
Agent that assesses ACC tool generalizability.
Analyzes why an ACC compliance tool fails on validation data and provides improvement guidance.
"""

import time
from typing import Optional, Tuple

import mlflow
from baml_py.baml_py import Collector
from baml_client import b
from baml_client.types import ACCToolAssessment
from src.config import LOG_LEVEL
from src.util import get_logger

# Initialize logger
_logger = get_logger(name="baml_acc_tool_assessor", log_level=LOG_LEVEL)


def assess_acc_tool(
    # Rule context
    rule_title: str,
    rule_code: str,
    rule_description: str,
    question: str,
    # Training context
    training_model_name: str,
    training_expected_guids: list[str],
    training_predicted_guids: list[str],
    training_tp: int,
    training_fp: int,
    training_fn: int,
    training_f1: float,
    # Validation context (abstract)
    validation_model_name: str,
    validation_expected_count: int,
    validation_predicted_count: int,
    validation_tp: int,
    validation_fp: int,
    validation_fn: int,
    validation_f1: float,
    # Tool details
    tool_name: str,
    tool_implementation: str,
    execution_log: str,
    # Retry context
    retry_count: int = 0,
    previous_hints: Optional[str] = None,
    # LLM config
    llm_provider: str = "zai",
    llm_name: str = "GLM-4.7",
    **kwargs,
) -> Tuple[ACCToolAssessment, Collector]:
    """
    Assess why an ACC tool performs differently on validation vs training data.

    This function analyzes the gap between training and validation performance
    and provides generic improvement guidance without leaking validation specifics.

    Args:
        rule_title: Title of the compliance rule
        rule_code: Code reference for the rule
        rule_description: Full description of the compliance rule
        question: The compliance check question
        training_model_name: Name of the training model
        training_expected_guids: GUIDs expected in training model
        training_predicted_guids: GUIDs found by tool in training model
        training_tp: True positives on training data
        training_fp: False positives on training data
        training_fn: False negatives on training data
        training_f1: F1 score on training data
        validation_model_name: Name of the validation model
        validation_expected_count: Number of expected violations (abstract - no GUIDs)
        validation_predicted_count: Number of predicted violations
        validation_tp: True positives on validation data
        validation_fp: False positives on validation data
        validation_fn: False negatives on validation data
        validation_f1: F1 score on validation data
        tool_name: Name of the ACC tool function
        tool_implementation: Python source code of the tool
        execution_log: Execution log from validation run
        retry_count: Current retry attempt number
        previous_hints: Previous improvement hints if any
        llm_provider: LLM provider name for logging
        llm_name: LLM model name for logging
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (ACCToolAssessment, Collector) where ACCToolAssessment contains:
        - thoughts: Analysis of the tool performance
        - diagnosis: Root cause (overfitting, missing_generalization, etc.)
        - improvement_hint: Generic guidance for improvement
        - recommendation: keep_tool or retry_with_hint
        - confidence: high, medium, or low
    """
    # Start timer
    start = time.time()

    # Create collector for token tracking
    collector = Collector(name="ACCToolAssessor")

    # Add collector to kwargs for BAML calls
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    with mlflow.start_span(
        name="ACCToolAssessor", span_type="LLM"
    ) as assessor_span:
        assessor_span.set_inputs(
            {
                "rule_title": rule_title,
                "rule_code": rule_code,
                "tool_name": tool_name,
                "training_model": training_model_name,
                "validation_model": validation_model_name,
                "training_f1": training_f1,
                "validation_f1": validation_f1,
                "retry_count": retry_count,
            }
        )

        # Assess ACC tool
        try:
            assessment = b.with_options(
                **kwargs.pop("baml_options", {})
            ).ACCToolAssessor(
                rule_title=rule_title,
                rule_code=rule_code,
                rule_description=rule_description,
                question=question,
                training_model_name=training_model_name,
                training_expected_guids=training_expected_guids,
                training_predicted_guids=training_predicted_guids,
                training_tp=training_tp,
                training_fp=training_fp,
                training_fn=training_fn,
                training_f1=training_f1,
                validation_model_name=validation_model_name,
                validation_expected_count=validation_expected_count,
                validation_predicted_count=validation_predicted_count,
                validation_tp=validation_tp,
                validation_fp=validation_fp,
                validation_fn=validation_fn,
                validation_f1=validation_f1,
                tool_name=tool_name,
                tool_implementation=tool_implementation,
                execution_log=execution_log,
                retry_count=retry_count,
                previous_hints=previous_hints,
                **kwargs,
            )
        except Exception as e:
            _logger.error(f"Error assessing ACC tool: {e}")
            assessment = ACCToolAssessment(
                thoughts=f"An Exception occurred when trying to assess ACC tool. Exception:\n{e}",
                diagnosis="unknown",
                improvement_hint="Unable to provide hint due to assessment error",
                recommendation="keep_tool",
                confidence="low",
            )

        # Log outputs
        assessor_span.set_outputs(
            {
                "thoughts": assessment.thoughts,
                "diagnosis": assessment.diagnosis,
                "improvement_hint": assessment.improvement_hint,
                "recommendation": assessment.recommendation,
                "confidence": assessment.confidence,
            }
        )

        # Calculate metrics
        duration = time.time() - start
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0

        if collector.last:
            usage = collector.last.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            total_tokens = input_tokens + output_tokens

        # Set span attributes
        assessor_span.set_attributes(
            {
                "llm_provider": llm_provider,
                "llm_name": llm_name,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "duration": duration,
            }
        )

        _logger.info(
            f"ACC tool assessment completed. Diagnosis: {assessment.diagnosis}, "
            f"Recommendation: {assessment.recommendation}, "
            f"Confidence: {assessment.confidence}, Tokens: {total_tokens}, Duration: {duration:.2f}s"
        )

        return assessment, collector


# Export for use in other modules
__all__ = ["assess_acc_tool"]
