"""/matters/*: matter workspaces, membership, document links and the audit log (WP1-C).

Handlers are sync (the matter services use blocking SQLite) so FastAPI runs them in its
threadpool. Errors use the same top-level ``{"error", "message"}`` body as the other routers.
"""

from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import get_current_user
from services import audit
from services import matters as matter_service
from services.document_access import summarize_matter_documents

router = APIRouter()

_MAX_ATTACH_BATCH = 100


class MatterCreateRequest(BaseModel):
    name: str
    client_ref: str = ""
    description: str = ""
    org_id: Optional[str] = None


class MatterUpdateRequest(BaseModel):
    name: Optional[str] = None
    client_ref: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class MatterMemberRequest(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
    role: str = "member"


class MatterMemberRemoveRequest(BaseModel):
    user_id: str


class MatterDocumentsRequest(BaseModel):
    document_id: Optional[str] = None
    document_ids: List[str] = []


def _error_response(exc: HTTPException) -> JSONResponse:
    detail: Any = exc.detail
    if not isinstance(detail, dict):
        detail = {"error": "request_failed", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=detail)


@router.get("/matters")
def list_matters(include_archived: bool = Query(False), current_user: dict = Depends(get_current_user)):
    try:
        matter_service.ensure_personal_workspace(current_user)
        return {"matters": matter_service.list_matters(current_user, include_archived=include_archived)}
    except HTTPException as exc:
        return _error_response(exc)


@router.post("/matters")
def create_matter(request: MatterCreateRequest, current_user: dict = Depends(get_current_user)):
    try:
        matter = matter_service.create_matter(
            current_user,
            name=request.name,
            client_ref=request.client_ref,
            description=request.description,
            org_id=request.org_id,
        )
        return {"matter": matter}
    except HTTPException as exc:
        return _error_response(exc)


@router.get("/matters/{matter_id}")
def get_matter(matter_id: str, current_user: dict = Depends(get_current_user)):
    try:
        return {"matter": matter_service.get_matter_for_user(matter_id, current_user)}
    except HTTPException as exc:
        return _error_response(exc)


@router.patch("/matters/{matter_id}")
def update_matter(matter_id: str, request: MatterUpdateRequest, current_user: dict = Depends(get_current_user)):
    try:
        matter = matter_service.update_matter(
            matter_id,
            current_user,
            name=request.name,
            client_ref=request.client_ref,
            description=request.description,
            status=request.status,
        )
        return {"matter": matter}
    except HTTPException as exc:
        return _error_response(exc)


@router.delete("/matters/{matter_id}")
def archive_matter(matter_id: str, current_user: dict = Depends(get_current_user)):
    """Archives the matter (status ``archived``); matters are never hard-deleted."""
    try:
        return {"matter": matter_service.archive_matter(matter_id, current_user), "archived": True}
    except HTTPException as exc:
        return _error_response(exc)


@router.get("/matters/{matter_id}/members")
def list_members(matter_id: str, current_user: dict = Depends(get_current_user)):
    try:
        return {"members": matter_service.list_members(matter_id, current_user)}
    except HTTPException as exc:
        return _error_response(exc)


@router.post("/matters/{matter_id}/members")
def add_member(matter_id: str, request: MatterMemberRequest, current_user: dict = Depends(get_current_user)):
    """Add a registered user by ``user_id`` or ``email``, or change an existing member's role."""
    try:
        member = matter_service.add_member(
            matter_id,
            current_user,
            member_user_id=request.user_id,
            email=request.email,
            role=request.role,
        )
        return {"member": member}
    except HTTPException as exc:
        return _error_response(exc)


@router.delete("/matters/{matter_id}/members")
def remove_member(
    matter_id: str,
    user_id: Optional[str] = Query(None),
    request: Optional[MatterMemberRemoveRequest] = Body(None),
    current_user: dict = Depends(get_current_user),
):
    """Remove the member given as ``?user_id=`` (or a JSON body ``{"user_id"}``)."""
    try:
        target = (user_id or (request.user_id if request else "") or "").strip()
        return matter_service.remove_member(matter_id, current_user, target)
    except HTTPException as exc:
        return _error_response(exc)


@router.get("/matters/{matter_id}/documents")
def list_matter_documents(matter_id: str, current_user: dict = Depends(get_current_user)):
    try:
        matter_service.require_matter_member(matter_id, current_user, "viewer")
        return {"documents": summarize_matter_documents(matter_id)}
    except HTTPException as exc:
        return _error_response(exc)


@router.post("/matters/{matter_id}/documents")
def attach_documents(matter_id: str, request: MatterDocumentsRequest, current_user: dict = Depends(get_current_user)):
    """Attach existing documents (``document_id`` and/or ``document_ids``) the caller owns; all or none."""
    requested = [item.strip() for item in [request.document_id or "", *request.document_ids] if item and item.strip()]
    document_ids = list(dict.fromkeys(requested))
    if not document_ids:
        return JSONResponse(status_code=400, content={"error": "invalid_document", "message": "Give document_id or document_ids."})
    if len(document_ids) > _MAX_ATTACH_BATCH:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_document", "message": f"Attach at most {_MAX_ATTACH_BATCH} documents per request."},
        )
    try:
        return {"documents": matter_service.attach_documents(matter_id, document_ids, current_user)}
    except HTTPException as exc:
        return _error_response(exc)


@router.delete("/matters/{matter_id}/documents/{document_id}")
def detach_document(matter_id: str, document_id: str, current_user: dict = Depends(get_current_user)):
    try:
        return matter_service.detach_document(matter_id, document_id, current_user)
    except HTTPException as exc:
        return _error_response(exc)


@router.get("/matters/{matter_id}/audit")
def list_matter_audit(
    matter_id: str,
    limit: int = Query(100, ge=1, le=audit.MAX_LIST_LIMIT),
    before: Optional[int] = Query(None, ge=1),
    current_user: dict = Depends(get_current_user),
):
    """Audit events of the matter, newest first; page with ``before=<next_before>``. Lead or org admin."""
    try:
        matter_service.require_matter_manager(matter_id, current_user)
        events = audit.list_events(matter_id, limit=limit, before=before)
        next_before = events[-1]["id"] if len(events) == limit else None
        return {"events": events, "next_before": next_before}
    except HTTPException as exc:
        return _error_response(exc)
