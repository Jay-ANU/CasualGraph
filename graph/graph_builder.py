"""Build a lightweight graph JSON from ESG extraction results."""

from __future__ import annotations

from typing import Dict, List

from graph.graph_utils import deduplicate_edges, deduplicate_nodes, infer_entity_type, normalize_entity_name


def build_graph_from_extractions(extractions: List[Dict]) -> Dict:
    """Convert extraction results into deduplicated node/edge graph JSON."""
    nodes: List[Dict] = []
    edges: List[Dict] = []

    for row in extractions:
        chunk_id = row.get("chunk_id") or row.get("id") or ""
        entities = row.get("entities", []) or []
        relations = row.get("relations", []) or []
        entity_lookup = _build_entity_lookup(entities)

        for entity in entities:
            if isinstance(entity, str):
                entity_name = normalize_entity_name(entity)
                if entity_name:
                    nodes.append({"id": entity_name, "type": "Entity", "properties": {"display_name": entity_name}})
            elif isinstance(entity, dict):
                entity_name = normalize_entity_name(
                    entity.get("name") or entity.get("entity") or entity.get("text") or entity.get("id") or ""
                )
                if entity_name:
                    properties = {k: v for k, v in entity.items() if k not in {"name", "entity", "text", "id", "type", "entity_type"}}
                    properties["display_name"] = entity.get("name") or entity.get("entity") or entity.get("text") or entity_name
                    if entity.get("id"):
                        properties["local_entity_id"] = entity.get("id")
                    nodes.append({"id": entity_name, "type": infer_entity_type(entity), "properties": properties})

        for relation in relations:
            if isinstance(relation, str):
                if len(entities) >= 2:
                    source = _entity_label(entities[0])
                    target = _entity_label(entities[1])
                    if source and target:
                        edges.append(
                            {
                                "source": source,
                                "target": target,
                                "relation": relation,
                                "properties": {"chunk_id": chunk_id},
                            }
                        )
                continue

            if not isinstance(relation, dict):
                continue

            source = _resolve_relation_endpoint(
                relation.get("subject_id")
                or relation.get("source_id")
                or relation.get("from")
                or relation.get("subject")
                or relation.get("source_entity")
                or relation.get("source")
                or relation.get("entity_1")
                or "",
                entity_lookup,
            )
            target = _resolve_relation_endpoint(
                relation.get("object_id")
                or relation.get("target_id")
                or relation.get("to")
                or relation.get("object")
                or relation.get("target_entity")
                or relation.get("target")
                or relation.get("entity_2")
                or "",
                entity_lookup,
            )
            predicate = (
                relation.get("relation")
                or relation.get("relation_type")
                or relation.get("predicate")
                or relation.get("type")
                or "related_to"
            )
            if not source or not target:
                continue

            properties = {k: v for k, v in relation.items() if k not in {"subject", "source_entity", "source", "entity_1", "object", "target_entity", "target", "entity_2", "relation", "relation_type", "predicate", "type"}}
            properties["chunk_id"] = chunk_id
            edges.append({"source": source, "target": target, "relation": predicate, "properties": properties})

    return {"nodes": deduplicate_nodes(nodes), "edges": deduplicate_edges(edges)}


def _build_entity_lookup(entities: List) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for entity in entities:
        if isinstance(entity, str):
            normalized = normalize_entity_name(entity)
            if normalized:
                lookup[normalized] = normalized
            continue
        if not isinstance(entity, dict):
            continue
        resolved_name = normalize_entity_name(
            entity.get("name") or entity.get("entity") or entity.get("text") or entity.get("id") or ""
        )
        if not resolved_name:
            continue
        for key in (entity.get("id"), entity.get("name"), entity.get("entity"), entity.get("text")):
            normalized_key = normalize_entity_name(str(key or ""))
            if normalized_key:
                lookup[normalized_key] = resolved_name
    return lookup


def _resolve_relation_endpoint(value, entity_lookup: Dict[str, str]) -> str:
    normalized = normalize_entity_name(str(value or ""))
    if not normalized:
      return ""
    return entity_lookup.get(normalized, normalized)


def _entity_label(entity) -> str:
    if isinstance(entity, str):
        return normalize_entity_name(entity)
    if isinstance(entity, dict):
        return normalize_entity_name(entity.get("name") or entity.get("entity") or entity.get("text") or "")
    return ""
