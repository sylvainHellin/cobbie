#!/usr/bin/env python3
"""
Flexible Training Script for IFC Answer Engine

This script provides a configurable way to run training experiments on the IFC QA system.
It supports various LLM models, customizable sample sizes, compiled model loading, and
proper MLflow tracking with comprehensive logging.

Usage:
    # Basic training with GLM-4.6 model (no cache)
    uv run scripts/run_training.py --model glm-4.6 --provider zai --no-cache

    # Training with custom parameters and evaluation
    uv run scripts/run_training.py \
        --model qwen3-coder \
        --provider deepinfra \
        --num-samples 20 \
        --load-compiled \
        --experiment-name "Custom_Training" \
        --cache \
        --evaluate

    # Continue existing MLflow run
    uv run scripts/run_training.py \
        --run-id 1234567890abcdef \
        --model glm-4.6 \
        --provider zai
"""

import argparse
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional, Literal

import dspy
import mlflow
import mlflow.dspy
from tqdm import tqdm

from src.config.agents import TrainingPipelineConfig
from src.config.llm import LLM
from src.engine.schemas import OutputsCollection, QA_Pair
from src.engine.util import get_logger
from src.experiment.datasets import load_train_dev_split
from src.experiment.db.experiment_models import Run
from src.experiment.db.query import add_run, update_run_metrics
from src.experiment.training.training_pipeline import TrainingPipeline


class TrainingRunner:
    """Flexible training runner for IFC Answer Engine."""

    def __init__(
        self,
        num_samples: Optional[int] = None,
        model_name: str = "glm-4.6",
        provider_name: str = "zai",
        load_compiled: bool = False,
        run_id: Optional[str] = None,
        use_cache: bool = False,
        experiment_name: str = "Training",
        evaluate: bool = False,
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
        batch_size: Optional[int] = None,
        force_batches: bool = False,
        disable_batches: bool = False,
        continue_run: bool = False,
    ):
        self.num_samples = num_samples
        self.model_name = model_name
        self.provider_name = provider_name
        self.load_compiled = load_compiled
        self.run_id = run_id
        self.use_cache = use_cache
        self.experiment_name = experiment_name
        self.evaluate = evaluate
        self.batch_size = batch_size
        self.force_batches = force_batches
        self.disable_batches = disable_batches
        self.continue_run = continue_run

        # Setup logger
        self.logger = get_logger(name="TrainingRunner", log_level=log_level)

        # Load and prepare datasets
        self.trainset_full, self.devset_full = load_train_dev_split()

        # Determine sample size
        if self.num_samples is None:
            self.num_samples = len(self.trainset_full)

        if self.num_samples > len(self.trainset_full):
            self.logger.warning(
                f"Requested {self.num_samples} samples, but only {len(self.trainset_full)} available. Using full dataset."
            )
            self.num_samples = len(self.trainset_full)

        # Prepare actual datasets
        self.trainset_full = self.trainset_full[: self.num_samples]
        self.devset = self.devset_full  # Use full devset for evaluation

        # Setup batch processing
        should_use_batches = self._should_use_batches()

        if self.disable_batches:
            self.batch_size = None
            self.logger.info("Batch processing explicitly disabled via --disable-batches flag")
        elif self.force_batches:
            self.batch_size = self.batch_size or 30
            self.logger.info("Batch processing forced via --force-batches flag")
        elif self.batch_size:
            self.logger.info(f"Batch processing enabled with explicit batch size {self.batch_size}")
        elif should_use_batches:
            self.batch_size = 30
            self.logger.info(f"Auto-enabled batch processing for large dataset ({len(self.trainset_full)} > 100 samples) with batch size {self.batch_size}")
        else:
            self.batch_size = None
            self.logger.info(f"Single-process mode enabled (dataset size {len(self.trainset_full)} <= 100 samples)")

        self.logger.info(
            f"Using {len(self.trainset_full)} training samples and {len(self.devset)} dev samples"
        )

        # Setup MLflow
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment(self.experiment_name)

    def _should_use_batches(self) -> bool:
        """Determine if batched mode should be used."""
        if self.force_batches:
            return True
        # Auto-enable batches for large datasets (>100 samples)
        return len(self.trainset_full) > 100

    def _get_most_recent_run_info(self) -> Optional[Dict]:
        """Get information about the most recent run to continue."""
        try:
            runs = mlflow.search_runs(
                experiment_names=[self.experiment_name],
                order_by=["start_time DESC"],
                max_results=1,
                output_format="list",
            )

            if not runs:
                return None

            latest_run = runs[0]
            run_id = latest_run.info.run_id

            # Get last processed question from traces
            last_question_id = self._get_last_question_id_from_traces(run_id)

            return {
                "run_id": run_id,
                "last_question_id": last_question_id,
                "status": latest_run.info.status,
                "start_time": latest_run.info.start_time,
            }

        except Exception as e:
            self.logger.error(f"Failed to get recent run info: {e}")
            return None

    def _get_last_question_id_from_traces(self, run_id: str) -> Optional[int]:
        """Extract the last processed question ID from MLflow traces."""
        try:
            traces = mlflow.search_traces(
                run_id=run_id,
                filter_string="name LIKE 'train_question_id_%'",
                order_by=["timestamp DESC"],
                max_results=1000,
                return_type="list",
            )

            question_ids = []
            for trace in traces:
                if trace.spans:
                    span_name = trace.spans[0].name
                    if span_name.startswith("train_question_id_"):
                        try:
                            question_id = int(span_name.split("_")[-1])
                            question_ids.append(question_id)
                        except (ValueError, IndexError):
                            continue

            return max(question_ids) if question_ids else None

        except Exception as e:
            self.logger.warning(f"Failed to get last question ID from traces: {e}")
            return None

    def _setup_resume_or_new_run(self) -> tuple[Optional[str], List[QA_Pair], bool]:
        """Setup run for resume or start new run."""
        if self.continue_run:
            recent_run_info = self._get_most_recent_run_info()

            if recent_run_info and recent_run_info["status"] != "FINISHED":
                run_id = recent_run_info["run_id"]
                last_question_id = recent_run_info["last_question_id"]

                self.logger.info(f"Found recent run: {run_id}")
                if last_question_id is not None:
                    self.logger.info(f"Resuming from question_id {last_question_id}")
                    trainset = self._prepare_resume_trainset(last_question_id)
                else:
                    self.logger.info(
                        "No previous questions found, starting from beginning"
                    )
                    trainset = self.trainset_full

                return run_id, trainset, True
            else:
                self.logger.warning("No suitable recent run found, starting new run")

        return None, self.trainset_full, False

    def _prepare_resume_trainset(self, last_question_id: int) -> List[QA_Pair]:
        """Prepare training set for resume by finding questions after last_question_id."""
        resume_from_index = None
        for i, qa_pair in enumerate(self.trainset_full):
            if qa_pair.id == last_question_id:
                resume_from_index = i + 1
                break

        if resume_from_index is None:
            self.logger.warning(
                f"Question ID {last_question_id} not found in training set, starting from beginning"
            )
            return self.trainset_full

        if resume_from_index >= len(self.trainset_full):
            self.logger.info("All questions have been processed, training complete")
            return []

        remaining_questions = self.trainset_full[resume_from_index:]
        self.logger.info(
            f"Resuming with {len(remaining_questions)} remaining questions"
        )
        return remaining_questions

    def _process_single_batch(
        self, batch_num: int, start_index: int, total_batches: int, attempt: int
    ) -> bool:
        """Process a single batch in a separate Python process."""

        cmd = [
            "uv",
            "run",
            "python",
            "scripts/run_training_batch.py",
            "--run-id",
            self.run_id,
            "--experiment-name",
            self.experiment_name,
            "--model",
            self.model_name,
            "--provider",
            self.provider_name,
            "--start-index",
            str(start_index),
            "--batch-size",
            str(self.batch_size),
            "--total-samples",
            str(len(self.trainset)),
            "--batch-num",
            str(batch_num + 1),
            "--total-batches",
            str(total_batches),
        ]

        self.logger.debug(f"Batch command: {' '.join(cmd)}")

        try:
            self.logger.info(
                f"Starting batch {batch_num + 1}/{total_batches} (attempt {attempt}) - processing questions {start_index} to {min(start_index + self.batch_size, len(self.trainset))}"
            )
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout
            )

            if result.returncode == 0:
                self.logger.info(f"Batch {batch_num + 1}/{total_batches} completed successfully")
                # Log any stdout output for debugging
                if result.stdout.strip():
                    self.logger.debug(f"Batch {batch_num + 1} stdout: {result.stdout.strip()}")
                return True
            else:
                self.logger.error(
                    f"Batch {batch_num + 1}/{total_batches} failed with return code {result.returncode}"
                )
                # Enhanced error reporting
                self.logger.error(f"Command executed: {' '.join(cmd)}")
                if result.stdout.strip():
                    self.logger.error(f"Batch {batch_num + 1} stdout:\n{result.stdout}")
                if result.stderr.strip():
                    self.logger.error(f"Batch {batch_num + 1} stderr:\n{result.stderr}")
                else:
                    self.logger.error(f"Batch {batch_num + 1} produced no stderr output")

                # Try to identify common issues
                error_output = (result.stdout + result.stderr).lower()
                if "module not found" in error_output or "import" in error_output:
                    self.logger.error("❌ Possible import/module dependency issue - check if all required modules are available")
                elif "mlflow" in error_output:
                    self.logger.error("❌ MLflow connection issue - ensure MLflow server is running on http://127.0.0.1:5000")
                elif "timeout" in error_output:
                    self.logger.error("❌ Timeout issue - consider reducing batch size or checking system resources")
                elif "memory" in error_output or "out of memory" in error_output:
                    self.logger.error("❌ Memory issue - consider reducing batch size")
                else:
                    self.logger.error("❌ Unknown error - see above output for details")

                return False

        except subprocess.TimeoutExpired:
            self.logger.error(f"Batch {batch_num + 1}/{total_batches} timed out after 1 hour")
            self.logger.error("Consider reducing batch size or checking system resources")
            return False
        except Exception as e:
            self.logger.error(f"Failed to run batch {batch_num + 1}/{total_batches}: {e}")
            self.logger.error(f"Exception type: {type(e).__name__}")
            return False

    def _run_training_batches(self) -> Dict:
        """Run training in batches with process isolation and fallback to single-process mode."""
        total_batches = (len(self.trainset) + self.batch_size - 1) // self.batch_size

        self.logger.info(
            f"Starting batched training: {total_batches} batches, {len(self.trainset)} total questions"
        )

        successful_batches = 0
        failed_batches = 0

        for batch_num in range(total_batches):
            start_index = batch_num * self.batch_size

            max_retries = 3
            for attempt in range(max_retries):
                success = self._process_single_batch(
                    batch_num=batch_num,
                    start_index=start_index,
                    total_batches=total_batches,
                    attempt=attempt + 1,
                )

                if success:
                    successful_batches += 1
                    break
                elif attempt < max_retries - 1:
                    self.logger.warning(
                        f"Batch {batch_num + 1}/{total_batches} failed, restarting Python process"
                    )
                    time.sleep(10)
                else:
                    failed_batches += 1
                    self.logger.error(
                        f"Batch {batch_num + 1}/{total_batches} failed after {max_retries} attempts"
                    )

        # Check if batch processing failed too often and consider fallback
        failure_rate = failed_batches / total_batches if total_batches > 0 else 0

        if failure_rate > 0.5:  # If more than 50% of batches failed
            self.logger.error(f"🚨 Batch processing failed for {failed_batches}/{total_batches} batches ({failure_rate:.1%} failure rate)")
            self.logger.error("💡 Attempting fallback to single-process mode...")

            # Create dummy configs for fallback
            llm_config = self._create_llm_config()
            training_config = self._create_training_config(llm_config)

            try:
                self.logger.info("🔄 Switching to single-process training mode")
                return self._run_training_single_process(llm_config, training_config)
            except Exception as e:
                self.logger.error(f"❌ Fallback to single-process mode also failed: {e}")
                # Still return batch metrics but indicate failure
                return self._compile_final_metrics(successful_batches, total_batches)

        if failed_batches > 0:
            self.logger.warning(f"⚠️  Batch processing completed with {failed_batches} failed batches")
            self.logger.warning("💡 Consider using --disable-batches flag if issues persist")

        return self._compile_final_metrics(successful_batches, total_batches)

    def _compile_final_metrics(
        self, successful_batches: int, total_batches: int
    ) -> Dict:
        """Compile final metrics after batch processing."""
        # For batch processing, we need to get metrics from MLflow
        # This is a simplified version - in practice you'd aggregate metrics from all batches
        return {
            "batch_processing": True,
            "total_batches": total_batches,
            "successful_batches": successful_batches,
            "failed_batches": total_batches - successful_batches,
            "batch_success_rate": successful_batches / total_batches
            if total_batches > 0
            else 0,
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "experiment_name": self.experiment_name,
            "run_id": self.run_id,
        }

    def _create_llm_config(self) -> LLM:
        """Create LLM configuration for the specified model and provider."""
        self.logger.info(
            f"Creating LLM config: {self.model_name} from {self.provider_name}"
        )
        return LLM(
            model_name=self.model_name,
            provider_name=self.provider_name,
        )

    def _create_training_config(self, llm_config: LLM) -> TrainingPipelineConfig:
        """Create training pipeline configuration."""
        return TrainingPipelineConfig(
            load_optimized_module=self.load_compiled,
            llm=llm_config,
            log_level="INFO",
            experiment_name=self.experiment_name,
            evaluate=self.evaluate,
        )

    def _log_parameters(self, llm_config: LLM):
        """Log experiment parameters to MLflow."""
        params = {
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "num_train_samples": len(self.trainset),
            "num_dev_samples": len(self.devset),
            "load_compiled": self.load_compiled,
            "use_cache": self.use_cache,
            "evaluate": self.evaluate,
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
        self, outputs: OutputsCollection, llm_config: LLM, training_time: float
    ) -> Dict:
        """Calculate and log training metrics."""
        # Basic metrics
        mean_accuracy = outputs.mean_acc()
        total_input_tokens = outputs.lm_metrics.input_tokens or 0
        total_output_tokens = outputs.lm_metrics.output_tokens or 0
        total_tokens = total_input_tokens + total_output_tokens

        # Success metrics
        successful_examples = len([o for o in outputs.outputs if o.status == "success"])
        failed_examples = len(outputs.outputs) - successful_examples

        # Performance metrics
        tokens_per_second = total_tokens / training_time if training_time > 0 else 0

        # Similarity threshold metrics (0.85)
        similarity_metrics = self._calculate_similarity_above_threshold(
            outputs, threshold=0.85
        )

        # Tool metrics
        tools_created = outputs.tools_metrics.nb_tools_created
        tools_updated = outputs.tools_metrics.nb_tools_updated
        tools_merged = outputs.tools_metrics.nb_tools_merged
        total_tools_modified = tools_created + tools_updated + tools_merged

        # Cost calculations
        total_cost = 0.0
        input_cost = 0.0
        output_cost = 0.0

        if (
            llm_config.cost_input_token is not None
            and llm_config.cost_output_token is not None
        ):
            input_cost = (total_input_tokens / 1_000_000) * llm_config.cost_input_token
            output_cost = (
                total_output_tokens / 1_000_000
            ) * llm_config.cost_output_token
            total_cost = input_cost + output_cost

        # Log metrics to MLflow
        metrics = {
            "mean_accuracy": mean_accuracy,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "successful_examples": successful_examples,
            "failed_examples": failed_examples,
            "success_rate": successful_examples / len(outputs.outputs)
            if outputs.outputs
            else 0,
            "training_time_seconds": training_time,
            "tokens_per_second": tokens_per_second,
            "avg_tokens_per_example": total_tokens / len(self.trainset)
            if self.trainset
            else 0,
            "answers_above_0_85_similarity": similarity_metrics["above_threshold"],
            "percentage_above_0_85_similarity": similarity_metrics[
                "percentage_above_threshold"
            ],
            # Tool metrics
            "tools_created": tools_created,
            "tools_updated": tools_updated,
            "tools_merged": tools_merged,
            "total_tools_modified": total_tools_modified,
        }

        # Add cost metrics if available
        if total_cost > 0:
            metrics.update(
                {
                    "total_cost_usd": total_cost,
                    "input_cost_usd": input_cost,
                    "output_cost_usd": output_cost,
                }
            )

        mlflow.log_metrics(metrics)

        # Prepare results summary
        results_summary = {
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "num_train_samples": len(self.trainset),
            "num_dev_samples": len(self.devset),
            "mean_accuracy": mean_accuracy,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "successful_examples": successful_examples,
            "failed_examples": failed_examples,
            "success_rate": successful_examples / len(outputs.outputs)
            if outputs.outputs
            else 0,
            "training_time_seconds": training_time,
            "tokens_per_second": tokens_per_second,
            "avg_tokens_per_example": total_tokens / len(self.trainset)
            if self.trainset
            else 0,
            "total_cost_usd": total_cost,
            "input_cost_usd": input_cost,
            "output_cost_usd": output_cost,
            "load_compiled": self.load_compiled,
            "use_cache": self.use_cache,
            "evaluate": self.evaluate,
            # Tool metrics
            "tools_created": tools_created,
            "tools_updated": tools_updated,
            "tools_merged": tools_merged,
            "total_tools_modified": total_tools_modified,
            # Add similarity metrics
            "answers_above_0_85_similarity": similarity_metrics["above_threshold"],
            "percentage_above_0_85_similarity": similarity_metrics[
                "percentage_above_threshold"
            ],
        }

        return results_summary

    def _calculate_similarity_above_threshold(
        self, outputs: OutputsCollection, threshold: float = 0.85
    ) -> Dict:
        """Calculate percentage of answers above similarity threshold."""
        successful_outputs = [o for o in outputs.outputs if o.status == "success"]

        if not successful_outputs:
            return {
                "total_successful": 0,
                "above_threshold": 0,
                "percentage_above_threshold": 0.0,
            }

        above_threshold_count = sum(
            1
            for o in successful_outputs
            if o.result.similarity_score is not None
            and o.result.similarity_score >= threshold
        )

        percentage = (above_threshold_count / len(successful_outputs)) * 100

        return {
            "total_successful": len(successful_outputs),
            "above_threshold": above_threshold_count,
            "percentage_above_threshold": percentage,
        }

    def _print_results(self, results_summary: Dict):
        """Print formatted training results."""
        print("\n" + "=" * 80)
        print("TRAINING RESULTS")
        print("=" * 80)

        if results_summary.get("batch_processing"):
            # Batch processing mode
            print(
                f"Model: {results_summary['model_name']} ({results_summary['provider_name']})"
            )
            print(f"Training Mode: Batched Processing")
            print(f"Total Batches: {results_summary['total_batches']}")
            print(f"Successful Batches: {results_summary['successful_batches']}")
            print(f"Failed Batches: {results_summary['failed_batches']}")
            print(f"Batch Success Rate: {results_summary['batch_success_rate']:.3f}")
            print()
            print("Note: Detailed metrics available in MLflow")
        else:
            # Single-process mode
            print(
                f"Model: {results_summary['model_name']} ({results_summary['provider_name']})"
            )
            print(f"Training Samples: {results_summary['num_train_samples']}")
            print(f"Dev Samples: {results_summary['num_dev_samples']}")
            print(f"Load Compiled: {results_summary['load_compiled']}")
            print(f"Use Cache: {results_summary['use_cache']}")
            print(f"Evaluate: {results_summary['evaluate']}")
            print()

            print("Performance Metrics:")
            print(f"  Mean Accuracy: {results_summary['mean_accuracy']:.3f}")
            print(f"  Success Rate: {results_summary['success_rate']:.3f}")
            print(f"  Successful Examples: {results_summary['successful_examples']}")
            print(f"  Failed Examples: {results_summary['failed_examples']}")
            print(
                f"  Answers with Similarity ≥0.85: {results_summary['answers_above_0_85_similarity']}/{results_summary['successful_examples']} ({results_summary['percentage_above_0_85_similarity']:.1f}%)"
            )
            print()

            print("Tool Creation Metrics:")
            print(f"  Tools Created: {results_summary['tools_created']}")
            print(f"  Tools Updated: {results_summary['tools_updated']}")
            print(f"  Tools Merged: {results_summary['tools_merged']}")
            print(f"  Total Tools Modified: {results_summary['total_tools_modified']}")
            print()

            print("Token Usage:")
            print(f"  Input Tokens: {results_summary['total_input_tokens']:,}")
            print(f"  Output Tokens: {results_summary['total_output_tokens']:,}")
            print(f"  Total Tokens: {results_summary['total_tokens']:,}")
            print(
                f"  Avg Tokens/Example: {results_summary['avg_tokens_per_example']:.1f}"
            )
            print()

            print("Performance:")
            print(f"  Training Time: {results_summary['training_time_seconds']:.1f}s")
            print(f"  Tokens/Second: {results_summary['tokens_per_second']:.1f}")
            print()

            if results_summary["total_cost_usd"] > 0:
                print("Cost Analysis:")
                print(f"  Input Cost: ${results_summary['input_cost_usd']:.4f}")
                print(f"  Output Cost: ${results_summary['output_cost_usd']:.4f}")
                print(f"  Total Cost: ${results_summary['total_cost_usd']:.4f}")
                print()

        print("MLflow Information:")
        if self.run_id:
            print(f"  Run ID: {self.run_id}")
        print(f"  Experiment: {self.experiment_name}")
        print("  View details: http://127.0.0.1:5000")
        print("=" * 80)

    def run_training(self) -> Dict:
        """Run the training experiment."""
        self.logger.info("Starting training experiment")
        self.logger.info(f"Configuration: {self.model_name} from {self.provider_name}")
        self.logger.info(
            f"Training samples: {len(self.trainset_full)}, Dev samples: {len(self.devset_full)}"
        )
        self.logger.info(f"Load Compiled: {self.load_compiled}")
        self.logger.info(f"Use Cache: {self.use_cache}")
        self.logger.info(f"Evaluate: {self.evaluate}")
        self.logger.info(f"Batch Size: {self.batch_size}")
        self.logger.info(f"Force Batches: {self.force_batches}")
        self.logger.info(f"Continue Run: {self.continue_run}")

        # Setup resume or new run
        resume_run_id, trainset, is_resume = self._setup_resume_or_new_run()
        self.trainset = trainset

        if not self.trainset:
            self.logger.info("No questions to process - training already complete")
            return {"status": "already_complete", "run_id": resume_run_id}

        # Create configurations
        llm_config = self._create_llm_config()
        training_config = self._create_training_config(llm_config)

        # Setup MLflow run context
        if is_resume and resume_run_id:
            # Continue existing run
            self.run_id = resume_run_id
            self.logger.info(f"Continuing existing MLflow run: {self.run_id}")
            mlflow_context = mlflow.start_run(run_id=self.run_id)
            is_new_run = False
        elif self.run_id:
            # Explicit run ID provided
            self.logger.info(f"Using provided MLflow run ID: {self.run_id}")
            mlflow_context = mlflow.start_run(run_id=self.run_id)
            is_new_run = False
        else:
            # Start new run
            date_str = datetime.now().strftime("%Y-%m-%d")
            run_name = f"{date_str}-{self.model_name}-{len(self.trainset)}"
            self.logger.info(f"Starting new MLflow run: {run_name}")
            mlflow_context = mlflow.start_run(run_name=run_name)
            is_new_run = True

        try:
            with mlflow_context as run:
                self.run_id = run.info.run_id
                self.logger.info(f"MLflow run started with ID: {self.run_id}")

                # Log parameters only for new runs
                if is_new_run:
                    self._log_parameters(llm_config)
                    mlflow.log_params(
                        {
                            "batch_size": self.batch_size,
                            "force_batches": self.force_batches,
                            "continue_run": self.continue_run,
                            "is_batched": self.batch_size is not None,
                        }
                    )
                else:
                    self.logger.info(
                        "Continuing existing run - skipping parameter logging"
                    )

                # Enable DSPy autologging
                mlflow.dspy.autolog()  # type: ignore

                # Configure DSPy cache
                dspy.configure_cache(enable_disk_cache=self.use_cache)
                self.logger.info(f"DSPy cache enabled: {self.use_cache}")

                # Create database entries for new runs
                if is_new_run:
                    experiment = mlflow.get_experiment_by_name(self.experiment_name)
                    experiment_id = str(experiment.experiment_id) if experiment else "0"

                    # Create run in local DB
                    timestamp = datetime.now()
                    db_run = Run(
                        id=self.run_id,
                        experiment_id=experiment_id,
                        name=run_name if is_new_run else f"continued_{self.run_id}",
                        timestamp=timestamp,
                    )
                    add_run(run=db_run)

                # Determine training mode and execute
                if self.batch_size:
                    # Batched mode with process isolation
                    self.logger.info(
                        "Using batched training mode with process isolation"
                    )
                    results_summary = self._run_training_batches()
                else:
                    # Single-process mode (original logic)
                    self.logger.info("Using single-process training mode")
                    results_summary = self._run_training_single_process(
                        llm_config, training_config
                    )

                # Log additional info
                mlflow.set_tag("training_status", "completed")
                mlflow.set_tag("trainset_size", len(self.trainset))
                mlflow.set_tag("devset_size", len(self.devset_full))
                mlflow.set_tag("batch_processing", self.batch_size is not None)

                self.logger.info("Training completed successfully")
                if "mean_accuracy" in results_summary:
                    self.logger.info(
                        f"Mean accuracy: {results_summary['mean_accuracy']:.3f}"
                    )
                self.logger.info(f"Total questions processed: {len(self.trainset)}")

                # Print results
                self._print_results(results_summary)

                return results_summary

        except Exception as e:
            self.logger.error(f"Training failed: {e}")
            if self.run_id:
                mlflow.set_tag("training_status", "failed")
                mlflow.set_tag("error", str(e))
            raise

    def _run_training_single_process(
        self, llm_config: LLM, training_config: TrainingPipelineConfig
    ) -> Dict:
        """Run training in single-process mode (original logic)."""
        # Create training pipeline
        experiment = mlflow.get_experiment_by_name(self.experiment_name)
        experiment_id = str(experiment.experiment_id) if experiment else "0"
        training_pipeline = TrainingPipeline(
            run_id=self.run_id,
            experiment_id=experiment_id,
            config=training_config,
        )

        # Time the training
        start_time = time.time()

        # Run training with progress bar
        self.logger.info("Running training...")
        with tqdm(total=len(self.trainset), desc=f"Training {self.model_name}") as pbar:
            outputs = training_pipeline.forward(
                devset=self.devset_full if self.evaluate else [],
                trainset=self.trainset,
            )
            pbar.update(len(self.trainset))

        end_time = time.time()
        training_time = end_time - start_time

        # Calculate and log metrics
        results_summary = self._calculate_and_log_metrics(
            outputs, llm_config, training_time
        )

        # Update run metrics in database
        update_run_metrics(run_id=self.run_id)

        return results_summary


def main():
    """Main function to run the training."""
    parser = argparse.ArgumentParser(
        description="Run training experiments on IFC Answer Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic training with GLM-4.6 (no cache)
  uv run python scripts/run_training.py --model glm-4.6 --provider zai --no-cache

  # Custom training with evaluation and compiled model
  uv run python scripts/run_training.py --model qwen3-coder --provider deepinfra --num-samples 20 --load-compiled --cache --evaluate

  # Continue existing run
  uv run python scripts/run_training.py --run-id 1234567890abcdef --model glm-4.6 --provider zai

  # Auto-enable batching for large datasets
  uv run python scripts/run_training.py --model glm-4.6 --provider zai --no-cache

  # Force batching for small datasets
  uv run python scripts/run_training.py --model glm-4.6 --provider zai --force-batches --batch-size 30

  # Continue the most recent run
  uv run python scripts/run_training.py --continue --model glm-4.6 --provider zai

  # Continue with custom batch size
  uv run python scripts/run_training.py --continue --model glm-4.6 --provider zai --batch-size 20

  # Force single-process mode for large datasets (if batch processing has issues)
  uv run python scripts/run_training.py --model glm-4.6 --provider zai --disable-batches
        """,
    )

    parser.add_argument(
        "--num-samples",
        type=int,
        help="Number of training samples to use (default: all available)",
    )

    parser.add_argument(
        "--model", default="glm-4.6", help="LLM model name (default: glm-4.6)"
    )

    parser.add_argument(
        "--provider", default="zai", help="LLM provider name (default: zai)"
    )

    parser.add_argument(
        "--load-compiled",
        action="store_true",
        help="Load compiled model (default: False)",
    )

    parser.add_argument(
        "--no-load-compiled",
        action="store_false",
        dest="load_compiled",
        help="Do not load compiled model",
    )

    parser.add_argument("--run-id", help="Optional existing MLflow run ID to continue")

    parser.add_argument(
        "--cache",
        action="store_true",
        default=False,
        help="Enable DSPy disk cache (default: False)",
    )

    parser.add_argument(
        "--no-cache", action="store_false", dest="cache", help="Disable DSPy disk cache"
    )

    parser.add_argument(
        "--experiment-name",
        default="Training",
        help="MLflow experiment name (default: Training)",
    )

    parser.add_argument(
        "--evaluate",
        action="store_true",
        default=False,
        help="Run evaluation before and after training (default: False)",
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument(
        "--continue",
        action="store_true",
        dest="continue_run",
        help="Continue the most recent run in the experiment (requires MLflow server)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Process training data in batches (default: 30 for large datasets, None for small datasets)",
    )

    parser.add_argument(
        "--force-batches",
        action="store_true",
        help="Force batched mode even for small datasets",
    )

    parser.add_argument(
        "--disable-batches",
        action="store_true",
        help="Force single-process mode even for large datasets (useful if batch processing has issues)",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.num_samples is not None and args.num_samples <= 0:
        print("Error: --num-samples must be positive")
        return 1

    # Validate conflicting batch arguments
    if args.force_batches and args.disable_batches:
        print("Error: Cannot use both --force-batches and --disable-batches simultaneously")
        return 1

    if args.batch_size is not None and args.disable_batches:
        print("Error: Cannot specify --batch-size when using --disable-batches")
        return 1

    # Create and run training
    runner = TrainingRunner(
        num_samples=args.num_samples,
        model_name=args.model,
        provider_name=args.provider,
        load_compiled=args.load_compiled,
        run_id=args.run_id,
        use_cache=args.cache,
        experiment_name=args.experiment_name,
        evaluate=args.evaluate,
        log_level=args.log_level,
        batch_size=args.batch_size,
        force_batches=args.force_batches,
        disable_batches=args.disable_batches,
        continue_run=args.continue_run,
    )

    try:
        runner.run_training()
        print("\nTraining completed successfully!")
        return 0

    except Exception as e:
        print(f"\nError during training: {e}")
        return 1


if __name__ == "__main__":
    exit(main())