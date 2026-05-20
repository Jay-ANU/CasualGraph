"""Multi-query expansion for RAG retrieval."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
import re
import threading
from typing import Dict, List, Optional

from configs.settings import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_TIMEOUT, openai_configured
from rag.openai_client import get_openai_client
from rag.openai_compat import chat_token_kwargs


_WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "did",
    "does",
    "for",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
}
_MULTI_QUERY_CACHE_MAXSIZE = 512
_multi_query_cache: "OrderedDict[tuple[str, int, str], Dict[str, object]]" = OrderedDict()
_multi_query_cache_lock = threading.Lock()


def generate_query_variants(query: str, history_block: str = "", n_variants: int = 3) -> Dict[str, object]:
    """Return query variants with the original query first."""
    original = str(query or "").strip()
    if not original:
        return {"variants": [], "backend": "disabled", "original": original}

    n_variants = max(1, int(n_variants or 1))
    cache_key = (original, n_variants, _history_signature(history_block))
    cached = _multi_query_cache_get(cache_key)
    if cached is not None:
        return cached
    if n_variants == 1:
        result = {"variants": [original], "backend": "disabled", "original": original}
        _multi_query_cache_set(cache_key, result)
        return result

    variants = _variants_with_openai(original, history_block=history_block, n_variants=n_variants)
    backend = "openai"
    if not variants:
        variants = _variants_with_heuristics(original, n_variants=n_variants)
        backend = "heuristic" if len(variants) > 1 else "disabled"

    variants = _dedupe([original, *variants])[:n_variants]
    if not variants:
        variants = [original]
        backend = "disabled"
    if variants[0] != original:
        variants.insert(0, original)
    result = {"variants": variants[:n_variants], "backend": backend, "original": original}
    _multi_query_cache_set(cache_key, result)
    return result


def _variants_with_openai(query: str, history_block: str, n_variants: int) -> List[str]:
    if not openai_configured():
        return []
    try:
        import openai
    except Exception:
        return []

    system_prompt = (
        "Generate semantic search query variants for ESG RAG retrieval. "
        "Use synonyms, expand abbreviations, and include English/Chinese paraphrases when helpful. "
        "Return one query per line. Do not number, explain, or answer."
    )
    user_prompt = (
        f"Conversation history:\n{history_block or 'No history.'}\n\n"
        f"Original query:\n{query}\n\n"
        f"Generate {max(1, n_variants - 1)} alternative retrieval queries:"
    )
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

    try:
        if hasattr(openai, "OpenAI"):
            client = get_openai_client()
            if client is None:
                return []
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.2,
                messages=messages,
                **chat_token_kwargs(OPENAI_MODEL, 160),
            )
            raw = response.choices[0].message.content or ""
        else:
            openai.api_key = OPENAI_API_KEY
            if OPENAI_BASE_URL:
                openai.api_base = OPENAI_BASE_URL
            response = openai.ChatCompletion.create(
                model=OPENAI_MODEL,
                temperature=0.2,
                messages=messages,
                request_timeout=OPENAI_TIMEOUT,
                **chat_token_kwargs(OPENAI_MODEL, 160),
            )
            raw = response["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        print(f"[rag] multi_query fell back: {type(exc).__name__}: {exc}")
        return []

    return [line.strip().lstrip("-*0123456789. ").strip() for line in raw.splitlines() if line.strip()]


def _variants_with_heuristics(query: str, n_variants: int) -> List[str]:
    terms = [term.lower() for term in _WORD_PATTERN.findall(query) if term.lower() not in _STOP_WORDS]
    variants = []
    if terms:
        variants.append(" ".join(terms))
        variants.append(" ".join(sorted(set(terms))))
    return _dedupe(variants)[: max(0, n_variants - 1)]


def _dedupe(values: List[str]) -> List[str]:
    seen = set()
    output = []
    for value in values:
        key = " ".join(str(value or "").strip().lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(str(value).strip())
    return output


def _history_signature(history_block: str) -> str:
    return hashlib.sha1(str(history_block or "").encode("utf-8")).hexdigest()[:16]


def _multi_query_cache_get(key: tuple[str, int, str]) -> Optional[Dict[str, object]]:
    with _multi_query_cache_lock:
        cached = _multi_query_cache.get(key)
        if cached is None:
            return None
        _multi_query_cache.move_to_end(key)
        return {"variants": list(cached.get("variants", [])), "backend": cached.get("backend"), "original": cached.get("original")}


def _multi_query_cache_set(key: tuple[str, int, str], value: Dict[str, object]) -> None:
    with _multi_query_cache_lock:
        _multi_query_cache[key] = {
            "variants": [str(item) for item in (value.get("variants") or [])],
            "backend": str(value.get("backend") or ""),
            "original": str(value.get("original") or ""),
        }
        _multi_query_cache.move_to_end(key)
        while len(_multi_query_cache) > _MULTI_QUERY_CACHE_MAXSIZE:
            _multi_query_cache.popitem(last=False)
