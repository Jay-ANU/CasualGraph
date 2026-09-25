"""User-requested legacy surfaces stay reachable without weakening tenant or offer permissions."""
import asyncio
import base64
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
from legal import contract_documents
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
    cp.update(original_b64=base64.b64encode(raw).decode(), mapping={})
    c = {'payload':cp,'matter_id':'m','org_id':'o'}
    r = {'status':'completed','payload':{'decisions':{'f1':{'block_id':'p1','decision':'accepted','text':'验收后60日付款。'}}}}
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


def test_word_does_not_silently_become_txt(export_data):
    with pytest.raises(HTTPException) as error:
        contracts.export('r', format='txt', user={'id':'u'})
    assert error.value.status_code == 422


def test_word_requires_selected_edits(export_data):
    export_data[0]['payload']['decisions'] = {}
    with pytest.raises(HTTPException) as error:
        contracts.export('r', format='docx', user={'id':'u'})
    assert error.value.status_code == 409


def test_original_identity_export_still_requires_edit_permission(export_data, monkeypatch):
    def denied(*args, **kwargs):
        raise HTTPException(403, 'Denied')
    monkeypatch.setattr(contracts, '_access', denied)
    with pytest.raises(HTTPException) as error:
        contracts.export('r', user={'id':'viewer'})
    assert error.value.status_code == 403
