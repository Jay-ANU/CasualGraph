"""Answer-mode routing for report-grounded vs general questions."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

from configs.settings import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    RAG_ANSWER_INTENT_ROUTER_ENABLED,
    RAG_ANSWER_INTENT_ROUTER_MAX_TOKENS,
    RAG_ANSWER_INTENT_ROUTER_MODEL,
    RAG_ANSWER_INTENT_ROUTER_TIMEOUT,
    deepseek_configured,
)


AnswerIntent = Dict[str, Any]

_INTENT_CACHE_MAXSIZE = 512
_intent_cache: "OrderedDict[tuple[str, str], AnswerIntent]" = OrderedDict()
_intent_cache_lock = threading.Lock()

_EVIDENCE_MARKER_PATTERN = re.compile(
    r"\b("
    r"according to|based on|from (?:the )?(?:report|document|pdf|filing|evidence)|"
    r"in (?:the )?(?:report|document|pdf|filing)|uploaded|provided report|"
    r"cite|citation|source|evidence|chunk|retrieved|support(?:ed)? by"
    r")\b|根据|按照|基于|引用|出处|来源|报告里|文档里|上传",
    re.I,
)
_PREDICTIVE_PATTERN = re.compile(
    r"\b("
    r"predict|forecast|likely|impact|implication|scenario|recommend|suggest|"
    r"strategy|strategic|write|draft|framework|improve|direction"
    r")\b|预测|影响|建议|策略|框架|怎么写|帮我写|方向",
    re.I,
)
_GENERAL_PATTERN = re.compile(
    r"\b("
    r"what is|what are|explain|how to|how should|concept|definition|meaning|"
    r"example|teach|learn|general|framework|method|methodology|best practice"
    r")\b|是什么|解释|概念|定义|怎么|如何|通用|一般|例子|学习",
    re.I,
)
_REPORT_OBJECT_PATTERN = re.compile(
    r"\b(report|document|pdf|filing|10-k|annual report|sustainability report|uploaded)\b|报告|文档|材料",
    re.I,
)
_BROAD_ENTITY_REQUEST_PATTERN = re.compile(r"\b(tell me something about|tell me about|overview of|who is|what is)\b|介绍一下|讲讲", re.I)
_SPECIFIC_ENTITY_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,4}\b")
_QUESTION_WORDS = {"what", "how", "why", "when", "where", "which", "who", "tell", "give", "can", "could"}
_VALID_MODES = {"evidence", "general", "hybrid"}


def classify_answer_intent(query: str, history_block: str = "") -> AnswerIntent:
    """Classify whether the answer should be grounded, general, or mixed.

    DeepSeek is the semantic router when configured. Local policy still owns
    hard safety boundaries, so explicit evidence requests cannot be downgraded
    to unsourced general answers.
    """

    text = str(query or "").strip()
    history_signature = _history_signature(history_block)
    cache_key = (text, history_signature)
    with _intent_cache_lock:
        cached = _intent_cache.get(cache_key)
        if cached is not None:
            _intent_cache.move_to_end(cache_key)
            return dict(cached)

    llm_result: Optional[AnswerIntent] = None
    if RAG_ANSWER_INTENT_ROUTER_ENABLED and deepseek_configured():
        llm_result = _classify_with_deepseek(query=text, history_block=history_block)

    result = _apply_policy_overrides(text, llm_result or _classify_with_rules(text))
    with _intent_cache_lock:
        _intent_cache[cache_key] = dict(result)
        _intent_cache.move_to_end(cache_key)
        while len(_intent_cache) > _INTENT_CACHE_MAXSIZE:
            _intent_cache.popitem(last=False)
    return result


def _classify_with_deepseek(query: str, history_block: str) -> Optional[AnswerIntent]:
    try:
        import openai
    except Exception:
        return None

    prompt = f"""Classify the user's answer mode for an ESG/report research assistant.

Modes:
- evidence: The user asks for facts from uploaded reports/documents, citations, or source-backed claims.
- general: The user asks a general concept, method, writing, learning, or work-help question that can be answered without uploaded report evidence.
- hybrid: The user asks for prediction, recommendation, drafting, strategy, implications, or analysis where report evidence should be used if available, but general reasoning may be useful when evidence is incomplete.

Return JSON only:
{{
  "mode": "evidence|general|hybrid",
  "needs_retrieval": true,
  "needs_citations": true,
  "allow_general_answer": false,
  "reason": "short reason",
  "confidence": 0.0
}}

Hard guidance:
- If the user explicitly asks "based on/according to/cite/source/uploaded report", mode cannot be general.
- If the user asks about a specific company/report factual claim, prefer evidence unless it is explicitly a prediction/recommendation/drafting task.
- If the user asks for general ESG, business, academic writing, or learning help, prefer general.

Recent history:
{history_block or "No history."}

User question:
{query}"""
    messages = [
        {"role": "system", "content": "You are a routing classifier. Do not answer the user."},
        {"role": "user", "content": prompt},
    ]

    try:
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL,
                timeout=RAG_ANSWER_INTENT_ROUTER_TIMEOUT,
            )
            response = client.chat.completions.create(
                model=RAG_ANSWER_INTENT_ROUTER_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=RAG_ANSWER_INTENT_ROUTER_MAX_TOKENS,
            )
            raw = response.choices[0].message.content or ""
        else:
            openai.api_key = DEEPSEEK_API_KEY
            openai.api_base = DEEPSEEK_BASE_URL
            response = openai.ChatCompletion.create(
                model=RAG_ANSWER_INTENT_ROUTER_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                request_timeout=RAG_ANSWER_INTENT_ROUTER_TIMEOUT,
                max_tokens=RAG_ANSWER_INTENT_ROUTER_MAX_TOKENS,
            )
            raw = response["choices"][0]["message"]["content"] or ""
        parsed = _parse_json_object(str(raw))
        return _normalize_intent(parsed, backend="deepseek")
    except Exception as exc:
        print(f"[rag.answer_intent] DeepSeek router fell back: {type(exc).__name__}: {exc}")
        return None


def _classify_with_rules(query: str) -> AnswerIntent:
    has_evidence_marker = bool(_EVIDENCE_MARKER_PATTERN.search(query))
    has_predictive_marker = bool(_PREDICTIVE_PATTERN.search(query))
    has_general_marker = bool(_GENERAL_PATTERN.search(query))
    has_report_object = bool(_REPORT_OBJECT_PATTERN.search(query))
    has_specific_entity = _has_specific_entity(query)

    if has_evidence_marker or has_report_object:
        mode = "hybrid" if has_predictive_marker else "evidence"
    elif has_predictive_marker:
        mode = "hybrid"
    elif has_general_marker and not has_specific_entity:
        mode = "general"
    elif has_specific_entity:
        mode = "evidence"
    else:
        mode = "general"
    return _intent_for_mode(mode, reason="rule_classification", backend="heuristic", confidence=0.55)


def _apply_policy_overrides(query: str, intent: AnswerIntent) -> AnswerIntent:
    result = _normalize_intent(intent, backend=str(intent.get("backend") or "unknown"))
    has_evidence_marker = bool(_EVIDENCE_MARKER_PATTERN.search(query))
    has_report_object = bool(_REPORT_OBJECT_PATTERN.search(query))
    has_predictive_marker = bool(_PREDICTIVE_PATTERN.search(query))
    has_specific_entity = _has_specific_entity(query)

    if has_evidence_marker or has_report_object:
        forced = "hybrid" if has_predictive_marker else "evidence"
        if result["mode"] != forced:
            result.update(_intent_for_mode(forced, reason="policy_explicit_evidence_request", backend=result["backend"], confidence=max(result["confidence"], 0.9)))
    elif has_predictive_marker and result["mode"] == "general":
        result.update(_intent_for_mode("hybrid", reason="policy_predictive_or_recommendation_allows_general_analysis", backend=result["backend"], confidence=max(result["confidence"], 0.82)))
    elif has_specific_entity and _BROAD_ENTITY_REQUEST_PATTERN.search(query) and result["mode"] != "hybrid":
        result.update(_intent_for_mode("hybrid", reason="policy_broad_entity_request_allows_general_context", backend=result["backend"], confidence=max(result["confidence"], 0.78)))
    elif result["mode"] == "general" and has_specific_entity and not _GENERAL_PATTERN.search(query):
        forced = "hybrid" if has_predictive_marker else "evidence"
        result.update(_intent_for_mode(forced, reason="policy_specific_entity_requires_grounding", backend=result["backend"], confidence=max(result["confidence"], 0.78)))

    return result


def _normalize_intent(value: Dict[str, Any], backend: str) -> AnswerIntent:
    mode = str(value.get("mode") or "").strip().lower()
    if mode not in _VALID_MODES:
        mode = "evidence"
    result = _intent_for_mode(
        mode,
        reason=str(value.get("reason") or "classification"),
        backend=backend,
        confidence=_safe_float(value.get("confidence"), 0.0),
    )
    for key in ("needs_retrieval", "needs_citations", "allow_general_answer"):
        if key in value:
            result[key] = bool(value.get(key))
    if result["mode"] == "evidence":
        result["allow_general_answer"] = False
        result["needs_retrieval"] = True
        result["needs_citations"] = True
    elif result["mode"] == "general":
        result["allow_general_answer"] = True
        result["needs_retrieval"] = False
        result["needs_citations"] = False
    else:
        result["allow_general_answer"] = True
        result["needs_retrieval"] = True
        result["needs_citations"] = True
    return result


def _intent_for_mode(mode: str, *, reason: str, backend: str, confidence: float) -> AnswerIntent:
    if mode == "general":
        return {
            "mode": "general",
            "needs_retrieval": False,
            "needs_citations": False,
            "allow_general_answer": True,
            "reason": reason,
            "backend": backend,
            "confidence": confidence,
        }
    if mode == "hybrid":
        return {
            "mode": "hybrid",
            "needs_retrieval": True,
            "needs_citations": True,
            "allow_general_answer": True,
            "reason": reason,
            "backend": backend,
            "confidence": confidence,
        }
    return {
        "mode": "evidence",
        "needs_retrieval": True,
        "needs_citations": True,
        "allow_general_answer": False,
        "reason": reason,
        "backend": backend,
        "confidence": confidence,
    }


def _has_specific_entity(query: str) -> bool:
    for match in _SPECIFIC_ENTITY_PATTERN.findall(str(query or "")):
        value = match.strip()
        if value.lower() in _QUESTION_WORDS:
            continue
        if value.lower() in {"esg", "ai", "rag"}:
            continue
        return True
    return False


def _safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_json_object(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def _history_signature(history_block: str) -> str:
    return hashlib.sha1(str(history_block or "").encode("utf-8")).hexdigest()[:16]
