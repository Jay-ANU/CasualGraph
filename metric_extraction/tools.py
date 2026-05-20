"""Agent-callable tools over the structured ESG metric store.

Three tool functions, each returns a list of dicts with provenance (document_id,
chunk_id, evidence_text) so the agent can produce grounded citations:

    query_metric    — single entity, one or all years
    compare_metric  — multiple entities, one year, aligned
    metric_trend    — single entity, year range, time series

`get_tool_schemas()` returns OpenAI/DeepSeek-compatible function-call schemas,
ready to pass as `tools=...` when LLM tool_use lands.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from configs import settings as cfg
from metric_extraction.store import MetricStore, init_metric_store
from metric_extraction.taxonomy import Taxonomy, load_taxonomy


def _get_store() -> MetricStore:
    return init_metric_store(cfg.ESG_METRICS_DB_PATH)


def _get_taxonomy() -> Taxonomy:
    return load_taxonomy(cfg.ESG_METRICS_TAXONOMY_PATH)


def _project_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Trim DB-internal columns; keep what an agent needs to cite."""
    return {
        "metric_id": row.get("metric_id"),
        "value": row.get("value"),
        "unit": row.get("unit"),
        "year": row.get("year"),
        "year_qualifier": row.get("year_qualifier"),
        "scope_qualifier": row.get("scope_qualifier"),
        "entity_hint": row.get("entity_hint"),
        "confidence": row.get("confidence"),
        "document_id": row.get("document_id"),
        "chunk_id": row.get("chunk_id"),
        "evidence_text": row.get("evidence_text"),
        "raw_value": row.get("raw_value"),
        "raw_unit": row.get("raw_unit"),
    }


def query_metric(
    metric_id: str,
    *,
    entity_hint: Optional[str] = None,
    year: Optional[int] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    scope_qualifier: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Look up reported values for one metric, optionally filtered by entity / year / scope."""
    if year is not None and year_min is None and year_max is None:
        year_min = year
        year_max = year
    threshold = float(min_confidence) if min_confidence is not None else cfg.ESG_METRICS_MIN_CONFIDENCE
    rows = _get_store().query(
        metric_id=metric_id,
        entity_hint=entity_hint,
        year_min=year_min,
        year_max=year_max,
        scope_qualifier=scope_qualifier,
        min_confidence=threshold,
        limit=limit,
    )
    return [_project_row(row) for row in rows]


def compare_metric(
    metric_id: str,
    entity_hints: List[str],
    *,
    year: int,
    scope_qualifier: Optional[str] = None,
    min_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    """Aligned single-year comparison across entities.

    Returns:
        {
          "metric_id": ...,
          "year": ...,
          "rows": [<one per entity>],
          "missing": [<entity_hints with no data>],
        }
    """
    threshold = float(min_confidence) if min_confidence is not None else cfg.ESG_METRICS_MIN_CONFIDENCE
    store = _get_store()
    rows: List[Dict[str, Any]] = []
    missing: List[str] = []
    for hint in entity_hints:
        matches = store.query(
            metric_id=metric_id,
            entity_hint=hint,
            year_min=year,
            year_max=year,
            scope_qualifier=scope_qualifier,
            min_confidence=threshold,
            limit=1,
        )
        if matches:
            rows.append(_project_row(matches[0]))
        else:
            missing.append(hint)
    return {"metric_id": metric_id, "year": year, "rows": rows, "missing": missing}


def metric_trend(
    metric_id: str,
    entity_hint: str,
    *,
    year_min: int,
    year_max: int,
    scope_qualifier: Optional[str] = None,
    min_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    """Time series for one entity over [year_min, year_max].

    Returns:
        {
          "metric_id": ...,
          "entity_hint": ...,
          "rows": [<one per year, ordered ascending>],
          "missing_years": [<years with no data>],
        }
    """
    threshold = float(min_confidence) if min_confidence is not None else cfg.ESG_METRICS_MIN_CONFIDENCE
    raw = _get_store().query(
        metric_id=metric_id,
        entity_hint=entity_hint,
        year_min=year_min,
        year_max=year_max,
        scope_qualifier=scope_qualifier,
        min_confidence=threshold,
        limit=200,
    )
    by_year: Dict[int, Dict[str, Any]] = {}
    for row in raw:
        year_value = row.get("year")
        if year_value is None:
            continue
        existing = by_year.get(int(year_value))
        if not existing or float(existing.get("confidence") or 0) < float(row.get("confidence") or 0):
            by_year[int(year_value)] = _project_row(row)
    ordered = [by_year[y] for y in sorted(by_year)]
    expected_years = set(range(year_min, year_max + 1))
    missing_years = sorted(expected_years - set(by_year.keys()))
    return {
        "metric_id": metric_id,
        "entity_hint": entity_hint,
        "rows": ordered,
        "missing_years": missing_years,
    }


def list_available_metrics() -> List[Dict[str, Any]]:
    """Return the taxonomy in a shape the agent can show users."""
    taxonomy = _get_taxonomy()
    out: List[Dict[str, Any]] = []
    for metric_id in taxonomy.all_metric_ids():
        spec = taxonomy.get(metric_id)
        if spec is None:
            continue
        out.append({
            "metric_id": metric_id,
            "display_name_en": spec.display_name_en,
            "display_name_zh": spec.display_name_zh,
            "canonical_unit": spec.canonical_unit,
            "category": spec.category,
            "scope_qualifiers": spec.scope_qualifiers,
            "description": spec.description,
        })
    return out


def get_tool_schemas() -> List[Dict[str, Any]]:
    """OpenAI/DeepSeek-compatible function schemas for these tools.

    Pass to `chat.completions.create(tools=...)` to enable LLM tool_use.
    The metric_id enum is sourced from the live taxonomy so the model is
    constrained to canonical IDs.
    """
    metric_ids = _get_taxonomy().all_metric_ids()
    return [
        {
            "type": "function",
            "function": {
                "name": "query_metric",
                "description": (
                    "Look up reported values for one ESG metric, for one entity, optionally "
                    "filtered by year and scope. Use when the question asks for a specific "
                    "number (e.g. 'Company X's Scope 1 emissions in 2023'). Do NOT use for "
                    "cross-entity comparisons (use compare_metric) or multi-year trends "
                    "(use metric_trend)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric_id": {"type": "string", "enum": metric_ids},
                        "entity_hint": {
                            "type": "string",
                            "description": "Company or organization name. Substring match, case-insensitive.",
                        },
                        "year": {"type": "integer"},
                        "year_min": {"type": "integer"},
                        "year_max": {"type": "integer"},
                        "scope_qualifier": {"type": "string"},
                        "min_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["metric_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compare_metric",
                "description": (
                    "Compare ONE metric across MULTIPLE entities for ONE year. "
                    "Use when the user asks 'compare A and B on X' or 'rank these companies by X'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric_id": {"type": "string", "enum": metric_ids},
                        "entity_hints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 2,
                        },
                        "year": {"type": "integer"},
                        "scope_qualifier": {"type": "string"},
                        "min_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                    "required": ["metric_id", "entity_hints", "year"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "metric_trend",
                "description": (
                    "Time-series of ONE metric for ONE entity over a year range. "
                    "Use when the user asks about 'trend' / 'change over time' / 'history'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric_id": {"type": "string", "enum": metric_ids},
                        "entity_hint": {"type": "string"},
                        "year_min": {"type": "integer"},
                        "year_max": {"type": "integer"},
                        "scope_qualifier": {"type": "string"},
                        "min_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                    "required": ["metric_id", "entity_hint", "year_min", "year_max"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_available_metrics",
                "description": "List all metrics in the taxonomy. Use when the user asks 'what can you tell me' or you need to disambiguate which metric to query.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


TOOL_DISPATCH = {
    "query_metric": query_metric,
    "compare_metric": compare_metric,
    "metric_trend": metric_trend,
    "list_available_metrics": list_available_metrics,
}


def dispatch_tool(name: str, arguments: Dict[str, Any]) -> Any:
    """Invoke a tool by name with kwargs. Raises KeyError on unknown tool."""
    fn = TOOL_DISPATCH[name]
    return fn(**arguments)
