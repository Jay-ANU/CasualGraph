"""Lightweight source relevance gating for retrieved evidence."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from configs.settings import RAG_MIN_SOURCE_RELEVANCE


_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}")
_STOP_WORDS = {
    "about",
    "across",
    "all",
    "also",
    "and",
    "are",
    "based",
    "compare",
    "comparison",
    "document",
    "documents",
    "does",
    "evidence",
    "explain",
    "for",
    "from",
    "how",
    "into",
    "report",
    "reports",
    "show",
    "that",
    "the",
    "their",
    "these",
    "this",
    "those",
    "uploaded",
    "what",
    "when",
    "where",
    "which",
    "with",
}


def source_relevance_score(query: str, source_text: str) -> Optional[float]:
    terms = _query_terms(query)
    if not terms:
        return None
    haystack = str(source_text or "").lower()
    matched = sum(1 for term in terms if term in haystack)
    return matched / len(terms)


def annotate_source_relevance(query: str, source: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(source)
    score = source_relevance_score(query, str(row.get("text") or row.get("content") or ""))
    if score is not None:
        row["relevance_score"] = round(score, 4)
    return row


def filter_sources_by_relevance(
    query: str,
    sources: List[Dict[str, Any]],
    *,
    min_score: Optional[float] = None,
) -> List[Dict[str, Any]]:
    threshold = RAG_MIN_SOURCE_RELEVANCE if min_score is None else max(0.0, min(1.0, float(min_score)))
    output: List[Dict[str, Any]] = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        row = annotate_source_relevance(query, source)
        score = row.get("relevance_score")
        if score is None or float(score) >= threshold:
            output.append(row)
    return output


def filter_layered_sources_by_relevance(
    query: str,
    layered_context: Optional[Dict[str, List[Dict[str, Any]]]],
    *,
    min_score: Optional[float] = None,
) -> Optional[Dict[str, List[Dict[str, Any]]]]:
    if not isinstance(layered_context, dict):
        return layered_context
    return {
        layer: filter_sources_by_relevance(query, list(rows or []), min_score=min_score)
        for layer, rows in layered_context.items()
    }


def _query_terms(query: str) -> List[str]:
    seen = set()
    terms: List[str] = []
    for raw in _TOKEN_PATTERN.findall(str(query or "")):
        term = raw.strip().lower()
        if len(term) < 2 or term in _STOP_WORDS or term in seen:
            continue
        terms.append(term)
        seen.add(term)
    return terms
