"""Authenticated contract workbench endpoints; independent of legacy RAG ingestion."""
from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
import zipfile
from lxml import etree
from pypdf.errors import PdfReadError
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api.deps import get_current_user
from services.db import get_db
from legal.access import require_legal_max, access_status
from legal import ydata
from services import matters
from legal import contract_documents as documents
from legal import external_law, review_engine as engine, review_store as store

router = APIRouter(prefix='/legal', tags=['contract-review'], dependencies=[Depends(require_legal_max)])
public_router = APIRouter(prefix='/legal', tags=['contract-review'])


class RedactionRequest(BaseModel):
    additional_terms: list[str] = Field(default_factory=list, max_length=100)
    confirmed: bool = False
    revision: int = Field(ge=1)


class ReviewRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=160, pattern=r'^[A-Za-z0-9][A-Za-z0-9._/-]*$')
    external_processing_provider: Literal['ydata']
    our_role: Literal['采购方', '供应方', '服务提供方', '服务接受方', '披露方', '接收方']
    contract_type: Literal['采购合同', '服务合同', '保密协议', '其他商事合同']
    jurisdiction: Literal['中国大陆'] = '中国大陆'
    transaction_date: date | None = None
    external_processing_confirmed: bool = False
    fresh_review: bool = False
    instructions: str = Field(default="", max_length=1500)
    review_mode: Literal["standard", "multi_agent"] = "multi_agent"


class PolicyRequest(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    text: str = Field(min_length=5, max_length=2500)
    contract_type: Literal['全部', '采购合同', '服务合同', '保密协议', '其他商事合同'] = '全部'
    version: int | None = Field(default=None, ge=1)


class DecisionRequest(BaseModel):
    decision: Literal['accepted', 'rejected', 'pending']
    text: str = Field(default='', max_length=12000)
    expected_version: int = Field(default=0, ge=0)
    legal_basis_confirmed: bool = False
    manual_edit_confirmed: bool = False


def _access(c: dict, user: dict, write=False):
    access = matters.require_matter_member(c['matter_id'], user, 'member' if write else 'viewer', require_active=write)
    with store.transaction() as conn:
        store.org_access(conn, access['matter']['org_id'], str(user['id']))
    return access['matter']


def _contract(cid, user, write=False):
    c = store.contract(cid)
    _access(c, user, write)
    return c


def _review(rid, user, write=False):
    r = store.review(rid)
    c = _contract(r['contract_id'], user, write)
    return r, c


def _view(c: dict):
    p = c['payload']
    redacted, mapping = documents.redact_blocks(p['blocks'])
    return {'id': c['id'], 'matter_id': c['matter_id'], 'org_id': c['org_id'], 'name': p['name'],
            'format': p['format'], 'revision': c['revision'], 'status': c['status'],
            'blocks': p.get('redacted_blocks', redacted), 'warnings': p['warnings'],
            'replacement_count': len(p.get('mapping', mapping)), 'reviews': store.reviews(c['id'])}


def _review_view(r: dict):
    from legal.review_v2 import all_sources
    p = r['payload']
    now = time.time()
    expired = (r['status'] == 'running' and r['lease_until'] < now) or (r['status'] == 'queued' and r.get('updated_at', now) < now - 600)
    can_resume = not p.get('decisions') and (r['status'] == 'failed' or expired or (r['status'] == 'partial' and p.get('retryable') is True))
    return {'id': r['id'], 'contract_id': r['contract_id'], 'status': r['status'], 'created_at': r['created_at'],
            'stage': p.get('stage', '等待执行'), 'error': p.get('error'), 'resumable': can_resume,
            'findings': p.get('findings', []), 'coverage': p.get('coverage', []), 'sources': all_sources(p),
            'decisions': p.get('decisions', {}), 'profile': p.get('profile', {}), 'policies': p.get('policies', []),
            'engine_version': p.get('engine_version', 1), 'intake': p.get('intake', {'facts': []}),
            'collaboration': p.get('collaboration'), 'metrics': p.get('metrics', {}),
            'summary': p.get('summary', {}), 'progress': p.get('progress'), 'batch_errors': p.get('batch_errors', {}),
            'retrieval': [{'rule_id': k, 'status': s['status'], 'provider': s['provider'], 'warnings': s.get('warnings', [])}
                          for k, s in p.get('searches', {}).items()],
            'notice': '法律意见为辅助审查；模型复核和原文匹配不代表法条版本及适用已由法务确认。未发现意见不代表无风险。'}


@public_router.get('/version')
def version():
    return {'product': 'contract-review', 'version': '1.0.0', 'law_source': 'external', 'rules_source': 'database',
            'max_only': True, 'model_gateway': 'ydata', 'model_selection_version': 1, 'review_engine_version': 2, 'followup_questions': True, 'collaboration_version': 1}


@public_router.get('/access')
async def legal_access(user: dict = Depends(get_current_user), db=Depends(get_db)):
    return await access_status(user, db)


def _gateway_failure(exc):
    return HTTPException(exc.status_code, {'error': exc.code, 'message': exc.message})


@router.get('/models')
def models():
    try:
        return ydata.model_catalog()
    except ydata.GatewayError as exc:
        raise _gateway_failure(exc) from None


@router.get('/capabilities')
def capabilities(user: dict = Depends(get_current_user)):
    from services.crypto import get_fernet
    try:
        get_fernet()
        encrypted = True
    except Exception:
        encrypted = False
    return {'product': 'contract-review', 'model_configured': ydata.configured(), 'model_gateway': 'ydata', 'encryption_configured': encrypted,
            'review_engine_version': 2, 'followup_questions': True, 'collaboration_version': 1,
            'law_search': external_law.provider_status(), 'contract_types': ['采购合同', '服务合同', '保密协议', '其他商事合同'],
            'limits': {'max_upload_mb': 10, 'max_characters': documents.MAX_TEXT, 'max_blocks': documents.MAX_BLOCKS}}


@router.get('/workspace')
def workspace(user: dict = Depends(get_current_user)):
    ws = matters.ensure_personal_workspace(user)
    access = matters.require_matter_member(ws['matter_id'], user)
    return {'matter_id': ws['matter_id'], 'org_id': access['matter']['org_id']}


@router.get('/contracts')
def list_contracts(matter_id: str, user: dict = Depends(get_current_user)):
    access = matters.require_matter_member(matter_id, user)
    with store.transaction() as conn:
        store.org_access(conn, access['matter']['org_id'], str(user['id']))
    return {'contracts': store.contract_list(matter_id)}


@router.post('/contracts', status_code=201)
def upload(matter_id: str = Form(...), file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    access = matters.require_matter_member(matter_id, user, 'member', require_active=True)
    data = file.file.read(documents.MAX_UPLOAD + 1)
    try:
        parsed = documents.parse_contract(data, file.filename or '')
        parsed.update(name=(file.filename or '合同')[:200], original_b64=base64.b64encode(data).decode())
        cid = store.create_contract(access['matter'], str(user['id']), parsed)
        return _view(store.contract(cid))
    except (zipfile.BadZipFile, etree.XMLSyntaxError, PdfReadError) as exc:
        raise HTTPException(422, '文件结构无法解析，请提供有效的 DOCX、文字 PDF 或 UTF-8 TXT。') from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (RuntimeError, KeyError) as exc:
        raise HTTPException(503, '安全存储未就绪，原件未进入外部模型，请联系管理员。') from exc


@router.get('/contracts/{cid}')
def get_contract(cid: str, user: dict = Depends(get_current_user)):
    return _view(_contract(cid, user))


@router.post('/contracts/{cid}/redaction')
def redaction(cid: str, request: RedactionRequest, user: dict = Depends(get_current_user)):
    c = _contract(cid, user, True)
    if c['status'] != 'redaction_pending':
        raise HTTPException(409, '脱敏已确认。需要更改时请上传新的合同版本。')
    if any(len(x) > 200 for x in request.additional_terms):
        raise HTTPException(422, '单个脱敏词不能超过 200 字。')
    blocks, mapping = documents.redact_blocks(c['payload']['blocks'], request.additional_terms)
    if request.confirmed:
        store.confirm_redaction(cid, str(user['id']), request.revision, blocks, mapping)
    return {'blocks': blocks, 'replacement_count': len(mapping), 'confirmed': request.confirmed}


@router.get('/policies')
def list_policies(org_id: str, user: dict = Depends(get_current_user)):
    return {'policies': store.policies(org_id, str(user['id']))}


@router.post('/policies', status_code=201)
def create_policy(org_id: str, request: PolicyRequest, user: dict = Depends(get_current_user)):
    return store.save_policy(org_id, str(user['id']), request.model_dump(exclude={'version'}))


@router.put('/policies/{pid}')
def update_policy(pid: str, org_id: str, request: PolicyRequest, user: dict = Depends(get_current_user)):
    return store.save_policy(org_id, str(user['id']), request.model_dump(exclude={'version'}), pid, request.version)


@router.delete('/policies/{pid}')
def delete_policy(pid: str, org_id: str, version: int, user: dict = Depends(get_current_user)):
    store.archive_policy(org_id, str(user['id']), pid, version)
    return {'archived': True}


@router.post('/contracts/{cid}/reviews', status_code=202)
def start_review(cid: str, request: ReviewRequest, user: dict = Depends(get_current_user)):
    c = _contract(cid, user, True)
    if c['status'] != 'ready' or not request.external_processing_confirmed:
        raise HTTPException(409, '请先确认脱敏，并授权将脱敏合同及适用公司规范交给已配置模型审查。')
    try:
        selected = ydata.select_model(request.model_id)
    except ydata.GatewayError as exc:
        raise _gateway_failure(exc) from None
    profile = request.model_dump(mode='json', exclude={'external_processing_confirmed', 'fresh_review', 'external_processing_provider', 'model_id'})
    from legal.review_questions import redact_note
    profile['instructions'] = redact_note(profile.get('instructions', ''), c['payload'])
    profile['model'] = selected
    profile['external_processing_provider'] = 'ydata'
    profile['review_date'] = date.today().isoformat()
    policies = [p for p in store.policies(c['org_id'], str(user['id'])) if p['contract_type'] in ('全部', request.contract_type)]
    snapshot = {'engine_version': 2, 'contract_revision': c['revision'], 'profile': profile, 'policies': policies, 'stage': '等待执行', 'findings': [], 'coverage': []}
    fingerprint = hashlib.sha256(json.dumps({'contract': cid, **snapshot, 'nonce': uuid.uuid4().hex if request.fresh_review else ''},
                                               sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    rid, created = store.create_review(c, str(user['id']), fingerprint, snapshot)
    if created:
        engine.submit(rid)
    return _review_view(store.review(rid))


@router.get('/reviews/{rid}')
def get_review(rid: str, user: dict = Depends(get_current_user)):
    r, _ = _review(rid, user)
    return _review_view(r)


@router.post('/reviews/{rid}/resume', status_code=202)
def resume(rid: str, user: dict = Depends(get_current_user)):
    r, c = _review(rid, user, True)
    if r['status'] in ('completed', 'cancelled') or (r['status'] == 'partial' and not r['payload'].get('retryable')):
        raise HTTPException(409, '该任务已结束；补充事实或改变要求时请新建审查。')
    if r['payload'].get('decisions'):
        raise HTTPException(409, '本轮已有人工决定，请新建审查，避免覆盖已确认修改。')
    if r['payload'].get('profile', {}).get('external_processing_provider') != 'ydata':
        raise HTTPException(409, '旧任务未确认 YData 处理授权，请选择模型并新建审查。')
    store.queue_resume(rid)
    engine.submit(rid)
    return _review_view(store.review(rid))


@router.patch('/reviews/{rid}/findings/{fid}')
def decision(rid: str, fid: str, request: DecisionRequest, user: dict = Depends(get_current_user)):
    _review(rid, user, True)
    return store.decide(rid, str(user['id']), fid, request.decision, request.text, request.expected_version,
                        legal_basis_confirmed=request.legal_basis_confirmed,
                        manual_edit_confirmed=request.manual_edit_confirmed)


@router.get('/reviews/{rid}/export')
def export(rid: str, format: Literal['json', 'docx', 'txt'] | None = None, user: dict = Depends(get_current_user)):
    r, c = _review(rid, user)
    if r['status'] not in ('completed', 'partial'):
        raise HTTPException(409, '请在审查完成后导出。')
    # Require editing permission for reconstructed originals: viewers can only export redacted reports.
    p, cp = r['payload'], c['payload']
    format = format or ('docx' if cp['format'] == 'docx' else 'json')
    if cp['format'] == 'docx' and format == 'txt':
        raise HTTPException(422, 'Word 合同请导出带修订痕迹的 DOCX；审查报告可单独导出。')
    if format == 'json':
        content = json.dumps(_review_view(r), ensure_ascii=False, indent=2).encode()
        mime, filename = 'application/json', f'review-{rid[:8]}.json'
    else:
        _access(c, user, True)
        changes = {d['block_id']: documents.restore(d['text'], cp.get('mapping', {}))
                   for d in p.get('decisions', {}).values() if d['decision'] == 'accepted'}
        if format == 'docx':
            if cp['format'] != 'docx':
                raise HTTPException(422, '仅 DOCX 原件可导出 Word 修订；其他格式请选择文字修改稿。')
            if not changes:
                raise HTTPException(409, '尚未选择需要纳入修订稿的修改，请先接受至少一项建议。')
            try:
                content = documents.redline_docx(base64.b64decode(cp['original_b64']), cp['blocks'], changes)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            mime, filename = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', f'revised-{rid[:8]}.docx'
        else:
            content = '\n\n'.join(changes.get(b['id'], b['text']) for b in cp['blocks']).encode('utf-8-sig')
            mime, filename = 'text/plain; charset=utf-8', f'revised-{rid[:8]}.txt'
    with store.transaction() as conn:
        store.audit(conn, str(user['id']), c['matter_id'], c['org_id'], 'review.exported', rid, {'format': format})
    return Response(content=content, media_type=mime, headers={'Content-Disposition': f'attachment; filename="{filename}"', 'Cache-Control': 'no-store'})

class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1500)
    request_id: str = Field(min_length=1, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    external_processing_confirmed: bool = False

@router.post('/reviews/{rid}/cancel')
def cancel_review(rid: str, user: dict = Depends(get_current_user)):
    r, c = _review(rid, user, True)
    store.cancel_review(rid, str(user['id']), c['org_id'])
    return _review_view(store.review(rid))

@router.get('/reviews/{rid}/questions')
def question_history(rid: str, user: dict = Depends(get_current_user)):
    from legal import review_questions
    _review(rid, user)
    return {'messages': review_questions.history(rid, str(user['id']))}

@router.post('/reviews/{rid}/questions')
def ask_question(rid: str, request: QuestionRequest, user: dict = Depends(get_current_user)):
    from legal import review_questions
    from legal.access import assert_worker_max
    r, c = _review(rid, user, True)
    if not request.external_processing_confirmed:
        raise HTTPException(409, '请明确授权把本次提问及本轮脱敏材料发送给原审查模型。')
    def authorize():
        assert_worker_max(str(user['id']))
        _review(rid, user, True)
    try:
        return review_questions.ask(r, c, user, request.question, request.request_id, authorize)
    except ydata.GatewayError as exc:
        raise _gateway_failure(exc) from None

