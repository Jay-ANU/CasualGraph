"""Local admin audit storage for document ingestion events."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional


_DB_PATH = Path(__file__).resolve().parent / "auth.db"
_LOCK = Lock()


def init_admin_db() -> None:
    with _connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS upload_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT UNIQUE NOT NULL,
                document_id TEXT,
                title TEXT NOT NULL,
                filename TEXT,
                domain TEXT,
                source_type TEXT,
                source TEXT,
                uploader_id TEXT,
                uploader_email TEXT,
                uploader_username TEXT,
                status TEXT NOT NULL,
                stage TEXT,
                progress INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT,
                error TEXT,
                chunk_count INTEGER DEFAULT 0,
                entity_count INTEGER DEFAULT 0,
                relation_count INTEGER DEFAULT 0,
                processed_text_path TEXT,
                chunks_path TEXT,
                extractions_path TEXT,
                graph_path TEXT,
                vector_store_path TEXT
            )
            """
        )
        _ensure_column(db, "upload_audit", "progress", "INTEGER DEFAULT 0")
        _ensure_column(db, "upload_audit", "content_hash", "TEXT")
        _ensure_column(db, "upload_audit", "duplicate_of_document_id", "TEXT")
        _ensure_column(db, "upload_audit", "deleted_at", "TEXT")
        _ensure_column(db, "upload_audit", "deleted_by", "TEXT")
        _ensure_column(db, "upload_audit", "delete_reason", "TEXT")
        _ensure_column(db, "upload_audit", "cleanup_status", "TEXT")
        _ensure_column(db, "upload_audit", "cleanup_detail", "TEXT")
        _ensure_column(db, "upload_audit", "cleanup_completed_at", "TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS upload_audit_created_at ON upload_audit(created_at)")
        db.execute("CREATE INDEX IF NOT EXISTS upload_audit_status ON upload_audit(status)")
        db.execute("CREATE INDEX IF NOT EXISTS upload_audit_content_hash ON upload_audit(content_hash)")
        db.commit()


def record_upload_created(
    *,
    job_id: str,
    title: str,
    filename: Optional[str],
    domain: str,
    source_type: str,
    source: str,
    uploader: Optional[Dict[str, Any]],
) -> None:
    init_admin_db()
    now = _now()
    with _LOCK, _connect() as db:
        db.execute(
            """
            INSERT OR REPLACE INTO upload_audit (
                job_id, title, filename, domain, source_type, source,
                uploader_id, uploader_email, uploader_username,
                status, stage, progress, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 'queued', 0, ?, ?)
            """,
            (
                job_id,
                title,
                filename or "",
                domain,
                source_type,
                source,
                (uploader or {}).get("id", ""),
                (uploader or {}).get("email", ""),
                (uploader or {}).get("username", ""),
                now,
                now,
            ),
        )
        db.commit()


def record_upload_progress(job_id: str, *, status: str, stage: str, progress: int) -> None:
    now = _now()
    init_admin_db()
    with _LOCK, _connect() as db:
        db.execute(
            """
            UPDATE upload_audit
            SET status = ?, stage = ?, progress = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (status, stage, int(progress), now, job_id),
        )
        db.commit()


def record_upload_completed(job_id: str, result: Dict[str, Any]) -> None:
    document = result.get("document") or {}
    stats = result.get("stats") or {}
    now = _now()
    init_admin_db()
    with _LOCK, _connect() as db:
        db.execute(
            """
            UPDATE upload_audit
            SET status = 'completed',
                stage = 'completed',
                progress = 100,
                updated_at = ?,
                completed_at = ?,
                document_id = ?,
                chunk_count = ?,
                entity_count = ?,
                relation_count = ?,
                processed_text_path = ?,
                chunks_path = ?,
                extractions_path = ?,
                graph_path = ?,
                vector_store_path = ?,
                content_hash = ?
            WHERE job_id = ?
            """,
            (
                now,
                now,
                document.get("id", ""),
                int(stats.get("chunk_count") or 0),
                int(stats.get("entity_count") or 0),
                int(stats.get("relation_count") or 0),
                document.get("processed_text_path", ""),
                document.get("chunks_path", ""),
                document.get("extractions_path", ""),
                document.get("graph_path", ""),
                document.get("vector_store_path", ""),
                document.get("content_hash", ""),
                job_id,
            ),
        )
        db.commit()


def record_upload_rejected(job_id: str, *, reason: str, result: Optional[Dict[str, Any]] = None) -> None:
    document = (result or {}).get("document") or {}
    now = _now()
    init_admin_db()
    with _LOCK, _connect() as db:
        db.execute(
            """
            UPDATE upload_audit
            SET status = 'rejected',
                stage = 'rejected',
                progress = 100,
                updated_at = ?,
                completed_at = ?,
                error = ?,
                document_id = '',
                content_hash = ?,
                duplicate_of_document_id = ?
            WHERE job_id = ?
            """,
            (
                now,
                now,
                reason,
                document.get("content_hash", ""),
                document.get("duplicate_of_document_id", ""),
                job_id,
            ),
        )
        db.commit()


def record_upload_failed(job_id: str, error: str) -> None:
    now = _now()
    init_admin_db()
    with _LOCK, _connect() as db:
        db.execute(
            """
            UPDATE upload_audit
            SET status = 'failed', stage = 'failed', progress = 100, updated_at = ?, completed_at = ?, error = ?
            WHERE job_id = ?
            """,
            (now, now, error, job_id),
        )
        db.commit()


def list_uploads(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    init_admin_db()
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    with _connect() as db:
        rows = db.execute(
            """
            SELECT job_id, document_id, title, filename, domain, source_type, source,
                   uploader_id, uploader_email, uploader_username, status, stage,
                   progress, created_at, updated_at, completed_at, error,
                   chunk_count, entity_count, relation_count,
                   processed_text_path, chunks_path, extractions_path, graph_path, vector_store_path,
                   content_hash, duplicate_of_document_id, deleted_at, deleted_by, delete_reason,
                   cleanup_status, cleanup_detail, cleanup_completed_at
            FROM upload_audit
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [_row_to_upload(row) for row in rows]


def get_latest_upload_by_document_id(document_id: str) -> Optional[Dict[str, Any]]:
    init_admin_db()
    document_id = str(document_id or "").strip()
    if not document_id:
        return None
    with _connect() as db:
        row = db.execute(
            """
            SELECT job_id, document_id, title, filename, domain, source_type, source,
                   uploader_id, uploader_email, uploader_username, status, stage,
                   progress, created_at, updated_at, completed_at, error,
                   chunk_count, entity_count, relation_count,
                   processed_text_path, chunks_path, extractions_path, graph_path, vector_store_path,
                   content_hash, duplicate_of_document_id, deleted_at, deleted_by, delete_reason,
                   cleanup_status, cleanup_detail, cleanup_completed_at
            FROM upload_audit
            WHERE document_id = ?
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT 1
            """,
            (document_id,),
        ).fetchone()
    return _row_to_upload(row) if row else None


def list_latest_uploads_by_document_id() -> Dict[str, Dict[str, Any]]:
    init_admin_db()
    with _connect() as db:
        rows = db.execute(
            """
            SELECT job_id, document_id, title, filename, domain, source_type, source,
                   uploader_id, uploader_email, uploader_username, status, stage,
                   progress, created_at, updated_at, completed_at, error,
                   chunk_count, entity_count, relation_count,
                   processed_text_path, chunks_path, extractions_path, graph_path, vector_store_path,
                   content_hash, duplicate_of_document_id, deleted_at, deleted_by, delete_reason,
                   cleanup_status, cleanup_detail, cleanup_completed_at
            FROM upload_audit
            WHERE ifnull(document_id, '') != ''
            ORDER BY datetime(created_at) DESC, id DESC
            """
        ).fetchall()

    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        document_id = str(row["document_id"] or "").strip()
        if document_id and document_id not in latest:
            latest[document_id] = _row_to_upload(row)
    return latest


def admin_overview(days: int = 14) -> Dict[str, Any]:
    init_admin_db()
    days = max(1, min(int(days), 90))
    start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date()
    with _connect() as db:
        totals = db.execute(
            """
            SELECT
              count(*) AS total,
              sum(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
              sum(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
              sum(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected,
              sum(CASE WHEN status IN ('deleted', 'deleted_with_warnings') THEN 1 ELSE 0 END) AS deleted,
              sum(CASE WHEN status IN ('queued', 'running') THEN 1 ELSE 0 END) AS active,
              sum(chunk_count) AS chunks,
              sum(entity_count) AS entities,
              sum(relation_count) AS relations
            FROM upload_audit
            """
        ).fetchone()
        daily_rows = db.execute(
            """
            SELECT substr(created_at, 1, 10) AS day, count(*) AS uploads
            FROM upload_audit
            WHERE date(created_at) >= date(?)
            GROUP BY day
            ORDER BY day ASC
            """,
            (start.isoformat(),),
        ).fetchall()

    daily_map = {row["day"]: int(row["uploads"] or 0) for row in daily_rows}
    daily = []
    for index in range(days):
        day = start + timedelta(days=index)
        daily.append({"date": day.isoformat(), "uploads": daily_map.get(day.isoformat(), 0)})

    return {
        "totals": {
            "uploads": int(totals["total"] or 0),
            "completed": int(totals["completed"] or 0),
            "failed": int(totals["failed"] or 0),
            "rejected": int(totals["rejected"] or 0),
            "deleted": int(totals["deleted"] or 0),
            "active": int(totals["active"] or 0),
            "chunks": int(totals["chunks"] or 0),
            "entities": int(totals["entities"] or 0),
            "relations": int(totals["relations"] or 0),
        },
        "daily": daily,
        "recent_uploads": list_uploads(limit=10),
    }


def get_upload(job_id: str) -> Optional[Dict[str, Any]]:
    init_admin_db()
    with _connect() as db:
        row = db.execute(
            """
            SELECT job_id, document_id, title, filename, domain, source_type, source,
                   uploader_id, uploader_email, uploader_username, status, stage,
                   progress, created_at, updated_at, completed_at, error,
                   chunk_count, entity_count, relation_count,
                   processed_text_path, chunks_path, extractions_path, graph_path, vector_store_path,
                   content_hash, duplicate_of_document_id, deleted_at, deleted_by, delete_reason,
                   cleanup_status, cleanup_detail, cleanup_completed_at
            FROM upload_audit
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
    return _row_to_upload(row) if row else None


def find_completed_upload_by_hash(content_hash: str) -> Optional[Dict[str, Any]]:
    if not content_hash:
        return None
    init_admin_db()
    with _connect() as db:
        row = db.execute(
            """
            SELECT job_id, document_id, title, filename, domain, source_type, source,
                   uploader_id, uploader_email, uploader_username, status, stage,
                   progress, created_at, updated_at, completed_at, error,
                   chunk_count, entity_count, relation_count,
                   processed_text_path, chunks_path, extractions_path, graph_path, vector_store_path,
                   content_hash, duplicate_of_document_id, deleted_at, deleted_by, delete_reason,
                   cleanup_status, cleanup_detail, cleanup_completed_at
            FROM upload_audit
            WHERE content_hash = ?
              AND status = 'completed'
              AND coalesce(deleted_at, '') = ''
              AND coalesce(document_id, '') != ''
            ORDER BY datetime(completed_at) DESC, id DESC
            LIMIT 1
            """,
            (content_hash,),
        ).fetchone()
    return _row_to_upload(row) if row else None


def update_upload_metadata(job_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = {"title", "domain", "source_type", "source"}
    assignments = []
    values: List[Any] = []
    for key in allowed:
        if key in updates:
            assignments.append(f"{key} = ?")
            values.append(str(updates.get(key) or ""))
    if not assignments:
        return get_upload(job_id)

    now = _now()
    assignments.append("updated_at = ?")
    values.append(now)
    values.append(job_id)
    init_admin_db()
    with _LOCK, _connect() as db:
        db.execute(
            f"UPDATE upload_audit SET {', '.join(assignments)} WHERE job_id = ?",
            values,
        )
        db.commit()
    return get_upload(job_id)


def mark_upload_deleted(
    job_id: str,
    *,
    deleted_by: str = "",
    reason: str = "",
    status: str = "deleted",
    cleanup_status: str = "cleanup_pending",
    cleanup_detail: str = "",
) -> Optional[Dict[str, Any]]:
    now = _now()
    final_status = status if status in {"deleted", "deleted_with_warnings"} else "deleted"
    init_admin_db()
    with _LOCK, _connect() as db:
        current = db.execute(
            "SELECT document_id FROM upload_audit WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        document_id = current["document_id"] if current else ""
        db.execute(
            """
            UPDATE upload_audit
            SET status = ?,
                stage = 'deleted',
                progress = 100,
                updated_at = ?,
                deleted_at = ?,
                deleted_by = ?,
                delete_reason = ?,
                cleanup_status = ?,
                cleanup_detail = ?,
                cleanup_completed_at = CASE
                    WHEN ? IN ('cleanup_completed', 'cleanup_failed', 'cleanup_skipped') THEN ?
                    ELSE cleanup_completed_at
                END
            WHERE job_id = ?
            """,
            (final_status, now, now, deleted_by, reason, cleanup_status, cleanup_detail, cleanup_status, now, job_id),
        )
        if document_id:
            db.execute(
                """
                UPDATE upload_audit
                SET duplicate_of_document_id = '',
                    updated_at = ?
                WHERE duplicate_of_document_id = ?
                  AND job_id != ?
                """,
                (now, document_id, job_id),
            )
        db.commit()
    return get_upload(job_id)


def record_upload_cleanup(
    job_id: str,
    *,
    cleanup_status: str,
    cleanup_detail: str = "",
    status: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    now = _now()
    init_admin_db()
    with _LOCK, _connect() as db:
        if status:
            db.execute(
                """
                UPDATE upload_audit
                SET status = ?,
                    cleanup_status = ?,
                    cleanup_detail = ?,
                    cleanup_completed_at = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (status, cleanup_status, cleanup_detail, now, now, job_id),
            )
        else:
            db.execute(
                """
                UPDATE upload_audit
                SET cleanup_status = ?,
                    cleanup_detail = ?,
                    cleanup_completed_at = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (cleanup_status, cleanup_detail, now, now, job_id),
            )
        db.commit()
    return get_upload(job_id)


def _connect() -> sqlite3.Connection:
    db = sqlite3.connect(os.getenv("AUTH_DB_PATH", str(_DB_PATH)))
    db.row_factory = sqlite3.Row
    return db


def _ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_upload(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "document_id": row["document_id"],
        "title": row["title"],
        "filename": row["filename"],
        "domain": row["domain"],
        "source_type": row["source_type"],
        "source": row["source"],
        "uploader": {
            "id": row["uploader_id"],
            "email": row["uploader_email"],
            "username": row["uploader_username"],
        },
        "status": row["status"],
        "stage": row["stage"],
        "progress": int(row["progress"] or 0),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "error": row["error"],
        "content_hash": row["content_hash"] if "content_hash" in row.keys() else "",
        "duplicate_of_document_id": row["duplicate_of_document_id"] if "duplicate_of_document_id" in row.keys() else "",
        "deleted_at": row["deleted_at"] if "deleted_at" in row.keys() else "",
        "deleted_by": row["deleted_by"] if "deleted_by" in row.keys() else "",
        "delete_reason": row["delete_reason"] if "delete_reason" in row.keys() else "",
        "cleanup_status": row["cleanup_status"] if "cleanup_status" in row.keys() else "",
        "cleanup_detail": row["cleanup_detail"] if "cleanup_detail" in row.keys() else "",
        "cleanup_completed_at": row["cleanup_completed_at"] if "cleanup_completed_at" in row.keys() else "",
        "stats": {
            "chunks": int(row["chunk_count"] or 0),
            "entities": int(row["entity_count"] or 0),
            "relations": int(row["relation_count"] or 0),
        },
        "paths": {
            "processed_text_path": row["processed_text_path"],
            "chunks_path": row["chunks_path"],
            "extractions_path": row["extractions_path"],
            "graph_path": row["graph_path"],
            "vector_store_path": row["vector_store_path"],
        },
    }
