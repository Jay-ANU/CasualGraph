"""Tools in the chat-style review: the toolbox, the review's tool loop and both gateways' tool calls.

Synthetic model replies, search results and statute text only; nothing here is real law.
"""
from copy import deepcopy
import json
import time

import httpx
import pytest

from legal import anthropic_gateway, external_law, review_chat as chat_review, review_store as store, review_tools as tools, review_v2 as v2, ydata

P1 = '甲方应在验收后90日内支付全部价款。'
P2 = '乙方违约的，应按合同总价的百分之三十支付违约金。'
P3 = '本合同自双方签字盖章之日起生效。'
P4 = '【脱敏1】应于2025年1月1日前交付全部货物。'
RULES = ['capacity', 'performance', 'liability', 'termination', 'ip_data', 'disputes', 'whole_contract']
STATUTE = ('中华人民共和国测试法\n第五百八十四条 这是用于软件测试的合成条文，不是真实法律。\n'
           '第五百八十五条 当事人可以约定违约金；约定的违约金过分高于造成的损失的，可以请求适当减少。这是合成测试文本。\n'
           '第五百八十六条 这是另一条合成测试条文。')
PAGE = {'id': 'law_page', 'title': '中华人民共和国测试法', 'url': 'https://www.gov.cn/test-law', 'text': STATUTE,
        'source_kind': 'normative_candidate', 'retrieved_at': '2026-10-01T00:00:00Z'}
MEMO = '## 一、交易概况与我方位置\n合成审查意见书。\n## 二、总体评价\n需谈判违约金。'


def blocks():
    return [{'id': 'p1', 'text': P1}, {'id': 'p2', 'text': P2}, {'id': 'p3', 'text': P3}, {'id': 'p4', 'text': P4}]


def toolbox(retrieve=None, tier='ultra_fast', log=None, sources=None, payload=None):
    return tools.Toolbox(tier, blocks(), payload or {'mapping': {'【脱敏1】': '真实主体'}}, retrieve=retrieve,
                         log=[] if log is None else log, sources={} if sources is None else sources)


def call(name, ident='c1', **arguments):
    return {'id': ident, 'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False)}


def run(box, *calls):
    """One round of calls; the parsed content of each reply, in order."""
    return [json.loads(m['content']) for m in box.run(list(calls), lambda: None)]


def found(*sources, status='retrieved'):
    return lambda query, keywords: {'status': status, 'sources': [deepcopy(s) for s in sources], 'provider': 'synthetic'}


# The toolbox ---------------------------------------------------------------------------------------------

def test_search_sends_only_screened_wording_and_returns_citable_sources():
    queries = []

    def retrieve(query, keywords):
        queries.append((query, keywords))
        return {'status': 'retrieved', 'sources': [deepcopy(PAGE)], 'provider': 'synthetic'}
    log, sources = [], {}
    box = toolbox(retrieve, log=log, sources=sources)
    ok, contract_words, token, amount = run(box, call('search_law', 'a', query='测试法 违约金 调整'),
                                            call('search_law', 'b', query='验收后90日内支付全部价款'),
                                            call('search_law', 'c', query='【脱敏1】 违约责任'), call('search_law', 'd', query='违约金 30万元'))
    assert queries == [('测试法 违约金 调整', ['违约金', '调整'])]
    assert ok['status'] == 'ok' and ok['results'][0]['source_id'] == 'law_page' and ok['results'][0]['text'] == STATUTE
    assert all(r['status'] == 'rejected' and r['error'] == tools.UNSAFE for r in (contract_words, token, amount))
    assert sources['law_page']['step'] == 'review' and sources['law_page']['origin'] == 'tool' and sources['law_page']['laws'] == ['测试法']
    assert [(r['name'], r['status']) for r in log] == [('search_law', 'ok')] + [('search_law', 'rejected')] * 3
    assert [r.get('reason') for r in log] == [None, 'unsafe', 'unsafe', 'unsafe']
    assert log[0]['detail'] == '测试法 违约金 调整' and log[0]['count'] == 1 and log[0]['titles'] == ['中华人民共和国测试法']


def test_a_search_with_no_official_text_says_so_rather_than_inventing_one():
    empty, down = toolbox(found()), toolbox(found(status='unavailable'))
    [nothing] = run(empty, call('search_law', query='测试法 违约金'))
    [failed] = run(down, call('search_law', query='测试法 违约金'))
    assert nothing['status'] == 'empty' and '不要编造' in nothing['note'] and empty.log[0]['count'] == 0
    assert failed['status'] == 'error' and not down.sources


def test_an_article_is_read_from_text_already_obtained_without_searching_again():
    box = toolbox(lambda *a: pytest.fail('the article is already here'), sources={'law_page': {**PAGE, 'step': 'review'}})
    [article] = run(box, call('read_law_article', law='《中华人民共和国测试法》', article='第585条'))
    assert article['status'] == 'ok' and article['text'].startswith('第五百八十五条 当事人可以约定违约金')
    assert article['source_id'].startswith('law_') and article['source_id'] in box.sources
    assert box.sources[article['source_id']]['text'] == article['text'] and box.log[0]['detail'] == '中华人民共和国测试法 第585条'


def test_an_article_comes_only_from_the_statute_itself_not_a_page_about_it():
    about = {**PAGE, 'id': 'law_about', 'title': '最高人民法院关于适用《中华人民共和国测试法》若干问题的解释'}
    queries = []
    box = toolbox(lambda query, keywords: queries.append((query, keywords)) or {'status': 'retrieved', 'sources': [deepcopy(about)]})
    [missing] = run(box, call('read_law_article', law='中华人民共和国测试法', article='第五百八十五条'))
    assert queries == [('《中华人民共和国测试法》 第五百八十五条', ['第五百八十五条'])]
    assert missing['status'] == 'empty' and not box.sources
    box = toolbox(found(about, PAGE))
    [article] = run(box, call('read_law_article', law='中华人民共和国测试法', article='第五百八十五条'))
    assert article['status'] == 'ok' and box.sources[article['source_id']]['url'] == PAGE['url']


def test_the_contract_can_be_searched_and_reread_exactly():
    box = toolbox()
    [search, paragraphs, nothing] = run(box, call('find_in_contract', 'a', terms=['违约金', '验收', '９０日']),
                                        call('read_paragraphs', 'b', ids=['p2-p3', 'P1', 'p9']), call('find_in_contract', 'c', terms='保密'))
    hits = {m['term']: [p['block_id'] for p in m['paragraphs']] for m in search['matches']}
    assert hits == {'违约金': ['p2'], '验收': ['p1'], '９０日': ['p1']} and search['matches'][0]['paragraphs'][0]['text'] == P2
    assert [p['block_id'] for p in paragraphs['paragraphs']] == ['p2', 'p3', 'p1'] and paragraphs['missing'] == ['p9']
    assert paragraphs['paragraphs'][0]['text'] == P2 and nothing['status'] == 'empty'
    assert [r['count'] for r in box.log] == [2, 3, 0] and box.log[0]['blocks'] == ['p1', 'p2']


@pytest.mark.parametrize('expression,value', [('1200000 * 30%', '360000'), ('(500000 - 120000) / 500000 * 100', '76'),
                                              ('120万 × 0.3', '360000'), ('1,200,000 * 3 %', '36000'), ('100 / (20 + 30)%', '200'),
                                              ('1/3', '0.3333333333'), ('0.1 + 0.2', '0.3'), ('2 ** 10', '1024')])
def test_sums_are_exact(expression, value):
    [result] = run(toolbox(), call('calculate', expression=expression))
    assert result == {'status': 'ok', 'expression': expression, 'result': value}


@pytest.mark.parametrize('expression', ['10 / 0', '__import__("os")', 'abs(-3)', '2 ** 100000', '(1 + 2', 'x' * 400])
def test_anything_but_arithmetic_is_refused(expression):
    [result] = run(toolbox(), call('calculate', expression=expression))
    assert result['status'] == 'rejected' and result['error']


def test_dates_are_counted_and_moved():
    box = toolbox()
    between, moved, month_end, bad = run(box, call('date_calc', 'a', start='2025-01-01', end='2025-03-01'),
                                         call('date_calc', 'b', start='2025年1月1日', days=30), call('date_calc', 'c', start='2024-01-31', months=1),
                                         call('date_calc', 'd', start='2025-02-30', days=1))
    assert between['days'] == 59 and between['end_weekday'] == '星期六'
    assert moved['result'] == '2025-01-31' and month_end['result'] == '2024-02-29'
    assert bad['status'] == 'rejected' and [r['detail'] for r in box.log][:3] == ['2025-01-01 → 2025-03-01', '2025年1月1日 +30d', '2024-01-31 +1m']


def test_revisions_get_the_exporters_checks_before_they_are_written():
    box = toolbox()
    good, tokens, identity, same, unknown = run(
        box, call('check_revision', 'a', block_id='p1', revised_text='甲方应在验收后30日内支付全部价款。'),
        call('check_revision', 'b', block_id='p4', revised_text='乙方应于2025年1月1日前交付全部货物。'),
        call('check_revision', 'c', block_id='p4', revised_text=P4 + '联系人：张三，电话13800000000。'),
        call('check_revision', 'd', block_id='p3', revised_text=P3), call('check_revision', 'e', block_id='p9', revised_text='x'))
    assert good['status'] == 'ok' and good['passed'] and not good['problems']
    assert tokens['status'] == 'issues' and '脱敏主体' in tokens['problems'][0]
    assert identity['status'] == 'issues' and '身份信息' in identity['problems'][0]
    assert same['status'] == 'issues' and unknown['status'] == 'rejected'
    assert box.log[1]['problems'] == tokens['problems'] and box.log[0]['blocks'] == ['p1']


def test_bad_calls_are_answered_not_run():
    box = toolbox()
    unknown = run(box, call('delete_contract'))[0]
    broken = json.loads(box.run([{'id': 'x', 'name': 'calculate', 'arguments': '{"expression": '}], lambda: None)[0]['content'])
    law = run(box, call('search_law', query='测试法'))[0]
    assert unknown['status'] == 'rejected' and broken['status'] == 'rejected'
    assert law['status'] == 'rejected' and 'search_law' not in box.names and 'read_law_article' not in box.names
    assert [r['reason'] for r in box.log] == ['invalid'] * 3


def test_budgets_stop_a_runaway_loop_but_answer_every_call(monkeypatch):
    monkeypatch.setitem(tools.BUDGETS, 'ultra_fast', {'rounds': 2, 'calls': 3, 'legal': 1, 'characters': 100000})
    box = toolbox(found(PAGE))
    replies = run(box, call('search_law', 'a', query='测试法 违约金'), call('search_law', 'b', query='测试法 定金'),
                  call('calculate', 'c', expression='1+1'), call('calculate', 'd', expression='2+2'), call('calculate', 'e', expression='3+3'))
    assert [r['status'] for r in replies] == ['ok', 'limit', 'ok', 'ok', 'limit']
    assert replies[1]['error'] == tools.LIMITS['legal'] and replies[4]['error'] == tools.LIMITS['calls']
    box.begin('review')
    assert run(box, call('calculate', expression='1+1'))[0]['status'] == 'ok' and len(box.log) == 1


def test_results_beyond_the_answers_room_are_held_back(monkeypatch):
    monkeypatch.setitem(tools.BUDGETS, 'ultra_fast', {'rounds': 2, 'calls': 9, 'legal': 9, 'characters': 300})
    box = toolbox(found(PAGE))
    [law] = run(box, call('search_law', query='测试法 违约金'))
    assert law == {'status': 'limit', 'error': tools.LIMITS['characters']} and not box.sources


def test_calls_run_side_by_side_and_a_slow_one_times_out(monkeypatch):
    monkeypatch.setattr(tools, 'ROUND_SECONDS', .3)

    def slow(query, keywords):
        time.sleep(2 if '定金' in query else .05)
        return {'status': 'retrieved', 'sources': [deepcopy(PAGE)]}
    box = toolbox(slow)
    started = time.monotonic()
    replies = run(box, call('search_law', 'a', query='测试法 定金'), call('search_law', 'b', query='测试法 违约金'), call('calculate', 'c', expression='1+1'))
    assert time.monotonic() - started < 1.5
    assert [r['status'] for r in replies] == ['timeout', 'ok', 'ok'] and [r['id'] for r in box.log] == ['a', 'b', 'c']


def test_a_new_try_at_an_answer_drops_only_that_answers_records_and_sources():
    log, sources = [], {}
    box = toolbox(found(PAGE), log=log, sources=sources)
    run(box, call('search_law', query='测试法 违约金'))
    box.begin('final')
    run(box, call('read_law_article', law='中华人民共和国测试法', article='第五百八十四条'), call('search_law', 'c2', query='测试法 违约金'))
    assert [r['step'] for r in log] == ['review', 'final', 'final'] and {s['step'] for s in sources.values()} == {'review', 'final'}
    assert sources['law_page']['step'] == 'review'
    box.begin('final')
    assert [r['step'] for r in log] == ['review'] and list(sources) == ['law_page'] and box.obtained('review') == [sources['law_page']]


# The review's tool loop ----------------------------------------------------------------------------------

def checklist():
    return [{'id': i, 'status': 'reviewed', 'note': '合成检查。'} for i in RULES]


def item(block='p2', quote='百分之三十支付违约金', title='违约金约定过高', revised='乙方违约的，应按实际损失支付违约金。', **extra):
    return {'block_id': block, 'quote': quote, 'title': title, 'category': 'legal', 'severity': 'high', 'impact': '可能被请求调减。',
            'analysis': '合成分析：违约金明显高于可能的损失。', 'revised_text': revised,
            'law_refs': [{'law': '中华人民共和国测试法', 'article': '第五百八十五条', 'point': '合成要点'}], 'policy_ids': [],
            'missing_facts': [], 'checklist_ids': ['liability'], **extra}


def answer(findings=None, memo=MEMO, prefix=''):
    result = {'checklist': checklist(), 'findings': [item()] if findings is None else findings}
    return {'content': f'{prefix}<review_memo>\n{memo}\n</review_memo>\n<review_result>\n{json.dumps(result, ensure_ascii=False)}\n</review_result>',
            'finish': 'stop', 'reasoning_chars': 0}


def asking(*calls, content='', reasoning=None):
    reply = {'content': content, 'finish': 'tool_calls', 'reasoning_chars': len(reasoning or ''), 'tool_calls': list(calls)}
    if reasoning:
        reply['reasoning'] = reasoning
    return reply


class Agent:
    """A synthetic chat model that may ask for tools: replies in order; each request is recorded."""

    def __init__(self, *replies, piece=40):
        self.replies, self.seen, self.piece = list(replies), [], piece

    def __call__(self, messages, selection, *, max_tokens, on_delta, tools=None):
        self.seen.append({'messages': deepcopy(messages), 'tools': [t['function']['name'] for t in tools or []], 'max_tokens': max_tokens})
        assert self.replies, 'unexpected model request'
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        for i in range(0, len(reply['content']), self.piece):
            on_delta(reply['content'][i:i + self.piece], 0)
        return deepcopy(reply)


@pytest.fixture
def runtime(monkeypatch):
    contract = {'id': 'c1', 'matter_id': 'm1', 'org_id': 'o1', 'status': 'ready', 'revision': 1,
                'payload': {'redacted_blocks': [{**b, 'page': None} for b in blocks()], 'warnings': [], 'mapping': {'【脱敏1】': '真实主体'}}}
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
        job.update(payload=json.loads(json.dumps(payload)), status=status)
        history.append(json.loads(json.dumps(payload)))

    monkeypatch.setattr(store, 'review', lambda rid: deepcopy({k: v for k, v in job.items() if k not in ('history',)}))
    monkeypatch.setattr(store, 'contract', lambda cid: deepcopy(contract))
    monkeypatch.setattr(store, 'claim', claim)
    monkeypatch.setattr(store, 'checkpoint', checkpoint)
    monkeypatch.setattr(store, 'renew', lambda rid, token: True)
    monkeypatch.delenv('LEGAL_CHAT_TOOLS', raising=False)
    monkeypatch.setattr(v2, 'RATE_LIMIT_PAUSE', 0)
    monkeypatch.setattr(v2, 'TRANSIENT_PAUSE', 0)
    monkeypatch.setattr(chat_review, 'LIVE_SECONDS', 0)
    job['history'] = history
    return job


def review(job, tier, model, retrieve=None):
    job['payload']['profile']['review_tier'] = tier
    if job['status'] not in ('queued', 'failed', 'partial'):
        job['status'] = 'queued'
    v2.run_review('r1', chat=model, retrieve=retrieve or found(PAGE), authorize=lambda *a: None)
    return job['payload']


def test_ultra_fast_calls_tools_like_a_chat_app_and_cites_what_they_found(runtime):
    # The id the article will get once read: the provision's own text on the statute's page.
    article = tools.Toolbox._article('中华人民共和国测试法', '第五百八十五条', PAGE, STATUTE.split('\n')[2])[0]
    quote = '约定的违约金过分高于造成的损失的，可以请求适当减少'
    model = Agent(asking(call('search_law', 'c1', query='测试法 违约金 调整'), call('calculate', 'c2', expression='1000000 * 30%'),
                         content='我先核对违约金的法律依据并计算金额。', reasoning='需要先查条文。'),
                  asking(call('read_law_article', 'c3', law='中华人民共和国测试法', article='第五百八十五条')),
                  answer([item(citations=[{'source_id': article['source_id'], 'supporting_quote': quote}])]))
    p = review(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'completed' and len(model.seen) == 3
    opening = model.seen[0]['messages']
    assert opening[0]['content'].startswith(chat_review.SYSTEM) and '可用工具' in opening[0]['content'] and '速度优先' in opening[0]['content']
    assert model.seen[0]['tools'] == tools.offered(True) and model.seen[2]['tools'] == tools.offered(True)
    second = model.seen[1]['messages']
    assert second[:2] == opening and second[2]['role'] == 'assistant' and second[2]['content'] == '我先核对违约金的法律依据并计算金额。'
    assert [c['function']['name'] for c in second[2]['tool_calls']] == ['search_law', 'calculate'] and second[2]['reasoning_content'] == '需要先查条文。'
    assert [(m['role'], m['tool_call_id']) for m in second[3:]] == [('tool', 'c1'), ('tool', 'c2')]
    assert json.loads(second[3]['content'])['results'][0]['source_id'] == 'law_page' and json.loads(second[4]['content'])['result'] == '300000'
    assert json.loads(model.seen[2]['messages'][-1]['content'])['source_id'] == article['source_id']
    assert p['memo'] == MEMO and '我先核对' not in p['memo']
    [f] = p['findings']
    assert f['citations'] == [{'source_id': article['source_id'], 'supporting_quote': quote}] and f['evidence_status'] == 'source_matched'
    assert f['law_refs'][0]['status'] == 'source_matched' and f['verification_note'] == chat_review.TOOL_NOTE['ultra_fast']
    assert {s['id'] for s in v2.all_sources(p)} >= {'law_page', article['source_id']}
    assert [(r['name'], r['status']) for r in p['tool_log']] == [('search_law', 'ok'), ('calculate', 'ok'), ('read_law_article', 'ok')]
    assert p['research'] == {'status': 'tools', 'issues': [], 'rejected_queries': 0} and not p['searches']
    assert p['stage'] == '极速审查完成（按需调用工具，未做独立复核），修订稿已就绪，可直接查看、修改并导出'
    assert p['metrics']['tool_rounds'] == 2 and p['metrics']['tool_calls'] == 3 and p['metrics']['model_calls'] == 3
    assert not p['retryable'] and len(p['decisions']) == 1 and 'live' not in p


def test_a_call_id_a_route_reuses_is_made_unique(runtime):
    model = Agent(asking(call('calculate', 'call_0', expression='1+1')), asking(call('calculate', 'call_0', expression='2+2')), answer())
    p = review(runtime, 'ultra_fast', model)
    history = model.seen[2]['messages']
    first, second = history[2]['tool_calls'][0]['id'], history[4]['tool_calls'][0]['id']
    assert first == 'call_0' and second != 'call_0' and history[5]['tool_call_id'] == second
    assert [r['id'] for r in p['tool_log']] == [first, second]


def test_tool_activity_is_shown_while_the_review_runs(runtime):
    model = Agent(asking(call('find_in_contract', 'c1', terms=['违约金'])), answer())
    review(runtime, 'ultra_fast', model)
    live = [h['live'] for h in runtime['history'] if h.get('live')]
    running = [x for x in live if x['activity'] == 'tools']
    assert running and running[0]['tools'][0]['name'] == 'find_in_contract' and running[0]['tools'][0]['status'] == 'running'
    assert any(x.get('tools') and x['tools'][0]['status'] == 'ok' and x['tools'][0]['count'] == 1 for x in live)
    assert any(x['activity'] == 'writing_result' for x in live)


def test_an_answer_the_model_starts_again_after_a_tool_call_is_read_from_its_last_start(runtime):
    draft = answer([item(title='旧版意见')])['content']
    model = Agent(asking(call('check_revision', 'c1', block_id='p2', revised_text='乙方违约的，应按实际损失支付违约金。'), content=draft),
                  answer(prefix='核对通过，以下是完整结果。\n'))
    p = review(runtime, 'ultra_fast', model)
    assert [f['title'] for f in p['findings']] == ['违约金约定过高'] and p['memo'] == MEMO
    assert chat_review.live_view(draft + '核对通过。' + answer()['content'])[0] == MEMO


def test_an_answer_continued_after_a_tool_round_keeps_both_halves(runtime):
    full = answer()['content']
    cut = len(full) // 2
    model = Agent(asking(call('calculate', 'c1', expression='1+1'), content='先算一下。'),
                  {'content': full[:cut], 'finish': 'length', 'reasoning_chars': 0}, {'content': full[cut:], 'finish': 'stop', 'reasoning_chars': 0})
    p = review(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'completed' and p['memo'] == MEMO and len(p['findings']) == 1
    last = model.seen[2]['messages']
    assert last[-2] == {'role': 'assistant', 'content': full[:cut]} and last[-1] == {'role': 'user', 'content': chat_review.CONTINUE}
    assert last[2]['tool_calls'][0]['id'] == 'c1' and last[3]['role'] == 'tool'


def test_a_model_that_keeps_calling_tools_is_told_to_write_and_then_stopped(runtime, monkeypatch):
    monkeypatch.setitem(tools.BUDGETS, 'ultra_fast', {'rounds': 2, 'calls': 48, 'legal': 12, 'characters': 40000})
    model = Agent(*[asking(call('calculate', 'c%d' % i, expression='1+1')) for i in range(5)])
    p = review(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'failed' and p['step_errors'][0]['code'] == 'legal_tool_loop' and p['retryable']
    refused = json.loads(model.seen[3]['messages'][-1]['content'])
    assert refused == {'status': 'limit', 'error': tools.LIMITS['rounds']} and len(model.seen) == 5
    assert [r['status'] for r in p['tool_log']] == ['ok', 'ok', 'limit', 'limit']


def test_reasoning_goes_back_with_tool_calls_unless_the_route_refuses_it(runtime):
    refused = ydata.GatewayError('ydata_request_failed', 'YData 请求失败（HTTP 400）。', 502, upstream_status=400)
    model = Agent(asking(call('calculate', 'c1', expression='1+1'), reasoning='先算。'), refused, refused, answer())
    review(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'completed' and runtime['payload'].get('chat_tools') is None
    # A refusal first lowers the output budget, then drops the echoed reasoning; the tools stay.
    assert [s['max_tokens'] for s in model.seen] == [ydata.chat_output_tokens()] * 2 + [ydata.default_output_tokens()] * 2
    assert model.seen[2]['messages'][2]['reasoning_content'] == '先算。' and 'reasoning_content' not in model.seen[3]['messages'][2]
    assert model.seen[3]['tools'] == tools.offered(True)


def test_a_route_that_refuses_tools_gets_the_review_without_them(runtime):
    refused = ydata.GatewayError('ydata_request_failed', 'YData 请求失败（HTTP 400）。', 502, upstream_status=400)
    model = Agent(refused, refused, answer())
    p = review(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'completed' and p['chat_tools'] is False and len(model.seen) == 3
    assert [s['tools'] for s in model.seen] == [tools.offered(True), tools.offered(True), []]
    assert [s['max_tokens'] for s in model.seen] == [ydata.chat_output_tokens(), ydata.default_output_tokens(), ydata.default_output_tokens()]
    assert model.seen[2]['messages'][0]['content'] == chat_review.SYSTEM and p['research']['reason'] == 'tier'
    assert p['stage'].startswith('极速审查完成（未做法规检索和独立复核）') and not p['tool_log']
    # A later conversation for this review does not offer them again.
    retry = Agent(answer())
    runtime['status'] = 'failed'
    runtime['payload'].pop('chat')
    review(runtime, 'ultra_fast', retry)
    assert retry.seen[0]['tools'] == []


def test_official_claude_refusing_tools_also_falls_back(runtime):
    runtime['payload']['profile'].update(model={'id': 'claude-test', 'provider': 'anthropic'}, external_processing_provider='anthropic')
    refused = ydata.GatewayError('anthropic_invalid_request', '参数被拒绝。', 422, upstream_status=400)
    model = Agent(refused, refused, answer())
    p = review(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'completed' and p['chat_tools'] is False and model.seen[2]['tools'] == []


def test_fast_uses_tools_in_both_reads_and_rereads_with_what_it_found(runtime):
    model = Agent(asking(call('search_law', 'c1', query='测试法 违约金 调整')), answer([item(title='初审意见')], memo='初审意见书'),
                  asking(call('check_revision', 'c2', block_id='p2', revised_text='乙方违约的，应按实际损失支付违约金。')),
                  answer([item(citations=[{'source_id': 'law_page', 'supporting_quote': '当事人可以约定违约金'}])]))
    p = review(runtime, 'fast', model)
    assert runtime['status'] == 'completed' and len(model.seen) == 4 and all(s['tools'] == tools.offered(True) for s in model.seen)
    assert '本轮是第一遍审查：高风险法律意见所依据的关键条文' in model.seen[0]['messages'][0]['content']
    reread = model.seen[2]['messages']
    assert reread[2] == {'role': 'assistant', 'content': answer([item(title='初审意见')], memo='初审意见书')['content']}
    assert reread[3]['content'].startswith('请以资深合伙人复核初稿的标准') and '[law_page] 中华人民共和国测试法（https://www.gov.cn/test-law）' in reread[3]['content']
    assert '工具仍然可用' in reread[3]['content'] and len(reread) == 4
    assert [(r['step'], r['name']) for r in p['tool_log']] == [('review', 'search_law'), ('final', 'check_revision')]
    assert p['stage'] == '快速审查完成（已复读定稿，未做独立复核），修订稿已就绪，可直接查看、修改并导出'
    [f] = p['findings']
    assert f['title'] == '违约金约定过高' and f['evidence_status'] == 'source_matched' and f['verification_note'] == chat_review.TOOL_NOTE['fast']
    interim = [h for h in runtime['history'] if (h.get('live') or {}).get('step') == 'final']
    assert interim and interim[0]['findings'][0]['title'] == '初审意见' and not interim[0]['findings'][0]['revision_allowed']


def test_fast_retries_only_the_reread_and_keeps_the_first_reads_tools(runtime):
    failure = ydata.GatewayError('ydata_unavailable', '连接中断。', 502)
    model = Agent(asking(call('search_law', 'c1', query='测试法 违约金')), answer([item(title='初审意见')]),
                  asking(call('calculate', 'c2', expression='1+1')), failure, failure, failure)
    p = review(runtime, 'fast', model)
    assert runtime['status'] == 'partial' and p['batch_errors'] == {'final': '连接中断。'} and [f['title'] for f in p['findings']] == ['初审意见']
    assert [(r['step'], r['name']) for r in p['tool_log']] == [('review', 'search_law'), ('final', 'calculate')]
    retry = Agent(answer())
    p = review(runtime, 'fast', retry)
    assert runtime['status'] == 'completed' and len(retry.seen) == 1 and retry.seen[0]['messages'][3]['content'].startswith('请以资深合伙人')
    assert [(r['step'], r['name']) for r in p['tool_log']] == [('review', 'search_law')]


def test_without_a_search_service_only_local_tools_are_offered(runtime, monkeypatch):
    monkeypatch.setattr(external_law, 'provider_status', lambda: {'provider': 'tavily', 'configured': False})
    monkeypatch.setattr(external_law, 'retrieve_law', lambda *a: pytest.fail('no search service'))
    model = Agent(answer([item(law_refs=[])]))
    runtime['payload']['profile']['review_tier'] = 'ultra_fast'
    v2.run_review('r1', chat=model, authorize=lambda *a: None)
    p = runtime['payload']
    assert model.seen[0]['tools'] == ['find_in_contract', 'read_paragraphs', 'calculate', 'date_calc', 'check_revision']
    system = model.seen[0]['messages'][0]['content']
    assert 'search_law' not in system and '检索词只写' not in system and '金额、日期或修改文本' in system
    assert p['research'] == {'status': 'skipped', 'issues': [], 'rejected_queries': 0, 'reason': 'not_configured'}


def test_searches_from_tools_never_carry_contract_details_and_rejections_are_counted(runtime):
    queries = []
    model = Agent(asking(call('search_law', 'c1', query='验收后90日内支付全部价款'), call('search_law', 'c2', query='测试法 违约金')), answer())
    p = review(runtime, 'ultra_fast', model, retrieve=lambda q, k: queries.append(q) or {'status': 'retrieved', 'sources': [deepcopy(PAGE)]})
    assert queries == ['测试法 违约金'] and p['research']['rejected_queries'] == 1


def test_a_search_with_no_result_is_not_a_gap_to_search_again(runtime):
    model = Agent(asking(call('search_law', 'c1', query='测试法 违约金')), answer())
    p = review(runtime, 'ultra_fast', model, retrieve=found(status='no_verified_source'))
    assert runtime['status'] == 'completed' and not p['retryable'] and p['tool_log'][0]['status'] == 'empty'
    assert p['findings'][0]['evidence_status'] == 'model_cited'


def test_a_cancelled_review_stops_between_tool_rounds(runtime):
    class Cancelling(Agent):
        def __call__(self, *args, **kwargs):
            reply = super().__call__(*args, **kwargs)
            runtime['status'] = 'cancelled'
            return reply
    model = Cancelling(asking(call('calculate', 'c1', expression='1+1')), answer())
    review(runtime, 'ultra_fast', model)
    assert runtime['status'] == 'cancelled' and len(model.seen) == 1 and not runtime['payload'].get('findings')


def test_tools_can_be_switched_off(runtime, monkeypatch):
    monkeypatch.setenv('LEGAL_CHAT_TOOLS', '0')
    model = Agent(answer())
    p = review(runtime, 'ultra_fast', model)
    assert model.seen[0]['tools'] == [] and model.seen[0]['messages'][0]['content'] == chat_review.SYSTEM and 'tool_log' in p


# Gateways ------------------------------------------------------------------------------------------------

@pytest.fixture
def ydata_key(monkeypatch):
    monkeypatch.setenv('YDATA_API_KEY', 'synthetic-test-gateway-key')
    for name in list(ydata.FAMILY_KEY_ENVS.values()) + ['LEGAL_YDATA_MODELS', 'ANTHROPIC_API_KEY', 'LEGAL_ANTHROPIC_MODELS']:
        monkeypatch.delenv(name, raising=False)
    ydata.clear_cache()
    yield
    ydata.clear_cache()


def sse(*chunks) -> bytes:
    return (''.join('data: %s\n\n' % json.dumps(c, ensure_ascii=False) for c in chunks) + 'data: [DONE]\n\n').encode()


def openai_gateway(answer_):
    sent = []

    def respond(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'glm-5.2'}, {'id': 'gpt-5-test'}]})
        body = json.loads(request.content)
        sent.append(body)
        return answer_(body)
    return respond, sent


SPECS = tools.specs(['search_law', 'calculate'])
HISTORY = [{'role': 'system', 'content': '审查说明'}, {'role': 'user', 'content': '合同全文'},
           {'role': 'assistant', 'content': '先查一下。', 'tool_calls': [{'id': 'c1', 'type': 'function', 'function': {'name': 'calculate', 'arguments': '{"expression": "1+1"}'}}]},
           {'role': 'tool', 'tool_call_id': 'c1', 'content': '{"status": "ok", "result": "2"}'}]


def test_streamed_tool_calls_are_assembled_with_the_models_reasoning(ydata_key):
    chunks = [{'choices': [{'index': 0, 'delta': {'reasoning_content': '需要检索。'}}]},
              {'choices': [{'index': 0, 'delta': {'content': '我先检索。'}}]},
              {'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'id': 'call_a', 'type': 'function', 'function': {'name': 'search_law', 'arguments': ''}}]}}]},
              {'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': '{"query": "测试法'}}]}}]},
              {'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': ' 违约金"}'}}]}}]},
              {'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 1, 'id': 'call_b', 'function': {'name': 'calculate', 'arguments': '{"expression": "1+1"}'}}]}}]},
              {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]}]
    respond, sent = openai_gateway(lambda body: httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=sse(*chunks)))
    seen = []
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = ydata.chat(HISTORY, {'provider': 'ydata', 'id': 'glm-5.2'}, client=client, tools=SPECS, on_delta=lambda piece, r: seen.append(piece))
    assert result == {'content': '我先检索。', 'finish': 'tool_calls', 'reasoning_chars': 5, 'model': 'glm-5.2', 'reasoning': '需要检索。',
                      'tool_calls': [{'id': 'call_a', 'name': 'search_law', 'arguments': '{"query": "测试法 违约金"}'},
                                     {'id': 'call_b', 'name': 'calculate', 'arguments': '{"expression": "1+1"}'}]}
    assert sent[0]['tools'] == SPECS and sent[0]['messages'] == HISTORY and ''.join(seen) == '我先检索。'


def test_tool_call_pieces_without_an_index_are_assembled_by_id(ydata_key):
    chunks = [{'choices': [{'index': 0, 'delta': {'tool_calls': [{'id': 'call_a', 'function': {'name': 'search_law', 'arguments': '{"query": '}}]}}]},
              {'choices': [{'index': 0, 'delta': {'tool_calls': [{'function': {'arguments': '"测试法 违约金"}'}}]}}]},
              {'choices': [{'index': 0, 'delta': {'tool_calls': [{'id': 'call_b', 'function': {'name': 'calculate', 'arguments': '{"expression": "1+1"}'}}]}}]},
              {'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}]}]
    respond, _ = openai_gateway(lambda body: httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=sse(*chunks)))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = ydata.chat(HISTORY, {'provider': 'ydata', 'id': 'glm-5.2'}, client=client, tools=SPECS)
    assert result['tool_calls'] == [{'id': 'call_a', 'name': 'search_law', 'arguments': '{"query": "测试法 违约金"}'},
                                    {'id': 'call_b', 'name': 'calculate', 'arguments': '{"expression": "1+1"}'}]


def test_a_complete_message_with_tool_calls_and_routes_that_skip_the_finish_reason(ydata_key):
    message = {'content': None, 'tool_calls': [{'id': 'call_a', 'type': 'function', 'function': {'name': 'calculate', 'arguments': '{"expression": "2*3"}'}}]}
    respond, _ = openai_gateway(lambda body: httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': message}]}))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = ydata.chat(HISTORY, {'provider': 'ydata', 'id': 'glm-5.2'}, client=client, tools=SPECS)
        plain = ydata.chat(HISTORY, {'provider': 'ydata', 'id': 'glm-5.2'}, client=client)
    assert result['finish'] == 'tool_calls' and result['tool_calls'] == [{'id': 'call_a', 'name': 'calculate', 'arguments': '{"expression": "2*3"}'}]
    assert plain == {'content': '', 'finish': 'stop', 'reasoning_chars': 0, 'model': 'glm-5.2'}


def test_a_tool_call_cut_off_at_the_output_limit_is_dropped(ydata_key):
    chunks = [{'choices': [{'index': 0, 'delta': {'content': '先查'}}]},
              {'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'id': 'call_a', 'function': {'name': 'search_law', 'arguments': '{"que'}}]}, 'finish_reason': 'length'}]}]
    respond, sent = openai_gateway(lambda body: httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=sse(*chunks)))
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = ydata.chat(HISTORY, {'provider': 'ydata', 'id': 'glm-5.2'}, client=client, tools=SPECS)
    assert result['finish'] == 'length' and 'tool_calls' not in result and result['content'] == '先查'


def claude_events(*blocks, finish='tool_use'):
    events = [{'type': 'message_start', 'message': {'id': 'm', 'type': 'message', 'role': 'assistant', 'content': [], 'model': 'claude-test',
                                                    'stop_reason': None, 'usage': {'input_tokens': 1, 'output_tokens': 1}}}]
    for index, (kind, value) in enumerate(blocks):
        if kind == 'text':
            events += [{'type': 'content_block_start', 'index': index, 'content_block': {'type': 'text', 'text': ''}},
                       {'type': 'content_block_delta', 'index': index, 'delta': {'type': 'text_delta', 'text': value}}]
        else:
            ident, name, arguments = value
            events += [{'type': 'content_block_start', 'index': index, 'content_block': {'type': 'tool_use', 'id': ident, 'name': name, 'input': {}}}]
            events += [{'type': 'content_block_delta', 'index': index, 'delta': {'type': 'input_json_delta', 'partial_json': arguments[i:i + 5]}}
                       for i in range(0, len(arguments), 5)]
        events.append({'type': 'content_block_stop', 'index': index})
    events += [{'type': 'message_delta', 'delta': {'stop_reason': finish, 'stop_sequence': None}, 'usage': {'output_tokens': 9}},
               {'type': 'message_stop'}]
    body = ''.join('event: %s\ndata: %s\n\n' % (e['type'], json.dumps(e, ensure_ascii=False)) for e in events).encode()
    return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=body)


@pytest.fixture
def claude_key(monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic-anthropic-key')
    monkeypatch.setenv('LEGAL_ANTHROPIC_MODELS', '["claude-test"]')
    monkeypatch.delenv('LEGAL_ANTHROPIC_STREAM', raising=False)
    ydata.clear_cache()
    yield
    ydata.clear_cache()


def claude_turn(handler, messages, **options):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return ydata.chat(messages, {'id': 'claude-test', 'provider': 'anthropic'}, client=client, **options)


def test_claude_tool_calls_and_results_use_the_native_blocks_and_the_prompt_cache(claude_key):
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return claude_events(('text', '我先检索。'), ('tool', ('toolu_1', 'search_law', '{"query": "测试法 违约金"}')))
    result = claude_turn(handler, HISTORY, tools=SPECS)
    assert result == {'content': '我先检索。', 'finish': 'tool_calls', 'reasoning_chars': 0, 'model': 'claude-test',
                      'tool_calls': [{'id': 'toolu_1', 'name': 'search_law', 'arguments': '{"query": "测试法 违约金"}'}]}
    body = sent[0]
    assert body['tools'][0] == {'name': 'search_law', 'description': SPECS[0]['function']['description'], 'input_schema': SPECS[0]['function']['parameters']}
    assert body['system'] == '审查说明'
    assert body['messages'] == [
        {'role': 'user', 'content': [{'type': 'text', 'text': '合同全文', 'cache_control': {'type': 'ephemeral'}}]},
        {'role': 'assistant', 'content': [{'type': 'text', 'text': '先查一下。'}, {'type': 'tool_use', 'id': 'c1', 'name': 'calculate', 'input': {'expression': '1+1'}}]},
        {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': 'c1', 'content': '{"status": "ok", "result": "2"}',
                                      'cache_control': {'type': 'ephemeral'}}]}]


def test_a_complete_claude_message_with_a_tool_call(claude_key):
    message = {'id': 'm', 'type': 'message', 'role': 'assistant', 'stop_reason': 'tool_use', 'model': 'claude-test',
               'content': [{'type': 'tool_use', 'id': 'toolu_1', 'name': 'calculate', 'input': {'expression': '2*3'}}]}
    result = claude_turn(lambda request: httpx.Response(200, json=message), HISTORY, tools=SPECS)
    assert result['finish'] == 'tool_calls' and result['tool_calls'] == [{'id': 'toolu_1', 'name': 'calculate', 'arguments': '{"expression": "2*3"}'}]


def test_a_claude_tool_call_without_tools_on_offer_is_not_accepted(claude_key):
    with pytest.raises(ydata.GatewayError) as exc:
        claude_turn(lambda request: claude_events(('tool', ('toolu_1', 'calculate', '{}'))), [{'role': 'user', 'content': '合同全文'}])
    assert exc.value.code == 'anthropic_incomplete'


def test_claude_conversations_without_tools_are_sent_as_before():
    system, turns = anthropic_gateway._conversation([{'role': 'system', 'content': 'S'}, {'role': 'user', 'content': 'A'},
                                                     {'role': 'user', 'content': 'B'}, {'role': 'assistant', 'content': 'C'},
                                                     {'role': 'user', 'content': 'D'}])
    assert system == 'S' and turns == [{'role': 'user', 'content': 'A\n\nB'}, {'role': 'assistant', 'content': 'C'}, {'role': 'user', 'content': 'D'}]
