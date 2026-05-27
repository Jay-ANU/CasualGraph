"""Route questions between fast, RAG, and controlled agent paths."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from configs.settings import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    RAG_HYBRID_AGENT_ROUTER_LLM_ENABLED,
    RAG_HYBRID_AGENT_ROUTER_MAX_TOKENS,
    RAG_HYBRID_AGENT_ROUTER_MODEL,
    RAG_HYBRID_AGENT_ROUTER_TIMEOUT,
    deepseek_configured,
)
from rag.agent_types import AgentBudget, HybridRouteDecision
from rag import deepseek_resilience


_FAST_BUDGET = AgentBudget(max_steps=0, deadline_seconds=4)
_RAG_BUDGET = AgentBudget(max_steps=0, deadline_seconds=12)
_FLASH_AGENT_BUDGET = AgentBudget(max_steps=2, deadline_seconds=20)
_DEEP_AGENT_BUDGET = AgentBudget(max_steps=5, deadline_seconds=90)
_VALID_PATHS = {"fast", "rag", "agent"}

_QUICK_CHITCHAT_PATTERN = re.compile(
    r"^\s*(hi|hello|hey|hi there|hello there|thanks|thank you|thx|bye|goodbye|"
    r"how are you|who are you|what can you do|help|你好|您好|在吗|谢谢|感谢|再见|拜拜|你是谁|你能做什么|帮助)"
    r"\s*[.!?。！？]*\s*$",
    re.I,
)
_COMPARISON_PATTERN = re.compile(
    r"\b(compare|contrast|versus|vs\.?|across|between|relative to|which|better|worse|rank|ranking)\b|"
    r"比较|对比|相比|哪个|排序",
    re.I,
)
_JUDGMENT_PATTERN = re.compile(
    r"\b(judge|assess|evaluate|determine|decide|identify|analy[sz]e|recommend|support(?:ed)? by evidence)\b|"
    r"判断|评估|分析|建议|证据支持",
    re.I,
)
_MULTI_STEP_PATTERN = re.compile(
    r"\b(and|then|also|with supporting evidence|supported by evidence|explain why|synthesi[sz]e)\b|"
    r"同时|并且|分别|综合|证据",
    re.I,
)
_ESG_COMPLEX_PATTERN = re.compile(
    r"\b("
    r"esg|sustainability|climate|transition risk|governance|emissions?|scope [123]|"
    r"net zero|decarboni[sz]ation|materiality|supply chain|human rights|"
    r"risk|risks|opportunit(?:y|ies)|target|targets|scenario|strategy"
    r")\b|"
    r"环境|社会|治理|排放|气候|风险|目标|供应链|战略",
    re.I,
)
_CROSS_DOCUMENT_SCOPE_PATTERN = re.compile(
    r"\b("
    r"across(?:\s+(?:all|uploaded|multiple|the))?\s+(?:reports?|documents?)|"
    r"all\s+(?:reports?|documents?)|"
    r"uploaded\s+(?:reports?|documents?)|"
    r"multiple\s+(?:reports?|documents?)"
    r")\b|"
    r"所有报告|全部报告|多个报告|跨文档|跨报告|这些报告|上传的报告",
    re.I,
)


def decide_hybrid_path(
    question: str,
    reasoning_mode: str,
    document_ids: List[str],
    preferred_document_id: Optional[str],
    answer_intent: Optional[Dict[str, Any]],
) -> HybridRouteDecision:
    """Choose the least expensive path that can answer the request.

    DeepSeek is the primary semantic router. Local rules are intentionally
    retained as a fallback when the LLM router is disabled, unconfigured, or
    returns an invalid response.
    """

    text = str(question or "").strip()
    mode = str((answer_intent or {}).get("mode") or "").strip().lower()
    intent_confidence = _safe_confidence((answer_intent or {}).get("confidence"), fallback=0.55)
    docs = [doc_id for doc_id in (document_ids or []) if doc_id]
    reasoning = str(reasoning_mode or "").strip().lower()
    fallback = _decide_with_rules(
        text=text,
        mode=mode,
        intent_confidence=intent_confidence,
        document_count=len(docs),
        preferred_document_id=preferred_document_id,
        reasoning_mode=reasoning,
    )
    if RAG_HYBRID_AGENT_ROUTER_LLM_ENABLED:
        llm_decision = _decide_with_deepseek(
            text=text,
            reasoning_mode=reasoning,
            document_count=len(docs),
            preferred_document_id=preferred_document_id,
            answer_intent=answer_intent or {},
        )
        if llm_decision is not None:
            return _apply_route_policy(llm_decision, text=text, mode=mode, fallback=fallback, reasoning_mode=reasoning)

    return fallback


def _decide_with_rules(
    *,
    text: str,
    mode: str,
    intent_confidence: float,
    document_count: int,
    preferred_document_id: Optional[str],
    reasoning_mode: str,
) -> HybridRouteDecision:
    if _is_fast_request(text, mode):
        return _decision(
            path="fast",
            reason="chitchat_or_general_no_retrieval",
            confidence=max(intent_confidence, 0.9 if mode == "chitchat" else 0.72),
            reasoning_mode=reasoning_mode,
        )

    if _needs_agent(text=text, mode=mode, document_count=document_count, preferred_document_id=preferred_document_id):
        return _decision(
            path="agent",
            reason="complex_multi_document_evidence_task",
            confidence=max(intent_confidence, 0.68),
            reasoning_mode=reasoning_mode,
        )

    return _decision(
        path="rag",
        reason="grounded_retrieval_sufficient",
        confidence=max(intent_confidence, 0.64 if document_count else 0.55),
        reasoning_mode=reasoning_mode,
    )


def _decide_with_deepseek(
    *,
    text: str,
    reasoning_mode: str,
    document_count: int,
    preferred_document_id: Optional[str],
    answer_intent: Dict[str, Any],
) -> Optional[HybridRouteDecision]:
    cache_payload = {
        "text": str(text or "").strip(),
        "reasoning_mode": str(reasoning_mode or "").strip().lower(),
        "document_count": int(document_count or 0),
        "preferred_document_id_present": bool(preferred_document_id),
        "answer_intent": answer_intent or {},
        "model": RAG_HYBRID_AGENT_ROUTER_MODEL,
    }
    cache_hit, cached_value = deepseek_resilience.cache_lookup("hybrid_agent_router", cache_payload)
    if cache_hit:
        if not isinstance(cached_value, dict):
            return None
        path = str(cached_value.get("path") or "").strip().lower()
        if path not in _VALID_PATHS:
            return None
        return _decision(
            path=path,
            reason=str(cached_value.get("reason") or "deepseek:cached_route"),
            confidence=_safe_confidence(cached_value.get("confidence"), fallback=0.7),
            reasoning_mode=reasoning_mode,
        )
    if deepseek_resilience.circuit_is_open("hybrid_agent_router"):
        return None
    if not deepseek_configured():
        return None
    try:
        import openai
    except Exception:
        return None

    prompt = f"""You are the routing controller for an ESG report assistant.

Choose exactly one path:
- fast: small talk or a simple general question that does not need uploaded reports.
- rag: direct report-grounded lookup, summary, or single-document evidence question where one retrieval pass is sufficient.
- agent: complex evidence work that benefits from multiple tool calls, including cross-report comparison, multi-source synthesis, uncertainty analysis, graph-context reasoning, ranking/judgment, or requests mentioning all/uploaded/multiple reports. If the user asks across all reports but only one document is currently visible, still choose agent so the system can verify evidence and state the limitation.

Return JSON only:
{{
  "path": "fast|rag|agent",
  "confidence": 0.0,
  "reason": "short routing reason"
}}

Request context:
- reasoning_mode: {reasoning_mode or "flash"}
- accessible_document_count: {document_count}
- preferred_document_id_present: {bool(preferred_document_id)}
- answer_intent: {json.dumps(answer_intent or {}, ensure_ascii=False)}

User question:
{text}"""
    messages = [
        {"role": "system", "content": "You are a routing classifier. Return only a JSON object."},
        {"role": "user", "content": prompt},
    ]

    try:
        if hasattr(openai, "OpenAI"):
            client = openai.OpenAI(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL,
                timeout=RAG_HYBRID_AGENT_ROUTER_TIMEOUT,
            )
            response = client.chat.completions.create(
                model=RAG_HYBRID_AGENT_ROUTER_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=RAG_HYBRID_AGENT_ROUTER_MAX_TOKENS,
            )
            raw = response.choices[0].message.content or ""
        else:
            openai.api_key = DEEPSEEK_API_KEY
            openai.api_base = DEEPSEEK_BASE_URL
            response = openai.ChatCompletion.create(
                model=RAG_HYBRID_AGENT_ROUTER_MODEL,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                request_timeout=RAG_HYBRID_AGENT_ROUTER_TIMEOUT,
                max_tokens=RAG_HYBRID_AGENT_ROUTER_MAX_TOKENS,
            )
            raw = response["choices"][0]["message"]["content"] or ""
        parsed = _parse_json_object(str(raw))
        path = str(parsed.get("path") or "").strip().lower()
        if path not in _VALID_PATHS:
            return None
        decision = _decision(
            path=path,
            reason=f"deepseek:{str(parsed.get('reason') or 'semantic_route')}",
            confidence=_safe_confidence(parsed.get("confidence"), fallback=0.7),
            reasoning_mode=reasoning_mode,
        )
        deepseek_resilience.cache_store(
            "hybrid_agent_router",
            cache_payload,
            {"path": decision.path, "reason": decision.reason, "confidence": decision.confidence},
        )
        deepseek_resilience.record_success("hybrid_agent_router")
        return decision
    except Exception as exc:
        deepseek_resilience.cache_failure("hybrid_agent_router", cache_payload)
        deepseek_resilience.record_failure("hybrid_agent_router")
        print(f"[rag.hybrid_agent_router] DeepSeek router fell back: {type(exc).__name__}: {exc}")
        return None


def _apply_route_policy(
    decision: HybridRouteDecision,
    *,
    text: str,
    mode: str,
    fallback: HybridRouteDecision,
    reasoning_mode: str,
) -> HybridRouteDecision:
    if decision.path == "fast" and mode in {"evidence", "hybrid"} and not _is_fast_request(text, mode):
        return _decision(
            path="rag",
            reason=f"policy_grounded_request_overrode_{decision.reason}",
            confidence=max(decision.confidence, fallback.confidence),
            reasoning_mode=reasoning_mode,
        )
    return decision


def _is_fast_request(text: str, mode: str) -> bool:
    if mode == "chitchat":
        return True
    if mode == "general" and not _ESG_COMPLEX_PATTERN.search(text):
        return True
    return bool(_QUICK_CHITCHAT_PATTERN.search(text))


def _needs_agent(text: str, mode: str, document_count: int, preferred_document_id: Optional[str]) -> bool:
    explicit_cross_document_scope = bool(_CROSS_DOCUMENT_SCOPE_PATTERN.search(text))

    if document_count < 2 and not explicit_cross_document_scope:
        return False
    if mode not in {"hybrid", "evidence"}:
        return False

    has_comparison = bool(_COMPARISON_PATTERN.search(text))
    has_judgment = bool(_JUDGMENT_PATTERN.search(text))
    has_multi_step = bool(_MULTI_STEP_PATTERN.search(text))
    has_complex_esg = bool(_ESG_COMPLEX_PATTERN.search(text))
    has_cross_document_scope = preferred_document_id is None or explicit_cross_document_scope

    return has_cross_document_scope and has_complex_esg and (
        has_comparison
        or has_judgment
        or (has_multi_step and document_count >= 3)
    )


def _agent_budget(reasoning_mode: str) -> AgentBudget:
    if reasoning_mode == "deep":
        return _DEEP_AGENT_BUDGET
    return _FLASH_AGENT_BUDGET


def _decision(path: str, reason: str, confidence: float, reasoning_mode: str) -> HybridRouteDecision:
    if path == "agent":
        budget = _agent_budget(reasoning_mode)
    elif path == "fast":
        budget = _FAST_BUDGET
    else:
        budget = _RAG_BUDGET
    return HybridRouteDecision(
        path=path,  # type: ignore[arg-type]
        reason=reason,
        confidence=_safe_confidence(confidence, fallback=0.55),
        budget=budget,
    )


def _parse_json_object(raw: str) -> Dict[str, Any]:
    text = str(raw or "").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _safe_confidence(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(parsed, 1.0))
