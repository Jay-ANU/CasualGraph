"""Audit counterexamples and release invariants, using synthetic contracts only."""
from copy import deepcopy
import json
import sqlite3
from uuid import uuid4
import pytest
from fastapi import HTTPException
from legal import contract_documents as docs, review_quality as q, review_store as store
from legal import data_boundary as boundary, draft_release as release


def mask(text, additional=None, excluded=None):
    result, mapping = docs.redact_blocks([{'id': 'p1', 'text': text}], additional, excluded)
    assert docs.restore(result[0]['text'], mapping) == text
    return result[0], mapping


def test_company_mask_preserves_party_and_direction():
    block, mapping = mask('甲方北京星河科技有限公司向乙方上海云帆有限公司采购系统。')
    assert block['text'].startswith('甲方【脱敏') and '向乙方【脱敏' in block['text']
    assert set(mapping.values()) == {'北京星河科技有限公司', '上海云帆有限公司'}
    for span in block['redaction_spans']:
        assert block['text'][span['start']:span['end']] == span['token']


def test_person_field_preserves_duty():
    block, mapping = mask('联系人：张三负责验收，验收期限为五个工作日。')
    assert '张三' not in block['text'] and '负责验收' in block['text']
    assert '五个工作日' in block['text'] and '张三' in mapping.values()


def test_natural_name_mentions():
    block, _ = mask('由张三负责验收，李四负责付款审批。')
    assert '张三' not in block['text'] and '李四' not in block['text']
    assert block['text'].startswith('由【脱敏') and '负责付款审批' in block['text']


@pytest.mark.parametrize('source', ['甲方负责验收，乙方负责付款。', '双方负责协调，项目经理负责验收。', '甲方：验收后支付全部价款。'])
def test_roles_and_duties_not_persons(source):
    assert mask(source)[0]['text'] == source


def test_company_name_with_initial_conjunction_not_truncated():
    _, mapping = mask('和平有限公司与上海测试有限公司签约。')
    assert '和平有限公司' in mapping.values() and '上海测试有限公司' in mapping.values()


def test_explicit_unmask_and_longest_replacement():
    block, mapping = mask('上海测试有限公司与上海测试有限公司；上海测试', ['上海测试'])
    assert len(mapping) == 2 and block['text'].split('与')[0] == block['text'].split('与')[1].split('；')[0]
    block, _ = mask('联系人：张三；金额100万元', excluded=['张三'])
    assert '张三' in block['text']


def test_reserved_placeholders_rejected_on_upload():
    with pytest.raises(ValueError, match='保留'):
        docs.parse_contract('甲方【脱敏1】付款。'.encode(), 'a.txt')


def test_reversed_subjects_blocked_even_when_counts_match():
    old = '【脱敏1】应在验收后五日内向【脱敏2】支付合同价款。'
    new = '【脱敏2】应在验收后五日内向【脱敏1】支付合同价款。'
    assert any('顺序' in x for x in q.edit_warnings(old, new))


def test_rejected_and_unverified_findings_not_risk_counts():
    base = {'severity': 'high', 'kind': 'commercial', 'revision_allowed': False, 'missing_facts': []}
    result = q.summary([{**base, 'verification_status': 'rejected'}, {**base, 'verification_status': 'uncertain'},
                        {**base, 'verification_status': 'supported'},
                        {**base, 'verification_status': 'supported', 'evidence_status': 'unverified'}], [])
    assert result['high'] == 1 and result['unconfirmed'] == 2 and result['rejected_candidates'] == 1
    assert result['needs_confirmation'] == 3


def test_materials_share_namespace_without_mutating_policies():
    policies = [{'id': 'a', 'title': '张三规范', 'text': '联系人：张三；付款限额30%。'},
                {'id': 'b', 'title': '规则', 'text': '联系人：李四；金额100万元。'}]
    original = deepcopy(policies)
    masked, note = boundary.redact_materials({'mapping': {'【脱敏1】': '北京星河有限公司'}}, policies,
                                            '北京星河有限公司由张三负责验收。')
    assert policies == original
    encoded = json.dumps(masked, ensure_ascii=False)
    assert '张三' not in encoded and '李四' not in encoded and '30%' in encoded and '100万元' in encoded
    assert '【脱敏1】' in note and '北京星河' not in note
    assert masked[0]['text'].split('；')[0] != masked[1]['text'].split('；')[0]


def test_party_binding_requires_exact_current_span():
    blocks = [{'id': 'p1', 'text': '甲方【脱敏1】；乙方【脱敏2】'}]
    assert boundary.bind_party({'block_id': 'p1', 'quote': '乙方【脱敏2】'}, blocks)['confirmed_by'] == 'user'
    for value in (None, {'block_id': 'p9', 'quote': '乙方'}, {'block_id': 'p1', 'quote': '丙方'}):
        with pytest.raises(HTTPException):
            boundary.bind_party(value, blocks)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    path = tmp_path / 'audit.db'
    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE IF NOT EXISTS org_members(org_id TEXT,user_id TEXT,role TEXT)')
        conn.execute('''CREATE TABLE IF NOT EXISTS audit_events(org_id TEXT,matter_id TEXT,actor_user_id TEXT,
                     action TEXT,target_type TEXT,target_id TEXT,details_json TEXT,created_at TEXT)''')
        conn.commit()
        return conn
    monkeypatch.setattr(store, 'connect', connect)
    monkeypatch.setattr(store, 'encode', lambda p: json.dumps(p, ensure_ascii=False).encode())
    monkeypatch.setattr(store, 'decode', lambda p: json.loads(p))
    with connect() as conn:
        conn.execute("INSERT INTO org_members VALUES ('o1','u1','owner')")
    blocks = [{'id': 'p1', 'text': '甲方应在验收后90日内支付全部合同价款。', 'anchor': None},
              {'id': 'p2', 'text': '甲方应在交货后三日内完成验收。', 'anchor': None}]
    cp = {'name': '合成合同.txt', 'format': 'txt', 'blocks': blocks, 'redacted_blocks': blocks,
          'warnings': [], 'mapping': {}, 'content_hash': 'fixture', 'redaction_version': 2}
    cid = store.create_contract({'id': 'm1', 'org_id': 'o1'}, 'u1', cp)
    store.confirm_redaction(cid, 'u1', 1, blocks, {})
    c = store.contract(cid)
    findings = [{'id': 'f1', 'block_id': 'p1', 'kind': 'commercial', 'revision_allowed': True,
                 'verification_status': 'supported', 'evidence_status': 'not_applicable', 'severity': 'medium',
                 'reason': '缩短回款周期。', 'missing_facts': [], 'suggested_text': blocks[0]['text'].replace('90', '60')}]
    p = {'engine_version': 2, 'audit_foundation_version': 1, 'contract_revision': 1,
         'profile': {'model': {'provider': 'ydata', 'id': 'glm-5.2'}, 'external_processing_provider': 'ydata'},
         'findings': findings, 'coverage': [], 'policies': [], 'decisions': {}}
    rid, _ = store.create_review(c, 'u1', uuid4().hex, p)
    token = store.claim(rid)
    store.checkpoint(rid, token, p, 'completed')
    return rid, cid, findings[0]


def supported(system, data, model):
    return {'checks': [{'finding_id': x['finding_id'], 'status': 'supported', 'reason': '合成逐项对比。'} for x in data['selected_changes']],
            'whole_contract': {'status': 'consistent', 'reason': '合成全文对比。'}, 'missing_facts': []}


def select(runtime, text=None, decision='accepted'):
    rid, _, f = runtime
    return store.decide(rid, 'u1', 'f1', decision, text or f['suggested_text'], 0, manual_edit_confirmed=True)


@pytest.mark.parametrize('decision', ['accepted', 'draft'])
def test_user_can_save_or_accept_their_edited_text_without_model_approval(runtime, decision):
    select(runtime, runtime[2]['suggested_text'].replace('60', '30'), decision)
    payload = store.review(runtime[0])['payload']
    assert payload['decisions']['f1']['decision'] == decision
    assert payload['decisions']['f1']['manual'] is True
    assert payload['decisions']['f1']['source'] == 'user'
    assert 'draft_approval' not in payload and 'draft_check' not in payload


def test_user_acceptance_is_sufficient_to_export_without_a_model_call(runtime, monkeypatch):
    select(runtime)
    monkeypatch.setattr(release.ydata, 'chat_json', lambda *args: pytest.fail('export must be local'))
    data = release.assert_exportable(store.review(runtime[0]), store.contract(runtime[1]))
    assert data['pending_count'] == 0 and '60日' in data['final_contract'][0]['text']


def test_exact_selected_combination_then_human_approval(runtime):
    select(runtime, runtime[2]['suggested_text'].replace('60', '30'), 'draft')
    rid, cid, _ = runtime
    seen = []
    def model(s, d, m):
        seen.append(deepcopy(d))
        return supported(s, d, m)
    checked = release.check(rid, 'u1', 'request1', lambda: None, model=model)
    assert checked['status'] == 'verified' and '30日' in seen[0]['final_contract'][0]['text']
    assert '90日' in seen[0]['original_contract'][0]['text']
    with pytest.raises(HTTPException):
        release.assert_exportable(store.review(rid), store.contract(cid))
    with pytest.raises(HTTPException):
        release.approve(rid, 'u1', checked['fingerprint'], False)
    release.approve(rid, 'u1', checked['fingerprint'], True)
    r = store.review(rid)
    assert r['payload']['decisions']['f1']['decision'] == 'accepted'
    assert release.assert_exportable(r, store.contract(cid))['final_hash'] == checked['final_hash']
    store.decide(rid, 'u1', 'f1', 'pending', '', r['payload']['decisions']['f1']['version'])
    assert 'draft_approval' not in store.review(rid)['payload']
    with pytest.raises(HTTPException):
        release.assert_exportable(store.review(rid), store.contract(cid))


@pytest.mark.parametrize('raw', [{}, None, {'checks': []},
    {'checks': [{'finding_id': 'f1', 'status': 'supported', 'reason': 'x'}], 'whole_contract': {'status': 'consistent', 'reason': 'x'}},
    {'checks': [{'finding_id': [], 'status': 'supported', 'reason': 'x'}], 'missing_facts': []}])
def test_incomplete_checks_fail_closed(raw):
    assert release.validate_check(raw, [{'finding_id': 'f1'}])['status'] == 'needs_review'


def test_duplicate_checks_and_conflict_fail_closed():
    valid = supported('', {'selected_changes': [{'finding_id': 'f1'}]}, {})
    valid['checks'] *= 2
    assert release.validate_check(valid, [{'finding_id': 'f1'}])['status'] == 'needs_review'
    valid = supported('', {'selected_changes': [{'finding_id': 'f1'}]}, {})
    valid['whole_contract']['status'] = 'conflict'
    assert release.validate_check(valid, [{'finding_id': 'f1'}])['status'] == 'needs_review'


def test_late_check_cannot_bless_changed_decisions(runtime):
    select(runtime)
    rid = runtime[0]
    def model(s, d, m):
        store.decide(rid, 'u1', 'f1', 'pending', '', 1)
        return supported(s, d, m)
    with pytest.raises(HTTPException):
        release.check(rid, 'u1', 'late', lambda: None, model=model)
    assert 'draft_check' not in store.review(rid)['payload']


def test_revoked_authority_does_not_publish_check(runtime):
    select(runtime)
    count = 0
    def authorize():
        nonlocal count
        count += 1
        if count == 3:
            raise HTTPException(403, 'revoked')
    with pytest.raises(HTTPException):
        release.check(runtime[0], 'u1', 'revoked', authorize, model=supported)
    assert 'draft_check' not in store.review(runtime[0])['payload']


def test_idempotent_check_does_not_call_model_twice(runtime):
    select(runtime)
    result = release.check(runtime[0], 'u1', 'same', lambda: None, model=supported)
    cached = release.check(runtime[0], 'u1', 'same', lambda: None, model=lambda *a: pytest.fail('duplicate call'))
    assert cached == result


def test_wrong_approval_hash_fails(runtime):
    select(runtime)
    with pytest.raises(HTTPException):
        release.approve(runtime[0], 'u1', '0' * 64, True)


def test_changed_original_and_legacy_review_cannot_export(runtime):
    select(runtime)
    rid, cid, _ = runtime
    checked = release.check(rid, 'u1', 'original', lambda: None, model=supported)
    release.approve(rid, 'u1', checked['fingerprint'], True)
    c = store.contract(cid)
    c['payload']['redacted_blocks'][0]['text'] += '新增条件。'
    with pytest.raises(HTTPException):
        release.assert_exportable(store.review(rid), c)
    c = store.contract(cid)
    c['payload'].pop('redaction_version')
    with pytest.raises(HTTPException):
        release.assert_exportable(store.review(rid), c)


def test_failed_model_never_leaves_export_approval(runtime):
    select(runtime)
    def fail(*args):
        raise RuntimeError('synthetic failure')
    with pytest.raises(RuntimeError):
        release.check(runtime[0], 'u1', 'failure', lambda: None, model=fail)
    assert 'draft_check' not in store.review(runtime[0])['payload']
    assert 'draft_approval' not in store.review(runtime[0])['payload']
    assert release.assert_exportable(store.review(runtime[0]), store.contract(runtime[1]))['pending_count'] == 0


def test_uncertain_model_advice_does_not_veto_user_approval_or_export(runtime):
    select(runtime)
    checked = release.check(runtime[0], 'u1', 'uncertain', lambda: None, model=lambda *args: {})
    assert checked['status'] == 'needs_review'
    release.approve(runtime[0], 'u1', checked['fingerprint'], True)
    assert release.assert_exportable(store.review(runtime[0]), store.contract(runtime[1]))['pending_count'] == 0


def test_new_sensitive_identity_in_manual_edit_is_not_sent(runtime):
    replacement = runtime[2]['suggested_text'] + '联系人：张三。'
    with pytest.raises(HTTPException) as exc:
        select(runtime, replacement, 'draft')
    assert exc.value.status_code == 422


def test_disclosure_does_not_certify_configured_region(monkeypatch):
    monkeypatch.setenv('LEGAL_STORAGE_REGION', 'Sydney (operator declaration)')
    d = boundary.disclosure()
    assert d['raw_upload_before_redaction'] is True and d['region_verified'] is False
    assert 'Sydney' in d['storage_region']


def test_changed_transaction_brief_invalidates_the_preview_fingerprint(runtime):
    select(runtime)
    rid, cid, _ = runtime
    checked = release.check(rid, 'u1', 'context', lambda: None, model=supported)
    release.approve(rid, 'u1', checked['fingerprint'], True)
    r = store.review(rid)
    fingerprint = release.snapshot(r, store.contract(cid))['fingerprint']
    r['payload']['transaction_brief'] = {'context': {'attachments_status':'存在未提供附件'}}
    with pytest.raises(HTTPException) as error:
        release.assert_exportable(r, store.contract(cid), fingerprint=fingerprint)
    assert error.value.status_code == 409 and error.value.detail['code'] == 'export_stale'


def set_finding(runtime, **update):
    with store.transaction() as conn:
        row = conn.execute('SELECT payload FROM legal_reviews WHERE id=?', (runtime[0],)).fetchone()
        payload = store.decode(row['payload'])
        payload['findings'][0].update(update)
        conn.execute('UPDATE legal_reviews SET payload=? WHERE id=?', (store.encode(payload), runtime[0]))


@pytest.mark.parametrize('verification', ['uncertain', 'rejected', 'unreviewed', None])
@pytest.mark.parametrize('decision', ['accepted', 'draft'])
def test_model_status_never_blocks_the_users_revision_choice(runtime, verification, decision):
    rid, cid, f = runtime
    set_finding(runtime, revision_allowed=False, verification_status=verification, missing_facts=['尚有事实未补充'])
    saved = store.decide(rid, 'u1', 'f1', decision, f['suggested_text'], 0)
    assert saved['decision'] == decision and saved['manual_edit_confirmed'] is False
    data = release.snapshot(store.review(rid), store.contract(cid))
    assert data['pending_count'] == (1 if decision == 'draft' else 0)
    exported = release.assert_exportable(store.review(rid), store.contract(cid), confirmed=True, fingerprint=data['fingerprint'])
    assert exported['final_contract'][0]['text'] == f['suggested_text']


def test_rejected_model_advice_allows_manual_revision_and_confirmed_export(runtime):
    set_finding(runtime, revision_allowed=False, verification_status='rejected')
    store.decide(runtime[0], 'u1', 'f1', 'draft', '甲方应在验收后30日内支付全部合同价款。', 0)
    r, c = store.review(runtime[0]), store.contract(runtime[1])
    state = release.export_state(r, c)
    with pytest.raises(HTTPException) as error:
        release.assert_exportable(r, c)
    assert error.value.detail['code'] == 'export_confirmation_required'
    assert error.value.detail['pending_count'] == state['pending_count'] == 1
    data = release.assert_exportable(r, c, confirmed=True, fingerprint=state['fingerprint'])
    assert '30日' in data['final_contract'][0]['text']


def test_legal_basis_confirmation_is_recorded_without_becoming_a_save_gate(runtime):
    set_finding(runtime, kind='legal', evidence_status='model_cited')
    saved = store.decide(runtime[0], 'u1', 'f1', 'draft', runtime[2]['suggested_text'], 0)
    assert saved['legal_basis_confirmed'] is False
    decision = store.decide(runtime[0], 'u1', 'f1', 'accepted', runtime[2]['suggested_text'], 1, legal_basis_confirmed=True)
    assert decision['legal_basis_confirmed'] is True and decision['manual'] is False


def test_user_rewrite_is_not_vetoed_by_a_similarity_heuristic(runtime):
    original = '甲方应在验收后90日内支付全部合同价款，不得拖延。'
    replacement = '本条删除原付款安排，双方同意由受托方完成交付后结算。'
    assert any('范围过大' in warning for warning in q.edit_warnings(original, replacement))
    with store.transaction() as conn:
        _, contract = release.current(conn, runtime[0])
        contract['payload']['blocks'][0]['text'] = original
        contract['payload']['redacted_blocks'][0]['text'] = original
        conn.execute('UPDATE legal_contracts SET payload=? WHERE id=?', (store.encode(contract['payload']), runtime[1]))
    saved = store.decide(runtime[0], 'u1', 'f1', 'draft', replacement, 0)
    assert saved['text'] == replacement


def test_pending_confirmation_needs_an_exact_current_fingerprint(runtime):
    select(runtime, decision='draft')
    r, c = store.review(runtime[0]), store.contract(runtime[1])
    data = release.snapshot(r, c)
    for fingerprint in (None, '0' * 64):
        with pytest.raises(HTTPException) as error:
            release.assert_exportable(r, c, confirmed=True, fingerprint=fingerprint)
        assert error.value.detail['code'] == 'export_stale'
    assert release.assert_exportable(r, c, confirmed=True, fingerprint=data['fingerprint'])['pending_count'] == 1


def test_local_export_does_not_need_external_processing_authorization(runtime):
    select(runtime)
    r, c = store.review(runtime[0]), store.contract(runtime[1])
    r['payload']['profile'].pop('external_processing_provider')
    assert release.assert_exportable(r, c)['pending_count'] == 0


@pytest.fixture
def export_client(runtime, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routers import contract_review as routes

    actor = {'id': 'u1', 'matter_role': 'member'}
    application = FastAPI()
    application.include_router(routes.router)
    application.dependency_overrides[routes.get_current_user] = lambda: actor
    application.dependency_overrides[routes.require_legal_max] = lambda: actor

    def member(matter_id, user, min_role='viewer', require_active=False):
        if matter_id != 'm1' or user['id'] != 'u1' or (min_role == 'member' and user['matter_role'] == 'viewer'):
            raise HTTPException(403, 'no access')
        return {'matter': {'id': 'm1', 'org_id': 'o1'}, 'role': user['matter_role']}

    monkeypatch.setattr(routes.matters, 'require_matter_member', member)
    monkeypatch.setattr(routes.ydata, 'chat_json', lambda *a, **kw: pytest.fail('local export called a model'))
    monkeypatch.setattr(release, 'check', lambda *a, **kw: pytest.fail('local export called a draft check'))
    return TestClient(application), actor


def test_export_api_returns_pending_count_then_downloads_current_text(runtime, export_client):
    client, _ = export_client
    rid, cid, _ = runtime
    state = client.get(f'/legal/reviews/{rid}').json()['export_state']
    assert state['ready'] and state['pending_count'] == 1 and state['selected_count'] == 0
    response = client.get(f'/legal/reviews/{rid}/export', params={'format': 'txt', 'fingerprint': state['fingerprint']})
    detail = response.json()['detail']
    assert response.status_code == 409 and detail['code'] == 'export_confirmation_required'
    assert detail['pending_count'] == 1 and detail['fingerprint'] == state['fingerprint']
    result = client.get(f'/legal/reviews/{rid}/export', params={'format': 'txt', 'confirmed': 'true', 'fingerprint': detail['fingerprint']})
    assert result.status_code == 200 and '90日' in result.content.decode('utf-8-sig')
    assert result.headers['cache-control'] == 'no-store'
    assert not store.review(rid)['payload']['decisions']
    with store.transaction() as conn:
        audit = json.loads(conn.execute("SELECT details_json FROM audit_events WHERE action='review.exported'").fetchone()[0])
    assert audit['pending_count'] == 1 and audit['pending_acknowledged'] is True


def test_export_api_saves_rejected_legal_draft_and_exports_its_actual_text(runtime, export_client):
    client, _ = export_client
    rid, _, _ = runtime
    set_finding(runtime, verification_status='rejected', revision_allowed=False, kind='legal', missing_facts=['事实未确认'])
    body = {'decision': 'draft', 'text': '甲方应在验收后30日内支付全部合同价款。', 'expected_version': 0}
    saved = client.patch(f'/legal/reviews/{rid}/findings/f1', json=body)
    assert saved.status_code == 200 and saved.json()['legal_basis_confirmed'] is False
    state = client.get(f'/legal/reviews/{rid}').json()['export_state']
    assert state['pending_count'] == state['selected_count'] == 1
    result = client.get(f'/legal/reviews/{rid}/export', params={'format': 'txt', 'confirmed': 'true', 'fingerprint': state['fingerprint']})
    assert result.status_code == 200 and '30日' in result.content.decode('utf-8-sig')
    accepted = client.patch(f'/legal/reviews/{rid}/findings/f1', json={**body, 'decision': 'accepted', 'expected_version': 1})
    assert accepted.status_code == 200
    state = client.get(f'/legal/reviews/{rid}').json()['export_state']
    assert state['pending_count'] == 0
    assert client.get(f'/legal/reviews/{rid}/export', params={'format': 'txt', 'fingerprint': state['fingerprint']}).status_code == 200


def test_export_api_old_confirmation_is_rejected_even_when_count_is_unchanged(runtime, export_client):
    client, _ = export_client
    rid, _, f = runtime
    store.decide(rid, 'u1', 'f1', 'draft', f['suggested_text'], 0)
    old = client.get(f'/legal/reviews/{rid}').json()['export_state']
    store.decide(rid, 'u1', 'f1', 'draft', f['suggested_text'].replace('60', '30'), 1)
    stale = client.get(f'/legal/reviews/{rid}/export', params={'format': 'txt', 'confirmed': 'true', 'fingerprint': old['fingerprint']})
    assert stale.status_code == 409 and stale.json()['detail']['code'] == 'export_stale'
    assert stale.json()['detail']['pending_count'] == old['pending_count'] == 1
    current = client.get(f'/legal/reviews/{rid}').json()['export_state']
    assert current['fingerprint'] != old['fingerprint']
    result = client.get(f'/legal/reviews/{rid}/export', params={'format': 'txt', 'confirmed': 'true', 'fingerprint': current['fingerprint']})
    assert result.status_code == 200 and '30日' in result.content.decode('utf-8-sig')


def test_export_api_confirmation_does_not_bypass_permissions(runtime, export_client):
    client, actor = export_client
    rid = runtime[0]
    state = client.get(f'/legal/reviews/{rid}').json()['export_state']
    actor['matter_role'] = 'viewer'
    denied = client.get(f'/legal/reviews/{rid}/export', params={'format': 'txt', 'confirmed': 'true', 'fingerprint': state['fingerprint']})
    assert denied.status_code == 403
    assert client.get(f'/legal/reviews/{rid}/export', params={'format': 'json'}).status_code == 200
    actor['id'] = 'outside-tenant'
    assert client.get(f'/legal/reviews/{rid}').status_code == 403


@pytest.mark.parametrize('user_edited', [False, True])
def test_generated_drafts_can_resume_but_user_decisions_are_preserved(runtime, export_client, monkeypatch, user_edited):
    from api.routers import contract_review as routes
    client, _ = export_client
    rid, _, f = runtime
    if user_edited:
        store.decide(rid, 'u1', 'f1', 'draft', f['suggested_text'], 0)
    with store.transaction() as conn:
        r, _ = release.current(conn, rid)
        p = r['payload']
        p['retryable'] = True
        if not user_edited:
            p['decisions'] = {'f1': {'decision': 'draft', 'text': f['suggested_text'], 'block_id': 'p1',
                                     'version': 0, 'source': 'model', 'manual': False}}
        conn.execute("UPDATE legal_reviews SET status='partial',payload=? WHERE id=?", (store.encode(p), rid))
    submitted = []
    monkeypatch.setattr(routes.engine, 'submit', submitted.append)
    before = client.get(f'/legal/reviews/{rid}').json()
    assert before['resumable'] is (not user_edited)
    resumed = client.post(f'/legal/reviews/{rid}/resume')
    assert resumed.status_code == (409 if user_edited else 202)
    assert submitted == ([] if user_edited else [rid])
    if user_edited:
        with pytest.raises(HTTPException) as error:
            store.queue_resume(rid)
        assert error.value.status_code == 409


@pytest.mark.parametrize('decision', ['accepted', 'draft', 'rejected'])
def test_user_paragraph_choice_supersedes_automatic_draft_without_a_conflict(runtime, decision):
    from legal.review_v2 import prepare_draft
    rid, cid, f = runtime
    with store.transaction() as conn:
        r, c = release.current(conn, rid)
        p = r['payload']
        p['findings'].append({**deepcopy(f), 'id': 'f2'})
        p['decisions'] = prepare_draft(p['findings'], c['payload']['redacted_blocks'], c['payload'])
        assert set(p['decisions']) == {'f1'}
        old_version = p['decisions']['f1']['version']
        conn.execute('UPDATE legal_reviews SET payload=? WHERE id=?', (store.encode(p), rid))
    replacement = f['suggested_text'].replace('60', '30') if decision != 'rejected' else ''
    store.decide(rid, 'u1', 'f2', decision, replacement, 0)
    r = store.review(rid)
    displaced = r['payload']['decisions']['f1']
    assert displaced['decision'] == 'pending' and displaced['superseded_by'] == 'f2'
    assert displaced['version'] == old_version + 1
    data = release.snapshot(r, store.contract(cid))
    assert len(data['selected_changes']) == (0 if decision == 'rejected' else 1)
    assert ('90日' if decision == 'rejected' else '30日') in data['final_contract'][0]['text']
    with pytest.raises(HTTPException) as error:
        store.decide(rid, 'u1', 'f1', 'accepted', f['suggested_text'], old_version)
    assert error.value.status_code == 409
