"""
ACC Compliance Evaluator Module
Evaluates model predictions against ground truth using GUID-based comparison.

Phase 5 of the ACC Ground Truth Pipeline:
- GUID-based comparison between predictions and ground truth
- Support for partial matches
- Metrics: precision, recall, F1 per rule and overall
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from config import ACC_RES_PATH


@dataclass
class IssueMetrics:
    """Metrics for a single issue (topic)."""
    topic_id: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0


@dataclass
class RuleMetrics:
    """Aggregated metrics for a rule."""
    rule_title: str
    rule_code: str
    question: str
    issues_count: int = 0
    matched_issues: int = 0  # Issues with at least one correct GUID
    total_true_positives: int = 0
    total_false_positives: int = 0
    total_false_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    issue_metrics: list[IssueMetrics] = field(default_factory=list)
    is_pass_rule: bool = False  # True if ground truth has no issues
    correctly_passed: bool = False  # True if pass rule and predicted no issues


@dataclass
class EvaluationResult:
    """Complete evaluation result."""
    model_name: str
    rules_count: int = 0
    total_issues: int = 0
    total_matched_issues: int = 0
    total_true_positives: int = 0
    total_false_positives: int = 0
    total_false_negatives: int = 0
    micro_precision: float = 0.0
    micro_recall: float = 0.0
    micro_f1: float = 0.0
    macro_precision: float = 0.0
    macro_recall: float = 0.0
    macro_f1: float = 0.0
    rule_metrics: dict[str, RuleMetrics] = field(default_factory=dict)
    total_pass_rules: int = 0  # Rules where ground truth has no issues
    total_correct_passes: int = 0  # Pass rules where we correctly predicted no issues


class AccEvaluator:
    """
    Evaluates compliance check predictions against ground truth.

    Compares predicted GUIDs against required_guids from ground truth,
    computing precision, recall, and F1 scores at issue, rule, and overall levels.

    Usage:
        evaluator = AccEvaluator("duplex")
        predictions = {
            "304.3.1": [
                {"topic_id": "abc", "predicted_guids": ["GUID1", "GUID2"]},
                ...
            ]
        }
        result = evaluator.evaluate(predictions)
    """

    def __init__(self, model_name: str, ground_truth_path: Path | None = None) -> None:
        """
        Initialize evaluator with ground truth.

        Args:
            model_name: Name of the model (e.g., "duplex")
            ground_truth_path: Path to ground_truth.json (optional)
        """
        self.model_name = model_name

        if ground_truth_path is None:
            ground_truth_path = Path(ACC_RES_PATH) / model_name / "ground_truth.json"

        self.ground_truth_path = ground_truth_path
        self.ground_truth: dict[str, Any] = {}
        self._load_ground_truth()

    def _load_ground_truth(self) -> None:
        """Load ground truth from JSON file."""
        if not self.ground_truth_path.exists():
            raise FileNotFoundError(f"Ground truth not found: {self.ground_truth_path}")

        with open(self.ground_truth_path, encoding="utf-8") as f:
            self.ground_truth = json.load(f)

    def _compute_metrics(self, predicted: set[str], expected: set[str]) -> tuple[int, int, int, float, float, float]:
        """
        Compute set-based metrics.

        Args:
            predicted: Set of predicted GUIDs
            expected: Set of expected (required) GUIDs

        Returns:
            Tuple of (tp, fp, fn, precision, recall, f1)
        """
        tp = len(predicted & expected)
        fp = len(predicted - expected)
        fn = len(expected - predicted)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return tp, fp, fn, precision, recall, f1

    def evaluate(self, predictions: dict[str, list[dict[str, Any]]]) -> EvaluationResult:
        """
        Evaluate predictions against ground truth.

        Args:
            predictions: Dict mapping rule_title to list of predictions.
                Each prediction is {"topic_id": str, "predicted_guids": list[str]}
                If topic_id is not provided, predictions are matched by order.

        Returns:
            EvaluationResult with metrics at all levels
        """
        result = EvaluationResult(model_name=self.model_name)
        rules = self.ground_truth.get("rules", {})
        result.rules_count = len(rules)

        for rule_title, rule_data in rules.items():
            rule_metrics = RuleMetrics(
                rule_title=rule_title,
                rule_code=rule_data.get("rule_code", ""),
                question=rule_data.get("question", ""),
                issues_count=rule_data.get("issues_count", 0),
            )

            # Get predictions for this rule
            rule_predictions = predictions.get(rule_title, [])

            # Build lookup by topic_id
            pred_by_topic: dict[str, set[str]] = {}
            all_predicted_guids: set[str] = set()
            for pred in rule_predictions:
                topic_id = pred.get("topic_id", "")
                guids = set(pred.get("predicted_guids", []))
                all_predicted_guids.update(guids)
                if topic_id:
                    pred_by_topic[topic_id] = guids

            issues = rule_data.get("issues", [])

            # Check for pass rule (no issues in ground truth)
            if not issues:
                rule_metrics.is_pass_rule = True
                rule_metrics.correctly_passed = len(all_predicted_guids) == 0
                # Any prediction on a pass rule is a false positive
                rule_metrics.total_false_positives = len(all_predicted_guids)
                result.total_pass_rules += 1
                if rule_metrics.correctly_passed:
                    result.total_correct_passes += 1
            else:
                # Normal case: evaluate each issue
                for issue in issues:
                    topic_id = issue.get("topic_id", "")
                    expected = set(issue.get("required_guids", []))

                    # Get prediction for this topic
                    predicted = pred_by_topic.get(topic_id, set())

                    tp, fp, fn, precision, recall, f1 = self._compute_metrics(predicted, expected)

                    issue_metrics = IssueMetrics(
                        topic_id=topic_id,
                        true_positives=tp,
                        false_positives=fp,
                        false_negatives=fn,
                        precision=precision,
                        recall=recall,
                        f1=f1,
                    )
                    rule_metrics.issue_metrics.append(issue_metrics)

                    # Aggregate to rule level
                    rule_metrics.total_true_positives += tp
                    rule_metrics.total_false_positives += fp
                    rule_metrics.total_false_negatives += fn
                    if tp > 0:
                        rule_metrics.matched_issues += 1

            # Compute rule-level metrics
            tp = rule_metrics.total_true_positives
            fp = rule_metrics.total_false_positives
            fn = rule_metrics.total_false_negatives

            rule_metrics.precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rule_metrics.recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            rule_metrics.f1 = (
                2 * rule_metrics.precision * rule_metrics.recall / (rule_metrics.precision + rule_metrics.recall)
                if (rule_metrics.precision + rule_metrics.recall) > 0 else 0.0
            )

            result.rule_metrics[rule_title] = rule_metrics

            # Aggregate to overall level
            result.total_issues += rule_metrics.issues_count
            result.total_matched_issues += rule_metrics.matched_issues
            result.total_true_positives += tp
            result.total_false_positives += fp
            result.total_false_negatives += fn

        # Compute overall micro metrics
        tp = result.total_true_positives
        fp = result.total_false_positives
        fn = result.total_false_negatives

        result.micro_precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        result.micro_recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        result.micro_f1 = (
            2 * result.micro_precision * result.micro_recall / (result.micro_precision + result.micro_recall)
            if (result.micro_precision + result.micro_recall) > 0 else 0.0
        )

        # Compute macro metrics (average across rules)
        if result.rule_metrics:
            result.macro_precision = sum(r.precision for r in result.rule_metrics.values()) / len(result.rule_metrics)
            result.macro_recall = sum(r.recall for r in result.rule_metrics.values()) / len(result.rule_metrics)
            result.macro_f1 = sum(r.f1 for r in result.rule_metrics.values()) / len(result.rule_metrics)

        return result

    def evaluate_flat(self, predictions: list[dict[str, Any]]) -> EvaluationResult:
        """
        Evaluate predictions in flat format (list of all predictions).

        Args:
            predictions: List of {"rule_title": str, "topic_id": str, "predicted_guids": list[str]}

        Returns:
            EvaluationResult with metrics at all levels
        """
        # Convert to grouped format
        grouped: dict[str, list[dict[str, Any]]] = {}
        for pred in predictions:
            rule_title = pred.get("rule_title", "")
            if rule_title not in grouped:
                grouped[rule_title] = []
            grouped[rule_title].append(pred)

        return self.evaluate(grouped)


def format_evaluation_result(result: EvaluationResult) -> str:
    """Format evaluation result as a readable string."""
    pass_accuracy = (
        result.total_correct_passes / result.total_pass_rules
        if result.total_pass_rules > 0
        else 0.0
    )

    lines = [
        f"=== Evaluation Results: {result.model_name} ===",
        f"Rules: {result.rules_count} | Issues: {result.total_issues} | Matched: {result.total_matched_issues}",
        f"Pass Rules: {result.total_pass_rules} | Correct Passes: {result.total_correct_passes}",
        "",
        "Overall Metrics:",
        f"  Micro: P={result.micro_precision:.3f} R={result.micro_recall:.3f} F1={result.micro_f1:.3f}",
        f"  Macro: P={result.macro_precision:.3f} R={result.macro_recall:.3f} F1={result.macro_f1:.3f}",
        f"  Pass Accuracy: {pass_accuracy:.3f}",
        "",
        "Per-Rule Metrics:",
    ]

    for rule_title, metrics in result.rule_metrics.items():
        if metrics.is_pass_rule:
            status = "CORRECT" if metrics.correctly_passed else "INCORRECT"
            lines.append(f"  {rule_title}: [PASS RULE] {status}")
        else:
            lines.append(
                f"  {rule_title}: P={metrics.precision:.3f} R={metrics.recall:.3f} F1={metrics.f1:.3f} "
                f"({metrics.matched_issues}/{metrics.issues_count} matched)"
            )

    return "\n".join(lines)


if __name__ == "__main__":
    # Example: Evaluate with empty predictions (baseline)
    evaluator = AccEvaluator("duplex")
    result = evaluator.evaluate({})
    print(format_evaluation_result(result))
