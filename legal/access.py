"""Fail-closed Max entitlement checks for HTTP and checkpointed review workers."""
from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
from fastapi import Depends, HTTPException

from api.deps import get_current_user
from services.db import get_db
from services.rate_limit import _rag_account_plan


def max_required():
    return HTTPException(403, {'error': 'legal_max_required', 'required_plan': 'max',
                               'message': '法务 Agent 仅向有效的 Max 用户开放，Free 和 Pro 用户暂不可使用。'})


async def access_status(user: dict, db) -> dict:
    plan = await _rag_account_plan(db, user)
    return {'allowed': plan.get('plan') == 'max', 'plan': plan.get('plan', 'free'), 'required_plan': 'max'}


async def require_legal_max(user: dict = Depends(get_current_user), db=Depends(get_db)) -> dict:
    if not (await access_status(user, db))['allowed']:
        raise max_required()
    return user


async def _check_worker(user_id: str):
    from services import db as database
    uri = Path(database._DB_PATH).resolve().as_uri() + '?mode=ro'
    async with aiosqlite.connect(uri, uri=True) as db:
        cursor = await db.execute('SELECT id, email, role FROM users WHERE id = ?', (user_id,))
        row = await cursor.fetchone()
        if row is None or not (await access_status({'id': row[0], 'email': row[1], 'role': row[2]}, db))['allowed']:
            raise max_required()


def assert_worker_max(user_id: str):
    # Runs in the existing worker thread, never on the request event loop. Re-read the
    # authoritative DB before each billable step so revocation also affects queued jobs.
    asyncio.run(_check_worker(user_id))
