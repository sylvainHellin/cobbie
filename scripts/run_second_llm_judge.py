#!/usr/bin/env python3
"""
Run Second LLM Judge (Gemini 3.0 Pro) on existing evaluation data.

Reads answers from H1's grading sheet and evaluates them with Gemini,
outputting results in the same format as existing eval CSVs.

Includes full MLflow tracing for debugging and analysis.

Usage:
    uv run scripts/run_second_llm_judge.py
    uv run scripts/run_second_llm_judge.py --dry-run  # Preview without calling API
"""

import argparse
import time
from datetime import datetime
from pathlib import Path

import mlflow
import pandas as pd
from baml_py.baml_py import Collector
from loguru import logger
from tqdm import tqdm

from src.agents.answer_verifier import derive_binary_classification
from src.baml.baml_client import b
from src.baml.baml_client.types import QuestionCategory

# Input file (H1's grading sheet with all data)
INPUT_FILE = Path("src/db/eval/EC3-2026 - H1 (H1) 2026-01-20_21-07.csv")
OUTPUT_DIR = Path("src/db/eval")

# Client info for MLflow logging
CLIENT_INFO = {
    "model": "gemini-3-pro-preview",
    "provider": "google",
}


def map_category(cat: int) -> QuestionCategory:
    """Map category number to BAML enum."""
    return {
        1: QuestionCategory.Category1,
        2: QuestionCategory.Category2,
        3: QuestionCategory.Category3,
        4: QuestionCategory.Category4,
    }[cat]


def run_gemini_judge(dry_run: bool = False) -> None:
    """Run Gemini judge on all valid questions with MLflow tracing."""
    # Load data
    df = pd.read_csv(INPUT_FILE)
    logger.info(f"Loaded {len(df)} questions from {INPUT_FILE}")

    # Filter: Error=0, UPDATED != 'x'
    valid = df[(df["Error"] == 0) & (df["UPDATED"] != "x")].copy()
    logger.info(f"Valid questions after filtering: {len(valid)}")

    if dry_run:
        logger.info("DRY RUN - not calling API")
        print(f"Would evaluate {len(valid)} questions")
        print(f"Sample question IDs: {list(valid['Question ID'].iloc[:5])}")
        return

    # Setup MLflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("GeminiJudge")

    run_name = f"GeminiJudge_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"

    # Prepare output dataframe
    results = []

    with mlflow.start_run(run_name=run_name) as parent_run:
        # Log parent run params
        mlflow.log_params(
            {
                "model_name": CLIENT_INFO["model"],
                "provider_name": CLIENT_INFO["provider"],
                "input_file": str(INPUT_FILE),
                "total_questions": len(valid),
                "component": "GeminiJudge",
            }
        )

        logger.info(f"MLflow run started: {parent_run.info.run_id}")

        start_time = time.time()

        for _, row in tqdm(valid.iterrows(), total=len(valid), desc="Evaluating with Gemini"):
            question_id = int(row["Question ID"])
            question = str(row["Question"])
            answer = str(row["Cobbie's Answer"])
            ground_truth = str(row["Ground Truth"])
            category = int(row["Category"])

            # Create nested run for this question
            run_name_q = f"question_{question_id}"

            with mlflow.start_run(run_name=run_name_q, nested=True):
                # Log question params
                mlflow.log_params(
                    {
                        "question_id": question_id,
                        "question": question[:500],  # Truncate for MLflow limits
                        "ground_truth": ground_truth[:500],
                        "category": category,
                        "llm": CLIENT_INFO["model"],
                        "provider_name": CLIENT_INFO["provider"],
                    }
                )

                with mlflow.start_span(name="GeminiEvaluator", span_type="LLM") as span:
                    span.set_inputs(
                        {
                            "question": question,
                            "category": category,
                            "ground_truth": ground_truth,
                            "system_response": answer,
                        }
                    )

                    q_start_time = time.time()

                    # Create collector for token tracking
                    collector = Collector(name="GeminiJudge")

                    try:
                        result = b.with_options(collector=collector).EvaluateResponseGemini(
                            question=question,
                            category=map_category(category),
                            ground_truth=ground_truth,
                            system_response=answer,
                        )

                        duration = time.time() - q_start_time

                        # Extract token usage
                        input_tokens = 0
                        output_tokens = 0
                        if collector.last:
                            usage = collector.last.usage
                            input_tokens = usage.input_tokens or 0
                            output_tokens = usage.output_tokens or 0

                        binary = derive_binary_classification(result)

                        # Log metrics
                        mlflow.log_metrics(
                            {
                                "duration": duration,
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "total_tokens": input_tokens + output_tokens,
                                "success": 1,
                            }
                        )

                        # Log evaluation results as params
                        mlflow.log_params(
                            {
                                "abstention": str(result.abstention),
                                "faithfulness": result.faithfulness.value,
                                "completeness": result.completeness.value,
                                "transparency": result.transparency.value,
                                "relevance": result.relevance.value,
                                "classification": binary,
                                "justification": result.justification[:500] if result.justification else "",
                            }
                        )

                        # Set span outputs
                        span.set_outputs(
                            {
                                "abstention": result.abstention,
                                "faithfulness": result.faithfulness.value,
                                "completeness": result.completeness.value,
                                "transparency": result.transparency.value,
                                "relevance": result.relevance.value,
                                "classification": binary,
                                "justification": result.justification,
                            }
                        )
                        span.set_status("OK")

                        results.append(
                            {
                                "Question ID": question_id,
                                "Abstention": result.abstention,
                                "Faithfulness": result.faithfulness.value,
                                "Completeness": result.completeness.value,
                                "Transparency": result.transparency.value,
                                "Relevance": result.relevance.value,
                                "Question": question,
                                "Cobbie's Answer": answer,
                                "Ground Truth": ground_truth,
                                "Category": category,
                                "Category Name": row["Category Name"],
                                "Project": row["Project"],
                                "Justification": result.justification,
                                "Binary Classification": binary,
                            }
                        )

                        logger.debug(
                            f"Question {question_id}: {binary} in {duration:.2f}s"
                        )

                    except Exception as e:
                        duration = time.time() - q_start_time
                        logger.error(f"Error evaluating question {question_id}: {e}")

                        mlflow.log_metrics({"success": 0, "duration": duration})
                        mlflow.log_params(
                            {
                                "abstention": "True",
                                "faithfulness": "Na",
                                "completeness": "Na",
                                "transparency": "Na",
                                "relevance": "Na",
                                "classification": "abstained",
                                "justification": f"ERROR: {e}"[:500],
                            }
                        )

                        span.set_status("ERROR")

                        results.append(
                            {
                                "Question ID": question_id,
                                "Abstention": True,
                                "Faithfulness": "Na",
                                "Completeness": "Na",
                                "Transparency": "Na",
                                "Relevance": "Na",
                                "Question": question,
                                "Cobbie's Answer": answer,
                                "Ground Truth": ground_truth,
                                "Category": category,
                                "Category Name": row["Category Name"],
                                "Project": row["Project"],
                                "Justification": f"ERROR: {e}",
                                "Binary Classification": "abstained",
                            }
                        )

        total_duration = time.time() - start_time

        # Log aggregate metrics to parent run
        total_abstentions = sum(1 for r in results if r["Abstention"])
        total_correct = sum(1 for r in results if r["Binary Classification"] == "correct")
        total_wrong = sum(1 for r in results if r["Binary Classification"] == "wrong")

        mlflow.log_metrics(
            {
                "total_questions": len(results),
                "total_duration": total_duration,
                "abstention_count": total_abstentions,
                "correct_count": total_correct,
                "wrong_count": total_wrong,
                "accuracy": total_correct / (total_correct + total_wrong) if (total_correct + total_wrong) > 0 else 0,
            }
        )

        mlflow.set_tag("evaluation_status", "completed")

    # Save output CSV
    output_df = pd.DataFrame(results)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    output_file = OUTPUT_DIR / f"EC3-2026 - Gemini_Judge (Gemini_Judge) {timestamp}.csv"
    output_df.to_csv(output_file, index=False)
    logger.info(f"Saved results to {output_file}")

    # Summary
    print(f"\n{'='*60}")
    print("GEMINI JUDGE RESULTS")
    print(f"{'='*60}")
    print(f"Total evaluated: {len(results)}")
    print(f"Abstentions: {total_abstentions}")
    print(f"Correct: {total_correct}")
    print(f"Wrong: {total_wrong}")
    print(f"Total duration: {total_duration:.1f}s")
    print(f"Output file: {output_file}")
    print("MLflow run: http://127.0.0.1:5000")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Gemini judge on existing answers")
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls")
    args = parser.parse_args()

    run_gemini_judge(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
