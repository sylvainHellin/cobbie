#!/usr/bin/env python3
"""
Evaluation Script for IFC Answer Engine

This script provides a single, clean interface for evaluating both DSPy and BAML engines
using the same evaluation approach. It eliminates the EvaluationPipeline wrapper and uses
engines directly via the create_engine() factory.

Usage:
    # Basic evaluation with DSPy engine (auto-detect from config)
    uv run scripts/run_evaluation.py --model glm-4.6 --provider zai --num-samples 10

    # Force BAML engine evaluation
    uv run scripts/run_evaluation.py --engine-type baml --model glm-4.6 --provider zai

    # DSPy-specific: Load compiled model and enable cache
    uv run scripts/run_evaluation.py --engine-type dspy --load-compiled --cache

    # Continue existing MLflow run
    uv run scripts/run_evaluation.py --run-id 1234567890abcdef --model glm-4.6 --provider zai
"""

import argparse
import time
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, cast

import dspy
import mlflow
import mlflow.dspy
from tqdm import tqdm

from src.config.agents import AGENT_CONFIGS, IfcAnswerEngineConfig
from src.engine import create_engine
from src.engine.components.baml_answer_verifier import BamlAnswerVerifier
from src.engine.schemas import ModuleOutput
from src.engine.util import get_logger
from src.experiment.datasets import DEVSET, Dataset


class EvaluationRunner:
    """Evaluation runner for both DSPy and BAML engines."""

    def __init__(
        self,
        engine_type: Literal["baml", "dspy"] = "baml",
        model_name: Optional[str] = None,
        provider_name: Optional[str] = None,
        num_samples: int = 15,
        load_compiled: bool = False,
        cache: bool = False,
        run_id: Optional[str] = None,
        experiment_name: str = "Evaluation",
        log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO",
    ):
        self.engine_type: Literal['baml', 'dspy'] = engine_type
        self.model_name = model_name
        self.provider_name = provider_name
        self.num_samples = num_samples
        self.load_compiled = load_compiled
        self.cache = cache
        self.run_id = run_id
        self.experiment_name = experiment_name

        # Setup logger
        self.logger = get_logger(name="EvaluationRunner", log_level=log_level)

        # Prepare dataset
        self.dataset = DEVSET[:num_samples]
        self.logger.info(f"Using {len(self.dataset)} samples for evaluation")

        # Setup MLflow
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment(self.experiment_name)

        # Initialize BAML AnswerVerifier
        self.answer_verifier = BamlAnswerVerifier()

        # Initialize metrics tracking (unified for both engines)
        self.evaluation_metrics = {
            "total_questions": 0,
            "successful_answers": 0,
            "failed_answers": 0,
            "total_execution_time": 0.0,
            "classifications": [],
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "engine_specific_metrics": {},
            "error_types": {},
        }

    def _create_engine_config(self) -> IfcAnswerEngineConfig:
        """Create engine configuration with CLI overrides."""
        # Start with base config
        config = AGENT_CONFIGS.ifc_answer_engine.model_copy(deep=True)
        # Apply LLM overrides
        if self.model_name:
            config.llm.model_name = self.model_name
        if self.provider_name:
            config.llm.provider_name = self.provider_name
        config.engine_type = self.engine_type

        self.logger.info(f"Engine config: type={config.engine_type}, model={config.llm.model_name}, provider={config.llm.provider_name}")

        return config

    def _create_engine(self, config: IfcAnswerEngineConfig):
        """Create engine using factory function."""
        self.logger.info(f"Creating engine: {config.engine_type}")
        engine = create_engine(config=config)
        return engine

    def _log_parameters(self, config: IfcAnswerEngineConfig):
        """Log experiment parameters to MLflow."""
        params = {
            "engine_type": config.engine_type,
            "model_name": config.llm.model_name,
            "provider_name": config.llm.provider_name,
            "num_samples": len(self.dataset),
            "load_compiled": self.load_compiled,
            "cache": self.cache,
            "max_tokens": config.llm.max_tokens,
        }

        # Log cost information if available
        if config.llm.cost_input_token is not None:
            params["cost_input_token_per_m"] = config.llm.cost_input_token
        if config.llm.cost_output_token is not None:
            params["cost_output_token_per_m"] = config.llm.cost_output_token

        # Log engine-specific parameters
        if config.engine_type == "dspy":
            params["dspy_cache_enabled"] = self.cache
            params["dspy_load_compiled"] = self.load_compiled
        elif config.engine_type == "baml":
            params["max_iters"] = config.max_iters
            params["add_code_prefix"] = config.add_code_prefix

        mlflow.log_params(params)
        self.logger.info(f"Logged parameters: {params}")

    def _process_single_question(
        self,
        engine,
        example: Dataset,
        example_index: int,
        config: IfcAnswerEngineConfig
    ) -> Dict[str, Any]:
        """Process a single question with individual MLflow trace."""
        question = example.question
        ground_truth = getattr(example, 'answer', '') or getattr(example, 'ground_truth', '')
        category = getattr(example, 'category', None)
        question_id = getattr(example, 'id', f'q_{example_index + 1}')

        # Skip question if category is not provided
        if category is None:
            error_msg = f"ERROR: Question {question_id} missing required 'category' field. SKIPPING this question. Please update the dataset."
            self.logger.error(error_msg)
            print(f"\n{error_msg}")

            # Log error to MLflow
            with mlflow.start_span(name="Missing_Category_Error", span_type="ERROR") as error_span:
                error_span.set_inputs({
                    "question": question,
                    "question_id": question_id
                })
                error_span.set_outputs({
                    "error": "Missing required 'category' field",
                    "action": "Question skipped"
                })
                error_span.set_status("ERROR")

            # Return error result
            return {
                "question": question,
                "ground_truth": ground_truth,
                "category": None,
                "status": "error",
                "error_message": "Missing required 'category' field",
                "execution_time": 0.0,
                "classification": None,
                "justification": None,
                "confidence": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "mlflow_run_id": "skipped_no_category",
            }

        self.logger.info(f"Processing question {example_index + 1}/{len(self.dataset)}: {question[:100]}...")

        # Create individual MLflow run (nested run) for this question
        run_name = f"{config.engine_type.upper()}_Q{example_index + 1}_{question_id}_{config.llm.model_name}"

        assert example.ifc is not None, "The ifc field of the Example cannot be None."
        with mlflow.start_run(run_name=run_name, nested=True) as question_run:
            # Log question parameters
            mlflow.log_params({
                "question": question,
                "ground_truth": ground_truth,
                "category": category,
                "question_id": question_id,
                "engine_type": config.engine_type,
                "llm": config.llm.model_name,
                "provider_name": config.llm.provider_name,
                "project_name": example.ifc.project_name,
                "model_name": example.ifc.model_name,
            })

            # Create main span for this question processing
            with mlflow.start_span(name="Engine_Question_Processing", span_type="CHAIN") as question_span:
                question_span.set_inputs({
                    "question": question,
                    "ground_truth": ground_truth,
                    "category": category,
                    "question_index": example_index + 1,
                    "engine_type": config.engine_type
                })
                question_span.set_attributes({
                    "engine": config.engine_type,
                    "model": config.llm.model_name,
                    "provider": config.llm.provider_name
                })

                start_time = time.time()

                try:
                    # Extract IFC path from question data
                    ifc_path = example.ifc.model_path if example.ifc else None
                    if not ifc_path:
                        self.logger.warning(f"No IFC path found for question {example_index + 1}")

                    # Run the engine
                    result = engine.forward(question, ifc_path)
                    execution_time = time.time() - start_time

                    # Extract result information from ModuleOutput
                    status = result.status
                    answer = result.result.answer if result.result else ""
                    reasoning = getattr(result.result, 'reasoning', '') if result.result else ""

                    # Extract token usage
                    input_tokens = result.lm_metrics.input_tokens or 0
                    output_tokens = result.lm_metrics.output_tokens or 0

                    # Update metrics
                    self.evaluation_metrics["total_questions"] += 1
                    self.evaluation_metrics["total_execution_time"] += execution_time
                    self.evaluation_metrics["total_input_tokens"] += input_tokens
                    self.evaluation_metrics["total_output_tokens"] += output_tokens

                    if status == "success":
                        self.evaluation_metrics["successful_answers"] += 1
                    else:
                        self.evaluation_metrics["failed_answers"] += 1
                        error_type = self._extract_error_type(getattr(result, 'error_msg', ''))
                        self.evaluation_metrics["error_types"][error_type] = \
                            self.evaluation_metrics["error_types"].get(error_type, 0) + 1
                    # Log question-level metrics
                    mlflow.log_metrics({
                        "execution_time": execution_time,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "success": 1 if status == "success" else 0,
                    })

                    # Prepare question span outputs
                    question_outputs = {
                        "status": status,
                        "execution_time": execution_time,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    }

                    if status == "success":
                        question_outputs.update({
                            "answer": answer,
                            "reasoning": reasoning,
                            "reasoning_length": len(reasoning)
                        })
                    else:
                        question_outputs.update({
                            "error_msg": getattr(result, 'error_msg', ''),
                            "error_type": self._extract_error_type(getattr(result, 'error_msg', ''))
                        })

                    question_span.set_outputs(question_outputs)
                    question_span.set_status("OK")
                    question_span.set_attributes({
                        "question.status": status,
                        "question.category": category,
                    })

                    # Now run AnswerVerifier if we have a successful answer
                    classification = None
                    justification = None
                    confidence = None
                    if status == "success" and answer and ground_truth:
                        verifier_result = self._run_answer_verifier(
                            question, category, ground_truth, answer
                        )

                        classification = verifier_result.classification
                        justification = verifier_result.justification
                        confidence = verifier_result.confidence

                        # Update classification metrics
                        self.evaluation_metrics["classifications"].append(classification)

                        question_outputs.update({
                            "classification": classification,
                            "justification": justification,
                            "confidence": confidence
                        })

                    self.logger.info(f"Question {example_index + 1} completed: {status} in {execution_time:.2f}s, classification: {classification}")

                    # Log LLM outputs as parameters
                    mlflow.log_params({
                        "answer": answer,
                        "classification": classification or "not_evaluated",
                        "justification": justification or "not_evaluated",
                        "confidence": confidence or "not_evaluated",
                    })

                    return {
                        "question": question,
                        "ground_truth": ground_truth,
                        "category": category,
                        "status": status,
                        "answer": answer,
                        "reasoning": reasoning,
                        "execution_time": execution_time,
                        "classification": classification,
                        "justification": justification,
                        "confidence": confidence,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "error_message": getattr(result, 'error_msg', ''),
                        "mlflow_run_id": question_run.info.run_id,
                    }

                except Exception as e:
                    execution_time = time.time() - start_time
                    self.logger.error(f"Question {example_index + 1} failed with exception: {str(e)}")

                    # Update error metrics
                    self.evaluation_metrics["total_questions"] += 1
                    self.evaluation_metrics["failed_answers"] += 1
                    error_type = type(e).__name__
                    self.evaluation_metrics["error_types"][error_type] = \
                        self.evaluation_metrics["error_types"].get(error_type, 0) + 1

                    # Log failure
                    mlflow.log_metrics({
                        "execution_time": execution_time,
                        "success": 0.0,
                        })

                    mlflow.log_params({
                        "error_type": error_type,
                        "error_message": str(e),
                    })

                    question_span.set_outputs({
                        "status": "error",
                        "execution_time": execution_time,
                        "error_message": str(e),
                        "error_type": error_type
                    })
                    question_span.set_attributes({
                        "question.status": "error",
                        "question.success": False
                    })

                    return {
                        "question": question,
                        "ground_truth": ground_truth,
                        "category": category,
                        "status": "error",
                        "error_message": str(e),
                        "execution_time": execution_time,
                        "classification": None,
                        "justification": None,
                        "confidence": None,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "engine_metrics": {},
                        "mlflow_run_id": question_run.info.run_id,
                    }

    def _run_answer_verifier(self, question: str, category: str, ground_truth: str, system_response: str):
        """Run the BAML AnswerVerifier to get AnswerEvaluationResult."""
        try:
            with mlflow.start_span(name="BamlAnswerVerifier", span_type="CHAIN") as verifier_span:
                verifier_span.set_inputs({
                    "question": question,
                    "category": category,
                    "ground_truth": ground_truth,
                    "system_response": system_response
                })

                # Run BAML AnswerVerifier
                verifier_result = self.answer_verifier.forward(
                    question=question,
                    category=category,
                    ground_truth=ground_truth,
                    system_response=system_response
                )

                verifier_span.set_outputs({
                    "classification": verifier_result.classification,
                    "justification": verifier_result.justification,
                    "confidence": verifier_result.confidence,
                    "status": "success"
                })
                verifier_span.set_status("OK")

                self.logger.debug(f"BamlAnswerVerifier: classification={verifier_result.classification}, confidence={verifier_result.confidence}")
                return verifier_result

        except Exception as e:
            self.logger.error(f"BamlAnswerVerifier exception: {str(e)}")
            raise

    def _extract_error_type(self, error_message: str) -> str:
        """Extract error type from error message."""
        error_message = error_message.lower()

        if "maximum iterations" in error_message:
            return "max_iterations_reached"
        elif "baml" in error_message:
            return "baml_error"
        elif "code execution" in error_message or "execution" in error_message:
            return "code_execution_error"
        elif "ifc" in error_message:
            return "ifc_error"
        elif "file" in error_message:
            return "file_error"
        else:
            return "unknown_error"

    def _calculate_and_log_metrics(self, question_results: List[Dict], config: IfcAnswerEngineConfig) -> Dict:
        """Calculate comprehensive evaluation metrics and log to MLflow."""
        total_questions = len(question_results)
        successful_results = [r for r in question_results if r["status"] == "success"]

        # Basic success metrics
        success_rate = len(successful_results) / total_questions if total_questions > 0 else 0.0

        # Classification metrics
        classifications = [r["classification"] for r in successful_results if r["classification"] is not None]
        correct_count = sum(1 for c in classifications if c == "correct")
        wrong_count = sum(1 for c in classifications if c == "wrong")
        abstained_count = sum(1 for c in classifications if c == "abstained")

        # Calculate accuracy and abstainance rate
        accuracy = correct_count / (correct_count + wrong_count) if (correct_count + wrong_count) > 0 else 0.0
        abstainance_rate = abstained_count / len(classifications) if classifications else 0.0

        # Performance metrics
        total_execution_time = sum(r["execution_time"] for r in question_results)
        avg_execution_time = total_execution_time / total_questions if total_questions > 0 else 0.0

        # Token metrics
        total_input_tokens = sum(r["input_tokens"] for r in question_results)
        total_output_tokens = sum(r["output_tokens"] for r in question_results)
        total_tokens = total_input_tokens + total_output_tokens

        # Log comprehensive metrics to MLflow
        metrics = {
            # Success metrics
            "success_rate": success_rate,
            "successful_answers": len(successful_results),
            "failed_answers": total_questions - len(successful_results),
            "total_questions": total_questions,

            # Classification metrics
            "accuracy": accuracy,
            "abstainance_rate": abstainance_rate,
            "correct_count": correct_count,
            "wrong_count": wrong_count,
            "abstained_count": abstained_count,
            "total_evaluated": len(classifications),

            # Performance metrics
            "total_execution_time": total_execution_time,
            "avg_execution_time": avg_execution_time,

            # Token metrics
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "avg_tokens_per_question": total_tokens / total_questions if total_questions > 0 else 0.0,

            # Tokens per second
            "tokens_per_second": total_tokens / total_execution_time if total_execution_time > 0 else 0.0,
        }

        # Add cost calculations if available
        if config.llm.cost_input_token is not None and config.llm.cost_output_token is not None:
            input_cost = (total_input_tokens / 1_000_000) * config.llm.cost_input_token
            output_cost = (total_output_tokens / 1_000_000) * config.llm.cost_output_token
            total_cost = input_cost + output_cost

            metrics.update({
                "cost": total_cost
            })

        mlflow.log_metrics(metrics)

        # Log error breakdown
        for error_type, count in self.evaluation_metrics["error_types"].items():
            mlflow.log_metric(f"error_{error_type}", count)

        # Prepare results summary
        results_summary = {
            "engine_type": config.engine_type,
            "model_name": config.llm.model_name,
            "provider_name": config.llm.provider_name,
            "num_samples": total_questions,

            # Success metrics
            "success_rate": success_rate,
            "successful_answers": len(successful_results),
            "failed_answers": total_questions - len(successful_results),

            # Classification metrics
            "accuracy": accuracy,
            "abstainance_rate": abstainance_rate,
            "correct_count": correct_count,
            "wrong_count": wrong_count,
            "abstained_count": abstained_count,
            "total_evaluated": len(classifications),

            # Performance metrics
            "total_execution_time": total_execution_time,
            "avg_execution_time": avg_execution_time,

            # Token metrics
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "avg_tokens_per_question": total_tokens / total_questions if total_questions > 0 else 0.0,

            # Tokens per second
            "tokens_per_second": total_tokens / total_execution_time if total_execution_time > 0 else 0.0,

            # Cost
            "cost": metrics.get("cost", 0)
        }

        return results_summary

    def _print_results(self, results_summary: Dict):
        """Print formatted evaluation results."""
        print("\n" + "=" * 80)
        print("EVALUATION RESULTS")
        print("=" * 80)

        print(f"Engine: {results_summary['engine_type'].upper()}")
        print(f"Model: {results_summary['model_name']} ({results_summary['provider_name']})")
        print(f"Samples: {results_summary['num_samples']}")
        print()

        print("Classification Metrics:")
        print(f"  Accuracy: {results_summary['accuracy']:.3f}")
        print(f"  Abstainance Rate: {results_summary['abstainance_rate']:.3f}")
        print(f"  Correct Answers: {results_summary['correct_count']}")
        print(f"  Wrong Answers: {results_summary['wrong_count']}")
        print(f"  Abstained Answers: {results_summary['abstained_count']}")
        print(f"  Total Evaluated: {results_summary['total_evaluated']}")
        print()

        print("Token Usage:")
        print(f"  Input Tokens: {results_summary['total_input_tokens']:,}")
        print(f"  Output Tokens: {results_summary['total_output_tokens']:,}")
        print(f"  Total Tokens: {results_summary['total_tokens']:,}")
        print(f"  Avg Tokens/Question: {results_summary['avg_tokens_per_question']:.1f}")
        print()

        print("Performance:")
        print(f"  Total Execution Time: {results_summary['total_execution_time']:.1f}s")
        print(f"  Avg Execution Time/Question: {results_summary['avg_execution_time']:.1f}s")
        print(f"  Tokens/Second: {results_summary['tokens_per_second']:.1f}")
        print()

        if "total_cost_usd" in results_summary:
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

    def run_evaluation(self) -> Dict:
        """Run the evaluation experiment."""
        self.logger.info("Starting evaluation experiment")

        # Create engine configuration
        config = self._create_engine_config()

        self.logger.info(f"Configuration: {config.engine_type} engine, {config.llm.model_name} from {config.llm.provider_name}")
        self.logger.info(f"Samples: {len(self.dataset)}, Load Compiled: {self.load_compiled}, Cache: {self.cache}")

        # Create engine
        engine = self._create_engine(config)

        # Setup MLflow run context
        is_new_run = self.run_id is None

        try:
            if self.run_id:
                # Continue existing run
                self.logger.info(f"Continuing existing MLflow run: {self.run_id}")
                run_context = mlflow.start_run(run_id=self.run_id)
            else:
                # Start new run
                run_name = f"{config.engine_type}_{config.llm.model_name}_{config.llm.provider_name}_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
                self.logger.info(f"Starting new MLflow run: {run_name}")
                run_context = mlflow.start_run(run_name=run_name)

            with run_context as run:
                self.run_id = run.info.run_id
                self.logger.info(f"MLflow run started with ID: {self.run_id}")

                # Log parameters only for new runs
                if is_new_run:
                    self._log_parameters(config)
                else:
                    self.logger.info("Continuing existing run - skipping parameter logging")

                # Configure DSPy settings if applicable
                if config.engine_type == "dspy":
                    dspy.configure_cache(enable_disk_cache=self.cache)
                    self.logger.info(f"DSPy cache enabled: {self.cache}")

                    # Enable DSPy autologging
                    try:
                        mlflow.dspy.autolog()  # type: ignore
                        self.logger.info("DSPy autologging enabled")
                    except Exception as e:
                        self.logger.warning(f"DSPy autologging not available: {e}")

                # Time the evaluation
                start_time = time.time()

                # Process each question (each creates its own MLflow run)
                question_results = []
                with tqdm(total=len(self.dataset), desc=f"Evaluating {config.engine_type.upper()} {config.llm.model_name}") as pbar:
                    for i, question_data in enumerate(self.dataset):
                        result = self._process_single_question(engine, question_data, i, config)
                        question_results.append(result)
                        pbar.update(1)

                end_time = time.time()
                total_evaluation_time = end_time - start_time

                # Calculate and log metrics for the main evaluation run
                results_summary = self._calculate_and_log_metrics(question_results, config)
                results_summary["total_evaluation_time"] = total_evaluation_time

                # Log additional info to main run
                mlflow.set_tag("evaluation_status", "completed")
                mlflow.set_tag("engine_type", config.engine_type)
                mlflow.set_tag("total_evaluation_time", total_evaluation_time)
                mlflow.set_tag("individual_question_traces", "true")

                self.logger.info("Evaluation completed successfully")
                self.logger.info(f"Success rate: {results_summary['success_rate']:.3f}")
                self.logger.info(f"Accuracy: {results_summary['accuracy']:.3f}")
                self.logger.info(f"Total evaluation time: {total_evaluation_time:.1f}s")
                self.logger.info(f"Individual question traces created: {len(question_results)}")

                # Print results
                self._print_results(results_summary)

                return results_summary

        except Exception as e:
            self.logger.error(f"Evaluation failed: {e}")
            if self.run_id:
                try:
                    mlflow.set_tag("evaluation_status", "failed")
                    mlflow.set_tag("error", str(e))
                except Exception as mlflow_error:
                    self.logger.warning(f"Failed to set MLflow error tags: {mlflow_error}")
            raise


def main():
    """Main function to run the evaluation."""
    parser = argparse.ArgumentParser(
        description="Run evaluation experiments on IFC Answer Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic evaluation with auto engine detection (from config)
  uv run scripts/run_evaluation.py --model glm-4.6 --provider zai --num-samples 10

  # Force DSPy engine evaluation
  uv run scripts/run_evaluation.py --engine-type dspy --model glm-4.6 --provider zai --load-compiled --cache

  # Force BAML engine evaluation
  uv run scripts/run_evaluation.py --engine-type baml --model glm-4.6 --provider zai

  # Continue existing run
  uv run scripts/run_evaluation.py --run-id 1234567890abcdef --model glm-4.6 --provider zai
        """
    )

    # Engine selection
    parser.add_argument(
        "--engine-type",
        choices=["dspy", "baml"],
        default="baml",
        help="Engine type (default: baml)"
    )

    # Core parameters
    parser.add_argument(
        "--model",
        help="Override model name"
    )

    parser.add_argument(
        "--provider",
        help="Override provider name"
    )

    parser.add_argument(
        "--num-samples",
        type=int,
        default=10,
        help="Number of samples to evaluate (default: 10)"
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

    # DSPy-specific flags
    parser.add_argument(
        "--load-compiled",
        action="store_true",
        help="Load compiled model (DSPy only)"
    )

    parser.add_argument(
        "--cache",
        action="store_true",
        help="Enable DSPy cache (DSPy only)"
    )

    # Existing functionality
    parser.add_argument(
        "--run-id",
        help="Optional existing MLflow run ID to continue"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.num_samples <= 0:
        print("Error: --num-samples must be positive")
        return 1

    if args.num_samples > len(DEVSET):
        print(f"WARNING: --num-samples ({args.num_samples}) exceeds available dataset size ({len(DEVSET)})")
        print("Evaluation will be done for the whole dataset.")

    # Validate DSPy-specific flags
    if args.engine_type == "baml" and args.load_compiled:
        print("Warning: --load-compiled only applies to DSPy engine, ignoring for BAML")
        args.load_compiled = False

    if args.engine_type == "baml" and args.cache:
        print("Warning: --cache only applies to DSPy engine, ignoring for BAML")
        args.cache = False

    # Create and run evaluation
    runner = EvaluationRunner(
        engine_type=args.engine_type,
        model_name=args.model,
        provider_name=args.provider,
        num_samples=args.num_samples,
        load_compiled=args.load_compiled,
        cache=args.cache,
        run_id=args.run_id,
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
