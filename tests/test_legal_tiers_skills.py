"""Review tiers (ultra_fast, fast, standard, deep) and review skills. Synthetic data only."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import pytest
from legal import review_quality as quality, review_store as store, review_v2 as v2, skill_registry as registry, ydata

LAW = {'id': 'law1', 'text': '第一条 这是用于软件测试的完整条文，不是真实法律依据。', 'title': '测试规则', 'url': 'https://www.gov.cn/test',
       'retrieved_at': '2026-09-25T00:00:00Z'}
SKILL = {'id': 's1', 'name': '合成技能', 'version': '1.0.0', 'sha256': 'x' * 64, 'reason': '通用审查方法',
         'guidance': '合成指引：先检查付款与验收。', 'source': {'origin': 'in-house'}}


def search(*args):
    return {'status': 'retrieved', 'sources': [deepcopy(LAW)], 'provider': 'synthetic', 'warnings': []}


def fake_model(system, data):
    if system == v2.INTAKE:
        return {'facts': [], 'issues': [{'rule_ids': ['liability'], 'issue': '违约金能否调整',
                                          'laws': [{'name': '中华人民共和国民法典', 'articles': []}], 'queries': ['民法典 违约金 调整']}]}
    if system.startswith(v2.VERIFY):
        return {'checks': [{'finding_id': f['id'], 'status': 'supported', 'replacement_supported': True, 'reason': '合成复核通过。'} for f in data['findings']],
                'coverage_checks': [{'rule_id': c['rule_id'], 'status': 'covered', 'reason': '合成检查范围完整。'} for c in data['coverage']],
                'proposal_checks': [{'finding_id': c['finding_id'], 'status': 'consistent', 'reason': '不冲突。'} for c in data.get('proposed_changes', [])]}
    rule = data['rules'][0]
    return {'coverage': [{'rule_id': r['id'], 'status': 'reviewed', 'note': '合成检查。'} for r in data['rules']],
            'findings': [{'rule_id': rule['id'], 'block_id': 'p1', 'original_quote': data['contract_blocks'][0]['text'], 'kind': 'commercial',
                          'title': '问题-' + rule['id'], 'severity': 'high', 'impact': '回款周期需要调整。', 'reason': '基于合同的付款期限。',
                          'missing_facts': [], 'citations': [], 'policy_ids': [],
                          'suggested_text': data['contract_blocks'][0]['text'].replace('90', '60')}]}


@pytest.fixture
def runtime(monkeypatch):
    block = {'id': 'p1', 'text': '甲方应在验收后90日内支付全部价款。', 'page': None}
    contract = {'id': 'c1', 'matter_id': 'm1', 'org_id': 'o1', 'status': 'ready', 'revision': 1, 'payload': {'redacted_blocks': [block], 'warnings': []}}
    job = {'id': 'r1', 'contract_id': 'c1', 'created_by': 'u1', 'status': 'queued', 'worker_token': '',
           'payload': {'engine_version': 2, 'contract_revision': 1, 'policies': [],
                       'profile': {'our_role': '采购方', 'contract_type': '采购合同', 'external_processing_provider': 'ydata',
                                   'model': {'id': 'glm-5.2', 'provider': 'ydata'}}}}

    def claim(rid):
        if job['status'] not in ('queued', 'partial', 'failed'):
            return None
        token = uuid4().hex
        job.update(worker_token=token, status='running')
        return token

    def checkpoint(rid, token, payload, status='running'):
        if token != job['worker_token']:
            raise RuntimeError('lost lease')
        job.update(payload=deepcopy(payload), status=status)

    monkeypatch.setattr(store, 'review', lambda rid: deepcopy(job))
    monkeypatch.setattr(store, 'contract', lambda cid: deepcopy(contract))
    monkeypatch.setattr(store, 'claim', claim)
    monkeypatch.setattr(store, 'checkpoint', checkpoint)
    return job


def run_tier(job, tier, model=fake_model, retrieve=search, skills=None):
    job['payload']['profile']['review_tier'] = tier
    if skills is not None:
        job['payload']['skills'] = skills
    seen = []

    def recording(system, data):
        seen.append((system, data))
        return model(system, data)

    v2.run_review('r1', model=recording, retrieve=retrieve, authorize=lambda *a: None)
    kinds = ['intake' if s == v2.INTAKE else 'cross' if s == v2.CROSS_CHECK else 'verify' if s == v2.VERIFY else 'review' for s, _ in seen]
    return seen, kinds


def no_search(*args):
    raise AssertionError('this tier must not search')


def test_ultra_fast_is_one_round_of_review_calls_without_research_or_verification(runtime):
    seen, kinds = run_tier(runtime, 'ultra_fast', retrieve=no_search)
    p = runtime['payload']
    assert kinds == ['review'] * 3 and all(s.endswith(v2.QUICK) for s, _ in seen)
    assert runtime['status'] == 'completed' and p['stage'].startswith('极速审查完成（未做法规检索和独立复核）')
    assert p['research']['status'] == 'skipped' and not p['searches']
    assert all(f['verification_status'] == 'skipped' and not f['revision_allowed'] for f in p['findings'])
    assert {quality.finding_status(f) for f in p['findings']} == {'quick'}
    assert p['summary']['high'] == len(p['findings']) and '未经独立复核' in p['summary']['notice']


def test_fast_verifies_each_group_but_skips_research_and_the_compatibility_pass(runtime):
    seen, kinds = run_tier(runtime, 'fast', retrieve=no_search)
    p = runtime['payload']
    assert sorted(kinds) == ['review'] * 3 + ['verify'] * 3
    assert runtime['status'] == 'completed' and p['stage'].startswith('快速审查完成（已逐项复核')
    assert all(f['revision_allowed'] and f['cross_edit_status'] == 'unchecked' and f['cross_edit_note'] == v2.UNCHECKED for f in p['findings'])


def test_fast_still_blocks_two_different_replacements_for_one_paragraph(runtime):
    def model(system, data):
        raw = fake_model(system, data)
        if system not in (v2.INTAKE,) and not system.startswith(v2.VERIFY):
            for f in raw['findings']:
                f['suggested_text'] = f['original_quote'].replace('90', str(30 + len(data['rules'][0]['id'])))
        return raw
    run_tier(runtime, 'fast', model=model)
    findings = runtime['payload']['findings']
    assert len({f['suggested_text'] for f in findings}) > 1
    assert all(f['cross_edit_status'] == 'conflict' and not f['revision_allowed'] for f in findings)
    assert runtime['status'] == 'partial'


def test_standard_and_deep_keep_research_verification_and_the_compatibility_pass(runtime):
    _, kinds = run_tier(runtime, 'standard')
    assert kinds.count('intake') == 1 and kinds.count('cross') == 1 and kinds.count('verify') == 3
    runtime.update(status='queued', payload={**runtime['payload'], 'batches': {}, 'findings': [], 'searches': {}, 'research': None,
                                             'cross_check': None, 'batch_errors': {}, 'plan': runtime['payload']['plan']})
    seen, kinds = run_tier(runtime, 'deep')
    assert 'collaboration' in runtime['payload'] and any(d['agent_context']['id'] == 'arbiter' for _, d in seen)


def test_reviews_created_before_tiers_keep_their_mode():
    assert v2.review_tier({'review_mode': 'multi_agent'}) == 'deep'
    assert v2.review_tier({'review_mode': 'standard'}) == 'standard' and v2.review_tier({}) == 'standard'
    assert v2.review_tier({'review_mode': 'multi_agent', 'review_tier': 'fast'}) == 'fast'


def test_skills_reach_review_calls_only(runtime):
    seen, kinds = run_tier(runtime, 'standard', skills=[SKILL])
    for (system, data), kind in zip(seen, kinds):
        if kind == 'review':
            assert data['skills'] == [{'name': '合成技能', 'guidance': '合成指引：先检查付款与验收。'}]
        else:
            assert 'skills' not in data
    assert 'skills' in v2.REVIEW and '不是法律依据' in v2.REVIEW


def write_skill(root: Path, skill_id: str, head: str, body: str = '检查要点：付款。') -> None:
    (root / skill_id).mkdir(parents=True)
    (root / skill_id / 'SKILL.md').write_text(f'---\nid: {skill_id}\n{head}\n---\n{body}\n', encoding='utf-8')


def test_registry_validates_selects_within_budget_and_records_provenance(tmp_path):
    base = 'name: 技能\ndescription: 说明\nversion: 2.0.0\nsource:\n  origin: in-house'
    write_skill(tmp_path, 'always-on', base + '\nstatus: active\napplies_to:\n  always: true')
    write_skill(tmp_path, 'by-scenario', base + '\nstatus: active\napplies_to:\n  scenarios: [service]')
    write_skill(tmp_path, 'by-words', base + '\nstatus: active\napplies_to:\n  keywords: [患者, 病历]\n  min_keyword_hits: 2')
    write_skill(tmp_path, 'one-word', base + '\nstatus: active\napplies_to:\n  keywords: [患者, 处方]\n  min_keyword_hits: 2')
    write_skill(tmp_path, 'draft-only', base + '\nstatus: draft\napplies_to:\n  always: true')
    write_skill(tmp_path, 'too-long', base + '\nstatus: active\napplies_to:\n  always: true\ntiers: [ultra_fast]', '长' * 4500)
    write_skill(tmp_path, 'bad-source', 'name: 技能\ndescription: 说明\nstatus: active\nsource:\n  origin: imported')
    write_skill(tmp_path, 'Bad_Id', base + '\nstatus: active')
    (tmp_path / 'broken').mkdir()
    (tmp_path / 'broken' / 'SKILL.md').write_text('no front matter', encoding='utf-8')
    registry.reload()
    loaded = {s['id'] for s in registry.load(tmp_path)}
    assert loaded == {'always-on', 'by-scenario', 'by-words', 'one-word', 'draft-only', 'too-long'}
    profile = {'scenario': {'id': 'service', 'label': '服务合同'}}
    blocks = [{'id': 'p1', 'text': '乙方处理患者病历时应当保密。'}]
    chosen = registry.select(profile, blocks, 'ultra_fast', root=tmp_path)
    assert [s['id'] for s in chosen] == ['always-on', 'by-scenario', 'by-words']
    assert chosen[1]['reason'] == '合同场景：服务合同' and chosen[2]['reason'] == '合同涉及：患者、病历'
    assert chosen[0]['version'] == '2.0.0' and len(chosen[0]['sha256']) == 64
    assert registry.prompt_items(chosen)[0] == {'name': '技能', 'guidance': '检查要点：付款。'}
    assert 'guidance' not in registry.public(chosen)[0]
    catalog = registry.catalog(tmp_path)
    assert 'draft-only' not in {s['id'] for s in catalog['skills']} and catalog['drafts'] == 1
    registry.reload()


def test_bundled_skills_are_valid_attributed_and_fit_every_tier():
    registry.reload()
    skills = registry.load()
    assert {s['id'] for s in skills} >= {'review-method', 'service-tech-contracts', 'personal-information', 'ai-services', 'listed-company', 'cross-border'}
    assert all(s['status'] == 'active' for s in skills)
    adapted = [s for s in skills if s['source']['origin'] != 'in-house']
    assert adapted and all(s['source']['license'] == 'Apache-2.0' and s['source']['repo'].startswith('https://github.com/') for s in adapted)
    assert (registry.SKILLS_DIR / 'LICENSES' / 'Apache-2.0.txt').is_file()
    # A health-data AI consulting contract gets method, scenario, AI and personal-information guidance.
    blocks = [{'id': 'p1', 'text': '乙方为甲方提供人工智能顾问服务与咨询服务，交付物按里程碑验收，并处理患者个人信息。'}]
    for tier in registry.TIERS:
        chosen = registry.select({'scenario': {'id': 'service', 'label': '服务合同'}}, blocks, tier)
        assert [s['id'] for s in chosen][:1] == ['review-method']
        assert {'service-tech-contracts', 'ai-services', 'personal-information'} <= {s['id'] for s in chosen}
        assert sum(len(s['guidance']) for s in chosen) <= registry.BUDGET[tier]


def test_importer_brings_external_skills_in_as_inert_drafts(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location('import_legal_skill', Path(__file__).resolve().parents[1] / 'scripts' / 'import_legal_skill.py')
    importer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(importer)
    source = tmp_path / 'external' / 'SKILL.md'
    source.parent.mkdir()
    source.write_text('---\nname: nda-review\ndescription: Review an NDA.\n---\n# NDA\nCheck the definition of confidential information.\n', encoding='utf-8')
    skills_root = tmp_path / 'skills'
    skills_root.mkdir()
    sha = 'a' * 40
    common = ['--source', str(source), '--repo', 'https://github.com/example/skills', '--commit', sha]
    assert importer.main(common + ['--license', 'Proprietary'], root=skills_root) == 1
    assert importer.main(common + ['--license', 'MIT'], root=skills_root) == 0
    assert importer.main(common + ['--license', 'MIT'], root=skills_root) == 1  # never overwrites
    registry.reload()
    [skill] = registry.load(skills_root)
    assert skill['id'] == 'nda-review' and skill['status'] == 'draft' and skill['source']['license'] == 'MIT'
    assert registry.select({'scenario': {'id': 'nda'}}, [{'id': 'p1', 'text': 'confidential information'}], 'standard', root=skills_root) == []
    registry.reload()


def test_rate_limits_back_off_up_to_three_times_without_losing_the_truncation_retry(runtime, monkeypatch):
    monkeypatch.setattr(v2, 'RATE_LIMIT_PAUSE', 0.01)
    monkeypatch.setattr(v2.random, 'uniform', lambda a, b: 0.0)
    failures = {'limited': 0, 'truncated': 0}

    def model(system, data):
        if system.startswith(v2.REVIEW) and data['rules'][0]['id'] != 'whole_contract':
            if failures['limited'] < 3:
                failures['limited'] += 1
                raise ydata.GatewayError('ydata_rate_limited', '限流', 429, retry_after=0.01)
            if failures['truncated'] < 1:
                failures['truncated'] += 1
                raise ydata.GatewayError('ydata_truncated', '截断', 502)
        return fake_model(system, data)
    run_tier(runtime, 'ultra_fast', model=model, retrieve=no_search)
    assert failures == {'limited': 3, 'truncated': 1}
    assert runtime['status'] == 'completed' and not runtime['payload']['batch_errors']


def test_a_fourth_rate_limit_pauses_the_review_and_keeps_it_retryable(runtime, monkeypatch):
    monkeypatch.setattr(v2, 'RATE_LIMIT_PAUSE', 0.01)
    monkeypatch.setattr(v2.random, 'uniform', lambda a, b: 0.0)

    def model(system, data):
        if data['rules'][0]['id'] == 'whole_contract':
            raise ydata.GatewayError('ydata_rate_limited', '限流', 429)
        return fake_model(system, data)
    run_tier(runtime, 'ultra_fast', model=model, retrieve=no_search)
    assert runtime['payload']['retryable'] and 'consistency' in runtime['payload']['batch_errors']


def test_retry_after_header_is_read_in_seconds_and_capped():
    assert ydata._retry_after('7') == 7.0 and ydata._retry_after('600') == 60.0
    assert ydata._retry_after(None) is None and ydata._retry_after('Wed, 21 Oct 2026 07:28:00 GMT') is None
