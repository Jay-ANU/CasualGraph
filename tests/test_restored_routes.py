"""User-requested legacy surfaces stay reachable without weakening tenant or offer permissions."""
import asyncio
import base64
import hashlib
import io
import json
import sqlite3
import zipfile
from contextlib import nullcontext

import pytest
from docx import Document
from fastapi import HTTPException
from fastapi.testclient import TestClient
from lxml import etree

import app
from api import deps
from api.routers import contract_review as contracts, recruitment, research_graph
from legal import contract_documents, draft_release
from services import db as db_service


@pytest.fixture
def isolated_offer_db(monkeypatch, tmp_path):
    path = tmp_path / 'auth.db'
    monkeypatch.setattr(db_service, '_DB_PATH', str(path))
    asyncio.run(db_service._init_auth_db())
    asyncio.run(recruitment.initialize_recruitment())
    return path


def test_restored_offer_admin_route_requires_authentication():
    client = TestClient(app.app)
    for method, path in [('GET','/admin/recruitment/offers'), ('POST','/admin/recruitment/offers/preview'),
                         ('POST','/admin/recruitment/offers'), ('PATCH','/admin/recruitment/offers/no-id'),
                         ('DELETE','/admin/recruitment/offers/no-id'), ('POST','/admin/recruitment/offers/no-id/resend')]:
        assert client.request(method, path, json={}).status_code in (401, 403)


def test_regular_user_cannot_administer_offers():
    app.app.dependency_overrides[deps.get_current_user] = lambda: {'id':'ordinary', 'role':'user'}
    try:
        assert TestClient(app.app).get('/admin/recruitment/offers').status_code == 403
    finally:
        app.app.dependency_overrides.pop(deps.get_current_user, None)


def test_offer_schema_is_additive_and_invalid_tokens_do_not_disclose_data(isolated_offer_db):
    with sqlite3.connect(isolated_offer_db) as conn:
        conn.execute("CREATE TABLE preserved_test (value TEXT)")
        conn.execute("INSERT INTO preserved_test VALUES ('keep')")
    asyncio.run(recruitment.initialize_recruitment())
    with sqlite3.connect(isolated_offer_db) as conn:
        assert conn.execute('SELECT value FROM preserved_test').fetchone()[0] == 'keep'
        assert 'token' in {r[1] for r in conn.execute('PRAGMA table_info(recruitment_offers)')}
    assert TestClient(app.app).get('/offers/invalid-token').status_code == 404


def test_graph_public_and_workspace_are_scoped(monkeypatch, tmp_path):
    from services import document_access
    monkeypatch.setattr(research_graph, 'GRAPH_DIR', tmp_path)
    rows = []
    for did, public in [('public1',True), ('private1',False)]:
        path = tmp_path / f'{did}.json'
        path.write_text(json.dumps({'nodes':[{'id':'company','label':did}], 'edges':[]}))
        rows.append({'document_id':did, 'document_group':'global_kb' if public else 'user_private',
                     'owner_user_id':'owner', 'paths':{'graph':str(path)}})
    monkeypatch.setattr(document_access, '_collect_document_entries', lambda: rows)
    monkeypatch.setattr(document_access, '_can_access_entry', lambda u,e,**kw: u['id'] == e['owner_user_id'])
    assert [n['label'] for n in research_graph.graph_for(None,20,20)['nodes']] == ['public1']
    assert [n['label'] for n in research_graph.graph_for({'id':'other'},20,20)['nodes']] == ['public1']
    assert {n['label'] for n in research_graph.graph_for({'id':'owner'},20,20)['nodes']} == {'public1','private1'}
    assert str(tmp_path) not in json.dumps(research_graph.graph_for(None,20,20))
    assert TestClient(app.app).get('/graph/workspace').status_code in (401,403)


@pytest.fixture
def export_data(monkeypatch):
    doc = Document()
    doc.add_paragraph('验收后90日付款。')
    buf = io.BytesIO(); doc.save(buf)
    raw = buf.getvalue()
    cp = contract_documents.parse_contract(raw, '合同.docx')
    cp.update(original_b64=base64.b64encode(raw).decode(), mapping={},
              redacted_blocks=cp['blocks'], redaction_version=2)
    c = {'id':'c','status':'ready','revision':1,'payload':cp,'matter_id':'m','org_id':'o'}
    r = {'id':'r','contract_id':'c','created_at':0,'updated_at':0,'lease_until':0,'status':'completed','payload':{
        'engine_version':2,'audit_foundation_version':1,'contract_revision':1,
        'profile':{'external_processing_provider':'ydata','our_party':{'block_id':'p1','quote':'验收'}},
        'findings':[{'id':'f1','block_id':'p1','kind':'commercial','revision_allowed':True,
                     'verification_status':'supported','missing_facts':[],
                     'suggested_text':'验收后60日付款。','reason':'合成回款周期修改。'}],
        'decisions':{'f1':{'block_id':'p1','decision':'accepted','text':'验收后60日付款。','version':1}}}}
    # No model check or stored approval is needed for the user's current draft.
    monkeypatch.setattr(draft_release, 'check', lambda *a,**kw: pytest.fail('export called a model check'))
    monkeypatch.setattr(contracts.ydata, 'chat_json', lambda *a,**kw: pytest.fail('export called a model'))
    monkeypatch.setattr(draft_release, 'current', lambda conn,rid: (r,c))
    monkeypatch.setattr(contracts, '_review', lambda rid,user: (r,c))
    monkeypatch.setattr(contracts, '_access', lambda *a,**kw: None)
    monkeypatch.setattr(contracts.store, 'transaction', lambda: nullcontext(object()))
    monkeypatch.setattr(contracts.store, 'audit', lambda *a,**kw: None)
    return r,c


def test_word_download_defaults_to_native_pending_revisions(export_data):
    result = contracts.export('r', user={'id':'u'})
    assert result.media_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    assert '.docx' in result.headers['content-disposition']
    with zipfile.ZipFile(io.BytesIO(result.body)) as z:
        root = etree.fromstring(z.read('word/document.xml'))
    ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    assert root.xpath('//w:del//w:delText/text()',namespaces=ns) == ['9']
    assert root.xpath('//w:ins//w:t/text()',namespaces=ns) == ['6']


def test_word_can_explicitly_export_txt_without_changing_default_docx(export_data):
    result = contracts.export('r', format='txt', user={'id':'u'})
    assert result.body.decode('utf-8-sig') == '验收后60日付款。'
    assert '.txt' in result.headers['content-disposition']
    assert '.docx' in contracts.export('r', user={'id':'u'}).headers['content-disposition']


def test_word_with_unhandled_items_exports_original_after_one_confirmation(export_data):
    r, c = export_data
    r['payload']['decisions'] = {}
    with pytest.raises(HTTPException) as error:
        contracts.export('r', format='docx', user={'id':'u'})
    assert error.value.status_code == 409 and error.value.detail['pending_count'] == 1
    assert error.value.detail['code'] == 'export_confirmation_required'
    result = contracts.export('r', format='docx', user={'id':'u'}, confirmed=True, fingerprint=error.value.detail['fingerprint'])
    assert result.body == base64.b64decode(c['payload']['original_b64'])


def test_word_with_zero_findings_exports_unchanged_original_directly(export_data):
    r, c = export_data
    r['payload'].update(decisions={}, findings=[])
    result = contracts.export('r', user={'id':'u'})
    assert result.body == base64.b64decode(c['payload']['original_b64'])


def test_original_identity_export_still_requires_edit_permission(export_data, monkeypatch):
    def denied(*args, **kwargs):
        raise HTTPException(403, 'Denied')
    monkeypatch.setattr(contracts, '_access', denied)
    with pytest.raises(HTTPException) as error:
        contracts.export('r', user={'id':'viewer'})
    assert error.value.status_code == 403


def test_native_export_needs_neither_model_check_nor_stored_approval(export_data):
    assert 'draft_approval' not in export_data[0]['payload']
    assert 'draft_check' not in export_data[0]['payload']
    assert contracts.export('r', user={'id':'u'}).status_code == 200


def test_native_export_includes_exact_unverified_draft_text(export_data):
    r, c = export_data
    r['payload']['findings'][0].update(verification_status='rejected', revision_allowed=False, kind='legal')
    r['payload']['decisions']['f1'].update(decision='draft', text='验收后30日付款。', legal_basis_confirmed=False)
    state = draft_release.export_state(r, c)
    assert state['pending_count'] == state['selected_count'] == 1
    result = contracts.export('r', user={'id':'u'}, confirmed=True, fingerprint=state['fingerprint'])
    with zipfile.ZipFile(io.BytesIO(result.body)) as archive:
        root = etree.fromstring(archive.read('word/document.xml'))
    ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    assert ''.join(root.xpath('//w:p//w:t[not(ancestor::w:del)]/text()', namespaces=ns)) == '验收后30日付款。'
    assert root.xpath('//w:ins//w:t/text()', namespaces=ns) == ['3']
    assert r['payload']['decisions']['f1']['decision'] == 'draft'


def test_native_export_refuses_decision_changed_during_generation(export_data, monkeypatch):
    from legal import docx_redlines
    original = docx_redlines.redline_docx_result
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        export_data[0]['payload']['decisions']['f1']['text'] = '验收后30日付款。'
        return result
    monkeypatch.setattr(docx_redlines, 'redline_docx_result', changed)
    with pytest.raises(HTTPException) as error:
        contracts.export('r', user={'id':'u'})
    assert error.value.status_code == 409 and error.value.detail['code'] == 'export_stale'


def test_docx_structural_limitation_preserves_original_and_adds_explicit_appendix(export_data):
    r, c = export_data
    raw = base64.b64decode(c['payload']['original_b64'])
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(out, 'w') as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == 'word/document.xml':
                root = etree.fromstring(data)
                ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                p = root.xpath('//w:body/w:p', namespaces=ns)[0]
                p.insert(0, etree.Element('{'+ns['w']+'}bookmarkStart', {'{'+ns['w']+'}id':'9', '{'+ns['w']+'}name':'payment'}))
                data = etree.tostring(root)
            target.writestr(info, data)
    c['payload'].update(original_b64=base64.b64encode(out.getvalue()).decode(), content_hash=hashlib.sha256(out.getvalue()).hexdigest())
    result = contracts.export('r', user={'id':'u'})
    assert result.status_code == 200 and result.headers['x-legal-appendix-count'] == '1'
    with zipfile.ZipFile(io.BytesIO(result.body)) as archive:
        root = etree.fromstring(archive.read('word/document.xml'))
        assert root.xpath('//w:body/w:p[1]//w:t/text()', namespaces=ns) == ['验收后90日付款。']
        assert root.xpath('//w:bookmarkStart/@w:name', namespaces=ns) == ['payment']
        assert '验收后60日付款。' in ''.join(root.xpath('//w:t/text()', namespaces=ns))
        assert not root.xpath('//w:body/w:p[1]/w:ins|//w:body/w:p[1]/w:del', namespaces=ns)
    text_result = contracts.export('r', format='txt', user={'id':'u'})
    assert text_result.body.decode('utf-8-sig') == '验收后60日付款。'
