"""Question answering pipeline using retrieved report chunks."""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterator, List, Optional
import traceback

from configs.settings import (
    RAG_ALLOW_SPECULATION,
    RAG_ANSWER_MODE,
    RAG_HYBRID_ENABLED,
    RAG_HYBRID_FUSION,
    RAG_MULTI_QUERY_ENABLED,
    RAG_MULTI_QUERY_N,
    RAG_GRAPH_CONTEXT_MIN_SOURCES,
)
from notifications.client import notify_unanswerable_async
from rag.agent_runner import AgentRunner, AgentRunResult, agent_result_to_payload, stream_agent_run
from rag.agent_tools import AgentToolRegistry
from rag.agent_types import AgentBudget, HybridRouteDecision
from rag.answer_intent import classify_answer_intent
from rag.chitchat import generate_chitchat_reply, stream_chitchat_reply
from rag.graph_context import build_graph_context, graph_context_enabled
from rag.multi_query import generate_query_variants
from rag.claude_answering import (
    claude_answering_available,
    generate_claude_deep_rag_answer,
    stream_claude_deep_rag_answer,
)
from rag.openai_answering import generate_openai_rag_answer, openai_answering_available, stream_openai_rag_answer
from rag.query_rewriter import format_history, rewrite_query
from rag.retriever import retrieve_context, retrieve_context_multi, retrieve_layered_context
from rag.hybrid_agent_router import decide_hybrid_path
from rag.router import _CJK_PRONOUN_PATTERN, _PRONOUN_PATTERN, route_query
from rag.strategies import STRATEGY_REGISTRY


INSUFFICIENT_CONTEXT_ANSWER = "The provided reports do not contain enough information to answer this question."
_WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")


def _resolve_tier(reasoning_mode: Optional[str]) -> str:
    """Normalize the user-facing model-tier selector to 'flash' or 'deep'.

    Flash = OpenAI quick path (current default). Deep = Anthropic Claude with
    layered retrieval + graph context. Unknown values fall back to Flash.
    """
    normalized = str(reasoning_mode or "flash").strip().lower()
    return "deep" if normalized == "deep" else "flash"


def _extract_query_terms(query: str) -> set[str]:
    stop_words = {
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
    return {term.lower() for term in _WORD_PATTERN.findall(query) if term.lower() not in stop_words}


def _fallback_answer_from_sources(query: str, sources: List[Dict]) -> str:
    """Build a conservative extractive answer when the QA model is unavailable."""
    query_terms = _extract_query_terms(query)
    if not query_terms:
        return INSUFFICIENT_CONTEXT_ANSWER

    scored_sentences = []
    for item in sources:
        text = (item.get("text") or "").strip()
        sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            sentence_terms = {term.lower() for term in _WORD_PATTERN.findall(sentence)}
            overlap = len(query_terms & sentence_terms)
            if overlap:
                scored_sentences.append((overlap, sentence))

    if not scored_sentences:
        return INSUFFICIENT_CONTEXT_ANSWER

    scored_sentences.sort(key=lambda item: (-item[0], len(item[1])))
    selected = []
    seen = set()
    for _, sentence in scored_sentences:
        if sentence in seen:
            continue
        selected.append(sentence)
        seen.add(sentence)
        if len(selected) == 2:
            break

    return " ".join(selected) if selected else INSUFFICIENT_CONTEXT_ANSWER


def _fallback_general_answer(query: str, answer_mode: str) -> str:
    if _CJK_PATTERN.search(str(query or "")):
        prefix = "我没有检索到可引用的报告证据，下面是通用分析："
        if answer_mode == "general":
            prefix = "下面是通用建议，不是来自已上传报告的结论："
        return f"{prefix}\n\n你可以把问题拆成：背景或定义、关键影响因素、可量化指标、风险与机会、最后形成可验证的结论。"
    prefix = "I did not retrieve report evidence for this, so this is general analysis:"
    if answer_mode == "general":
        prefix = "General guidance, not sourced from uploaded reports:"
    return (
        f"{prefix}\n\nBreak the question into context, key drivers, measurable indicators, "
        "risks and opportunities, then turn the result into claims that can be verified with sources."
    )


def _build_local_prompt(
    query: str,
    context: str,
    history_block: str,
    allow_speculation: bool,
    graph_context: Optional[str] = None,
    answer_intent: str = "evidence",
) -> str:
    conversation_context = f"\nConversation history:\n{history_block}\n" if history_block else ""
    graph_context_block = f"\nGraph context:\n{graph_context}\n" if graph_context else ""
    if answer_intent == "general":
        return f"""You are a practical ESG, business, and academic research assistant.

Answer this as general guidance. Do not claim the answer is based on uploaded reports, and do not cite report chunks.
{conversation_context}

Question:
{query}

Answer:
"""

    if answer_intent == "hybrid":
        return f"""You are an ESG report question answering assistant.

Use retrieved report excerpts first when they are available. Cite chunk ids only for claims supported by excerpts.
If the excerpts do not fully answer the question, say so and then provide a clearly labeled "General analysis" section.
Do not present general reasoning as report-backed.
{conversation_context}
{graph_context_block}

Question:
{query}

Report excerpts:
{context}

Answer:
"""

    if allow_speculation:
        return f"""You are an ESG report question answering assistant.

Use the retrieved report excerpts first.
If the excerpts do not fully answer the question, say that clearly and then provide a clearly labeled
"Tentative hypothesis" based on general knowledge.
Do not present speculative claims as if they were supported by the report.
{conversation_context}
{graph_context_block}

Question:
{query}

Report excerpts:
{context}

Answer:
"""

    return f"""You are an ESG report question answering assistant.

Answer the question using only the provided report excerpts.
If the excerpts do not contain enough information, answer exactly:
{INSUFFICIENT_CONTEXT_ANSWER}
{conversation_context}
{graph_context_block}

Question:
{query}

Report excerpts:
{context}

Answer:
"""


def _initialize_timings() -> Dict[str, float]:
    return {
        "rewrite": 0.0,
        "route": 0.0,
        "hyde": 0.0,
        "retrieval": 0.0,
        "rerank": 0.0,
        "graph": 0.0,
        "generate": 0.0,
        "total": 0.0,
    }


def _prepare_answer_context(
    *,
    query: str,
    top_k: int,
    history: Optional[List[Dict]],
    retrieval_filters: Optional[Dict],
    mode: str,
    reasoning_mode: str = "flash",
    user_id: Optional[str],
    answer_intent: Optional[Dict[str, Any]] = None,
) -> Dict:
    timings = _initialize_timings()
    total_started = time.perf_counter()
    tier = _resolve_tier(reasoning_mode)
    # The legacy 'mode' kwarg used to switch between ask/predict execution paths.
    # We now drive routing/retrieval depth solely off `tier`. We still pass a
    # mode hint to route_query so the existing layered-routing heuristic
    # (originally keyed on mode=="predict") fires for Deep.
    route_mode = "predict" if tier == "deep" else "ask"
    resolved_mode = "ask"
    provided_answer_mode = str((answer_intent or {}).get("mode") or "").strip().lower()

    rewrite_started = time.perf_counter()
    if provided_answer_mode == "chitchat":
        rewrite_result = {
            "query": query,
            "rewrite_applied": False,
            "rewrite_backend": "skipped_chitchat",
            "history_used": [],
        }
    elif _should_skip_rewrite_for_query(query=query, history=history):
        rewrite_result = {
            "query": query,
            "rewrite_applied": False,
            "rewrite_backend": "skipped_short_no_history",
            "history_used": [],
        }
    else:
        rewrite_result = rewrite_query(query=query, history=history)
    timings["rewrite"] = round((time.perf_counter() - rewrite_started) * 1000, 2)
    retrieval_query = str(rewrite_result["query"]).strip() or query
    history_block = format_history(history, current_query=query)
    if answer_intent is None:
        answer_intent = classify_answer_intent(query=retrieval_query, history_block=history_block)
    answer_mode = str((answer_intent or {}).get("mode") or "evidence").strip().lower()

    route_started = time.perf_counter()
    if answer_mode in {"general", "chitchat"}:
        routing = {
            "strategy": "no_retrieval",
            "reason": f"answer_intent_{answer_mode}",
            "backend": str(answer_intent.get("backend") or "answer_intent"),
            "fallback_chain": [],
        }
    else:
        routing = route_query(query=retrieval_query, history_block=history_block, mode=route_mode, filters=retrieval_filters)
    timings["route"] = round((time.perf_counter() - route_started) * 1000, 2)

    retrieval_result: Dict = {"sources": [], "metadata": {}, "strategy": str(routing.get("strategy") or "vector_only")}
    graph_ctx: Dict = _empty_graph_context("disabled")
    entity_scope_miss = bool((retrieval_filters or {}).get("entity_scope_miss"))
    if entity_scope_miss:
        retrieval_result = {
            "sources": [],
            "metadata": {
                "reason": "entity_scope_miss",
                "entity_scope_terms": list((retrieval_filters or {}).get("entity_scope_terms") or []),
            },
            "strategy": str(routing.get("strategy") or "vector_only"),
            "fallbacks_used": [],
        }
        graph_ctx = _empty_graph_context("entity_scope_miss")
    elif routing.get("strategy") != "no_retrieval":
        retrieval_started = time.perf_counter()
        graph_started = None
        can_parallel_graph = _can_parallel_graph_context(retrieval_filters) and RAG_GRAPH_CONTEXT_MIN_SOURCES <= 0

        if can_parallel_graph and graph_context_enabled():
            graph_started = time.perf_counter()
            graph_filters = _graph_filters_from_retrieval_filters(retrieval_filters, sources=None)
            with ThreadPoolExecutor(max_workers=2) as executor:
                retrieval_future = executor.submit(
                    _run_routed_retrieval,
                    routing=routing,
                    query=retrieval_query,
                    top_k=top_k,
                    filters=retrieval_filters,
                    history_block=history_block,
                )
                graph_future = executor.submit(
                    build_graph_context,
                    question=retrieval_query,
                    filters=graph_filters,
                )
                retrieval_result = retrieval_future.result()
                timings["retrieval"] = round((time.perf_counter() - retrieval_started) * 1000, 2)
                try:
                    graph_ctx = graph_future.result()
                except Exception as exc:
                    print(f"[rag.graph] graph context failed: {type(exc).__name__}: {exc}")
                    graph_ctx = _empty_graph_context("graph_error")
                timings["graph"] = round((time.perf_counter() - graph_started) * 1000, 2) if graph_started else 0.0
        else:
            retrieval_result = _run_routed_retrieval(
                routing=routing,
                query=retrieval_query,
                top_k=top_k,
                filters=retrieval_filters,
                history_block=history_block,
            )
            timings["retrieval"] = round((time.perf_counter() - retrieval_started) * 1000, 2)
            graph_started = time.perf_counter()
            sources_preview = retrieval_result.get("sources", [])
            if RAG_GRAPH_CONTEXT_MIN_SOURCES > 0 and len(sources_preview) >= RAG_GRAPH_CONTEXT_MIN_SOURCES:
                graph_ctx = _empty_graph_context("skipped_sufficient_sources")
            elif graph_context_enabled():
                graph_filters = _graph_filters_from_retrieval_filters(retrieval_filters, sources=sources_preview)
                try:
                    graph_ctx = build_graph_context(question=retrieval_query, filters=graph_filters)
                except Exception as exc:
                    print(f"[rag.graph] graph context failed: {type(exc).__name__}: {exc}")
                    graph_ctx = _empty_graph_context("graph_error")
            else:
                graph_ctx = _empty_graph_context("disabled")
            timings["graph"] = round((time.perf_counter() - graph_started) * 1000, 2)

    sources = retrieval_result.get("sources", [])
    retrieval_metadata = retrieval_result.get("metadata", {})
    timings["hyde"] = _extract_source_ms(retrieval_result, "hyde_ms")
    timings["rerank"] = _extract_rerank_ms(retrieval_result)
    queries = _flatten_queries(retrieval_metadata.get("sub_queries") or [retrieval_query])
    layered_context = retrieval_metadata.get("layered_context")
    decomposition = retrieval_metadata.get("decomposition")
    if tier == "deep" and not layered_context:
        layered_context = {"primary": sources, "priors": [], "regulatory": []}

    return {
        "query": query,
        "top_k": top_k,
        "history": history,
        "retrieval_filters": retrieval_filters,
        "user_id": user_id,
        "resolved_mode": resolved_mode,
        "tier": tier,
        "reasoning_mode": tier,
        "rewrite_result": rewrite_result,
        "retrieval_query": retrieval_query,
        "history_block": history_block,
        "routing": routing,
        "answer_intent": dict(answer_intent or {}),
        "retrieval_result": retrieval_result,
        "graph_ctx": graph_ctx,
        "sources": sources,
        "retrieval_metadata": retrieval_metadata,
        "queries": queries,
        "layered_context": layered_context,
        "decomposition": decomposition,
        "allow_speculation": bool((answer_mode == "hybrid" or (RAG_ALLOW_SPECULATION and answer_mode != "evidence")) and not entity_scope_miss),
        "graph_context_text": graph_ctx.get("text") or None,
        "timings": timings,
        "total_started": total_started,
        "strategy": str(retrieval_result.get("strategy") or routing.get("strategy") or "vector_only"),
    }


def _intent_from_context(prepared: Dict, *, fallback: str) -> str:
    answer_mode = str((prepared.get("answer_intent") or {}).get("mode") or "").lower()
    if answer_mode == "chitchat":
        return "chitchat"
    if answer_mode == "general":
        return "general_guidance"
    if answer_mode == "hybrid":
        return "hybrid"
    strategy = str((prepared.get("routing") or {}).get("strategy") or "").lower()
    if strategy == "no_retrieval":
        return "chitchat"
    if prepared.get("tier") == "deep":
        return "analysis"
    if "graph" in strategy or (prepared.get("graph_ctx") or {}).get("edges"):
        return "graph_reasoning"
    if (prepared.get("decomposition") or {}).get("subquestions"):
        return "comparison"
    return fallback


def _extract_rerank_ms(retrieval_result: Dict) -> float:
    return _extract_source_ms(retrieval_result, "rerank_ms")


def _extract_source_ms(retrieval_result: Dict, field_name: str) -> float:
    values: List[float] = []

    def collect(rows: object) -> None:
        if not isinstance(rows, list):
            return
        seen_values = set()
        for item in rows:
            if not isinstance(item, dict):
                continue
            try:
                value = float(item.get(field_name) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0 and value not in seen_values:
                seen_values.add(value)
                values.append(value)

    collect(retrieval_result.get("sources"))
    layered = (retrieval_result.get("metadata") or {}).get("layered_context")
    if isinstance(layered, dict):
        for rows in layered.values():
            collect(rows)

    return round(sum(values), 2) if values else 0.0


def _build_answer_blocks(*, answer: str, sources: List[Dict], graph_sources: Dict, intent: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = [
        {
            "type": "summary",
            "title": "Answer",
            "content": answer,
        }
    ]
    graph_edges = list((graph_sources or {}).get("edges") or [])
    if graph_edges:
        blocks.append(
            {
                "type": "graph",
                "title": "Graph context",
                "items": graph_edges[:6],
            }
        )
    if sources:
        blocks.append(
            {
                "type": "evidence",
                "title": "Evidence",
                "items": sources[:6],
            }
        )
    if intent == "chitchat":
        blocks[0]["title"] = "Conversation"
    return blocks


def _source_trace_labels(sources: List[Dict], limit: int = 3) -> List[str]:
    labels: List[str] = []
    seen = set()
    for source in sources:
        title = str(source.get("document_title") or source.get("document_id") or "report").strip()
        chunk = str(source.get("chunk_id") or "").strip()
        label = f"{title} · {chunk}" if chunk else title
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def _build_reasoning_trace(prepared: Dict, *, backend: Optional[str] = None) -> List[Dict[str, Any]]:
    """Build a user-facing reasoning trace from executed pipeline decisions.

    This deliberately exposes observable routing, retrieval, graph, and model
    choices rather than hidden model chain-of-thought.
    """

    answer_intent = dict(prepared.get("answer_intent") or {})
    mode = str(answer_intent.get("mode") or "evidence")
    intent_reason = str(answer_intent.get("reason") or "classified from the request")
    intent_backend = str(answer_intent.get("backend") or "router")
    routing = dict(prepared.get("routing") or {})
    retrieval_result = dict(prepared.get("retrieval_result") or {})
    graph_ctx = dict(prepared.get("graph_ctx") or {})
    sources = list(prepared.get("sources") or [])
    timings = dict(prepared.get("timings") or {})
    trace: List[Dict[str, Any]] = [
        {
            "title": "Question type",
            "detail": f"Classified as {mode}. {intent_reason}",
            "meta": {"backend": intent_backend, "mode": mode},
        }
    ]

    rewrite_result = dict(prepared.get("rewrite_result") or {})
    if rewrite_result.get("rewrite_applied"):
        trace.append(
            {
                "title": "Query rewrite",
                "detail": f"Rewritten for retrieval: {prepared.get('retrieval_query')}",
                "meta": {"backend": rewrite_result.get("rewrite_backend"), "timing_ms": timings.get("rewrite")},
            }
        )
    else:
        trace.append(
            {
                "title": "Query rewrite",
                "detail": "Used the original wording because no rewrite was needed.",
                "meta": {"backend": rewrite_result.get("rewrite_backend"), "timing_ms": timings.get("rewrite")},
            }
        )

    strategy = str(retrieval_result.get("strategy") or routing.get("strategy") or "vector_only")
    if strategy == "no_retrieval":
        trace.append(
            {
                "title": "Retrieval",
                "detail": "Skipped report retrieval because the question can be answered as general guidance.",
                "meta": {"strategy": strategy, "timing_ms": timings.get("retrieval")},
            }
        )
    else:
        sub_queries = list(prepared.get("queries") or [])
        detail = f"Used {strategy} over accessible reports and kept {len(sources)} source chunk"
        detail += "" if len(sources) == 1 else "s"
        if len(sub_queries) > 1:
            detail += f" across {len(sub_queries)} sub-queries"
        detail += "."
        trace.append(
            {
                "title": "Evidence search",
                "detail": detail,
                "items": _source_trace_labels(sources),
                "meta": {"strategy": strategy, "timing_ms": timings.get("retrieval")},
            }
        )

    graph_edges = list(graph_ctx.get("edges") or [])
    matched_entities = list(graph_ctx.get("matched_entities") or [])
    if graph_edges or matched_entities:
        trace.append(
            {
                "title": "Graph context",
                "detail": f"Added {len(graph_edges)} graph edge"
                + ("" if len(graph_edges) == 1 else "s")
                + f" and {len(matched_entities)} matched entit"
                + ("y." if len(matched_entities) == 1 else "ies."),
                "meta": {"timing_ms": timings.get("graph")},
            }
        )
    else:
        skipped = str(graph_ctx.get("skipped_reason") or "not used")
        trace.append(
            {
                "title": "Graph context",
                "detail": f"No graph context was added ({skipped}).",
                "meta": {"timing_ms": timings.get("graph")},
            }
        )

    trace.append(
        {
            "title": "Answer generation",
            "detail": f"Generated with {backend or 'selected model'} in {prepared.get('tier') or 'flash'} mode; citations are shown separately when sources were used.",
            "meta": {"backend": backend, "timing_ms": timings.get("generate")},
        }
    )
    return trace


def _build_ask_payload(prepared: Dict, *, answer: str, backend: str) -> Dict:
    tier = prepared.get("tier") or prepared.get("reasoning_mode") or "flash"
    answer_intent = dict(prepared.get("answer_intent") or {})
    payload = {
        "answer": answer,
        "sources": _serialize_sources(prepared["sources"]),
        "graph_sources": _serialize_graph_sources(prepared["graph_ctx"]),
        "backend": backend,
        "mode": "ask",
        "reasoning_mode": tier,
        "answer_mode": answer_intent.get("mode") or "evidence",
        "answer_intent": answer_intent,
        "intent": _intent_from_context(prepared, fallback="answer"),
        "original_query": prepared["query"],
        "rewritten_query": prepared["retrieval_query"],
        "rewrite_applied": bool(prepared["rewrite_result"]["rewrite_applied"]),
        "rewrite_backend": prepared["rewrite_result"]["rewrite_backend"],
        "sub_queries": prepared["queries"],
        "retrieval_strategy": prepared["retrieval_result"].get("strategy"),
        "fusion_method": prepared["retrieval_metadata"].get("fusion_method")
        or _fusion_method_from_strategy(prepared["retrieval_result"].get("strategy")),
        "routing": _serialize_routing(prepared["routing"], prepared["retrieval_result"]),
    }
    # Deep tier exposes the layered (primary / priors / regulatory) context the
    # Claude prompt was built from, so the UI can show provenance beyond the
    # single 'sources' list. Flash sticks to the lean ask payload.
    if tier == "deep":
        payload["layered_sources"] = _serialize_layered_sources(prepared.get("layered_context"))
        payload["decomposition"] = prepared.get("decomposition")
    payload["blocks"] = _build_answer_blocks(
        answer=answer,
        sources=payload["sources"],
        graph_sources=payload["graph_sources"],
        intent=payload["intent"],
    )
    return payload


def _build_stream_meta_payload(prepared: Dict) -> Dict:
    return {
        "sources": _serialize_sources(prepared["sources"]),
        "graph_sources": _serialize_graph_sources(prepared["graph_ctx"]),
        "routing": _serialize_routing(prepared["routing"], prepared["retrieval_result"]),
        "sub_queries": prepared["queries"],
        "retrieval_strategy": prepared["retrieval_result"].get("strategy") or prepared["routing"].get("strategy"),
        "rewritten_query": prepared["retrieval_query"],
        "mode": prepared["resolved_mode"],
        "reasoning_mode": prepared.get("reasoning_mode") or "flash",
        "answer_mode": (prepared.get("answer_intent") or {}).get("mode") or "evidence",
        "answer_intent": dict(prepared.get("answer_intent") or {}),
        "intent": _intent_from_context(prepared, fallback="answer"),
        "reasoning_trace": _build_reasoning_trace(prepared),
        "stream_stage": "context_ready",
    }


def _has_grounding_context(prepared: Dict) -> bool:
    return bool(prepared.get("sources") or prepared.get("graph_context_text"))


def answer_question(
    query: str,
    top_k: int = 5,
    history: Optional[List[Dict]] = None,
    retrieval_filters: Optional[Dict] = None,
    mode: str = "ask",
    reasoning_mode: str = "flash",
    user_id: Optional[str] = None,
    answer_intent: Optional[Dict[str, Any]] = None,
) -> Dict:
    """Answer a question using retrieved ESG report chunks."""
    prepared = _prepare_answer_context(
        query=query,
        top_k=top_k,
        history=history,
        retrieval_filters=retrieval_filters,
        mode=mode,
        reasoning_mode=reasoning_mode,
        user_id=user_id,
        answer_intent=answer_intent,
    )
    timings = prepared["timings"]
    resolved_mode = prepared["resolved_mode"]

    answer_intent_mode = str((prepared.get("answer_intent") or {}).get("mode") or "evidence").lower()

    if (retrieval_filters or {}).get("entity_scope_miss"):
        timings["generate"] = 0.0
        return _finalize_response(
            payload=_build_ask_payload(prepared, answer=INSUFFICIENT_CONTEXT_ANSWER, backend="no_context"),
            timings=timings,
            total_started=prepared["total_started"],
            mode=resolved_mode,
            strategy=prepared["strategy"],
        )

    hybrid_decision = decide_hybrid_path(
        question=query,
        reasoning_mode=reasoning_mode,
        document_ids=list((retrieval_filters or {}).get("document_ids") or []),
        preferred_document_id=(retrieval_filters or {}).get("preferred_document_id"),
        answer_intent=prepared.get("answer_intent"),
    )
    if hybrid_decision.path == "agent":
        registry = AgentToolRegistry(filters=retrieval_filters or {}, history_block=prepared["history_block"])
        runner = AgentRunner(registry=registry, budget=hybrid_decision.budget)
        generate_started = time.perf_counter()
        agent_result = runner.run(
            question=query,
            reasoning_mode=prepared.get("reasoning_mode") or "flash",
            history_block=prepared["history_block"],
        )
        timings["generate"] = round((time.perf_counter() - generate_started) * 1000, 2)
        payload = agent_result_to_payload(agent_result, reasoning_mode=prepared.get("reasoning_mode") or "flash")
        payload["routing"] = {
            "strategy": "agent",
            "reason": hybrid_decision.reason,
            "backend": "hybrid_agent_router",
            "fallback_chain": [],
            "fallbacks_used": [],
        }
        payload["answer_intent"] = dict(prepared.get("answer_intent") or {})
        payload["answer_mode"] = answer_intent_mode
        return _finalize_response(
            payload=payload,
            timings=timings,
            total_started=prepared["total_started"],
            mode=resolved_mode,
            strategy="agent",
        )

    if prepared["routing"].get("strategy") == "no_retrieval" and answer_intent_mode != "general":
        generate_started = time.perf_counter()
        answer = generate_chitchat_reply(query=query, history_block=prepared["history_block"])
        timings["generate"] = round((time.perf_counter() - generate_started) * 1000, 2)
        chitchat_graph_sources = _serialize_graph_sources(None)
        return _finalize_response(
            payload={
                "answer": answer,
                "sources": [],
                "graph_sources": chitchat_graph_sources,
                "backend": "chitchat",
                "mode": resolved_mode,
                "reasoning_mode": prepared.get("reasoning_mode") or "flash",
                "answer_mode": answer_intent_mode,
                "answer_intent": dict(prepared.get("answer_intent") or {}),
                "intent": "chitchat",
                "blocks": _build_answer_blocks(answer=answer, sources=[], graph_sources=chitchat_graph_sources, intent="chitchat"),
                "original_query": query,
                "rewritten_query": prepared["retrieval_query"],
                "rewrite_applied": bool(prepared["rewrite_result"]["rewrite_applied"]),
                "rewrite_backend": prepared["rewrite_result"]["rewrite_backend"],
                "sub_queries": [],
                "retrieval_strategy": "no_retrieval",
                "fusion_method": "none",
                "routing": {
                    "strategy": "no_retrieval",
                    "reason": prepared["routing"].get("reason"),
                    "backend": prepared["routing"].get("backend"),
                    "fallback_chain": [],
                    "fallbacks_used": [],
                },
            },
            timings=timings,
            total_started=prepared["total_started"],
            mode=resolved_mode,
            strategy="no_retrieval",
        )

    tier = prepared.get("tier") or "flash"

    if tier == "deep":
        # Try Claude Deep first. If unconfigured / errored / empty, transparently
        # fall through to the Flash (OpenAI) path below — the user still gets an
        # answer, just from the Flash provider, and the backend label records it.
        generate_started = time.perf_counter()
        deep_answer = None
        if claude_answering_available():
            try:
                layered = prepared.get("layered_context") or {}
                deep_answer = generate_claude_deep_rag_answer(
                    question=query,
                    sources=prepared["sources"],
                    history_block=prepared["history_block"],
                    graph_context=prepared["graph_context_text"],
                    priors=list(layered.get("priors") or []),
                    regulatory=list(layered.get("regulatory") or []),
                    answer_intent=answer_intent_mode,
                )
            except Exception as exc:
                print(f"[rag] Claude Deep answering failed: {type(exc).__name__}: {exc}")
                traceback.print_exc()
                deep_answer = None
        if deep_answer:
            timings["generate"] = round((time.perf_counter() - generate_started) * 1000, 2)
            backend = "claude_deep+graph" if prepared["graph_context_text"] else "claude_deep"
            return _finalize_response(
                payload=_build_ask_payload(prepared, answer=deep_answer, backend=backend),
                timings=timings,
                total_started=prepared["total_started"],
                mode=resolved_mode,
                strategy=prepared["strategy"],
            )
        # Claude unavailable — record nothing yet; fall through to Flash logic.
        print("[rag] Deep tier requested but Claude unavailable — falling back to Flash.")

    if not _has_grounding_context(prepared) and not prepared["allow_speculation"] and answer_intent_mode == "evidence":
        timings["generate"] = 0.0
        _notify_unanswerable(
            query=query,
            rewritten_query=prepared["retrieval_query"],
            failure_reason="no_context",
            retrieval_strategy=prepared["strategy"],
            filters=retrieval_filters or {},
            mode=resolved_mode,
            history=history,
            user_id=user_id,
            top_sources_preview=[],
        )
        return _finalize_response(
            payload=_build_ask_payload(prepared, answer=INSUFFICIENT_CONTEXT_ANSWER, backend="no_context"),
            timings=timings,
            total_started=prepared["total_started"],
            mode=resolved_mode,
            strategy=prepared["strategy"],
        )

    context = (
        "\n\n".join(f"[{item['chunk_id']}] {item['text']}" for item in prepared["sources"])
        if prepared["sources"]
        else "No relevant report excerpts were retrieved."
    )
    prompt = _build_local_prompt(
        query=query,
        context=context,
        history_block=prepared["history_block"],
        allow_speculation=prepared["allow_speculation"],
        graph_context=prepared["graph_context_text"],
        answer_intent=answer_intent_mode,
    )

    answer = None
    backend = None
    answer_backend_mode = RAG_ANSWER_MODE or "auto"
    generate_started = time.perf_counter()

    if answer_backend_mode == "extractive":
        answer = _fallback_answer_from_sources(query, prepared["sources"])
        backend = "extractive_only"

    if answer is None and answer_backend_mode in {"auto", "openai"} and openai_answering_available():
        try:
            answer = generate_openai_rag_answer(
                question=query,
                sources=prepared["sources"],
                history_block=prepared["history_block"],
                graph_context=prepared["graph_context_text"],
                allow_speculation=prepared["allow_speculation"],
                answer_intent=answer_intent_mode,
            )
            if answer:
                backend = "openai" if _has_grounding_context(prepared) else "openai_speculative"
                if prepared["graph_context_text"]:
                    backend = f"{backend}+graph"
        except Exception as exc:
            print(f"[rag] OpenAI answering failed: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            answer = None

    try:
        if answer is None and answer_backend_mode in {"auto", "local_qlora"}:
            import torch
            from ai_service.model_loader import get_model_and_tokenizer

            model, tokenizer = get_model_and_tokenizer()
            inputs = tokenizer(prompt, return_tensors="pt")
            model_device = next(model.parameters()).device
            inputs = {key: value.to(model_device) for key, value in inputs.items()}

            with torch.inference_mode():
                output = model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False,
                    pad_token_id=tokenizer.eos_token_id,
                )

            answer_tokens = output[0][inputs["input_ids"].shape[1]:]
            answer = tokenizer.decode(answer_tokens, skip_special_tokens=True).strip()
            if not answer:
                answer = INSUFFICIENT_CONTEXT_ANSWER
            backend = "local_qlora" if prepared["sources"] else "local_qlora_speculative"
    except Exception as exc:
        print(f"[rag] Local QLoRA answering failed: {type(exc).__name__}: {exc}")
        answer = None

    if answer is None:
        if answer_intent_mode in {"general", "hybrid"} and not prepared["sources"]:
            answer = _fallback_general_answer(query, answer_intent_mode)
            backend = f"{answer_intent_mode}_fallback"
        else:
            answer = _fallback_answer_from_sources(query, prepared["sources"])
            backend = "extractive_fallback" if answer_backend_mode == "auto" else f"{answer_backend_mode}_fallback"
    timings["generate"] = round((time.perf_counter() - generate_started) * 1000, 2)

    if backend == "extractive_fallback":
        _notify_unanswerable(
            query=query,
            rewritten_query=prepared["retrieval_query"],
            failure_reason="extractive_fallback",
            retrieval_strategy=prepared["strategy"],
            filters=retrieval_filters or {},
            mode=resolved_mode,
            history=history,
            user_id=user_id,
            top_sources_preview=prepared["sources"],
        )
    elif answer == INSUFFICIENT_CONTEXT_ANSWER:
        _notify_unanswerable(
            query=query,
            rewritten_query=prepared["retrieval_query"],
            failure_reason="insufficient_context",
            retrieval_strategy=prepared["strategy"],
            filters=retrieval_filters or {},
            mode=resolved_mode,
            history=history,
            user_id=user_id,
            top_sources_preview=prepared["sources"],
        )

    return _finalize_response(
        payload=_build_ask_payload(prepared, answer=answer, backend=backend),
        timings=timings,
        total_started=prepared["total_started"],
        mode=resolved_mode,
        strategy=prepared["strategy"],
    )


def stream_answer_question(
    query: str,
    top_k: int = 5,
    history: Optional[List[Dict]] = None,
    retrieval_filters: Optional[Dict] = None,
    mode: str = "ask",
    reasoning_mode: str = "flash",
    user_id: Optional[str] = None,
    answer_intent: Optional[Dict[str, Any]] = None,
) -> Iterator[Dict]:
    """Yield meta, token, and done events for the selected tier.

    Both Flash (OpenAI) and Deep (Claude) emit the same wire shape:
    ``{type: 'meta'|'token'|'done', ...}``. Deep transparently falls back to
    Flash streaming when Anthropic is unconfigured or its stream yields nothing.
    """

    yield {
        "type": "meta",
        "payload": {
            "mode": "ask",
            "reasoning_mode": _resolve_tier(reasoning_mode),
            "stream_stage": "routing",
        },
    }

    prepared = _prepare_answer_context(
        query=query,
        top_k=top_k,
        history=history,
        retrieval_filters=retrieval_filters,
        mode=mode,
        reasoning_mode=reasoning_mode,
        user_id=user_id,
        answer_intent=answer_intent,
    )
    timings = prepared["timings"]
    yield {"type": "meta", "payload": _build_stream_meta_payload(prepared)}
    answer_intent_mode = str((prepared.get("answer_intent") or {}).get("mode") or "evidence").lower()

    if (retrieval_filters or {}).get("entity_scope_miss"):
        answer = INSUFFICIENT_CONTEXT_ANSWER
        yield {"type": "token", "text": answer}
        timings["generate"] = 0.0
        done_payload = _finalize_response(
            payload=_build_ask_payload(prepared, answer=answer, backend="no_context"),
            timings=timings,
            total_started=prepared["total_started"],
            mode="ask",
            strategy=prepared["strategy"],
        )
        yield {"type": "done", "payload": done_payload}
        return

    hybrid_decision = decide_hybrid_path(
        question=query,
        reasoning_mode=reasoning_mode,
        document_ids=list((retrieval_filters or {}).get("document_ids") or []),
        preferred_document_id=(retrieval_filters or {}).get("preferred_document_id"),
        answer_intent=prepared.get("answer_intent"),
    )
    if hybrid_decision.path == "agent":
        registry = AgentToolRegistry(filters=retrieval_filters or {}, history_block=prepared["history_block"])
        runner = AgentRunner(registry=registry, budget=hybrid_decision.budget)
        generate_started = time.perf_counter()
        for event in stream_agent_run(
            runner=runner,
            question=query,
            reasoning_mode=prepared.get("reasoning_mode") or "flash",
            history_block=prepared["history_block"],
        ):
            if event.get("type") == "done":
                timings["generate"] = round((time.perf_counter() - generate_started) * 1000, 2)
                payload = dict(event.get("payload") or {})
                payload["routing"] = {
                    "strategy": "agent",
                    "reason": hybrid_decision.reason,
                    "backend": "hybrid_agent_router",
                    "fallback_chain": [],
                    "fallbacks_used": [],
                }
                payload["answer_intent"] = dict(prepared.get("answer_intent") or {})
                payload["answer_mode"] = answer_intent_mode
                event = {
                    "type": "done",
                    "payload": _finalize_response(
                        payload=payload,
                        timings=timings,
                        total_started=prepared["total_started"],
                        mode="ask",
                        strategy="agent",
                    ),
                }
            yield event
        return

    if prepared["routing"].get("strategy") == "no_retrieval" and answer_intent_mode != "general":
        generate_started = time.perf_counter()
        parts: List[str] = []
        for chunk in stream_chitchat_reply(query=query, history_block=prepared["history_block"]):
            if not chunk:
                continue
            text = str(chunk)
            parts.append(text)
            yield {"type": "token", "text": text}
        answer = "".join(parts).strip() or generate_chitchat_reply(query=query, history_block=prepared["history_block"])
        timings["generate"] = round((time.perf_counter() - generate_started) * 1000, 2)
        chitchat_graph_sources = _serialize_graph_sources(None)
        done_payload = _finalize_response(
            payload={
                "answer": answer,
                "sources": [],
                "graph_sources": chitchat_graph_sources,
                "backend": "chitchat",
                "mode": "ask",
                "reasoning_mode": prepared.get("reasoning_mode") or "flash",
                "answer_mode": answer_intent_mode,
                "answer_intent": dict(prepared.get("answer_intent") or {}),
                "intent": "chitchat",
                "blocks": _build_answer_blocks(answer=answer, sources=[], graph_sources=chitchat_graph_sources, intent="chitchat"),
                "original_query": query,
                "rewritten_query": prepared["retrieval_query"],
                "rewrite_applied": bool(prepared["rewrite_result"]["rewrite_applied"]),
                "rewrite_backend": prepared["rewrite_result"]["rewrite_backend"],
                "sub_queries": [],
                "retrieval_strategy": "no_retrieval",
                "fusion_method": "none",
                "routing": {
                    "strategy": "no_retrieval",
                    "reason": prepared["routing"].get("reason"),
                    "backend": prepared["routing"].get("backend"),
                    "fallback_chain": [],
                    "fallbacks_used": [],
                },
            },
            timings=timings,
            total_started=prepared["total_started"],
            mode="ask",
            strategy="no_retrieval",
        )
        yield {"type": "done", "payload": done_payload}
        return

    if not _has_grounding_context(prepared) and not prepared["allow_speculation"] and answer_intent_mode == "evidence":
        answer = INSUFFICIENT_CONTEXT_ANSWER
        yield {"type": "token", "text": answer}
        timings["generate"] = 0.0
        _notify_unanswerable(
            query=query,
            rewritten_query=prepared["retrieval_query"],
            failure_reason="no_context",
            retrieval_strategy=prepared["strategy"],
            filters=retrieval_filters or {},
            mode="ask",
            history=history,
            user_id=user_id,
            top_sources_preview=[],
        )
        done_payload = _finalize_response(
            payload=_build_ask_payload(prepared, answer=answer, backend="no_context"),
            timings=timings,
            total_started=prepared["total_started"],
            mode="ask",
            strategy=prepared["strategy"],
        )
        yield {"type": "done", "payload": done_payload}
        return

    answer = None
    backend = None
    answer_backend_mode = RAG_ANSWER_MODE or "auto"
    generate_started = time.perf_counter()
    emitted_parts: List[str] = []
    tier = prepared.get("tier") or "flash"

    if answer_backend_mode == "extractive":
        answer = _fallback_answer_from_sources(query, prepared["sources"])
        backend = "extractive_only"
        if answer:
            emitted_parts.append(answer)
            yield {"type": "token", "text": answer}

    # Deep tier: try Claude streaming first. If it yields nothing (unconfigured,
    # SDK missing, or stream errored), fall through to the Flash path so the
    # user still gets an answer. Emit a meta event so the FE can surface a
    # 'fell back to Flash' notice.
    if answer is None and tier == "deep" and claude_answering_available():
        deep_parts: List[str] = []
        try:
            layered = prepared.get("layered_context") or {}
            for chunk in stream_claude_deep_rag_answer(
                question=query,
                sources=prepared["sources"],
                history_block=prepared["history_block"],
                graph_context=prepared["graph_context_text"],
                priors=list(layered.get("priors") or []),
                regulatory=list(layered.get("regulatory") or []),
                answer_intent=answer_intent_mode,
            ):
                if not chunk:
                    continue
                text = str(chunk)
                deep_parts.append(text)
                emitted_parts.append(text)
                yield {"type": "token", "text": text}
        except Exception as exc:
            print(f"[rag] Claude Deep streaming failed: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            deep_parts = []
        streamed = "".join(deep_parts).strip()
        if streamed:
            answer = streamed
            backend = "claude_deep+graph" if prepared["graph_context_text"] else "claude_deep"
        else:
            # Reset emitted_parts so the Flash stream re-emits cleanly without
            # duplicate Deep prefix tokens to the client.
            emitted_parts = []
            yield {"type": "meta", "payload": {"fallback_to_flash": True, "reason": "claude_unavailable_or_empty"}}
    elif answer is None and tier == "deep" and not claude_answering_available():
        # Deep requested but Anthropic never configured — tell the FE upfront.
        yield {"type": "meta", "payload": {"fallback_to_flash": True, "reason": "anthropic_not_configured"}}

    if answer is None and answer_backend_mode in {"auto", "openai"} and openai_answering_available():
        try:
            for chunk in stream_openai_rag_answer(
                question=query,
                sources=prepared["sources"],
                history_block=prepared["history_block"],
                graph_context=prepared["graph_context_text"],
                allow_speculation=prepared["allow_speculation"],
                answer_intent=answer_intent_mode,
            ):
                if not chunk:
                    continue
                text = str(chunk)
                emitted_parts.append(text)
                yield {"type": "token", "text": text}
            streamed = "".join(emitted_parts).strip()
            if streamed:
                answer = streamed
                backend = "openai" if _has_grounding_context(prepared) else "openai_speculative"
                if prepared["graph_context_text"]:
                    backend = f"{backend}+graph"
        except Exception as exc:
            print(f"[rag] OpenAI streaming failed: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            answer = None

    try:
        if answer is None and answer_backend_mode in {"auto", "local_qlora"}:
            import torch
            from ai_service.model_loader import get_model_and_tokenizer

            context = (
                "\n\n".join(f"[{item['chunk_id']}] {item['text']}" for item in prepared["sources"])
                if prepared["sources"]
                else "No relevant report excerpts were retrieved."
            )
            prompt = _build_local_prompt(
                query=query,
                context=context,
                history_block=prepared["history_block"],
                allow_speculation=prepared["allow_speculation"],
                graph_context=prepared["graph_context_text"],
                answer_intent=answer_intent_mode,
            )
            model, tokenizer = get_model_and_tokenizer()
            inputs = tokenizer(prompt, return_tensors="pt")
            model_device = next(model.parameters()).device
            inputs = {key: value.to(model_device) for key, value in inputs.items()}
            with torch.inference_mode():
                output = model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False,
                    pad_token_id=tokenizer.eos_token_id,
                )
            answer_tokens = output[0][inputs["input_ids"].shape[1]:]
            answer = tokenizer.decode(answer_tokens, skip_special_tokens=True).strip() or INSUFFICIENT_CONTEXT_ANSWER
            backend = "local_qlora" if prepared["sources"] else "local_qlora_speculative"
            yield {"type": "token", "text": answer}
    except Exception as exc:
        print(f"[rag] Local QLoRA answering failed: {type(exc).__name__}: {exc}")
        answer = None

    if answer is None:
        if answer_intent_mode in {"general", "hybrid"} and not prepared["sources"]:
            answer = _fallback_general_answer(query, answer_intent_mode)
            backend = f"{answer_intent_mode}_fallback"
        else:
            answer = _fallback_answer_from_sources(query, prepared["sources"])
            backend = "extractive_fallback" if answer_backend_mode == "auto" else f"{answer_backend_mode}_fallback"
        yield {"type": "token", "text": answer}
    timings["generate"] = round((time.perf_counter() - generate_started) * 1000, 2)

    if backend == "extractive_fallback":
        _notify_unanswerable(
            query=query,
            rewritten_query=prepared["retrieval_query"],
            failure_reason="extractive_fallback",
            retrieval_strategy=prepared["strategy"],
            filters=retrieval_filters or {},
            mode="ask",
            history=history,
            user_id=user_id,
            top_sources_preview=prepared["sources"],
        )
    elif answer == INSUFFICIENT_CONTEXT_ANSWER:
        _notify_unanswerable(
            query=query,
            rewritten_query=prepared["retrieval_query"],
            failure_reason="insufficient_context",
            retrieval_strategy=prepared["strategy"],
            filters=retrieval_filters or {},
            mode="ask",
            history=history,
            user_id=user_id,
            top_sources_preview=prepared["sources"],
        )

    done_payload = _finalize_response(
        payload=_build_ask_payload(prepared, answer=answer, backend=backend),
        timings=timings,
        total_started=prepared["total_started"],
        mode="ask",
        strategy=prepared["strategy"],
    )
    yield {"type": "done", "payload": done_payload}


def _finalize_response(
    *,
    payload: Dict,
    timings: Dict[str, float],
    total_started: float,
    mode: str,
    strategy: str,
) -> Dict:
    timings["total"] = round((time.perf_counter() - total_started) * 1000, 2)
    payload["timings_ms"] = dict(timings)
    print(f"[rag.timing] mode={mode} strategy={strategy} timings_ms={timings}")
    return payload


def _notify_unanswerable(
    *,
    query: str,
    rewritten_query: str,
    failure_reason: str,
    retrieval_strategy: str,
    filters: Optional[Dict],
    mode: str,
    history: Optional[List[Dict]],
    user_id: Optional[str],
    top_sources_preview: List[Dict],
) -> None:
    try:
        notify_unanswerable_async(
            query=query,
            rewritten_query=rewritten_query,
            failure_reason=failure_reason,
            retrieval_strategy=retrieval_strategy,
            filters=filters or {},
            mode=mode,
            user_id=str(user_id).strip() if str(user_id or "").strip() else _extract_notification_user_id(history),
            top_sources_preview=_build_top_sources_preview(top_sources_preview),
        )
    except Exception as exc:
        print(f"[notify] unexpected pipeline hook failure: {type(exc).__name__}: {exc}")


def _extract_notification_user_id(history: Optional[List[Dict]]) -> Optional[str]:
    for item in reversed(history or []):
        value = str(item.get("user_id") or "").strip()
        if value:
            return value
    return None


def _build_top_sources_preview(sources: List[Dict]) -> List[Dict]:
    preview: List[Dict] = []
    for item in sources[:3]:
        preview.append(
            {
                "chunk_id": str(item.get("chunk_id") or ""),
                "document_id": str(item.get("document_id") or ""),
                "score": float(item.get("fusion_score") or item.get("score") or 0.0),
            }
        )
    return preview


def _empty_graph_context(skipped_reason: str) -> Dict:
    return {
        "text": "",
        "matched_entities": [],
        "nodes": [],
        "edges": [],
        "skipped_reason": skipped_reason,
    }


def _can_parallel_graph_context(retrieval_filters: Optional[Dict]) -> bool:
    filters = retrieval_filters or {}
    has_document_ids = bool([item for item in (filters.get("document_ids") or []) if item])
    has_preferred = bool(str(filters.get("preferred_document_id") or "").strip())
    return has_document_ids or has_preferred


def _should_skip_rewrite_for_query(query: str, history: Optional[List[Dict]]) -> bool:
    if history:
        return False
    text = str(query or "").strip()
    if not text:
        return True
    if _PRONOUN_PATTERN.search(text) or _CJK_PRONOUN_PATTERN.search(text):
        return False
    return True


def _serialize_sources(sources: List[Dict]) -> List[Dict]:
    return [
        {
            "chunk_id": item["chunk_id"],
            "text": item["text"],
            "document_id": item.get("document_id"),
            "document_title": item.get("document_title"),
            "document_group": item.get("document_group"),
            "source_type": item.get("source_type"),
            "domain": item.get("domain"),
            "retrieval_scope": item.get("retrieval_scope"),
            "sub_question": item.get("sub_question"),
            "fusion_score": item.get("fusion_score"),
            "fusion_method": item.get("fusion_method"),
        }
        for item in sources
    ]


def _run_routed_retrieval(
    routing: Dict[str, object],
    query: str,
    top_k: int,
    filters: Optional[Dict],
    history_block: str,
) -> Dict:
    primary = str(routing.get("strategy") or "vector_only")
    fallbacks = [str(item) for item in (routing.get("fallback_chain") or [])]
    attempted = [primary, *fallbacks]
    fallbacks_used: List[str] = []
    last_result: Dict = {"sources": [], "metadata": {}, "strategy": primary, "fallbacks_used": []}

    for index, strategy_name in enumerate(attempted):
        strategy = STRATEGY_REGISTRY.get(strategy_name) or STRATEGY_REGISTRY["vector_only"]
        try:
            result = strategy.run(query=query, top_k=top_k, filters=filters, history_block=history_block)
        except Exception as exc:
            print(f"[rag.router] strategy {strategy_name} failed: {type(exc).__name__}: {exc}")
            result = {"sources": [], "metadata": {"error": str(exc)}}
        result["strategy"] = strategy.name
        result["fallbacks_used"] = list(fallbacks_used)
        last_result = result
        if result.get("sources"):
            return result
        if index < len(attempted) - 1:
            next_strategy = attempted[index + 1]
            print(f"[rag.router] fallback {strategy_name} -> {next_strategy}: no_sources")
            fallbacks_used.append(next_strategy)

    return last_result


def _serialize_routing(routing: Dict[str, object], retrieval_result: Dict) -> Dict:
    return {
        "strategy": retrieval_result.get("strategy") or routing.get("strategy"),
        "reason": routing.get("reason"),
        "backend": routing.get("backend"),
        "fallback_chain": routing.get("fallback_chain") or [],
        "fallbacks_used": retrieval_result.get("fallbacks_used") or [],
    }


def _flatten_queries(value) -> List[str]:
    if not isinstance(value, list):
        return [str(value)] if value else []
    output: List[str] = []
    for item in value:
        if isinstance(item, list):
            output.extend(_flatten_queries(item))
        elif str(item or "").strip():
            output.append(str(item).strip())
    return _dedupe_strings(output)


def _fusion_method_from_strategy(strategy: object) -> str:
    value = str(strategy or "")
    if value == "vector_only":
        return "vector"
    if value == "hybrid":
        return "hybrid"
    if value == "multi_query":
        return "rrf_multi_query"
    if value == "decomposition":
        return "decomposition"
    if value == "graph_first":
        return "graph_first"
    if value == "layered":
        return "layered"
    return "vector"


def _build_multi_query(retrieval_query: str, history_block: str) -> Dict[str, object]:
    if not RAG_MULTI_QUERY_ENABLED:
        return {"variants": [retrieval_query], "backend": "disabled", "original": retrieval_query}
    return generate_query_variants(
        query=retrieval_query,
        history_block=history_block,
        n_variants=RAG_MULTI_QUERY_N,
    )


def _retrieve_decomposed_layered_context(
    subquestions: List[str],
    top_k: int,
    filters: Optional[Dict],
    history_block: str,
) -> Dict[str, List[Dict]]:
    primary: List[Dict] = []
    priors: List[Dict] = []
    regulatory: List[Dict] = []
    max_workers = max(1, min(len(subquestions), 4))

    def _run_subquestion(index: int, subquestion: str):
        started = time.perf_counter()
        subquestion_text = str(subquestion or "").strip()
        if not subquestion_text:
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(f"[rag.timing] subq={index} took_ms={elapsed_ms:.0f}")
            return index, "", [], {"primary": [], "priors": [], "regulatory": []}
        try:
            mq = _build_multi_query(subquestion_text, history_block)
            sub_queries = mq.get("variants") or [subquestion_text]
            layered = retrieve_layered_context(
                query=subquestion_text,
                top_k=top_k,
                filters=filters,
                primary_queries=sub_queries if RAG_MULTI_QUERY_ENABLED else None,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(f"[rag.timing] subq={index} took_ms={elapsed_ms:.0f}")
            return index, subquestion_text, [str(item) for item in sub_queries], layered
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(f"[rag.timing] subq={index} took_ms={elapsed_ms:.0f}")
            print(f"[rag.pipeline] decomposed layered subq failed: idx={index} {type(exc).__name__}: {exc}")
            return index, subquestion_text, [subquestion_text], {"primary": [], "priors": [], "regulatory": []}

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for item in executor.map(lambda args: _run_subquestion(*args), list(enumerate(subquestions))):
            results.append(item)

    results.sort(key=lambda row: row[0])
    sub_query_layers: List[List[str]] = []
    for _, subquestion_text, sub_queries, layered in results:
        if not subquestion_text:
            continue
        sub_query_layers.append(sub_queries)
        primary.extend(_tag_sources(layered.get("primary", []), subquestion_text))
        priors.extend(_tag_sources(layered.get("priors", []), subquestion_text))
        regulatory.extend(_tag_sources(layered.get("regulatory", []), subquestion_text))

    return {
        "primary": _dedupe_source_list(primary, top_k=top_k),
        "priors": _dedupe_source_list(priors, top_k=max(3, top_k)),
        "regulatory": _dedupe_source_list(regulatory, top_k=max(3, top_k)),
        "sub_queries": sub_query_layers,
    }


def _tag_sources(sources: List[Dict], subquestion: str) -> List[Dict]:
    return [{**item, "sub_question": subquestion} for item in sources]


def _dedupe_source_list(sources: List[Dict], top_k: int) -> List[Dict]:
    output = []
    seen = set()
    for item in sources:
        key = _source_key_for_pipeline(item)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= top_k:
            break
    return output


def _source_key_for_pipeline(item: Dict) -> str:
    return "||".join(
        [
            str(item.get("document_id") or "").strip(),
            str(item.get("chunk_id") or "").strip(),
            str(item.get("text") or "").strip(),
        ]
    )


def _dedupe_strings(values: List[str]) -> List[str]:
    output = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _fusion_method() -> str:
    if RAG_HYBRID_ENABLED:
        return f"hybrid_{RAG_HYBRID_FUSION if RAG_HYBRID_FUSION in {'rrf', 'weighted'} else 'rrf'}"
    return "vector"


def _serialize_layered_sources(layered_context: Optional[Dict[str, List[Dict]]]) -> Dict[str, List[Dict]]:
    layered_context = layered_context or {}
    return {
        "primary": _serialize_sources(layered_context.get("primary", [])),
        "priors": _serialize_sources(layered_context.get("priors", [])),
        "regulatory": _serialize_sources(layered_context.get("regulatory", [])),
    }


def _serialize_graph_sources(graph_ctx: Optional[Dict]) -> Dict:
    """Shape the graph context for inclusion in the API response."""
    if not graph_ctx:
        return {"used": False, "matched_entities": [], "edges": [], "skipped_reason": "missing"}
    edges = graph_ctx.get("edges") or []
    return {
        "used": bool(graph_ctx.get("text")),
        "matched_entities": [
            {"id": row.get("id"), "name": row.get("name"), "type": row.get("type")}
            for row in (graph_ctx.get("matched_entities") or [])
        ],
        "edges": [
            {
                "source": edge.get("source"),
                "target": edge.get("target"),
                "relation_type": edge.get("relation_type"),
                "confidence": edge.get("confidence"),
                "evidence": edge.get("evidence"),
                "chunk_id": edge.get("chunk_id"),
                "document_id": edge.get("document_id"),
            }
            for edge in edges
        ],
        "skipped_reason": graph_ctx.get("skipped_reason"),
    }


def _graph_filters_from_retrieval_filters(retrieval_filters: Optional[Dict], sources: Optional[List[Dict]] = None) -> Dict:
    """Use the same document scope for vector retrieval and Neo4j graph context."""
    filters = retrieval_filters or {}
    document_ids = [item for item in (filters.get("document_ids") or []) if item]
    preferred_document_id = filters.get("preferred_document_id")
    if preferred_document_id and preferred_document_id not in document_ids:
        document_ids = [preferred_document_id, *document_ids]
    if not document_ids:
        seen = set()
        for source in sources or []:
            document_id = source.get("document_id")
            if document_id and document_id not in seen:
                document_ids.append(document_id)
                seen.add(document_id)

    return {
        "document_ids": document_ids,
        "document_group": filters.get("document_group"),
        "source_type": filters.get("source_type"),
        "domain": filters.get("domain"),
    }
