"""Token counting helper (tiktoken-based)."""

import tiktoken


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """Count the number of tokens in ``text`` using tiktoken.

    Falls back to the ``cl100k_base`` encoding when the model is unknown.
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))
