"""Shared OpenAI client factory for RAG modules."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from configs.settings import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_TIMEOUT, openai_configured


@lru_cache(maxsize=1)
def _build_client(api_key: str, base_url: str, timeout: float):
    import openai

    client_kwargs = {"api_key": api_key, "timeout": timeout, "max_retries": 1}
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


def get_vision_client() -> Optional[object]:
    """Return a separately configured image-capable client, never V4 Pro implicitly."""
    from configs.settings import VISION_API_KEY, VISION_BASE_URL, VISION_MODEL

    if not (VISION_API_KEY and VISION_BASE_URL and VISION_MODEL):
        return None
    return _build_client(VISION_API_KEY, VISION_BASE_URL, float(OPENAI_TIMEOUT))
