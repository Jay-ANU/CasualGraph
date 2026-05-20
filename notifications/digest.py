"""Digest rendering for unanswered-query notifications."""

from __future__ import annotations

from typing import Dict, List


def build_digest(records: List[Dict], *, window_hours: int, stats: Dict) -> str:
    ordered = sorted(
        records or [],
        key=lambda item: (
            len(item.get("user_ids") or []),
            int(item.get("occurrence_count") or 0),
            str(item.get("last_seen_at") or ""),
        ),
        reverse=True,
    )
    if not ordered:
        return "No unanswered questions in window"

    recurring = [item for item in ordered if int(item.get("occurrence_count") or 0) > 1]
    singletons = [item for item in ordered if int(item.get("occurrence_count") or 0) <= 1]
    total_records = len(ordered)
    recurring_count = len(recurring)

    lines = [
        f"Subject: [CausalGraph] {total_records} unanswered ESG questions (last {window_hours}h, {recurring_count} recurring)",
        "",
        "Top recurring (please prioritize):",
        "─────────────────────────────────",
    ]
    if recurring:
        for index, item in enumerate(recurring, start=1):
            lines.extend(_format_record(item, index=index))
    else:
        lines.append("none")

    lines.extend(
        [
            "",
            f"New singletons ({len(singletons)}):",
            "─────────────────────────────────",
        ]
    )
    if singletons:
        for item in singletons:
            lines.append(f'- "{item.get("query", "")}"')
    else:
        lines.append("none")

    lines.extend(
        [
            "",
            f'Stats: total={stats.get("total", 0)} · unique={stats.get("unique_queries", 0)} · by_reason={stats.get("by_reason", {})}',
        ]
    )
    return "\n".join(lines)


def build_subject(records: List[Dict], *, window_hours: int) -> str:
    ordered = records or []
    recurring_count = sum(1 for item in ordered if int(item.get("occurrence_count") or 0) > 1)
    return f"[CausalGraph] {len(ordered)} unanswered ESG questions (last {window_hours}h, {recurring_count} recurring)"


def _format_record(item: Dict, *, index: int) -> List[str]:
    preview = _format_sources(item.get("top_sources_preview") or [])
    users = item.get("user_ids") or []
    return [
        f'[{index}] "{item.get("query", "")}"   asked {int(item.get("occurrence_count") or 0)}× by {len(users)} users',
        f'    reason: {item.get("failure_reason", "")} (strategy: {item.get("retrieval_strategy", "") or "unknown"})',
        f'    closest sources: {preview}',
        "",
    ]


def _format_sources(items: List[Dict]) -> str:
    if not items:
        return "none"
    parts = []
    for item in items[:3]:
        parts.append(
            f'{item.get("chunk_id") or "unknown"} / {item.get("document_id") or "unknown"} / score={float(item.get("score") or 0.0):.3f}'
        )
    return "; ".join(parts)
