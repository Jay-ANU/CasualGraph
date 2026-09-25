"""Administrator-managed Max access. Grants never alter the user's admin role."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import require_admin
from services.db import get_db
from services.auth import _normalize_email
from services.max_membership import init_max_memberships

router = APIRouter(prefix='/admin/max-memberships', tags=['membership'], dependencies=[Depends(require_admin)])


class MembershipRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    expires_at: datetime | None = None
    note: str = Field(default='', max_length=500)
    expected_version: int = Field(default=0, ge=0)


@router.get('')
async def list_memberships(db=Depends(get_db)):
    await init_max_memberships(db)
    cursor = await db.execute('''SELECT m.user_id, u.email, m.expires_at, m.note, m.updated_at, m.version
        FROM max_memberships m JOIN users u ON u.id=m.user_id ORDER BY m.updated_at DESC LIMIT 500''')
    keys = ('user_id', 'email', 'expires_at', 'note', 'updated_at', 'version')
    return {'memberships': [dict(zip(keys, row)) for row in await cursor.fetchall()]}


@router.put('')
async def grant_membership(request: MembershipRequest, user=Depends(require_admin), db=Depends(get_db)):
    if request.expires_at is not None and (request.expires_at.tzinfo is None or request.expires_at <= datetime.now(timezone.utc)):
        raise HTTPException(422, '到期时间必须是带时区的未来时间。')
    email = _normalize_email(request.email)
    cursor = await db.execute('SELECT id FROM users WHERE lower(email)=?', (email,))
    row = await cursor.fetchone()
    if row is None:
        raise HTTPException(404, '该邮箱尚未注册，不会自动创建账号。')
    await init_max_memberships(db)
    uid, now = row[0], datetime.now(timezone.utc).isoformat()
    expiry = request.expires_at.astimezone(timezone.utc).isoformat() if request.expires_at else None
    try:
        if request.expected_version == 0:
            cursor = await db.execute('''INSERT INTO max_memberships(user_id,expires_at,note,granted_by,updated_at,version)
                VALUES(?,?,?,?,?,1) ON CONFLICT(user_id) DO NOTHING''', (uid, expiry, request.note, user['id'], now))
        else:
            cursor = await db.execute('''UPDATE max_memberships SET expires_at=?,note=?,granted_by=?,updated_at=?,version=version+1
                WHERE user_id=? AND version=?''', (expiry, request.note, user['id'], now, uid, request.expected_version))
        if cursor.rowcount != 1:
            raise HTTPException(409, '会员记录已变化，请刷新后重试。')
        await db.execute('''INSERT INTO audit_events(actor_user_id,action,target_type,target_id,details_json,created_at)
            VALUES(?,?,?,?,?,?)''', (user['id'], 'membership.max_granted', 'user', uid,
            json.dumps({'expires_at': expiry, 'version': request.expected_version + 1}), now))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {'user_id': uid, 'email': email, 'expires_at': expiry, 'version': request.expected_version + 1}


@router.delete('/{user_id}')
async def revoke_membership(user_id: str, version: int = Query(ge=1), user=Depends(require_admin), db=Depends(get_db)):
    await init_max_memberships(db)
    try:
        # Keep a versioned tombstone. Deleting/reinserting would reset the version
        # and allow an old request to revoke a newly granted membership (ABA).
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute('''UPDATE max_memberships SET expires_at=?,updated_at=?,granted_by=?,version=version+1
            WHERE user_id=? AND version=?''', (now, now, user['id'], user_id, version))
        if cursor.rowcount != 1:
            raise HTTPException(409, '会员记录已变化，请刷新后重试。')
        await db.execute('''INSERT INTO audit_events(actor_user_id,action,target_type,target_id,details_json,created_at)
            VALUES(?,?,?,?,?,?)''', (user['id'], 'membership.max_revoked', 'user', user_id, '{}', datetime.now(timezone.utc).isoformat()))
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {'revoked': True}
