"""Utility helpers for ESG extraction output cleanup."""

from __future__ import annotations

import json
import re
from typing import Any, Dict


def parse_json_safely(raw_text: str) -> Dict[str, Any]:
    """Parse model output into JSON with safe fallbacks."""
    text = (raw_text or "").strip()
    text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```\s*$", "", text)
    if not text:
        return {"entities": [], "relations": [], "raw": raw_text}

    try:
        return json.loads(text)
    except Exception as exc:
        first_error = exc

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            return json.loads(candidate)
        except Exception as exc:
            first_error = exc

    print(f"[extractor] JSON parse failed: {type(first_error).__name__}: {first_error}")
    print(f"[extractor] raw output (first 300): {text[:300]!r}")
    return {"entities": [], "relations": [], "raw": raw_text}


def normalize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Guarantee the extraction result contains list-valued entities and relations."""
    if not isinstance(result, dict):
        return {"entities": [], "relations": [], "raw": str(result)}

    normalized = dict(result)

    for key in ("entities", "relations"):
        value = normalized.get(key, [])
        if isinstance(value, list):
            normalized[key] = value
        elif value is None:
            normalized[key] = []
        else:
            normalized[key] = [value]

    normalized.setdefault("entities", [])
    normalized.setdefault("relations", [])
    normalized["relations"] = [_normalize_relation(relation) for relation in normalized["relations"]]
    return normalized


def _normalize_relation(relation: Any) -> Dict[str, Any]:
    """Accept both prompt-facing and graph-facing relation field names."""
    if not isinstance(relation, dict):
        return {"source_entity": "", "target_entity": "", "relation_type": "related_to", "evidence": str(relation)}

    normalized = dict(relation)
    subject = normalized.get("source_entity") or normalized.get("subject") or normalized.get("source")
    obj = normalized.get("target_entity") or normalized.get("object") or normalized.get("target")
    predicate = normalized.get("relation_type") or normalized.get("predicate") or normalized.get("relation") or normalized.get("type")

    if subject is not None:
        normalized["source_entity"] = subject
        normalized.setdefault("subject", subject)
    if obj is not None:
        normalized["target_entity"] = obj
        normalized.setdefault("object", obj)
    if predicate is not None:
        normalized["relation_type"] = predicate
        normalized.setdefault("predicate", predicate)

    normalized.setdefault("relation_type", "related_to")
    return normalized
