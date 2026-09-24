"""/admin/*: dashboard, upload audit, invite codes and the unlimited-plan allowlist."""

from __future__ import annotations

import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Tuple
from urllib.parse import unquote

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import document_registry
from admin_audit import (
    admin_overview,
    get_upload,
    list_uploads,
    mark_upload_deleted,
    record_upload_cleanup,
    update_upload_metadata,
)
from api.deps import get_db, require_admin
from pipeline_runtime import delete_uploaded_document
from services.auth import _normalize_email, _utc_in_minutes_iso, _utc_now_iso

router = APIRouter()


class AdminInviteCreateRequest(BaseModel):
    ttl_minutes: int = 5


class RagUnlimitedUserRequest(BaseModel):
    email: str
    note: Optional[str] = ""


_CLEANUP_EXECUTOR = ThreadPoolExecutor(max_workers=1)


@router.get("/admin/overview")
async def admin_dashboard_overview(
    days: int = Query(default=14, ge=1, le=90),
    current_user: dict = Depends(require_admin),
):
    return JSONResponse(content=admin_overview(days=days))


@router.get("/admin/uploads")
async def admin_uploads(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_admin),
):
    return JSONResponse(content={"uploads": list_uploads(limit=limit, offset=offset)})


@router.post("/admin/invite-codes")
async def create_admin_invite_code(
    request: AdminInviteCreateRequest,
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    ttl_minutes = max(1, min(int(request.ttl_minutes), 5))
    code = f"ADM-{secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:10].upper()}"
    invite_id = str(uuid.uuid4())
    now = _utc_now_iso()
    expires_at = _utc_in_minutes_iso(ttl_minutes)
    await db.execute(
        """
        INSERT INTO admin_invite_codes (
            id, code, created_by_user_id, created_at, expires_at, used_at, used_by_user_id
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL)
        """,
        (invite_id, code, str(current_user.get("id") or ""), now, expires_at),
    )
    await db.commit()
    return {
        "invite_code": code,
        "expires_at": expires_at,
        "ttl_minutes": ttl_minutes,
        "single_use": True,
    }


def _rag_unlimited_user_payload(row: Tuple[Any, ...]) -> Dict[str, Any]:
    return {
        "email": row[0],
        "note": row[1],
        "created_by_user_id": row[2],
        "created_at": row[3],
    }


@router.get("/admin/rag-unlimited-users")
async def list_rag_unlimited_users(
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    cursor = await db.execute(
        """
        SELECT email, note, created_by_user_id, created_at
        FROM rag_unlimited_users
        ORDER BY lower(email)
        """
    )
    rows = await cursor.fetchall()
    return {"users": [_rag_unlimited_user_payload(row) for row in rows]}


@router.post("/admin/rag-unlimited-users")
async def add_rag_unlimited_user(
    request: RagUnlimitedUserRequest,
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    email = _normalize_email(request.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required")
    note = str(request.note or "").strip()[:240]
    await db.execute(
        """
        INSERT INTO rag_unlimited_users (email, note, created_by_user_id, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(email) DO UPDATE SET
            note = excluded.note,
            created_by_user_id = excluded.created_by_user_id,
            created_at = excluded.created_at
        """,
        (email, note, str(current_user.get("id") or ""), _utc_now_iso()),
    )
    await db.commit()
    cursor = await db.execute(
        """
        SELECT email, note, created_by_user_id, created_at
        FROM rag_unlimited_users
        WHERE email = ?
        """,
        (email,),
    )
    row = await cursor.fetchone()
    return {"user": _rag_unlimited_user_payload(row)}


@router.delete("/admin/rag-unlimited-users/{email}")
async def delete_rag_unlimited_user(
    email: str,
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(get_db),
):
    normalized_email = _normalize_email(unquote(email))
    cursor = await db.execute("DELETE FROM rag_unlimited_users WHERE email = ?", (normalized_email,))
    await db.commit()
    return {"deleted": cursor.rowcount > 0, "email": normalized_email}


class AdminUploadUpdateRequest(BaseModel):
    title: Optional[str] = None
    domain: Optional[str] = None
    source_type: Optional[str] = None
    source: Optional[str] = None


@router.patch("/admin/uploads/{job_id}")
async def admin_update_upload(
    job_id: str,
    request: AdminUploadUpdateRequest,
    current_user: dict = Depends(require_admin),
):
    updates = request.dict(exclude_unset=True)
    updated = update_upload_metadata(job_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Upload record not found")
    document_id = str(updated.get("document_id") or "").strip()
    if document_id:
        document_registry.update_metadata(document_id, updates)
    return JSONResponse(content={"upload": updated})


@router.delete("/admin/uploads/{job_id}")
async def admin_delete_upload(
    job_id: str,
    reason: str = Query(default=""),
    current_user: dict = Depends(require_admin),
):
    upload = get_upload(job_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload record not found")
    status = str(upload.get("status") or "")
    if status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Running or queued uploads cannot be deleted until processing finishes")
    deleted = mark_upload_deleted(
        job_id,
        deleted_by=str(current_user.get("email") or current_user.get("username") or ""),
        reason=reason,
        status="deleted",
        cleanup_status="cleanup_skipped" if status == "rejected" else "cleanup_pending",
        cleanup_detail="Rejected upload has no indexed resources." if status == "rejected" else "Cleanup queued.",
    )
    if deleted is None:
        raise HTTPException(status_code=404, detail="Upload record not found")
    if status != "rejected":
        _CLEANUP_EXECUTOR.submit(
            _cleanup_deleted_upload,
            job_id,
            upload,
            str(current_user.get("email") or current_user.get("username") or ""),
            reason,
        )
    return JSONResponse(
        content={
            "upload": deleted,
            "cleanup": {
                "queued": status != "rejected",
                "warnings": [],
                "neo4j": {"enabled": False, "deleted": False, "reason": "background_cleanup_queued"},
            },
        }
    )


def _cleanup_deleted_upload(job_id: str, upload: Dict[str, Any], deleted_by: str, reason: str) -> None:
    try:
        cleanup = delete_uploaded_document(upload)
        document_id = str(upload.get("document_id") or "").strip()
        if document_id:
            document_registry.remove(document_id)
        warnings = list(cleanup.get("warnings") or [])
        neo4j_result = cleanup.get("neo4j") or {}
        if neo4j_result.get("enabled") and neo4j_result.get("deleted") is False and neo4j_result.get("reason") not in {
            "missing_document_id",
        }:
            warnings.append(f"neo4j: {neo4j_result.get('reason') or 'delete_not_confirmed'}")
        if warnings:
            record_upload_cleanup(
                job_id,
                cleanup_status="cleanup_failed",
                cleanup_detail=f"Cleanup warnings: {'; '.join(warnings[:5])}",
                status="deleted_with_warnings",
            )
        else:
            deleted_count = len(cleanup.get("deleted_paths") or [])
            record_upload_cleanup(
                job_id,
                cleanup_status="cleanup_completed",
                cleanup_detail=f"Deleted {deleted_count} local path(s). Neo4j: {neo4j_result.get('reason') or neo4j_result.get('deleted')}.",
                status="deleted",
            )
    except Exception as exc:
        record_upload_cleanup(
            job_id,
            cleanup_status="cleanup_failed",
            cleanup_detail=f"Cleanup failed: {type(exc).__name__}: {exc}",
            status="deleted_with_warnings",
        )
