"""Max memberships are independent of admin roles; only admins can grant them."""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

SCHEMA = '''CREATE TABLE IF NOT EXISTS max_memberships (
    user_id TEXT PRIMARY KEY,
    expires_at TEXT,
    note TEXT NOT NULL DEFAULT '',
    granted_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1
)'''


async def init_max_memberships(db):
    await db.execute(SCHEMA)


async def has_max_membership(db, user_id: str) -> bool:
    if not user_id:
        return False
    try:
        cursor = await db.execute('SELECT expires_at FROM max_memberships WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
    except sqlite3.OperationalError as exc:
        # Old databases/test fixtures do not grant Max by default.
        if 'no such table: max_memberships' in str(exc):
            return False
        raise
    if row is None:
        return False
    if row[0] is None:
        return True
    try:
        expiry = datetime.fromisoformat(row[0].replace('Z', '+00:00'))
        return expiry.tzinfo is not None and expiry > datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False
