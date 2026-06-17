"""LLM initialization with model prefix routing.

Ported from the sibling ``bim-query-comparison/shared/src/shared/llm.py`` with
the tracing dependency removed. Backbone selection is purely a function of the
prefixed model id, so the factorial runner can swap providers by string.
"""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model

# OpenAI-compatible providers: prefix -> (base_url, env var holding the key).
_OPENAI_COMPAT = {
    "minimax": ("https://api.minimax.io/v1", "MINIMAX_API_KEY"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"),
    "glm": ("https://api.z.ai/api/coding/paas/v4", "Z_AI_API_KEY"),
    "grok": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}

# Anthropic-compatible providers: prefix -> (base_url, env var holding the key).
# Routed through ChatAnthropic so prompt-cache tokens (cache_creation /
# cache_read) are reported explicitly in usage_metadata -- needed for the
# cached-input cost study. MiniMax M3 is served here.
_ANTHROPIC_COMPAT = {
    "minimax-anthropic": ("https://api.minimax.io/anthropic", "MINIMAX_API_KEY"),
}


def init_llm(model: str, *, request_timeout: float | None = 120, **kwargs):
    """Initialize a LangChain chat model with prefix-based provider routing.

    Args:
        model: Prefixed model id (e.g. ``minimax:MiniMax-M2.7``).
        request_timeout: HTTP request timeout in seconds. Passed as
            ``request_timeout`` to OpenAI-compatible providers, ``timeout`` to
            Gemini/Anthropic, and forwarded for anything else. ``None`` disables
            the timeout.
        **kwargs: Extra keyword arguments forwarded to ``init_chat_model()``.

    Supported prefixes:
      minimax:<model>           MiniMax PAYG (OpenAI-compatible)
      minimax-anthropic:<model> MiniMax PAYG (Anthropic-compatible; cache tokens)
      fireworks:<model>         Fireworks AI (OpenAI-compatible)
      glm:<model>         Z.AI / GLM (OpenAI-compatible)
      grok:<model>        xAI (OpenAI-compatible)
      openrouter:<model>  OpenRouter (OpenAI-compatible; e.g. Opus probe)
      gemini:<model>      Google GenAI
      openai:<model>      OpenAI (pass-through)
      anthropic:<model>   Anthropic (pass-through)
    """
    prefix, _, model_name = model.partition(":")
    if not model_name:
        # No prefix -- pass the whole string to LangChain.
        if request_timeout is not None:
            kwargs.setdefault("timeout", request_timeout)
        return init_chat_model(model, **kwargs)

    if prefix in _OPENAI_COMPAT:
        base_url, env_key = _OPENAI_COMPAT[prefix]
        if request_timeout is not None:
            kwargs.setdefault("request_timeout", request_timeout)
        return init_chat_model(
            f"openai:{model_name}",
            base_url=base_url,
            api_key=os.environ.get(env_key, ""),
            **kwargs,
        )

    if prefix in _ANTHROPIC_COMPAT:
        base_url, env_key = _ANTHROPIC_COMPAT[prefix]
        if request_timeout is not None:
            kwargs.setdefault("timeout", request_timeout)
        return init_chat_model(
            f"anthropic:{model_name}",
            base_url=base_url,
            api_key=os.environ.get(env_key, ""),
            **kwargs,
        )

    if prefix == "gemini":
        if request_timeout is not None:
            kwargs.setdefault("timeout", request_timeout)
        return init_chat_model(
            f"google_genai:{model_name}",
            api_key=os.environ.get("GEMINI_API_KEY", ""),
            **kwargs,
        )

    # openai, anthropic, or any other LangChain-native prefix.
    if request_timeout is not None:
        if prefix == "openai":
            kwargs.setdefault("request_timeout", request_timeout)
        else:
            kwargs.setdefault("timeout", request_timeout)
    return init_chat_model(model, **kwargs)
