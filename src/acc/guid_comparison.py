"""
GUID Comparison Utilities for ACC Training

Provides utilities for comparing predicted GUIDs against ground truth,
used during ACC tool validation in the training phase.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.config import ACC_RES_PATH


@dataclass
class GUIDComparisonResult:
    """Result of comparing predicted GUIDs against expected GUIDs."""

    tp: int  # True positives
    fp: int  # False positives
    fn: int  # False negatives
    precision: float
    recall: float
    f1: float
    is_perfect_match: bool

    @property
    def predicted_count(self) -> int:
        """Number of predicted GUIDs (TP + FP)."""
        return self.tp + self.fp

    @property
    def expected_count(self) -> int:
        """Number of expected GUIDs (TP + FN)."""
        return self.tp + self.fn


def compare_guids(predicted: set[str], expected: set[str]) -> GUIDComparisonResult:
    """
    Compare predicted GUIDs against expected GUIDs.

    Handles edge cases:
    - Both empty: Perfect match (F1 = 1.0) - pass rule correctly identified as no violations
    - Empty expected, non-empty predicted: All false positives
    - Non-empty expected, empty predicted: All false negatives

    Args:
        predicted: Set of GUIDs predicted by the tool
        expected: Set of GUIDs from ground truth

    Returns:
        GUIDComparisonResult with TP/FP/FN counts and precision/recall/F1 metrics
    """
    tp = len(predicted & expected)
    fp = len(predicted - expected)
    fn = len(expected - predicted)

    # Handle pass rules: both empty = perfect match (100%)
    if len(predicted) == 0 and len(expected) == 0:
        return GUIDComparisonResult(
            tp=0,
            fp=0,
            fn=0,
            precision=1.0,
            recall=1.0,
            f1=1.0,
            is_perfect_match=True,
        )

    # Standard metrics calculation
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return GUIDComparisonResult(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        is_perfect_match=(fp == 0 and fn == 0),
    )


def get_expected_guids(model_name: str, rule_title: str) -> list[str]:
    """
    Get expected GUIDs for a specific rule from ground truth.

    Args:
        model_name: Name of the model (e.g., 'duplex', 'dental_clinic')
        rule_title: Title of the rule (e.g., '304_3_1_circular_space')

    Returns:
        List of expected GUIDs (can be empty for pass rules)

    Raises:
        FileNotFoundError: If ground truth file doesn't exist
        KeyError: If rule_title not found in ground truth
    """
    ground_truth_path = Path(ACC_RES_PATH) / model_name / "ground_truth.json"

    if not ground_truth_path.exists():
        raise FileNotFoundError(f"Ground truth not found: {ground_truth_path}")

    with open(ground_truth_path, encoding="utf-8") as f:
        ground_truth = json.load(f)

    rules = ground_truth.get("rules", {})
    if rule_title not in rules:
        raise KeyError(f"Rule '{rule_title}' not found in ground truth for model '{model_name}'")

    rule_data = rules[rule_title]
    issues = rule_data.get("issues", [])

    # Collect all required_guids from all issues for this rule
    expected_guids: list[str] = []
    for issue in issues:
        expected_guids.extend(issue.get("required_guids", []))

    return expected_guids


def get_rule_context(model_name: str, rule_title: str) -> dict:
    """
    Get rule context from ground truth for a specific model and rule.

    Args:
        model_name: Name of the model (e.g., 'duplex', 'dental_clinic')
        rule_title: Title of the rule (e.g., '304_3_1_circular_space')

    Returns:
        Dictionary with rule context including:
        - rule_code: The rule code (e.g., '304.3.1')
        - question: The compliance question
        - rule_description: Full rule description
        - issues_count: Number of issues in ground truth
        - expected_guids: List of expected GUIDs

    Raises:
        FileNotFoundError: If ground truth file doesn't exist
        KeyError: If rule_title not found in ground truth
    """
    ground_truth_path = Path(ACC_RES_PATH) / model_name / "ground_truth.json"

    if not ground_truth_path.exists():
        raise FileNotFoundError(f"Ground truth not found: {ground_truth_path}")

    with open(ground_truth_path, encoding="utf-8") as f:
        ground_truth = json.load(f)

    rules = ground_truth.get("rules", {})
    if rule_title not in rules:
        raise KeyError(f"Rule '{rule_title}' not found in ground truth for model '{model_name}'")

    rule_data = rules[rule_title]
    issues = rule_data.get("issues", [])

    # Collect all required_guids from all issues
    expected_guids: list[str] = []
    for issue in issues:
        expected_guids.extend(issue.get("required_guids", []))

    return {
        "rule_code": rule_data.get("rule_code", ""),
        "question": rule_data.get("question", ""),
        "rule_description": rule_data.get("rule", ""),
        "parameters": rule_data.get("parameters", ""),
        "issues_count": rule_data.get("issues_count", 0),
        "expected_guids": expected_guids,
    }


def load_ground_truth(model_name: str) -> dict:
    """
    Load the full ground truth for a model.

    Args:
        model_name: Name of the model (e.g., 'duplex', 'dental_clinic')

    Returns:
        Full ground truth dictionary

    Raises:
        FileNotFoundError: If ground truth file doesn't exist
    """
    ground_truth_path = Path(ACC_RES_PATH) / model_name / "ground_truth.json"

    if not ground_truth_path.exists():
        raise FileNotFoundError(f"Ground truth not found: {ground_truth_path}")

    with open(ground_truth_path, encoding="utf-8") as f:
        return json.load(f)


def get_available_rules(model_name: str) -> list[str]:
    """
    Get list of available rule titles for a model.

    Args:
        model_name: Name of the model (e.g., 'duplex', 'dental_clinic')

    Returns:
        List of rule titles available in the ground truth

    Raises:
        FileNotFoundError: If ground truth file doesn't exist
    """
    ground_truth = load_ground_truth(model_name)
    return list(ground_truth.get("rules", {}).keys())


def get_model_path(model_name: str) -> Optional[str]:
    """
    Get the IFC model path for a given model name.

    Args:
        model_name: Name of the model (e.g., 'duplex', 'dental_clinic')

    Returns:
        Path to the IFC model file, or None if not found
    """
    from src.config import ACC_MODELS_PATH

    models_path = Path(ACC_MODELS_PATH)

    # Check for common patterns
    possible_paths = [
        models_path / model_name / "arc.ifc",
        models_path / model_name / f"{model_name}.ifc",
        models_path / f"{model_name}.ifc",
    ]

    # Also search for any .ifc file in the model directory
    model_dir = models_path / model_name
    if model_dir.is_dir():
        ifc_files = list(model_dir.glob("*.ifc"))
        if ifc_files:
            possible_paths.extend(ifc_files)

    for path in possible_paths:
        if path.exists():
            return str(path)

    return None


__all__ = [
    "GUIDComparisonResult",
    "compare_guids",
    "get_expected_guids",
    "get_rule_context",
    "load_ground_truth",
    "get_available_rules",
    "get_model_path",
]
