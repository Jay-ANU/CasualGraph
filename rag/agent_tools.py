"""Fixed tool registry for controlled hybrid agent evidence gathering."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from rag.agent_types import AgentToolObservation
from rag.graph_context import build_graph_context
from rag.retriever import retrieve_context, retrieve_hybrid, retrieve_layered_context
from rag.source_relevance import filter_layered_sources_by_relevance, filter_sources_by_relevance


class AgentToolRegistry:
    """Small fixed registry for agent-safe evidence tools."""

    def __init__(self, filters: Optional[Dict[str, Any]] = None, history_block: str = "") -> None:
        self.filters = dict(filters or {})
        self.history_block = str(history_block or "")

    def call(self, tool: str, arguments: Optional[Dict[str, Any]] = None) -> AgentToolObservation:
        args = dict(arguments or {})
        try:
            if tool == "search_documents":
                return self._search_documents(args)
            if tool == "read_chunks":
                return self._read_chunks(args)
            if tool in {"get_graph_context", "query_neo4j"}:
                return self._get_graph_context(tool, args)
            if tool == "summarize_evidence":
                return self._summarize_evidence(args)
            return AgentToolObservation(
                tool=tool,
                ok=False,
                summary=f"Unknown tool: {tool}",
                data={},
                error=f"Unknown tool: {tool}",
            )
        except Exception as exc:
            return AgentToolObservation(
                tool=tool,
                ok=False,
                summary=f"{tool} failed: {type(exc).__name__}",
                data={},
                error=str(exc) or type(exc).__name__,
            )

    def _search_documents(self, args: Dict[str, Any]) -> AgentToolObservation:
        query = str(args.get("query") or args.get("question") or "").strip()
        if not query:
            return AgentToolObservation(
                tool="search_documents",
                ok=False,
                summary="Search query is required.",
                data={"sources": []},
                error="missing_query",
            )

        top_k = _bounded_int(args.get("top_k"), default=5, lower=1, upper=12)
        strategy = str(args.get("strategy") or "vector").strip().lower()
        use_hyde = bool(args.get("use_hyde", False))

        if strategy == "layered":
            active_filters = self._filters_for_search(args)
            layered = retrieve_layered_context(
                query=query,
                top_k=top_k,
                filters=active_filters,
                primary_queries=_clean_string_list(args.get("primary_queries")),
                use_hyde=use_hyde,
                history_block=self.history_block,
            )
            layered = _filter_layered_sources_for_target(
                layered,
                expected_entity=str(args.get("expected_entity") or "").strip(),
                expected_document_ids=_clean_string_list(args.get("document_ids")) or [],
            )
            layered = filter_layered_sources_by_relevance(query, layered) or {}
            sources = _flatten_layered_sources(layered)
            return AgentToolObservation(
                tool="search_documents",
                ok=bool(sources),
                summary=f"Retrieved {len(sources)} primary source chunk(s) with layered search.",
                data={"sources": sources, "layered_sources": layered, "strategy": "layered", "top_k": top_k},
                error=None if sources else "no_sources",
            )

        if strategy == "hybrid":
            active_filters = self._filters_for_search(args)
            sources = retrieve_hybrid(
                query=query,
                top_k=top_k,
                filters=active_filters,
                use_hyde=use_hyde,
                history_block=self.history_block,
            )
            resolved_strategy = "hybrid"
        else:
            active_filters = self._filters_for_search(args)
            sources = retrieve_context(
                query=query,
                top_k=top_k,
                filters=active_filters,
                use_hyde=use_hyde,
                history_block=self.history_block,
            )
            resolved_strategy = "vector"
        expected_entity = str(args.get("expected_entity") or "").strip()
        expected_document_ids = _clean_string_list(args.get("document_ids")) or []
        sources = _filter_sources_for_target(
            sources,
            expected_entity=expected_entity,
            expected_document_ids=expected_document_ids,
        )
        sources = filter_sources_by_relevance(query, sources)

        return AgentToolObservation(
            tool="search_documents",
            ok=bool(sources),
            summary=f"Retrieved {len(sources)} source chunk(s) with {resolved_strategy} search.",
            data={"sources": sources, "strategy": resolved_strategy, "top_k": top_k},
            error=None if sources else "no_sources",
        )

    def _filters_for_search(self, args: Dict[str, Any]) -> Dict[str, Any]:
        filters = dict(self.filters)
        document_ids = _clean_string_list(args.get("document_ids"))
        if document_ids is not None:
            filters["document_ids"] = document_ids
        preferred_document_id = str(args.get("preferred_document_id") or "").strip()
        if preferred_document_id:
            filters["preferred_document_id"] = preferred_document_id
        return filters

    def _read_chunks(self, args: Dict[str, Any]) -> AgentToolObservation:
        chunks = args.get("chunks")
        if chunks is None:
            chunks = args.get("sources")
        if chunks is None:
            chunks = []
        if not isinstance(chunks, list):
            chunks = [chunks]
        return AgentToolObservation(
            tool="read_chunks",
            ok=bool(chunks),
            summary=f"Read {len(chunks)} chunk(s).",
            data={"chunks": chunks, "sources": chunks},
            error=None if chunks else "no_chunks",
        )

    def _get_graph_context(self, tool: str, args: Dict[str, Any]) -> AgentToolObservation:
        question = str(args.get("question") or args.get("query") or "").strip()
        if not question:
            return AgentToolObservation(
                tool=tool,
                ok=False,
                summary="Graph context question is required.",
                data={},
                error="missing_question",
            )

        limit = _bounded_int(args.get("limit"), default=10, lower=1, upper=30)
        max_triples = args.get("max_triples")
        if max_triples is not None:
            max_triples = _bounded_int(max_triples, default=limit, lower=1, upper=30)

        context = build_graph_context(
            question=question,
            filters=self.filters,
            hops=args.get("hops"),
            limit=limit,
            max_triples=max_triples,
        )
        has_context = bool((context.get("text") or "").strip() or context.get("edges"))
        if has_context:
            return AgentToolObservation(
                tool=tool,
                ok=True,
                summary=f"Found graph context with {len(context.get('edges') or [])} edge(s).",
                data={"graph": context},
            )

        error = str(context.get("skipped_reason") or "no_graph_context")
        return AgentToolObservation(
            tool=tool,
            ok=False,
            summary="No graph context available.",
            data={"graph": context},
            error=error,
        )

    def _summarize_evidence(self, args: Dict[str, Any]) -> AgentToolObservation:
        sources = args.get("sources")
        if sources is None:
            sources = args.get("chunks")
        source_list = sources if isinstance(sources, list) else []

        graph_context = args.get("graph_context") or args.get("graph") or {}
        graph_text = ""
        if isinstance(graph_context, dict):
            graph_text = str(graph_context.get("text") or "").strip()
        elif graph_context:
            graph_text = str(graph_context).strip()

        evidence_lines: List[str] = []
        for item in source_list[:3]:
            if not isinstance(item, dict):
                continue
            chunk_id = str(item.get("chunk_id") or item.get("id") or "chunk").strip()
            text = _truncate_words(str(item.get("text") or item.get("content") or "").strip(), 24)
            if text:
                evidence_lines.append(f"{chunk_id}: {text}")
        if graph_text:
            evidence_lines.append(f"graph: {_truncate_words(graph_text, 24)}")

        summary = " ".join(evidence_lines) if evidence_lines else "No evidence provided to summarize."
        return AgentToolObservation(
            tool="summarize_evidence",
            ok=True,
            summary=summary,
            data={"summary": summary, "source_count": len(source_list), "has_graph_context": bool(graph_text)},
        )


def _bounded_int(value: Any, *, default: int, lower: int, upper: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(lower, min(upper, parsed))


def _clean_string_list(value: Any) -> Optional[List[str]]:
    if not isinstance(value, list):
        return None
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or None


def _flatten_layered_sources(layers: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for layer_name in ("primary", "priors", "regulatory"):
        for item in layers.get(layer_name) or []:
            row = dict(item)
            row["agent_layer"] = layer_name
            output.append(row)
    return output


def _filter_layered_sources_for_target(
    layers: Dict[str, List[Dict[str, Any]]],
    *,
    expected_entity: str,
    expected_document_ids: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    return {
        layer_name: _filter_sources_for_target(
            list(rows or []),
            expected_entity=expected_entity if layer_name == "primary" else "",
            expected_document_ids=expected_document_ids if layer_name == "primary" else [],
        )
        for layer_name, rows in (layers or {}).items()
    }


def _filter_sources_for_target(
    sources: List[Dict[str, Any]],
    *,
    expected_entity: str,
    expected_document_ids: List[str],
) -> List[Dict[str, Any]]:
    expected_ids = {str(item).strip() for item in expected_document_ids or [] if str(item).strip()}
    expected_entity = str(expected_entity or "").strip()
    if not expected_ids and not expected_entity:
        return list(sources or [])

    output: List[Dict[str, Any]] = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        document_id = str(source.get("document_id") or "").strip()
        if expected_ids and document_id in expected_ids:
            output.append(source)
            continue
        if expected_entity and _source_mentions_entity(source, expected_entity):
            output.append(source)
    return output


def _source_mentions_entity(source: Dict[str, Any], entity: str) -> bool:
    tokens = _entity_tokens(entity)
    if not tokens:
        return False
    blob = " ".join(
        str(source.get(key) or "")
        for key in ("document_id", "document_title", "title", "source", "text", "content")
    ).lower()
    if not blob:
        return False
    normalized_entity = " ".join(tokens)
    if normalized_entity and normalized_entity in blob:
        return True
    blob_tokens = set(_entity_tokens(blob))
    return bool(blob_tokens) and set(tokens).issubset(blob_tokens)


def _entity_tokens(value: str) -> List[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", str(value or "")) if len(token) >= 2]


def _truncate_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip() + "..."


__all__ = ["AgentToolRegistry"]
