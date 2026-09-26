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


def test_manual_edit_cannot_reuse_candidate_approval(runtime):
    with pytest.raises(HTTPException) as exc:
        select(runtime, runtime[2]['suggested_text'].replace('60', '30'))
    assert exc.value.status_code == 409
    select(runtime, runtime[2]['suggested_text'].replace('60', '30'), 'draft')
    assert store.review(runtime[0])['payload']['decisions']['f1']['decision'] == 'draft'


def test_selection_alone_never_authorizes_export(runtime):
    select(runtime)
    with pytest.raises(HTTPException):
        release.assert_exportable(store.review(runtime[0]), store.contract(runtime[1]))


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
    release.check(runtime[0], 'u1', 'hash', lambda: None, model=supported)
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


def test_uncertain_combination_cannot_be_human_approved(runtime):
    select(runtime)
    checked = release.check(runtime[0], 'u1', 'uncertain', lambda: None, model=lambda *args: {})
    assert checked['status'] == 'needs_review'
    with pytest.raises(HTTPException):
        release.approve(runtime[0], 'u1', checked['fingerprint'], True)


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


def test_changed_transaction_brief_invalidates_exact_export_approval(runtime):
    select(runtime)
    rid, cid, _ = runtime
    checked = release.check(rid, 'u1', 'context', lambda: None, model=supported)
    release.approve(rid, 'u1', checked['fingerprint'], True)
    r = store.review(rid)
    r['payload']['transaction_brief'] = {'context': {'attachments_status':'存在未提供附件'}}
    with pytest.raises(HTTPException) as error:
        release.assert_exportable(r, store.contract(cid))
    assert error.value.status_code == 409


def set_finding(runtime, **update):
    with store.transaction() as conn:
        row = conn.execute('SELECT payload FROM legal_reviews WHERE id=?', (runtime[0],)).fetchone()
        payload = store.decode(row['payload'])
        payload['findings'][0].update(update)
        conn.execute('UPDATE legal_reviews SET payload=? WHERE id=?', (store.encode(payload), runtime[0]))


def test_unconfirmed_finding_can_become_a_human_revision_but_not_a_one_click_adoption(runtime):
    rid, cid, f = runtime
    set_finding(runtime, revision_allowed=False, verification_status='uncertain')
    with pytest.raises(HTTPException):
        store.decide(rid, 'u1', 'f1', 'accepted', f['suggested_text'], 0)
    with pytest.raises(HTTPException):
        store.decide(rid, 'u1', 'f1', 'draft', f['suggested_text'], 0)
    store.decide(rid, 'u1', 'f1', 'draft', f['suggested_text'], 0, manual_edit_confirmed=True)
    assert store.review(rid)['payload']['decisions']['f1']['manual'] is True
    checked = release.check(rid, 'u1', 'human-draft', lambda: None, model=supported)
    assert checked['status'] == 'verified'
    release.approve(rid, 'u1', checked['fingerprint'], True)
    assert release.assert_exportable(store.review(rid), store.contract(cid))['final_hash'] == checked['final_hash']


def test_rejected_finding_cannot_seed_a_revision(runtime):
    set_finding(runtime, revision_allowed=False, verification_status='rejected')
    with pytest.raises(HTTPException):
        store.decide(runtime[0], 'u1', 'f1', 'draft', '甲方应在验收后30日内支付全部合同价款。', 0, manual_edit_confirmed=True)


def test_legal_revision_needs_confirmed_basis_even_as_human_draft(runtime):
    set_finding(runtime, kind='legal', evidence_status='model_cited')
    with pytest.raises(HTTPException):
        store.decide(runtime[0], 'u1', 'f1', 'draft', runtime[2]['suggested_text'], 0, manual_edit_confirmed=True)
    decision = store.decide(runtime[0], 'u1', 'f1', 'accepted', runtime[2]['suggested_text'], 0, legal_basis_confirmed=True)
    assert decision['legal_basis_confirmed'] is True and decision['manual'] is False
