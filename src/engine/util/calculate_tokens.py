"""Utility function for calculating tokens from LM history."""

from dspy import LM


def calculate_tokens(lm: LM) -> tuple[int, int]:
    """Calculate total input and output tokens from LM history.

    Args:
        lm: Language model object with history attribute

    Returns:
        tuple[int, int]: (total_input_tokens, total_output_tokens)
    """
    total_input_tokens = 0
    total_output_tokens = 0

    if hasattr(lm, "history") and lm.history:
        for call in lm.history:
            usage = call.get("usage", {})
            total_input_tokens += usage.get("prompt_tokens", 0)
            total_output_tokens += usage.get("completion_tokens", 0)

    return total_input_tokens, total_output_tokens
