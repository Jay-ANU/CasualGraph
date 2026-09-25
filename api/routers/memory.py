"""/memory/*: long-term user memory settings and entries."""

from __future__ import annotations

from typing import Literal, Optional

import aiosqlite
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.deps import get_current_user, get_db
from user_memory_service import (
    delete_user_memory,
    get_memory_settings,
    list_user_memories,
    update_memory_settings,
    update_user_memory,
)

router = APIRouter()


class MemorySettingsUpdateRequest(BaseModel):
    enabled: Optional[bool] = None
    auto_extract: Optional[bool] = None
    raw_retention_days: Optional[int] = Field(default=None, ge=1, le=365)


class MemoryUpdateRequest(BaseModel):
    category: Optional[str] = None
    content: Optional[str] = Field(default=None, min_length=1, max_length=420)
    sensitivity: Optional[Literal["normal", "sensitive"]] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


@router.get("/memory/settings")
async def get_long_term_memory_settings(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    settings = await get_memory_settings(db, str(current_user["id"]))
    return JSONResponse(content={"settings": settings, "memory_backend": "sqlite+vector"})


@router.patch("/memory/settings")
async def update_long_term_memory_settings(
    request: MemorySettingsUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    settings = await update_memory_settings(
        db,
        str(current_user["id"]),
        enabled=request.enabled,
        auto_extract=request.auto_extract,
        raw_retention_days=request.raw_retention_days,
    )
    return JSONResponse(content={"settings": settings, "memory_backend": "sqlite+vector"})


@router.get("/memory")
async def get_long_term_memories(
    category: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = Query(80, ge=1, le=300),
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    memories = await list_user_memories(
        db,
        str(current_user["id"]),
        category=category,
        include_deleted=include_deleted,
        limit=limit,
    )
    settings = await get_memory_settings(db, str(current_user["id"]))
    return JSONResponse(content={"memories": memories, "settings": settings, "memory_backend": "sqlite+vector"})


@router.patch("/memory/{memory_id}")
async def patch_long_term_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    memory = await update_user_memory(
        db,
        str(current_user["id"]),
        memory_id,
        category=request.category,
        content=request.content,
        sensitivity=request.sensitivity,
        confidence=request.confidence,
    )
    if memory is None:
        return JSONResponse(
            status_code=404,
            content={"error": "memory_not_found", "message": "No active memory found for this account."},
        )
    return JSONResponse(content={"memory": memory, "memory_backend": "sqlite+vector"})


@router.delete("/memory/{memory_id}")
async def remove_long_term_memory(
    memory_id: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    deleted = await delete_user_memory(db, str(current_user["id"]), memory_id)
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={"error": "memory_not_found", "message": "No active memory found for this account."},
        )
    return JSONResponse(content={"deleted": True, "memory_backend": "sqlite+vector"})
