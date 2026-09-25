"""YData transport and real server entitlement regression; all model traffic is synthetic."""
import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import deps
from api.routers import contract_review, max_memberships
from legal import access, ydata, review_engine
from services import db as database


@pytest.fixture(autouse=True)
def no_live_gateway(monkeypatch):
    monkeypatch.setenv('YDATA_API_KEY', 'synthetic-test-gateway-key')
    for env_name in ydata.FAMILY_KEY_ENVS.values():
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.delenv('LEGAL_YDATA_MODELS', raising=False)
    monkeypatch.delenv('LEGAL_YDATA_DEFAULT_MODEL', raising=False)
    ydata.clear_cache()
    yield
    ydata.clear_cache()


def catalog_response():
    return {'data': [{'id': mid} for mid in ['gpt-5-test','claude-test','deepseek-test','kimi-test','glm-5.2',
                                            'gpt-image-test','gpt-audio-test','text-embedding-test','unrelated-test']]}


def test_all_requested_families_are_discovered_without_invented_ids():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=catalog_response()))) as client:
        result = ydata.model_catalog(client=client)
    assert [m['family'] for m in result['models']] == list(ydata.FAMILIES)
    assert len(result['models']) == 5
    assert result['default_model'] == 'glm-5.2'
    assert 'synthetic-test-gateway-key' not in json.dumps(result)

def test_family_specific_keys_merge_catalog(monkeypatch):
    monkeypatch.delenv('YDATA_API_KEY')
    key_models = {
        'gpt-key': 'gpt-5-test',
        'claude-key': 'claude-test',
        'deepseek-key': 'deepseek-test',
        'kimi-key': 'kimi-test',
        'glm-key': 'glm-5.2',
    }
    for family, key in zip(ydata.FAMILIES, key_models):
        monkeypatch.setenv(ydata.FAMILY_KEY_ENVS[family], key)

    def respond(request):
        key = request.headers['Authorization'].removeprefix('Bearer ')
        return httpx.Response(200, json={'data': [{'id': key_models[key]}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = ydata.model_catalog(client=client)
    assert [m['family'] for m in result['models']] == list(ydata.FAMILIES)
    assert result['available_families'] == list(ydata.FAMILIES)
    assert result['unavailable_families'] == []


def test_selected_family_uses_its_own_key(monkeypatch):
    monkeypatch.delenv('YDATA_API_KEY')
    inventory = ['gpt-5-test', 'claude-test', 'deepseek-test', 'kimi-test', 'glm-5.2']
    keys = {}
    for family, mid in zip(ydata.FAMILIES, inventory):
        key = family.lower() + '-key'
        keys[mid] = key
        monkeypatch.setenv(ydata.FAMILY_KEY_ENVS[family], key)
    monkeypatch.setenv('LEGAL_YDATA_MODELS', json.dumps(inventory))

    def respond(request):
        body = json.loads(request.content)
        assert request.method == 'POST'
        assert request.headers['Authorization'] == 'Bearer ' + keys[body['model']]
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok": true}'}}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        for mid in inventory:
            assert ydata.chat_json('JSON', {}, {'provider': 'ydata', 'id': mid}, client=client) == {'ok': True}


def test_one_broken_family_key_does_not_hide_healthy_models(monkeypatch):
    monkeypatch.delenv('YDATA_API_KEY')
    monkeypatch.setenv('YDATA_GPT_API_KEY', 'good-key')
    monkeypatch.setenv('YDATA_CLAUDE_API_KEY', 'bad-key')

    def respond(request):
        key = request.headers['Authorization'].removeprefix('Bearer ')
        if key == 'bad-key':
            return httpx.Response(401, json={'error': 'never expose this'})
        return httpx.Response(200, json={'data': [{'id': 'gpt-5-test'}]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = ydata.model_catalog(client=client)
    assert result['models'] == [{'id': 'gpt-5-test', 'family': 'GPT'}]
    assert result['unavailable_families'] == ['Claude']


def test_same_key_cannot_be_bound_to_two_families(monkeypatch):
    monkeypatch.delenv('YDATA_API_KEY')
    monkeypatch.setenv('YDATA_GPT_API_KEY', 'same-key')
    monkeypatch.setenv('YDATA_CLAUDE_API_KEY', 'same-key')
    assert ydata.configured() is False
    with pytest.raises(ydata.GatewayError) as exc:
        ydata.model_catalog()
    assert exc.value.code == 'ydata_key_conflict'



@pytest.mark.parametrize('mid,family', [('openai/gpt-5-test','GPT'),('o3-test','GPT'),('anthropic/claude-test','Claude'),
                                       ('deepseek-test','DeepSeek'),('moonshot-test','Kimi'),('glm-5.2','GLM'),
                                       ('gpt-image-test',None),('https://evil.test',None),('',None),(None,None)])
def test_model_families(mid,family):
    assert ydata.family_of(mid) == family


@pytest.mark.parametrize('mid', ['gpt-5-test','claude-test','deepseek-test','kimi-test','glm-5.2'])
def test_families_use_exact_selected_model_and_gateway(mid):
    sent=[]
    def respond(request):
        assert request.url.host == 'www.ydata.space'
        assert request.headers['Authorization'] == 'Bearer synthetic-test-gateway-key'
        if request.method == 'GET': return httpx.Response(200,json=catalog_response())
        body=json.loads(request.content); sent.append(body)
        assert request.url.path == '/v1/chat/completions'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'```json\n{"findings": []}\n```'}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = ydata.chat_json('Return JSON', {'contract_blocks':[{'text':'【脱敏1】'}]}, {'id':mid,'provider':'ydata'}, client=client)
    assert result == {'findings':[]}
    assert len(sent) == 1 and sent[0]['model'] == mid
    assert sent[0]['stream'] is False
    assert 'response_format' not in sent[0] and 'temperature' not in sent[0]
    assert 'synthetic-test-gateway-key' not in json.dumps(sent)


@pytest.mark.parametrize('status', [401,403,429,500,302])
def test_upstream_failures_are_sanitized_and_not_retried(status):
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(status,json={'error':'secret-raw-contract-and-key'},headers={'Location':'https://evil.test'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ydata.GatewayError) as exc: ydata.model_catalog(client=client)
    assert 'secret-raw-contract-and-key' not in str(exc.value)
    assert len(calls) == 1


@pytest.mark.parametrize('finish,content', [('length','{}'),('stop','not json'),('stop','[]'),('stop','{"x":'),('content_filter','{}')])
def test_incomplete_or_invalid_model_output_is_not_published(finish,content):
    def respond(r):
        return httpx.Response(200,json=catalog_response() if r.method=='GET' else {'choices':[{'finish_reason':finish,'message':{'content':content}}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ydata.GatewayError): ydata.chat_json('JSON',{}, {'provider':'ydata','id':'glm-5.2'},client=client)


def test_missing_key_is_not_replaced_by_research_provider_key(monkeypatch):
    monkeypatch.delenv('YDATA_API_KEY')
    monkeypatch.setenv('DEEPSEEK_API_KEY','unrelated-key')
    assert not ydata.configured()
    with pytest.raises(ydata.GatewayError,match='YDATA_API_KEY'): ydata.model_catalog()


def test_configured_inventory_and_unknown_model(monkeypatch):
    monkeypatch.setenv('LEGAL_YDATA_MODELS','["glm-5.2", "claude-test"]')
    assert ydata.select_model('claude-test')['provider']=='ydata'
    with pytest.raises(ydata.GatewayError) as exc: ydata.select_model('gpt-made-up')
    assert exc.value.status_code==422
    monkeypatch.setenv('LEGAL_YDATA_MODELS','["https://evil.test/"]')
    with pytest.raises(ydata.GatewayError): ydata.model_catalog()


def test_catalog_cache_is_key_scoped_and_config_changes_invalidate_it(monkeypatch):
    monkeypatch.setenv('LEGAL_YDATA_MODELS','["glm-5.2"]')
    assert ydata.model_catalog()['models'][0]['id']=='glm-5.2'
    monkeypatch.setenv('LEGAL_YDATA_MODELS','["claude-test"]')
    assert ydata.model_catalog()['models'][0]['id']=='claude-test'
    monkeypatch.setenv('YDATA_API_KEY','...')
    with pytest.raises(ydata.GatewayError): ydata.model_catalog()


def test_review_engine_uses_snapshot_not_global_model(monkeypatch):
    seen=[]
    monkeypatch.setattr(ydata,'chat_json',lambda system,payload,selection: seen.append(selection.copy()) or {})
    for mid in ('claude-test','glm-5.2'):
        review_engine.model_json('JSON', {'profile':{'model':{'id':mid,'provider':'ydata'}}})
    assert [x['id'] for x in seen]==['claude-test','glm-5.2']


@pytest.fixture
def api(tmp_path,monkeypatch):
    path=tmp_path/'auth.db'
    monkeypatch.setattr(database,'_DB_PATH',str(path))
    asyncio.run(database._init_auth_db())
    with sqlite3.connect(path) as db:
        for uid,role in [('free','user'),('pro','user'),('max','user'),('expired','user'),('admin','admin')]:
            db.execute('INSERT INTO users(id,email,username,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',
                       (uid,uid+'@example.test',uid,'test-only',role,datetime.now(timezone.utc).isoformat()))
        for uid,expiry in [('max',None),('expired',(datetime.now(timezone.utc)-timedelta(days=1)).isoformat())]:
            db.execute('INSERT INTO max_memberships(user_id,expires_at,granted_by,updated_at) VALUES(?,?,?,?)',
                       (uid,expiry,'admin',datetime.now(timezone.utc).isoformat()))
        db.execute('INSERT INTO rag_unlimited_users(email,created_by_user_id,created_at) VALUES(?,?,?)',
                   ('pro@example.test','admin',datetime.now(timezone.utc).isoformat()))
    actor={'id':'free','email':'free@example.test','role':'user','plan':'max'}
    app=FastAPI()
    app.include_router(contract_review.router); app.include_router(contract_review.public_router); app.include_router(max_memberships.router)
    app.dependency_overrides[deps.get_current_user]=lambda:actor
    return TestClient(app),actor,path,app


@pytest.mark.parametrize('uid',['free','pro','expired'])
def test_non_max_cannot_use_any_legal_module_endpoint(api,uid,monkeypatch):
    client,actor,_,_=api
    actor.update(id=uid,email=uid+'@example.test')
    monkeypatch.setattr(ydata,'model_catalog',lambda **kw:pytest.fail('non-Max called gateway'))
    monkeypatch.setattr(contract_review.documents,'parse_contract',lambda *args:pytest.fail('non-Max parsed contract'))
    assert client.get('/legal/access').json()['allowed'] is False
    for path in ['/legal/workspace','/legal/models','/legal/capabilities','/legal/contracts?matter_id=m',
                 '/legal/contracts/c','/legal/reviews/r','/legal/reviews/r/export','/legal/policies?org_id=o']:
        assert client.get(path).status_code==403, path
    assert client.post('/legal/contracts',data={'matter_id':'m'},files={'file':('test.txt',b'test')}).status_code==403
    assert client.post('/legal/contracts/c/reviews',json={'model_id':'glm-5.2','external_processing_provider':'ydata',
        'our_role':'采购方','contract_type':'采购合同','external_processing_confirmed':True}).status_code==403
    assert client.post('/legal/reviews/r/resume').status_code==403
    assert client.post('/legal/contracts/c/redaction',json={'revision':1,'confirmed':True}).status_code==403
    assert client.patch('/legal/reviews/r/findings/f',json={'decision':'accepted','expected_version':0}).status_code==403
    assert client.post('/legal/policies?org_id=o',json={'title':'rule','text':'enough text'}).status_code==403
    assert client.put('/legal/policies/p?org_id=o',json={'title':'rule','text':'enough text'}).status_code==403
    assert client.delete('/legal/policies/p?org_id=o&version=1').status_code==403


def test_max_customer_has_access_but_not_admin_privileges(api,monkeypatch):
    client,actor,_,_=api
    actor.update(id='max',email='max@example.test')
    monkeypatch.setenv('LEGAL_YDATA_MODELS','["glm-5.2"]')
    assert client.get('/legal/access').json()['allowed'] is True
    assert client.get('/legal/models').json()['models'][0]['id']=='glm-5.2'
    assert client.get('/admin/max-memberships').status_code==403
    assert client.put('/admin/max-memberships',json={'email':'free@example.test'}).status_code==403


def test_admin_grant_revoke_cas_and_worker_revocation(api):
    client,actor,path,_=api
    actor.update(id='admin',email='admin@example.test',role='admin')
    assert client.put('/admin/max-memberships',json={'email':'free@example.test'}).status_code==200
    access.assert_worker_max('free')
    assert client.put('/admin/max-memberships',json={'email':'free@example.test'}).status_code==409
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT role FROM users WHERE id="free"').fetchone()[0]=='user'
        assert db.execute('SELECT COUNT(*) FROM audit_events WHERE action="membership.max_granted"').fetchone()[0]==1
    assert client.delete('/admin/max-memberships/free?version=2').status_code==409
    assert client.delete('/admin/max-memberships/free?version=1').status_code==200
    with pytest.raises(HTTPException) as exc: access.assert_worker_max('free')
    assert exc.value.status_code==403


def test_invalid_expiry_and_unknown_user_cannot_be_granted(api):
    client,actor,_,_=api
    actor.update(id='admin',email='admin@example.test',role='admin')
    assert client.put('/admin/max-memberships',json={'email':'free@example.test','expires_at':'2020-01-01T00:00:00Z'}).status_code==422
    assert client.put('/admin/max-memberships',json={'email':'missing@example.test'}).status_code==404


def test_unauthenticated_and_old_clients_fail_closed(api):
    client,actor,_,app=api
    actor.update(id='max',email='max@example.test')
    assert client.post('/legal/contracts/c/reviews',json={'our_role':'采购方','contract_type':'采购合同','external_processing_confirmed':True}).status_code==422
    app.dependency_overrides.clear()
    assert client.get('/legal/access').status_code==401
    assert client.get('/legal/models').status_code==401
    assert client.get('/legal/version').json()['max_only'] is True


def test_every_private_legal_route_has_the_guard():
    for route in contract_review.router.routes:
        assert any(d.call is access.require_legal_max for d in route.dependant.dependencies), route.path

def test_regrant_never_reuses_a_revoked_version(api):
    client,actor,path,_=api
    actor.update(id='admin',email='admin@example.test',role='admin')
    assert client.put('/admin/max-memberships',json={'email':'free@example.test'}).json()['version']==1
    assert client.delete('/admin/max-memberships/free?version=1').status_code==200
    assert client.put('/admin/max-memberships',json={'email':'free@example.test','expected_version':0}).status_code==409
    assert client.put('/admin/max-memberships',json={'email':'free@example.test','expected_version':2}).json()['version']==3
    assert client.delete('/admin/max-memberships/free?version=1').status_code==409
    access.assert_worker_max('free')
