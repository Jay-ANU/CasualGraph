"""Query decomposition for compound prediction questions."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
import json
import threading
from typing import Dict, List, Optional

from configs.settings import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_TIMEOUT, openai_configured
from rag.openai_client import get_openai_client
from rag.openai_compat import chat_token_kwargs

_DECOMPOSE_CACHE_MAXSIZE = 512
_decompose_cache: "OrderedDict[tuple[str, int, str], Dict[str, object]]" = OrderedDict()
_decompose_cache_lock = threading.Lock()


def decompose_query(question: str, history_block: str = "", max_subquestions: int = 3) -> Dict[str, object]:
    """Return subquestions for compound questions."""
    question = str(question or "").strip()
    if not question:
        return {"subquestions": [], "is_compound": False, "backend": "disabled"}
    max_subquestions = max(1, int(max_subquestions))
    cache_key = (question, max_subquestions, _history_signature(history_block))
    cached = _decompose_cache_get(cache_key)
    if cached is not None:
        return cached

    if not openai_configured():
        result = _heuristic_decompose(question, max_subquestions=max_subquestions)
        _decompose_cache_set(cache_key, result)
        return result

    try:
        import openai
    except Exception:
        result = _heuristic_decompose(question, max_subquestions=max_subquestions)
        _decompose_cache_set(cache_key, result)
        return result

    system_prompt = (
        "You identify compound ESG questions and decompose them for retrieval. "
        "A compound question has multiple independent subquestions, multi-company or multi-year comparison, "
        "or a multi-step causal chain. Return JSON only."
    )
    user_prompt = f"""{history_block}

Question:
{question}

Return:
{{"is_compound": true|false, "subquestions": ["..."]}}

Limit subquestions to {max(1, max_subquestions)}. If the question is not compound, return the original question as the only subquestion."""
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

    try:
        if hasattr(openai, "OpenAI"):
            client = get_openai_client()
            if client is None:
                result = _heuristic_decompose(question, max_subquestions=max_subquestions)
                _decompose_cache_set(cache_key, result)
                return result
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                **chat_token_kwargs(OPENAI_MODEL, 300),
            )
            raw = response.choices[0].message.content or ""
        else:
            openai.api_key = OPENAI_API_KEY
            if OPENAI_BASE_URL:
                openai.api_base = OPENAI_BASE_URL
            response = openai.ChatCompletion.create(
                model=OPENAI_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                request_timeout=OPENAI_TIMEOUT,
                **chat_token_kwargs(OPENAI_MODEL, 300),
            )
            raw = response["choices"][0]["message"]["content"] or ""
        parsed = json.loads(raw)
        subquestions = _clean_subquestions(parsed.get("subquestions"), question, max_subquestions)
        result = {
            "subquestions": subquestions,
            "is_compound": bool(parsed.get("is_compound")) and len(subquestions) > 1,
            "backend": "openai",
        }
        _decompose_cache_set(cache_key, result)
        return result
    except Exception as exc:
        print(f"[rag] decomposer fell back: {type(exc).__name__}: {exc}")
        result = _heuristic_decompose(question, max_subquestions=max_subquestions)
        _decompose_cache_set(cache_key, result)
        return result


def _heuristic_decompose(question: str, max_subquestions: int) -> Dict[str, object]:
    lowered = question.lower()
    separators = [" and explain ", " and compare ", ";"]
    parts = [question]
    for separator in separators:
        if separator in lowered:
            parts = [part.strip(" ?.") for part in question.split(separator) if part.strip(" ?.")]
            break
    if len(parts) == 1 and any(token in lowered for token in ("compare", " versus ", " vs ", "scope 1, 2, 3")):
        parts = [question]
    subquestions = _clean_subquestions(parts, question, max_subquestions)
    return {"subquestions": subquestions, "is_compound": len(subquestions) > 1, "backend": "heuristic"}


def _clean_subquestions(value, fallback: str, max_subquestions: int) -> List[str]:
    if not isinstance(value, list):
        value = [fallback]
    output = []
    seen = set()
    for item in value:
        text = str(item or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= max(1, max_subquestions):
            break
    return output or [fallback]


def _history_signature(history_block: str) -> str:
    return hashlib.sha1(str(history_block or "").encode("utf-8")).hexdigest()[:16]


def _decompose_cache_get(key: tuple[str, int, str]) -> Optional[Dict[str, object]]:
    with _decompose_cache_lock:
        cached = _decompose_cache.get(key)
        if cached is None:
            return None
        _decompose_cache.move_to_end(key)
        return {
            "subquestions": [str(item) for item in (cached.get("subquestions") or [])],
            "is_compound": bool(cached.get("is_compound")),
            "backend": str(cached.get("backend") or ""),
        }


def _decompose_cache_set(key: tuple[str, int, str], value: Dict[str, object]) -> None:
    with _decompose_cache_lock:
        _decompose_cache[key] = {
            "subquestions": [str(item) for item in (value.get("subquestions") or [])],
            "is_compound": bool(value.get("is_compound")),
            "backend": str(value.get("backend") or ""),
        }
        _decompose_cache.move_to_end(key)
        while len(_decompose_cache) > _DECOMPOSE_CACHE_MAXSIZE:
            _decompose_cache.popitem(last=False)
