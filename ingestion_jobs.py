"""In-memory upload job tracking for long-running document ingestion."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

from admin_audit import (
    record_upload_completed,
    record_upload_created,
    record_upload_failed,
    record_upload_progress,
    record_upload_rejected,
)
from configs.settings import INGESTION_AUDIT_THROTTLE_SECONDS, INGESTION_JOB_MAX_WORKERS, INGESTION_MAX_QUEUED_JOBS
import document_registry
from pipeline_runtime import _build_duplicate_response, ingest_uploaded_document


_EXECUTOR = ThreadPoolExecutor(max_workers=INGESTION_JOB_MAX_WORKERS)
_LOCK = Lock()
_JOBS: Dict[str, Dict[str, Any]] = {}
_AUDIT_SNAPSHOTS: Dict[str, Dict[str, Any]] = {}


def start_ingestion_job(
    *,
    title: str,
    domain: str,
    source: str,
    content: str,
    filename: Optional[str],
    file_bytes: Optional[bytes],
    document_group: str = "user_upload",
    source_type: str = "",
    uploader: Optional[Dict[str, Any]] = None,
    owner_user_id: str = "",
    visibility_scope: str = "global",
) -> Dict[str, Any]:
    with _LOCK:
        active_or_queued = sum(1 for item in _JOBS.values() if item.get("status") in {"queued", "running"})
        if active_or_queued >= INGESTION_MAX_QUEUED_JOBS:
            raise RuntimeError(
                f"Upload queue is full ({active_or_queued}/{INGESTION_MAX_QUEUED_JOBS}). "
                "Please wait for the current document processing jobs to finish."
            )

    job_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    job = {
        "job_id": job_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "message": "Job queued",
        "created_at": now,
        "updated_at": now,
        "result": None,
        "error": None,
    }
    with _LOCK:
        _JOBS[job_id] = job
    try:
        record_upload_created(
            job_id=job_id,
            title=title,
            filename=filename,
            domain=domain,
            source_type=source_type,
            source=source,
            uploader=uploader,
        )
    except Exception as exc:
        print(f"[ingestion] Upload audit create failed for {job_id}: {type(exc).__name__}: {exc}")

    raw_hash = document_registry.compute_raw_hash(file_bytes, content)
    if raw_hash:
        existing = document_registry.lookup(
            raw_hash=raw_hash,
            text_hash=None,
            document_group=document_group,
            owner_user_id=owner_user_id,
        )
        if existing:
            duplicate_result = _build_duplicate_response(existing)
            _update_job(
                job_id,
                status="completed",
                stage="completed",
                progress=100,
                message="Duplicate detected; reusing existing document",
                result=duplicate_result,
            )
            try:
                record_upload_completed(job_id, duplicate_result)
            except Exception as audit_exc:
                print(f"[ingestion] Upload audit complete failed for {job_id}: {type(audit_exc).__name__}: {audit_exc}")
            with _LOCK:
                return dict(_JOBS[job_id])

    _EXECUTOR.submit(
        _run_job,
        job_id,
        title=title,
        domain=domain,
        source=source,
        content=content,
        filename=filename,
        file_bytes=file_bytes,
        document_group=document_group,
        source_type=source_type,
        owner_user_id=owner_user_id,
        visibility_scope=visibility_scope,
    )
    return dict(job)


def get_ingestion_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        snapshot = dict(job)
        if snapshot.get("status") == "queued":
            created_at = str(job.get("created_at") or "")
            ahead = 0
            for other_id, other in _JOBS.items():
                if other_id == job_id:
                    continue
                other_status = other.get("status")
                if other_status == "running":
                    ahead += 1
                elif other_status == "queued" and str(other.get("created_at") or "") < created_at:
                    ahead += 1
            position = ahead + 1
            snapshot["queue_position"] = position
            snapshot["queue_ahead"] = ahead
            if ahead == 0:
                snapshot["message"] = "Next in queue, starting shortly"
            else:
                snapshot["message"] = f"Waiting in queue (position {position}, {ahead} ahead)"
        return snapshot


def _run_job(
    job_id: str,
    *,
    title: str,
    domain: str,
    source: str,
    content: str,
    filename: Optional[str],
    file_bytes: Optional[bytes],
    document_group: str,
    source_type: str,
    owner_user_id: str,
    visibility_scope: str,
) -> None:
    _update_job(job_id, status="running", stage="starting", progress=1, message="Starting ingestion")

    def progress(stage: str, message: str, percent: int) -> None:
        _update_job(job_id, status="running", stage=stage, progress=percent, message=message)

    try:
        result = ingest_uploaded_document(
            title=title,
            domain=domain,
            source=source,
            content=content,
            filename=filename,
            file_bytes=file_bytes,
            document_group=document_group,
            source_type=source_type,
            owner_user_id=owner_user_id,
            visibility_scope=visibility_scope,
            progress_callback=progress,
        )
        if result.get("rejected"):
            message = str(result.get("message") or "Upload request was rejected")
            _update_job(
                job_id,
                status="rejected",
                stage="rejected",
                progress=100,
                message=message,
                result=result,
                error=message,
            )
            try:
                record_upload_rejected(job_id, reason=message, result=result)
            except Exception as audit_exc:
                print(f"[ingestion] Upload audit rejection failed for {job_id}: {type(audit_exc).__name__}: {audit_exc}")
            return

        _update_job(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            message="Document processing complete",
            result=result,
        )
        try:
            record_upload_completed(job_id, result)
        except Exception as audit_exc:
            print(f"[ingestion] Upload audit complete failed for {job_id}: {type(audit_exc).__name__}: {audit_exc}")
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            message="Document processing failed",
            error=str(exc),
        )
        try:
            record_upload_failed(job_id, str(exc))
        except Exception as audit_exc:
            print(f"[ingestion] Upload audit failure record failed for {job_id}: {type(audit_exc).__name__}: {audit_exc}")


def _update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    result: Any = None,
    error: Optional[str] = None,
) -> None:
    should_record_progress = False
    audit_payload: Dict[str, Any] = {}
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        if status is not None:
            job["status"] = status
        if stage is not None:
            job["stage"] = stage
        if progress is not None:
            job["progress"] = progress
        if message is not None:
            job["message"] = message
        if result is not None:
            job["result"] = result
        if error is not None:
            job["error"] = error
        job["updated_at"] = datetime.now(timezone.utc).isoformat()
        status_value = str(job.get("status") or "queued")
        stage_value = str(job.get("stage") or status_value)
        progress_value = int(job.get("progress") or 0)
        should_record_progress = _should_record_audit_progress(
            job_id=job_id,
            status=status_value,
            stage=stage_value,
            progress=progress_value,
            now_iso=str(job["updated_at"]),
        )
        audit_payload = {"status": status_value, "stage": stage_value, "progress": progress_value}
    if should_record_progress:
        try:
            record_upload_progress(job_id, **audit_payload)
        except Exception:
            pass


def _should_record_audit_progress(*, job_id: str, status: str, stage: str, progress: int, now_iso: str) -> bool:
    if status in {"completed", "failed", "rejected"}:
        _AUDIT_SNAPSHOTS[job_id] = {"status": status, "stage": stage, "progress": progress, "updated_at": now_iso}
        return True

    previous = _AUDIT_SNAPSHOTS.get(job_id)
    if previous is None:
        _AUDIT_SNAPSHOTS[job_id] = {"status": status, "stage": stage, "progress": progress, "updated_at": now_iso}
        return True

    if previous.get("status") != status or previous.get("stage") != stage:
        _AUDIT_SNAPSHOTS[job_id] = {"status": status, "stage": stage, "progress": progress, "updated_at": now_iso}
        return True

    if progress - int(previous.get("progress") or 0) >= 5:
        _AUDIT_SNAPSHOTS[job_id] = {"status": status, "stage": stage, "progress": progress, "updated_at": now_iso}
        return True

    try:
        last = datetime.fromisoformat(str(previous.get("updated_at")))
        current = datetime.fromisoformat(now_iso)
        if (current - last).total_seconds() >= INGESTION_AUDIT_THROTTLE_SECONDS:
            _AUDIT_SNAPSHOTS[job_id] = {"status": status, "stage": stage, "progress": progress, "updated_at": now_iso}
            return True
    except Exception:
        _AUDIT_SNAPSHOTS[job_id] = {"status": status, "stage": stage, "progress": progress, "updated_at": now_iso}
        return True

    return False
