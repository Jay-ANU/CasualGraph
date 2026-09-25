"""SQLite locations, the request-scoped auth DB connection, and schema initialisation."""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Tuple

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

# Matters and tenancy (contracts §8). Every statement is idempotent so both the async startup
# init and the sync connection helper below can run them at any time.
MATTER_SCHEMA_STATEMENTS: Tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS organizations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        settings_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS org_members (
        org_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
        created_at TEXT NOT NULL,
        PRIMARY KEY (org_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matters (
        id TEXT PRIMARY KEY,
        org_id TEXT NOT NULL,
        name TEXT NOT NULL,
        client_ref TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        settings_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_members (
        matter_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('lead', 'member', 'viewer')),
        added_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (matter_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matter_documents (
        matter_id TEXT NOT NULL,
        document_id TEXT NOT NULL,
        added_by TEXT NOT NULL,
        added_at TEXT NOT NULL,
        PRIMARY KEY (matter_id, document_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id TEXT,
        matter_id TEXT,
        actor_user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        details_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS matter_members_user_id_idx ON matter_members(user_id)",
    "CREATE INDEX IF NOT EXISTS matter_documents_document_id_idx ON matter_documents(document_id)",
    "CREATE INDEX IF NOT EXISTS audit_events_matter_created_idx ON audit_events(matter_id, created_at)",
)

_SYNC_BUSY_TIMEOUT_SECONDS = 15.0
_SYNC_SCHEMA_READY: set[str] = set()
_SYNC_SCHEMA_LOCK = threading.Lock()


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
        for statement in MATTER_SCHEMA_STATEMENTS:
            await db.execute(statement)
        from services.max_membership import init_max_memberships
        await init_max_memberships(db)
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


def create_matter_schema_sync(conn: sqlite3.Connection) -> None:
    """Create the matter tables and indexes on ``conn`` (idempotent; runs in the caller's transaction)."""
    for statement in MATTER_SCHEMA_STATEMENTS:
        conn.execute(statement)


def connect_auth_db_sync(*, ensure_schema: bool = True) -> sqlite3.Connection:
    """A blocking connection to the same auth DB as ``get_db`` for sync callers.

    Document access checks, the RAG scope resolver, audit writes and scripts are synchronous, so
    they cannot use the aiosqlite dependency. The path is read at call time (tests patch
    ``_DB_PATH``). The connection is in autocommit mode: use ``auth_db_transaction`` to write.
    """
    path = _DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=_SYNC_BUSY_TIMEOUT_SECONDS, isolation_level=None)
    conn.row_factory = sqlite3.Row
    if ensure_schema and path not in _SYNC_SCHEMA_READY:
        try:
            with _SYNC_SCHEMA_LOCK:
                if path not in _SYNC_SCHEMA_READY:
                    create_matter_schema_sync(conn)
                    _SYNC_SCHEMA_READY.add(path)
        except Exception:
            conn.close()
            raise
    return conn


@contextmanager
def auth_db_transaction(*, ensure_schema: bool = True) -> Iterator[sqlite3.Connection]:
    """``BEGIN IMMEDIATE`` ... ``COMMIT`` on a fresh sync connection; rolls back on any error.

    IMMEDIATE takes the write lock up front, so read-then-write sequences (idempotent
    provisioning, last-lead checks) cannot interleave with another writer.
    """
    conn = connect_auth_db_sync(ensure_schema=ensure_schema)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


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
