"""Daily RAG points per plan (Free / Pro / Max) and the per-request rate limit."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiosqlite
from fastapi import HTTPException

from services.auth import _env_flag, _is_admin_user, _normalize_email, _parse_utc_iso


_RAG_RATE_LIMIT_ENABLED = _env_flag("RAG_RATE_LIMIT_ENABLED", "true")
_RAG_FREE_DAILY_POINTS = max(1, int(os.getenv("RAG_FREE_DAILY_POINTS", "30")))
_RAG_PRO_DAILY_POINTS = max(1, int(os.getenv("RAG_PRO_DAILY_POINTS", "300")))
_RAG_FLASH_POINT_COST = max(1, int(os.getenv("RAG_FLASH_POINT_COST", "1")))
_RAG_DEEP_POINT_COST = max(1, int(os.getenv("RAG_DEEP_POINT_COST", "5")))
_RAG_MIN_SECONDS_BETWEEN_REQUESTS = max(0, int(os.getenv("RAG_MIN_SECONDS_BETWEEN_REQUESTS", "20")))
_RAG_ANONYMOUS_ENABLED = _env_flag("RAG_ANONYMOUS_ENABLED", "false")


def _rag_usage_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _rag_point_cost(reasoning_mode: Optional[str]) -> int:
    mode = str(reasoning_mode or "flash").strip().lower()
    return _RAG_DEEP_POINT_COST if mode == "deep" else _RAG_FLASH_POINT_COST


def _rag_limit_error(status_code: int, message: str, **extra: Any) -> HTTPException:
    detail = {"error": "rag_rate_limited", "message": message, **extra}
    return HTTPException(status_code=status_code, detail=detail)


async def _is_rag_pro_user(db: aiosqlite.Connection, current_user: Optional[Dict[str, Any]]) -> bool:
    email = _normalize_email(str((current_user or {}).get("email") or ""))
    if not email:
        return False
    cursor = await db.execute("SELECT 1 FROM rag_unlimited_users WHERE email = ?", (email,))
    return await cursor.fetchone() is not None


async def _rag_account_plan(db: aiosqlite.Connection, current_user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if _is_admin_user(current_user):
        return {"plan": "max", "plan_label": "Max", "points_limit": None, "unlimited": True}
    if await _is_rag_pro_user(db, current_user):
        return {"plan": "pro", "plan_label": "Pro", "points_limit": _RAG_PRO_DAILY_POINTS, "unlimited": False}
    return {"plan": "free", "plan_label": "Free", "points_limit": _RAG_FREE_DAILY_POINTS, "unlimited": False}


def _attach_account_plan(user: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    return {**user, **plan}


async def _enforce_rag_rate_limit(
    db: aiosqlite.Connection,
    current_user: Optional[Dict[str, Any]],
    reasoning_mode: Optional[str],
) -> Dict[str, Any]:
    if not _RAG_RATE_LIMIT_ENABLED:
        return {"bypassed": True, "reason": "disabled"}
    account_plan = await _rag_account_plan(db, current_user)
    if account_plan.get("unlimited"):
        return {"bypassed": True, "reason": "admin", **account_plan}
    if not current_user:
        if not _RAG_ANONYMOUS_ENABLED:
            raise _rag_limit_error(401, "Please sign in to use the AI agent.")
        user_id = "anonymous"
    else:
        user_id = str(current_user.get("id") or "").strip()
    if not user_id:
        raise _rag_limit_error(401, "Please sign in to use the AI agent.")

    mode = "deep" if str(reasoning_mode or "flash").strip().lower() == "deep" else "flash"
    cost = _rag_point_cost(mode)
    points_limit = int(account_plan.get("points_limit") or _RAG_FREE_DAILY_POINTS)
    usage_date = _rag_usage_date()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    cursor = await db.execute(
        """
        SELECT points_used, request_count, flash_count, deep_count, last_request_at
        FROM rag_rate_usage
        WHERE user_id = ? AND usage_date = ?
        """,
        (user_id, usage_date),
    )
    row = await cursor.fetchone()
    points_used = int(row[0] or 0) if row else 0
    request_count = int(row[1] or 0) if row else 0
    flash_count = int(row[2] or 0) if row else 0
    deep_count = int(row[3] or 0) if row else 0
    last_request_at = str(row[4] or "") if row else ""

    if last_request_at and _RAG_MIN_SECONDS_BETWEEN_REQUESTS > 0:
        elapsed = (now - _parse_utc_iso(last_request_at)).total_seconds()
        if elapsed < _RAG_MIN_SECONDS_BETWEEN_REQUESTS:
            retry_after = max(1, int(_RAG_MIN_SECONDS_BETWEEN_REQUESTS - elapsed))
            raise _rag_limit_error(
                429,
                f"Please wait {retry_after} seconds before sending another message.",
                retry_after_seconds=retry_after,
                plan=account_plan["plan"],
                plan_label=account_plan["plan_label"],
                points_limit=points_limit,
                points_used=points_used,
                points_remaining=max(0, points_limit - points_used),
            )

    if points_used + cost > points_limit:
        raise _rag_limit_error(
            429,
            "Daily message limit reached. Please try again tomorrow.",
            plan=account_plan["plan"],
            plan_label=account_plan["plan_label"],
            points_limit=points_limit,
            points_used=points_used,
            points_remaining=max(0, points_limit - points_used),
            points_required=cost,
            reset_at=f"{usage_date}T23:59:59+00:00",
        )

    new_points = points_used + cost
    new_request_count = request_count + 1
    new_flash_count = flash_count + (1 if mode == "flash" else 0)
    new_deep_count = deep_count + (1 if mode == "deep" else 0)
    await db.execute(
        """
        INSERT INTO rag_rate_usage (
            user_id, usage_date, points_used, request_count, flash_count, deep_count, last_request_at
        ) VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(user_id, usage_date) DO UPDATE SET
            points_used = excluded.points_used,
            request_count = excluded.request_count,
            flash_count = excluded.flash_count,
            deep_count = excluded.deep_count,
            last_request_at = excluded.last_request_at
        """,
        (user_id, usage_date, new_points, new_request_count, new_flash_count, new_deep_count, now_iso),
    )
    await db.commit()
    return {
        "bypassed": False,
        "plan": account_plan["plan"],
        "plan_label": account_plan["plan_label"],
        "mode": mode,
        "points_cost": cost,
        "points_limit": points_limit,
        "points_used": new_points,
        "points_remaining": max(0, points_limit - new_points),
        "request_count": new_request_count,
        "flash_count": new_flash_count,
        "deep_count": new_deep_count,
    }
