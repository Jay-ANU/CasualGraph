"""Project CI: real module imports, synthetic providers and fixture-scoped store."""
from uuid import uuid4
from copy import deepcopy
import pytest
from fastapi import HTTPException
from legal import review_store as store, ydata, review_v2 as v2
from legal.review_questions import validate_answer
LAW={'id':'law1','text':'第一条 这是用于软件测试的完整条文，不是真实法律依据。','title':'测试规则','url':'https://www.gov.cn/test','retrieved_at':'2026-09-25T00:00:00Z'}
def search(*args):return {'status':'retrieved','sources':[deepcopy(LAW)],'provider':'synthetic','warnings':[]}
def fake_model(system,data):
    if system==v2.INTAKE:
        return {'facts':[{'name':'期限','value':'90日','block_id':'p1','quote':data['contract_blocks'][0]['text']}]}
    if system.startswith(v2.VERIFY):
        return {'checks':[{'finding_id':f['id'],'status':'supported','replacement_supported':True,'reason':'合成复核通过。'} for f in data['findings']],
                'coverage_checks':[{'rule_id':c['rule_id'],'status':'covered','reason':'合成检查范围完整。'} for c in data['coverage']],
                'proposal_checks':[{'finding_id':c['finding_id'],'status':'consistent','reason':'合成测试：与其他建议不冲突。'} for c in data.get('proposed_changes', [])]}
    rule=data['rules'][0]
    return {'coverage':[{'rule_id':r['id'],'status':'reviewed','note':'检查全文合成测试。'} for r in data['rules']],
        'findings':[{'rule_id':rule['id'],'block_id':'p1','original_quote':data['contract_blocks'][0]['text'],
                    'kind':'commercial','title':'问题-'+rule['id'],'severity':'high','impact':'回款周期需要调整。',
                    'reason':'基于合同的付款期限。','missing_facts':[],'citations':[],'policy_ids':[],
                    'suggested_text':data['contract_blocks'][0]['text'].replace('90','60')}]}
def run(rt,model=fake_model,retrieve=search,authorize=lambda *a:None):
    return v2.run_review('r1',model=model,retrieve=retrieve,authorize=authorize)
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
def test_full_versioned_pipeline_and_snapshots(runtime):
    calls=[]
    def model(s,d):calls.append((s,d));return fake_model(s,d)
    run(runtime,model=model)
    p=runtime['job']['payload'];assert runtime['job']['status']=='completed'
    assert len(calls)==7 and len(p['coverage'])==7 and len(p['batches'])==3
    assert all(d['profile']['model']['id']=='glm-5.2' for _,d in calls)
    assert len(p['intake']['facts'])==1 and all(f['revision_allowed'] for f in p['findings'])
def test_zero_findings_still_requires_independent_coverage_review(runtime):
    audited=[]
    def model(s,d):
        raw=fake_model(s,d)
        if s==v2.REVIEW:raw['findings']=[]
        if s.startswith(v2.VERIFY):audited.append(d)
        return raw
    run(runtime,model=model)
    assert len(audited)==3 and runtime['job']['status']=='completed'
def test_missing_verifier_output_is_not_a_pass(runtime):
    run(runtime,model=lambda s,d:{} if s.startswith(v2.VERIFY) else fake_model(s,d))
    assert runtime['job']['status']=='partial' and not any(f['revision_allowed'] for f in runtime['job']['payload']['findings'])
def test_search_failure_partial_then_recover_affected_work(runtime):
    run(runtime,retrieve=lambda *a:{'status':'no_verified_source','sources':[],'provider':'synthetic'})
    assert runtime['job']['status']=='partial' and runtime['job']['payload']['retryable']
    intake=deepcopy(runtime['job']['payload']['intake']);seen=[]
    def model(s,d):seen.append(s);return fake_model(s,d)
    run(runtime,model=model)
    assert runtime['job']['status']=='completed' and runtime['job']['payload']['intake']==intake
    assert v2.INTAKE not in seen
def test_failed_batch_preserves_successful_work_and_resume_is_selective(runtime):
    def model(s,d):
        if s==v2.REVIEW and d['rules'][0]['id']=='termination':raise runtime['GatewayError']('ydata_invalid_json','模拟失败')
        return fake_model(s,d)
    run(runtime,model=model)
    p=runtime['job']['payload'];assert runtime['job']['status']=='partial' and '0' in p['batches'] and '3' in p['batch_errors']
    original=deepcopy(p['batches']['0']);called=[]
    def resumed(s,d):called.append((s,d));return fake_model(s,d)
    run(runtime,model=resumed)
    assert runtime['job']['status']=='completed' and runtime['job']['payload']['batches']['0']==original
    assert len(called)==4
def test_cancelled_worker_does_not_publish_late_model_result(runtime):
    def model(s,d):runtime['job'].update(status='cancelled',worker_token='');return fake_model(s,d)
    run(runtime,model=model)
    assert runtime['job']['status']=='cancelled' and 'intake' not in runtime['job']['payload']
def test_revocation_stops_next_external_step(runtime):
    n=0
    def authorize(*a):
        nonlocal n;n+=1
        if n>2:raise HTTPException(403,'revoked')
    calls=[]
    def model(s,d):calls.append(s);return fake_model(s,d)
    run(runtime,model=model,authorize=authorize)
    assert len(calls)<=1 and runtime['job']['status']=='failed'
def test_contract_version_change_stops_late_result(runtime):
    def model(s,d):runtime['contract']['revision']=2;return fake_model(s,d)
    run(runtime,model=model)
    assert 'intake' not in runtime['job']['payload']
def test_no_restart_of_already_decided_partial_review(runtime):
    runtime['job']['payload']['decisions']={'f1':{'decision':'accepted','text':'已确认内容'}}
    run(runtime,model=lambda *a:pytest.fail('must not call a model'))
    assert runtime['job']['status']=='failed' and runtime['job']['payload']['decisions']
def test_source_snapshot_survives_new_search_page_content():
    old={**LAW,'text':'原始完整引文'};new={**LAW,'id':'law-new','text':'变化后的全文'}
    p={'searches':{'rule':{'sources':[new]}},'batches':{'0':{'sources':[old]}}}
    assert {x['text'] for x in v2.all_sources(p)}=={'原始完整引文','变化后的全文'}
def test_followup_unfounded_legal_claim_not_published():
    answer=validate_answer({'answer':'此合同违法无效。','block_refs':[{'block_id':'p1','quote':'合同正文'}]},[{'id':'p1','text':'合同正文'}],[])
    assert answer['uncertain'] and '违法无效' not in answer['answer']
def test_followup_fact_answer_keeps_clickable_reference():
    answer=validate_answer({'answer':'付款时间写的是验收后90日。','block_refs':[{'block_id':'p1','quote':'验收后90日'}],'uncertain':False},[{'id':'p1','text':'验收后90日付款。'}],[])
    assert answer['block_refs'] and '90日' in answer['answer']


def test_standard_engine_receives_frozen_brief_and_cannot_skip_material_gate(runtime):
    from legal.transaction_brief import build_brief
    cp = runtime['contract']['payload']
    cp['redacted_blocks'][0]['text'] += '验收标准详见附件一。'
    payload = runtime['job']['payload']
    payload['profile']['transaction_context'] = {'performance_stage':'谈判中', 'attachments_status':'存在未提供附件', 'deal_value':'100.05'}
    payload['transaction_brief'] = build_brief(payload['profile'], cp['redacted_blocks'], [])
    seen = []
    def model(system, data):
        seen.append(data)
        return fake_model(system, data)
    run(runtime, model=model)
    assert runtime['job']['status'] == 'partial'
    assert seen and all(d['transaction_brief']['context']['deal_value'] == '100.05' for d in seen)
    assert all(f['missing_facts'] and not f['revision_allowed'] for f in runtime['job']['payload']['findings'])
