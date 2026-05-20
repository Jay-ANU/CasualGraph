"""Utility functions for graph normalization and deduplication."""

from __future__ import annotations

from typing import Dict, List
import re


def normalize_entity_name(name: str) -> str:
    """Normalize entity names to stable graph ids."""
    normalized = re.sub(r"\s+", " ", (name or "").strip())
    return normalized


def infer_entity_type(entity) -> str:
    """Infer a coarse entity type from a string or dict entity payload."""
    if isinstance(entity, dict):
        entity_type = entity.get("type") or entity.get("entity_type")
        if entity_type:
            return str(entity_type)
    return "Entity"


def deduplicate_nodes(nodes: List[Dict]) -> List[Dict]:
    """Deduplicate nodes by id."""
    seen = {}
    for node in nodes:
        seen[node["id"]] = node
    return list(seen.values())


def deduplicate_edges(edges: List[Dict]) -> List[Dict]:
    """Deduplicate edges by source-target-relation."""
    seen = {}
    for edge in edges:
        key = (edge["source"], edge["target"], edge["relation"])
        seen[key] = edge
    return list(seen.values())
