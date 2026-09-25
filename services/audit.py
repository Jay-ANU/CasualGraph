"""Matter audit log: who did what to which matter, member or document.

Events carry ids, counts, flags and short enum labels only. Document text, questions, answers,
redaction values and other personal data never belong in ``details``; ``validate_details``
rejects text-like keys and long strings so a careless caller fails loudly instead of leaking.

``record_event`` is synchronous and opens its own connection, so sync code (the redaction
pipeline, ingestion callbacks, scripts) can call it directly. Services that already hold a write
transaction use ``write_event`` so the audit row commits or rolls back with the change it records.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from services import db as db_service

# Keys that name free text. Matching is case-insensitive; the suffixes catch "original_text",
# "block_content", "new_value" and the like.
FORBIDDEN_DETAIL_KEYS = frozenset(
    {
        "text",
        "texts",
        "content",
        "contents",
        "quote",
        "quotes",
        "value",
        "values",
        "question",
        "query",
        "answer",
        "prompt",
        "snippet",
        "excerpt",
    }
)
FORBIDDEN_DETAIL_KEY_SUFFIXES = ("_text", "_texts", "_content", "_contents", "_quote", "_quotes", "_value", "_values")
MAX_DETAIL_STRING_LENGTH = 512
MAX_DETAIL_DEPTH = 6
MAX_DETAILS_JSON_BYTES = 8192
MAX_LIST_LIMIT = 500

_ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_IDENTIFIER_MAX_LENGTH = 512


class AuditDetailsError(ValueError):
    """The audit details held something other than ids, counts, flags or short labels."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_forbidden_key(key: str) -> bool:
    lowered = key.strip().lower()
    return lowered in FORBIDDEN_DETAIL_KEYS or lowered.endswith(FORBIDDEN_DETAIL_KEY_SUFFIXES)


def _check_detail_value(value: Any, path: str, depth: int) -> Any:
    if depth > MAX_DETAIL_DEPTH:
        raise AuditDetailsError(f"audit details nest deeper than {MAX_DETAIL_DEPTH} levels at {path}")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AuditDetailsError(f"audit detail {path} is not a finite number")
        return value
    if isinstance(value, str):
        if len(value) > MAX_DETAIL_STRING_LENGTH:
            # Never echo the value itself: it is exactly what must not be logged.
            raise AuditDetailsError(
                f"audit detail {path} is a {len(value)}-character string; details hold ids and counts only"
            )
        return value
    if isinstance(value, dict):
        checked: Dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise AuditDetailsError(f"audit detail keys must be strings (at {path})")
            if _is_forbidden_key(key):
                raise AuditDetailsError(f"audit detail key {key!r} at {path} names free text; record ids and counts only")
            checked[key] = _check_detail_value(item, f"{path}.{key}", depth + 1)
        return checked
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else list(value)
        return [_check_detail_value(item, f"{path}[{index}]", depth + 1) for index, item in enumerate(items)]
    raise AuditDetailsError(f"audit detail {path} has unsupported type {type(value).__name__}")


def validate_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a JSON-safe copy of ``details`` or raise ``AuditDetailsError``.

    Allowed: nested dicts/lists of ids (strings up to ``MAX_DETAIL_STRING_LENGTH``), numbers,
    booleans and nulls. Rejected: keys in ``FORBIDDEN_DETAIL_KEYS`` or ending in one of
    ``FORBIDDEN_DETAIL_KEY_SUFFIXES`` (at any depth), long strings, non-JSON types, and payloads
    over ``MAX_DETAILS_JSON_BYTES``.
    """
    if details is None:
        return {}
    if not isinstance(details, dict):
        raise AuditDetailsError("audit details must be a JSON object")
    checked = _check_detail_value(details, "details", 0)
    encoded = json.dumps(checked, ensure_ascii=False, sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_DETAILS_JSON_BYTES:
        raise AuditDetailsError(f"audit details exceed {MAX_DETAILS_JSON_BYTES} bytes")
    return checked


def _clean_identifier(value: Any, field: str, *, required: bool) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"audit {field} is required")
    if len(text) > _IDENTIFIER_MAX_LENGTH:
        raise ValueError(f"audit {field} is longer than {_IDENTIFIER_MAX_LENGTH} characters")
    return text


def _prepare_event(
    *,
    actor_user_id: str,
    action: str,
    target_type: str,
    target_id: str,
    matter_id: Optional[str],
    org_id: Optional[str],
    details: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    action_value = _clean_identifier(action, "action", required=True)
    if not _ACTION_PATTERN.match(action_value):
        raise ValueError(f"audit action {action_value!r} must look like 'area.verb' (lowercase, dotted)")
    return {
        "actor_user_id": _clean_identifier(actor_user_id, "actor_user_id", required=True),
        "action": action_value,
        "target_type": _clean_identifier(target_type, "target_type", required=True),
        "target_id": _clean_identifier(target_id, "target_id", required=False),
        "matter_id": _clean_identifier(matter_id, "matter_id", required=False) or None,
        "org_id": _clean_identifier(org_id, "org_id", required=False) or None,
        "details_json": json.dumps(validate_details(details), ensure_ascii=False, sort_keys=True),
    }


def _insert_prepared(conn: sqlite3.Connection, event: Dict[str, Any]) -> int:
    org_id = event["org_id"]
    if event["matter_id"] and not org_id:
        row = conn.execute("SELECT org_id FROM matters WHERE id = ?", (event["matter_id"],)).fetchone()
        org_id = row[0] if row else None
    cursor = conn.execute(
        """
        INSERT INTO audit_events
            (org_id, matter_id, actor_user_id, action, target_type, target_id, details_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            org_id,
            event["matter_id"],
            event["actor_user_id"],
            event["action"],
            event["target_type"],
            event["target_id"],
            event["details_json"],
            _now_iso(),
        ),
    )
    return int(cursor.lastrowid)


def write_event(
    conn: sqlite3.Connection,
    *,
    actor_user_id: str,
    action: str,
    target_type: str,
    target_id: str,
    matter_id: Optional[str] = None,
    org_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> int:
    """Insert an event inside the caller's open transaction (it commits with the change it records)."""
    event = _prepare_event(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        matter_id=matter_id,
        org_id=org_id,
        details=details,
    )
    return _insert_prepared(conn, event)


def record_event(
    *,
    actor_user_id: str,
    action: str,
    target_type: str,
    target_id: str,
    matter_id: Optional[str] = None,
    org_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> int:
    """Append one audit event and return its id. Sync; safe to call from sync code and threads.

    ``org_id`` is filled from the matter when only ``matter_id`` is given. Raises
    ``AuditDetailsError`` (a ``ValueError``) for unsafe details before touching the database.
    """
    event = _prepare_event(
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        matter_id=matter_id,
        org_id=org_id,
        details=details,
    )
    with db_service.auth_db_transaction() as conn:
        return _insert_prepared(conn, event)


def _event_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        details = json.loads(row["details_json"] or "{}")
    except json.JSONDecodeError:
        details = {}
    return {
        "id": int(row["id"]),
        "org_id": row["org_id"],
        "matter_id": row["matter_id"],
        "actor_user_id": row["actor_user_id"],
        "action": row["action"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "details": details if isinstance(details, dict) else {},
        "created_at": row["created_at"],
    }


def list_events(matter_id: str, limit: int = 100, before: Optional[Union[int, str]] = None) -> List[Dict[str, Any]]:
    """Events of one matter, newest first. ``before`` is an event id cursor (exclusive)."""
    matter_value = str(matter_id or "").strip()
    if not matter_value:
        return []
    limit_value = max(1, min(int(limit or 100), MAX_LIST_LIMIT))
    params: List[Any] = [matter_value]
    sql = "SELECT * FROM audit_events WHERE matter_id = ?"
    if before is not None and str(before).strip():
        try:
            before_id = int(str(before).strip())
        except ValueError as exc:
            raise ValueError("before must be an audit event id") from exc
        sql += " AND id < ?"
        params.append(before_id)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit_value)
    conn = db_service.connect_auth_db_sync()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [_event_from_row(row) for row in rows]
