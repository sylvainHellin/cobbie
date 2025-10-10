#!/usr/bin/env python3
"""
LLM Comparison Script

This script compares the performance of two different LLMs on the IFC question-answering task.
It evaluates accuracy, token consumption, costs, and other metrics with MLflow tracking.

Usage:
    uv run scripts/compare_llms.py \
        --model1 glm-4.6 \
        --provider1 zai \
        --model2 qwen3-coder \
        --provider2 deepinfra \
        --num-examples 10 \
        --experiment-name "GLM_vs_Qwen_Comparison"
"""

import argparse
import time
from datetime import datetime
from typing import Dict, Literal, Tuple

import dspy
import mlflow
import mlflow.dspy
from tabulate import tabulate
from tqdm import tqdm

from src.config.agents import EvaluationPipelineConfig
from src.config.llm import LLM
from src.engine.schemas import OutputsCollection
from src.engine.util import get_logger
from src.experiment.datasets import DEVSET
from src.experiment.evaluation.evaluation import EvaluationPipeline


class LLMComparer:
    """Compare performance of two LLMs on IFC QA task."""

    def __init__(
        self,
        model1_name: str,
        provider1_name: str,
        model2_name: str,
        provider2_name: str,
        num_examples: int = 10,
        experiment_name: str = "LLM_Comparison",
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
        cache: bool = True,
    ):
        self.model1_name = model1_name
        self.provider1_name = provider1_name
        self.model2_name = model2_name
        self.provider2_name = provider2_name
        self.num_examples = num_examples
        self.experiment_name = experiment_name
        self.cache = cache

        self.logger = get_logger(name="LLMComparer", log_level=log_level)

        # Setup MLflow
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment(self.experiment_name)

        # Prepare dataset
        self.dataset = DEVSET[:num_examples]
        self.logger.info(f"Using {len(self.dataset)} examples for comparison")

        # Store results
        self.results: Dict[str, Dict] = {}

    def _create_llm_config(self, model_name: str, provider_name: str) -> LLM:
        """Create LLM configuration for the specified model and provider."""
        return LLM(
            model_name=model_name,
            provider_name=provider_name,
        )

    def _evaluate_model(
        self, model_name: str, provider_name: str, run_name_suffix: str = ""
    ) -> Tuple[OutputsCollection, Dict]:
        """Evaluate a single model and return results."""
        self.logger.info(f"Evaluating {model_name} from {provider_name}")

        # Create LLM configuration
        llm_config = self._create_llm_config(model_name, provider_name)

        # Create evaluation pipeline config
        eval_config = EvaluationPipelineConfig(
            load_optimized_module=False,  # Start fresh for fair comparison
            llm=llm_config,
            log_level="WARNING",  # Reduce log noise during comparison
        )

        # Setup MLflow run
        run_name = f"{model_name}_{provider_name}_{run_name_suffix}_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"

        with mlflow.start_run(run_name=run_name) as run:
            # Log parameters
            mlflow.log_params(
                {
                    "model_name": model_name,
                    "provider_name": provider_name,
                    "num_examples": len(self.dataset),
                    "max_tokens": llm_config.max_tokens,
                    "adapter": type(llm_config.adapter).__name__,
                }
            )

            # Log cost information
            mlflow.log_params(
                {
                    "cost_input_token_per_m": llm_config.cost_input_token,
                    "cost_output_token_per_m": llm_config.cost_output_token,
                }
            )

            # Create evaluation pipeline
            evaluation_pipeline = EvaluationPipeline(config=eval_config)

            # Time the evaluation
            start_time = time.time()

            # Enable DSPy autologging
            mlflow.dspy.autolog()  # type: ignore

            # Set cache based on configuration
            dspy.configure_cache(enable_disk_cache=self.cache)

            # Run evaluation
            outputs = evaluation_pipeline.forward(
                dataset=self.dataset, mode=f"_{model_name}_{provider_name}"
            )

            end_time = time.time()
            evaluation_time = end_time - start_time

            # Calculate additional metrics
            total_input_tokens = outputs.lm_metrics.input_tokens or 0
            total_output_tokens = outputs.lm_metrics.output_tokens or 0
            mean_accuracy = outputs.mean_acc()

            # Calculate costs
            input_cost = (total_input_tokens / 1_000_000) * llm_config.cost_input_token
            output_cost = (
                total_output_tokens / 1_000_000
            ) * llm_config.cost_output_token
            total_cost = input_cost + output_cost

            # Calculate tokens per second
            tokens_per_second = (
                (total_input_tokens + total_output_tokens) / evaluation_time
                if evaluation_time > 0
                else 0
            )

            # Log additional metrics
            mlflow.log_metrics(
                {
                    "evaluation_time_seconds": evaluation_time,
                    "tokens_per_second": tokens_per_second,
                    "total_cost_usd": total_cost,
                    "input_cost_usd": input_cost,
                    "output_cost_usd": output_cost,
                    "avg_tokens_per_example": (total_input_tokens + total_output_tokens)
                    / len(self.dataset),
                }
            )

            # Prepare results summary
            results_summary = {
                "run_id": run.info.run_id,
                "model_name": model_name,
                "provider_name": provider_name,
                "mean_accuracy": mean_accuracy,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "evaluation_time_seconds": evaluation_time,
                "tokens_per_second": tokens_per_second,
                "input_cost_usd": input_cost,
                "output_cost_usd": output_cost,
                "total_cost_usd": total_cost,
                "num_examples": len(self.dataset),
                "successful_examples": len(
                    [o for o in outputs.outputs if o.status == "success"]
                ),
                "failed_examples": len(
                    [o for o in outputs.outputs if o.status != "success"]
                ),
            }

            self.logger.info(f"Completed evaluation for {model_name}")
            self.logger.info(f"  Mean Accuracy: {mean_accuracy:.3f}")
            self.logger.info(f"  Total Cost: ${total_cost:.4f}")
            self.logger.info(f"  Tokens/sec: {tokens_per_second:.1f}")
            self.logger.info(f"  Run ID: {run.info.run_id}")

            return outputs, results_summary

    def run_comparison(self) -> Dict[str, Dict]:
        """Run comparison for both models."""
        self.logger.info("Starting LLM comparison")
        self.logger.info(f"Model 1: {self.model1_name} from {self.provider1_name}")
        self.logger.info(f"Model 2: {self.model2_name} from {self.provider2_name}")

        # Evaluate first model
        with tqdm(
            total=len(self.dataset), desc=f"Evaluating {self.model1_name}"
        ) as pbar:
            try:
                outputs1, results1 = self._evaluate_model(
                    self.model1_name, self.provider1_name, "model1"
                )
                pbar.update(len(self.dataset))
            except Exception as e:
                self.logger.error(f"Error evaluating {self.model1_name}: {e}")
                raise

        self.results["model1"] = results1

        # Evaluate second model
        with tqdm(
            total=len(self.dataset), desc=f"Evaluating {self.model2_name}"
        ) as pbar:
            try:
                outputs2, results2 = self._evaluate_model(
                    self.model2_name, self.provider2_name, "model2"
                )
                pbar.update(len(self.dataset))
            except Exception as e:
                self.logger.error(f"Error evaluating {self.model2_name}: {e}")
                raise

        self.results["model2"] = results2

        # Print comparison results
        self._print_comparison_table()

        return self.results

    def _print_comparison_table(self):
        """Print a formatted comparison table."""
        if len(self.results) != 2:
            self.logger.warning("Need both model results for comparison")
            return

        r1, r2 = self.results["model1"], self.results["model2"]

        # Create comparison table
        table_data = [
            [
                "Metric",
                f"{r1['model_name']} ({r1['provider_name']})",
                f"{r2['model_name']} ({r2['provider_name']})",
                "Winner",
            ],
            [
                "Mean Accuracy",
                f"{r1['mean_accuracy']:.3f}",
                f"{r2['mean_accuracy']:.3f}",
                "Model 1"
                if r1["mean_accuracy"] > r2["mean_accuracy"]
                else "Model 2"
                if r2["mean_accuracy"] > r1["mean_accuracy"]
                else "Tie",
            ],
            [
                "Total Cost ($)",
                f"{r1['total_cost_usd']:.4f}",
                f"{r2['total_cost_usd']:.4f}",
                "Model 1"
                if r1["total_cost_usd"] < r2["total_cost_usd"]
                else "Model 2"
                if r2["total_cost_usd"] < r1["total_cost_usd"]
                else "Tie",
            ],
            [
                "Total Tokens",
                f"{r1['total_tokens']:,}",
                f"{r2['total_tokens']:,}",
                "Model 1"
                if r1["total_tokens"] < r2["total_tokens"]
                else "Model 2"
                if r2["total_tokens"] < r1["total_tokens"]
                else "Tie",
            ],
            [
                "Tokens/sec",
                f"{r1['tokens_per_second']:.1f}",
                f"{r2['tokens_per_second']:.1f}",
                "Model 1"
                if r1["tokens_per_second"] > r2["tokens_per_second"]
                else "Model 2"
                if r2["tokens_per_second"] > r1["tokens_per_second"]
                else "Tie",
            ],
            [
                "Eval Time (s)",
                f"{r1['evaluation_time_seconds']:.1f}",
                f"{r2['evaluation_time_seconds']:.1f}",
                "Model 1"
                if r1["evaluation_time_seconds"] < r2["evaluation_time_seconds"]
                else "Model 2"
                if r2["evaluation_time_seconds"] < r1["evaluation_time_seconds"]
                else "Tie",
            ],
            [
                "Success Rate",
                f"{r1['successful_examples']}/{r1['num_examples']}",
                f"{r2['successful_examples']}/{r2['num_examples']}",
                "Model 1"
                if r1["successful_examples"] > r2["successful_examples"]
                else "Model 2"
                if r2["successful_examples"] > r1["successful_examples"]
                else "Tie",
            ],
        ]

        print("\n" + "=" * 80)
        print("LLM COMPARISON RESULTS")
        print("=" * 80)
        print(tabulate(table_data, headers="firstrow", tablefmt="grid"))
        print("=" * 80)

        # Print summary insights
        print("\nKEY INSIGHTS:")

        accuracy_diff = r1["mean_accuracy"] - r2["mean_accuracy"]
        if abs(accuracy_diff) > 0.05:
            better_model = "Model 1" if accuracy_diff > 0 else "Model 2"
            print(
                f"• {better_model} has significantly better accuracy ({abs(accuracy_diff):.3f} difference)"
            )

        cost_diff = r1["total_cost_usd"] - r2["total_cost_usd"]
        if abs(cost_diff) > 0.01:
            cheaper = "Model 1" if cost_diff < 0 else "Model 2"
            print(
                f"• {cheaper} is more cost-effective (${abs(cost_diff):.4f} difference)"
            )

        speed_diff = r1["tokens_per_second"] - r2["tokens_per_second"]
        if abs(speed_diff) > 10:
            faster = "Model 1" if speed_diff > 0 else "Model 2"
            print(f"• {faster} is faster ({abs(speed_diff):.1f} tokens/sec difference)")

        print(f"\nMLflow Experiment: {self.experiment_name}")
        print("View detailed results at: http://127.0.0.1:5000")


def main():
    """Main function to run the comparison."""
    parser = argparse.ArgumentParser(description="Compare two LLMs on IFC QA task")

    parser.add_argument("--model1", required=True, help="Name of first model")
    parser.add_argument("--provider1", required=True, help="Provider for first model")
    parser.add_argument("--model2", required=True, help="Name of second model")
    parser.add_argument("--provider2", required=True, help="Provider for second model")
    parser.add_argument(
        "--num-examples", type=int, default=10, help="Number of examples to test"
    )
    parser.add_argument(
        "--experiment-name", default="LLM_Comparison", help="MLflow experiment name"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        default=True,
        help="Enable disk cache for DSPy (default: True)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_false",
        dest="cache",
        help="Disable disk cache for DSPy",
    )

    args = parser.parse_args()

    # Create and run comparer
    comparer = LLMComparer(
        model1_name=args.model1,
        provider1_name=args.provider1,
        model2_name=args.model2,
        provider2_name=args.provider2,
        num_examples=args.num_examples,
        experiment_name=args.experiment_name,
        log_level=args.log_level,
        cache=args.cache,
    )

    try:
        comparer.run_comparison()
        print("\nComparison completed successfully!")
        print(f"Results saved to MLflow experiment: {args.experiment_name}")

    except Exception as e:
        print(f"Error during comparison: {e}")
        raise


if __name__ == "__main__":
    main()
