"""Anthropic-format transport for DeepSeek; no Anthropic account is used.

The public factory name stays stable for the existing Deep answerer. DeepSeek
supports the Messages API and its SSE text stream at /anthropic, so prompts,
source citations, history and the frontend's streaming contract stay intact.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from configs.settings import (
    ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, RAG_DEEP_TIMEOUT,
    DEEPSEEK_MAX_RETRIES, anthropic_configured,
)


@lru_cache(maxsize=1)
def _build_client(api_key: str, base_url: str, timeout: float):
    import anthropic
    if not base_url:
        raise ValueError("A DeepSeek endpoint is required; refusing an implicit Anthropic fallback.")
    return anthropic.Anthropic(
        api_key=api_key, base_url=base_url, timeout=timeout,
        max_retries=DEEPSEEK_MAX_RETRIES,
    )


def get_anthropic_client() -> Optional[object]:
    if not anthropic_configured():
        return None
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return None
    return _build_client(ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, float(RAG_DEEP_TIMEOUT))
