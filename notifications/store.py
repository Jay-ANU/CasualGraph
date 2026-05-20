"""SQLite-backed storage for unanswered-query notifications."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from configs.settings import (
    NOTIFICATIONS_DB_PATH,
    NOTIFICATIONS_DEDUP_WINDOW_MINUTES,
    PROJECT_ROOT,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS unanswered_notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL,
  query TEXT NOT NULL,
  rewritten_query TEXT,
  failure_reason TEXT NOT NULL,
  retrieval_strategy TEXT,
  filters_json TEXT,
  mode TEXT,
  occurrence_count INTEGER NOT NULL DEFAULT 1,
  user_ids_json TEXT,
  first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status TEXT NOT NULL DEFAULT 'pending',
  resolution TEXT,
  resolved_at TIMESTAMP,
  top_sources_json TEXT,
  email_sent_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_status_last_seen
  ON unanswered_notifications(status, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_fingerprint_status
  ON unanswered_notifications(fingerprint, status);
"""


def init_db(db_path: str) -> None:
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(_SCHEMA)
        conn.commit()


def compute_fingerprint(query: str, filters: Optional[dict] = None) -> str:
    normalized_query = " ".join(str(query or "").strip().lower().split())
    sorted_filters = json.dumps(filters or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(f"{normalized_query}|{sorted_filters}".encode("utf-8")).hexdigest()[:16]


def record_unanswered(
    *,
    query,
    rewritten_query,
    failure_reason,
    retrieval_strategy,
    filters,
    mode,
    user_id,
    top_sources_preview,
) -> int:
    path = _default_db_path()
    init_db(str(path))
    now = _utc_now_iso()
    cutoff = _utc_iso_before(minutes=NOTIFICATIONS_DEDUP_WINDOW_MINUTES)
    fingerprint = compute_fingerprint(str(query or ""), filters if isinstance(filters, dict) else {})
    filters_json = json.dumps(filters or {}, sort_keys=True, ensure_ascii=False)
    user_hash = _anonymize_user_id(user_id)
    sanitized_sources = _sanitize_top_sources_preview(top_sources_preview)

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT *
            FROM unanswered_notifications
            WHERE fingerprint = ?
              AND status = 'pending'
              AND last_seen_at >= ?
            ORDER BY last_seen_at DESC, id DESC
            LIMIT 1
            """,
            (fingerprint, cutoff),
        ).fetchone()

        if row is not None:
            merged_users = _merge_user_ids(row["user_ids_json"], user_hash)
            merged_sources = sanitized_sources or _load_json_list(row["top_sources_json"])
            conn.execute(
                """
                UPDATE unanswered_notifications
                SET rewritten_query = ?,
                    failure_reason = ?,
                    retrieval_strategy = ?,
                    filters_json = ?,
                    mode = ?,
                    occurrence_count = ?,
                    user_ids_json = ?,
                    last_seen_at = ?,
                    top_sources_json = ?
                WHERE id = ?
                """,
                (
                    str(rewritten_query or row["rewritten_query"] or ""),
                    str(failure_reason or row["failure_reason"] or ""),
                    str(retrieval_strategy or row["retrieval_strategy"] or ""),
                    filters_json,
                    str(mode or row["mode"] or ""),
                    int(row["occurrence_count"] or 0) + 1,
                    json.dumps(merged_users, ensure_ascii=False),
                    now,
                    json.dumps(merged_sources, ensure_ascii=False),
                    int(row["id"]),
                ),
            )
            conn.commit()
            return int(row["id"])

        cursor = conn.execute(
            """
            INSERT INTO unanswered_notifications (
                fingerprint,
                query,
                rewritten_query,
                failure_reason,
                retrieval_strategy,
                filters_json,
                mode,
                occurrence_count,
                user_ids_json,
                first_seen_at,
                last_seen_at,
                status,
                top_sources_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                fingerprint,
                str(query or ""),
                str(rewritten_query or ""),
                str(failure_reason or ""),
                str(retrieval_strategy or ""),
                filters_json,
                str(mode or ""),
                1,
                json.dumps(_merge_user_ids(None, user_hash), ensure_ascii=False),
                now,
                now,
                json.dumps(sanitized_sources, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_pending(limit: int = 100, since: datetime | None = None) -> list[dict]:
    path = _default_db_path()
    init_db(str(path))
    params: List[Any] = []
    query = """
        SELECT *
        FROM unanswered_notifications
        WHERE status = 'pending'
    """
    if since is not None:
        query += " AND last_seen_at >= ?"
        params.append(_to_utc_iso(since))
    query += " ORDER BY last_seen_at DESC, id DESC LIMIT ?"
    params.append(max(1, int(limit)))

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def mark_sent(ids: list[int]) -> None:
    if not ids:
        return
    path = _default_db_path()
    init_db(str(path))
    now = _utc_now_iso()
    placeholders = ", ".join("?" for _ in ids)
    params = [now, *[int(item) for item in ids]]
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""
            UPDATE unanswered_notifications
            SET status = 'sent',
                email_sent_at = ?
            WHERE id IN ({placeholders})
            """,
            params,
        )
        conn.commit()


def mark_resolved(id_: int, resolution: str, note: str | None = None) -> None:
    path = _default_db_path()
    init_db(str(path))
    resolved_text = str(resolution or "").strip()
    if note:
        resolved_text = f"{resolved_text} | {str(note).strip()}" if resolved_text else str(note).strip()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            UPDATE unanswered_notifications
            SET status = 'resolved',
                resolution = ?,
                resolved_at = ?
            WHERE id = ?
            """,
            (resolved_text, _utc_now_iso(), int(id_)),
        )
        conn.commit()


def get_stats(window_hours: int = 24) -> dict:
    path = _default_db_path()
    init_db(str(path))
    since = _utc_iso_before(hours=max(1, int(window_hours)))
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM unanswered_notifications
            WHERE status = 'pending'
              AND last_seen_at >= ?
            ORDER BY occurrence_count DESC, last_seen_at DESC
            """,
            (since,),
        ).fetchall()

    items = [_row_to_dict(row) for row in rows]
    by_reason: Dict[str, int] = {}
    for item in items:
        reason = str(item.get("failure_reason") or "unknown")
        by_reason[reason] = by_reason.get(reason, 0) + 1

    return {
        "total": len(items),
        "unique_queries": len({str(item.get("query") or "").strip().lower() for item in items if str(item.get("query") or "").strip()}),
        "by_reason": by_reason,
        "top_recurring": items[:5],
    }


def _default_db_path() -> Path:
    return _resolve_db_path(NOTIFICATIONS_DB_PATH)


def _resolve_db_path(db_path: str) -> Path:
    path = Path(str(db_path or "backend/notifications.db")).expanduser()
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": int(row["id"]),
        "fingerprint": str(row["fingerprint"] or ""),
        "query": str(row["query"] or ""),
        "rewritten_query": str(row["rewritten_query"] or ""),
        "failure_reason": str(row["failure_reason"] or ""),
        "retrieval_strategy": str(row["retrieval_strategy"] or ""),
        "filters": _load_json_object(row["filters_json"]),
        "mode": str(row["mode"] or ""),
        "occurrence_count": int(row["occurrence_count"] or 0),
        "user_ids": _load_json_list(row["user_ids_json"]),
        "first_seen_at": str(row["first_seen_at"] or ""),
        "last_seen_at": str(row["last_seen_at"] or ""),
        "status": str(row["status"] or ""),
        "resolution": str(row["resolution"] or ""),
        "resolved_at": str(row["resolved_at"] or ""),
        "top_sources_preview": _load_json_list(row["top_sources_json"]),
        "email_sent_at": str(row["email_sent_at"] or ""),
    }


def _load_json_object(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _load_json_list(value: Any) -> List[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _merge_user_ids(existing_json: Any, user_hash: Optional[str]) -> List[str]:
    merged = []
    seen = set()
    for value in _load_json_list(existing_json):
        key = str(value or "").strip()
        if key and key not in seen:
            seen.add(key)
            merged.append(key)
    if user_hash and user_hash not in seen:
        merged.append(user_hash)
    return merged


def _sanitize_top_sources_preview(items: Any) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return output
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        row = {
            "chunk_id": str(item.get("chunk_id") or ""),
            "document_id": str(item.get("document_id") or ""),
            "score": float(item.get("score") or item.get("fusion_score") or 0.0),
        }
        output.append(row)
    return output


def _anonymize_user_id(raw_user_id: Any) -> Optional[str]:
    value = str(raw_user_id or "").strip()
    if not value:
        return None
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _to_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _utc_iso_before(*, minutes: int = 0, hours: int = 0) -> str:
    delta = timedelta(minutes=minutes, hours=hours)
    return _to_utc_iso(datetime.now(timezone.utc) - delta)
