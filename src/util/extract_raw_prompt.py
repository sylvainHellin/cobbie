"""Utility to extract the rendered system prompt from a BAML Collector."""

import json

from baml_py.baml_py import Collector
from loguru import logger


def extract_raw_prompt(collector: Collector) -> str | None:
    """
    Extract the system prompt from the first HTTP call in a BAML Collector.

    Parses collector.last.calls[0].http_request.body → JSON → messages[role=system].content.

    Returns:
        The system prompt string, or None if extraction fails.
    """
    try:
        if not collector.last or not collector.last.calls:
            return None

        first_call = collector.last.calls[0]

        if not hasattr(first_call, "http_request") or not first_call.http_request:
            return None

        http_body = first_call.http_request.body

        # Try text method first
        if hasattr(http_body, "text"):
            try:
                body_text = http_body.text()
                if body_text:
                    prompt = _extract_system_from_json(body_text)
                    if prompt:
                        return prompt
            except Exception:
                pass

        # Try json method
        if hasattr(http_body, "json"):
            try:
                body_json = http_body.json()
                if isinstance(body_json, dict) and "messages" in body_json:
                    return _find_system_content(body_json["messages"])
                elif isinstance(body_json, str):
                    return body_json
            except Exception:
                pass

        # Try raw method as last resort
        if hasattr(http_body, "raw"):
            try:
                body_raw = http_body.raw()
                if isinstance(body_raw, bytes):
                    body_raw = body_raw.decode("utf-8")
                return body_raw
            except Exception:
                pass

    except Exception as e:
        logger.warning(f"Could not extract raw prompt: {e}")

    return None


def _extract_system_from_json(text: str) -> str | None:
    """Parse JSON text and extract the system message content."""
    try:
        body_json = json.loads(text)
        if isinstance(body_json, dict) and "messages" in body_json:
            return _find_system_content(body_json["messages"])
        return text
    except json.JSONDecodeError:
        return text


def _find_system_content(messages: list) -> str | None:
    """Find and return the content of the first system message."""
    for msg in messages:
        if msg.get("role") == "system":
            content = msg.get("content", "")
            if isinstance(content, list) and len(content) > 0:
                return content[0].get("text", "")
            elif isinstance(content, str):
                return content
    return None
