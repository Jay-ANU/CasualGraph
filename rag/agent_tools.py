"""Fixed tool registry for controlled hybrid agent evidence gathering."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from rag.agent_types import AgentToolObservation
from rag.graph_context import build_graph_context
from rag.retriever import retrieve_context, retrieve_hybrid, retrieve_layered_context


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
            layered = retrieve_layered_context(
                query=query,
                top_k=top_k,
                filters=self.filters,
                primary_queries=_clean_string_list(args.get("primary_queries")),
                use_hyde=use_hyde,
                history_block=self.history_block,
            )
            sources = _flatten_layered_sources(layered)
            return AgentToolObservation(
                tool="search_documents",
                ok=bool(sources),
                summary=f"Retrieved {len(sources)} primary source chunk(s) with layered search.",
                data={"sources": sources, "layered_sources": layered, "strategy": "layered", "top_k": top_k},
                error=None if sources else "no_sources",
            )

        if strategy == "hybrid":
            sources = retrieve_hybrid(
                query=query,
                top_k=top_k,
                filters=self.filters,
                use_hyde=use_hyde,
                history_block=self.history_block,
            )
            resolved_strategy = "hybrid"
        else:
            sources = retrieve_context(
                query=query,
                top_k=top_k,
                filters=self.filters,
                use_hyde=use_hyde,
                history_block=self.history_block,
            )
            resolved_strategy = "vector"

        return AgentToolObservation(
            tool="search_documents",
            ok=bool(sources),
            summary=f"Retrieved {len(sources)} source chunk(s) with {resolved_strategy} search.",
            data={"sources": sources, "strategy": resolved_strategy, "top_k": top_k},
            error=None if sources else "no_sources",
        )

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


def _truncate_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    return " ".join(words[:limit]).rstrip() + "..."


__all__ = ["AgentToolRegistry"]
