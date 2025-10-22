#!/usr/bin/env python3
"""
Flexible Evaluation Script for IFC Answer Engine

This script provides a configurable way to run evaluation experiments on the IFC QA system.
It supports various LLM models, customizable sample sizes, compiled model loading, and
proper MLflow tracking with comprehensive logging.

Usage:
    # Basic evaluation with GLM-4.6 model (no cache)
    uv run scripts/run_evaluation.py --model glm-4.6 --provider zai --no-cache

    # Evaluation with custom parameters
    uv run scripts/run_evaluation.py \
        --model qwen3-coder \
        --provider deepinfra \
        --num-samples 20 \
        --load-compiled \
        --experiment-name "Custom_Evaluation" \
        --cache

    # Continue existing MLflow run
    uv run scripts/run_evaluation.py \
        --run-id 1234567890abcdef \
        --model glm-4.6 \
        --provider zai
"""

import argparse
import time
from datetime import datetime
from typing import Dict, Optional

import dspy
import mlflow
import mlflow.dspy
from tqdm import tqdm

from src.config.agents import EvaluationPipelineConfig
from src.config.llm import LLM
from src.engine.schemas import OutputsCollection
from src.engine.util import get_logger
from src.experiment.datasets import DEVSET
from src.experiment.evaluation.evaluation import EvaluationPipeline


class EvaluationRunner:
    """Flexible evaluation runner for IFC Answer Engine."""

    def __init__(
        self,
        num_samples: int = 10,
        model_name: str = "glm-4.6",
        provider_name: str = "zai",
        load_compiled: bool = False,
        run_id: Optional[str] = None,
        use_cache: bool = False,
        experiment_name: str = "Evaluation",
        log_level: str = "INFO",
    ):
        self.num_samples = num_samples
        self.model_name = model_name
        self.provider_name = provider_name
        self.load_compiled = load_compiled
        self.run_id = run_id
        self.use_cache = use_cache
        self.experiment_name = experiment_name

        # Setup logger
        self.logger = get_logger(name="EvaluationRunner", log_level=log_level)

        # Prepare dataset
        self.dataset = DEVSET[:num_samples]
        self.logger.info(f"Using {len(self.dataset)} samples for evaluation")

        # Setup MLflow
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment(self.experiment_name)

    def _create_llm_config(self) -> LLM:
        """Create LLM configuration for the specified model and provider."""
        self.logger.info(f"Creating LLM config: {self.model_name} from {self.provider_name}")
        return LLM(
            model_name=self.model_name,
            provider_name=self.provider_name,
        )

    def _create_evaluation_config(self, llm_config: LLM) -> EvaluationPipelineConfig:
        """Create evaluation pipeline configuration."""
        return EvaluationPipelineConfig(
            load_optimized_module=self.load_compiled,
            llm=llm_config,
            log_level="INFO",
            experiment_name=self.experiment_name,
            start_run=(self.run_id is None),  # Only start new run if no run_id provided
        )

    def _log_parameters(self, llm_config: LLM):
        """Log experiment parameters to MLflow."""
        params = {
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "num_samples": len(self.dataset),
            "load_compiled": self.load_compiled,
            "use_cache": self.use_cache,
            "max_tokens": llm_config.max_tokens,
            "adapter": type(llm_config.adapter).__name__,
        }

        # Log cost information if available
        if llm_config.cost_input_token is not None:
            params["cost_input_token_per_m"] = llm_config.cost_input_token
        if llm_config.cost_output_token is not None:
            params["cost_output_token_per_m"] = llm_config.cost_output_token

        mlflow.log_params(params)
        self.logger.info(f"Logged parameters: {params}")

    def _calculate_and_log_metrics(
        self,
        outputs: OutputsCollection,
        llm_config: LLM,
        evaluation_time: float
    ) -> Dict:
        """Calculate and log evaluation metrics."""
        # Basic metrics
        mean_accuracy = outputs.mean_acc()
        total_input_tokens = outputs.lm_metrics.input_tokens or 0
        total_output_tokens = outputs.lm_metrics.output_tokens or 0
        total_tokens = total_input_tokens + total_output_tokens

        # Success metrics
        successful_examples = len([o for o in outputs.outputs if o.status == "success"])
        failed_examples = len(outputs.outputs) - successful_examples

        # Performance metrics
        tokens_per_second = total_tokens / evaluation_time if evaluation_time > 0 else 0

        # Similarity threshold metrics (0.85)
        similarity_metrics = self._calculate_similarity_above_threshold(outputs, threshold=0.85)

        # Cost calculations
        total_cost = 0.0
        input_cost = 0.0
        output_cost = 0.0

        if llm_config.cost_input_token is not None and llm_config.cost_output_token is not None:
            input_cost = (total_input_tokens / 1_000_000) * llm_config.cost_input_token
            output_cost = (total_output_tokens / 1_000_000) * llm_config.cost_output_token
            total_cost = input_cost + output_cost

        # Log metrics to MLflow
        metrics = {
            "mean_accuracy": mean_accuracy,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "successful_examples": successful_examples,
            "failed_examples": failed_examples,
            "success_rate": successful_examples / len(outputs.outputs) if outputs.outputs else 0,
            "evaluation_time_seconds": evaluation_time,
            "tokens_per_second": tokens_per_second,
            "avg_tokens_per_example": total_tokens / len(self.dataset) if self.dataset else 0,
            "answers_above_0_85_similarity": similarity_metrics["above_threshold"],
            "percentage_above_0_85_similarity": similarity_metrics["percentage_above_threshold"],
        }

        # Add cost metrics if available
        if total_cost > 0:
            metrics.update({
                "total_cost_usd": total_cost,
                "input_cost_usd": input_cost,
                "output_cost_usd": output_cost,
            })

        mlflow.log_metrics(metrics)

        # Prepare results summary
        results_summary = {
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "num_samples": len(self.dataset),
            "mean_accuracy": mean_accuracy,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "successful_examples": successful_examples,
            "failed_examples": failed_examples,
            "success_rate": successful_examples / len(outputs.outputs) if outputs.outputs else 0,
            "evaluation_time_seconds": evaluation_time,
            "tokens_per_second": tokens_per_second,
            "avg_tokens_per_example": total_tokens / len(self.dataset) if self.dataset else 0,
            "total_cost_usd": total_cost,
            "input_cost_usd": input_cost,
            "output_cost_usd": output_cost,
            "load_compiled": self.load_compiled,
            "use_cache": self.use_cache,
            # Add similarity metrics
            "answers_above_0_85_similarity": similarity_metrics["above_threshold"],
            "percentage_above_0_85_similarity": similarity_metrics["percentage_above_threshold"],
        }

        return results_summary

    def _calculate_similarity_above_threshold(self, outputs: OutputsCollection, threshold: float = 0.85) -> Dict:
        """Calculate percentage of answers above similarity threshold."""
        successful_outputs = [o for o in outputs.outputs if o.status == "success"]

        if not successful_outputs:
            return {
                "total_successful": 0,
                "above_threshold": 0,
                "percentage_above_threshold": 0.0
            }

        above_threshold_count = sum(
            1 for o in successful_outputs
            if o.result.similarity_score is not None and o.result.similarity_score >= threshold
        )

        percentage = (above_threshold_count / len(successful_outputs)) * 100

        return {
            "total_successful": len(successful_outputs),
            "above_threshold": above_threshold_count,
            "percentage_above_threshold": percentage
        }

    def _print_results(self, results_summary: Dict):
        """Print formatted evaluation results."""
        print("\n" + "=" * 80)
        print("EVALUATION RESULTS")
        print("=" * 80)

        print(f"Model: {results_summary['model_name']} ({results_summary['provider_name']})")
        print(f"Samples: {results_summary['num_samples']}")
        print(f"Load Compiled: {results_summary['load_compiled']}")
        print(f"Use Cache: {results_summary['use_cache']}")
        print()

        print("Performance Metrics:")
        print(f"  Mean Accuracy: {results_summary['mean_accuracy']:.3f}")
        print(f"  Success Rate: {results_summary['success_rate']:.3f}")
        print(f"  Successful Examples: {results_summary['successful_examples']}")
        print(f"  Failed Examples: {results_summary['failed_examples']}")
        print(f"  Answers with Similarity ≥0.85: {results_summary['answers_above_0_85_similarity']}/{results_summary['successful_examples']} ({results_summary['percentage_above_0_85_similarity']:.1f}%)")
        print()

        print("Token Usage:")
        print(f"  Input Tokens: {results_summary['total_input_tokens']:,}")
        print(f"  Output Tokens: {results_summary['total_output_tokens']:,}")
        print(f"  Total Tokens: {results_summary['total_tokens']:,}")
        print(f"  Avg Tokens/Example: {results_summary['avg_tokens_per_example']:.1f}")
        print()

        print("Performance:")
        print(f"  Evaluation Time: {results_summary['evaluation_time_seconds']:.1f}s")
        print(f"  Tokens/Second: {results_summary['tokens_per_second']:.1f}")
        print()

        if results_summary['total_cost_usd'] > 0:
            print("Cost Analysis:")
            print(f"  Input Cost: ${results_summary['input_cost_usd']:.4f}")
            print(f"  Output Cost: ${results_summary['output_cost_usd']:.4f}")
            print(f"  Total Cost: ${results_summary['total_cost_usd']:.4f}")
            print()

        print("MLflow Information:")
        if self.run_id:
            print(f"  Run ID: {self.run_id}")
        print(f"  Experiment: {self.experiment_name}")
        print(f"  View details: http://127.0.0.1:5000")
        print("=" * 80)

    def run_evaluation(self) -> Dict:
        """Run the evaluation experiment."""
        self.logger.info("Starting evaluation experiment")
        self.logger.info(f"Configuration: {self.model_name} from {self.provider_name}")
        self.logger.info(f"Samples: {len(self.dataset)}, Load Compiled: {self.load_compiled}")
        self.logger.info(f"Use Cache: {self.use_cache}")

        # Create configurations
        llm_config = self._create_llm_config()
        eval_config = self._create_evaluation_config(llm_config)

        # Setup MLflow run context
        is_new_run = self.run_id is None

        if self.run_id:
            # Continue existing run
            self.logger.info(f"Continuing existing MLflow run: {self.run_id}")
            mlflow_context = mlflow.start_run(run_id=self.run_id)
        else:
            # Start new run
            run_name = f"{self.model_name}_{self.provider_name}_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
            self.logger.info(f"Starting new MLflow run: {run_name}")
            mlflow_context = mlflow.start_run(run_name=run_name)

        try:
            with mlflow_context as run:
                self.run_id = run.info.run_id
                self.logger.info(f"MLflow run started with ID: {self.run_id}")

                # Log parameters only for new runs
                if is_new_run:
                    self._log_parameters(llm_config)
                else:
                    self.logger.info("Continuing existing run - skipping parameter logging")

                # Enable DSPy autologging
                mlflow.dspy.autolog()  # type: ignore

                # Configure DSPy cache
                dspy.configure_cache(enable_disk_cache=self.use_cache)
                self.logger.info(f"DSPy cache enabled: {self.use_cache}")

                # Create evaluation pipeline
                evaluation_pipeline = EvaluationPipeline(config=eval_config)

                # Time the evaluation
                start_time = time.time()

                # Run evaluation with progress bar
                self.logger.info("Running evaluation...")
                with tqdm(total=len(self.dataset), desc=f"Evaluating {self.model_name}") as pbar:
                    outputs = evaluation_pipeline.forward(
                        dataset=self.dataset,
                        mode=f"_{self.model_name}_{self.provider_name}"
                    )
                    pbar.update(len(self.dataset))

                end_time = time.time()
                evaluation_time = end_time - start_time

                # Calculate and log metrics
                results_summary = self._calculate_and_log_metrics(
                    outputs, llm_config, evaluation_time
                )

                # Log additional info
                mlflow.set_tag("evaluation_status", "completed")
                mlflow.set_tag("dataset_size", len(self.dataset))

                self.logger.info("Evaluation completed successfully")
                self.logger.info(f"Mean accuracy: {results_summary['mean_accuracy']:.3f}")
                self.logger.info(f"Total tokens: {results_summary['total_tokens']:,}")
                self.logger.info(f"Evaluation time: {evaluation_time:.1f}s")

                # Print results
                self._print_results(results_summary)

                return results_summary

        except Exception as e:
            self.logger.error(f"Evaluation failed: {e}")
            if self.run_id:
                mlflow.set_tag("evaluation_status", "failed")
                mlflow.set_tag("error", str(e))
            raise


def main():
    """Main function to run the evaluation."""
    parser = argparse.ArgumentParser(
        description="Run evaluation experiments on IFC Answer Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic evaluation with GLM-4.6 (no cache)
  uv run scripts/run_evaluation.py --model glm-4.6 --provider zai --no-cache

  # Custom evaluation with compiled model
  uv run scripts/run_evaluation.py --model qwen3-coder --provider deepinfra --num-samples 20 --load-compiled --cache

  # Continue existing run
  uv run scripts/run_evaluation.py --run-id 1234567890abcdef --model glm-4.6 --provider zai
        """
    )

    parser.add_argument(
        "--num-samples",
        type=int,
        default=10,
        help="Number of samples to evaluate (default: 10)"
    )

    parser.add_argument(
        "--model",
        default="glm-4.6",
        help="LLM model name (default: glm-4.6)"
    )

    parser.add_argument(
        "--provider",
        default="zai",
        help="LLM provider name (default: zai)"
    )

    parser.add_argument(
        "--load-compiled",
        action="store_true",
        help="Load compiled model (default: False)"
    )

    parser.add_argument(
        "--no-load-compiled",
        action="store_false",
        dest="load_compiled",
        help="Do not load compiled model"
    )

    parser.add_argument(
        "--run-id",
        help="Optional existing MLflow run ID to continue"
    )

    parser.add_argument(
        "--cache",
        action="store_true",
        default=False,
        help="Enable DSPy disk cache (default: False)"
    )

    parser.add_argument(
        "--no-cache",
        action="store_false",
        dest="cache",
        help="Disable DSPy disk cache"
    )

    parser.add_argument(
        "--experiment-name",
        default="Evaluation",
        help="MLflow experiment name (default: Evaluation)"
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.num_samples <= 0:
        print("Error: --num-samples must be positive")
        return 1

    if args.num_samples > len(DEVSET):
        print(f"Error: --num-samples ({args.num_samples}) exceeds available dataset size ({len(DEVSET)})")
        return 1

    # Create and run evaluation
    runner = EvaluationRunner(
        num_samples=args.num_samples,
        model_name=args.model,
        provider_name=args.provider,
        load_compiled=args.load_compiled,
        run_id=args.run_id,
        use_cache=args.cache,
        experiment_name=args.experiment_name,
        log_level=args.log_level,
    )

    try:
        runner.run_evaluation()
        print("\nEvaluation completed successfully!")
        return 0

    except Exception as e:
        print(f"\nError during evaluation: {e}")
        return 1


if __name__ == "__main__":
    exit(main())