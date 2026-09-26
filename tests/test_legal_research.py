"""Model-planned research: guards, evidence matching and bounded retrieval. Synthetic text only."""
import json
import threading
import time
import httpx
import pytest
from legal import external_law as law, research, review_quality as quality, ydata

BLOCKS = [{'id': 'p1', 'text': '甲方应在验收合格后三十日内向【脱敏1】支付服务费人民币伍拾万元。'},
          {'id': 'p2', 'text': '根据《中华人民共和国民法典》的规定，双方协商一致签订本合同。'}]
RULES = [{'id': 'liability', 'title': '违约'}, {'id': 'capacity', 'title': '主体'}]
CODE = '第五百八十四条 当事人一方不履行合同义务，造成对方损失的，应当赔偿。\n第五百八十五条 当事人可以约定一方违约时应当根据违约情况向对方支付一定数额的违约金。\n第五百八十六条 当事人可以约定一方向对方给付定金作为债权的担保。'


@pytest.mark.parametrize('query', ['【脱敏1】 违约责任', '甲方应在验收合格后三十日内 付款', '违约金 伍拾万元', '服务费 500000',
                                   '违约金 50万元', 'x' * 61, '', 'https://evil.test 民法典', 'a@b.cn 保密'])
def test_queries_never_carry_contract_contents(query):
    assert research.guard_query(query, research.contract_fingerprint(BLOCKS)) is None


@pytest.mark.parametrize('query', ['民法典 第五百八十五条 违约金 调整', '中华人民共和国民法典 违约金', '个人信息保护法 敏感个人信息 医疗'])
def test_generic_legal_queries_pass_even_when_the_contract_names_the_statute(query):
    assert research.guard_query(query, research.contract_fingerprint(BLOCKS)) == query


def test_plan_keeps_valid_issues_and_counts_rejected_queries():
    raw = {'issues': [
        {'rule_ids': ['liability', 'made_up'], 'issue': '违约金能否调整', 'laws': [{'name': '《中华人民共和国民法典》', 'articles': ['第五百八十五条第二款', 'x']}],
         'queries': ['甲方应在验收合格后三十日内 违约', '民法典 违约金 调整']},
        {'rule_ids': [], 'issue': '只有法律名称', 'laws': [{'name': '中华人民共和国个人信息保护法', 'articles': []}], 'queries': ['【脱敏1】']},
        {'issue': '无法检索', 'laws': [], 'queries': []}, 'bad']}
    planned = research.plan_issues(raw, RULES, BLOCKS)
    first, second = planned['issues']
    assert first['rule_ids'] == ['liability'] and first['queries'] == ['民法典 违约金 调整']
    assert first['laws'] == [{'name': '中华人民共和国民法典', 'articles': ['第五百八十五条']}]
    assert second['rule_ids'] == ['*'] and second['queries'] == ['个人信息保护法']
    assert planned['rejected_queries'] == 2
    assert research.plan_issues(None, RULES, BLOCKS) == {'issues': [], 'rejected_queries': 0}


def test_model_cited_article_gets_official_text_attached():
    source = {'id': 'law_x', 'title': '权威发布', 'url': 'https://www.court.gov.cn/x', 'text': CODE, 'laws': ['中华人民共和国民法典'],
              'source_kind': 'normative_candidate', 'version_status': 'needs_verification', 'retrieved_at': 't'}
    finding = {'kind': 'legal', 'citations': [], 'evidence_status': 'model_cited',
               'law_refs': [{'law': '民法典', 'article': '第585条', 'point': '违约金', 'status': 'model_cited'},
                            {'law': '民法典', 'article': '第九百九十九条', 'point': '不存在于来源', 'status': 'model_cited'},
                            {'law': '著作权法', 'article': '第五百八十四条', 'point': '别的法律', 'status': 'model_cited'}]}
    units = research.attach_evidence([finding], [source])
    assert len(units) == 1 and units[0]['text'].startswith('第五百八十五条') and '第五百八十六条' not in units[0]['text']
    assert finding['evidence_status'] == 'source_matched' and [r['status'] for r in finding['law_refs']] == ['source_matched', 'model_cited', 'model_cited']
    assert quality.citations(finding['citations'], units) == finding['citations']
    draft = {**source, 'source_kind': 'draft'}
    other = {'kind': 'legal', 'citations': [], 'evidence_status': 'model_cited', 'law_refs': [{'law': '民法典', 'article': '第五百八十五条', 'point': '', 'status': 'model_cited'}]}
    assert research.attach_evidence([other], [draft]) == [] and other['evidence_status'] == 'model_cited'


def test_statute_names_match_on_core_title_only():
    interpretation = {'laws': ['最高人民法院关于适用《中华人民共和国民法典》合同编通则若干问题的解释'], 'title': '权威发布'}
    assert research.law_matches('合同编通则司法解释', interpretation)
    assert research.law_matches('中华人民共和国民法典', {'laws': [], 'title': '中华人民共和国民法典 - 最高人民法院'})
    assert not research.law_matches('著作权法', {'laws': ['中华人民共和国专利法'], 'title': ''})


def test_retrieval_runs_in_parallel_and_a_slow_issue_becomes_a_gap():
    issues = [{'key': f'issue_{i}', 'issue': str(i), 'rule_ids': ['*'], 'laws': [], 'queries': [f'民法典 问题{i}']} for i in range(3)]
    barrier, release = threading.Barrier(2, timeout=5), threading.Event()
    def retrieve(query, keywords):
        if query.endswith('2'):
            release.wait(5)
            return {'status': 'retrieved', 'sources': [], 'provider': 'synthetic'}
        barrier.wait()
        return {'status': 'retrieved', 'sources': [{'id': query, 'text': '第一条 合成'}], 'provider': 'synthetic', 'warnings': []}
    started = time.monotonic()
    found = research.run_retrieval(issues, retrieve, lambda: None, deadline=1)
    release.set()
    assert time.monotonic() - started < 3
    assert found['issue_0']['status'] == found['issue_1']['status'] == 'retrieved'
    assert found['issue_2']['status'] == 'timeout' and not found['issue_2']['sources']


def test_authorization_failure_stops_retrieval():
    def deny():
        raise RuntimeError('revoked')
    issues = [{'key': 'issue_1', 'issue': 'x', 'rule_ids': ['*'], 'laws': [], 'queries': ['民法典 违约金']}]
    with pytest.raises(RuntimeError):
        research.run_retrieval(issues, lambda *a: pytest.fail('must not search'), deny)


def test_excerpt_prefers_the_named_provision_and_article_unit_is_exact():
    assert law.excerpt(CODE, ['第五百八十五条', '违约'], limit=60).startswith('第五百八十五条')
    assert law.article_unit(CODE, 586).startswith('第五百八十六条') and law.article_unit(CODE, 1) == ''


def test_official_pages_are_cached_between_searches(monkeypatch):
    monkeypatch.setenv('LEGAL_SEARCH_PROVIDER', 'bing_rss')
    monkeypatch.setattr(law, '_public_host', lambda _: None)
    law.clear_page_cache()
    fetched = []
    def respond(request):
        if request.url.host == 'www.bing.com':
            return httpx.Response(200, text='<rss><channel><item><title>t</title><link>http://www.gov.cn/code</link></item></channel></rss>')
        fetched.append(str(request.url))
        return httpx.Response(200, headers={'content-type': 'text/html'}, text='<p>' + CODE.replace('\n', '</p><p>') + '</p>')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        first = law.retrieve_law('民法典 违约金', ['违约金'], client=client, cache=True)
        second = law.retrieve_law('民法典 定金', ['定金'], client=client, cache=True)
    law.clear_page_cache()
    assert fetched == ['https://www.gov.cn/code']
    assert first['sources'][0]['url'] == second['sources'][0]['url'] == 'https://www.gov.cn/code'
    assert '第五百八十六条' in second['sources'][0]['text']


def gateway(content, finish='stop'):
    def respond(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'glm-5.2'}]})
        return httpx.Response(200, json={'choices': [{'finish_reason': finish, 'message': {'content': content}}]})
    return httpx.Client(transport=httpx.MockTransport(respond))


def test_truncated_answer_has_its_own_error(monkeypatch):
    monkeypatch.setenv('YDATA_API_KEY', 'synthetic-key')
    ydata.clear_cache()
    with gateway('{"findings": [', 'length') as client:
        with pytest.raises(ydata.GatewayError) as exc:
            ydata.chat_json('JSON', {}, {'provider': 'ydata', 'id': 'glm-5.2'}, client=client)
    assert exc.value.code == 'ydata_truncated'


@pytest.mark.parametrize('content', ['以下是结果：\n{"findings": []}', '<think>先分析合同</think>\n```json\n{"findings": []}\n```'])
def test_preamble_or_thinking_block_does_not_fail_valid_json(monkeypatch, content):
    monkeypatch.setenv('YDATA_API_KEY', 'synthetic-key')
    ydata.clear_cache()
    with gateway(content) as client:
        assert ydata.chat_json('JSON', {}, {'provider': 'ydata', 'id': 'glm-5.2'}, client=client) == {'findings': []}


def test_output_budget_can_be_raised_by_operator(monkeypatch):
    monkeypatch.setenv('LEGAL_YDATA_MAX_TOKENS', '32768')
    assert ydata._token_budget('glm-5.2') == {'max_tokens': 32768}
    monkeypatch.setenv('LEGAL_YDATA_MAX_TOKENS', 'lots')
    assert ydata._token_budget('gpt-5-test') == {'max_completion_tokens': 8192}
    assert json.dumps(ydata._token_budget('glm-5.2'))


def test_followup_may_cite_contract_clause_numbers():
    from legal.review_questions import validate_answer
    blocks = [{'id': 'p3', 'text': '第三条 付款方式\n甲方应在货物验收合格且收到发票后30日内支付货款。'},
              {'id': 'p5', 'text': '第五条 交付\n第一批货物应于2026年10月31日前交付。'}]
    for text, bid, quote in (('付款条件见第三条：验收合格且收到发票后30日内付款。', 'p3', '甲方应在货物验收合格且收到发票后30日内支付货款。'),
                             ('第一批货物的交付条件是10月31日前交付。', 'p5', '第一批货物应于2026年10月31日前交付')):
        result = validate_answer({'answer': text, 'block_refs': [{'block_id': bid, 'quote': quote}], 'uncertain': False}, blocks, [])
        assert result['answer'] == text and result['block_refs'] and not result['uncertain']


def test_followup_legal_answer_with_model_cited_law_is_kept_but_marked():
    from legal.review_questions import validate_answer
    blocks = [{'id': 'p8', 'text': '第八条 乙方对因其故意或重大过失造成的损失不承担责任。'}]
    raw = {'answer': '第八条的免责约定依法可能无效。', 'block_refs': [{'block_id': 'p8', 'quote': '乙方对因其故意或重大过失造成的损失不承担责任'}],
           'law_refs': [{'law': '中华人民共和国民法典', 'article': '第五百零六条', 'point': '故意或重大过失造成财产损失的免责条款无效'}], 'uncertain': False}
    result = validate_answer(raw, blocks, [])
    assert result['answer'] == raw['answer'] and result['uncertain'] is True and result['law_refs'][0]['article'] == '第五百零六条'


def test_unrelated_search_answer_is_retried_and_official_pages_are_not_crowded_out(monkeypatch):
    monkeypatch.setenv('LEGAL_SEARCH_PROVIDER', 'bing_rss')
    monkeypatch.setattr(law, '_public_host', lambda _: None)
    junk = ''.join(f'<item><title>t</title><link>https://shop{i}.example.com/</link></item>' for i in range(6))
    searches = []
    def respond(request):
        if request.url.host == 'www.bing.com':
            searches.append(request.url.params['q'])
            items = junk if len(searches) == 1 else junk + '<item><title>法</title><link>http://www.npc.gov.cn/law</link></item>'
            return httpx.Response(200, text=f'<rss><channel>{items}</channel></rss>')
        return httpx.Response(200, headers={'content-type': 'text/html'}, text='<p>' + CODE.replace('\n', '</p><p>') + '</p>')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = law.retrieve_law('反不正当竞争法 商业秘密 保密义务', ['第五百八十五条'], client=client)
    assert len(searches) == 2 and searches[1].startswith('反不正当竞争法 商业秘密 (site:')
    assert result['status'] == 'retrieved' and result['sources'][0]['url'] == 'https://www.npc.gov.cn/law'
    assert result['sources'][0]['discovery'] == 'search'


def test_each_unused_candidate_records_why(monkeypatch):
    monkeypatch.setenv('LEGAL_SEARCH_PROVIDER', 'bing_rss')
    monkeypatch.setenv('LEGAL_DIRECT_OFFICIAL_FALLBACK', 'false')
    monkeypatch.setattr(law, '_public_host', lambda _: None)
    links = ['https://www.npc.gov.cn/downgrade', 'https://www.gov.cn/forbidden', 'https://www.moj.gov.cn/pdf', 'https://www.cac.gov.cn/unrelated']
    items = ''.join(f'<item><title>t</title><link>{link}</link></item>' for link in links)
    def respond(request):
        if request.url.host == 'www.bing.com':
            return httpx.Response(200, text=f'<rss><channel>{items}</channel></rss>')
        if request.url.path == '/downgrade':
            return httpx.Response(302, headers={'location': 'http://www.npc.gov.cn/downgrade'})
        if request.url.path == '/forbidden':
            return httpx.Response(403)
        if request.url.path == '/pdf':
            return httpx.Response(200, headers={'content-type': 'application/pdf'}, content=b'%PDF')
        return httpx.Response(200, headers={'content-type': 'text/html'}, text='<p>' + '无关内容。' * 40 + '</p>')
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = law.retrieve_law('民法典 违约金', ['第五百八十五条'], client=client)
    assert result['status'] == 'no_verified_source'
    assert [r['reason'] for r in result['rejected']] == ['non_official_source via http://www.npc.gov.cn', 'http_403',
                                                          'unsupported_source_format', 'no_matching_provision']
