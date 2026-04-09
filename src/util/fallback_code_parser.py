"""Fallback parser for CodeAction when BAML structured parsing fails.

When glm-4.7 returns raw Python code instead of JSON-structured CodeAction,
this parser extracts the code and constructs a valid CodeAction object.
"""

import re

from loguru import logger

from src.baml.baml_client.types import CodeAction
from src.schemas.agent_error import AgentError


def try_parse_code_action(error: AgentError) -> CodeAction | None:
    """
    Attempt to extract a CodeAction from a failed BAML response.

    Handles two known failure modes:
    1. Model returns raw Python code (```python ... ```) without JSON wrapping
    2. Model returns empty response (nothing to recover)

    Args:
        error: The AgentError from call_baml_with_retry containing raw_output

    Returns:
        CodeAction if code was successfully extracted, None otherwise
    """
    raw = error.raw_output
    if not raw or not raw.strip():
        logger.warning("[fallback_code_parser] Empty raw_output -- nothing to recover")
        return None

    # Try to extract code from markdown code blocks
    code = _extract_code_block(raw)
    if code:
        logger.info(
            f"[fallback_code_parser] Recovered {len(code)} chars of Python code "
            f"from raw LLM output (markdown code block)"
        )
        return CodeAction(
            thoughts="(fallback: model returned raw code without JSON structure)",
            python_code=code,
        )

    # Try to extract from JSON-like structure with thoughts/python_code fields
    code = _extract_json_fields(raw)
    if code:
        logger.info(
            f"[fallback_code_parser] Recovered {len(code)} chars of Python code "
            f"from raw LLM output (partial JSON)"
        )
        return CodeAction(
            thoughts="(fallback: partially parsed from malformed JSON)",
            python_code=code,
        )

    # If the raw output looks like Python code directly (no markdown fences)
    if _looks_like_python(raw.strip()):
        logger.info(
            f"[fallback_code_parser] Recovered {len(raw.strip())} chars of Python code "
            f"from raw LLM output (bare code)"
        )
        return CodeAction(
            thoughts="(fallback: model returned bare Python code)",
            python_code=raw.strip(),
        )

    logger.warning(
        f"[fallback_code_parser] Could not extract code from raw output "
        f"({len(raw)} chars): {raw[:200]}"
    )
    return None


def _extract_code_block(text: str) -> str | None:
    """Extract Python code from markdown code blocks."""
    # Match ```python ... ``` or ``` ... ```
    patterns = [
        r"```python\s*\n(.*?)```",
        r"```\s*\n(.*?)```",
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            # Return the longest match (most likely the main code block)
            return max(matches, key=len).strip()
    return None


def _extract_json_fields(text: str) -> str | None:
    """Try to extract python_code from a malformed JSON response."""
    # Look for "python_code": "..." or 'python_code': '...'
    pattern = r'"python_code"\s*:\s*"((?:[^"\\]|\\.)*)"|"python_code"\s*:\s*`((?:[^`])*)`'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        code = match.group(1) or match.group(2)
        if code:
            # Unescape JSON string
            code = code.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
            return code.strip()
    return None


def _looks_like_python(text: str) -> bool:
    """Heuristic: does this text look like Python code?"""
    python_indicators = [
        "import ",
        "from ",
        "def ",
        "class ",
        "print(",
        "ifcopenshell",
        "model = ",
        "for ",
        "if __name__",
    ]
    lines = text.split("\n")
    if len(lines) < 3:
        return False
    indicator_count = sum(1 for ind in python_indicators if ind in text)
    return indicator_count >= 2
