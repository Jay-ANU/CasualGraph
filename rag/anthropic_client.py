"""Shared Anthropic client factory for the Deep reasoning tier.

Mirrors ``rag.openai_client``: lazy + cached construction so we only pay the
SDK import / TLS handshake when Deep mode is actually used. Returns ``None``
when ANTHROPIC_API_KEY is not set so callers can fall back to Flash without
raising.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from configs.settings import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    RAG_DEEP_TIMEOUT,
    anthropic_configured,
)


@lru_cache(maxsize=1)
def _build_client(api_key: str, base_url: str, timeout: float):
    # Import here so projects that never use Deep mode don't need the SDK.
    import os
    import anthropic

    # Empty ANTHROPIC_BASE_URL leaked via load_dotenv() makes httpx raise
    # UnsupportedProtocol because the SDK falls back to the env var and treats
    # "" as the base URL. Always pass a concrete URL so the env fallback is
    # never consulted.
    resolved_base_url = (base_url or "").strip() or "https://api.anthropic.com"
    if not (base_url or "").strip():
        # Also scrub the env var so any other Anthropic client created elsewhere
        # in this process doesn't trip on the empty value.
        if os.environ.get("ANTHROPIC_BASE_URL", None) == "":
            os.environ.pop("ANTHROPIC_BASE_URL", None)
    return anthropic.Anthropic(api_key=api_key, base_url=resolved_base_url, timeout=timeout)


def get_anthropic_client() -> Optional[object]:
    """Return a cached Anthropic client, or None if the Deep tier isn't usable."""
    if not anthropic_configured():
        return None
    try:
        import anthropic  # noqa: F401  — surface ImportError early
    except Exception:
        return None
    return _build_client(ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, float(RAG_DEEP_TIMEOUT))
