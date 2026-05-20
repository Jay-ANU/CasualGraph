"""Conversation-aware query rewriting for retrieval."""

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
_ENGLISH_PRONOUN_PATTERN = re.compile(
    r"\b(it|its|they|them|their|theirs|this|that|these|those|he|him|his|she|her|hers)\b",
    re.IGNORECASE,
)
_CHINESE_PRONOUN_PATTERN = re.compile(r"(它|他们|她们|这个|那个|这些|那些|其)")
_CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")

_FOLLOWUP_PREFIXES = (
    "and",
    "also",
    "then",
    "so",
    "what about",
    "how about",
    "what else",
    "how else",
    "why",
    "how",
    "when",
    "where",
    "which one",
    "which ones",
    "more",
    "details",
    "tell me more",
    "expand",
    "compare that",
)
_CHINESE_FOLLOWUP_PREFIXES = (
    "那",
    "那么",
    "那对",
    "那在",
    "这个",
    "那个",
    "这些",
    "那些",
    "然后",
    "还有",
    "以及",
)
_REWRITE_CACHE_MAXSIZE = 512
_rewrite_cache: "OrderedDict[tuple[str, str], Dict[str, object]]" = OrderedDict()
_rewrite_cache_lock = threading.Lock()


def normalize_history(history: Optional[List[Dict]], current_query: str = "", max_items: int = 6) -> List[Dict[str, str]]:
    """Normalize conversation history and drop a duplicate current user turn."""
    if not history:
        return []

    normalized: List[Dict[str, str]] = []
    for item in history[-max_items:]:
        role = str(item.get("role") or item.get("type") or "user").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "agent":
            role = "assistant"
        elif role not in {"user", "assistant"}:
            role = "user"
        normalized.append({"role": role, "content": content})

    query_key = _normalize_text(current_query)
    while normalized and normalized[-1]["role"] == "user" and _normalize_text(normalized[-1]["content"]) == query_key:
        normalized.pop()
    return normalized


def format_history(history: Optional[List[Dict]], current_query: str = "") -> str:
    """Format normalized history for answer prompts."""
    lines = [f"{item['role']}: {item['content']}" for item in normalize_history(history, current_query=current_query)]
    return "\n".join(lines)


def rewrite_query(query: str, history: Optional[List[Dict]] = None) -> Dict[str, object]:
    """Rewrite a follow-up query into a standalone retrieval query when needed."""
    cleaned_query = str(query or "").strip()
    normalized_history = normalize_history(history, current_query=cleaned_query)
    history_block = "\n".join(f"{item['role']}: {item['content']}" for item in normalized_history)
    cache_key = (cleaned_query, _history_signature(history_block))
    cached = _rewrite_cache_get(cache_key)
    if cached is not None:
        return dict(cached)
    if not cleaned_query:
        result = {
            "query": "",
            "rewrite_applied": False,
            "rewrite_backend": "not_needed",
            "history_used": normalized_history,
        }
        _rewrite_cache_set(cache_key, result)
        return result

    if not _should_rewrite(cleaned_query, normalized_history):
        result = {
            "query": cleaned_query,
            "rewrite_applied": False,
            "rewrite_backend": "not_needed",
            "history_used": normalized_history,
        }
        _rewrite_cache_set(cache_key, result)
        return result

    rewritten = _rewrite_with_openai(cleaned_query, normalized_history)
    backend = "openai"
    if not rewritten:
        rewritten = _rewrite_with_heuristics(cleaned_query, normalized_history)
        backend = "heuristic"

    rewritten = rewritten.strip() if rewritten else cleaned_query
    if not rewritten:
        rewritten = cleaned_query

    result = {
        "query": rewritten,
        "rewrite_applied": _normalize_text(rewritten) != _normalize_text(cleaned_query),
        "rewrite_backend": backend,
        "history_used": normalized_history,
    }
    _rewrite_cache_set(cache_key, result)
    return result


def _should_rewrite(query: str, history: List[Dict[str, str]]) -> bool:
    if not history:
        return False

    lowered = query.strip().lower()
    if not lowered:
        return False

    if lowered.startswith(_FOLLOWUP_PREFIXES):
        return True
    if query.startswith(_CHINESE_FOLLOWUP_PREFIXES):
        return True
    if query.endswith("呢"):
        return True
    if _ENGLISH_PRONOUN_PATTERN.search(query):
        return True
    if _CHINESE_PRONOUN_PATTERN.search(query) and len(query) <= 24:
        return True

    word_count = len(_WORD_PATTERN.findall(query))
    if word_count and word_count <= 3 and lowered in {"why", "how", "when", "where", "details", "more"}:
        return True
    if word_count and word_count <= 4 and lowered.startswith(("and ", "also ", "then ")):
        return True
    return False


def _rewrite_with_heuristics(query: str, history: List[Dict[str, str]]) -> str:
    anchor = _select_anchor_turn(history)
    if not anchor:
        return query

    anchor_clean = anchor.rstrip("?.!。！？")
    query_clean = query.strip()
    query_lower = query_clean.lower()

    if _contains_cjk(query_clean) or _contains_cjk(anchor_clean):
        return f"基于前文关于{anchor_clean}的讨论，{query_clean}"

    if query_lower.startswith(("what about", "how about", "and ", "also ", "then ", "what else")):
        return f"In the context of {anchor_clean}, {query_clean}"
    if query_lower in {"why", "how", "when", "where", "details", "more"}:
        return f"{query_clean.capitalize()} about {anchor_clean}?"
    if _ENGLISH_PRONOUN_PATTERN.search(query_clean):
        return f"In the context of {anchor_clean}, {query_clean}"
    return f"{anchor_clean}. {query_clean}"


def _select_anchor_turn(history: List[Dict[str, str]]) -> str:
    user_turns = [item["content"] for item in history if item["role"] == "user"]
    if not user_turns:
        return history[-1]["content"] if history else ""

    for candidate in reversed(user_turns):
        if not _looks_like_followup(candidate):
            return candidate
    return user_turns[-1]


def _looks_like_followup(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return False
    if lowered.startswith(_FOLLOWUP_PREFIXES):
        return True
    if text.startswith(_CHINESE_FOLLOWUP_PREFIXES):
        return True
    if text.endswith("呢"):
        return True
    if _ENGLISH_PRONOUN_PATTERN.search(text):
        return True
    if _CHINESE_PRONOUN_PATTERN.search(text) and len(text) <= 24:
        return True
    return False


def _rewrite_with_openai(query: str, history: List[Dict[str, str]]) -> Optional[str]:
    if not history or not openai_configured():
        return None

    try:
        import openai
    except Exception:
        return None

    history_block = "\n".join(f"{item['role']}: {item['content']}" for item in history)
    system_prompt = (
        "You rewrite follow-up user questions into standalone search queries for retrieval. "
        "Preserve the user's original intent, company, timeframe, metric, and topic. "
        "If the question is already standalone, return it unchanged. "
        "Do not answer the question. Return only the rewritten query."
    )
    user_prompt = (
        f"Conversation history:\n{history_block}\n\n"
        f"Current user question:\n{query}\n\n"
        "Standalone retrieval query:"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        if hasattr(openai, "OpenAI"):
            client = get_openai_client()
            if client is None:
                return None
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0,
                messages=messages,
                **chat_token_kwargs(OPENAI_MODEL, 96),
            )
            rewritten = (response.choices[0].message.content or "").strip()
        else:
            openai.api_key = OPENAI_API_KEY
            if OPENAI_BASE_URL:
                openai.api_base = OPENAI_BASE_URL
            response = openai.ChatCompletion.create(
                model=OPENAI_MODEL,
                temperature=0,
                messages=messages,
                request_timeout=OPENAI_TIMEOUT,
                **chat_token_kwargs(OPENAI_MODEL, 96),
            )
            rewritten = (response["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return None

    rewritten = rewritten.strip().strip('"').strip("'")
    return rewritten or None


def _contains_cjk(text: str) -> bool:
    return bool(_CHINESE_CHAR_PATTERN.search(text))


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _history_signature(history_block: str) -> str:
    return hashlib.sha1(history_block.encode("utf-8")).hexdigest()[:16]


def _rewrite_cache_get(key: tuple[str, str]) -> Optional[Dict[str, object]]:
    with _rewrite_cache_lock:
        cached = _rewrite_cache.get(key)
        if cached is None:
            return None
        _rewrite_cache.move_to_end(key)
        return dict(cached)


def _rewrite_cache_set(key: tuple[str, str], value: Dict[str, object]) -> None:
    with _rewrite_cache_lock:
        _rewrite_cache[key] = dict(value)
        _rewrite_cache.move_to_end(key)
        while len(_rewrite_cache) > _REWRITE_CACHE_MAXSIZE:
            _rewrite_cache.popitem(last=False)
