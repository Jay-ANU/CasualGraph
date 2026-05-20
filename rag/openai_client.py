"""Shared OpenAI client factory for RAG modules."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from configs.settings import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_TIMEOUT, openai_configured


@lru_cache(maxsize=1)
def _build_client(api_key: str, base_url: str, timeout: float):
    import openai

    client_kwargs = {"api_key": api_key, "timeout": timeout}
    if base_url:
        client_kwargs["base_url"] = base_url
    return openai.OpenAI(**client_kwargs)


def get_openai_client() -> Optional[object]:
    """Return a cached OpenAI client when the v1 SDK is available."""
    if not openai_configured():
        return None
    try:
        import openai
    except Exception:
        return None
    if not hasattr(openai, "OpenAI"):
        return None
    return _build_client(OPENAI_API_KEY, OPENAI_BASE_URL, float(OPENAI_TIMEOUT))
