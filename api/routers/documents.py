"""/documents/*: listing, upload (sync and async jobs), detail, delete, text ingestion."""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import document_registry
from admin_audit import (
    get_latest_upload_by_document_id,
    get_upload,
    list_latest_uploads_by_document_id,
    mark_upload_deleted,
    record_upload_cleanup,
)
from api.deps import get_current_user
from configs.settings import DATA_DIR
from ingestion_jobs import get_ingestion_job, start_ingestion_job
from pipeline_runtime import (
    delete_uploaded_document,
    ingest_uploaded_document,
    load_registered_document,
    summarize_registered_document,
)
from services.auth import _is_admin_user
from services.document_access import _can_access_entry, _collect_document_entries, _entry_from_upload

router = APIRouter()


_UPLOAD_SPOOL_DIR = DATA_DIR / "upload_spool"
_UPLOAD_SPOOL_CHUNK_BYTES = 1024 * 1024


async def _spool_upload_file(file: UploadFile) -> Tuple[str, str, int]:
    _UPLOAD_SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    suffix = re.sub(r"[^A-Za-z0-9.]", "", Path(file.filename or "").suffix.lower())[:24]
    path = _UPLOAD_SPOOL_DIR / f"{uuid.uuid4().hex}{suffix}"
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("wb") as handle:
            while True:
                chunk = await file.read(_UPLOAD_SPOOL_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                digest.update(chunk)
                handle.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return str(path), "sha256:" + digest.hexdigest(), size


def _remove_spooled_upload(file_path: Optional[str]) -> None:
    if not file_path:
        return
    try:
        Path(file_path).unlink(missing_ok=True)
    except Exception as exc:
        print(f"[documents] Failed to remove spooled upload {file_path}: {type(exc).__name__}: {exc}")


class ManualDocumentRequest(BaseModel):
    title: str
    content: str
    domain: str = "general"
    source: str = ""
    source_type: str = ""


@router.get("/documents")
async def list_documents(current_user: dict = Depends(get_current_user)):
    try:
        audit_index = list_latest_uploads_by_document_id()
        entries = [entry for entry in _collect_document_entries() if _can_access_entry(current_user, entry)]
        documents: List[Dict[str, Any]] = []
        for entry in entries:
            document_id = str(entry.get("document_id") or "").strip()
            if not document_id:
                continue
            audit = audit_index.get(document_id)
            if audit and str(audit.get("status") or "") in {"deleted", "deleted_with_warnings"}:
                continue
            try:
                documents.append(summarize_registered_document(entry, audit=audit))
            except Exception as exc:
                print(f"[documents] Summary load failed for {document_id}: {type(exc).__name__}: {exc}")
        return JSONResponse(content={"documents": documents})
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "document_list_failed", "message": str(exc)},
        )


@router.post("/documents/upload")
async def upload_document(
    title: str = Form(""),
    domain: str = Form("general"),
    source_type: str = Form(""),
    source: str = Form(""),
    content: str = Form(""),
    file: Optional[UploadFile] = File(default=None),
    current_user: dict = Depends(get_current_user),
):
    file_path: Optional[str] = None
    try:
        raw_hash: Optional[str] = None
        if file is not None:
            file_path, raw_hash, _ = await _spool_upload_file(file)
        is_admin = _is_admin_user(current_user)
        document_group = "global_kb" if is_admin else "user_private"
        visibility_scope = "global" if is_admin else "private"
        try:
            result = ingest_uploaded_document(
                title=title or (file.filename if file else "Uploaded document"),
                domain=domain,
                source=source,
                source_type=source_type,
                content=content,
                filename=file.filename if file else None,
                file_bytes=None,
                file_path=file_path,
                raw_hash=raw_hash,
                document_group=document_group,
                owner_user_id=str(current_user.get("id") or ""),
                visibility_scope=visibility_scope,
            )
        finally:
            _remove_spooled_upload(file_path)
        return JSONResponse(content=result)
    except Exception as exc:
        _remove_spooled_upload(file_path)
        return JSONResponse(
            status_code=400,
            content={"error": "document_upload_failed", "message": str(exc)},
        )


@router.post("/documents/upload-async")
async def upload_document_async(
    title: str = Form(""),
    domain: str = Form("general"),
    source_type: str = Form(""),
    source: str = Form(""),
    content: str = Form(""),
    file: Optional[UploadFile] = File(default=None),
    current_user: dict = Depends(get_current_user),
):
    file_path: Optional[str] = None
    try:
        raw_hash: Optional[str] = None
        if file is not None:
            file_path, raw_hash, _ = await _spool_upload_file(file)
        is_admin = _is_admin_user(current_user)
        document_group = "global_kb" if is_admin else "user_private"
        visibility_scope = "global" if is_admin else "private"
        try:
            job = start_ingestion_job(
                title=title or (file.filename if file else "Uploaded document"),
                domain=domain,
                source=source,
                source_type=source_type,
                content=content,
                filename=file.filename if file else None,
                file_bytes=None,
                file_path=file_path,
                raw_hash=raw_hash,
                document_group=document_group,
                uploader=current_user,
                owner_user_id=str(current_user.get("id") or ""),
                visibility_scope=visibility_scope,
            )
        except Exception:
            _remove_spooled_upload(file_path)
            raise
        return JSONResponse(content=job)
    except Exception as exc:
        _remove_spooled_upload(file_path)
        return JSONResponse(
            status_code=400,
            content={"error": "document_upload_failed", "message": str(exc)},
        )


@router.get("/documents/jobs/{job_id}")
async def get_document_job(job_id: str, current_user: dict = Depends(get_current_user)):
    upload = get_upload(job_id)
    if upload is not None and not _is_admin_user(current_user):
        uploader = upload.get("uploader") or {}
        if str(uploader.get("id") or "").strip() != str(current_user.get("id") or "").strip():
            return JSONResponse(
                status_code=403,
                content={"error": "job_forbidden", "message": "You do not have access to this ingestion job."},
            )
    job = get_ingestion_job(job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error": "job_not_found", "message": f"No ingestion job found for id {job_id}."},
        )
    return JSONResponse(content=job)


@router.get("/documents/{document_id}")
async def get_document(document_id: str, current_user: dict = Depends(get_current_user)):
    try:
        entry = document_registry.get_entry(document_id, valid_only=True)
        audit = get_latest_upload_by_document_id(document_id)
        if entry is None and audit is not None:
            entry = _entry_from_upload(audit)
        if entry is None:
            return JSONResponse(
                status_code=404,
                content={"error": "document_not_found", "message": f"No document found for id {document_id}."},
            )
        if not _can_access_entry(current_user, entry):
            return JSONResponse(
                status_code=403,
                content={"error": "document_forbidden", "message": "You do not have access to this document."},
            )
        if audit and str(audit.get("status") or "") in {"deleted", "deleted_with_warnings"}:
            return JSONResponse(
                status_code=404,
                content={"error": "document_not_found", "message": f"No document found for id {document_id}."},
            )
        return JSONResponse(content={"document": load_registered_document(entry, audit=audit)})
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "document_load_failed", "message": str(exc)},
        )


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, current_user: dict = Depends(get_current_user)):
    try:
        entry = document_registry.get_entry(document_id, valid_only=False)
        audit = get_latest_upload_by_document_id(document_id)
        if entry is None and audit is not None:
            entry = _entry_from_upload(audit)
        if entry is None:
            return JSONResponse(
                status_code=404,
                content={"error": "document_not_found", "message": f"No document found for id {document_id}."},
            )
        if not _can_access_entry(current_user, entry):
            return JSONResponse(
                status_code=403,
                content={"error": "document_forbidden", "message": "You do not have access to this document."},
            )
        if not _is_admin_user(current_user):
            entry_owner = str(entry.get("owner_user_id") or "").strip()
            if entry_owner != str(current_user.get("id") or "").strip():
                return JSONResponse(
                    status_code=403,
                    content={"error": "document_forbidden", "message": "Only admins can delete global knowledge base documents."},
                )
        if audit and str(audit.get("status") or "") in {"deleted", "deleted_with_warnings"}:
            return JSONResponse(
                status_code=404,
                content={"error": "document_not_found", "message": f"No document found for id {document_id}."},
            )

        upload = audit or {
            "document_id": document_id,
            "status": "completed",
            "paths": {
                "processed_text_path": str((entry.get("paths") or {}).get("processed_text") or ""),
                "chunks_path": str((entry.get("paths") or {}).get("chunks") or ""),
                "extractions_path": str((entry.get("paths") or {}).get("extractions") or ""),
                "graph_path": str((entry.get("paths") or {}).get("graph") or ""),
                "vector_store_path": str((entry.get("paths") or {}).get("vector_store") or ""),
            },
        }

        if audit:
            mark_upload_deleted(
                audit["job_id"],
                deleted_by=str(current_user.get("email") or current_user.get("username") or ""),
                reason="user_deleted",
                status="deleted",
                cleanup_status="cleanup_pending",
                cleanup_detail="User deletion in progress.",
            )

        cleanup = delete_uploaded_document(upload)
        document_registry.remove(document_id)

        warnings = list(cleanup.get("warnings") or [])
        neo4j_result = cleanup.get("neo4j") or {}
        if neo4j_result.get("enabled") and neo4j_result.get("deleted") is False and neo4j_result.get("reason") not in {
            "missing_document_id",
        }:
            warnings.append(f"neo4j: {neo4j_result.get('reason') or 'delete_not_confirmed'}")

        if audit:
            if warnings:
                record_upload_cleanup(
                    audit["job_id"],
                    cleanup_status="cleanup_failed",
                    cleanup_detail=f"Cleanup warnings: {'; '.join(warnings[:5])}",
                    status="deleted_with_warnings",
                )
            else:
                deleted_count = len(cleanup.get("deleted_paths") or [])
                record_upload_cleanup(
                    audit["job_id"],
                    cleanup_status="cleanup_completed",
                    cleanup_detail=f"Deleted {deleted_count} local path(s). Neo4j: {neo4j_result.get('reason') or neo4j_result.get('deleted')}.",
                    status="deleted",
                )

        return JSONResponse(
            content={
                "deleted": True,
                "document_id": document_id,
                "cleanup": cleanup,
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "document_delete_failed", "message": str(exc)},
        )


@router.post("/documents/ingest-text")
async def ingest_text_document(request: ManualDocumentRequest, current_user: dict = Depends(get_current_user)):
    try:
        is_admin = _is_admin_user(current_user)
        result = ingest_uploaded_document(
            title=request.title,
            domain=request.domain,
            source=request.source,
            source_type=request.source_type,
            content=request.content,
            document_group="global_kb" if is_admin else "user_private",
            owner_user_id=str(current_user.get("id") or ""),
            visibility_scope="global" if is_admin else "private",
        )
        return JSONResponse(content=result)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "document_ingest_failed", "message": str(exc)},
        )
