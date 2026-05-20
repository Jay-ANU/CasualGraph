"""Build Neo4j-backed graph context for the RAG answering pipeline."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from configs.settings import (
    RAG_GRAPH_CONTEXT_HOPS,
    RAG_GRAPH_CONTEXT_LIMIT,
    RAG_GRAPH_CONTEXT_MAX_TRIPLES,
    RAG_USE_GRAPH_CONTEXT,
)


def graph_context_enabled() -> bool:
    return bool(RAG_USE_GRAPH_CONTEXT)


def build_graph_context(
    question: str,
    filters: Optional[Dict[str, Any]] = None,
    hops: Optional[int] = None,
    limit: Optional[int] = None,
    max_triples: Optional[int] = None,
) -> Dict[str, Any]:
    """Return a textual graph context plus structured nodes/edges for a question.

    The result has the shape:
        {
            "text": "<formatted triples or empty>",
            "matched_entities": [...],
            "nodes": [...],
            "edges": [...],
            "skipped_reason": "<reason or None>",
        }
    Callers can pass ``text`` to the LLM and ``nodes``/``edges`` back to the API.
    """
    result: Dict[str, Any] = {
        "text": "",
        "matched_entities": [],
        "nodes": [],
        "edges": [],
        "skipped_reason": None,
    }

    if not graph_context_enabled():
        result["skipped_reason"] = "disabled"
        return result

    try:
        from graph.neo4j_store import get_neo4j_store, neo4j_enabled
    except Exception as exc:
        result["skipped_reason"] = f"import_error: {type(exc).__name__}"
        return result

    if not neo4j_enabled():
        result["skipped_reason"] = "neo4j_not_configured"
        return result

    store = get_neo4j_store()
    if store is None:
        result["skipped_reason"] = "neo4j_unavailable"
        return result

    hop_count = hops if hops is not None else RAG_GRAPH_CONTEXT_HOPS
    match_limit = limit if limit is not None else RAG_GRAPH_CONTEXT_LIMIT
    triple_limit = max_triples if max_triples is not None else RAG_GRAPH_CONTEXT_MAX_TRIPLES

    try:
        t0 = time.perf_counter()
        subgraph = store.find_relevant_subgraph(
            question=question,
            limit=match_limit,
            hops=hop_count,
            filters=filters,
        )
        match_ms = (time.perf_counter() - t0) * 1000
    except Exception as exc:
        result["skipped_reason"] = f"query_failed: {type(exc).__name__}: {exc}"
        return result

    format_started = time.perf_counter()
    matched = subgraph.get("matched_entities") or []
    nodes = subgraph.get("nodes") or []
    edges = subgraph.get("edges") or []

    if not matched:
        result["skipped_reason"] = "no_entity_match"
        _log_graph_timing(match_ms=match_ms, format_started=format_started, matched=matched, nodes=nodes, edges=edges)
        return result

    node_label = {
        node.get("id"): (node.get("name") or node.get("normalized_name") or node.get("id") or "?")
        for node in nodes
    }
    matched_ids = {row.get("id") for row in matched if row.get("id")}

    ranked_edges = sorted(
        edges,
        key=lambda edge: (
            -_endpoint_match_score(edge, matched_ids),
            -_safe_float(edge.get("confidence"), 0.0),
        ),
    )

    triples: List[str] = []
    used_edges: List[Dict[str, Any]] = []
    seen_keys = set()
    for edge in ranked_edges:
        if len(triples) >= triple_limit:
            break
        source_id = edge.get("source")
        target_id = edge.get("target")
        relation = (edge.get("relation_type") or "related_to").strip() or "related_to"
        if not source_id or not target_id:
            continue
        key = (source_id, target_id, relation, edge.get("chunk_id"))
        if key in seen_keys:
            continue
        seen_keys.add(key)

        source_label = node_label.get(source_id, source_id)
        target_label = node_label.get(target_id, target_id)
        confidence = _safe_float(edge.get("confidence"), 0.0)
        chunk_id = (edge.get("chunk_id") or "").strip()
        evidence = (edge.get("evidence") or "").strip()

        marker = f"G{len(triples) + 1}"
        meta_bits = []
        if confidence:
            meta_bits.append(f"conf={confidence:.2f}")
        if chunk_id:
            meta_bits.append(f"chunk={chunk_id}")
        meta = f" ({', '.join(meta_bits)})" if meta_bits else ""

        line = f"[{marker}] ({source_label}) --{relation}--> ({target_label}){meta}"
        if evidence:
            line += f"\n    evidence: {_truncate(evidence, 200)}"
        triples.append(line)
        used_edges.append(edge)

    if not triples:
        result["skipped_reason"] = "no_edges"
        result["matched_entities"] = matched
        result["nodes"] = nodes
        _log_graph_timing(match_ms=match_ms, format_started=format_started, matched=matched, nodes=nodes, edges=edges)
        return result

    result["text"] = "\n".join(triples)
    result["matched_entities"] = matched
    result["nodes"] = nodes
    result["edges"] = used_edges
    _log_graph_timing(match_ms=match_ms, format_started=format_started, matched=matched, nodes=nodes, edges=used_edges)
    return result


def _endpoint_match_score(edge: Dict[str, Any], matched_ids: set) -> int:
    score = 0
    if edge.get("source") in matched_ids:
        score += 1
    if edge.get("target") in matched_ids:
        score += 1
    return score


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _log_graph_timing(
    *,
    match_ms: float,
    format_started: float,
    matched: List[Dict[str, Any]],
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> None:
    format_ms = (time.perf_counter() - format_started) * 1000
    print(
        f"[rag.graph.timing] match_ms={match_ms:.0f} format_ms={format_ms:.0f} "
        f"entities={len(matched)} nodes={len(nodes)} edges={len(edges)}"
    )
