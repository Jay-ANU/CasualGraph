"""Synthetic source/transaction invariants. Not a substantive legal benchmark."""
from copy import deepcopy
from decimal import Decimal
import json
import httpx
import pytest
from pydantic import ValidationError
from legal import external_law as law, review_quality as quality
from legal.law_evidence import screen_page, evidence_health
from legal.transaction_brief import TransactionContext, build_brief, apply_material_gates


def test_decimal_money_preserved_exactly():
    c = TransactionContext(deal_value='999999999999.99')
    assert c.deal_value == Decimal('999999999999.99')
    assert c.model_dump(mode='json')['deal_value'] == '999999999999.99'
    assert TransactionContext(deal_value=0).deal_value == 0
    assert TransactionContext(deal_value='1000000000000').deal_value == Decimal('1000000000000')


@pytest.mark.parametrize('value', [True, False, -1, 'NaN', 'Infinity', float('nan'), float('inf'), '1e5', '3万元', '1.001', '1000000000000.01', [], {}])
def test_invalid_money_cannot_turn_into_unknown(value):
    with pytest.raises(ValidationError):
        TransactionContext(deal_value=value)


def test_extra_context_cannot_inject_role_or_provider():
    with pytest.raises(ValidationError):
        TransactionContext(provider='other', our_role='替用户决定')


def test_unknown_context_not_turned_into_verified_fact():
    profile = {'transaction_context': TransactionContext().model_dump(mode='json')}
    original = deepcopy(profile)
    b = build_brief(profile, [{'id': 'p1', 'text': '双方按约定履行。'}], [])
    assert b['context_source'] == 'user_statement_not_independently_verified'
    assert b['context']['deal_value'] is None and b['transaction_date'] is None
    assert b['blocked_edit_blocks'] == []
    assert {g['code'] for g in b['gaps']} == {'stage_unknown', 'date_unknown'}
    assert profile == original


@pytest.mark.parametrize('state', ['未知', '无附件', '存在未提供附件'])
def test_referenced_material_gap_cannot_be_omitted_by_model(state):
    blocks = [{'id': 'p1', 'text': '验收标准详见附件一。'}, {'id': 'p2', 'text': '双方负责沟通。'}]
    b = build_brief({'transaction_context': {'attachments_status': state}}, blocks, [])
    assert b['blocked_edit_blocks'] == ['p1'] and b['material_references'][0]['quote'] in blocks[0]['text']
    checked = {'findings': [{'id':'f1','block_id':'p1','revision_allowed': True, 'missing_facts': [], 'validation_warnings': [],
                  'suggested_text':'验收标准详见附件一，由双方书面确定。', 'evidence_status':'not_applicable', 'kind':'commercial'}], 'coverage': []}
    apply_material_gates(checked, b)
    quality.apply_verification(checked, {'checks':[{'finding_id':'f1','status':'supported','replacement_supported':True,'reason':'合成模型同意'}]})
    assert not checked['findings'][0]['revision_allowed'] and checked['findings'][0]['missing_facts']
    apply_material_gates(checked, b)
    assert len(checked['findings'][0]['missing_facts']) == 1


def test_all_attachments_declaration_is_not_a_completeness_certificate():
    b = build_brief({'transaction_context': {'attachments_status':'已提供全部关键附件'}}, [{'id':'p1','text':'详见附件一。'}], [])
    assert b['material_references'] and not b['blocked_edit_blocks']
    assert '不等于' in b['notice'] and 'verified' not in b


def test_no_attachment_statement_is_not_itself_a_reference():
    b = build_brief({'transaction_context': {'attachments_status':'无附件'}}, [{'id':'p1','text':'本合同没有附件。'}], [])
    assert not b['material_references'] and not b['blocked_edit_blocks']


def test_search_scope_contains_court_and_npc_not_only_gov():
    query = law.public_search_query('合成公开主题')
    assert 'site:www.court.gov.cn' in query and 'site:www.npc.gov.cn' in query and ' OR ' in query


BODY = '<html><head><title>合成规定</title></head><body><h1>合成规定</h1><p>自2025年1月2日起施行。</p><p>第一条 违约金测试条文，不是真实法律。'+ '这是完整的合成条文。'*15 + '</p><p>第二条 其他合成内容，只有软件测试用途。</p></body></html>'


def test_live_official_fetch_can_recover_discovery_failure(monkeypatch):
    monkeypatch.setenv('LEGAL_SEARCH_PROVIDER', 'bing_rss')
    monkeypatch.setenv('LEGAL_DIRECT_OFFICIAL_FALLBACK', 'true')
    monkeypatch.setattr(law, '_public_host', lambda _: None)
    seen = []
    def transport(request):
        seen.append(request)
        if request.url.host == 'www.bing.com':
            return httpx.Response(503)
        return httpx.Response(200, headers={'content-type':'text/html; charset=utf-8'}, text=BODY)
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result = law.retrieve_law('合同编通则 违约金', ['违约金'], client=client)
    assert result['status'] == 'retrieved' and result['discovery_status'] == 'unavailable'
    source = result['sources'][0]
    assert source['discovery'] == 'direct_official' and source['source_kind'] == 'normative_candidate'
    assert source['version_status'] == 'needs_verification'
    assert source['effective_date_candidates'][0]['date'] == '2025-01-02'
    assert all(r.method == 'GET' for r in seen)
    assert any('有限' in warning for warning in result['warnings'])


def test_direct_fallback_does_not_bypass_admin_disable(monkeypatch):
    monkeypatch.setenv('LEGAL_SEARCH_PROVIDER', 'disabled')
    with httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail('network not authorized'))) as client:
        assert law.retrieve_law('合同', ['合同'], client=client)['status'] == 'unavailable'
    monkeypatch.setenv('LEGAL_SEARCH_PROVIDER', 'bing_rss')
    monkeypatch.setenv('LEGAL_DIRECT_OFFICIAL_FALLBACK', 'false')
    seen = []
    def fail(request):
        seen.append(request.url.host)
        return httpx.Response(503)
    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        result = law.retrieve_law('合同', ['合同'], client=client)
    assert seen == ['www.bing.com'] and not result['sources']


def test_redirect_snapshot_records_final_official_url(monkeypatch):
    monkeypatch.setenv('LEGAL_SEARCH_PROVIDER', 'bing_rss')
    monkeypatch.setattr(law, '_public_host', lambda _: None)
    def response(r):
        if r.url.host == 'www.bing.com':
            return httpx.Response(200, text='<rss><channel><item><title>检索标题不能证明效力</title><link>https://www.gov.cn/old</link></item></channel></rss>')
        if r.url.path == '/old':
            return httpx.Response(302, headers={'location':'https://www.gov.cn/new'})
        return httpx.Response(200, headers={'content-type':'text/html'}, text=BODY)
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        result = law.retrieve_law('合成公开主题', ['违约金'], client=client)
    assert result['sources'][0]['url'] == 'https://www.gov.cn/new'
    assert result['sources'][0]['requested_url'] == 'https://www.gov.cn/old'


@pytest.mark.parametrize('heading,kind', [('合成规定（征求意见稿）','draft'), ('合成规定答记者问','commentary'), ('合成典型案例','case_material')])
def test_search_title_cannot_promote_non_normative_page(heading, kind):
    raw = BODY.replace('合成规定', heading)
    result = screen_page(raw, law.html_text(raw), '已生效的法律正文')
    assert result['source_kind'] == kind and result['version_status'] == 'needs_verification'
    source = {'id':'s1','text':law.html_text(raw),'source_kind':kind}
    item = {'rule_id':'r','block_id':'p1','original_quote':'甲方应按约付款。','title':'合成法律意见','impact':'合成影响','reason':'合成理由','kind':'legal',
            'missing_facts':[], 'citations':[{'source_id':'s1','supporting_quote':'第一条 违约金测试条文，不是真实法律。'}], 'suggested_text':'甲方应依约按时付款。'}
    checked = quality.validate({'findings':[item]}, [{'id':'r','title':'合成规则'}], [{'id':'p1','text':'甲方应按约付款。'}], [source], [])
    assert checked['findings'][0]['evidence_status'] == 'unverified' and not checked['findings'][0]['suggested_text']


def test_effective_date_candidates_never_autoverify_version():
    body = law.html_text(BODY) + '\n本规定自2026年9月1日起施行。'
    meta = screen_page(BODY, body, '')
    assert len(meta['effective_date_candidates']) == 2
    assert all(x['quote'] in body for x in meta['effective_date_candidates'])
    assert meta['version_status'] != 'verified'


def test_unverified_legal_version_is_not_confirmed_high_risk():
    base={'severity':'high','kind':'legal','verification_status':'supported','evidence_status':'source_matched','missing_facts':[],'revision_allowed':True}
    assert quality.summary([base], [])['high'] == 0
    assert quality.summary([base], [])['unconfirmed'] == 1


def test_excerpts_never_truncate_sole_oversized_provision():
    assert law.excerpt('第一条 违约金'+'x'*17000, ['违约金']) == ''
    body = '第一条 依据第二条规定审查违约金，例外必须保留。\n第二条 其他完整规定。'
    assert len(law.article_units(body)) == 2
    assert '依据第二条规定' in law.excerpt(body, ['违约金'])


def test_retrieval_health_distinguishes_fetch_from_version_checks():
    h = evidence_health({'a':{'status':'retrieved'},'b':{'status':'no_verified_source'}}, [{'source_kind':'commentary','version_status':'needs_verification'}])
    assert h['status'] == 'gaps' and h['failed_or_empty_topics'] == 1
    assert h['version_pending'] == 1 and h['non_authoritative_sources'] == 1


def test_followup_cannot_use_draft_as_legal_rule():
    from legal.review_questions import validate_answer
    body='第一条 此处全部为合成测试草案，不是真实法律。'
    answer=validate_answer({'answer':'依法该合同无效。','citations':[{'source_id':'s1','supporting_quote':body}], 'uncertain':False},
                          [], [{'id':'s1','text':body,'source_kind':'draft'}])
    assert answer['uncertain'] and not answer['citations']
