from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import aiosqlite
import pytest
from fastapi import HTTPException

from app import (
    EmailCodeSendRequest,
    RegisterRequest,
    _CAPTCHA_STORE,
    _init_auth_db,
    register,
    send_email_code,
)


def test_register_rejects_missing_email_verification_code(tmp_path):
    asyncio.run(_register_rejects_missing_email_verification_code(tmp_path))


async def _register_rejects_missing_email_verification_code(tmp_path):
    db_path = tmp_path / "auth.db"
    with patch("app._DB_PATH", str(db_path)):
        await _init_auth_db()
        _CAPTCHA_STORE["captcha-missing-email-code"] = ("1234", time.time() + 300)
        async with aiosqlite.connect(db_path) as db:
            req = RegisterRequest(
                email="missing-code@example.com",
                username="Missing Code",
                password="pass123456",
                captcha_id="captcha-missing-email-code",
                captcha_code="1234",
            )

            with pytest.raises(HTTPException) as exc:
                await register(req, db)

    assert exc.value.status_code == 400
    assert "email verification" in str(exc.value.detail).lower()


def test_send_email_code_then_registers_with_matching_code(tmp_path):
    asyncio.run(_send_email_code_then_registers_with_matching_code(tmp_path))


async def _send_email_code_then_registers_with_matching_code(tmp_path):
    db_path = tmp_path / "auth.db"
    sent_codes: list[str] = []

    def capture_code(*, email: str, code: str) -> None:
        assert email == "verified@example.com"
        sent_codes.append(code)

    with patch("app._DB_PATH", str(db_path)), patch("app._deliver_email_verification_code", side_effect=capture_code):
        await _init_auth_db()
        _CAPTCHA_STORE["captcha-send-email-code"] = ("5678", time.time() + 300)

        async with aiosqlite.connect(db_path) as db:
            send_result = await send_email_code(
                EmailCodeSendRequest(
                    email="verified@example.com",
                    captcha_id="captcha-send-email-code",
                    captcha_code="5678",
                ),
                db,
            )

            assert send_result["sent"] is True
            assert len(sent_codes) == 1

            req = RegisterRequest(
                email="verified@example.com",
                username="Verified User",
                password="pass123456",
                captcha_id="captcha-send-email-code",
                captcha_code="5678",
                email_code=sent_codes[0],
            )
            response = await register(req, db)

    assert response["token"]
    assert response["user"]["email"] == "verified@example.com"
