"""Public-query live retrieval diagnostic; never uses a contract or model credential.

Runs the kind of generic queries the research planner writes, and logs for each one what
the search provider returned, which candidates passed the official-source checks and
what was fetched. Success here shows a page was obtained, not that the law applies.
"""
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legal import external_law as law  # noqa: E402

QUERIES = [
    ('民法典 第五百八十五条 违约金 调整', ['第五百八十五条', '违约金', '调整']),
    ('个人信息保护法 敏感个人信息 医疗健康', ['敏感个人信息', '医疗健康', '委托处理']),
    ('反不正当竞争法 商业秘密 保密义务', ['商业秘密', '保密']),
    ('合同编通则司法解释 第六十五条 违约金 损失', ['第六十五条', '违约金']),
]


def candidates(query: str) -> list[dict]:
    status = law.provider_status()
    try:
        with law._client() as client:
            rows = law.discover(client, query, status['provider'])
    except Exception as exc:  # diagnostic only
        return [{'error': type(exc).__name__}]
    return [{'url': url, 'admitted': law.official_url(law.upgrade_scheme(url))} for url, _ in rows[:8]]


def search_variants() -> list[dict]:
    """Which public search requests return official pages at all. Diagnostic only."""
    import httpx
    from urllib.parse import urlparse
    browser = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
               'Accept-Language': 'zh-CN,zh;q=0.9'}
    zh = {'setlang': 'zh-Hans', 'mkt': 'zh-CN', 'cc': 'CN'}
    report = []
    for query in ('民法典 第五百八十五条 违约金', '反不正当竞争法 商业秘密'):
        variants = [
            ('bing-current', 'https://www.bing.com/search', {'q': law.public_search_query(query), 'format': 'rss'}, {}),
            ('bing-zh', 'https://www.bing.com/search', {'q': law.public_search_query(query), 'format': 'rss', **zh}, {}),
            ('bing-zh-site-gov', 'https://www.bing.com/search', {'q': query + ' site:gov.cn', 'format': 'rss', **zh}, {}),
            ('bing-zh-browser', 'https://www.bing.com/search', {'q': query + ' site:gov.cn', 'format': 'rss', **zh}, browser),
            ('cn-bing-zh', 'https://cn.bing.com/search', {'q': query + ' site:gov.cn', 'format': 'rss', **zh}, browser),
            ('bing-no-scope', 'https://www.bing.com/search', {'q': query, 'format': 'rss', **zh}, browser),
        ]
        for name, url, params, headers in variants:
            try:
                with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
                    response = client.get(url, params=params)
                links = re.findall(r'<link>([^<]+)</link>', response.text)[1:9]
                hosts = [urlparse(x).hostname for x in links]
                report.append({'query': query, 'variant': name, 'status': response.status_code, 'hosts': hosts,
                               'official': sum(law.official_url(law.upgrade_scheme(x)) for x in links)})
            except Exception as exc:
                report.append({'query': query, 'variant': name, 'error': type(exc).__name__})
    for title in ('反不正当竞争法', '民法典'):
        try:
            with httpx.Client(timeout=15, follow_redirects=True, headers=browser) as client:
                response = client.get('https://flk.npc.gov.cn/api/', params={'type': '', 'searchType': 'title;vague', 'sortTr': 'f_bbrq_s;desc',
                                      'gbrqStart': '', 'gbrqEnd': '', 'sxrqStart': '', 'sxrqEnd': '', 'sort': 'true', 'page': 1, 'size': 5, 'title': title})
            report.append({'query': title, 'variant': 'flk-npc-api', 'status': response.status_code,
                           'content_type': response.headers.get('content-type'), 'head': response.text[:600]})
        except Exception as exc:
            report.append({'query': title, 'variant': 'flk-npc-api', 'error': type(exc).__name__})
    return report


def fetch_variants() -> list[dict]:
    """How official statute pages answer the production client, one hop at a time. Diagnostic only."""
    import httpx
    browser = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
    pages = ['https://www.npc.gov.cn/npc/c2/c30834/202108/t20210820_313088.html',
             'http://www.npc.gov.cn/npc/c2/c30834/202108/t20210820_313088.html',
             'https://www.npc.gov.cn/c2/c30834/202108/t20210823_313123.html',
             'https://www.court.gov.cn/zixun/xiangqing/233181.html']
    report = []
    for url in pages:
        for agent in ('production', 'browser'):
            row = {'url': url, 'agent': agent}
            try:
                with law._client() as client:
                    if agent == 'browser':
                        client.headers['User-Agent'] = browser
                    response = client.get(url)
                row.update(status=response.status_code, location=response.headers.get('location'),
                           content_type=response.headers.get('content-type'), bytes=len(response.content),
                           text_chars=len(law.html_text(response.text)) if 'html' in response.headers.get('content-type', '') else None)
                trace = {}
                try:
                    with law._client() as client:
                        if agent == 'browser':
                            client.headers['User-Agent'] = browser
                        body = law.html_text(law._read(client, 'GET', law.upgrade_scheme(url), official=True, trace=trace))
                    row['read'] = f'ok {len(body)} chars'
                except Exception as exc:  # diagnostic only
                    row['read'] = law.failure_reason(exc, trace)
            except Exception as exc:  # diagnostic only
                row['error'] = f'{type(exc).__name__}: {exc}'[:200]
            report.append(row)
    return report


summary = {'provider': law.provider_status(), 'queries': []}
for query, keywords in QUERIES:
    result = law.retrieve_law(query, keywords)
    summary['queries'].append({
        'query': query, 'status': result['status'], 'discovery_status': result.get('discovery_status'),
        'candidates': candidates(query), 'warnings': result['warnings'], 'rejected': result.get('rejected'),
        'sources': [{k: s.get(k) for k in ('url', 'title', 'source_kind', 'discovery')} | {'excerpt_chars': len(s['text'])}
                    for s in result['sources']]})
summary['search_variants'] = search_variants()
summary['fetch_variants'] = fetch_variants()
Path('legal-retrieval-probe.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
print(json.dumps(summary, ensure_ascii=False, indent=2))
found = sum(bool(q['sources']) for q in summary['queries'])
print(f'official sources obtained for {found}/{len(QUERIES)} queries')
if not found:
    print('::warning::Live external search did not produce a readable official source. Legal findings stay model-cited; configure an approved search provider and retry.')

# Release-time operators may explicitly require sources. CI remains an honest
# network diagnostic rather than declaring substantive legal correctness.
if '--require-source' in sys.argv and not found:
    raise SystemExit(1)
