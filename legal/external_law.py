"""External-only legal evidence retrieval. No model-memory or bundled-law fallback."""
from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import socket
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse
from xml.etree import ElementTree
from legal.law_evidence import ARTICLE_START, screen_page

import httpx

# Explicit source origins, never a substring match against an arbitrary URL.
OFFICIAL_HOSTS = frozenset({'www.gov.cn', 'www.npc.gov.cn', 'flk.npc.gov.cn', 'www.court.gov.cn',
                          'www.spp.gov.cn', 'www.moj.gov.cn', 'www.samr.gov.cn', 'www.cac.gov.cn',
                          'www.mofcom.gov.cn', 'www.pbc.gov.cn', 'www.chinatax.gov.cn'})
MAX_RESPONSE = 2 * 1024 * 1024


class LawRetrievalError(RuntimeError):
    pass


def official_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme == 'https' and p.hostname in OFFICIAL_HOSTS and p.port in (None, 443) and not p.username and not p.password
    except ValueError:
        return False


def _public_host(host: str) -> None:
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise LawRetrievalError('blocked_network_target')


def _read(client: httpx.Client, method: str, url: str, *, official: bool = False, trace: dict | None = None, **kwargs) -> str:
    # Redirects are checked before following; original contracts are never sent here.
    for _ in range(4):
        if not official:
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.hostname not in {'www.bing.com', 'cn.bing.com', 'api.tavily.com'} or parsed.port not in (None, 443) or parsed.username or parsed.password:
                raise LawRetrievalError('blocked_search_redirect')
        if official:
            if not official_url(url):
                raise LawRetrievalError('non_official_source')
            _public_host(urlparse(url).hostname or '')
        with client.stream(method, url, **kwargs) as response:
            if response.is_redirect:
                url = str(response.url.join(response.headers.get('location', '')))
                kwargs = {}
                method = 'GET'
                continue
            response.raise_for_status()
            if trace is not None:
                trace['url'] = str(response.url)
            if official and 'text/html' not in response.headers.get('content-type', '') and 'text/plain' not in response.headers.get('content-type', ''):
                raise LawRetrievalError('unsupported_source_format')
            raw = bytearray()
            for part in response.iter_bytes():
                raw.extend(part)
                if len(raw) > MAX_RESPONSE:
                    raise LawRetrievalError('source_too_large')
            encoding = response.encoding or 'utf-8'
            if b'charset=gb' in bytes(raw[:3000]).lower() or b'charset="gb' in bytes(raw[:3000]).lower():
                encoding = 'gb18030'
            return bytes(raw).decode(encoding, errors='replace')
    raise LawRetrievalError('too_many_redirects')


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self.hidden += 1
        if tag in ('p', 'br', 'div', 'h1', 'h2', 'li'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript'):
            self.hidden = max(0, self.hidden - 1)
        if tag in ('p', 'div', 'li'):
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def html_text(raw: str) -> str:
    parser = _Text()
    parser.feed(raw)
    return re.sub(r'[ \t]+', ' ', re.sub(r'\n\s*\n', '\n', ''.join(parser.parts))).strip()


def article_units(text: str) -> list[str]:
    """Split only at provision headings, never an in-sentence cross-reference."""
    starts = sorted({0, *(m.start() for m in ARTICLE_START.finditer(text))})
    return [text[a:b] for a, b in zip(starts, starts[1:] + [len(text)])]


def excerpt(text: str, keywords: list[str], limit: int = 16000) -> str:
    """Keep complete provisions. An oversized sole provision is not evidence."""
    chunks = article_units(text)
    ranked = sorted(enumerate(chunks), key=lambda x: sum(x[1].count(k) for k in keywords), reverse=True)
    chosen, size = [], 0
    for index, chunk in ranked:
        cost = len(chunk) + (len('\n[…]\n') if chosen else 0)
        if any(k in chunk for k in keywords) and cost <= limit - size:
            chosen.append((index, chunk))
            size += cost
    return '\n[…]\n'.join(c for _, c in sorted(chosen))


# Addresses only, not cached statutes or a claim that these are the latest law.
# They are refetched through the same allowlist/content limits as discovered URLs.
DIRECT_ORIGINS = (
    (('民法典',), 'https://www.court.gov.cn/zixun/xiangqing/233181.html', '中华人民共和国民法典'),
    (('合同编通则', '违约金', '合同'), 'https://www.court.gov.cn/fabu/xiangqing/419382.html', '合同编通则司法解释'),
    (('个人信息',), 'https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm', '中华人民共和国个人信息保护法'),
)


def public_search_query(query: str) -> str:
    # Use the exact same domain scope for discovery and source admission.
    scope = ' OR '.join('site:' + host for host in sorted(OFFICIAL_HOSTS))
    return query + ' (' + scope + ')'


def provider_status() -> dict:
    provider = os.getenv('LEGAL_SEARCH_PROVIDER', 'auto').lower()
    if provider == 'auto':
        provider = 'tavily' if os.getenv('TAVILY_API_KEY') else 'bing_rss'
    return {'provider': provider, 'configured': provider == 'bing_rss' or (provider == 'tavily' and bool(os.getenv('TAVILY_API_KEY'))),
            'mode': 'external_only', 'live_verified': False,
            'direct_official_fallback': os.getenv('LEGAL_DIRECT_OFFICIAL_FALLBACK', 'true').lower() == 'true',
            'notice': '公开网页检索不是完整法规库；原文、版本及适用性仍需复核。检索失败不会视为无风险。'}


def retrieve_law(query: str, keywords: list[str], *, client: httpx.Client | None = None) -> dict:
    """Use only server-defined public topics. Never send contract contents here."""
    status = provider_status()
    if not status['configured']:
        return {**status, 'sources': [], 'status': 'unavailable', 'warnings': ['检索服务未配置。']}
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(12, connect=5), follow_redirects=False, trust_env=False,
                                   headers={'User-Agent': 'CausalGraph-Legal/1.1 (+legal-evidence-retrieval)'})
    sources, warnings, candidates, seen = [], [], [], set()
    discovery_failed = False
    failures = (httpx.HTTPError, OSError, ValueError, ElementTree.ParseError, LawRetrievalError)

    def fetch_candidates(rows: list, method: str) -> None:
        for url, title in rows[:8]:
            if not isinstance(url, str) or not official_url(url) or url in seen:
                continue
            seen.add(url)
            trace = {}
            try:
                raw = _read(client, 'GET', url, official=True, trace=trace)
                body = html_text(raw)
                if len(body) < 100:
                    continue
                quote = excerpt(body, keywords)
                if not quote:
                    warnings.append('有来源没有预算内完整的相关条文，未截断条文作为依据。')
                    continue
                resolved = trace.get('url', url)
                metadata = screen_page(raw, body, title if isinstance(title, str) else '')
                sources.append({'id': 'law_' + hashlib.sha256((resolved + '\n' + quote).encode()).hexdigest()[:16],
                                **metadata, 'url': resolved, 'requested_url': url, 'text': quote,
                                'retrieved_at': datetime.now(timezone.utc).isoformat(),
                                'content_hash': hashlib.sha256(body.encode()).hexdigest(),
                                'source_status': 'official_page_fetched', 'is_excerpt': quote != body,
                                'discovery': method, 'query': query})
            except failures:
                warnings.append('有候选来源无法读取或未通过来源检查。')
            if len(sources) >= 2:
                break
    try:
        try:
            if status['provider'] == 'tavily':
                import json
                raw = _read(client, 'POST', 'https://api.tavily.com/search', headers={'Authorization': 'Bearer ' + os.environ['TAVILY_API_KEY']}, json={
                    'query': query, 'search_depth': 'basic', 'max_results': 5, 'include_answer': False,
                    'include_domains': sorted(OFFICIAL_HOSTS)})
                value = json.loads(raw)
                if not isinstance(value, dict) or not isinstance(value.get('results'), list):
                    raise ValueError('invalid_search_response')
                candidates = [(x.get('url', ''), x.get('title', '')) for x in value['results'] if isinstance(x, dict)]
            else:
                raw = _read(client, 'GET', 'https://www.bing.com/search', params={'q': public_search_query(query), 'format': 'rss'})
                if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():
                    raise LawRetrievalError('invalid_search_response')
                tree = ElementTree.fromstring(raw)
                candidates = [(x.findtext('link', ''), x.findtext('title', '')) for x in tree.findall('.//item')]
        except failures:
            discovery_failed = True
            warnings.append('公开搜索未完成，不能将搜索失败解释为没有法律风险。')
        fetch_candidates(candidates, 'search')
        if not sources and status['direct_official_fallback']:
            direct = [(url, title) for terms, url, title in DIRECT_ORIGINS if any(t in query for t in terms)][:2]
            fetch_candidates(direct, 'direct_official')
            if sources:
                warnings.append('搜索未取得可用来源，已实时读取有限的官方原文地址；仍须核对最新版本与适用性。')
        return {**status, 'sources': sources,
                'status': 'retrieved' if sources else ('unavailable' if discovery_failed else 'no_verified_source'),
                'warnings': list(dict.fromkeys(warnings)),
                'discovery_status': 'unavailable' if discovery_failed else 'completed'}
    finally:
        if own:
            client.close()
