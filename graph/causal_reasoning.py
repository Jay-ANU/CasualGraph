"""Causal path queries over Neo4j CAUSAL_LINK relationships."""

from __future__ import annotations

from typing import Any, Dict, List

from graph.graph_utils import normalize_entity_name


class CausalReasoner:
    def __init__(self, store):
        self.store = store

    def backward_chain(self, target_entity: str, depth: int = 3, limit: int = 20) -> Dict:
        """Why did X happen? (cause)-[:CAUSAL_LINK*1..depth]->(X)."""
        depth = _bounded_depth(depth)
        limit = _bounded_limit(limit)

        def operation():
            with self.store._session() as session:
                rows = session.run(
                    f"""
                    MATCH (target:Entity)
                    WHERE target.id IN $entities
                       OR toLower(target.name) IN $entities_lower
                       OR toLower(target.normalized_name) IN $entities_lower
                       OR any(term IN $entities_lower WHERE toLower(target.id) CONTAINS term OR toLower(target.name) CONTAINS term OR toLower(target.normalized_name) CONTAINS term)
                    MATCH p=(:Entity)-[:CAUSAL_LINK*1..{depth}]->(target)
                    RETURN
                      [n IN nodes(p) | n{{.id, .name, .type}}] AS nodes,
                      [r IN relationships(p) | {{
                        source: startNode(r).id,
                        target: endNode(r).id,
                        causal_type: r.causal_type,
                        polarity: r.polarity,
                        confidence: r.confidence,
                        evidence: r.evidence,
                        chunk_id: r.chunk_id,
                        document_id: r.document_id
                      }}] AS edges
                    LIMIT $limit
                    """,
                    entities=_entity_variants(target_entity),
                    entities_lower=[item.lower() for item in _entity_variants(target_entity)],
                    limit=limit,
                ).data()
                return rows

        rows = self.store._run_with_reconnect(operation)
        return {"query": {"type": "backward", "entity": target_entity, "depth": depth, "limit": limit}, "paths": _format_paths(rows)}

    def forward_chain(self, source_entity: str, depth: int = 3, limit: int = 20) -> Dict:
        """If X, then? (X)-[:CAUSAL_LINK*1..depth]->(effect)."""
        depth = _bounded_depth(depth)
        limit = _bounded_limit(limit)

        def operation():
            with self.store._session() as session:
                rows = session.run(
                    f"""
                    MATCH (source:Entity)
                    WHERE source.id IN $entities
                       OR toLower(source.name) IN $entities_lower
                       OR toLower(source.normalized_name) IN $entities_lower
                       OR any(term IN $entities_lower WHERE toLower(source.id) CONTAINS term OR toLower(source.name) CONTAINS term OR toLower(source.normalized_name) CONTAINS term)
                    MATCH p=(source)-[:CAUSAL_LINK*1..{depth}]->(:Entity)
                    RETURN
                      [n IN nodes(p) | n{{.id, .name, .type}}] AS nodes,
                      [r IN relationships(p) | {{
                        source: startNode(r).id,
                        target: endNode(r).id,
                        causal_type: r.causal_type,
                        polarity: r.polarity,
                        confidence: r.confidence,
                        evidence: r.evidence,
                        chunk_id: r.chunk_id,
                        document_id: r.document_id
                      }}] AS edges
                    LIMIT $limit
                    """,
                    entities=_entity_variants(source_entity),
                    entities_lower=[item.lower() for item in _entity_variants(source_entity)],
                    limit=limit,
                ).data()
                return rows

        rows = self.store._run_with_reconnect(operation)
        return {"query": {"type": "forward", "entity": source_entity, "depth": depth, "limit": limit}, "paths": _format_paths(rows)}

    def shortest_path(self, source: str, target: str, max_depth: int = 5) -> Dict:
        """How does X affect Y? shortestPath((X)-[:CAUSAL_LINK*..max_depth]->(Y))."""
        max_depth = _bounded_depth(max_depth, maximum=5)

        def operation():
            with self.store._session() as session:
                rows = session.run(
                    f"""
                    MATCH (source:Entity), (target:Entity)
                    WHERE (source.id IN $sources
                       OR toLower(source.name) IN $sources_lower
                       OR toLower(source.normalized_name) IN $sources_lower
                       OR any(term IN $sources_lower WHERE toLower(source.id) CONTAINS term OR toLower(source.name) CONTAINS term OR toLower(source.normalized_name) CONTAINS term))
                      AND (target.id IN $targets
                       OR toLower(target.name) IN $targets_lower
                       OR toLower(target.normalized_name) IN $targets_lower
                       OR any(term IN $targets_lower WHERE toLower(target.id) CONTAINS term OR toLower(target.name) CONTAINS term OR toLower(target.normalized_name) CONTAINS term))
                    MATCH p=shortestPath((source)-[:CAUSAL_LINK*..{max_depth}]->(target))
                    RETURN
                      [n IN nodes(p) | n{{.id, .name, .type}}] AS nodes,
                      [r IN relationships(p) | {{
                        source: startNode(r).id,
                        target: endNode(r).id,
                        causal_type: r.causal_type,
                        polarity: r.polarity,
                        confidence: r.confidence,
                        evidence: r.evidence,
                        chunk_id: r.chunk_id,
                        document_id: r.document_id
                      }}] AS edges
                    LIMIT 1
                    """,
                    sources=_entity_variants(source),
                    sources_lower=[item.lower() for item in _entity_variants(source)],
                    targets=_entity_variants(target),
                    targets_lower=[item.lower() for item in _entity_variants(target)],
                ).data()
                return rows

        rows = self.store._run_with_reconnect(operation)
        return {"query": {"type": "path", "source": source, "target": target, "max_depth": max_depth}, "paths": _format_paths(rows)}


def _format_paths(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [_format_path(row.get("nodes") or [], row.get("edges") or []) for row in rows]


def _format_path(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    product = 1.0
    negative_count = 0
    has_zero = False
    formatted_edges = []

    for edge in edges:
        confidence = _safe_float(edge.get("confidence"), 0.75)
        polarity = int(_safe_float(edge.get("polarity"), 0))
        product *= confidence
        if polarity < 0:
            negative_count += 1
        if polarity == 0:
            has_zero = True
        formatted_edges.append(
            {
                "source": edge.get("source"),
                "target": edge.get("target"),
                "causal_type": edge.get("causal_type") or "related_to",
                "polarity": polarity,
                "confidence": confidence,
                "evidence": edge.get("evidence") or "",
                "chunk_id": edge.get("chunk_id") or "",
                "document_id": edge.get("document_id") or "",
            }
        )

    net_polarity = 0 if has_zero else (-1 if negative_count % 2 else 1)
    path_score = product
    return {
        "nodes": [
            {
                "id": node.get("id"),
                "name": node.get("name") or node.get("id"),
                "type": node.get("type") or "Entity",
            }
            for node in nodes
        ],
        "edges": formatted_edges,
        "length": len(formatted_edges),
        "path_score": path_score,
        "net_polarity": net_polarity,
    }


def _bounded_depth(value: int, maximum: int = 4) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = 3
    return max(1, min(parsed, maximum))


def _entity_variants(value: str) -> List[str]:
    normalized = normalize_entity_name(value)
    variants = [normalized]
    if "_" in normalized:
        variants.append(normalize_entity_name(normalized.replace("_", " ")))
    return list(dict.fromkeys(item for item in variants if item))


def _bounded_limit(value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = 20
    return max(1, min(parsed, 100))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default
