"""/auth/*: captcha, email verification codes, registration, login, current user."""

from __future__ import annotations

import base64
import random
import string
import time
import uuid
from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_current_user, get_db
from services.auth import (
    _CAPTCHA_STORE,
    _CAPTCHA_TTL,
    _EMAIL_CODE_RESEND_COOLDOWN_SECONDS,
    _EMAIL_CODE_TTL_SECONDS,
    _assert_email_code_send_allowed,
    _check_pw,
    _cleanup_captchas,
    _consume_admin_invite,
    _deliver_email_verification_code,
    _gen_captcha_image,
    _generate_email_code,
    _hash_pw,
    _make_token,
    _normalize_email,
    _normalize_role,
    _store_email_code,
    _utc_now_iso,
    _validate_captcha,
    _verify_email_code,
)
from services.rate_limit import _attach_account_plan, _rag_account_plan

router = APIRouter()


class EmailCodeSendRequest(BaseModel):
    email: str
    captcha_id: str
    captcha_code: str


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    captcha_id: str
    captcha_code: str
    email_code: Optional[str] = None
    role: str = "user"
    admin_invite_code: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


@router.get("/auth/captcha")
async def get_captcha():
    _cleanup_captchas()
    code = "".join(random.choices(string.digits, k=4))
    captcha_id = str(uuid.uuid4())
    _CAPTCHA_STORE[captcha_id] = (code, time.time() + _CAPTCHA_TTL)
    img_b64 = base64.b64encode(_gen_captcha_image(code)).decode()
    return {"captcha_id": captcha_id, "image": f"data:image/png;base64,{img_b64}"}


@router.post("/auth/email-code/send")
async def send_email_code(req: EmailCodeSendRequest, db: aiosqlite.Connection = Depends(get_db)):
    _validate_captcha(req.captcha_id, req.captcha_code, consume=False)
    email = _normalize_email(req.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="A valid email address is required")
    cursor = await db.execute("SELECT id FROM users WHERE email = ?", (email,))
    if await cursor.fetchone():
        raise HTTPException(status_code=400, detail="Email already registered")
    await _assert_email_code_send_allowed(db, email, "register")
    code = _generate_email_code()
    await _store_email_code(db, email, code, "register")
    _deliver_email_verification_code(email=email, code=code)
    await db.commit()
    return {
        "sent": True,
        "ttl_seconds": _EMAIL_CODE_TTL_SECONDS,
        "cooldown_seconds": _EMAIL_CODE_RESEND_COOLDOWN_SECONDS,
    }


@router.post("/auth/register")
async def register(req: RegisterRequest, db: aiosqlite.Connection = Depends(get_db)):
    _validate_captcha(req.captcha_id, req.captcha_code, consume=True)
    email = _normalize_email(req.email)
    cursor = await db.execute("SELECT id FROM users WHERE email = ?", (email,))
    if await cursor.fetchone():
        raise HTTPException(status_code=400, detail="Email already registered")
    await _verify_email_code(db, email, req.email_code, "register")
    user_id = str(uuid.uuid4())
    role = _normalize_role(req.role)
    if role == "admin":
        await _consume_admin_invite(req.admin_invite_code or "", user_id, db)
    await db.execute(
        "INSERT INTO users (id, email, username, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
        (user_id, email, req.username, _hash_pw(req.password), role, _utc_now_iso()),
    )
    await db.commit()
    token = _make_token(user_id, email)
    user_payload = {
        "id": user_id,
        "email": email,
        "username": req.username,
        "role": role,
        "created_at": _utc_now_iso(),
    }
    return {
        "token": token,
        "user": _attach_account_plan(user_payload, await _rag_account_plan(db, user_payload)),
    }


@router.post("/auth/login")
async def login(req: LoginRequest, db: aiosqlite.Connection = Depends(get_db)):
    # Registration stores normalised emails; lower(email) also matches accounts created before that.
    cursor = await db.execute(
        "SELECT id, email, username, password_hash, role, created_at FROM users WHERE lower(email) = ?",
        (_normalize_email(req.email),),
    )
    row = await cursor.fetchone()
    if not row or not _check_pw(req.password, row[3]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = _make_token(row[0], row[1])
    user_payload = {
        "id": row[0],
        "email": row[1],
        "username": row[2],
        "role": _normalize_role(row[4]),
        "created_at": row[5],
    }
    return {
        "token": token,
        "user": _attach_account_plan(user_payload, await _rag_account_plan(db, user_payload)),
    }


@router.get("/auth/me")
async def me(current_user: dict = Depends(get_current_user), db: aiosqlite.Connection = Depends(get_db)):
    return _attach_account_plan(current_user, await _rag_account_plan(db, current_user))
