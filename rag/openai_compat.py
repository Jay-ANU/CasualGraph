"""Compatibility helpers for text completion parameters."""
from __future__ import annotations


def chat_token_kwargs(model: str, max_tokens: int) -> dict:
    """Keep bounded auxiliary/Flash requests in non-thinking mode on DeepSeek.

    Deep mode uses the Anthropic-format endpoint and its own reasoning budget.
    Without this override DeepSeek may spend a small output budget on reasoning
    and return no visible content to the existing RAG pipeline.
    """
    normalized = (model or "").strip().lower()
    if normalized.startswith("deepseek-v4-"):
        return {"max_tokens": max_tokens, "extra_body": {"thinking": {"type": "disabled"}}}
    if normalized.startswith(("gpt-5", "o1", "o3")):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}
