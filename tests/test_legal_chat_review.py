"""Chat-style review (ultra_fast and fast tiers). Synthetic model replies and sources only."""
from copy import deepcopy
import json
import pytest
from legal import external_law, review_chat as chat_review, review_quality as quality, review_store as store, review_v2 as v2, ydata

P1 = '甲方应在验收后90日内支付全部价款。'
P2 = '乙方违约的，应按合同总价的百分之三十支付违约金。'
P3 = '本合同自双方签字盖章之日起生效。'
RULES = ['capacity', 'performance', 'liability', 'termination', 'ip_data', 'disputes', 'whole_contract']
LAW = {'id': 'law1', 'text': '第一条 这是用于软件测试的完整条文，不是真实法律依据。', 'title': '测试规则', 'url': 'https://www.gov.cn/test',
       'retrieved_at': '2026-10-01T00:00:00Z'}
MEMO = '## 一、交易概况与我方位置\n合成审查意见书：本合同为采购合同。\n## 二、总体评价\n需谈判付款期限。'


def checklist(ids=RULES):
    return [{'id': i, 'status': 'reviewed', 'note': '合成检查。'} for i in ids]


def item(block='p1', quote='验收后90日内支付', title='付款期限过长', revised='甲方应在验收后30日内支付全部价款。', **extra):
    return {'block_id': block, 'quote': quote, 'title': title, 'category': 'commercial', 'severity': 'high', 'impact': '回款周期长，占用资金。',
            'analysis': '合成分析：九十日账期明显长于行业惯例。', 'revised_text': revised, 'law_refs': [], 'policy_ids': [],
            'missing_facts': [], 'checklist_ids': ['performance'], **extra}


def answer(findings=None, memo=MEMO, checks=None, research=None, finish='stop', reasoning=0):
    result = {'checklist': checklist() if checks is None else checks, 'findings': [item()] if findings is None else findings}
    if research is not None:
        result['research'] = research
    content = f'<review_memo>\n{memo}\n</review_memo>\n<review_result>\n{json.dumps(result, ensure_ascii=False)}\n</review_result>'
    return {'content': content, 'finish': finish, 'reasoning_chars': reasoning}


class Chat:
    """A synthetic chat model: replies in order, streams each reply and records every conversation."""

    def __init__(self, *replies, piece=40):
        self.replies, self.seen, self.piece = list(replies), [], piece

    def __call__(self, messages, selection, *, max_tokens, on_delta):
        self.seen.append({'messages': deepcopy(messages), 'max_tokens': max_tokens, 'model': selection['id']})
        assert self.replies, 'unexpected model request'
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, str):
            reply = {'content': reply, 'finish': 'stop', 'reasoning_chars': 0}
        if reply.get('reasoning_chars'):
            on_delta('', reply['reasoning_chars'])
        for i in range(0, len(reply['content']), self.piece):
            on_delta(reply['content'][i:i + self.piece], 0)
        return reply


def search(*args):
    return {'status': 'retrieved', 'sources': [deepcopy(LAW)], 'provider': 'synthetic', 'warnings': []}


def no_search(*args):
    raise AssertionError('this review must not search')


@pytest.fixture
def runtime(monkeypatch):
    blocks = [{'id': 'p1', 'text': P1, 'page': None}, {'id': 'p2', 'text': P2, 'page': None}, {'id': 'p3', 'text': P3, 'page': 2}]
    contract = {'id': 'c1', 'matter_id': 'm1', 'org_id': 'o1', 'status': 'ready', 'revision': 1,
                'payload': {'redacted_blocks': blocks, 'warnings': ['合成解析提示。'], 'mapping': {}}}
    job = {'id': 'r1', 'contract_id': 'c1', 'created_by': 'u1', 'status': 'queued', 'worker_token': '',
           'payload': {'engine_version': 2, 'contract_revision': 1, 'policies': [],
                       'profile': {'our_role': '采购方', 'contract_type': '采购合同', 'external_processing_provider': 'ydata',
                                   'our_party': {'block_id': 'p1', 'quote': '甲方'}, 'model': {'id': 'glm-5.2', 'provider': 'ydata'}}}}
    history = []

    def claim(rid):
        if job['status'] not in ('queued', 'partial', 'failed'):
            return None
        job.update(worker_token='t%d' % len(history), status='running')
        return job['worker_token']

    def checkpoint(rid, token, payload, status='running'):
        if token != job['worker_token']:
            raise RuntimeError('lost lease')
        job.update(payload=deepcopy(payload), status=status)
        history.append(deepcopy(payload))

    monkeypatch.setattr(store, 'review', lambda rid: deepcopy({k: v for k, v in job.items() if k not in ('history', 'contract')}))
    monkeypatch.setattr(store, 'contract', lambda cid: deepcopy(contract))
    monkeypatch.setattr(store, 'claim', claim)
    monkeypatch.setattr(store, 'checkpoint', checkpoint)
    monkeypatch.setattr(store, 'renew', lambda rid, token: True)
    monkeypatch.setattr(v2, 'RATE_LIMIT_PAUSE', 0)
    monkeypatch.setattr(v2, 'TRANSIENT_PAUSE', 0)
    monkeypatch.setattr(chat_review.random, 'uniform', lambda a, b: 0)
    job['history'], job['contract'] = history, contract
    return job


def run(job, tier, model, retrieve=no_search):
    job['payload']['profile']['review_tier'] = tier
    if job['status'] not in ('queued', 'failed', 'partial'):
        job['status'] = 'queued'
    v2.run_review('r1', chat=model, retrieve=retrieve, authorize=lambda *a: None)
    return job['payload']


def test_ultra_fast_reviews_the_whole_contract_in_one_conversation_turn(runtime):
    model = Chat(answer())
    p = run(runtime, 'ultra_fast', model)
    [request] = model.seen
    system, user = request['messages']
    assert system == {'role': 'system', 'content': chat_review.SYSTEM}
    assert user['role'] == 'user' and '[p1] ' + P1 in user['content'] and '[p3]（第2页） ' + P3 in user['content']
    assert all(f'- {rid}｜' in user['content'] for rid in RULES)
    assert '最多8条' not in system['content'] + user['content'] and '不设条数上限' in system['content']
    assert request['max_tokens'] == ydata.chat_output_tokens()
    assert runtime['status'] == 'completed' and p['engine'] == 'chat' and 'live' not in p
    assert p['stage'] == '极速审查完成（未做法规检索和独立复核），修订稿已就绪，可直接查看、修改并导出'
    assert p['memo'] == MEMO and p['research'] == {'status': 'skipped', 'issues': [], 'rejected_queries': 0, 'reason': 'tier'}
    [f] = p['findings']
    assert f['block_id'] == 'p1' and f['original_quote'] == '验收后90日内支付' and f['reason'].startswith('合成分析')
    assert f['verification_status'] == 'skipped' and f['revision_allowed'] and quality.finding_status(f) == 'quick'
    assert p['decisions'] == {f['id']: {'decision': 'draft', 'text': '甲方应在验收后30日内支付全部价款。', 'block_id': 'p1', 'version': 1,
                                        'manual': False, 'source': 'model', 'legal_basis_confirmed': False}}
    assert {c['rule_id'] for c in p['coverage']} == set(RULES) and all(c['status'] == 'reviewed' for c in p['coverage'])
    assert p['metrics']['model_calls'] == 1 and not p['step_errors'] and not p['retryable']


def test_findings_and_analysis_are_not_capped(runtime):
    blocks = [{'id': f'p{i}', 'text': f'第{i}条 甲方承担第{i}项全部责任且不设上限。', 'page': None} for i in range(1, 46)]
    runtime['contract']['payload']['redacted_blocks'] = blocks
    analysis = '详细分析。' * 600
    findings = [item(block=b['id'], quote=b['text'][:6], title=f'问题{i}', revised=b['text'].replace('不设上限', '以合同总价为上限'),
                     analysis=analysis) for i, b in enumerate(blocks)]
    p = run(runtime, 'ultra_fast', Chat(answer(findings)))
    assert len(p['findings']) == 45 and len(p['decisions']) == 45
    assert all(len(f['reason']) == len(analysis) for f in p['findings'])


def test_a_long_answer_is_continued_in_the_same_conversation(runtime):
    full = answer()['content']
    cut = len(full) // 2
    model = Chat({'content': full[:cut], 'finish': 'length', 'reasoning_chars': 0}, {'content': full[cut:], 'finish': 'stop', 'reasoning_chars': 0})
    p = run(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'completed' and len(p['findings']) == 1 and p['memo'] == MEMO
    second = model.seen[1]['messages']
    assert second[:2] == model.seen[0]['messages']
    assert second[2] == {'role': 'assistant', 'content': full[:cut]} and second[3] == {'role': 'user', 'content': chat_review.CONTINUE}
    assert p['metrics']['continuations'] == 1 and p['metrics']['model_calls'] == 2


def test_reasoning_that_fills_the_output_budget_gets_one_try_with_more_room(runtime):
    model = Chat({'content': '', 'finish': 'length', 'reasoning_chars': 9000}, answer())
    p = run(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'completed' and p['metrics']['reasoning_chars'] == 9000
    assert [s['max_tokens'] for s in model.seen] == [ydata.chat_output_tokens(), 2 * ydata.chat_output_tokens()]


def test_an_unreadable_result_is_sent_back_to_the_model_to_fix(runtime):
    broken = answer()['content'].replace('"findings": [', '"findings": [,', 1)
    fixed = '<review_result>' + json.dumps({'checklist': checklist(), 'findings': [item()]}, ensure_ascii=False) + '</review_result>'
    model = Chat(broken, fixed)
    p = run(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'completed' and p['memo'] == MEMO and len(p['findings']) == 1
    request = model.seen[1]['messages']
    assert request[2] == {'role': 'assistant', 'content': broken} and request[3]['content'].startswith('上一条回答中的 <review_result> 无法读取')
    assert p['metrics']['fixes'] == 1


def test_a_result_that_stays_unreadable_pauses_and_a_retry_writes_a_new_answer(runtime):
    model = Chat('<review_memo>意见书</review_memo><review_result>{"findings": [', 'still not json', '{oops')
    run(runtime, 'ultra_fast', model)
    p = runtime['payload']
    assert runtime['status'] == 'failed' and p['retryable'] and len(model.seen) == 3
    assert p['step_errors'][0]['id'] == 'review' and p['step_errors'][0]['code'] == 'legal_result_unreadable'
    retry = Chat(answer())
    p = run(runtime, 'ultra_fast', retry)
    assert runtime['status'] == 'completed' and len(retry.seen[0]['messages']) == 2 and not p.get('error')


def test_two_texts_for_one_paragraph_are_merged_by_the_model(runtime):
    findings = [item(), item(quote='全部价款', title='付款比例未分期', revised='甲方应在验收后90日内支付价款的百分之九十。')]
    merged = '甲方应在验收后30日内支付价款的百分之九十。'
    model = Chat(answer(findings), f'<merged>{{"paragraphs":[{{"block_id":"p1","revised_text":"{merged}"}}]}}</merged>')
    p = run(runtime, 'ultra_fast', model)
    assert '以下段落在你的结构化结果中有多份不同的修改文本' in model.seen[1]['messages'][-1]['content']
    assert {f['suggested_text'] for f in p['findings']} == {merged}
    assert [d['text'] for d in p['decisions'].values()] == [merged]
    assert not any(f.get('conflict_group') for f in p['findings']) and runtime['status'] == 'completed'


def test_when_a_merge_fails_the_alternatives_wait_for_the_user(runtime):
    findings = [item(), item(quote='全部价款', title='付款比例未分期', revised='甲方应在验收后90日内支付价款的百分之九十。')]
    p = run(runtime, 'ultra_fast', Chat(answer(findings), 'no merged text here'))
    assert all(f['cross_edit_status'] == 'conflict' and not f['revision_allowed'] for f in p['findings'])
    assert not p['decisions'] and runtime['status'] == 'completed'


def test_findings_are_anchored_rather_than_dropped(runtime):
    findings = [
        item(block='p1', quote='百分之三十支付违约金', title='引文在另一段', revised='乙方违约的，应按实际损失支付违约金。'),
        item(block='p2', quote='模型改写过的引文', title='引文对不上', revised=''),
        item(block='第p3段', quote='签字盖章之日起生效', title='编号写法不同', revised=''),
        item(block=None, quote='', title='缺少保密条款', revised='', analysis='建议新增保密条款：……'),
        item(block='p9', quote='', title='编号不存在', revised='甲方应在验收后45日内支付全部价款。'),
    ]
    p = run(runtime, 'ultra_fast', Chat(answer(findings)))
    by_title = {f['title']: f for f in p['findings']}
    assert len(by_title) == 5 and runtime['status'] == 'completed'
    assert by_title['引文在另一段']['block_id'] == 'p2' and by_title['引文在另一段']['original_quote'] == '百分之三十支付违约金'
    assert by_title['引文对不上']['block_id'] == 'p2' and by_title['引文对不上']['original_quote'] == P2
    assert by_title['编号写法不同']['block_id'] == 'p3'
    assert by_title['缺少保密条款']['block_id'] is None and not by_title['缺少保密条款']['suggested_text']
    assert by_title['编号不存在']['block_id'] == 'p1' and by_title['编号不存在']['suggested_text'].endswith('45日内支付全部价款。')


def test_policy_findings_must_name_a_policy_in_force(runtime):
    runtime['payload']['policies'] = [{'id': 'pol1', 'title': '付款规范', 'text': '账期不超过60日。'}]
    findings = [item(category='company_policy', policy_ids=['pol1']), item(block='p2', quote='百分之三十', title='无规范', category='company_policy',
                                                                          policy_ids=['made-up'], revised='')]
    model = Chat(answer(findings))
    p = run(runtime, 'ultra_fast', model)
    assert '- pol1｜付款规范：账期不超过60日。' in model.seen[0]['messages'][1]['content']
    kinds = {f['title']: (f['kind'], f['policy_ids']) for f in p['findings']}
    assert kinds == {'付款期限过长': ('company_policy', ['pol1']), '无规范': ('commercial', [])}


def test_checklist_items_the_model_did_not_report_are_flagged_not_failed(runtime):
    p = run(runtime, 'ultra_fast', Chat(answer(checks=checklist(RULES[:-2]))))
    missing = [c for c in p['coverage'] if c['rule_id'] in RULES[-2:]]
    assert runtime['status'] == 'completed' and all(c['status'] == 'needs_information' and c['note'] == chat_review.UNREPORTED for c in missing)


def test_drafts_go_through_the_exporters_checks(runtime):
    rewritten = '采购方在全部商品完成验收后的次月底结清合同约定的所有采购费用。'
    p = run(runtime, 'ultra_fast', Chat(answer([item(revised=rewritten), item(block='p2', quote='违约金', title='身份信息', revised=P2 + '联系人：张三。')])))
    by_title = {f['title']: f for f in p['findings']}
    assert by_title['付款期限过长']['revision_allowed'] and p['decisions'][by_title['付款期限过长']['id']]['text'] == rewritten
    assert by_title['身份信息']['suggested_text'] and not by_title['身份信息']['revision_allowed']
    assert by_title['身份信息']['id'] not in p['decisions']


def test_resume_rebuilds_model_drafts_but_never_overwrites_a_person(runtime):
    run(runtime, 'ultra_fast', Chat(answer()))
    p = runtime['payload']
    draft = next(iter(p['decisions'].values()))
    draft.update(decision='accepted', user_id='u1', source='user', text='甲方应在验收后45日内支付全部价款。')
    expected = deepcopy(p['decisions'])
    runtime['status'] = 'failed'
    model = Chat()
    run(runtime, 'ultra_fast', model)
    assert not model.seen and runtime['payload']['decisions'] == expected
    assert runtime['payload']['error'].startswith('本轮已有人工决定')


def test_fast_reads_searches_the_law_and_rereads_before_finalising(runtime):
    draft = answer([item(title='初审意见')], memo='初审意见书', research=[
        {'issue': '违约金能否调整', 'checklist_ids': ['liability'], 'laws': [{'name': '测试规则', 'articles': ['第一条']}],
         'queries': ['民法典 违约金 调整']}])
    legal = item(block='p2', quote='百分之三十支付违约金', title='违约金约定过高', revised='乙方违约的，应按实际损失支付违约金。',
                 category='legal', law_refs=[{'law': '测试规则', 'article': '第一条', 'point': '合成要点'}],
                 citations=[{'source_id': 'law1', 'supporting_quote': '这是用于软件测试的完整条文'}], checklist_ids=['liability'])
    model = Chat(draft, answer([item(), legal]))
    queries = []

    def recording(query, keywords):
        queries.append(query)
        return search()
    p = run(runtime, 'fast', model, retrieve=recording)
    assert queries == ['民法典 违约金 调整'] and len(model.seen) == 2
    first, second = model.seen
    assert first['messages'][0]['content'] == chat_review.SYSTEM + chat_review.DRAFT
    assert second['messages'][:2] == first['messages'] and second['messages'][2] == {'role': 'assistant', 'content': draft['content']}
    reread = second['messages'][3]['content']
    assert reread.startswith('请以资深合伙人复核初稿的标准') and '[law1] 测试规则（https://www.gov.cn/test）' in reread
    assert runtime['status'] == 'completed' and p['stage'] == '快速审查完成（已复读定稿，未做独立复核），修订稿已就绪，可直接查看、修改并导出'
    assert p['memo'] == MEMO and {f['title'] for f in p['findings']} == {'付款期限过长', '违约金约定过高'}
    legal_finding = next(f for f in p['findings'] if f['kind'] == 'legal')
    assert legal_finding['evidence_status'] == 'source_matched' and legal_finding['law_refs'][0]['status'] == 'source_matched'
    assert p['research']['status'] == 'done' and p['searches']['issue_1']['status'] == 'retrieved'
    assert any(s['id'] == 'law1' for s in v2.all_sources(p)) and len(p['decisions']) == 2


def test_fast_shows_the_first_review_while_it_rereads(runtime):
    draft = answer([item(title='初审意见')], memo='初审意见书', research=[])
    run(runtime, 'fast', Chat(draft, answer()))
    during = [h for h in runtime['history'] if (h.get('live') or {}).get('step') == 'research']
    assert during and during[0]['live']['memo'] == '初审意见书' and during[0]['live']['activity'] == 'searching'
    assert [f['title'] for f in during[0]['findings']] == ['初审意见'] and not during[0]['findings'][0]['revision_allowed']
    assert 'live' not in runtime['payload'] and runtime['payload']['findings'][0]['title'] == '付款期限过长'


def test_fast_without_a_search_service_still_rereads(runtime, monkeypatch):
    monkeypatch.setattr(external_law, 'provider_status', lambda: {'provider': 'tavily', 'configured': False})
    monkeypatch.setattr(external_law, 'retrieve_law', no_search)
    draft = answer(research=[{'issue': '违约金', 'laws': [{'name': '民法典', 'articles': []}], 'queries': ['民法典 违约金']}])
    model = Chat(draft, answer())
    runtime['payload']['profile']['review_tier'] = 'fast'
    runtime['status'] = 'queued'
    v2.run_review('r1', chat=model, authorize=lambda *a: None)
    p = runtime['payload']
    assert p['research']['status'] == 'skipped' and p['research']['reason'] == 'not_configured'
    assert chat_review.NO_SOURCES['not_configured'] in model.seen[1]['messages'][3]['content']
    assert runtime['status'] == 'completed' and not p['searches']


def test_search_queries_never_carry_contract_details(runtime):
    draft = answer(research=[{'issue': '付款', 'laws': [], 'queries': ['验收后90日内支付全部价款', '【脱敏1】 违约']},
                             {'issue': '违约金', 'laws': [{'name': '中华人民共和国民法典', 'articles': ['第五百八十五条']}], 'queries': ['百分之三十支付违约金 合同']}])
    queries = []
    run(runtime, 'fast', Chat(draft, answer()), retrieve=lambda q, k: queries.append(q) or search())
    assert queries == ['民法典 第五百八十五条']


def test_fast_delivers_the_first_review_when_the_reread_fails_and_a_retry_rereads(runtime):
    failure = ydata.GatewayError('ydata_unavailable', '连接中断。', 502)
    model = Chat(answer([item(title='初审意见')], research=[]), failure, failure, failure)
    p = run(runtime, 'fast', model)
    assert runtime['status'] == 'partial' and p['retryable'] and p['batch_errors'] == {'final': '连接中断。'}
    assert p['step_errors'][0]['title'] == '复读定稿' and p['stage'].startswith('快速审查部分完成：1 个步骤未完成')
    assert [f['title'] for f in p['findings']] == ['初审意见'] and len(p['decisions']) == 1
    retry = Chat(answer())
    p = run(runtime, 'fast', retry)
    assert len(retry.seen) == 1 and retry.seen[0]['messages'][3]['content'].startswith('请以资深合伙人复核初稿的标准')
    assert runtime['status'] == 'completed' and [f['title'] for f in p['findings']] == ['付款期限过长'] and not p['batch_errors']


def test_searching_again_for_missing_law_does_not_call_the_model(runtime):
    draft = answer(research=[{'issue': '违约金', 'laws': [{'name': '测试规则', 'articles': ['第一条']}], 'queries': ['民法典 违约金']}])
    legal = item(block='p2', quote='违约金', title='违约金约定过高', revised='', category='legal',
                 law_refs=[{'law': '测试规则', 'article': '第一条', 'point': '合成要点'}])
    run(runtime, 'fast', Chat(draft, answer([legal])), retrieve=lambda *a: {'status': 'no_verified_source', 'sources': [], 'provider': 'synthetic'})
    p = runtime['payload']
    assert runtime['status'] == 'partial' and p['retryable'] and p['stage'] == '快速审查完成，请逐项确认；1 个法律问题未取得官方原文，可重新检索'
    assert p['findings'][0]['evidence_status'] == 'model_cited'
    model = Chat()
    p = run(runtime, 'fast', model, retrieve=search)
    assert not model.seen and runtime['status'] == 'completed'
    assert p['findings'][0]['evidence_status'] == 'source_matched'


def test_dropped_streams_and_rate_limits_are_retried(runtime):
    limited = ydata.GatewayError('ydata_rate_limited', '限流。', 429, retry_after=0)
    dropped = ydata.GatewayError('ydata_unavailable', '连接中断。', 502)
    model = Chat(limited, dropped, answer())
    run(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'completed' and len(model.seen) == 3


def test_a_route_that_refuses_a_long_output_budget_falls_back_and_continues(runtime):
    refused = ydata.GatewayError('ydata_request_failed', 'YData 请求失败（HTTP 400）。', 502, upstream_status=400)
    model = Chat(refused, answer(), piece=1000)
    run(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'completed'
    assert [s['max_tokens'] for s in model.seen] == [ydata.chat_output_tokens(), ydata.default_output_tokens()]
    assert runtime['payload']['chat']['max_tokens'] == ydata.default_output_tokens()


@pytest.mark.parametrize('code', ['ydata_unauthorized', 'ydata_not_configured'])
def test_configuration_and_permission_errors_stop_without_retrying(runtime, code):
    model = Chat(ydata.GatewayError(code, '合成错误。', 503))
    p = run(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'failed' and len(model.seen) == 1 and p['error'] == '合成错误。'


def test_the_writing_is_streamed_into_the_review_while_it_runs(runtime, monkeypatch):
    monkeypatch.setattr(chat_review, 'LIVE_SECONDS', 0)
    run(runtime, 'ultra_fast', Chat(answer(), piece=10))
    live = [h['live'] for h in runtime['history'] if h.get('live')]
    assert any(x['activity'] == 'writing_memo' and x['memo'] and MEMO.startswith(x['memo'][:10]) for x in live)
    assert any(x['activity'] == 'writing_result' and x['findings'] >= 1 for x in live)
    assert max(x['written'] for x in live) > 0 and 'live' not in runtime['payload']


def test_a_cancelled_review_stops_while_the_model_is_writing(runtime, monkeypatch):
    monkeypatch.setattr(chat_review, 'LIVE_SECONDS', 0)

    class Cancelling(Chat):
        def __call__(self, messages, selection, *, max_tokens, on_delta):
            runtime['status'] = 'cancelled'
            return super().__call__(messages, selection, max_tokens=max_tokens, on_delta=on_delta)
    run(runtime, 'ultra_fast', Cancelling(answer()))
    assert runtime['status'] == 'cancelled' and not runtime['payload'].get('findings')


def test_the_contract_goes_to_the_model_as_one_document_with_its_brief():
    p = {'profile': {'our_role': '采购方', 'our_party': {'block_id': 'p1', 'quote': '甲方'}, 'contract_type': '采购合同',
                     'scenario': {'label': '采购合同', 'role_focus': '重点检查预付保障。'}, 'review_date': '2026-10-10',
                     'transaction_context': {'performance_stage': '谈判中', 'attachments_status': '存在未提供附件', 'business_priority': '付款与回款',
                                             'deal_value': '100000.00', 'currency': 'CNY'}, 'instructions': '请重点看付款。'},
         'transaction_brief': {'gaps': [{'message': '交易日期未提供。'}], 'material_references': [{'block_id': 'p2', 'quote': '详见附件一'}]}}
    text = chat_review.document(p, [{'id': 'p1', 'text': P1}, {'id': 'p2', 'text': '详见附件一', 'page': 3}],
                                [{'id': 'liability', 'title': '违约', 'checks': '检查违约金。'}], [{'id': 'pol1', 'title': '规范', 'text': '账期60日。'}],
                                [{'name': '合同审查方法', 'guidance': '先定位交易。'}], ['合成解析提示。'])
    for expected in ('我方交易角色：采购方', '我方主体：段落 p1 中的“甲方”（用户确认）', '我方关注重点：重点检查预付保障。', '交易日期：未提供',
                     '交易金额 100000.00 CNY', '已知资料缺口：交易日期未提供。', 'p2“详见附件一”', '请重点看付款。', '- liability｜违约：检查违约金。',
                     '- pol1｜规范：账期60日。', '《合同审查方法》\n先定位交易。', '- 合成解析提示。', '[p1] ' + P1, '[p2]（第3页） 详见附件一'):
        assert expected in text


@pytest.mark.parametrize('text', [
    '<review_memo>意见</review_memo>\n<review_result>\n```json\n{"findings": [{"title": "a"},], "checklist": []}\n```\n</review_result>',
    '意见\n<review_result>{"findings": [{"title": "a"}]}',
    '<think>推理</think><review_memo>意见</review_memo>[{"title": "a"}]',
])
def test_answers_are_read_despite_fences_missing_tags_and_trailing_commas(text):
    memo, result, problem = chat_review.split_answer(text)
    assert memo == '意见' and result['findings'] == [{'title': 'a'}] and not problem


def test_standard_and_deep_reviews_do_not_use_the_chat_engine(runtime):
    calls = []

    def model(system, data):
        calls.append(system)
        if system == v2.INTAKE:
            return {'facts': [], 'issues': []}
        if system.startswith(v2.VERIFY):
            return {'checks': [{'finding_id': f['id'], 'status': 'supported', 'replacement_supported': True, 'reason': '支持。'} for f in data['findings']],
                    'coverage_checks': [{'rule_id': c['rule_id'], 'status': 'covered', 'reason': '完整。'} for c in data['coverage']]}
        return {'coverage': [{'rule_id': r['id'], 'status': 'reviewed', 'note': '检查。'} for r in data['rules']], 'findings': []}
    runtime['payload']['profile']['review_tier'] = 'standard'
    v2.run_review('r1', model=model, chat=Chat(), retrieve=search, authorize=lambda *a: None)
    assert calls and runtime['status'] in ('completed', 'partial') and runtime['payload'].get('engine') != 'chat'


def test_review_skills_reach_the_conversation_as_guidance(runtime):
    runtime['payload']['skills'] = [{'id': 's1', 'name': '合成技能', 'version': '1.0.0', 'sha256': 'x' * 64, 'reason': '通用审查方法',
                                     'guidance': '合成指引：先检查付款与验收。', 'source': {'origin': 'in-house'}}]
    model = Chat(answer())
    run(runtime, 'ultra_fast', model)
    user = model.seen[0]['messages'][1]['content']
    assert '【审查方法与检查要点】（经维护的方法与清单，不是法律依据）\n《合成技能》\n合成指引：先检查付款与验收。' in user
