#!/usr/bin/env python3
"""
BAML-based Evaluation Script for IFC Answer Engine

This script provides a configurable way to run evaluation experiments using the BAML
implementation of the IFC QA system. It supports various LLM models, customizable
sample sizes, and comprehensive MLflow tracking with detailed tracing.

Usage:
    # Basic evaluation with GLM-4.6 model
    uv run scripts/run_baml_evaluation.py --model glm-4.6 --provider zai

    # Evaluation with custom parameters
    uv run scripts/run_baml_evaluation.py \
        --model qwen3-coder \
        --provider deepinfra \
        --num-samples 20 \
        --experiment-name "BAML_Custom_Evaluation" \
        --max-iterations 5

    # Continue existing MLflow run
    uv run scripts/run_baml_evaluation.py \
        --run-id 1234567890abcdef \
        --model glm-4.6 \
        --provider zai
"""

import argparse
import time
from datetime import datetime
from typing import Dict, Optional, Any, List

import mlflow
from tqdm import tqdm

from src.engine.components.bim_qas import BIMQASBaml
from src.engine.components.answer_verifier import AnswerVerifier
from src.engine.util import get_logger
from src.experiment.datasets import DEVSET


class BAMEvaluationRunner:
    """BAML-based evaluation runner for IFC Answer Engine."""

    def __init__(
        self,
        num_samples: int = 10,
        model_name: str = "glm-4.6",
        provider_name: str = "zai",
        run_id: Optional[str] = None,
        experiment_name: str = "BAML_Evaluation",
        log_level: str = "INFO",
        max_iterations: int = 5,
        ifc_model_path: str = "src/experiment/bim_models/duplex/arc.ifc",
        add_code_prefix: bool = True,
    ):
        self.num_samples = num_samples
        self.model_name = model_name
        self.provider_name = provider_name
        self.run_id = run_id
        self.experiment_name = experiment_name
        self.max_iterations = max_iterations
        self.ifc_model_path = ifc_model_path
        self.add_code_prefix = add_code_prefix

        # Setup logger
        self.logger = get_logger(name="BAMEvaluationRunner", log_level=log_level)

        # Prepare dataset
        self.dataset = DEVSET[:num_samples]
        self.logger.info(f"Using {len(self.dataset)} samples for evaluation")

        # Setup MLflow
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment(self.experiment_name)

        # Initialize AnswerVerifier
        self.answer_verifier = AnswerVerifier()

        # Initialize metrics tracking
        self.evaluation_metrics = {
            "total_questions": 0,
            "successful_answers": 0,
            "failed_answers": 0,
            "total_iterations": 0,
            "total_execution_time": 0.0,
            "total_baml_calls": 0,
            "total_code_executions": 0,
            "similarity_scores": [],
            "answer_lengths": [],
            "reasoning_lengths": [],
            "iteration_counts": [],
            "execution_times": [],
            "baml_calls_per_question": [],
            "code_executions_per_question": [],
            "error_types": {},
            "question_categories": {},
        }

    def _create_baml_agent(self) -> BIMQASBaml:
        """Create BAML agent instance with current configuration."""
        self.logger.info(f"Creating BAML agent with max_iterations={self.max_iterations}")
        return BIMQASBaml(
            max_iterations=self.max_iterations,
            log_level="INFO",
            path_ifc_model=self.ifc_model_path,
            add_code_prefix=self.add_code_prefix,
        )

    def _log_parameters(self):
        """Log experiment parameters to MLflow."""
        params = {
            "engine_type": "BAML",
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "num_samples": len(self.dataset),
            "max_iterations": self.max_iterations,
            "ifc_model_path": self.ifc_model_path,
            "add_code_prefix": self.add_code_prefix,
            "evaluation_framework": "BAML_CodeAct",
        }

        mlflow.log_params(params)
        self.logger.info(f"Logged parameters: {params}")

    def _process_single_question(
        self,
        agent: BIMQASBaml,
        question_data,  # QA_Pair object
        question_index: int
    ) -> Dict[str, Any]:
        """Process a single question with individual MLflow trace."""
        question = question_data.question
        ground_truth = question_data.ground_truth
        category = getattr(question_data, 'category', 'unknown')
        question_id = getattr(question_data, 'id', f'q_{question_index + 1}')

        self.logger.info(f"Processing question {question_index + 1}/{len(self.dataset)}: {question[:100]}...")

        # Create individual MLflow run (trace) for this question (nested run)
        run_name = f"BAML_Q{question_index + 1}_{question_id}_{self.model_name}"

        with mlflow.start_run(run_name=run_name, nested=True) as question_run:
            # Log question parameters
            mlflow.log_params({
                "question": question,
                "ground_truth": ground_truth,
                "category": category,
                "question_index": question_index + 1,
                "question_id": question_id,
                "model_name": self.model_name,
                "provider_name": self.provider_name,
                "engine_type": "BAML_CodeAct",
                "max_iterations": self.max_iterations,
                "ifc_model_path": self.ifc_model_path,
                "add_code_prefix": self.add_code_prefix,
            })

            # Create main span for this question processing
            with mlflow.start_span(name="BAML_Question_Processing", span_type="CHAIN") as question_span:
                question_span.set_inputs({
                    "question": question,
                    "ground_truth": ground_truth,
                    "category": category,
                    "question_index": question_index + 1,
                    "max_iterations": self.max_iterations
                })
                question_span.set_attributes({
                    "question_type": "evaluation",
                    "engine": "BAML_CodeAct",
                    "model": self.model_name,
                    "provider": self.provider_name
                })

                start_time = time.time()

                try:
                    # Run the BAML agent
                    result = agent.run(question)

                    execution_time = time.time() - start_time

                    # Extract result information
                    status = result.get("status", "unknown")
                    answer = result.get("answer", "")
                    reasoning = result.get("reasoning", "")
                    iterations = result.get("iterations", 0)
                    total_execution_time = result.get("total_execution_time", 0.0)
                    baml_calls_made = result.get("baml_calls_made", 0)
                    code_executions = result.get("code_executions", 0)
                    previous_results = result.get("previous_results", [])
                    error_message = result.get("error", "")

                    # Update metrics
                    self.evaluation_metrics["total_questions"] += 1
                    self.evaluation_metrics["total_iterations"] += iterations
                    self.evaluation_metrics["total_execution_time"] += execution_time
                    self.evaluation_metrics["total_baml_calls"] += baml_calls_made
                    self.evaluation_metrics["total_code_executions"] += code_executions

                    if status == "success":
                        self.evaluation_metrics["successful_answers"] += 1
                        self.evaluation_metrics["answer_lengths"].append(len(answer))
                        self.evaluation_metrics["reasoning_lengths"].append(len(reasoning))
                    else:
                        self.evaluation_metrics["failed_answers"] += 1
                        error_type = self._extract_error_type(error_message)
                        self.evaluation_metrics["error_types"][error_type] = self.evaluation_metrics["error_types"].get(error_type, 0) + 1

                    self.evaluation_metrics["iteration_counts"].append(iterations)
                    self.evaluation_metrics["execution_times"].append(execution_time)
                    self.evaluation_metrics["baml_calls_per_question"].append(baml_calls_made)
                    self.evaluation_metrics["code_executions_per_question"].append(code_executions)

                    # Track question categories
                    self.evaluation_metrics["question_categories"][category] = \
                        self.evaluation_metrics["question_categories"].get(category, 0) + 1

                    # Log question-level metrics
                    mlflow.log_metrics({
                        "execution_time_seconds": execution_time,
                        "iterations_used": iterations,
                        "baml_calls_made": baml_calls_made,
                        "code_executions": code_executions,
                        "answer_length": len(answer),
                        "has_reasoning": 1 if reasoning else 0,
                        "previous_results_count": len(previous_results),
                        "success": 1 if status == "success" else 0,
                    })

                    # Prepare question span outputs
                    question_outputs = {
                        "status": status,
                        "execution_time_seconds": execution_time,
                        "iterations_used": iterations,
                        "baml_calls_made": baml_calls_made,
                        "code_executions": code_executions,
                        "answer_length": len(answer),
                        "has_reasoning": bool(reasoning),
                        "previous_results_count": len(previous_results)
                    }

                    if status == "success":
                        question_outputs.update({
                            "answer_preview": answer[:200] + "..." if len(answer) > 200 else answer,
                            "reasoning_preview": reasoning[:200] + "..." if len(reasoning) > 200 else reasoning,
                            "reasoning_length": len(reasoning)
                        })
                    else:
                        question_outputs.update({
                            "error_message": error_message,
                            "error_type": self._extract_error_type(error_message)
                        })

                    question_span.set_outputs(question_outputs)
                    question_span.set_attributes({
                        "question.status": status,
                        "question.category": category,
                        "question.success": status == "success"
                    })

                    # Now run AnswerVerifier if we have a successful answer
                    similarity_score = 0.0
                    verifier_reasoning = ""
                    if status == "success" and answer and ground_truth:
                        similarity_score, verifier_reasoning = self._run_answer_verifier(
                            question, answer, ground_truth
                        )

                        # Update similarity metrics
                        self.evaluation_metrics["similarity_scores"].append(similarity_score)

                        # Log similarity metrics
                        mlflow.log_metrics({
                            "similarity_score": similarity_score,
                            "has_verifier_reasoning": 1 if verifier_reasoning else 0,
                            "verifier_reasoning_length": len(verifier_reasoning),
                        })

                        question_outputs.update({
                            "similarity_score": similarity_score,
                            "verifier_reasoning_preview": verifier_reasoning[:200] + "..." if len(verifier_reasoning) > 200 else verifier_reasoning,
                            "has_verifier_reasoning": bool(verifier_reasoning),
                        })

                    self.logger.info(f"Question {question_index + 1} completed: {status} in {execution_time:.2f}s, {iterations} iterations, similarity: {similarity_score:.3f}")

                    return {
                        "question": question,
                        "ground_truth": ground_truth,
                        "category": category,
                        "status": status,
                        "answer": answer,
                        "reasoning": reasoning,
                        "iterations": iterations,
                        "execution_time": execution_time,
                        "similarity_score": similarity_score,
                        "verifier_reasoning": verifier_reasoning,
                        "baml_calls": baml_calls_made,
                        "code_executions": code_executions,
                        "error_message": error_message,
                        "previous_results": previous_results,
                        "mlflow_run_id": question_run.info.run_id,
                    }

                except Exception as e:
                    execution_time = time.time() - start_time
                    self.logger.error(f"Question {question_index + 1} failed with exception: {str(e)}")

                    # Update error metrics
                    self.evaluation_metrics["total_questions"] += 1
                    self.evaluation_metrics["failed_answers"] += 1
                    error_type = type(e).__name__
                    self.evaluation_metrics["error_types"][error_type] = self.evaluation_metrics["error_types"].get(error_type, 0) + 1

                    # Log failure
                    mlflow.log_metrics({
                        "execution_time_seconds": execution_time,
                        "success": 0,
                        "error_type": error_type,
                        "error_message": str(e),
                    })

                    question_span.set_outputs({
                        "status": "error",
                        "execution_time_seconds": execution_time,
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
                        "similarity_score": 0.0,
                        "verifier_reasoning": "",
                        "iterations": 0,
                        "baml_calls": 0,
                        "code_executions": 0,
                        "mlflow_run_id": question_run.info.run_id,
                    }

    def _run_answer_verifier(self, question: str, answer: str, ground_truth: str) -> tuple[float, str]:
        """Run the AnswerVerifier to get similarity score and reasoning.

        Args:
            question: The question being answered
            answer: The generated answer
            ground_truth: The ground truth answer

        Returns:
            Tuple of (similarity_score, reasoning)
        """
        try:
            with mlflow.start_span(name="AnswerVerifier", span_type="CHAIN") as verifier_span:
                verifier_span.set_inputs({
                    "question": question,
                    "answer": answer,
                    "ground_truth": ground_truth
                })
                verifier_span.set_attributes({
                    "verifier_type": "DSPy_AnswerVerifier",
                    "llm_model": self.answer_verifier.lm.model if hasattr(self.answer_verifier, 'lm') else "unknown"
                })

                # Run AnswerVerifier
                verifier_output = self.answer_verifier(
                    question=question,
                    first_answer=answer,
                    second_answer=ground_truth
                )

                if verifier_output.status == "success" and verifier_output.result:
                    similarity_score = verifier_output.result.similarity_score or 0.0
                    reasoning = verifier_output.result.reasoning or ""

                    verifier_span.set_outputs({
                        "similarity_score": similarity_score,
                        "reasoning": reasoning,
                        "status": "success"
                    })
                    verifier_span.set_attributes({
                        "verifier.status": "success",
                        "similarity_score_valid": True
                    })

                    self.logger.debug(f"AnswerVerifier: similarity={similarity_score:.3f}, reasoning: {reasoning[:100]}...")
                    return similarity_score, reasoning
                else:
                    error_msg = verifier_output.error_msg or "Unknown AnswerVerifier error"
                    verifier_span.set_outputs({
                        "error_message": error_msg,
                        "status": "error"
                    })
                    verifier_span.set_attributes({
                        "verifier.status": "error",
                        "similarity_score_valid": False
                    })

                    self.logger.warning(f"AnswerVerifier failed: {error_msg}")
                    return 0.0, ""

        except Exception as e:
            self.logger.error(f"AnswerVerifier exception: {str(e)}")
            return 0.0, ""

    def _calculate_similarity(self, answer: str, ground_truth: str) -> float:
        """Calculate similarity score between answer and ground truth.

        This is a simple fallback implementation. The primary similarity scoring
        is done by the AnswerVerifier.
        """
        if not answer or not ground_truth:
            return 0.0

        # Simple word-based similarity
        answer_words = set(answer.lower().split())
        truth_words = set(ground_truth.lower().split())

        if not answer_words or not truth_words:
            return 0.0

        intersection = answer_words.intersection(truth_words)
        union = answer_words.union(truth_words)

        return len(intersection) / len(union) if union else 0.0

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

    def _calculate_and_log_metrics(self, question_results: List[Dict]) -> Dict:
        """Calculate comprehensive evaluation metrics and log to MLflow."""
        total_questions = len(question_results)
        successful_results = [r for r in question_results if r["status"] == "success"]

        # Basic success metrics
        success_rate = len(successful_results) / total_questions if total_questions > 0 else 0.0

        # Similarity metrics
        similarity_scores = [r["similarity_score"] for r in successful_results]
        mean_similarity = sum(similarity_scores) / len(similarity_scores) if similarity_scores else 0.0
        high_similarity_count = sum(1 for score in similarity_scores if score >= 0.85)
        high_similarity_rate = (high_similarity_count / len(similarity_scores)) * 100 if similarity_scores else 0.0

        # Performance metrics
        total_execution_time = sum(r["execution_time"] for r in question_results)
        avg_execution_time = total_execution_time / total_questions if total_questions > 0 else 0.0

        total_iterations = sum(r["iterations"] for r in question_results)
        avg_iterations = total_iterations / total_questions if total_questions > 0 else 0.0

        total_baml_calls = sum(r["baml_calls"] for r in question_results)
        avg_baml_calls = total_baml_calls / total_questions if total_questions > 0 else 0.0

        total_code_executions = sum(r["code_executions"] for r in question_results)
        avg_code_executions = total_code_executions / total_questions if total_questions > 0 else 0.0

        # Answer quality metrics
        answer_lengths = [len(r["answer"]) for r in successful_results]
        avg_answer_length = sum(answer_lengths) / len(answer_lengths) if answer_lengths else 0.0

        reasoning_lengths = [len(r["reasoning"]) for r in successful_results if r.get("reasoning")]
        avg_reasoning_length = sum(reasoning_lengths) / len(reasoning_lengths) if reasoning_lengths else 0.0

        # AnswerVerifier metrics
        verifier_reasonings = [r.get("verifier_reasoning", "") for r in successful_results if r.get("verifier_reasoning")]
        questions_with_verifier = len([r for r in successful_results if r.get("verifier_reasoning")])
        avg_verifier_reasoning_length = sum(len(reasoning) for reasoning in verifier_reasonings) / len(verifier_reasonings) if verifier_reasonings else 0.0

        # Log comprehensive metrics to MLflow
        metrics = {
            # Success metrics
            "success_rate": success_rate,
            "successful_answers": len(successful_results),
            "failed_answers": total_questions - len(successful_results),
            "total_questions": total_questions,

            # Similarity metrics
            "mean_similarity_score": mean_similarity,
            "high_similarity_count": high_similarity_count,
            "high_similarity_rate_percent": high_similarity_rate,
            "answers_above_0_85_similarity": high_similarity_count,

            # Performance metrics
            "total_execution_time_seconds": total_execution_time,
            "avg_execution_time_seconds": avg_execution_time,
            "total_iterations": total_iterations,
            "avg_iterations_per_question": avg_iterations,

            # BAML-specific metrics
            "total_baml_calls": total_baml_calls,
            "avg_baml_calls_per_question": avg_baml_calls,
            "total_code_executions": total_code_executions,
            "avg_code_executions_per_question": avg_code_executions,

            # Answer quality metrics
            "avg_answer_length": avg_answer_length,
            "avg_reasoning_length": avg_reasoning_length,
            "questions_with_reasoning": len(reasoning_lengths),

            # AnswerVerifier metrics
            "questions_with_verifier": questions_with_verifier,
            "avg_verifier_reasoning_length": avg_verifier_reasoning_length,
        }

        mlflow.log_metrics(metrics)

        # Log error breakdown
        for error_type, count in self.evaluation_metrics["error_types"].items():
            mlflow.log_metric(f"error_{error_type}", count)

        # Log category breakdown
        for category, count in self.evaluation_metrics["question_categories"].items():
            mlflow.log_metric(f"category_{category}", count)

        # Prepare results summary
        results_summary = {
            "engine_type": "BAML",
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "num_samples": total_questions,
            "max_iterations": self.max_iterations,

            # Success metrics
            "success_rate": success_rate,
            "successful_answers": len(successful_results),
            "failed_answers": total_questions - len(successful_results),

            # Similarity metrics
            "mean_similarity_score": mean_similarity,
            "high_similarity_count": high_similarity_count,
            "high_similarity_rate_percent": high_similarity_rate,

            # Performance metrics
            "total_execution_time_seconds": total_execution_time,
            "avg_execution_time_seconds": avg_execution_time,
            "total_iterations": total_iterations,
            "avg_iterations_per_question": avg_iterations,

            # BAML-specific metrics
            "total_baml_calls": total_baml_calls,
            "avg_baml_calls_per_question": avg_baml_calls,
            "total_code_executions": total_code_executions,
            "avg_code_executions_per_question": avg_code_executions,

            # Answer quality metrics
            "avg_answer_length": avg_answer_length,
            "avg_reasoning_length": avg_reasoning_length,
            "questions_with_reasoning": len(reasoning_lengths),

            # AnswerVerifier metrics
            "questions_with_verifier": questions_with_verifier,
            "avg_verifier_reasoning_length": avg_verifier_reasoning_length,

            # Configuration
            "ifc_model_path": self.ifc_model_path,
            "add_code_prefix": self.add_code_prefix,
            "experiment_name": self.experiment_name,
        }

        return results_summary

    def _print_results(self, results_summary: Dict):
        """Print formatted evaluation results."""
        print("\n" + "=" * 80)
        print("BAML EVALUATION RESULTS")
        print("=" * 80)

        print(f"Engine: BAML CodeAct")
        print(f"Model: {results_summary['model_name']} ({results_summary['provider_name']})")
        print(f"Samples: {results_summary['num_samples']}")
        print(f"Max Iterations: {results_summary['max_iterations']}")
        print(f"IFC Model: {results_summary['ifc_model_path']}")
        print()

        print("Performance Metrics:")
        print(f"  Success Rate: {results_summary['success_rate']:.3f}")
        print(f"  Successful Answers: {results_summary['successful_answers']}")
        print(f"  Failed Answers: {results_summary['failed_answers']}")
        print(f"  Mean Similarity Score: {results_summary['mean_similarity_score']:.3f}")
        print(f"  High Similarity (≥0.85): {results_summary['high_similarity_count']} ({results_summary['high_similarity_rate_percent']:.1f}%)")
        print()

        print("BAML-Specific Metrics:")
        print(f"  Total BAML Calls: {results_summary['total_baml_calls']}")
        print(f"  Avg BAML Calls/Question: {results_summary['avg_baml_calls_per_question']:.1f}")
        print(f"  Total Code Executions: {results_summary['total_code_executions']}")
        print(f"  Avg Code Executions/Question: {results_summary['avg_code_executions_per_question']:.1f}")
        print(f"  Total Iterations: {results_summary['total_iterations']}")
        print(f"  Avg Iterations/Question: {results_summary['avg_iterations_per_question']:.1f}")
        print()

        print("Performance:")
        print(f"  Total Execution Time: {results_summary['total_execution_time_seconds']:.1f}s")
        print(f"  Avg Execution Time/Question: {results_summary['avg_execution_time_seconds']:.1f}s")
        print()

        print("Answer Quality:")
        print(f"  Avg Answer Length: {results_summary['avg_answer_length']:.0f} characters")
        print(f"  Questions with Reasoning: {results_summary['questions_with_reasoning']}")
        if results_summary['questions_with_reasoning'] > 0:
            print(f"  Avg Reasoning Length: {results_summary['avg_reasoning_length']:.0f} characters")
        print()

        print("AnswerVerifier Results:")
        print(f"  Questions with Verifier Analysis: {results_summary['questions_with_verifier']}")
        if results_summary['questions_with_verifier'] > 0:
            print(f"  Avg Verifier Reasoning Length: {results_summary['avg_verifier_reasoning_length']:.0f} characters")
        print()

        if self.evaluation_metrics["error_types"]:
            print("Error Breakdown:")
            for error_type, count in self.evaluation_metrics["error_types"].items():
                print(f"  {error_type}: {count}")
            print()

        print("MLflow Information:")
        if self.run_id:
            print(f"  Run ID: {self.run_id}")
        print(f"  Experiment: {self.experiment_name}")
        print(f"  View details: http://127.0.0.1:5000")
        print("=" * 80)

    def run_evaluation(self) -> Dict:
        """Run the BAML evaluation experiment."""
        self.logger.info("Starting BAML evaluation experiment")
        self.logger.info(f"Configuration: {self.model_name} from {self.provider_name}")
        self.logger.info(f"Samples: {len(self.dataset)}, Max Iterations: {self.max_iterations}")

        # Create BAML agent
        agent = self._create_baml_agent()

        # Setup MLflow run context
        is_new_run = self.run_id is None

        if self.run_id:
            # Continue existing run
            self.logger.info(f"Continuing existing MLflow run: {self.run_id}")
            mlflow_context = mlflow.start_run(run_id=self.run_id)
        else:
            # Start new run
            run_name = f"BAML_{self.model_name}_{self.provider_name}_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
            self.logger.info(f"Starting new MLflow run: {run_name}")
            mlflow_context = mlflow.start_run(run_name=run_name)

        try:
            with mlflow_context as run:
                self.run_id = run.info.run_id
                self.logger.info(f"MLflow run started with ID: {self.run_id}")

                # Log parameters only for new runs
                if is_new_run:
                    self._log_parameters()
                else:
                    self.logger.info("Continuing existing run - skipping parameter logging")

                # Time the evaluation
                start_time = time.time()

                # Process each question (each creates its own MLflow run)
                question_results = []
                with tqdm(total=len(self.dataset), desc=f"Evaluating BAML {self.model_name}") as pbar:
                    for i, question_data in enumerate(self.dataset):
                        result = self._process_single_question(agent, question_data, i)
                        question_results.append(result)
                        pbar.update(1)

                end_time = time.time()
                total_evaluation_time = end_time - start_time

                # Calculate and log metrics for the main evaluation run
                results_summary = self._calculate_and_log_metrics(question_results)
                results_summary["total_evaluation_time_seconds"] = total_evaluation_time

                # Log additional info to main run
                mlflow.set_tag("evaluation_status", "completed")
                mlflow.set_tag("engine_type", "BAML")
                mlflow.set_tag("total_evaluation_time_seconds", total_evaluation_time)
                mlflow.set_tag("individual_question_traces", "true")

                self.logger.info("BAML evaluation completed successfully")
                self.logger.info(f"Success rate: {results_summary['success_rate']:.3f}")
                self.logger.info(f"Mean similarity: {results_summary['mean_similarity_score']:.3f}")
                self.logger.info(f"Total evaluation time: {total_evaluation_time:.1f}s")
                self.logger.info(f"Individual question traces created: {len(question_results)}")

                # Print results
                self._print_results(results_summary)

                return results_summary

        except Exception as e:
            self.logger.error(f"BAML evaluation failed: {e}")
            if self.run_id:
                mlflow.set_tag("evaluation_status", "failed")
                mlflow.set_tag("error", str(e))
            raise


def main():
    """Main function to run the BAML evaluation."""
    parser = argparse.ArgumentParser(
        description="Run BAML-based evaluation experiments on IFC Answer Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic evaluation with GLM-4.6
  uv run scripts/run_baml_evaluation.py --model glm-4.6 --provider zai

  # Custom evaluation with more iterations
  uv run scripts/run_baml_evaluation.py --model qwen3-coder --provider deepinfra --num-samples 20 --max-iterations 8

  # Continue existing run
  uv run scripts/run_baml_evaluation.py --run-id 1234567890abcdef --model glm-4.6 --provider zai
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
        "--run-id",
        help="Optional existing MLflow run ID to continue"
    )

    parser.add_argument(
        "--experiment-name",
        default="BAML_Evaluation",
        help="MLflow experiment name (default: BAML_Evaluation)"
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=5,
        help="Maximum iterations per question (default: 5)"
    )

    parser.add_argument(
        "--ifc-model-path",
        default="src/experiment/bim_models/duplex/arc.ifc",
        help="Path to IFC model file (default: src/experiment/bim_models/duplex/arc.ifc)"
    )

    parser.add_argument(
        "--no-code-prefix",
        action="store_false",
        dest="add_code_prefix",
        help="Disable code prefix injection"
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

    if args.max_iterations <= 0:
        print("Error: --max-iterations must be positive")
        return 1

    # Create and run evaluation
    runner = BAMEvaluationRunner(
        num_samples=args.num_samples,
        model_name=args.model,
        provider_name=args.provider,
        run_id=args.run_id,
        experiment_name=args.experiment_name,
        log_level=args.log_level,
        max_iterations=args.max_iterations,
        ifc_model_path=args.ifc_model_path,
        add_code_prefix=args.add_code_prefix,
    )

    try:
        runner.run_evaluation()
        print("\nBAML evaluation completed successfully!")
        return 0

    except Exception as e:
        print(f"\nError during BAML evaluation: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
