"""Scenario routing and isolation tests. Synthetic data, not legal accuracy scores."""
from copy import deepcopy
import json
import pytest
from legal import scenarios
from legal.review_plan import build_plan
from legal.transaction_brief import build_brief, apply_material_gates

LABELS = [s['label'] for s in scenarios.catalog()['scenarios']]


@pytest.mark.parametrize('label', LABELS)
def test_each_scene_has_three_unique_special_checks_and_material_guidance(label):
    scene = scenarios.get_scenario(label)
    assert len(scene['rules']) == 3
    assert len({r['id'] for r in scene['rules']}) == 3
    assert scene['materials'] and scene['limits']
    for role in scene['roles']:
        assert scenarios.validate_role(label, role['value']) == role['value']
        assert scenarios.descriptor(scene, role['value'])['role_focus'] == role['focus']
    with pytest.raises(ValueError):
        scenarios.validate_role(label, '未绑定的其他人')


def test_catalog_has_twenty_routes_not_just_extra_labels():
    data = scenarios.catalog()
    assert len(data['scenarios']) == 20 and data['version'] == 1
    ids = [c['id'] for s in data['scenarios'] for c in s['checks']]
    assert len(ids) == len(set(ids)) == 60
    assert {'采购合同', '销售合同', '服务合同', '保密协议'} <= set(LABELS)


def test_catalog_returns_copies_and_rejects_unknown_type():
    first = scenarios.catalog()
    first['scenarios'][0]['roles'].clear()
    assert scenarios.catalog()['scenarios'][0]['roles']
    assert scenarios.normalize_type(' 购销合同 ') == '销售合同'
    assert scenarios.normalize_type('SaaS协议') == 'SaaS订阅协议'
    for value in ('', '劳动合同', '不存在的类型', '全部'):
        with pytest.raises(ValueError):
            scenarios.normalize_type(value)


def test_scopes_do_not_cross_buyer_seller_or_expand_legacy_service_policies():
    rows = [
        {'id':'all','contract_type':'全部'},
        {'id':'sales_legacy','contract_type':'销售合同'},
        {'id':'seller','contract_type':'销售合同','our_roles':['销售方']},
        {'id':'buyer','contract_type':'销售合同','our_roles':['购买方']},
        {'id':'purchase','contract_type':'采购合同'},
        {'id':'service','contract_type':'服务合同'},
    ]
    original = deepcopy(rows)
    assert {p['id'] for p in scenarios.matching_policies(rows,'销售合同','销售方')} == {'all','sales_legacy','seller'}
    assert {p['id'] for p in scenarios.matching_policies(rows,'销售合同','购买方')} == {'all','sales_legacy','buyer'}
    assert {p['id'] for p in scenarios.matching_policies(rows,'SaaS订阅协议','服务接受方')} == {'all'}
    assert rows == original


@pytest.mark.parametrize('label', LABELS)
def test_real_plan_has_independently_verifiable_special_rules(label):
    from legal.review_engine import RULES
    scene = scenarios.get_scenario(label)
    role = scene['roles'][0]['value']
    profile = {'contract_type':label, 'our_role':role,'scenario':scenarios.descriptor(scene,role), 'instructions':'机密客户名称不得进入公开搜索'}
    plan = build_plan(RULES, [{'id':'p1','text':'机密客户名称 预付款 验收'}], profile, [], scenario=scene)
    assert len(plan) == 9 and len({r['id'] for r in plan}) == 9
    assert {r['id'] for r in scene['rules']} <= {r['id'] for r in plan}
    assert all(profile['scenario']['role_focus'] in rule['checks'] for rule in plan)
    assert all(not {'query','keywords','queries','topics'} & set(r) for r in plan)
    assert '机密客户名称' not in json.dumps(plan, ensure_ascii=False)
    if scene['id'] == 'nda':
        perf = next(r for r in plan if r['id']=='performance')
        assert '不是有偿供货' in perf['checks']


def test_legacy_plan_is_not_silently_reinterpreted():
    from legal.review_engine import RULES
    assert len(build_plan(RULES, [], {'our_role':'采购方','contract_type':'采购合同'}, [])) == 6


@pytest.mark.parametrize('state', ['未知','无附件','存在未提供附件'])
def test_supplement_without_original_blocks_rewrites_even_without_reference_keyword(state):
    blocks=[{'id':'p1','text':'支付期限调整为三十日。'}]
    brief=build_brief({'scenario':{'id':'supplement'},'transaction_context':{'attachments_status':state}},blocks,[])
    assert 'original_contract_gap' in {g['code'] for g in brief['gaps']}
    assert brief['blocked_edit_blocks'] == ['p1']
    checked={'findings':[{'block_id':'p1','revision_allowed':True}]}
    apply_material_gates(checked,brief)
    assert not checked['findings'][0]['revision_allowed']


def test_original_contract_reference_is_a_material_dependency():
    b=build_brief({'transaction_context':{'attachments_status':'未知'}},[{'id':'p1','text':'按照原合同计算价款。'}],[])
    assert b['blocked_edit_blocks']==['p1']


@pytest.mark.parametrize('label', LABELS)
def test_api_accepts_each_scenario_and_only_its_roles(label):
    from api.routers.contract_review import ReviewRequest, PolicyRequest
    from pydantic import ValidationError
    scene=scenarios.get_scenario(label)
    fields={'model_id':'test','external_processing_provider':'ydata','contract_type':label,'our_role':scene['roles'][0]['value']}
    assert ReviewRequest(**fields).contract_type == label
    assert PolicyRequest(title='合成规范',text='仅用于测试的规则',contract_type=label,our_roles=[fields['our_role']]).our_roles == [fields['our_role']]
    with pytest.raises(ValidationError):
        ReviewRequest(**{**fields,'our_role':'非法角色'})
    with pytest.raises(ValidationError):
        PolicyRequest(title='合成规范',text='仅用于测试的规则',contract_type=label,our_roles=['非法角色'])


def test_api_rejects_global_role_scope_and_user_defined_scene():
    from api.routers.contract_review import ReviewRequest, PolicyRequest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PolicyRequest(title='合成规范',text='仅用于测试的规则',contract_type='全部',our_roles=['采购方'])
    with pytest.raises(ValidationError):
        ReviewRequest(model_id='x',external_processing_provider='ydata',contract_type='用户自造类型',our_role='采购方')


def test_api_freezes_scene_plan_and_role_filtered_policy(monkeypatch):
    from api.routers import contract_review as api
    from fastapi import HTTPException
    contract={'id':'c','org_id':'o','matter_id':'m','revision':1,'status':'ready',
              'payload':{'redaction_version':2,'mapping':{},'warnings':[], 'redacted_blocks':[{'id':'p1','text':'甲方负责付款。'}]}}
    saved={}; calls=[]
    monkeypatch.setattr(api,'_contract',lambda *a:deepcopy(contract))
    monkeypatch.setattr(api.ydata,'select_model',lambda _: {'id':'synthetic','provider':'ydata'})
    monkeypatch.setattr(api.store,'policies',lambda *a:[{'id':'p1','title':'销售规范','text':'销售方按约收取货款。','contract_type':'销售合同','version':1,'our_roles':['销售方']},
        {'id':'p2','title':'采购规范','text':'采购方应先取得验收。','contract_type':'采购合同','version':1}])
    def create(c,u,f,p): saved.update(payload=deepcopy(p)); return 'r',True
    monkeypatch.setattr(api.store,'create_review',create)
    monkeypatch.setattr(api.store,'review',lambda _:saved)
    monkeypatch.setattr(api,'_review_view',lambda r:r['payload'])
    monkeypatch.setattr(api.engine,'submit',lambda rid:calls.append(rid))
    req=api.ReviewRequest(model_id='synthetic',external_processing_provider='ydata',external_processing_confirmed=True,
        our_party={'block_id':'p1','quote':'甲方'},contract_type='销售合同',our_role='销售方',scenario_revision=scenarios.catalog()['revision'])
    result=api.start_review('c',req,{'id':'u'})
    assert result['profile']['scenario']['id']=='sales'
    assert result['profile']['scenario']['catalog_revision']==scenarios.catalog()['revision']
    assert len(result['plan'])==10 and [p['id'] for p in result['policies']]==['p1']
    assert calls==['r']
    req.scenario_revision='0'*64
    with pytest.raises(HTTPException) as e: api.start_review('c',req,{'id':'u'})
    assert e.value.status_code==409 and calls==['r']
