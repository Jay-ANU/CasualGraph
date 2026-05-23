"""Dynamic retrieval router for RAG."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
import json
import re
import threading
from typing import Dict, Optional

from configs.settings import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    RAG_CHITCHAT_ENABLED,
    RAG_ROUTER_ENABLED,
    RAG_ROUTER_LLM_ENABLED,
    RAG_ROUTER_MAX_TOKENS,
    RAG_ROUTER_MODEL,
    RAG_ROUTER_TIMEOUT,
    deepseek_configured,
)
from rag.esg_lexicon import ESG_KEYWORDS


_WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_PRONOUN_PATTERN = re.compile(r"\b(it|its|they|them|their|this|that|these|those)\b", re.I)
_CJK_PRONOUN_PATTERN = re.compile(r"(它|他们|她们|这个|那个|这些|那些|其)")
_CODE_PATTERN = re.compile(r"\b(?:FY)?20\d{2}\b|\b\d+(?:\.\d+)?%?\b")
_ACRONYM_PATTERN = re.compile(r"\b(GHG|ISO|GRI|SASB|TCFD|CSRD|SEC|NGER|ESRS|CDP|SBTI|ISSB)\b")
_COMPOUND_PATTERN = re.compile(r"\b(compare|both|respectively|trend|versus|vs\.?|and explain|and compare)\b|以及|同时|分别|对比")
_ENTITY_HINT_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,3}\b")
_GREETINGS = {"hi", "hello", "hey", "你好", "在吗", "早上好", "下午好", "晚上好"}
_META_QUERIES = {"who are you", "what can you do", "help", "你是谁", "你能做什么", "帮助"}
_THANKS_BYE = {"thanks", "thank you", "bye", "goodbye", "谢谢", "感谢", "再见", "拜拜"}
_PURE_FEEDBACK = {"ok", "okay", "got it", "nice", "good", "收到", "好的", "不错", "明白"}
_ROUTER_CACHE_MAXSIZE = 512
_router_llm_cache: "OrderedDict[tuple[str, str, str], Dict[str, object]]" = OrderedDict()
_router_llm_cache_lock = threading.Lock()


def route_query(query: str, history_block: str, mode: str, filters: Optional[Dict]) -> Dict[str, object]:
    """Route a rewritten query to a retrieval strategy."""
    if not RAG_ROUTER_ENABLED:
        strategy = "layered" if mode == "predict" else "vector_only"
        return {"strategy": strategy, "reason": "router_disabled", "backend": "disabled", "fallback_chain": _fallbacks(strategy)}

    heuristic = _route_with_heuristics(query=query, mode=mode, filters=filters, history_block=history_block)
    if heuristic["strategy"] == "no_retrieval" or not RAG_ROUTER_LLM_ENABLED:
        return heuristic

    llm_route = _route_with_llm_cached(query=query, history_block=history_block, mode=mode)
    return llm_route or heuristic


def _route_with_heuristics(query: str, mode: str, filters: Optional[Dict], history_block: str) -> Dict[str, object]:
    text = str(query or "").strip()
    lowered = text.lower()
    word_count = len(_WORD_PATTERN.findall(text))

    if mode != "predict" and _is_no_retrieval(text, lowered, word_count, history_block=history_block):
        return _result("no_retrieval", "small_talk_or_meta_query", "heuristic")
    if mode == "predict":
        return _result("layered", "predict_mode_uses_layered_retrieval", "heuristic")
    if _COMPOUND_PATTERN.search(lowered) and word_count > 7:
        return _result("decomposition", "compound_query_detected", "heuristic")
    if word_count <= 4 or _PRONOUN_PATTERN.search(text) or (_CJK_PRONOUN_PATTERN.search(text) and len(text) <= 24):
        return _result("multi_query", "short_or_ambiguous_followup", "heuristic")
    if _CODE_PATTERN.search(text) or _ACRONYM_PATTERN.search(text):
        return _result("hybrid", "keyword_or_identifier_heavy_query", "heuristic")
    if (filters or {}).get("preferred_document_id") or _has_entity_hint(text):
        return _result("graph_first", "entity_centric_query", "heuristic")
    return _result("vector_only", "simple_lookup", "heuristic")


def _has_entity_hint(text: str) -> bool:
    question_words = {"what", "how", "why", "when", "where", "which", "who", "tell", "compare"}
    for match in _ENTITY_HINT_PATTERN.findall(text):
        if match.strip().lower() in question_words:
            continue
        return True
    return False


def _is_no_retrieval(text: str, lowered: str, word_count: int, history_block: str) -> bool:
    if not RAG_CHITCHAT_ENABLED:
        return False
    normalized = " ".join(lowered.split())
    if normalized in _THANKS_BYE:
        return True
    if normalized in _GREETINGS and word_count <= 3:
        return True
    if normalized in _META_QUERIES:
        return True
    if normalized in _PURE_FEEDBACK and _last_history_role(history_block) == "assistant":
        return True
    if _last_assistant_has_evidence(history_block) and (
        normalized in {"really", "really?", "why", "why?", "how", "解释下", "为什么"}
        or "why" in normalized
        or "为什么" in normalized
    ):
        return False
    if _looks_like_esg_query(text, lowered):
        return False
    if len(text) <= 20 and word_count <= 4 and not _CODE_PATTERN.search(text) and not _ACRONYM_PATTERN.search(text):
        return True
    return False


def _looks_like_esg_query(text: str, lowered: str) -> bool:
    if any(keyword in lowered for keyword in ESG_KEYWORDS):
        return True
    if any(keyword in text for keyword in ESG_KEYWORDS):
        return True
    if _CODE_PATTERN.search(text) or _ACRONYM_PATTERN.search(text):
        return True
    return _has_entity_hint(text)


def _last_history_role(history_block: str) -> str:
    role = ""
    for line in str(history_block or "").splitlines():
        if line.startswith("user:"):
            role = "user"
        elif line.startswith("assistant:"):
            role = "assistant"
    return role


def _last_assistant_has_evidence(history_block: str) -> bool:
    last = ""
    for line in str(history_block or "").splitlines():
        if line.startswith("assistant:"):
            last = line
    return bool(last and (re.search(r"\d", last) or "chunk_" in last.lower()))


def _route_with_llm(query: str, history_block: str, mode: str) -> Optional[Dict[str, object]]:
    if not deepseek_configured():
        return None
    try:
        import openai
    except Exception:
        return None

    prompt = f"""Classify this ESG/report assistant query into one retrieval strategy.

Allowed strategies:
- no_retrieval: pure greeting, thanks, bye, or meta chat that needs no documents.
- vector_only: narrow factual lookup where semantic chunks are enough.
- hybrid: metrics, dates, acronyms, standards, exact terms, or keyword-heavy queries.
- multi_query: short, ambiguous, follow-up, or broad question that benefits from query expansion.
- decomposition: multi-part, comparison, trend, respectively, or question with several sub-questions.
- graph_first: entity-centric, relationship, causal, "impact of X on Y", or path-style query.
- layered: strategic analysis, prediction, scenario, recommendation, Deep mode, or questions needing current/historical/regulatory context.

Return JSON only:
{{"strategy":"no_retrieval|vector_only|hybrid|multi_query|decomposition|graph_first|layered", "reason":"short reason", "confidence":0.0}}

Mode: {mode}
History:
{history_block or "No history."}

Query:
{query}"""
    messages = [
        {"role": "system", "content": "You are a retrieval router. Do not answer the user."},
        {"role": "user", "content": prompt},
    ]
    try:
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL,
                timeout=RAG_ROUTER_TIMEOUT,
            )
            response = client.chat.completions.create(
                model=RAG_ROUTER_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=RAG_ROUTER_MAX_TOKENS,
            )
            raw = response.choices[0].message.content or ""
        else:
            openai.api_key = DEEPSEEK_API_KEY
            openai.api_base = DEEPSEEK_BASE_URL
            response = openai.ChatCompletion.create(
                model=RAG_ROUTER_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                request_timeout=RAG_ROUTER_TIMEOUT,
                max_tokens=RAG_ROUTER_MAX_TOKENS,
            )
            raw = response["choices"][0]["message"]["content"] or ""
        parsed = _parse_json_object(str(raw))
        strategy = str(parsed.get("strategy") or "vector_only")
        if strategy not in {"no_retrieval", "vector_only", "hybrid", "multi_query", "decomposition", "graph_first", "layered"}:
            strategy = "vector_only"
        return _result(strategy, str(parsed.get("reason") or "deepseek_classification"), "deepseek")
    except Exception as exc:
        print(f"[rag.router] DeepSeek router fell back: {type(exc).__name__}: {exc}")
        return None


def _result(strategy: str, reason: str, backend: str) -> Dict[str, object]:
    return {"strategy": strategy, "reason": reason, "backend": backend, "fallback_chain": _fallbacks(strategy)}


def _fallbacks(strategy: str) -> list[str]:
    chains = {
        "vector_only": [],
        "no_retrieval": [],
        "hybrid": ["vector_only"],
        "multi_query": ["hybrid", "vector_only"],
        "decomposition": ["multi_query", "hybrid", "vector_only"],
        "graph_first": ["hybrid", "vector_only"],
        "layered": ["multi_query", "hybrid", "vector_only"],
    }
    return chains.get(strategy, ["vector_only"])


def _route_with_llm_cached(query: str, history_block: str, mode: str) -> Optional[Dict[str, object]]:
    cache_key = (str(query or "").strip(), str(mode or "").strip().lower(), _history_signature(history_block))
    with _router_llm_cache_lock:
        cached = _router_llm_cache.get(cache_key)
        if cached is not None:
            _router_llm_cache.move_to_end(cache_key)
            return dict(cached)

    result = _route_with_llm(query=query, history_block=history_block, mode=mode)
    if result is None:
        return None
    with _router_llm_cache_lock:
        _router_llm_cache[cache_key] = dict(result)
        _router_llm_cache.move_to_end(cache_key)
        while len(_router_llm_cache) > _ROUTER_CACHE_MAXSIZE:
            _router_llm_cache.popitem(last=False)
    return result


def _history_signature(history_block: str) -> str:
    return hashlib.sha1(str(history_block or "").encode("utf-8")).hexdigest()[:16]


def _parse_json_object(raw: str) -> Dict[str, object]:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)
