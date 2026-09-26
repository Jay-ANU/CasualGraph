"""Public-query live retrieval diagnostic; never uses a contract or model credential.

Runs the kind of generic queries the research planner writes, and logs for each one what
the search provider returned, which candidates passed the official-source checks and
what was fetched. Success here shows a page was obtained, not that the law applies.
"""
import json
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


summary = {'provider': law.provider_status(), 'queries': []}
for query, keywords in QUERIES:
    result = law.retrieve_law(query, keywords)
    summary['queries'].append({
        'query': query, 'status': result['status'], 'discovery_status': result.get('discovery_status'),
        'candidates': candidates(query), 'warnings': result['warnings'],
        'sources': [{k: s.get(k) for k in ('url', 'title', 'source_kind', 'discovery')} | {'excerpt_chars': len(s['text'])}
                    for s in result['sources']]})
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
