"""Compatibility helpers for OpenAI chat completion parameter differences."""

from __future__ import annotations


def chat_token_kwargs(model: str, max_tokens: int) -> dict:
    """Return the correct output-token parameter for the configured model."""
    normalized = (model or "").strip().lower()
    if normalized.startswith(("gpt-5", "o1", "o3")):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}
