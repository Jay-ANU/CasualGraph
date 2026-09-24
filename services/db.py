"""SQLite locations, the request-scoped auth DB connection, and schema initialisation."""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

from configs.settings import DATA_DIR
from user_memory_service import init_user_memory_db


def _resolve_auth_db_path() -> str:
    configured = os.getenv("AUTH_DB_PATH", "").strip()
    if configured:
        return configured

    fly_data_dir = Path("/data")
    if fly_data_dir.exists() and os.access(fly_data_dir, os.W_OK):
        return str(fly_data_dir / "auth.db")

    return str(Path(__file__).resolve().parents[1] / "auth.db")


def _resolve_feedback_db_path() -> str:
    configured = os.getenv("CAUSALGRAPH_DB_PATH", "").strip()
    if configured:
        return configured
    return str(DATA_DIR / "causalgraph.db")


_DB_PATH = _resolve_auth_db_path()
_FEEDBACK_DB_PATH = _resolve_feedback_db_path()


async def get_db():
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as db:
        yield db


async def _init_auth_db():
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_invite_codes (
                id TEXT PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                created_by_user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                used_by_user_id TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS email_verification_codes (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                purpose TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_sent_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rag_rate_usage (
                user_id TEXT NOT NULL,
                usage_date TEXT NOT NULL,
                points_used INTEGER NOT NULL DEFAULT 0,
                request_count INTEGER NOT NULL DEFAULT 0,
                flash_count INTEGER NOT NULL DEFAULT 0,
                deep_count INTEGER NOT NULL DEFAULT 0,
                last_request_at TEXT,
                PRIMARY KEY (user_id, usage_date)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rag_unlimited_users (
                email TEXT PRIMARY KEY,
                note TEXT NOT NULL DEFAULT '',
                created_by_user_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS admin_invite_codes_expires_at_idx ON admin_invite_codes(expires_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS admin_invite_codes_used_at_idx ON admin_invite_codes(used_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS email_verification_codes_email_purpose_idx ON email_verification_codes(email, purpose, created_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS email_verification_codes_expires_at_idx ON email_verification_codes(expires_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS rag_rate_usage_date_idx ON rag_rate_usage(usage_date)")
        await db.execute("CREATE INDEX IF NOT EXISTS rag_unlimited_users_created_at_idx ON rag_unlimited_users(created_at)")
        await _ensure_column(db, "users", "role", "TEXT NOT NULL DEFAULT 'user'")
        await db.execute("UPDATE users SET role = 'user' WHERE role IS NULL OR lower(role) NOT IN ('admin', 'user')")
        await init_user_memory_db(db)
        admin_emails = sorted(_admin_email_set())
        if admin_emails:
            placeholders = ",".join("?" for _ in admin_emails)
            await db.execute(
                f"UPDATE users SET role = 'admin' WHERE lower(email) IN ({placeholders})",
                tuple(admin_emails),
            )
        await db.execute("DELETE FROM admin_invite_codes WHERE datetime(expires_at) <= datetime('now') OR used_at IS NOT NULL")
        await db.execute("DELETE FROM email_verification_codes WHERE datetime(expires_at) <= datetime('now') OR consumed_at IS NOT NULL")
        await db.commit()


async def _init_feedback_db():
    Path(_FEEDBACK_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_FEEDBACK_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS answer_feedback (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       TEXT NOT NULL,
                session_id    TEXT NOT NULL,
                message_id    TEXT NOT NULL,
                query         TEXT NOT NULL,
                answer        TEXT NOT NULL,
                rating        TEXT NOT NULL,
                reason_tags   TEXT,
                reason_text   TEXT,
                sources_json  TEXT,
                timings_json  TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_feedback_rating ON answer_feedback(rating, created_at)")
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_feedback_user_message ON answer_feedback(user_id, message_id)")
        await db.commit()


async def _ensure_column(db: aiosqlite.Connection, table_name: str, column_name: str, definition: str) -> None:
    cursor = await db.execute(f"PRAGMA table_info({table_name})")
    rows = await cursor.fetchall()
    existing = {str(row[1]) for row in rows}
    if column_name not in existing:
        await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _admin_email_set() -> set[str]:
    return {
        email.strip().lower()
        for email in os.getenv("ADMIN_EMAILS", "").split(",")
        if email.strip()
    }
