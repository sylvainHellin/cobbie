from time import time
from pydantic import BaseModel
from typing import List, Tuple, Any, Dict


class EvaluationResult(BaseModel):
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
