"""/chat/sessions/*: short-term chat sessions (Redis)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import get_current_user
from chat_memory_service import RedisUnavailableError, chat_memory_service

router = APIRouter()


class ChatSessionCreateRequest(BaseModel):
    title: str = ""
    selected_document_id: str = ""
    mode: str = "ask"


class ChatSessionUpdateRequest(BaseModel):
    title: Optional[str] = None
    selected_document_id: Optional[str] = None
    mode: Optional[str] = None


class ChatSessionMessageRequest(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


@router.get("/chat/sessions")
async def list_chat_sessions(current_user: dict = Depends(get_current_user)):
    try:
        sessions = chat_memory_service.list_sessions(user_id=str(current_user["id"]))
        return JSONResponse(content={"sessions": sessions, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        return JSONResponse(
            content={"sessions": [], "warning": str(exc), "memory_backend": "disabled"},
        )


@router.post("/chat/sessions")
async def create_chat_session(
    request: ChatSessionCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        session = chat_memory_service.create_session(
            user_id=str(current_user["id"]),
            title=request.title,
            selected_document_id=request.selected_document_id,
            mode=request.mode,
        )
        return JSONResponse(content={"session": session, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        return JSONResponse(
            status_code=503,
            content={"error": "chat_memory_unavailable", "message": str(exc), "memory_backend": "disabled"},
        )


@router.get("/chat/sessions/{session_id}")
async def get_chat_session(session_id: str, current_user: dict = Depends(get_current_user)):
    try:
        payload = chat_memory_service.get_session(user_id=str(current_user["id"]), session_id=session_id, include_messages=True)
        return JSONResponse(content={**payload, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        status = 404 if "not found" in str(exc).lower() else 503
        return JSONResponse(
            status_code=status,
            content={"error": "chat_session_unavailable", "message": str(exc), "memory_backend": "disabled"},
        )


@router.patch("/chat/sessions/{session_id}")
async def update_chat_session(
    session_id: str,
    request: ChatSessionUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        session = chat_memory_service.update_session(
            user_id=str(current_user["id"]),
            session_id=session_id,
            title=request.title,
            selected_document_id=request.selected_document_id,
            mode=request.mode,
        )
        return JSONResponse(content={"session": session, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        status = 404 if "not found" in str(exc).lower() else 503
        return JSONResponse(
            status_code=status,
            content={"error": "chat_session_update_failed", "message": str(exc), "memory_backend": "disabled"},
        )


@router.post("/chat/sessions/{session_id}/messages")
async def append_chat_message(
    session_id: str,
    request: ChatSessionMessageRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        session = chat_memory_service.append_message(
            user_id=str(current_user["id"]),
            session_id=session_id,
            message=request.model_dump(),
        )
        return JSONResponse(content={"session": session, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        status = 404 if "not found" in str(exc).lower() else 503
        return JSONResponse(
            status_code=status,
            content={"error": "chat_message_append_failed", "message": str(exc), "memory_backend": "disabled"},
        )


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str, current_user: dict = Depends(get_current_user)):
    try:
        chat_memory_service.delete_session(user_id=str(current_user["id"]), session_id=session_id)
        return JSONResponse(content={"deleted": True, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        status = 404 if "not found" in str(exc).lower() else 503
        return JSONResponse(
            status_code=status,
            content={"error": "chat_session_delete_failed", "message": str(exc), "memory_backend": "disabled"},
        )
