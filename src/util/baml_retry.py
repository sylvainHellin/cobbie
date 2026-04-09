"""Shared retry wrapper for BAML LLM calls."""

import time
from typing import Callable, TypeVar

import mlflow
from loguru import logger

from src.schemas.agent_error import AgentError

T = TypeVar("T")

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY_S = 30


def call_baml_with_retry(
    fn: Callable[[], T],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay_s: int = DEFAULT_RETRY_DELAY_S,
    context_name: str = "baml_call",
) -> T | AgentError:
    """
    Call a BAML function with retry logic and MLflow error logging.

    Returns the BAML result on success, or AgentError after all retries exhausted.
    """
    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exception = e
            error_type = type(e).__name__
            raw_output = getattr(e, "raw_output", None)

            logger.warning(
                f"[{context_name}] Attempt {attempt}/{max_retries} failed "
                f"({error_type}): {str(e)[:200]}"
            )
            if raw_output:
                logger.debug(
                    f"[{context_name}] Raw LLM output ({len(raw_output)} chars): "
                    f"{raw_output[:500]}"
                )

            # Log to MLflow (best-effort)
            try:
                with mlflow.start_span(
                    name=f"{context_name}_retry_{attempt}",
                    span_type="CHAIN",
                ) as retry_span:
                    retry_span.set_attributes(
                        {
                            "error_type": error_type,
                            "attempt": attempt,
                            "max_retries": max_retries,
                        }
                    )
                    retry_span.set_inputs({"error_message": str(e)[:2000]})
                    if raw_output:
                        retry_span.set_outputs(
                            {"raw_output": str(raw_output)[:2000]}
                        )
                    retry_span.set_status("ERROR")
            except Exception:
                pass

            if attempt < max_retries:
                logger.info(
                    f"[{context_name}] Waiting {retry_delay_s}s before retry..."
                )
                time.sleep(retry_delay_s)

    # All retries exhausted - return AgentError (don't raise)
    assert last_exception is not None
    logger.error(
        f"[{context_name}] All {max_retries} retries exhausted. "
        f"Last error: {type(last_exception).__name__}"
    )
    return AgentError(
        error_type=type(last_exception).__name__,
        error_message=str(last_exception)[:2000],
        context_name=context_name,
        raw_output=str(getattr(last_exception, "raw_output", None))[:2000]
        if getattr(last_exception, "raw_output", None)
        else None,
        attempts=max_retries,
    )
