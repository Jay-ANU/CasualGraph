"""Route questions between fast, RAG, and controlled agent paths."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from rag.agent_types import AgentBudget, HybridRouteDecision


_FAST_BUDGET = AgentBudget(max_steps=0, deadline_seconds=4)
_RAG_BUDGET = AgentBudget(max_steps=0, deadline_seconds=12)
_FLASH_AGENT_BUDGET = AgentBudget(max_steps=3, deadline_seconds=20)
_DEEP_AGENT_BUDGET = AgentBudget(max_steps=8, deadline_seconds=90)

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
    r"\b(across|uploaded reports?|all reports?|multiple reports?|reports?|documents?)\b|"
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
    """Choose the least expensive path that can answer the request."""

    text = str(question or "").strip()
    mode = str((answer_intent or {}).get("mode") or "").strip().lower()
    intent_confidence = _safe_confidence((answer_intent or {}).get("confidence"), fallback=0.55)
    docs = [doc_id for doc_id in (document_ids or []) if doc_id]
    reasoning = str(reasoning_mode or "").strip().lower()

    if _is_fast_request(text, mode):
        return HybridRouteDecision(
            path="fast",
            reason="chitchat_or_general_no_retrieval",
            confidence=max(intent_confidence, 0.9 if mode == "chitchat" else 0.72),
            budget=_FAST_BUDGET,
        )

    if _needs_agent(text=text, mode=mode, document_count=len(docs), preferred_document_id=preferred_document_id):
        return HybridRouteDecision(
            path="agent",
            reason="complex_multi_document_evidence_task",
            confidence=max(intent_confidence, 0.68),
            budget=_agent_budget(reasoning),
        )

    return HybridRouteDecision(
        path="rag",
        reason="grounded_retrieval_sufficient",
        confidence=max(intent_confidence, 0.64 if docs else 0.55),
        budget=_RAG_BUDGET,
    )


def _is_fast_request(text: str, mode: str) -> bool:
    if mode == "chitchat":
        return True
    if mode == "general" and not _ESG_COMPLEX_PATTERN.search(text):
        return True
    return bool(_QUICK_CHITCHAT_PATTERN.search(text))


def _needs_agent(text: str, mode: str, document_count: int, preferred_document_id: Optional[str]) -> bool:
    explicit_cross_document_scope = bool(_CROSS_DOCUMENT_SCOPE_PATTERN.search(text))
    unrestricted_all_documents_scope = document_count == 0 and preferred_document_id is None and explicit_cross_document_scope

    if document_count < 2 and not unrestricted_all_documents_scope:
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


def _safe_confidence(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(parsed, 1.0))
