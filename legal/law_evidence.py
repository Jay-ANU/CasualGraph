"""Source-type screening is a heuristic, not certification of legal authority."""
from __future__ import annotations
from datetime import date
from html import unescape
import re

ARTICLE_START = re.compile(r'(?m)^[ \t\u3000]*第[一二三四五六七八九十百千万零〇两\d]+条(?:之[一二三四五六七八九十\d]+)?(?=\s|[【〖：:])')
NON_AUTHORITIES = frozenset({'draft', 'commentary', 'case_material'})


def screen_page(raw: str, body: str, display_title: str) -> dict:
    # Search result titles are display hints, never evidence of document type.
    headings = re.findall(r'<h[12]\b[^>]*>(.*?)</h[12]>', raw, re.I | re.S)
    meta = re.search(r'<meta\s+[^>]*name=[\"\']ArticleTitle[\"\'][^>]*content=[\"\']([^\"\']+)', raw, re.I)
    title_tag = re.search(r'<title\b[^>]*>(.*?)</title>', raw, re.I | re.S)
    title = (meta.group(1) if meta else next((h for h in headings if len(re.sub('<[^>]*>', '', h).strip()) >= 6), '')
             or (title_tag.group(1) if title_tag else ''))
    title = re.sub(r'\s+', ' ', unescape(re.sub('<[^>]*>', '', title))).strip()[:300]
    signals = title or body[:800]
    if re.search('征求意见|草案|征求意见稿', signals):
        kind = 'draft'
    elif re.search('解读|答记者问|图解|新闻发布会|起草说明', signals):
        kind = 'commentary'
    elif re.search('典型案例|指导案例|裁判案例|案例分析', signals):
        kind = 'case_material'
    elif len(ARTICLE_START.findall(body)) >= 2 and re.search('法|典|条例|规定|办法|解释', signals):
        kind = 'normative_candidate'
    else:
        kind = 'unknown'
    dates = []
    # Retain literal date evidence; do NOT choose one as the effective version.
    for m in re.finditer(r'(?:自|于)(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日[^。；\n]{0,12}施行', body):
        try:
            value = date(*map(int, m.group(1, 2, 3))).isoformat()
        except ValueError:
            continue
        item = {'date': value, 'quote': m.group(), 'meaning': 'effective_date_candidate'}
        if item not in dates:
            dates.append(item)
    return {'title': title or display_title[:300] or '官方页面（标题待核验）',
            'source_kind': kind, 'source_kind_status': 'heuristic_not_certified',
            'effective_date_candidates': dates[:8], 'version_status': 'needs_verification'}


def evidence_health(searches: dict, sources: list[dict]) -> dict:
    states = [s.get('status') for s in searches.values()]
    return {'queried_topics': len(states), 'topics_with_sources': states.count('retrieved'),
            'failed_or_empty_topics': sum(s != 'retrieved' for s in states),
            'source_count': len(sources),
            'non_authoritative_sources': sum(s.get('source_kind') in NON_AUTHORITIES for s in sources),
            'version_pending': sum(s.get('version_status') != 'verified' for s in sources),
            'status': 'not_started' if not states else ('gaps' if any(s != 'retrieved' for s in states) else 'sources_obtained'),
            'notice': '取回官方网页只说明有来源；法规版本、效力、适用条件及例外仍需核验。'}
