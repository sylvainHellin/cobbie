from datetime import datetime
from time import time
from typing import Any, Dict, List, Literal, Optional, Tuple

import mlflow
from dspy import LM
from pydantic import BaseModel
from tqdm import tqdm

from src.engine import IfcAnswerEngine
from src.engine.util import get_logger
from src.experiment.validation import DEVSET, TRAINSET, metric


class ValidationResult(BaseModel):
    accuracy: List[float] = []
    duration: List[float] = []
    tokens: List[Tuple[int, int]] = []
    question_ids: List[int] = []
    llm: str
    nb_eval: int = 0
    nb_failed_eval: int = 0

    # Error tracking
    errors: List[Dict[str, Any]] = []
    skipped_examples: List[int] = []

    def mean_accuracy(self) -> float:
        """Calculate the mean accuracy across all evaluated examples."""
        return sum(self.accuracy) / len(self.accuracy) if self.accuracy else 0.0

    def mean_duration(self) -> float:
        """Calculate the mean duration (in seconds) across all evaluated examples."""
        return sum(self.duration) / len(self.duration) if self.duration else 0.0

    def total_input_tokens(self) -> int:
        """Calculate the total number of input tokens used across all examples."""
        return sum(tokens[0] for tokens in self.tokens)

    def total_output_tokens(self) -> int:
        """Calculate the total number of output tokens generated across all examples."""
        return sum(tokens[1] for tokens in self.tokens)

    def total_tokens(self) -> int:
        """Calculate the total number of tokens (input + output) used across all examples."""
        return self.total_input_tokens() + self.total_output_tokens()

    def mean_input_tokens(self) -> float:
        """Calculate the mean number of input tokens per example."""
        return self.total_input_tokens() / len(self.tokens) if self.tokens else 0.0

    def mean_output_tokens(self) -> float:
        """Calculate the mean number of output tokens per example."""
        return self.total_output_tokens() / len(self.tokens) if self.tokens else 0.0

    def success_rate(self) -> float:
        """Calculate the success rate (percentage of examples with accuracy > 0)."""
        if not self.accuracy:
            return 0.0
        successful = len([acc for acc in self.accuracy if acc > 0])
        return successful / len(self.accuracy)

    def failure_rate(self) -> float:
        """Calculate the failure rate (percentage of examples with accuracy = 0)."""
        return 1.0 - self.success_rate()

    def add_error(
        self,
        question_id: int,
        error_msg: str,
    ):
        """Record an error that occurred during evaluation"""
        self.errors.append(
            {
                "question_id": question_id,
                "error_msg": error_msg,
                "timestamp": time(),
            }
        )
        self.nb_failed_eval += 1

    def increment_eval_count(self):
        """Increment the total evaluation count"""
        self.nb_eval += 1

    def evaluation_success_rate(self) -> float:
        """Calculate success rate using nb_eval and nb_failed_eval attributes"""
        if self.nb_eval == 0:
            return 0.0
        return (self.nb_eval - self.nb_failed_eval) / self.nb_eval

    def evaluation_failure_rate(self) -> float:
        """Calculate failure rate using nb_eval and nb_failed_eval attributes"""
        if self.nb_eval == 0:
            return 0.0
        return self.nb_failed_eval / self.nb_eval

    def get_error_summary(self) -> Dict[str, int]:
        """Get a summary of error types"""
        error_types = {}
        for error in self.errors:
            error_type = error["error_type"]
            error_types[error_type] = error_types.get(error_type, 0) + 1
        return error_types

    def get_statistics(self) -> dict:
        """Get a comprehensive dictionary of all evaluation statistics."""
        return {
            "mean_accuracy": self.mean_accuracy(),
            "mean_duration": self.mean_duration(),
            "total_input_tokens": self.total_input_tokens(),
            "total_output_tokens": self.total_output_tokens(),
            "total_tokens": self.total_tokens(),
            "mean_input_tokens": self.mean_input_tokens(),
            "mean_output_tokens": self.mean_output_tokens(),
            "success_rate": self.success_rate(),
            "failure_rate": self.failure_rate(),
            "total_examples": len(self.accuracy),
            "nb_eval": self.nb_eval,
            "nb_failed_eval": self.nb_failed_eval,
            "evaluation_success_rate": self.evaluation_success_rate(),
            "evaluation_failure_rate": self.evaluation_failure_rate(),
            "nb_errors": len(self.errors),
            "nb_skipped": len(self.skipped_examples),
            "llm": self.llm,
        }


def evaluate(
    llm: LM,
    dataset_type: Literal["dev", "train"] = "dev",
    max_examples: int = -1,
    experiment_name: Optional[str] = "Evaluation",
    start_run: bool = False,
) -> ValidationResult:
    """
    Compute the accuracy of the IfcAnswerEngine with comprehensive error handling and logging.

    Args:
        llm: The language model to use for evaluation
        dataset_type: Which dataset to use ("dev" or "train")
        max_examples: Maximum number of examples to evaluate (-1 for all)
        experiment_name: MLflow experiment name
        continue_on_error: If True, continue evaluation even when individual examples fail
        log_detailed_errors: If True, log full tracebacks for debugging

    Returns:
        ValidationResult: Comprehensive evaluation results with error tracking
    """
    logger = get_logger("Evaluation")
    logger.info(f"Starting evaluation with LLM: {llm.model}")
    logger.info(f"Dataset: {dataset_type}, Max examples: {max_examples}")

    # Setup mlflow
    if experiment_name is not None:
        mlflow.set_experiment(experiment_name=experiment_name)
        logger.info(f"MLflow experiment set: {experiment_name}")
    if start_run:
        mlflow.start_run(run_name=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))
        logger.info("New run started.")

    # Initialize dataset
    dataset = DEVSET if dataset_type == "dev" else TRAINSET
    dataset = dataset[:max_examples]

    # Initialize result
    result = ValidationResult(llm=llm.model)

    # Initialize engine
    try:
        engine = IfcAnswerEngine(llm=llm)
        logger.info("IfcAnswerEngine initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize IfcAnswerEngine: {e}")
        return result

    # Process examples
    for _, example in enumerate(tqdm(dataset, desc="Evaluating examples")):
        with mlflow.start_span(
            name=f"question_id_{example.question_id}",
            span_type="CHAIN",
        ):
            # Increment total evaluation count
            #
            result.increment_eval_count()

            # Execute engine
            start = time()
            engine_output = engine.forward(
                question=example.question,
                path_ifc_model=example.path_ifc_model,
            )
            end = time()
            duration = end - start

            # Record metrics
            result.duration.append(duration)
            result.tokens.append(
                (engine_output.input_tokens or 0, engine_output.output_tokens or 0)
            )
            result.question_ids.append(example.question_id)
            result.duration.append(duration)

            if engine_output.status == "error":
                result.add_error(
                    example.question_id,
                    engine_output.error_msg or "",
                )
                continue

            acc = metric(example=example, output=engine_output)
            result.accuracy.append(acc)

    # Log final summary
    successful_evaluations = result.nb_eval - result.nb_failed_eval
    logger.info(
        f"Evaluation completed: {successful_evaluations} successful, {result.nb_failed_eval} failed out of {result.nb_eval} total"
    )
    logger.info(f"Success rate: {result.evaluation_success_rate():.2%}")
    logger.info(f"Mean accuracy: {result.mean_accuracy():.3f}")
    logger.info(f"Mean duration: {result.mean_duration():.2f}s")
    logger.info(f"Total tokens: {result.total_tokens():,}")

    if result.errors:
        logger.warning(f"Total errors encountered: {len(result.errors)}")
        error_summary = result.get_error_summary()
        for error_type, count in error_summary.items():
            logger.warning(f"  {error_type}: {count} occurrences")

    # Log metrics to MLflow if a run is active
    if mlflow.active_run() is not None:
        mlflow.log_metrics(
            metrics={
                "mean_accuracy": result.mean_accuracy(),
                "nb_errors": len(result.errors),
                "mean_duration": result.mean_duration(),
            },
            model_id=lm.model,
        )
        logger.info("Logged metrics to MLflow.")

    return result


if __name__ == "__main__":
    # Run evaluation with error handling
    from src.config import LANGUAGE_MODELS

    llm = LANGUAGE_MODELS["qwen3-coder"]
    lm = LM(
        model=llm.url,
        api_key=llm.api_key,
        max_tokens=2**14,
    )
    mlflow.dspy.autolog(log_evals=True)  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")

    result = evaluate(
        llm=lm,
        dataset_type="dev",
        max_examples=5,
        start_run=True,
    )

    # Check your tracking attributes
    print(f"Total attempts: {result.nb_eval}")
    print(f"Failed attempts: {result.nb_failed_eval}")
    print(f"Success rate: {result.evaluation_success_rate():.2%}")

    # Analyze error patterns
    error_summary = result.get_error_summary()
    print(f"Error breakdown: {error_summary}")
