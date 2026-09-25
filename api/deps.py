"""FastAPI dependencies shared by the routers."""

from __future__ import annotations

import aiosqlite
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.auth import _decode_token, _normalize_role
from services.db import get_db

__all__ = ["get_current_user", "get_db", "get_optional_current_user", "require_admin"]


_security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: aiosqlite.Connection = Depends(get_db),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_token(credentials.credentials)
    user_id = payload.get("sub")
    cursor = await db.execute(
        "SELECT id, email, username, role, created_at FROM users WHERE id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return {"id": row[0], "email": row[1], "username": row[2], "role": _normalize_role(row[3]), "created_at": row[4]}


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: aiosqlite.Connection = Depends(get_db),
):
    if credentials is None:
        return None
    try:
        payload = _decode_token(credentials.credentials)
    except HTTPException:
        return None
    user_id = payload.get("sub")
    cursor = await db.execute(
        "SELECT id, email, username, role, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "username": row[2], "role": _normalize_role(row[3]), "created_at": row[4]}


def _is_local_request(request: Request) -> bool:
    if request.headers.get("x-forwarded-for") or request.headers.get("x-forwarded-host"):
        return False
    host_header = request.headers.get("host", "")
    if "ngrok" in host_header:
        return False
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


async def require_admin(current_user: dict = Depends(get_current_user)):
    if _normalize_role(current_user.get("role", "")) == "admin":
        return current_user
    raise HTTPException(status_code=403, detail="Admin access required")
