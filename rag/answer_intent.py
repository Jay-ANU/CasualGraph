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
from rag import deepseek_resilience


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
    r"strategy|strategic|write|draft|framework|improve|direction|"
    r"score|rating|rate|rank|estimate"
    r")\b|预测|影响|建议|策略|框架|怎么写|帮我写|方向|评分|打分|评级|估计",
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
_FOLLOWUP_REFERENCE_PATTERN = re.compile(
    r"\b(this|that|it|they|them|those|these|above|previous|earlier|same|the former|the latter)\b|"
    r"这个|那个|这些|那些|它|他们|上述|上面|前面|刚才|同样|这份|该",
    re.I,
)
_QUICK_CHITCHAT_PATTERN = re.compile(
    r"^\s*(hi|hello|hey|hi there|hello there|thanks|thank you|thx|bye|goodbye|"
    r"how are you|who are you|what can you do|help|你好|您好|在吗|谢谢|感谢|再见|拜拜|你是谁|你能做什么|帮助)"
    r"\s*[.!?。！？]*\s*$",
    re.I,
)
_WORK_CONTEXT_PATTERN = re.compile(
    r"\b("
    r"esg|sustainability|emission|climate|governance|social|scope [123]|"
    r"materiality|metric|kpi|risk|opportunit|financial|revenue|margin|capex|"
    r"company|business|analysis|analyst|assignment|essay|paper|draft|write|"
    r"strategy|impact|performance|supply chain|board|audit|compliance"
    r")\b|报告|分析|论文|作业|公司|指标|治理|排放|气候|风险|财务|策略|影响",
    re.I,
)
_SPECIFIC_ENTITY_PATTERN = re.compile(r"\b[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,4}\b")
_QUESTION_WORDS = {"what", "how", "why", "when", "where", "which", "who", "tell", "give", "can", "could"}
_VALID_MODES = {"evidence", "general", "hybrid", "chitchat"}
_MIN_CHITCHAT_CONFIDENCE = 0.75
_MIN_GENERAL_CONFIDENCE_WITH_ENTITY = 0.70


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

    rule_result = _classify_with_rules(text)
    llm_result: Optional[AnswerIntent] = None
    if (
        RAG_ANSWER_INTENT_ROUTER_ENABLED
        and deepseek_configured()
        and not _is_high_confidence_rule(text, history_block, rule_result)
    ):
        llm_result = _classify_with_deepseek(query=text, history_block=history_block)

    result = _apply_policy_overrides(text, llm_result or rule_result, rule_result=rule_result)
    with _intent_cache_lock:
        _intent_cache[cache_key] = dict(result)
        _intent_cache.move_to_end(cache_key)
        while len(_intent_cache) > _INTENT_CACHE_MAXSIZE:
            _intent_cache.popitem(last=False)
    return result


def _classify_with_deepseek(query: str, history_block: str) -> Optional[AnswerIntent]:
    cache_payload = {
        "query": str(query or "").strip(),
        "history": _history_signature(history_block),
        "model": RAG_ANSWER_INTENT_ROUTER_MODEL,
    }
    cache_hit, cached_value = deepseek_resilience.cache_lookup("answer_intent", cache_payload)
    if cache_hit:
        return dict(cached_value) if isinstance(cached_value, dict) else None
    if deepseek_resilience.circuit_is_open("answer_intent"):
        return None
    try:
        import openai
    except Exception:
        return None

    prompt = f"""Classify the user's answer mode for an ESG/report research assistant.

Modes:
- chitchat: The user is making small talk, emotional/social conversation, greetings, thanks, casual personal questions, or meta conversation. No report retrieval is needed.
- evidence: The user asks for facts from uploaded reports/documents, citations, or source-backed claims.
- general: The user asks a general concept, method, writing, learning, or work-help question that can be answered without uploaded report evidence.
- hybrid: The user asks for prediction, recommendation, drafting, strategy, implications, or analysis where report evidence should be used if available, but general reasoning may be useful when evidence is incomplete.

Return JSON only:
{{
  "mode": "chitchat|evidence|general|hybrid",
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
- If the user asks casual social questions such as whether you like them, how you feel, greetings, thanks, or light conversation, prefer chitchat.

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
        result = _normalize_intent(parsed, backend="deepseek")
        deepseek_resilience.cache_store("answer_intent", cache_payload, result)
        deepseek_resilience.record_success("answer_intent")
        return result
    except Exception as exc:
        deepseek_resilience.cache_failure("answer_intent", cache_payload)
        deepseek_resilience.record_failure("answer_intent")
        print(f"[rag.answer_intent] DeepSeek router fell back: {type(exc).__name__}: {exc}")
        return None


def _classify_with_rules(query: str) -> AnswerIntent:
    if _QUICK_CHITCHAT_PATTERN.search(query):
        return _intent_for_mode("chitchat", reason="rule_quick_chitchat", backend="heuristic", confidence=0.92)

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


def _is_high_confidence_rule(query: str, history_block: str, intent: AnswerIntent) -> bool:
    """Skip the LLM router for cases where local policy is already decisive."""

    text = str(query or "").strip()
    if not text:
        return True

    if str(intent.get("mode") or "") == "chitchat":
        return True

    has_evidence_marker = bool(_EVIDENCE_MARKER_PATTERN.search(text))
    has_predictive_marker = bool(_PREDICTIVE_PATTERN.search(text))
    has_general_marker = bool(_GENERAL_PATTERN.search(text))
    has_report_object = bool(_REPORT_OBJECT_PATTERN.search(text))
    has_broad_entity_request = bool(_BROAD_ENTITY_REQUEST_PATTERN.search(text))
    has_specific_entity = _has_specific_entity(text)
    has_history = bool(str(history_block or "").strip())
    is_followup_reference = bool(_FOLLOWUP_REFERENCE_PATTERN.search(text))

    if has_history and is_followup_reference and not has_evidence_marker and not has_report_object:
        return False
    if has_evidence_marker or has_report_object:
        return True
    if has_predictive_marker:
        return True
    if has_broad_entity_request and has_specific_entity:
        return True
    if has_general_marker and not has_specific_entity and not is_followup_reference:
        return True
    if not has_history and not has_specific_entity:
        return True

    return float(intent.get("confidence") or 0.0) >= 0.85


def _apply_policy_overrides(query: str, intent: AnswerIntent, *, rule_result: Optional[AnswerIntent] = None) -> AnswerIntent:
    result = _normalize_intent(intent, backend=str(intent.get("backend") or "unknown"))
    heuristic = _normalize_intent(rule_result or _classify_with_rules(query), backend=str((rule_result or {}).get("backend") or "heuristic"))
    has_evidence_marker = bool(_EVIDENCE_MARKER_PATTERN.search(query))
    has_report_object = bool(_REPORT_OBJECT_PATTERN.search(query))
    has_predictive_marker = bool(_PREDICTIVE_PATTERN.search(query))
    has_work_context = bool(_WORK_CONTEXT_PATTERN.search(query))
    has_specific_entity = _has_specific_entity(query)
    confidence = float(result.get("confidence") or 0.0)

    if has_evidence_marker or has_report_object:
        forced = "hybrid" if has_predictive_marker else "evidence"
        if result["mode"] != forced:
            result.update(_intent_for_mode(forced, reason="policy_explicit_evidence_request", backend=result["backend"], confidence=max(result["confidence"], 0.9)))
    elif result["mode"] == "chitchat" and confidence < _MIN_CHITCHAT_CONFIDENCE:
        result.update(
            _intent_for_mode(
                str(heuristic.get("mode") or "general"),
                reason="policy_low_confidence_chitchat_fallback",
                backend=result["backend"],
                confidence=max(confidence, float(heuristic.get("confidence") or 0.0)),
            )
        )
    elif result["mode"] == "chitchat" and (has_predictive_marker or has_work_context or has_specific_entity):
        if has_predictive_marker:
            forced = "hybrid"
        elif has_specific_entity and not _GENERAL_PATTERN.search(query):
            forced = "evidence"
        else:
            forced = "general"
        result.update(_intent_for_mode(forced, reason="policy_task_context_not_chitchat", backend=result["backend"], confidence=max(result["confidence"], 0.82)))
    elif has_predictive_marker and result["mode"] in {"general", "chitchat"}:
        result.update(_intent_for_mode("hybrid", reason="policy_predictive_or_recommendation_allows_general_analysis", backend=result["backend"], confidence=max(result["confidence"], 0.82)))
    elif has_specific_entity and _BROAD_ENTITY_REQUEST_PATTERN.search(query) and result["mode"] != "hybrid":
        result.update(_intent_for_mode("hybrid", reason="policy_broad_entity_request_allows_general_context", backend=result["backend"], confidence=max(result["confidence"], 0.78)))
    elif result["mode"] == "general" and has_specific_entity and confidence < _MIN_GENERAL_CONFIDENCE_WITH_ENTITY:
        forced = "hybrid" if has_predictive_marker else "evidence"
        result.update(_intent_for_mode(forced, reason="policy_low_confidence_general_with_entity", backend=result["backend"], confidence=max(result["confidence"], 0.78)))
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
    elif result["mode"] == "chitchat":
        result["allow_general_answer"] = True
        result["needs_retrieval"] = False
        result["needs_citations"] = False
    else:
        result["allow_general_answer"] = True
        result["needs_retrieval"] = True
        result["needs_citations"] = True
    return result


def _intent_for_mode(mode: str, *, reason: str, backend: str, confidence: float) -> AnswerIntent:
    if mode == "chitchat":
        return {
            "mode": "chitchat",
            "needs_retrieval": False,
            "needs_citations": False,
            "allow_general_answer": True,
            "reason": reason,
            "backend": backend,
            "confidence": confidence,
        }
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
