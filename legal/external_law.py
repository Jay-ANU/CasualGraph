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


def _read(client: httpx.Client, method: str, url: str, *, official: bool = False, **kwargs) -> str:
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


def excerpt(text: str, keywords: list[str], limit: int = 16000) -> str:
    """Keep entire numbered provisions where possible; excerpts are never a full-law claim."""
    chunks = re.split(r'(?=第[一二三四五六七八九十百千万零〇两\d]+条(?:\s|　|[：:]))', text)
    ranked = sorted(enumerate(chunks), key=lambda x: sum(x[1].count(k) for k in keywords), reverse=True)
    chosen, size = [], 0
    for index, chunk in ranked:
        if any(k in chunk for k in keywords) and len(chunk) <= limit - size:
            chosen.append((index, chunk))
            size += len(chunk)
    return '\n[…]\n'.join(c for _, c in sorted(chosen)) if chosen else text[:limit]


def provider_status() -> dict:
    provider = os.getenv('LEGAL_SEARCH_PROVIDER', 'auto').lower()
    if provider == 'auto':
        provider = 'tavily' if os.getenv('TAVILY_API_KEY') else 'bing_rss'
    return {'provider': provider, 'configured': provider == 'bing_rss' or (provider == 'tavily' and bool(os.getenv('TAVILY_API_KEY'))),
            'mode': 'external_only', 'live_verified': False,
            'notice': '公开网页检索不是完整法规库；原文、版本及适用性仍需复核。检索失败不会视为无风险。'}


def retrieve_law(query: str, keywords: list[str], *, client: httpx.Client | None = None) -> dict:
    """Queries must come from the server's public rule catalogue, not contract contents."""
    status = provider_status()
    own = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(12, connect=5), follow_redirects=False,
                                   headers={'User-Agent': 'CausalGraph-Legal/1.0 (+legal-evidence-retrieval)'})
    sources, warnings, candidates = [], [], []
    try:
        if not status['configured']:
            return {'sources': [], 'status': 'unavailable', 'warnings': ['检索服务未配置。'], **status}
        if status['provider'] == 'tavily':
            import json
            raw = _read(client, 'POST', 'https://api.tavily.com/search', headers={'Authorization': 'Bearer ' + os.environ['TAVILY_API_KEY']}, json={
                'query': query,
                'search_depth': 'basic', 'max_results': 5, 'include_answer': False,
                'include_domains': sorted(OFFICIAL_HOSTS)})
            candidates = [(x.get('url', ''), x.get('title', '')) for x in json.loads(raw).get('results', [])]
        else:
            raw = _read(client, 'GET', 'https://www.bing.com/search', params={'q': query + ' site:gov.cn', 'format': 'rss'})
            # Reject entity declarations rather than allowing XML expansion from the network.
            if '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():
                raise LawRetrievalError('invalid_search_response')
            tree = ElementTree.fromstring(raw)
            candidates = [(x.findtext('link', ''), x.findtext('title', '')) for x in tree.findall('.//item')]
        seen = set()
        for url, title in candidates[:8]:
            if not official_url(url) or url in seen:
                continue
            seen.add(url)
            try:
                body = html_text(_read(client, 'GET', url, official=True))
                if len(body) < 100:
                    continue
                quote = excerpt(body, keywords)
                if not any(k in quote for k in keywords):
                    continue
                sources.append({'id': 'law_' + hashlib.sha256((url + '\n' + quote).encode()).hexdigest()[:16],
                                'title': title[:300], 'url': url, 'text': quote,
                                'retrieved_at': datetime.now(timezone.utc).isoformat(),
                                'content_hash': hashlib.sha256(body.encode()).hexdigest(),
                                'source_status': 'official_page_fetched', 'version_status': 'needs_verification',
                                'is_excerpt': True, 'query': query})
            except (httpx.HTTPError, OSError, ValueError, LawRetrievalError):
                warnings.append('有候选来源无法读取或未通过来源检查。')
            if len(sources) >= 2:
                break
        return {**status, 'sources': sources, 'status': 'retrieved' if sources else 'no_verified_source', 'warnings': warnings}
    except (httpx.HTTPError, OSError, ValueError, ElementTree.ParseError, LawRetrievalError):
        return {**status, 'sources': [], 'status': 'unavailable', 'warnings': ['外部检索失败；本轮不能据此排除法律风险。']}
    finally:
        if own:
            client.close()
