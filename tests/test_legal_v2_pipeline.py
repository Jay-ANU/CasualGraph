"""Project CI: real module imports, synthetic providers and fixture-scoped store."""
import json
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
        return {'facts':[{'name':'期限','value':'90日','block_id':'p1','quote':data['contract_blocks'][0]['text']}],
                'issues':[{'rule_ids':['liability'],'issue':'违约金能否调整','laws':[{'name':'中华人民共和国民法典','articles':['第五百八十五条']}],
                           'queries':['民法典 违约金 调整']}]}
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
    # planner + three groups x (review, verify) + one compatibility pass over the proposals
    assert len(calls)==8 and len(p['coverage'])==7 and len(p['batches'])==3
    assert all(d['profile']['model']['id']=='glm-5.2' for _,d in calls)
    assert len(p['intake']['facts'])==1 and all(f['revision_allowed'] for f in p['findings'])
    assert p['research']['issues'][0]['queries']==['民法典 违约金 调整'] and p['searches']['issue_1']['status']=='retrieved'
    assert all('anchor' not in b and 'redaction_spans' not in b for _,d in calls for b in d['contract_blocks'])
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
    # only the failed group (review, verify) and the compatibility pass over the changed proposals
    assert len(called)==3
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


def test_frozen_sales_scene_reaches_all_review_steps(runtime, monkeypatch):
    from legal import scenarios, review_engine
    from legal.review_plan import build_plan
    scene = scenarios.get_scenario('销售合同')
    payload = runtime['job']['payload']
    payload['profile'].update(contract_type='销售合同', our_role='销售方', scenario=scenarios.descriptor(scene, '销售方'))
    payload['plan'] = build_plan(review_engine.RULES, runtime['contract']['payload']['redacted_blocks'], payload['profile'], [], scenario=scene)
    expected = {r['id'] for r in scene['rules']}
    calls=[]
    def model(system, data):
        calls.append(data)
        return fake_model(system, data)
    monkeypatch.setattr(v2, 'build_plan', lambda *a, **kw: pytest.fail('frozen plan must not be rebuilt'))
    run(runtime, model=model)
    assert runtime['job']['status'] == 'completed', runtime['job']['payload'].get('error')
    covered = {c['rule_id'].split(':')[-1] for c in runtime['job']['payload']['coverage']}
    assert expected <= covered
    assert calls and all(d['profile']['scenario']['id'] == 'sales' for d in calls)


def test_review_groups_run_concurrently(runtime):
    import threading
    barrier=threading.Barrier(3)
    def model(system,data):
        if system==v2.REVIEW:
            barrier.wait(timeout=5)
        return fake_model(system,data)
    run(runtime,model=model)
    assert runtime['job']['status']=='completed'


def test_failed_compatibility_pass_flags_but_keeps_supported_revisions(runtime):
    def model(system,data):
        if system==v2.CROSS_CHECK:raise runtime['GatewayError']('ydata_invalid_json','合成错误')
        return fake_model(system,data)
    run(runtime,model=model)
    p=runtime['job']['payload']
    assert runtime['job']['status']=='partial' and 'cross_check' in p['batch_errors'] and p['retryable']
    assert p['findings'] and all(f['revision_allowed'] and f['cross_edit_status']=='unchecked' for f in p['findings'])


def test_truncated_output_is_retried_once_with_a_briefer_prompt(runtime):
    prompts=[]
    def model(system,data):
        prompts.append(system)
        if system==v2.REVIEW and data['rules'][0]['id']=='capacity':raise runtime['GatewayError']('ydata_truncated','截断')
        return fake_model(system,data)
    run(runtime,model=model)
    assert runtime['job']['status']=='completed'
    assert any(x.endswith(v2.BRIEFER) for x in prompts)


@pytest.mark.parametrize('mode',['standard','multi_agent'])
def test_large_document_best_case_keeps_revisions_within_context_budget(runtime,mode):
    """Regression: a ~10k-character, 340-paragraph document used to overflow the final step and block every revision."""
    blocks=[{'id':f'p{i}','text':f'{i}.1\u3000乙方应当按照附表约定按期交付第{i}项服务成果，并在甲方书面确认后开具发票；逾期交付的，每日按应付金额的千分之三支付违约金。','page':None,
             'anchor':i,'redaction_spans':[]} for i in range(1,341)]
    runtime['contract']['payload']['redacted_blocks']=blocks
    runtime['job']['payload']['profile']['review_mode']=mode
    long_law='\n'.join(f'第{n}条 '+'合成测试条文，仅用于衡量上下文体量，不是真实法律规定。'*20 for n in range(1,40))
    def search(*args):return {'status':'retrieved','sources':[{**LAW,'id':'law-big','text':long_law[:15000]}],'provider':'synthetic','warnings':[]}
    sizes=[]
    def model(system,data):
        sizes.append(len(system)+len(json.dumps(data,ensure_ascii=False)))
        if system==v2.INTAKE or system.startswith(v2.VERIFY):return fake_model(system,data)
        rules=data['rules'];kind=data.get('specialist',{}).get('allowed_kind','commercial')
        chosen=[blocks[(len(sizes)*7+k*13)%len(blocks)] for k in range(8)]
        return {'coverage':[{'rule_id':r['id'],'status':'reviewed','note':'合成检查。'} for r in rules],
                'findings':[{'rule_id':rules[k%len(rules)]['id'],'block_id':b['id'],'original_quote':b['text'][:40].replace('\u3000',' '),'kind':kind,
                             'title':'交付与违约金约定需收紧','severity':'high','impact':'我方难以按期取得成果。','reason':'交付节点与验收衔接不清。'*6,'missing_facts':[],
                             'citations':[],'policy_ids':[],'law_refs':[{'law':'中华人民共和国民法典','article':'第五百八十五条','point':'违约金调整'}] if kind=='legal' else [],
                             'suggested_text':b['text'].replace('千分之三','千分之五')} for k,b in enumerate(chosen)]}
    v2.run_review('r1',model=model,retrieve=search,authorize=lambda *a:None)
    p=runtime['job']['payload']
    assert not any('预算' in e for e in p.get('batch_errors',{}).values()), p.get('batch_errors')
    assert max(sizes) < v2.MAX_INPUT_CHARACTERS
    assert sum(f['revision_allowed'] for f in p['findings']) >= 8
    assert all('\u3000' in f['original_quote'] for f in p['findings'] if f.get('block_id'))
