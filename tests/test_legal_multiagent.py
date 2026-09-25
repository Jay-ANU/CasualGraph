"""Synthetic multi-agent regressions; no external calls or legal assertions."""
from copy import deepcopy
from uuid import uuid4
import threading
import time
import pytest
from fastapi import HTTPException
from legal import review_store as store, ydata, review_multiagent as team, review_v2 as v2
from legal.agent_team import build_tasks, enforce_specialist_scope

LAW={'id':'law1','text':'第一条 本文仅为软件测试合成依据，不是真实法律规定。','title':'合成规则','url':'https://www.gov.cn/test','retrieved_at':'2026-09-25T00:00:00Z'}
def retrieve(*args): return {'status':'retrieved','sources':[deepcopy(LAW)],'provider':'synthetic','warnings':[]}
def fake(system,data):
    if system==v2.INTAKE: return {'facts':[]}
    if system.startswith(v2.VERIFY):
        return {'checks':[{'finding_id':f['id'],'status':'supported','replacement_supported':True,'reason':'合成逐项复核。'} for f in data['findings']],
                'coverage_checks':[{'rule_id':c['rule_id'],'status':'covered','reason':'合成覆盖复核。'} for c in data['coverage']],
                'proposal_checks':[{'finding_id':f['finding_id'],'status':'consistent','reason':'合成兼容检查。'} for f in data.get('proposed_changes',[])]}
    rules=data['rules'];raw={'coverage':[{'rule_id':r['id'],'status':'reviewed','note':'合成规则全范围检查。'} for r in rules],'findings':[]}
    if data.get('specialist',{}).get('id')=='commercial':
        raw['findings']=[{'rule_id':rules[0]['id'],'block_id':'p1','original_quote':data['contract_blocks'][0]['text'],
                        'kind':'commercial','title':'回款周期'+rules[0]['id'],'severity':'high','impact':'我方回款较晚。','reason':'合成交易事实。',
                        'missing_facts':[],'citations':[],'policy_ids':[],'suggested_text':data['contract_blocks'][0]['text'].replace('90','60')}]
    return raw

def run(runtime,model=fake,search=retrieve,authorize=lambda *a:None):
    runtime['job']['payload']['profile']['review_mode']='multi_agent'
    v2.run_review('r1',model=model,retrieve=search,authorize=authorize)

@pytest.fixture
def runtime(monkeypatch):
    block={'id':'p1','text':'甲方应在验收后90日内支付全部价款。','page':None}
    contract={'id':'c1','matter_id':'m1','org_id':'o1','status':'ready','revision':1,'payload':{'redacted_blocks':[block],'warnings':[]}}
    job={'id':'r1','contract_id':'c1','created_by':'u1','status':'queued','worker_token':'','payload':{'engine_version':2,'contract_revision':1,'profile':{'our_role':'采购方','contract_type':'采购合同','external_processing_provider':'ydata','model':{'id':'glm-5.2','provider':'ydata'}},'policies':[]}}
    snapshots=[]
    def get(rid):return deepcopy(job)
    def claim(rid):
        if job['status'] not in ('queued','partial','failed'):return None
        token=uuid4().hex;job.update(worker_token=token,status='running');return token
    def checkpoint(rid,token,payload,status='running'):
        if token!=job['worker_token']:raise RuntimeError('lost lease')
        job.update(payload=deepcopy(payload),status=status);snapshots.append(deepcopy(job))
    monkeypatch.setattr(store,'review',get)
    monkeypatch.setattr(store,'contract',lambda cid:deepcopy(contract))
    monkeypatch.setattr(store,'claim',claim)
    monkeypatch.setattr(store,'checkpoint',checkpoint)
    return {'job':job,'contract':contract,'snapshots':snapshots,'store':store,'GatewayError':ydata.GatewayError}

def test_full_team_has_separate_coverage_and_one_model(runtime):
    calls=[]
    def model(s,d):calls.append(d);return fake(s,d)
    run(runtime,model)
    p=runtime['job']['payload']
    assert runtime['job']['status']=='completed',p.get('error')
    assert len(p['coverage'])==13 and len({c['rule_id'] for c in p['coverage']})==13
    assert len(calls)==11 and all(d['profile']['model']['id']=='glm-5.2' for d in calls)
    assert p['metrics']['model_calls']==11
    assert p['collaboration']['agents'][2]['status']=='not_applicable'
    assert all(f['agent_id']=='commercial' and f['revision_allowed'] for f in p['findings'])

def test_specialists_are_really_parallel(runtime):
    barrier=threading.Barrier(2);seen=set();lock=threading.Lock()
    def model(s,d):
        role=d.get('specialist',{}).get('id')
        if not s.startswith(v2.VERIFY) and role in ('legal','commercial'):
            with lock:
                first=role not in seen;seen.add(role)
            if first:barrier.wait(timeout=3)
        return fake(s,d)
    run(runtime,model)
    assert runtime['job']['status']=='completed' and seen=={'legal','commercial'}

def test_policy_agent_only_receives_its_snapshot(runtime):
    runtime['job']['payload']['policies']=[{'id':'pol1','title':'内规','text':'采购验收后付款。','version':4,'contract_type':'采购合同'}]
    seen=[]
    def model(s,d):seen.append(d);return fake(s,d)
    run(runtime,model)
    assert runtime['job']['status']=='completed'
    assert len(runtime['job']['payload']['coverage'])==14
    for d in seen:
        role=d.get('specialist',{}).get('id')
        if role in ('legal','commercial'):assert not d['company_policies']
        if role=='policy':assert d['company_policies'][0]['version']==4 and not d['legal_sources']

def test_no_raw_contract_in_public_search(runtime):
    seen=[]
    def search(q,k):seen.append(q);return retrieve(q,k)
    run(runtime,search=search)
    assert seen and all('甲方应在验收后90日' not in q for q in seen)
    assert len(seen)==6

def test_agent_role_drift_is_rejected():
    result=enforce_specialist_scope({'findings':[{'kind':'legal','rule_id':'commercial:capacity'}],
        'coverage':[{'rule_id':'commercial:capacity','status':'reviewed'}],'rejected_findings':0},
        {'agent_id':'commercial','kind':'commercial','title':'商业'})
    assert not result['findings'] and result['rejected_findings']==1
    assert result['coverage'][0]['status']=='needs_information'

def test_missing_critic_never_authorizes_revisions(runtime):
    def model(s,d):return {} if d['agent_context']['id']=='critic' else fake(s,d)
    run(runtime,model)
    assert runtime['job']['status']=='partial'
    assert not any(f['revision_allowed'] for f in runtime['job']['payload']['findings'])

def test_missing_arbitration_never_authorizes_revisions(runtime):
    run(runtime,lambda s,d:{} if s==team.ARBITRATE else fake(s,d))
    assert runtime['job']['status']=='partial'
    assert not any(f['revision_allowed'] for f in runtime['job']['payload']['findings'])

def test_conflicting_replacements_not_overruled_by_model():
    findings=[{'block_id':'p1','suggested_text':s,'verification_status':'supported','revision_allowed':True} for s in ('版本甲','版本乙')]
    team.block_conflicting_edits(findings)
    assert all(not f['revision_allowed'] and f['cross_edit_status']=='conflict' for f in findings)

def test_failure_retains_independent_results_and_selective_resume(runtime):
    def model(s,d):
        if d['agent_context']['id']=='legal':raise runtime['GatewayError']('ydata_invalid_json','合成错误')
        return fake(s,d)
    run(runtime,model)
    assert runtime['job']['status']=='partial'
    p=runtime['job']['payload'];old=deepcopy(p['batches']['commercial:0']);calls=[]
    def resumed(s,d):calls.append(d['agent_context']['id']);return fake(s,d)
    run(runtime,resumed)
    assert runtime['job']['status']=='completed'
    assert runtime['job']['payload']['batches']['commercial:0']==old
    assert 'commercial' not in calls and 'intake' not in calls

def test_cancel_late_result_not_published(runtime):
    def model(s,d):runtime['job'].update(status='cancelled',worker_token='');return fake(s,d)
    run(runtime,model)
    assert runtime['job']['status']=='cancelled' and 'intake' not in runtime['job']['payload']

def test_revocation_prevents_any_billable_call(runtime):
    def authorize(*a):raise HTTPException(403,'revoked')
    run(runtime,model=lambda *a:pytest.fail('must not invoke'),authorize=authorize)
    assert runtime['job']['status']=='failed'

def test_shared_budget_under_concurrent_calls(runtime,monkeypatch):
    monkeypatch.setattr(team,'MAX_CALLS_PER_ATTEMPT',4)
    calls=[]
    def model(s,d):calls.append(d);time.sleep(.003);return fake(s,d)
    run(runtime,model)
    assert len(calls)<=4 and runtime['job']['status'] in ('partial','failed')
    assert runtime['job']['payload']['retryable']

def test_every_model_gets_private_input_copy(runtime):
    def model(s,d):
        result=fake(s,d);d['profile']['model']['id']='tampered'
        d['contract_blocks'][0]['text']='tampered'
        return result
    run(runtime,model)
    assert runtime['job']['payload']['profile']['model']['id']=='glm-5.2'
    assert runtime['contract']['payload']['redacted_blocks'][0]['text']!='tampered'

def test_completed_agents_reused_but_arbiter_stays_completed(runtime):
    run(runtime)
    runtime['job']['status']='partial'
    run(runtime,model=lambda *a:pytest.fail('unchanged task must be reused'))
    assert runtime['job']['status']=='completed'
    assert runtime['job']['payload']['collaboration']['agents'][-1]['status']=='completed'

def test_all_rules_assigned_and_namespaced():
    plan=[{'id':'r1','title':'规则','queries':[]},{'id':'policy_a','policy_id':'a','title':'内规','queries':[]}]
    tasks=build_tasks(plan)
    assert {r['id'] for t in tasks for r in t['rules']}=={'legal:r1','commercial:r1','policy:policy_a'}

def test_identical_issue_with_different_edits_is_not_silently_deduplicated():
    from legal import review_quality as q
    a={'id':'a','kind':'commercial','block_id':'p1','title':'付款期限','original_quote':'90日', 'suggested_text':'60日','revision_allowed':True,'severity':'high'}
    b={**a,'id':'b','suggested_text':'30日'}
    found,_=q.consolidate({'second':{'findings':[b]},'first':{'findings':[a]}})
    assert len(found)==2 and all(f['conflict_group']=='p1' for f in found)


def test_team_critic_and_arbiter_cannot_erase_material_gap(runtime):
    from legal.transaction_brief import build_brief
    cp = runtime['contract']['payload']
    cp['redacted_blocks'][0]['text'] += '验收标准详见附件一。'
    payload = runtime['job']['payload']
    payload['profile']['transaction_context'] = {'performance_stage':'谈判中', 'attachments_status':'未知'}
    payload['transaction_brief'] = build_brief(payload['profile'], cp['redacted_blocks'], [])
    seen = []
    def model(system, data):
        seen.append(data)
        return fake(system, data)
    run(runtime, model=model)
    assert runtime['job']['status'] == 'partial'
    assert all(d['transaction_brief']['material_references'] for d in seen)
    assert all(f['missing_facts'] and not f['revision_allowed'] for f in runtime['job']['payload']['findings'])
