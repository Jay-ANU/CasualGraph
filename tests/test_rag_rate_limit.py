from __future__ import annotations

import asyncio
from unittest.mock import patch

import aiosqlite
import pytest
from fastapi import HTTPException

from app import (
    RagUnlimitedUserRequest,
    _enforce_rag_rate_limit,
    _init_auth_db,
    add_rag_unlimited_user,
    delete_rag_unlimited_user,
    list_rag_unlimited_users,
)


def test_regular_user_deep_request_costs_five_points_and_blocks_when_daily_points_exhausted(tmp_path):
    asyncio.run(_regular_user_deep_request_costs_five_points_and_blocks_when_daily_points_exhausted(tmp_path))


async def _regular_user_deep_request_costs_five_points_and_blocks_when_daily_points_exhausted(tmp_path):
    db_path = tmp_path / "auth.db"
    user = {"id": "user-1", "role": "user"}

    with patch("app._DB_PATH", str(db_path)), patch("app._RAG_FREE_DAILY_POINTS", 6), patch(
        "app._RAG_MIN_SECONDS_BETWEEN_REQUESTS", 0
    ):
        await _init_auth_db()
        async with aiosqlite.connect(db_path) as db:
            first = await _enforce_rag_rate_limit(db, user, "deep")
            assert first["points_used"] == 5
            assert first["points_remaining"] == 1

            with pytest.raises(HTTPException) as exc:
                await _enforce_rag_rate_limit(db, user, "deep")

    assert exc.value.status_code == 429
    assert "Daily message limit reached" in str(exc.value.detail)


def test_admin_user_bypasses_rag_rate_limit(tmp_path):
    asyncio.run(_admin_user_bypasses_rag_rate_limit(tmp_path))


async def _admin_user_bypasses_rag_rate_limit(tmp_path):
    db_path = tmp_path / "auth.db"
    admin = {"id": "admin-1", "role": "admin"}

    with patch("app._DB_PATH", str(db_path)), patch("app._RAG_FREE_DAILY_POINTS", 1), patch(
        "app._RAG_MIN_SECONDS_BETWEEN_REQUESTS", 999
    ):
        await _init_auth_db()
        async with aiosqlite.connect(db_path) as db:
            result = await _enforce_rag_rate_limit(db, admin, "deep")

    assert result["bypassed"] is True


def test_whitelisted_user_gets_pro_daily_points_without_admin_permissions(tmp_path):
    asyncio.run(_whitelisted_user_gets_pro_daily_points_without_admin_permissions(tmp_path))


async def _whitelisted_user_gets_pro_daily_points_without_admin_permissions(tmp_path):
    db_path = tmp_path / "auth.db"
    user = {"id": "vip-1", "email": "VIP@Example.com", "role": "user"}

    with patch("app._DB_PATH", str(db_path)), patch("app._RAG_FREE_DAILY_POINTS", 1), patch(
        "app._RAG_PRO_DAILY_POINTS", 300
    ), patch(
        "app._RAG_MIN_SECONDS_BETWEEN_REQUESTS", 0
    ):
        await _init_auth_db()
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                """
                INSERT INTO rag_unlimited_users (email, note, created_by_user_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                ("vip@example.com", "partner demo", "admin-1", "2026-01-01T00:00:00+00:00"),
            )
            await db.commit()

            result = await _enforce_rag_rate_limit(db, user, "deep")

    assert result["bypassed"] is False
    assert result["plan"] == "pro"
    assert result["plan_label"] == "Pro"
    assert result["points_limit"] == 300
    assert result["points_used"] == 5
    assert result["points_remaining"] == 295


def test_admin_can_add_list_and_delete_rag_unlimited_users(tmp_path):
    asyncio.run(_admin_can_add_list_and_delete_rag_unlimited_users(tmp_path))


async def _admin_can_add_list_and_delete_rag_unlimited_users(tmp_path):
    db_path = tmp_path / "auth.db"
    admin = {"id": "admin-1", "email": "admin@example.com", "role": "admin"}

    with patch("app._DB_PATH", str(db_path)):
        await _init_auth_db()
        async with aiosqlite.connect(db_path) as db:
            created = await add_rag_unlimited_user(
                RagUnlimitedUserRequest(email=" VIP@Example.com ", note="partner demo"),
                admin,
                db,
            )
            listed = await list_rag_unlimited_users(admin, db)
            deleted = await delete_rag_unlimited_user("VIP%40Example.com", admin, db)
            listed_after_delete = await list_rag_unlimited_users(admin, db)

    assert created["user"]["email"] == "vip@example.com"
    assert created["user"]["note"] == "partner demo"
    assert [item["email"] for item in listed["users"]] == ["vip@example.com"]
    assert deleted["deleted"] is True
    assert listed_after_delete["users"] == []


def test_anonymous_rag_is_disabled_by_default(tmp_path):
    asyncio.run(_anonymous_rag_is_disabled_by_default(tmp_path))


async def _anonymous_rag_is_disabled_by_default(tmp_path):
    db_path = tmp_path / "auth.db"

    with patch("app._DB_PATH", str(db_path)), patch("app._RAG_ANONYMOUS_ENABLED", False):
        await _init_auth_db()
        async with aiosqlite.connect(db_path) as db:
            with pytest.raises(HTTPException) as exc:
                await _enforce_rag_rate_limit(db, None, "flash")

    assert exc.value.status_code == 401
