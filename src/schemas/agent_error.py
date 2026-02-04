"""Unified error type returned by all agents on failure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from baml_py.baml_py import Collector

    from src.baml.baml_client.types import FinalAnswer


@dataclass
class AgentError:
    """Returned by any agent when a BAML call fails after all retries."""

    error_type: str  # e.g. "BamlValidationError", "ConnectionError"
    error_message: str
    context_name: str  # which agent/function failed, e.g. "Cobbie", "EvaluateResponse"
    raw_output: str | None = None  # raw LLM output if available (from BamlValidationError)
    attempts: int = 0  # how many retry attempts were made


@dataclass
class CobbiResult:
    """Result wrapper for the Cobbie agent."""

    answer: FinalAnswer | None = None
    error: AgentError | None = None
    collector: Collector | None = None
    history: str = ""
