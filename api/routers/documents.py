"""/documents/*: listing, upload (sync and async jobs), detail, delete, text ingestion."""

from __future__ import annotations

import hashlib
import inspect
import re
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
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
from services import matters as matter_service
from services.auth import _is_admin_user
from services.document_access import (
    _can_access_entry,
    _collect_document_entries,
    _entry_from_upload,
    _MatterDocumentIndex,
    _owner_rules_allow_access,
    summarize_matter_documents,
)

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


def _error_response(exc: HTTPException) -> JSONResponse:
    detail: Any = exc.detail
    if not isinstance(detail, dict):
        detail = {"error": "request_failed", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=detail)


def _accepts_keyword(func: Callable[..., Any], name: str) -> bool:
    try:
        parameter = inspect.signature(func).parameters.get(name)
    except (TypeError, ValueError):
        return False
    return parameter is not None and parameter.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)


def _matter_kwargs(func: Callable[..., Any], matter_id: str) -> Dict[str, str]:
    """``{"matter_id": ...}`` only when the ingestion entry point takes it (WP1-A adds the parameter)."""
    return {"matter_id": matter_id} if matter_id and _accepts_keyword(func, "matter_id") else {}


def _upload_target_matter(current_user: dict, matter_id: Optional[str]) -> str:
    """The matter an upload lands in: the requested one (role ``member``, not archived) or else the
    caller's default matter. Raises ``HTTPException`` for a requested matter the caller may not use;
    a failure to provision the default matter only costs the link (the migration files it later)."""
    requested = str(matter_id or "").strip()
    if requested:
        matter_service.require_matter_member(requested, current_user, "member", require_active=True)
        return requested
    try:
        return matter_service.ensure_personal_workspace(current_user)["matter_id"]
    except Exception as exc:
        print(f"[documents] Default matter unavailable; upload stays unfiled: {type(exc).__name__}")
        return ""


def _link_ingested_document(result: Any, matter_id: str, current_user: dict) -> None:
    """After a synchronous ingest: link the (new or deduplicated) document and audit the upload."""
    document_id = matter_service.result_document_id(result)
    if not matter_id or not document_id or result.get("rejected"):
        return
    try:
        matter_service.link_uploaded_document(
            matter_id,
            document_id,
            actor_user_id=str(current_user.get("id") or ""),
            details=matter_service.upload_audit_details(result),
        )
        result["matter_id"] = matter_id
    except Exception as exc:
        print(f"[documents] Matter link failed for an uploaded document: {type(exc).__name__}")
        result["matter_link_failed"] = True


def _link_started_job(job: Dict[str, Any], matter_id: str, current_user: dict) -> None:
    """After ``start_ingestion_job``: link now when the job already knows its document (a duplicate
    finished on the spot, or a reserved ``document_id``); otherwise remember the job so its result
    is linked when the finished job is first read from ``GET /documents/jobs/{job_id}``."""
    job_id = str(job.get("job_id") or "").strip()
    if not matter_id or not job_id:
        return
    user_id = str(current_user.get("id") or "")
    reserved_document_id = str(job.get("document_id") or "").strip()
    try:
        if reserved_document_id:
            matter_service.link_uploaded_document(
                matter_id,
                reserved_document_id,
                actor_user_id=user_id,
                details={"job_id": job_id},
            )
        matter_service.remember_pending_upload(
            job_id,
            matter_id=matter_id,
            user_id=user_id,
            linked_document_id=reserved_document_id,
        )
        matter_service.link_finished_upload(job)
        job["matter_id"] = matter_id
    except Exception as exc:
        print(f"[documents] Matter link failed for ingestion job {job_id}: {type(exc).__name__}")
        job["matter_link_failed"] = True


class ManualDocumentRequest(BaseModel):
    title: str
    content: str
    domain: str = "general"
    source: str = ""
    source_type: str = ""
    matter_id: Optional[str] = None


@router.get("/documents")
async def list_documents(
    matter_id: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    try:
        matter_value = str(matter_id or "").strip()
        if matter_value:
            try:
                matter_service.require_matter_member(matter_value, current_user, "viewer")
            except HTTPException as exc:
                return _error_response(exc)
            return JSONResponse(content={"documents": summarize_matter_documents(matter_value)})
        audit_index = list_latest_uploads_by_document_id()
        shared = _MatterDocumentIndex(current_user)
        entries = [
            entry
            for entry in _collect_document_entries()
            if _can_access_entry(current_user, entry, matter_document_ids=shared)
        ]
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
    matter_id: str = Form(""),
    file: Optional[UploadFile] = File(default=None),
    current_user: dict = Depends(get_current_user),
):
    try:
        target_matter_id = _upload_target_matter(current_user, matter_id)
    except HTTPException as exc:
        return _error_response(exc)
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
                **_matter_kwargs(ingest_uploaded_document, target_matter_id),
            )
        finally:
            _remove_spooled_upload(file_path)
        _link_ingested_document(result, target_matter_id, current_user)
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
    matter_id: str = Form(""),
    file: Optional[UploadFile] = File(default=None),
    current_user: dict = Depends(get_current_user),
):
    try:
        target_matter_id = _upload_target_matter(current_user, matter_id)
    except HTTPException as exc:
        return _error_response(exc)
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
                **_matter_kwargs(start_ingestion_job, target_matter_id),
            )
        except Exception:
            _remove_spooled_upload(file_path)
            raise
        _link_started_job(job, target_matter_id, current_user)
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
    # ingestion_jobs has no completion callback: an async upload into a matter is linked the
    # first time its finished job is read here (the upload page polls until it finishes).
    try:
        linked = matter_service.link_finished_upload(job)
    except Exception as exc:
        print(f"[documents] Matter link failed for ingestion job {job_id}: {type(exc).__name__}")
        linked = None
    if linked:
        job = {**job, "matter_id": linked["matter_id"]}
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
                message = (
                    "Only admins can delete global knowledge base documents."
                    if _owner_rules_allow_access(current_user, entry)
                    else "Only the document's owner can delete it; remove it from the matter instead."
                )
                return JSONResponse(status_code=403, content={"error": "document_forbidden", "message": message})
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
        try:
            detached_matter_ids = matter_service.detach_deleted_document(
                document_id,
                actor_user_id=str(current_user.get("id") or ""),
            )
        except Exception as exc:
            print(f"[documents] Matter detach failed after deleting a document: {type(exc).__name__}")
            detached_matter_ids = []

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
                "detached_matter_count": len(detached_matter_ids),
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
        target_matter_id = _upload_target_matter(current_user, request.matter_id)
    except HTTPException as exc:
        return _error_response(exc)
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
            **_matter_kwargs(ingest_uploaded_document, target_matter_id),
        )
        _link_ingested_document(result, target_matter_id, current_user)
        return JSONResponse(content=result)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "document_ingest_failed", "message": str(exc)},
        )
