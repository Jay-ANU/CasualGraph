"""Encrypted, tenant-scoped review state in the existing durable auth database."""
from __future__ import annotations

import json
import re
import time
import uuid
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException


SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS legal_contracts (
        id TEXT PRIMARY KEY, matter_id TEXT NOT NULL, org_id TEXT NOT NULL,
        created_by TEXT NOT NULL, created_at REAL NOT NULL,
        revision INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL, payload BLOB NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS legal_policies (
        id TEXT PRIMARY KEY, org_id TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
        active INTEGER NOT NULL DEFAULT 1, updated_at REAL NOT NULL, payload BLOB NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS legal_reviews (
        id TEXT PRIMARY KEY, contract_id TEXT NOT NULL, matter_id TEXT NOT NULL,
        fingerprint TEXT UNIQUE NOT NULL, created_by TEXT NOT NULL,
        created_at REAL NOT NULL, updated_at REAL NOT NULL, status TEXT NOT NULL,
        lease_until REAL NOT NULL DEFAULT 0, worker_token TEXT NOT NULL DEFAULT '',
        payload BLOB NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS legal_contracts_matter_idx ON legal_contracts(matter_id)',
    'CREATE INDEX IF NOT EXISTS legal_policies_org_idx ON legal_policies(org_id)',
    'CREATE INDEX IF NOT EXISTS legal_reviews_contract_idx ON legal_reviews(contract_id)',
)


def fail(code: int, message: str):
    raise HTTPException(code, detail=message)


def connect():
    from services.db import connect_auth_db_sync
    return connect_auth_db_sync()


def encode(payload):
    from services.crypto import encrypt_json
    return encrypt_json(payload)


def decode(payload):
    from services.crypto import decrypt_json
    return decrypt_json(payload)


@contextmanager
def transaction():
    conn = connect()
    try:
        for sql in SCHEMA:
            conn.execute(sql)
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def audit(conn, user_id, matter_id, org_id, action, target_id, details=None):
    # Never put contract text, policy content, file names or secret values in audit metadata.
    conn.execute('''INSERT INTO audit_events
        (org_id,matter_id,actor_user_id,action,target_type,target_id,details_json,created_at)
        VALUES (?,?,?,?,?,?,?,datetime('now'))''',
        (org_id, matter_id, user_id, action, 'legal_review', target_id,
         json.dumps(details or {}, ensure_ascii=False)))


def org_access(conn, org_id: str, user_id: str, write=False):
    row = conn.execute('SELECT role FROM org_members WHERE org_id=? AND user_id=?', (org_id, user_id)).fetchone()
    if not row or (write and row['role'] not in ('owner', 'admin')):
        fail(403, '公司规范仅组织成员可读，仅组织管理员可修改。')


def create_contract(matter: dict, user_id: str, payload: dict) -> str:
    cid = uuid.uuid4().hex
    with transaction() as conn:
        org_access(conn, matter['org_id'], user_id)
        conn.execute('INSERT INTO legal_contracts VALUES (?,?,?,?,?,1,?,?)',
                     (cid, matter['id'], matter['org_id'], user_id, time.time(), 'redaction_pending', encode(payload)))
        audit(conn, user_id, matter['id'], matter['org_id'], 'contract.created', cid)
    return cid


def contract(cid: str) -> dict:
    with transaction() as conn:
        row = conn.execute('SELECT * FROM legal_contracts WHERE id=?', (cid,)).fetchone()
        if not row:
            fail(404, '合同不存在。')
        return {**dict(row), 'payload': decode(row['payload'])}


def contract_list(matter_id: str) -> list:
    with transaction() as conn:
        rows = conn.execute('SELECT * FROM legal_contracts WHERE matter_id=? ORDER BY created_at DESC LIMIT 100', (matter_id,)).fetchall()
        return [{'id': r['id'], 'revision': r['revision'], 'status': r['status'], 'created_at': r['created_at'],
                 'name': decode(r['payload'])['name']} for r in rows]


def confirm_redaction(cid: str, user_id: str, revision: int, redacted: list, mapping: dict):
    with transaction() as conn:
        row = conn.execute('SELECT * FROM legal_contracts WHERE id=?', (cid,)).fetchone()
        if not row or row['revision'] != revision or row['status'] != 'redaction_pending':
            fail(409, '合同状态已变化，请刷新后操作。')
        payload = decode(row['payload'])
        payload.update(redacted_blocks=redacted, mapping=mapping)
        conn.execute('UPDATE legal_contracts SET status=?,payload=? WHERE id=?', ('ready', encode(payload), cid))
        audit(conn, user_id, row['matter_id'], row['org_id'], 'contract.redaction_confirmed', cid,
              {'revision': revision, 'replacement_count': len(mapping)})


def policies(org_id: str, user_id: str) -> list:
    with transaction() as conn:
        org_access(conn, org_id, user_id)
        rows = conn.execute('SELECT * FROM legal_policies WHERE org_id=? AND active=1 ORDER BY updated_at DESC', (org_id,)).fetchall()
        return [{'id': r['id'], 'version': r['version'], **decode(r['payload'])} for r in rows]


def save_policy(org_id: str, user_id: str, payload: dict, pid: str | None = None, version: int | None = None):
    with transaction() as conn:
        org_access(conn, org_id, user_id, write=True)
        if pid:
            row = conn.execute('SELECT * FROM legal_policies WHERE id=? AND org_id=?', (pid, org_id)).fetchone()
            if not row:
                fail(404, '公司规范不存在。')
            if row['version'] != version:
                fail(409, '规范已被其他成员更新，请刷新。')
            new_version = version + 1
            conn.execute('UPDATE legal_policies SET payload=?, version=?, updated_at=? WHERE id=?',
                         (encode(payload), new_version, time.time(), pid))
        else:
            if conn.execute('SELECT COUNT(*) FROM legal_policies WHERE org_id=? AND active=1', (org_id,)).fetchone()[0] >= 30:
                fail(409, '首版每个组织最多 30 条有效规范，请归档旧规范。')
            pid, new_version = uuid.uuid4().hex, 1
            conn.execute('INSERT INTO legal_policies VALUES (?,?,?,1,?,?)', (pid, org_id, new_version, time.time(), encode(payload)))
        audit(conn, user_id, None, org_id, 'policy.saved', pid, {'version': new_version})
        return {'id': pid, 'version': new_version, **payload}


def archive_policy(org_id, user_id, pid, version):
    with transaction() as conn:
        org_access(conn, org_id, user_id, write=True)
        changed = conn.execute('UPDATE legal_policies SET active=0,version=version+1 WHERE org_id=? AND id=? AND version=?', (org_id, pid, version)).rowcount
        if not changed:
            fail(409, '规范不存在或版本已变化。')
        audit(conn, user_id, None, org_id, 'policy.archived', pid)


def create_review(c: dict, user_id: str, fingerprint: str, payload: dict) -> tuple[str, bool]:
    with transaction() as conn:
        old = conn.execute('SELECT id FROM legal_reviews WHERE fingerprint=?', (fingerprint,)).fetchone()
        if old:
            return old['id'], False
        now = time.time()
        count = conn.execute("SELECT COUNT(*) FROM legal_reviews WHERE status='queued' OR (status='running' AND lease_until>?)", (now,)).fetchone()[0]
        own = conn.execute("SELECT COUNT(*) FROM legal_reviews WHERE created_by=? AND (status='queued' OR (status='running' AND lease_until>?))", (user_id, now)).fetchone()[0]
        if count >= 8 or own >= 2:
            fail(429, '审查队列已满，请完成现有任务后再提交。')
        rid = uuid.uuid4().hex
        conn.execute('INSERT INTO legal_reviews VALUES (?,?,?,?,?,?,?,?,0,?,?)',
                     (rid, c['id'], c['matter_id'], fingerprint, user_id, now, now, 'queued', '', encode(payload)))
        audit(conn, user_id, c['matter_id'], c['org_id'], 'review.created', rid, {'revision': c['revision']})
        return rid, True


def review(rid: str) -> dict:
    with transaction() as conn:
        row = conn.execute('SELECT * FROM legal_reviews WHERE id=?', (rid,)).fetchone()
        if not row:
            fail(404, '审查任务不存在。')
        return {**dict(row), 'payload': decode(row['payload'])}


def reviews(cid: str) -> list:
    with transaction() as conn:
        rows = conn.execute('SELECT id,status,created_at,updated_at,lease_until FROM legal_reviews WHERE contract_id=? ORDER BY created_at DESC LIMIT 20', (cid,)).fetchall()
        return [dict(r) for r in rows]


def claim(rid: str) -> str | None:
    token, now = uuid.uuid4().hex, time.time()
    with transaction() as conn:
        updated = conn.execute("""UPDATE legal_reviews SET status='running',worker_token=?,lease_until=?,updated_at=?
            WHERE id=? AND (status IN ('queued','failed') OR (status='running' AND lease_until<?))""",
            (token, now + 600, now, rid, now)).rowcount
    return token if updated else None


def checkpoint(rid: str, token: str, payload: dict, status='running'):
    with transaction() as conn:
        now = time.time()
        updated = conn.execute('UPDATE legal_reviews SET payload=?,status=?,updated_at=?,lease_until=? WHERE id=? AND worker_token=?',
            (encode(payload), status, now, now + 600 if status == 'running' else 0, rid, token)).rowcount
        if not updated:
            raise RuntimeError('review_lease_lost')


def decide(rid: str, user_id: str, finding_id: str, decision: str, text: str, expected_version: int, *, legal_basis_confirmed: bool = False, manual_edit_confirmed: bool = False):
    with transaction() as conn:
        row = conn.execute('SELECT * FROM legal_reviews WHERE id=?', (rid,)).fetchone()
        if not row:
            fail(404, '审查任务不存在。')
        if row['status'] not in ('completed', 'partial'):
            fail(409, '审查尚未结束。')
        payload = decode(row['payload'])
        finding = next((x for x in payload.get('findings', []) if x['id'] == finding_id), None)
        if not finding:
            fail(404, '审查意见不存在。')
        decisions = payload.setdefault('decisions', {})
        old = decisions.get(finding_id, {})
        if old.get('version', 0) != expected_version:
            fail(409, '该意见已由其他人处理，请刷新。')
        if decision not in ('accepted', 'rejected', 'pending'):
            fail(400, '无效的处理决定。')
        if decision == 'accepted':
            cp = conn.execute('SELECT payload FROM legal_contracts WHERE id=?', (row['contract_id'],)).fetchone()
            contract_payload = decode(cp['payload'])
            if payload.get('engine_version') == 2:
                from legal.review_quality import edit_warnings
                if finding.get('revision_allowed') is not True or finding.get('verification_status') != 'supported' or finding.get('missing_facts'):
                    fail(409, '此建议未完成复核或缺少关键事实，不能直接纳入修订。')
                if finding['kind'] == 'legal' and legal_basis_confirmed is not True:
                    fail(409, '请先核对法条版本及适用条件，再确认纳入修订。')
                if text != finding.get('suggested_text') and manual_edit_confirmed is not True:
                    fail(409, '手工编辑后的文本需要明确确认。')
                original = next((b['text'] for b in contract_payload['redacted_blocks'] if b['id'] == finding.get('block_id')), '')
                if not original or edit_warnings(original, text):
                    fail(422, '修改范围、主体代称或文本完整性检查未通过，请人工核对。')
            allowed = set(contract_payload.get('mapping', {}))
            if not set(re.findall(r'【脱敏\d+】', text)).issubset(allowed) or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', text):
                fail(422, '修改包含未知脱敏代称或非法控制字符，请修正。')
            if not finding.get('block_id') or not text.strip():
                fail(400, '缺失条款或空修改建议不能自动回写，请人工编辑合同。')
            if finding['kind'] == 'legal' and finding['evidence_status'] != 'source_matched':
                fail(409, '法律依据尚未核验，该建议不能直接接受回写。')
            if any(k != finding_id and d['decision'] == 'accepted' and d['block_id'] == finding['block_id'] for k, d in decisions.items()):
                fail(409, '该段落已有另一条接受的修改，请先撤销或合并修改。')
        decisions[finding_id] = {'decision': decision, 'text': text, 'block_id': finding.get('block_id'),
                                 'user_id': user_id, 'version': expected_version + 1,
                                 'legal_basis_confirmed': legal_basis_confirmed is True,
                                 'manual_edit_confirmed': manual_edit_confirmed is True}
        conn.execute('UPDATE legal_reviews SET payload=?,updated_at=? WHERE id=?', (encode(payload), time.time(), rid))
        c = conn.execute('SELECT org_id FROM legal_contracts WHERE id=?', (row['contract_id'],)).fetchone()
        audit(conn, user_id, row['matter_id'], c['org_id'], 'review.decision', rid,
              {'finding_id': finding_id, 'decision': decision, 'version': expected_version + 1})
        return decisions[finding_id]

def cancel_review(rid: str, user_id: str, org_id: str):
    """Invalidate the lease before returning; late responses cannot publish."""
    with transaction() as conn:
        row = conn.execute('SELECT * FROM legal_reviews WHERE id=?', (rid,)).fetchone()
        if not row:
            fail(404, '审查任务不存在。')
        if row['status'] == 'cancelled':
            return
        if row['status'] not in ('queued', 'running'):
            fail(409, '任务已结束，无需停止。')
        payload = decode(row['payload'])
        payload.update(stage='已停止后续步骤；已经发出的请求无法撤回。', retryable=False)
        conn.execute("UPDATE legal_reviews SET status='cancelled',worker_token='',lease_until=0,payload=?,updated_at=? WHERE id=?",
                     (encode(payload), time.time(), rid))
        audit(conn, user_id, row['matter_id'], org_id, 'review.cancelled', rid)

def queue_resume(rid: str):
    """Apply normal queue limits to retries and never enqueue a live worker twice."""
    with transaction() as conn:
        row = conn.execute('SELECT * FROM legal_reviews WHERE id=?', (rid,)).fetchone()
        if not row:
            fail(404, '审查任务不存在。')
        now = time.time()
        payload = decode(row['payload'])
        if payload.get('decisions'):
            fail(409, '本轮已有人工决定，请新建审查。')
        if row['status'] in ('completed', 'cancelled') or (row['status'] == 'partial' and not payload.get('retryable')):
            fail(409, '该任务不可重试。')
        if (row['status'] == 'running' and row['lease_until'] > now) or (row['status'] == 'queued' and row['updated_at'] > now - 600):
            fail(409, '任务仍在执行或排队，不重复提交。')
        count = conn.execute("SELECT COUNT(*) FROM legal_reviews WHERE id<>? AND (status='queued' OR (status='running' AND lease_until>?))", (rid, now)).fetchone()[0]
        own = conn.execute("SELECT COUNT(*) FROM legal_reviews WHERE id<>? AND created_by=? AND (status='queued' OR (status='running' AND lease_until>?))", (rid, row['created_by'], now)).fetchone()[0]
        if count >= 8 or own >= 2:
            fail(429, '审查队列已满，请完成现有任务后再提交。')
        conn.execute("UPDATE legal_reviews SET status='queued',worker_token='',lease_until=0,updated_at=? WHERE id=?", (now, rid))

