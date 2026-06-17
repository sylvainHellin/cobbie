"""CodeAct harness for the AUTCON revision factorial.

Ported from the sibling ``bim-query-comparison`` IFC DeepAgent pipeline, with
the static-prompt caching inversion, the static/agentic paradigm switch, and the
tools axis added. No tracing (no MLflow/Phoenix).
"""

from src.harness.agent import (
    AgentResult,
    create_ifc_agent,
    run_question,
    sanitize_answer,
)
from src.harness.llm import init_llm
from src.harness.prompts import render_question_message, render_system_prompt

__all__ = [
    "AgentResult",
    "create_ifc_agent",
    "run_question",
    "sanitize_answer",
    "init_llm",
    "render_system_prompt",
    "render_question_message",
]
