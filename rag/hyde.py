"""HyDE query expansion for vector retrieval."""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import OrderedDict
from typing import Dict, Optional

from configs.settings import (
    HYDE_ENABLED,
    HYDE_MAX_TOKENS,
    HYDE_MIN_CHARS,
    HYDE_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_TIMEOUT,
    openai_configured,
)
from rag.openai_client import get_openai_client
from rag.openai_compat import chat_token_kwargs


_WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*|[\u4e00-\u9fff]")
_HYDE_CACHE_MAXSIZE = 512
_hyde_cache: "OrderedDict[tuple[str, str], Dict[str, object]]" = OrderedDict()
_hyde_cache_lock = threading.Lock()


def maybe_generate_hyde_query(query: str, *, context: str = "", force: bool = False) -> Dict[str, object]:
    original = str(query or "").strip()
    if not original:
        return _disabled_result(original, "empty_query")
    if not HYDE_ENABLED:
        return _disabled_result(original, "disabled")
    if not force and not should_use_hyde(original):
        return _disabled_result(original, "not_triggered")

    cache_key = (original, _context_signature(context))
    cached = _hyde_cache_get(cache_key)
    if cached is not None:
        return cached

    started = time.perf_counter()
    hyde_text = generate_hypothetical_doc(original, context=context)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    if len(hyde_text.strip()) < HYDE_MIN_CHARS:
        result = {
            "query": original,
            "hyde_text": "",
            "enabled": False,
            "backend": "too_short",
            "cache_hit": False,
            "hyde_ms": elapsed_ms,
        }
    else:
        result = {
            "query": hyde_text.strip(),
            "hyde_text": hyde_text.strip(),
            "enabled": True,
            "backend": "openai",
            "cache_hit": False,
            "hyde_ms": elapsed_ms,
        }
    _hyde_cache_set(cache_key, result)
    return result


def generate_hypothetical_doc(query: str, context: str = "") -> str:
    """Generate a short hypothetical ESG report excerpt for vector search."""
    if not openai_configured():
        return ""
    try:
        import openai
    except Exception:
        return ""

    context_block = f"\nContext:\n{context.strip()}\n" if context and context.strip() else ""
    system_prompt = (
        "You are an ESG analyst writing a hypothetical report excerpt for retrieval. "
        "Write 3-4 concise, factual-sounding sentences that would directly answer the question. "
        "Do not mention that the passage is hypothetical. Do not include citations."
    )
    user_prompt = f"{context_block}\nQuestion:\n{query}\n\nPassage:"
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

    try:
        if hasattr(openai, "OpenAI"):
            client = get_openai_client()
            if client is None:
                return ""
            response = client.chat.completions.create(
                model=HYDE_MODEL,
                temperature=0.2,
                messages=messages,
                **chat_token_kwargs(HYDE_MODEL, HYDE_MAX_TOKENS),
            )
            return (response.choices[0].message.content or "").strip()

        openai.api_key = OPENAI_API_KEY
        if OPENAI_BASE_URL:
            openai.api_base = OPENAI_BASE_URL
        response = openai.ChatCompletion.create(
            model=HYDE_MODEL,
            temperature=0.2,
            messages=messages,
            request_timeout=OPENAI_TIMEOUT,
            **chat_token_kwargs(HYDE_MODEL, HYDE_MAX_TOKENS),
        )
        return (response["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        print(f"[rag.hyde] generation skipped: {type(exc).__name__}: {exc}")
        return ""


def should_use_hyde(query: str) -> bool:
    return len(_WORD_PATTERN.findall(str(query or ""))) < 10


def attach_hyde_metadata(row: Dict, hyde: Dict[str, object]) -> Dict:
    if not hyde.get("enabled"):
        return row
    output = dict(row)
    output["hyde_used"] = True
    output["hyde_backend"] = str(hyde.get("backend") or "")
    output["hyde_cache_hit"] = bool(hyde.get("cache_hit"))
    output["hyde_ms"] = float(hyde.get("hyde_ms") or 0.0)
    return output


def _disabled_result(query: str, reason: str) -> Dict[str, object]:
    return {
        "query": query,
        "hyde_text": "",
        "enabled": False,
        "backend": reason,
        "cache_hit": False,
        "hyde_ms": 0.0,
    }


def _context_signature(context: str) -> str:
    return hashlib.sha1(str(context or "").encode("utf-8")).hexdigest()[:16]


def _hyde_cache_get(key: tuple[str, str]) -> Optional[Dict[str, object]]:
    with _hyde_cache_lock:
        cached = _hyde_cache.get(key)
        if cached is None:
            return None
        _hyde_cache.move_to_end(key)
        return {**cached, "cache_hit": True, "hyde_ms": 0.0}


def _hyde_cache_set(key: tuple[str, str], value: Dict[str, object]) -> None:
    with _hyde_cache_lock:
        _hyde_cache[key] = dict(value)
        _hyde_cache.move_to_end(key)
        while len(_hyde_cache) > _HYDE_CACHE_MAXSIZE:
            _hyde_cache.popitem(last=False)
