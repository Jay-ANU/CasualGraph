"""Accounts: JWT, password hashing, captcha, email verification codes, admin invites, mail sending."""

from __future__ import annotations

import io
import os
import random
import secrets
import smtplib
import string
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite
import bcrypt
import jwt
from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import configs.settings  # noqa: F401  (loads .env before the module-level os.getenv() reads below)


# ── Auth config ──────────────────────────────────────────────────────────────
_DEFAULT_JWT_SECRET = "esg-demo-secret-change-in-prod"
_APP_ENV = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).strip().lower()
_JWT_SECRET = os.getenv("JWT_SECRET", _DEFAULT_JWT_SECRET).strip() or _DEFAULT_JWT_SECRET
_JWT_ALGORITHM = "HS256"
_TOKEN_MINUTES = 60 * 24  # 1 day


def _is_production_like_env(value: Optional[str] = None) -> bool:
    env = str(value if value is not None else _APP_ENV).strip().lower()
    return env in {"prod", "production", "staging"}


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


_MAIL_ENABLED = _env_flag("MAIL_ENABLED", "false")
_MAIL_SMTP_HOST = os.getenv("MAIL_SMTP_HOST", "").strip()
_MAIL_SMTP_PORT = int(os.getenv("MAIL_SMTP_PORT", "465"))
_MAIL_SMTP_SSL = _env_flag("MAIL_SMTP_SSL", "true")
_MAIL_SMTP_STARTTLS = _env_flag("MAIL_SMTP_STARTTLS", "false")
_MAIL_SMTP_USER = os.getenv("MAIL_SMTP_USER", "").strip()
_MAIL_SMTP_PASSWORD = os.getenv("MAIL_SMTP_PASSWORD", "").strip()
_MAIL_FROM = os.getenv("MAIL_FROM", _MAIL_SMTP_USER).strip()
_MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "CausalGraph AI").strip()
_EMAIL_CODE_TTL_SECONDS = max(60, int(os.getenv("EMAIL_CODE_TTL_SECONDS", "600")))
_EMAIL_CODE_RESEND_COOLDOWN_SECONDS = max(15, int(os.getenv("EMAIL_CODE_RESEND_COOLDOWN_SECONDS", "60")))
_EMAIL_CODE_MAX_ATTEMPTS = max(1, int(os.getenv("EMAIL_CODE_MAX_ATTEMPTS", "5")))
_EMAIL_CODE_LENGTH = max(4, int(os.getenv("EMAIL_CODE_LENGTH", "6")))


def _normalize_role(role: str) -> str:
    value = str(role or "").strip().lower()
    return value if value in {"admin", "user"} else "user"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_in_minutes_iso(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _utc_in_seconds_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _parse_utc_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_pw(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _hash_email_code(email: str, code: str) -> str:
    payload = f"{_normalize_email(email)}:{str(code).strip()}".encode()
    return bcrypt.hashpw(payload, bcrypt.gensalt()).decode()


def _check_email_code(email: str, code: str, hashed: str) -> bool:
    payload = f"{_normalize_email(email)}:{str(code).strip()}".encode()
    return bcrypt.checkpw(payload, hashed.encode())


def _make_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_MINUTES),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── Captcha ──────────────────────────────────────────────────────────────────
_CAPTCHA_STORE: Dict[str, Tuple[str, float]] = {}
_CAPTCHA_TTL = 300  # 5 minutes


def _gen_captcha_image(code: str) -> bytes:
    width, height = 160, 60
    img = Image.new("RGB", (width, height), color=(245, 245, 250))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
    except Exception:
        font = ImageFont.load_default()
    for i, char in enumerate(code):
        x = 18 + i * 30 + random.randint(-3, 3)
        y = 12 + random.randint(-6, 6)
        color = (random.randint(20, 80), random.randint(20, 80), random.randint(80, 150))
        draw.text((x, y), char, fill=color, font=font)
    for _ in range(5):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=(180, 180, 200), width=1)
    for _ in range(40):
        x, y = random.randint(0, width - 1), random.randint(0, height - 1)
        draw.point((x, y), fill=(150, 150, 180))
    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _cleanup_captchas():
    now = time.time()
    for key in [k for k, (_, exp) in _CAPTCHA_STORE.items() if exp < now]:
        _CAPTCHA_STORE.pop(key, None)


def _validate_captcha(captcha_id: str, captcha_code: str, *, consume: bool) -> None:
    _cleanup_captchas()
    stored = _CAPTCHA_STORE.get(str(captcha_id or ""))
    if not stored or stored[0] != str(captcha_code or "").strip():
        raise HTTPException(status_code=400, detail="Invalid or expired captcha")
    if consume:
        _CAPTCHA_STORE.pop(str(captcha_id or ""), None)


def _generate_email_code() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(_EMAIL_CODE_LENGTH))


async def _assert_email_code_send_allowed(db: aiosqlite.Connection, email: str, purpose: str) -> None:
    cursor = await db.execute(
        """
        SELECT last_sent_at
        FROM email_verification_codes
        WHERE email = ? AND purpose = ? AND consumed_at IS NULL
        ORDER BY datetime(last_sent_at) DESC
        LIMIT 1
        """,
        (_normalize_email(email), purpose),
    )
    row = await cursor.fetchone()
    if not row:
        return
    elapsed = (datetime.now(timezone.utc) - _parse_utc_iso(row[0])).total_seconds()
    if elapsed < _EMAIL_CODE_RESEND_COOLDOWN_SECONDS:
        retry_after = int(_EMAIL_CODE_RESEND_COOLDOWN_SECONDS - elapsed)
        raise HTTPException(
            status_code=429,
            detail=f"Email verification code was sent recently. Try again in {retry_after} seconds.",
        )


async def _store_email_code(db: aiosqlite.Connection, email: str, code: str, purpose: str) -> None:
    now = _utc_now_iso()
    await db.execute(
        """
        INSERT INTO email_verification_codes (
            id, email, purpose, code_hash, created_at, expires_at, consumed_at, attempts, last_sent_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            _normalize_email(email),
            purpose,
            _hash_email_code(email, code),
            now,
            _utc_in_seconds_iso(_EMAIL_CODE_TTL_SECONDS),
            None,
            0,
            now,
        ),
    )


async def _verify_email_code(db: aiosqlite.Connection, email: str, code: Optional[str], purpose: str) -> None:
    clean_code = str(code or "").strip()
    if not clean_code:
        raise HTTPException(status_code=400, detail="Email verification code is required")
    cursor = await db.execute(
        """
        SELECT id, code_hash, expires_at, attempts
        FROM email_verification_codes
        WHERE email = ? AND purpose = ? AND consumed_at IS NULL
        ORDER BY datetime(created_at) DESC
        LIMIT 1
        """,
        (_normalize_email(email), purpose),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or expired email verification code")
    if _parse_utc_iso(row[2]) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired email verification code")
    attempts = int(row[3] or 0)
    if attempts >= _EMAIL_CODE_MAX_ATTEMPTS:
        raise HTTPException(status_code=400, detail="Email verification code attempt limit exceeded")
    if not _check_email_code(email, clean_code, row[1]):
        await db.execute(
            "UPDATE email_verification_codes SET attempts = attempts + 1 WHERE id = ?",
            (row[0],),
        )
        raise HTTPException(status_code=400, detail="Invalid or expired email verification code")
    await db.execute(
        "UPDATE email_verification_codes SET consumed_at = ? WHERE id = ?",
        (_utc_now_iso(), row[0]),
    )


def _mail_missing_config() -> List[str]:
    return [
        name
        for name, value in {
            "MAIL_SMTP_HOST": _MAIL_SMTP_HOST,
            "MAIL_SMTP_USER": _MAIL_SMTP_USER,
            "MAIL_SMTP_PASSWORD": _MAIL_SMTP_PASSWORD,
            "MAIL_FROM": _MAIL_FROM,
        }.items()
        if not value
    ]


def _send_mail_message(message: EmailMessage) -> Dict[str, Any]:
    """Deliver through the configured SMTP server.

    Raises smtplib.SMTPException or OSError. Returns the recipients the server
    refused when it accepted at least one of them.
    """
    if _MAIL_SMTP_SSL:
        with smtplib.SMTP_SSL(_MAIL_SMTP_HOST, _MAIL_SMTP_PORT, timeout=15) as smtp:
            smtp.login(_MAIL_SMTP_USER, _MAIL_SMTP_PASSWORD)
            return smtp.send_message(message)
    with smtplib.SMTP(_MAIL_SMTP_HOST, _MAIL_SMTP_PORT, timeout=15) as smtp:
        if _MAIL_SMTP_STARTTLS:
            smtp.starttls()
        smtp.login(_MAIL_SMTP_USER, _MAIL_SMTP_PASSWORD)
        return smtp.send_message(message)


def _deliver_email_verification_code(*, email: str, code: str) -> None:
    if not _MAIL_ENABLED:
        if _is_production_like_env():
            raise HTTPException(status_code=503, detail="Email delivery is not configured")
        print(f"[email-verification] MAIL_ENABLED=false; code for {_normalize_email(email)}: {code}")
        return

    missing = _mail_missing_config()
    if missing:
        raise HTTPException(status_code=503, detail=f"Email delivery is missing configuration: {', '.join(missing)}")

    message = EmailMessage()
    message["Subject"] = "Your CausalGraph AI verification code"
    message["From"] = formataddr((_MAIL_FROM_NAME, _MAIL_FROM))
    message["To"] = _normalize_email(email)
    message.set_content(
        "\n".join(
            [
                "Your CausalGraph AI verification code is:",
                "",
                code,
                "",
                f"This code expires in {int(_EMAIL_CODE_TTL_SECONDS / 60)} minutes.",
                "If you did not request this code, you can ignore this email.",
            ]
        )
    )

    try:
        _send_mail_message(message)
    except smtplib.SMTPException as exc:
        raise HTTPException(status_code=502, detail="Email delivery failed") from exc


async def _consume_admin_invite(code: str, user_id: str, db: aiosqlite.Connection) -> None:
    invite_code = str(code or "").strip()
    if not invite_code:
        raise HTTPException(status_code=400, detail="Admin registration requires an invitation code")
    cursor = await db.execute(
        """
        SELECT id, expires_at, used_at
        FROM admin_invite_codes
        WHERE code = ?
        """,
        (invite_code,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid admin invitation code")
    if row[2]:
        raise HTTPException(status_code=400, detail="Admin invitation code has already been used")
    expires_at = datetime.fromisoformat(str(row[1]))
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Admin invitation code has expired")

    await db.execute(
        """
        UPDATE admin_invite_codes
        SET used_at = ?, used_by_user_id = ?
        WHERE id = ?
        """,
        (_utc_now_iso(), user_id, row[0]),
    )


def _is_admin_user(user: Optional[Dict[str, Any]]) -> bool:
    return _normalize_role((user or {}).get("role", "")) == "admin"
