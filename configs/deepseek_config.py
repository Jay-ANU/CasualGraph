"""Validated DeepSeek configuration, independent of the SDK and application state."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str = field(repr=False)
    model: str
    base_url: str
    anthropic_base_url: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def _base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query
            or parsed.fragment or (parsed.scheme != "https" and not (local and parsed.scheme == "http"))):
        raise ValueError("DeepSeek base URL must be HTTPS (HTTP is allowed only for localhost), without credentials, query or fragment.")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def load_deepseek_config(env: Mapping[str, str]) -> DeepSeekConfig:
    """Never use an old OpenAI/Anthropic key or endpoint as an implicit fallback.

    DeepSeek's Anthropic endpoint silently maps unknown model names to Flash;
    validate IDs here so a typo cannot downgrade the requested Pro model.
    """
    model = (env.get("DEEPSEEK_MODEL") or "deepseek-v4-pro").strip()
    if model not in {"deepseek-v4-pro", "deepseek-v4-flash"}:
        raise ValueError("DEEPSEEK_MODEL must be deepseek-v4-pro or deepseek-v4-flash.")
    base = _base_url(env.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com")
    # Accept the /v1 form used by OpenAI-compatible clients, but never append
    # /anthropic to /v1: DeepSeek exposes that compatibility API at the root.
    if base.endswith("/v1"):
        base = base[:-3]
    if base.endswith("/anthropic"):
        base = base[:-10]
    anthropic_base = _base_url(env.get("DEEPSEEK_ANTHROPIC_BASE_URL") or f"{base}/anthropic")
    return DeepSeekConfig(
        api_key=(env.get("DEEPSEEK_API_KEY") or "").strip(),
        model=model,
        base_url=base,
        anthropic_base_url=anthropic_base,
    )
