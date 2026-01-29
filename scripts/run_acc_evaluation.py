#!/usr/bin/env python3
"""
ACC (Automated Compliance Checking) Evaluation Script

Evaluates COBBIE's compliance checking capabilities using GUID-based metrics.
Compares predicted IFC GUIDs against ground truth from Solibri ACC.

MLflow Run Hierarchy:
    ACC_Evaluation (experiment)
    └── ACC_{timestamp} (parent run)
        ├── rule_304_3_1 (child run - rule level)
        │   ├── duplex (grandchild run - cobbie traces)
        │   └── office (grandchild run - cobbie traces)
        └── ...

Usage:
    # Evaluate single model
    uv run scripts/run_acc_evaluation.py --model duplex

    # Dry run (show questions only)
    uv run scripts/run_acc_evaluation.py --model duplex --dry-run

    # Evaluate all models
    uv run scripts/run_acc_evaluation.py --all
"""

import argparse
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import mlflow

from config import ACC_RES_PATH
from src.acc.Evaluator import AccEvaluator, EvaluationResult
from src.agents.cobbie import cobbie
from src.util import get_created_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RuleInfo:
    """Information about a rule across models."""

    rule_code: str
    rule_title: str
    rule: str
    question: str
    parameters: str
    models: dict[str, dict[str, Any]] = field(default_factory=dict)
    # models maps model_name -> rule_data (including issues)


def load_ground_truth(model_name: str) -> dict[str, Any]:
    """Load ground truth for a model."""
    gt_path = Path(ACC_RES_PATH) / model_name / "ground_truth.json"
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth not found: {gt_path}")

    with open(gt_path, encoding="utf-8") as f:
        return json.load(f)


def get_model_ifc_path(model_name: str) -> str:
    """Get IFC path for a model."""
    return f"src/db/bim_models/{model_name}/arc.ifc"


def collect_rules_across_models(model_names: list[str]) -> dict[str, RuleInfo]:
    """
    Collect all unique rules across models.

    Returns:
        Dict mapping rule_title -> RuleInfo with list of models that have this rule
    """
    rules_map: dict[str, RuleInfo] = {}

    for model_name in model_names:
        try:
            ground_truth = load_ground_truth(model_name)
            rules = ground_truth.get("rules", {})

            for rule_title, rule_data in rules.items():
                if rule_title not in rules_map:
                    rules_map[rule_title] = RuleInfo(
                        rule_code=rule_data.get("rule_code", ""),
                        rule_title=rule_title,
                        rule=rule_data.get("rule", ""),
                        question=rule_data.get("question", ""),
                        parameters=rule_data.get("parameters", ""),
                    )
                # Add this model's data for the rule
                rules_map[rule_title].models[model_name] = rule_data

        except FileNotFoundError:
            logger.warning(f"Ground truth not found for {model_name}, skipping")

    return rules_map


def build_enriched_question(rule_info: RuleInfo) -> str:
    """Build an enriched question with rule context."""
    return f"""Rule: {rule_info.rule}

Parameters: {rule_info.parameters}

Question: {rule_info.question}"""


def run_cobbie_for_rule(
    question: str,
    model_path: str | None,
    tools_dict: dict,
) -> list[str]:
    """
    Run COBBIE for a compliance question and extract predicted GUIDs.

    Returns:
        List of predicted IFC GUIDs from COBBIE's FinalAnswer
    """
    final_answer, _collector, _history = cobbie(
        user_input=question,
        tools=tools_dict,
        model_path=model_path,
    )

    guids = final_answer.ifc_guids if final_answer and final_answer.ifc_guids else []
    return guids


def compute_metrics(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Compute precision, recall, F1 from counts."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def evaluate_single_prediction(
    predicted_guids: list[str],
    rule_data: dict[str, Any],
) -> tuple[int, int, int, int, bool, bool]:
    """
    Evaluate a single prediction against ground truth issues.

    Returns:
        (matched_issues, true_positives, false_positives, false_negatives, is_pass_rule, is_correct_pass)

    A "pass rule" is one where the ground truth has no issues (the model passes that check).
    is_correct_pass is True if we correctly predicted no issues for a pass rule.
    """
    issues = rule_data.get("issues", [])
    predicted_set = set(predicted_guids)

    # Check for pass rule (no issues in ground truth)
    if not issues:
        is_correct = len(predicted_set) == 0
        fp = len(predicted_set)  # Any prediction is a false positive (false alarm)
        return 0, 0, fp, 0, True, is_correct

    # Normal case: compute metrics from GUID matching
    all_required: set[str] = set()
    matched_issues = 0

    for issue in issues:
        required = set(issue.get("required_guids", []))
        all_required.update(required)

        # Count as matched if at least one required GUID was predicted
        if predicted_set & required:
            matched_issues += 1

    tp = len(predicted_set & all_required)
    fp = len(predicted_set - all_required)
    fn = len(all_required - predicted_set)

    return matched_issues, tp, fp, fn, False, False


def run_evaluation(
    model_names: list[str],
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, EvaluationResult]:
    """
    Run evaluation with rule-first hierarchy.

    Args:
        model_names: List of model names to evaluate
        dry_run: If True, only show questions without running COBBIE
        limit: Maximum number of rules to evaluate (None = all)

    Returns:
        Dict mapping model_name -> EvaluationResult
    """
    # Collect all rules across models
    all_rules = collect_rules_across_models(model_names)

    print(f"\n{'=' * 60}")
    print(f"ACC Evaluation: {len(all_rules)} unique rules across {len(model_names)} models")
    print(f"{'=' * 60}")

    # Apply limit if specified
    rules_list = list(all_rules.items())
    if limit is not None:
        rules_list = rules_list[:limit]

    if dry_run:
        print(f"\n[DRY RUN] Questions to evaluate ({len(rules_list)} rules):")
        for rule_title, rule_info in rules_list:
            print(f"\n  {rule_title}:")
            print(f"    Question: {rule_info.question}")
            print(f"    Models: {list(rule_info.models.keys())}")
        return {}

    # Load tools once
    tools_dict = get_created_tools()

    # Track results per model for final evaluation
    model_predictions: dict[str, dict[str, list[dict[str, Any]]]] = {
        name: {} for name in model_names
    }

    # Track aggregated metrics
    overall_tp, overall_fp, overall_fn = 0, 0, 0
    overall_matched_issues, overall_total_issues = 0, 0
    overall_pass_rules, overall_correct_passes = 0, 0

    # Per-rule aggregated metrics for parent run
    rule_aggregated_metrics: dict[str, dict[str, float]] = {}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Parent run
    with mlflow.start_run(run_name=f"ACC_{timestamp}"):
        mlflow.log_params({
            "total_rules": len(rules_list),
            "total_models": len(model_names),
            "model_names": ",".join(model_names),
        })

        total_rules = len(rules_list)

        for rule_idx, (rule_title, rule_info) in enumerate(rules_list, 1):
            print(f"\n[{rule_idx}/{total_rules}] Rule: {rule_title}")
            print(f"  Models: {list(rule_info.models.keys())}")

            # Child run for rule
            with mlflow.start_run(run_name=f"rule_{rule_title}", nested=True):
                mlflow.log_params({
                    "rule_code": rule_info.rule_code,
                    "rule_title": rule_title,
                    "question": rule_info.question[:250],
                    "models_count": len(rule_info.models),
                })

                enriched_question = build_enriched_question(rule_info)

                rule_tp, rule_fp, rule_fn = 0, 0, 0
                rule_matched, rule_total_issues = 0, 0
                rule_pass_rules, rule_correct_passes = 0, 0

                for model_name, rule_data in rule_info.models.items():
                    model_path = get_model_ifc_path(model_name)
                    issues_count = rule_data.get("issues_count", 0)
                    rule_total_issues += issues_count

                    print(f"    {model_name}: {issues_count} issues")

                    # Grandchild run for model
                    with mlflow.start_run(run_name=model_name, nested=True):
                        # Log ground truth issues as artifact
                        mlflow.log_param("issues_count", issues_count)
                        mlflow.log_text(
                            json.dumps(rule_data.get("issues", []), indent=2),
                            "ground_truth_issues.json",
                        )
                        mlflow.log_param("enriched_question", enriched_question[:250])

                        start_time = time.time()

                        # Run COBBIE (traces logged to this grandchild run)
                        predicted_guids = run_cobbie_for_rule(
                            enriched_question, model_path, tools_dict
                        )

                        duration = time.time() - start_time

                        # Evaluate this prediction
                        matched, tp, fp, fn, is_pass_rule, is_correct_pass = evaluate_single_prediction(
                            predicted_guids, rule_data
                        )

                        precision, recall, f1 = compute_metrics(tp, fp, fn)

                        print(f"      Predicted: {len(predicted_guids)} GUIDs ({duration:.1f}s)")
                        if is_pass_rule:
                            print(f"      Pass rule: {'CORRECT' if is_correct_pass else 'INCORRECT'}")
                        else:
                            print(f"      P={precision:.3f} R={recall:.3f} F1={f1:.3f}")

                        # Log grandchild metrics
                        mlflow.log_metrics({
                            "predicted_guids_count": len(predicted_guids),
                            "duration_seconds": duration,
                            "true_positives": tp,
                            "false_positives": fp,
                            "false_negatives": fn,
                            "precision": precision,
                            "recall": recall,
                            "f1": f1,
                            "matched_issues": matched,
                            "is_pass_rule": 1 if is_pass_rule else 0,
                            "correct_pass": 1 if is_correct_pass else 0,
                        })

                        # Store prediction for final evaluation
                        model_predictions[model_name][rule_title] = [{
                            "topic_id": "all",
                            "predicted_guids": predicted_guids,
                        }]

                        # Aggregate to rule level
                        rule_tp += tp
                        rule_fp += fp
                        rule_fn += fn
                        rule_matched += matched
                        if is_pass_rule:
                            rule_pass_rules += 1
                            if is_correct_pass:
                                rule_correct_passes += 1

                # Log rule-level aggregated metrics (child run)
                rule_precision, rule_recall, rule_f1 = compute_metrics(
                    rule_tp, rule_fp, rule_fn
                )

                mlflow.log_metrics({
                    "agg_true_positives": rule_tp,
                    "agg_false_positives": rule_fp,
                    "agg_false_negatives": rule_fn,
                    "agg_precision": rule_precision,
                    "agg_recall": rule_recall,
                    "agg_f1": rule_f1,
                    "agg_matched_issues": rule_matched,
                    "agg_total_issues": rule_total_issues,
                    "pass_rules_count": rule_pass_rules,
                    "correct_passes": rule_correct_passes,
                })

                # Store for parent summary
                rule_aggregated_metrics[rule_title] = {
                    "precision": rule_precision,
                    "recall": rule_recall,
                    "f1": rule_f1,
                    "matched_issues": rule_matched,
                    "total_issues": rule_total_issues,
                    "pass_rules": rule_pass_rules,
                    "correct_passes": rule_correct_passes,
                }

                # Aggregate to overall
                overall_tp += rule_tp
                overall_fp += rule_fp
                overall_fn += rule_fn
                overall_matched_issues += rule_matched
                overall_total_issues += rule_total_issues
                overall_pass_rules += rule_pass_rules
                overall_correct_passes += rule_correct_passes

        # Log parent-level overall metrics
        overall_precision, overall_recall, overall_f1 = compute_metrics(
            overall_tp, overall_fp, overall_fn
        )

        # Compute pass accuracy
        pass_accuracy = (
            overall_correct_passes / overall_pass_rules
            if overall_pass_rules > 0
            else 0.0
        )

        mlflow.log_metrics({
            "overall_precision": overall_precision,
            "overall_recall": overall_recall,
            "overall_f1": overall_f1,
            "overall_matched_issues": overall_matched_issues,
            "overall_total_issues": overall_total_issues,
            "overall_true_positives": overall_tp,
            "overall_false_positives": overall_fp,
            "overall_false_negatives": overall_fn,
            "total_pass_rules": overall_pass_rules,
            "total_correct_passes": overall_correct_passes,
            "pass_accuracy": pass_accuracy,
        })

        # Log per-rule summary metrics to parent
        for rule_title, metrics in rule_aggregated_metrics.items():
            prefix = f"rule_{rule_title}"
            mlflow.log_metrics({
                f"{prefix}_f1": metrics["f1"],
                f"{prefix}_precision": metrics["precision"],
                f"{prefix}_recall": metrics["recall"],
            })

    # Run formal evaluation per model using AccEvaluator
    results: dict[str, EvaluationResult] = {}

    for model_name in model_names:
        if model_predictions[model_name]:
            try:
                evaluator = AccEvaluator(model_name)
                result = evaluator.evaluate(model_predictions[model_name])
                results[model_name] = result
            except FileNotFoundError:
                logger.warning(f"Could not evaluate {model_name}: ground truth not found")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="ACC Evaluation Script")
    parser.add_argument("--model", type=str, help="Model name to evaluate (e.g., duplex)")
    parser.add_argument("--all", action="store_true", help="Evaluate all models")
    parser.add_argument("--dry-run", action="store_true", help="Show questions only")
    parser.add_argument("--no-mlflow", action="store_true", help="Skip MLflow logging")
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of rules to evaluate (e.g., 1 for first rule only)",
    )

    args = parser.parse_args()

    if not args.model and not args.all:
        parser.error("Either --model or --all is required")

    # Determine models to evaluate
    if args.all:
        acc_res = Path(ACC_RES_PATH)
        model_names = [
            d.name
            for d in acc_res.iterdir()
            if d.is_dir() and (d / "ground_truth.json").exists()
        ]
    else:
        model_names = [args.model]

    print(f"Models to evaluate: {model_names}")

    # Set up MLflow tracking
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("ACC_Evaluation")

    # Run evaluation
    results = run_evaluation(
        model_names,
        dry_run=args.dry_run,
        limit=args.limit,
    )

    # Summary
    if results:
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        for model_name, result in results.items():
            print(f"\n{model_name}:")
            print(f"  Micro F1: {result.micro_f1:.3f}")
            print(f"  Macro F1: {result.macro_f1:.3f}")
            print(f"  Matched: {result.total_matched_issues}/{result.total_issues}")


if __name__ == "__main__":
    main()
