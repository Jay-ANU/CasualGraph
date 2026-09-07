"""Shared OpenAI-format client; requests are sent to DeepSeek, not OpenAI."""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from configs.settings import (
    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_TIMEOUT,
    DEEPSEEK_MAX_RETRIES, openai_configured,
)


@lru_cache(maxsize=1)
def _build_client(api_key: str, base_url: str, timeout: float):
    import openai
    if not base_url:
        raise ValueError("A DeepSeek endpoint is required; refusing an implicit OpenAI fallback.")
    return openai.OpenAI(
        api_key=api_key, base_url=base_url, timeout=timeout,
        max_retries=DEEPSEEK_MAX_RETRIES,
    )


def get_openai_client() -> Optional[object]:
    if not openai_configured():
        return None
    try:
        import openai
    except ImportError:
        return None
    if not hasattr(openai, "OpenAI"):
        return None
    return _build_client(OPENAI_API_KEY, OPENAI_BASE_URL, float(OPENAI_TIMEOUT))
