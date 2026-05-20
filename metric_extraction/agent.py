"""Pattern-match metric agent — a placeholder for real LLM tool_use.

This module exists so the eval harness can exercise the metric tool path
end-to-end before LLM tool_use is wired in. It maps a natural-language
question to a tool call using simple regex / alias matching.

Replace `dispatch(question)` with an LLM tool_use call when ready; the
return shape (`{answer, citations, tool_calls}`) is identical, so eval
cases continue to pass.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from metric_extraction.taxonomy import Taxonomy, load_taxonomy
from metric_extraction.tools import (
    compare_metric,
    list_available_metrics,
    metric_trend,
    query_metric,
)
from configs import settings as cfg


_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")
_YEAR_RANGE_PATTERN = re.compile(r"\b((?:19|20)\d{2})\s*(?:-|to|–|—|至)\s*((?:19|20)\d{2})\b")
_COMPARE_KEYWORDS = ["compare", " vs ", " vs.", "versus", "compared to", "对比", "比较", "相比"]
_TREND_KEYWORDS = ["trend", "over time", "history", "historical", "year-over-year", "yoy", "趋势", "历年", "逐年", "近几年"]
_LIST_KEYWORDS = ["what metrics", "which metrics", "available metrics", "list metrics", "支持哪些", "有哪些指标"]

# Sentence-starter capitals to drop when scanning for entity names.
_STOP_STARTERS = {
    "What", "How", "Which", "When", "Where", "Why", "Who",
    "Did", "Does", "Do", "Is", "Are", "Was", "Were",
    "Has", "Have", "Had", "Tell", "Show", "List", "Compare",
    "Scope", "GHG", "CO2", "ESG",  # metric words capitalized in some questions
}
_CAP_RUN = re.compile(r"(?<![A-Za-z])([A-Z][A-Za-z0-9&]*(?:\s+[A-Z][A-Za-z0-9&]*)*)")


def _detect_entity(question: str) -> Optional[str]:
    """Best-effort: longest run of capitalized tokens, after stripping
    sentence-starter / metric words.
    """
    stripped = re.sub(r"'s\b", "", question)
    candidates: List[str] = []
    for match in _CAP_RUN.findall(stripped):
        words = match.split()
        while words and words[0] in _STOP_STARTERS:
            words = words[1:]
        while words and words[-1] in _STOP_STARTERS:
            words = words[:-1]
        if words:
            candidates.append(" ".join(words))
    return max(candidates, key=len) if candidates else None


def _detect_metric(question: str, taxonomy: Taxonomy) -> Optional[str]:
    """Return the best-matching metric_id by alias substring, or None."""
    lower = question.lower()
    best: Tuple[int, Optional[str]] = (0, None)
    for metric_id in taxonomy.all_metric_ids():
        spec = taxonomy.get(metric_id)
        if spec is None:
            continue
        for alias in spec.aliases:
            alias_l = alias.lower()
            if alias_l and alias_l in lower:
                # Longer alias wins — "scope 1 emissions" beats "scope 1".
                if len(alias_l) > best[0]:
                    best = (len(alias_l), metric_id)
    return best[1]


def _detect_year_range(question: str) -> Tuple[Optional[int], Optional[int]]:
    range_match = _YEAR_RANGE_PATTERN.search(question)
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        return (min(start, end), max(start, end))
    years = [int(m.group(0)) for m in _YEAR_PATTERN.finditer(question)]
    if len(years) >= 2:
        return (min(years), max(years))
    if years:
        return (years[0], years[0])
    return (None, None)


def _split_compare_entities(question: str) -> List[str]:
    """Heuristic entity splitter for 'compare A and B' / 'A vs B'.
    Each split is then passed through _detect_entity to strip trailing prose
    like 'XYZ Industries: Scope 2 emissions in 2023' → 'XYZ Industries'.
    """
    raw_candidates: List[str] = []
    lower = question.lower()
    for delim in [" vs ", " vs.", " versus ", " 对比 ", " 比较 ", " 与 "]:
        if delim in lower:
            parts = re.split(re.escape(delim), question, flags=re.IGNORECASE)
            if len(parts) >= 2:
                raw_candidates = [p.strip(" .,?") for p in parts if p.strip()]
                break
    if not raw_candidates:
        match = re.search(r"compare\s+(.+?)\s+and\s+(.+?)(?:\s+on|\s+for|\s+by|\.|$)", question, re.IGNORECASE)
        if match:
            raw_candidates = [match.group(1).strip(), match.group(2).strip()]
    cleaned: List[str] = []
    for raw in raw_candidates:
        if not raw:
            continue
        ent = _detect_entity(raw)
        cleaned.append(ent if ent else raw[:80])
    return [c for c in cleaned if c]


def _format_query_answer(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "No reported value matched the requested metric and filters in the corpus."
    parts = []
    for row in rows[:5]:
        parts.append(
            f"- {row['entity_hint'] or 'Unknown entity'} ({row.get('year')}): "
            f"{row['value']:,g} {row['unit']}"
            + (f" [{row['scope_qualifier']}]" if row.get("scope_qualifier") else "")
            + f" — confidence {row['confidence']:.2f}"
        )
    return "\n".join(parts)


def _format_compare_answer(result: Dict[str, Any]) -> str:
    lines = [f"Comparison of {result['metric_id']} for year {result['year']}:"]
    for row in result["rows"]:
        lines.append(
            f"- {row['entity_hint']}: {row['value']:,g} {row['unit']} "
            f"(confidence {row['confidence']:.2f})"
        )
    if result["missing"]:
        lines.append(f"No data for: {', '.join(result['missing'])}")
    return "\n".join(lines)


def _format_trend_answer(result: Dict[str, Any]) -> str:
    if not result["rows"]:
        return f"No trend data found for {result['entity_hint']}."
    lines = [f"Trend of {result['metric_id']} for {result['entity_hint']}:"]
    for row in result["rows"]:
        lines.append(f"- {row['year']}: {row['value']:,g} {row['unit']}")
    if result.get("missing_years"):
        lines.append(f"Missing years: {result['missing_years']}")
    return "\n".join(lines)


def _format_list_answer(metrics: List[Dict[str, Any]]) -> str:
    return "Available metrics:\n" + "\n".join(
        f"- {m['metric_id']} ({m['canonical_unit']}, {m['category']})"
        for m in metrics
    )


def _extract_citations(rows: List[Dict[str, Any]]) -> List[str]:
    return list({row["document_id"] for row in rows if row.get("document_id")})


def dispatch(question: str) -> Dict[str, Any]:
    """Map a natural-language question to a tool call and execute it.

    This is a deliberately simple pattern matcher. It exists to let the
    eval harness exercise the structured-metric path before LLM tool_use
    is integrated. Real users get LLM-driven dispatch later; the contract
    (return shape) is identical so eval cases stay valid.
    """
    taxonomy = load_taxonomy(cfg.ESG_METRICS_TAXONOMY_PATH)
    lower = question.lower()
    tool_calls: List[Dict[str, Any]] = []

    # --- list metrics intent ---
    if any(kw in lower for kw in _LIST_KEYWORDS):
        metrics = list_available_metrics()
        tool_calls.append({"name": "list_available_metrics", "arguments": {}, "result": metrics})
        return {
            "answer": _format_list_answer(metrics),
            "citations": [],
            "tool_calls": tool_calls,
        }

    metric_id = _detect_metric(question, taxonomy)
    year_min, year_max = _detect_year_range(question)

    if metric_id is None:
        return {
            "answer": "Could not identify which ESG metric the question refers to. Ask about Scope 1/2/3 emissions, energy consumption, water withdrawal, or employee count.",
            "citations": [],
            "tool_calls": [],
        }

    # --- compare intent ---
    if any(kw in lower for kw in _COMPARE_KEYWORDS):
        entities = _split_compare_entities(question)
        if len(entities) >= 2 and year_min is not None:
            args = {"metric_id": metric_id, "entity_hints": entities, "year": year_min}
            result = compare_metric(**args)
            tool_calls.append({"name": "compare_metric", "arguments": args, "result": result})
            return {
                "answer": _format_compare_answer(result),
                "citations": _extract_citations(result["rows"]),
                "tool_calls": tool_calls,
            }

    # --- trend intent ---
    if any(kw in lower for kw in _TREND_KEYWORDS) and year_min is not None and year_max is not None and year_min != year_max:
        entity_hint = _detect_entity(question) or ""
        if entity_hint:
            args = {
                "metric_id": metric_id,
                "entity_hint": entity_hint,
                "year_min": year_min,
                "year_max": year_max,
            }
            result = metric_trend(**args)
            tool_calls.append({"name": "metric_trend", "arguments": args, "result": result})
            return {
                "answer": _format_trend_answer(result),
                "citations": _extract_citations(result["rows"]),
                "tool_calls": tool_calls,
            }

    # --- single query (default) ---
    entity_hint = _detect_entity(question)
    args = {"metric_id": metric_id}
    if entity_hint:
        args["entity_hint"] = entity_hint
    if year_min is not None:
        args["year"] = year_min
    rows = query_metric(**args)
    tool_calls.append({"name": "query_metric", "arguments": args, "result": rows})
    return {
        "answer": _format_query_answer(rows),
        "citations": _extract_citations(rows),
        "tool_calls": tool_calls,
    }
