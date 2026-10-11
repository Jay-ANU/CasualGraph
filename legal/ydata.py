"""Compatible legal model gateway: Claude uses Anthropic; four families use YData."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

BASE_URL = 'https://www.ydata.space/v1'
FAMILIES = ('GPT', 'Claude', 'DeepSeek', 'Kimi', 'GLM')
YDATA_FAMILIES = ('GPT', 'DeepSeek', 'Kimi', 'GLM')
FAMILY_KEY_ENVS = {
    'GPT': 'YDATA_GPT_API_KEY',
    'DeepSeek': 'YDATA_DEEPSEEK_API_KEY',
    'Kimi': 'YDATA_KIMI_API_KEY',
    'GLM': 'YDATA_GLM_API_KEY',
}
TTL_SECONDS = 120
_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {}
_PROVIDER_CACHE: dict[str, dict[str, Any]] = {}
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/-]{0,159}$')
_PLACEHOLDER_KEYS = {'...', 'your-api-key', 'replace-me', 'bearer ...'}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
# A streamed reply carries every token in its own event, many times the size of the text itself.
MAX_STREAM_BYTES = 48 * 1024 * 1024
MAX_REPLY_CHARACTERS = 1024 * 1024
STREAM_SECONDS = 900
# A chat turn may write a whole review: allow it longer, and keep what was written when time runs out.
CHAT_STREAM_SECONDS = 1800
CHAT_IDLE_SECONDS = 600
UNAVAILABLE = 'YData 连接超时或响应无效；没有自动切换其他模型。'
INCOMPLETE = '模型未返回完整的结构化审查结果；任务已保留，可重试，不会发布截断结论。'
log = logging.getLogger(__name__)


class GatewayError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 503, retry_after: float | None = None,
                 upstream_status: int | None = None):
        super().__init__(message)
        self.code, self.message, self.status_code, self.retry_after = code, message, status_code, retry_after
        # The gateway's own HTTP status: for logs, and to tell a refused stream from a failed call.
        self.upstream_status = upstream_status


class StreamDeadline(GatewayError):
    """A streamed reply still running when its time was up."""

    def __init__(self):
        super().__init__('ydata_unavailable', UNAVAILABLE, 502)


def _retry_after(value: str | None) -> float | None:
    """Seconds from a Retry-After header (delay form only), capped at one minute."""
    try:
        seconds = float(value or '')
    except ValueError:
        return None
    return min(60.0, seconds) if seconds >= 0 else None


def _read_key(env_name: str) -> str | None:
    value = os.getenv(env_name, '').strip()
    if not value or value.lower() in _PLACEHOLDER_KEYS:
        return None
    return value


def _legacy_key() -> str | None:
    return _read_key('YDATA_API_KEY')


def _dedicated_keys() -> dict[str, str]:
    result: dict[str, str] = {}
    seen: dict[str, str] = {}
    for family, env_name in FAMILY_KEY_ENVS.items():
        key = _read_key(env_name)
        if not key:
            continue
        previous = seen.get(key)
        if previous and previous != family:
            raise GatewayError(
                'ydata_key_conflict',
                f'{FAMILY_KEY_ENVS[previous]} 与 {env_name} 不能配置为同一 YData Key；一个 Key 只能绑定一个模型厂商。',
            )
        seen[key] = family
        result[family] = key
    return result


def _bindings() -> list[tuple[str | None, str]]:
    dedicated = _dedicated_keys()
    bindings = [(family, key) for family, key in dedicated.items()]
    legacy = _legacy_key()
    if legacy and legacy not in dedicated.values():
        bindings.append((None, legacy))
    if not bindings:
        raise GatewayError(
            'ydata_not_configured',
            'YData 密钥未配置。请至少配置 YDATA_API_KEY，或为模型厂商配置对应的 YDATA_*_API_KEY。',
        )
    return bindings


def _key_for_family(family: str) -> str:
    env_name = FAMILY_KEY_ENVS.get(family)
    if not env_name:
        raise GatewayError('legal_model_not_allowed', '所选模型系列不受支持。', 422)
    dedicated = _read_key(env_name)
    if dedicated:
        return dedicated
    legacy = _legacy_key()
    if legacy:
        return legacy
    raise GatewayError(
        'ydata_family_not_configured',
        f'{family} 模型尚未配置 YData Key，请管理员配置 {env_name}。',
    )


def configured() -> bool:
    from legal import anthropic_gateway
    try:
        _bindings()
        return True
    except GatewayError:
        return anthropic_gateway.configured()


def family_of(model: str) -> str | None:
    if not isinstance(model, str) or not _ID.fullmatch(model):
        return None
    name = model.rsplit('/', 1)[-1].lower()
    # This feature accepts text chat models, not the gateway's image/audio/embedding catalog.
    if any(word in name for word in ('embedding', 'rerank', 'moderation', 'realtime', 'audio', 'tts', 'transcrib', 'whisper', 'image', 'video')):
        return None
    if name.startswith(('gpt-', 'chatgpt-')) or re.match(r'^o\d+(?:-|$)', name):
        return 'GPT'
    for prefixes, family in ((('claude-',), 'Claude'), (('deepseek',), 'DeepSeek'),
                             (('kimi', 'moonshot'), 'Kimi'), (('glm-', 'chatglm'), 'GLM')):
        if name.startswith(prefixes):
            return family
    return None


def provider_for_model(model_id: str) -> str | None:
    family = family_of(model_id)
    return 'anthropic' if family == 'Claude' else 'ydata' if family in YDATA_FAMILIES else None


def _client(idle: float = 300) -> httpx.Client:
    # The read timeout is the longest silence allowed: between two chunks of a streamed reply, or
    # for the whole answer when a gateway does not stream.
    return httpx.Client(timeout=httpx.Timeout(idle, connect=10, pool=10, write=30),
                        follow_redirects=False, trust_env=False)


def _headers(key: str, accept: str) -> dict:
    return {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'Accept': accept}


def _status_error(response: httpx.Response) -> GatewayError:
    status = response.status_code
    if status in (401, 403):
        return GatewayError('ydata_unauthorized', 'YData 拒绝访问，请管理员检查密钥及模型授权。', upstream_status=status)
    if status == 429:
        return GatewayError('ydata_rate_limited', 'YData 请求限额已达到，请稍后重试。', 429,
                            retry_after=_retry_after(response.headers.get('retry-after')), upstream_status=status)
    return GatewayError('ydata_request_failed', f'YData 请求失败（HTTP {status}），请检查网关及所选模型的聊天接口支持。', 502,
                        upstream_status=status)


def _read_json(response: httpx.Response) -> dict:
    parts, size = [], 0
    for part in response.iter_bytes():
        size += len(part)
        if size > MAX_RESPONSE_BYTES:
            raise GatewayError('ydata_response_too_large', 'YData 响应超出限制。', 502)
        parts.append(part)
    data = json.loads(b''.join(parts))
    if not isinstance(data, dict):
        raise ValueError('not an object')
    return data


def _request(client: httpx.Client, method: str, path: str, key: str, **kwargs) -> dict:
    try:
        with client.stream(method, BASE_URL + path, headers=_headers(key, 'application/json'), **kwargs) as response:
            if not response.is_success:
                raise _status_error(response)
            return _read_json(response)
    except GatewayError:
        raise
    except (httpx.HTTPError, ValueError, UnicodeError):
        # Never expose upstream response bodies, authorization headers or contract prompts.
        raise GatewayError('ydata_unavailable', UNAVAILABLE, 502) from None


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        _PROVIDER_CACHE.clear()


def _cache_fingerprint(manual: str) -> str:
    values = {
        'legacy': _legacy_key() or '',
        'manual': manual,
        'default': os.getenv('LEGAL_YDATA_DEFAULT_MODEL', ''),
        'anthropic_key': _read_key('ANTHROPIC_API_KEY') or '',
        'anthropic_manual': os.getenv('LEGAL_ANTHROPIC_MODELS', ''),
        'retired_claude_key_present': bool(_read_key('YDATA_CLAUDE_API_KEY')),
        **{family: _read_key(env_name) or '' for family, env_name in FAMILY_KEY_ENVS.items()},
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _ydata_catalog(*, client: httpx.Client | None = None) -> dict:
    bindings = _bindings()
    manual = os.getenv('LEGAL_YDATA_MODELS', '').strip()

    models: dict[str, dict[str, str]] = {}
    unavailable: set[str] = set()
    source = 'configured' if manual else 'gateway'
    if manual:
        try:
            ids = json.loads(manual)
            if not isinstance(ids, list) or not ids or not all(isinstance(x, str) and family_of(x) for x in ids):
                raise ValueError('invalid model inventory')
            for mid in ids:
                family = family_of(mid)
                assert family is not None
                if family == 'Claude':
                    continue  # Legacy inventory cannot route Claude back through YData.
                _key_for_family(family)
                models[mid] = {'id': mid, 'family': family, 'provider': 'ydata'}
        except GatewayError:
            raise
        except (ValueError, TypeError):
            raise GatewayError('ydata_catalog_invalid', 'LEGAL_YDATA_MODELS 必须是 GPT、DeepSeek、Kimi、GLM 确切模型 ID 的 JSON 数组；Claude 请配置官方库存。') from None
    else:
        dedicated = _dedicated_keys()
        errors: list[GatewayError] = []
        owned = None
        active_client = client
        if active_client is None:
            owned = _client()
            active_client = owned
        try:
            for family_hint, key in bindings:
                try:
                    data = _request(active_client, 'GET', '/models', key, timeout=15)
                    rows = data.get('data')
                    if not isinstance(rows, list):
                        raise GatewayError('ydata_catalog_invalid', 'YData 模型列表格式无效。', 502)
                    matched = 0
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        mid = row.get('id')
                        family = family_of(mid)
                        if family not in YDATA_FAMILIES:
                            continue
                        if family_hint is not None and family != family_hint:
                            continue
                        # A dedicated family credential is authoritative for that family. Do not
                        # silently source the same family from the legacy credential.
                        if family_hint is None and family in dedicated:
                            continue
                        models[mid] = {'id': mid, 'family': family, 'provider': 'ydata'}
                        matched += 1
                    if family_hint is not None and matched == 0:
                        unavailable.add(family_hint)
                except GatewayError as exc:
                    errors.append(exc)
                    if family_hint is not None:
                        unavailable.add(family_hint)
        finally:
            if owned is not None:
                owned.close()

        if not models and errors:
            if len(bindings) == 1:
                raise errors[0]
            raise GatewayError(
                'ydata_no_chat_models',
                '已配置的 YData Key 均未返回可用聊天模型，请检查各模型厂商 Key 与授权。',
            )

    if not models:
        raise GatewayError('ydata_no_chat_models', '当前 YData 凭据未列出支持的 GPT、DeepSeek、Kimi 或 GLM 聊天型号；Claude 仅使用 Anthropic 官方 API。')

    ordered = sorted(models.values(), key=lambda m: (FAMILIES.index(m['family']), m['id']))
    preferred = os.getenv('LEGAL_YDATA_DEFAULT_MODEL', 'glm-5.2').strip()
    available_families = [family for family in FAMILIES if any(m['family'] == family for m in ordered)]
    result = {
        'provider': 'ydata',
        'models': ordered,
        'families': list(FAMILIES),
        'available_families': available_families,
        'unavailable_families': [family for family in FAMILIES if family in unavailable and family not in available_families],
        'catalog_source': source,
        'default_model': preferred if preferred in models else ordered[0]['id'],
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'notice': '后端按模型系列选择对应 YData Key；仅显示可由当前凭据发现或管理员配置的文本型号。不可用时明确报错，不会跨厂商换 Key 或自动换模型。',
    }
    return result


def _provider_catalog(provider: str, *, client: httpx.Client | None = None) -> dict:
    """A selection must never wait for another processing provider's discovery."""
    from legal import anthropic_gateway
    if provider == 'anthropic':
        values = {'key': _read_key('ANTHROPIC_API_KEY') or '', 'manual': os.getenv('LEGAL_ANTHROPIC_MODELS', '')}
        fetch = anthropic_gateway.model_catalog
    else:
        values = {'legacy': _legacy_key() or '', 'manual': os.getenv('LEGAL_YDATA_MODELS', ''),
                  **{family: _read_key(env_name) or '' for family, env_name in FAMILY_KEY_ENVS.items()}}
        fetch = _ydata_catalog
    fingerprint = hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    with _LOCK:
        cached = _PROVIDER_CACHE.get(provider, {})
        if client is None and cached.get('key') == fingerprint and cached.get('until', 0) > time.monotonic():
            return json.loads(json.dumps(cached['catalog']))
    catalog = fetch(client=client)
    if client is None:
        with _LOCK:
            _PROVIDER_CACHE[provider] = {'key': fingerprint, 'until': time.monotonic() + TTL_SECONDS, 'catalog': catalog}
    return json.loads(json.dumps(catalog))


def model_catalog(*, client: httpx.Client | None = None) -> dict:
    from legal import anthropic_gateway
    cache_key = _cache_fingerprint(os.getenv('LEGAL_YDATA_MODELS', '').strip())
    with _LOCK:
        if client is None and _CACHE.get('key') == cache_key and _CACHE.get('until', 0) > time.monotonic():
            return json.loads(json.dumps(_CACHE['catalog']))
    catalogs, errors = [], []
    ydata_declared = bool(_legacy_key() or any(_read_key(env_name) for env_name in FAMILY_KEY_ENVS.values()))
    anthropic_declared = bool(anthropic_gateway.configured() or os.getenv('LEGAL_ANTHROPIC_MODELS', '').strip()
                              or _read_key('YDATA_CLAUDE_API_KEY'))
    for provider, declared in (('ydata', ydata_declared), ('anthropic', anthropic_declared)):
        if not declared:
            continue
        try:
            catalogs.append(_provider_catalog(provider, client=client))
        except GatewayError as exc:
            errors.append((provider, exc))
    if not catalogs:
        if errors:
            raise errors[0][1]
        raise GatewayError('ydata_not_configured', '模型密钥未配置。Claude 请设置 ANTHROPIC_API_KEY，其他系列请配置 YDATA_API_KEY 或对应 YDATA_*_API_KEY。')
    models = [model for catalog in catalogs for model in catalog['models']]
    models.sort(key=lambda model: (FAMILIES.index(model['family']), model['id']))
    available = [family for family in FAMILIES if any(model['family'] == family for model in models)]
    providers = list(dict.fromkeys(model['provider'] for model in models))
    sources = {catalog['provider']: catalog['catalog_source'] for catalog in catalogs}
    unavailable = {family for catalog in catalogs for family in catalog.get('unavailable_families', [])}
    for provider, _ in errors:
        unavailable.update(('Claude',) if provider == 'anthropic' else YDATA_FAMILIES)
    preferred = os.getenv('LEGAL_YDATA_DEFAULT_MODEL', 'glm-5.2').strip()
    result = {
        'provider': providers[0] if len(providers) == 1 else 'mixed',
        'models': models, 'families': list(FAMILIES), 'available_families': available,
        'unavailable_families': [family for family in FAMILIES if family in unavailable and family not in available],
        'catalog_source': next(iter(sources.values())) if len(set(sources.values())) == 1 else 'mixed',
        'catalog_sources': sources,
        'default_model': preferred if any(model['id'] == preferred for model in models) else models[0]['id'],
        'provider_errors': [{'provider': provider, 'code': exc.code, 'message': exc.message,
                             'status_code': exc.status_code, 'retry_after': exc.retry_after, 'upstream_status': exc.upstream_status}
                            for provider, exc in errors],
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'notice': 'Claude 直接使用 Anthropic 官方 API；GPT、DeepSeek、Kimi、GLM 使用各自的 YData 凭据。仅列出接口发现或管理员明确配置的型号；不会自动切换提供方或模型。',
    }
    if client is None:
        with _LOCK:
            _CACHE.update(key=cache_key, until=time.monotonic() + TTL_SECONDS, catalog=result)
    return json.loads(json.dumps(result))


def select_model(model_id: str, *, client: httpx.Client | None = None) -> dict:
    provider = provider_for_model(model_id)
    if provider is None:
        raise GatewayError('legal_model_not_allowed', '所选模型不受支持，请刷新并重新选择。', 422)
    if provider == 'anthropic':
        from legal import anthropic_gateway
        anthropic_gateway.key()
    catalog = _provider_catalog(provider, client=client)
    match = next((m for m in catalog['models'] if m['id'] == model_id), None)
    if match is None:
        raise GatewayError('legal_model_not_allowed', '所选模型不在当前可用列表，请刷新并重新选择。', 422)
    if match['provider'] == 'anthropic':
        from legal import anthropic_gateway
        anthropic_gateway.key()
    else:
        _key_for_family(match['family'])
    return {**match, 'catalog_source': catalog.get('catalog_sources', {}).get(match['provider'], catalog['catalog_source'])}


def _output_tokens() -> int:
    """8192 by default; operators may raise it for model families that support longer answers."""
    try:
        return max(1024, min(65536, int(os.getenv('LEGAL_YDATA_MAX_TOKENS', '8192'))))
    except ValueError:
        return 8192


def default_output_tokens(selection: dict | None = None) -> int:
    """The output budget a request gets unless a caller asks for more, for the selected model's provider."""
    if isinstance(selection, dict) and selection.get('provider') == 'anthropic':
        from legal import anthropic_gateway
        return anthropic_gateway.default_output_tokens()
    return _output_tokens()


def chat_output_tokens() -> int:
    """Room for a complete written review in one turn (32768 by default); longer answers continue."""
    try:
        return max(1024, min(131072, int(os.getenv('LEGAL_CHAT_MAX_TOKENS', '32768'))))
    except ValueError:
        return 32768


def _token_budget(model: str, tokens: int | None = None) -> dict:
    name = model.rsplit('/', 1)[-1].lower()
    if re.match(r'^(?:gpt-(?:[5-9]|[1-9]\d)|o\d)', name):
        return {'max_completion_tokens': tokens or _output_tokens()}
    return {'max_tokens': tokens or _output_tokens()}


def _json_object(content: str) -> dict:
    """The JSON object in a reply, tolerating a code fence, a <think> block or a short preamble."""
    text = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE).strip()
    fenced = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except ValueError:
        start, end = text.find('{'), text.rfind('}')
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError('not an object')
    return value


def _streaming() -> bool:
    """Chat replies are streamed unless LEGAL_YDATA_STREAM=0, for a gateway that cannot stream."""
    return os.getenv('LEGAL_YDATA_STREAM', '1').strip().lower() not in ('0', 'false', 'no', 'off')


def _events(response: httpx.Response, deadline: float):
    """The data line of each server-sent event; OpenAI-style streams put one JSON chunk on each."""
    buffer, size = b'', 0
    for part in response.iter_bytes():
        size += len(part)
        if size > MAX_STREAM_BYTES:
            raise GatewayError('ydata_response_too_large', 'YData 响应超出限制。', 502)
        if time.monotonic() > deadline:
            raise StreamDeadline()
        *lines, buffer = (buffer + part).split(b'\n')
        for line in lines:
            if line.startswith(b'data:'):
                yield line[5:].strip().decode('utf-8')
    if buffer.startswith(b'data:'):
        yield buffer[5:].strip().decode('utf-8')


class _Calls:
    """Tool calls assembled from a stream, where each call's arguments arrive in pieces."""

    def __init__(self):
        self.slots: dict[int, dict] = {}

    def add(self, pieces) -> int:
        """Add one chunk's tool-call pieces; returns the characters of arguments received."""
        size = 0
        for piece in pieces if isinstance(pieces, list) else []:
            if not isinstance(piece, dict):
                continue
            function = piece.get('function') if isinstance(piece.get('function'), dict) else {}
            ident = piece.get('id') if isinstance(piece.get('id'), str) else ''
            index = piece.get('index')
            if type(index) is not int:
                # Without an index, a piece with a new id or name starts a call; anything else continues the last one.
                index = next((k for k, slot in self.slots.items() if ident and slot['id'] == ident), None)
                if index is None:
                    index = max(self.slots) if self.slots and not ident and not function.get('name') else max(self.slots, default=-1) + 1
            slot = self.slots.setdefault(index, {'id': '', 'name': '', 'arguments': []})
            slot['id'] = ident or slot['id']
            if isinstance(function.get('name'), str) and function['name']:
                slot['name'] = function['name']
            arguments = function.get('arguments')
            if isinstance(arguments, str):
                slot['arguments'].append(arguments)
                size += len(arguments)
            elif isinstance(arguments, dict):
                slot['arguments'] = [json.dumps(arguments, ensure_ascii=False)]
        return size

    def result(self) -> list[dict]:
        return [{'id': slot['id'] or 'call_' + os.urandom(6).hex(), 'name': slot['name'], 'arguments': ''.join(slot['arguments']) or '{}'}
                for _, slot in sorted(self.slots.items()) if slot['name']]


def _turn(content: str = '', finish: str | None = None, thinking: int = 0, reasoning: str = '', calls: list | None = None) -> dict:
    """What one completion returned: text, finish reason, reasoning (its length, and the text) and tool calls."""
    return {'content': content, 'finish': finish, 'thinking': thinking, 'reasoning': reasoning, 'tool_calls': calls or []}


def _reasoning(message: dict) -> str:
    """The model's reasoning text, which some models need back while they are calling tools."""
    for k in ('reasoning_content', 'reasoning'):
        if isinstance(message.get(k), str):
            return message[k]
    return ''


def _reply(data: dict) -> dict:
    """An ordinary (not streamed) completion."""
    try:
        choice = data['choices'][0]
        finish = choice.get('finish_reason')
        message = choice.get('message') or {}
    except (KeyError, IndexError, TypeError, AttributeError):
        raise GatewayError('ydata_invalid_json', INCOMPLETE, 502) from None
    if not isinstance(message, dict):
        return _turn(finish=finish)
    content = message.get('content')
    thinking = sum(len(message[k]) for k in ('reasoning_content', 'reasoning') if isinstance(message.get(k), str))
    calls = _Calls()
    calls.add(message.get('tool_calls'))
    return _turn(content if isinstance(content, str) else '', finish, thinking, _reasoning(message), calls.result())


# Called with each piece of answer text and each length of reasoning as they arrive.
Progress = Callable[[str, int], None]


def _stream_reply(client: httpx.Client, key: str, request: dict, on_delta: Progress | None = None,
                  seconds: float = STREAM_SECONDS, partial: bool = False) -> dict:
    """A completion read while it is written. Bytes keep arriving as the model works, so a long
    structured answer is not cut off by an idle timeout on the way; it is used only once complete.
    on_delta sees the text as it arrives, for progress only. With partial, a reply still running
    when time is up, or cut off by a dropped connection, is returned as far as it got and marked
    like one stopped at the output limit, so the conversation can continue from there; a tool call
    still being written then is dropped."""
    deadline = time.monotonic() + seconds
    text: list[str] = []
    reasoning: list[str] = []
    calls = _Calls()
    thinking = 0
    try:
        with client.stream('POST', BASE_URL + '/chat/completions', headers=_headers(key, 'text/event-stream'),
                            json={**request, 'stream': True}) as response:
            if not response.is_success:
                raise _status_error(response)
            if 'text/event-stream' not in response.headers.get('content-type', '').lower():
                # A gateway that ignores the stream flag answers with an ordinary completion.
                return _reply(_read_json(response))
            length, finish, done = 0, None, False
            for data in _events(response, deadline):
                if data == '[DONE]':
                    done = True
                    break
                if not data:
                    continue
                chunk = json.loads(data)
                if not isinstance(chunk, dict):
                    raise ValueError('not an object')
                if chunk.get('error'):
                    raise GatewayError('ydata_request_failed', 'YData 在模型输出过程中报错；未发布不完整结论，可重试。', 502)
                for choice in chunk.get('choices') or []:
                    if not isinstance(choice, dict) or (choice.get('index') or 0) != 0:
                        continue
                    delta = choice.get('delta') or choice.get('message') or {}
                    if isinstance(delta, dict):
                        piece = delta.get('content')
                        if isinstance(piece, str):
                            text.append(piece)
                            length += len(piece)
                        else:
                            piece = ''
                        # Reasoning is streamed beside the answer by some models; it is never part of it.
                        reasoned = sum(len(delta[k]) for k in ('reasoning_content', 'reasoning') if isinstance(delta.get(k), str))
                        thinking += reasoned
                        if reasoned:
                            reasoning.append(_reasoning(delta))
                        length += calls.add(delta.get('tool_calls'))
                        if on_delta and (piece or reasoned):
                            on_delta(piece, reasoned)
                    finish = choice.get('finish_reason') or finish
                if length > MAX_REPLY_CHARACTERS:
                    raise GatewayError('ydata_response_too_large', 'YData 响应超出限制。', 502)
    except StreamDeadline:
        if partial and ''.join(text).strip():
            return _turn(''.join(text), 'length', thinking)
        raise
    except GatewayError:
        raise
    except (httpx.HTTPError, ValueError, UnicodeError):
        if partial and ''.join(text).strip():
            return _turn(''.join(text), 'length', thinking)
        raise GatewayError('ydata_unavailable', UNAVAILABLE, 502) from None
    if finish is None and not done:
        if partial and ''.join(text).strip():
            return _turn(''.join(text), 'length', thinking)
        raise GatewayError('ydata_unavailable', 'YData 连接在模型输出完成前中断；未发布不完整结论，可重试。', 502)
    return _turn(''.join(text), finish or 'stop', thinking, ''.join(reasoning), calls.result())


def _complete(client: httpx.Client, key: str, request: dict, on_delta: Progress | None = None,
              seconds: float = STREAM_SECONDS, partial: bool = False) -> dict:
    if _streaming():
        try:
            return _stream_reply(client, key, request, on_delta, seconds, partial)
        except GatewayError as exc:
            # A route that refuses a streamed request may still answer an ordinary one.
            if exc.code != 'ydata_request_failed' or not 400 <= (exc.upstream_status or 0) < 500:
                raise
    turn = _reply(_request(client, 'POST', '/chat/completions', key, json={**request, 'stream': False}))
    if on_delta and (turn['content'] or turn['thinking']):
        on_delta(turn['content'], turn['thinking'])
    return turn


def _prepare(selection: dict, client: httpx.Client | None) -> dict:
    """The review's own model, through the recipient the user authorized; never another model or vendor."""
    if (not isinstance(selection, dict) or selection.get('provider') not in ('ydata', 'anthropic')
            or selection.get('provider') != provider_for_model(selection.get('id', ''))):
        raise GatewayError('legacy_review_restart_required', '本轮模型接收方与当前路由不一致，请重新选择模型并授权后新建审查。', 409)
    model = select_model(selection.get('id', ''), client=client)
    if model['provider'] != selection['provider']:
        raise GatewayError('legacy_review_restart_required', '本轮模型接收方已变化，请重新选择模型并授权后新建审查。', 409)
    return model


def _exchange(model: dict, key: str, messages: list[dict], tokens: int | None, on_delta: Progress | None,
              client: httpx.Client | None, chat: bool = False, tools: list[dict] | None = None) -> dict:
    request = {'model': model['id'], 'messages': messages, **_token_budget(model['id'], tokens), **({'tools': tools} if tools else {})}
    seconds = CHAT_STREAM_SECONDS if chat else STREAM_SECONDS
    if client is None:
        with (_client(CHAT_IDLE_SECONDS) if chat else _client()) as owned:
            return _complete(owned, key, request, on_delta, seconds, chat)
    return _complete(client, key, request, on_delta, seconds, chat)


def _failed(model_id: str, exc: GatewayError, started: float) -> None:
    # Codes, sizes and timing only: never the prompt, the reply or a key.
    log.warning('ydata chat failed: model=%s code=%s upstream=%s seconds=%.1f', model_id, exc.code,
                exc.upstream_status, time.monotonic() - started)


def chat(messages: list[dict], selection: dict, *, max_tokens: int | None = None, on_delta: Progress | None = None,
         client: httpx.Client | None = None, tools: list[dict] | None = None) -> dict:
    """One turn of a conversation, returned as the model wrote it.

    Unlike chat_json, an answer stopped at the output limit, or still being written when its time
    is up, is returned with finish="length" so the caller can ask the model to continue, the way a
    chat app does. With tools (OpenAI-style function definitions) the model may instead ask for
    them: finish="tool_calls", with tool_calls [{id, name, arguments}] and, when the model reasons
    aloud, its reasoning, which some models need back in the conversation. Claude goes to
    Anthropic's official API. Messages are sent as given; contract text in them must already be
    redacted.
    """
    model = _prepare(selection, client)
    if model['provider'] == 'anthropic':
        from legal import anthropic_gateway
        return anthropic_gateway.chat(messages, model, max_tokens=max_tokens, on_delta=on_delta, client=client, tools=tools)
    key = _key_for_family(model['family'])
    started = time.monotonic()
    try:
        turn = _exchange(model, key, messages, max_tokens, on_delta, client, chat=True, tools=tools)
        finish, calls = turn['finish'], turn['tool_calls'] if tools else []
        if finish in ('length', 'max_tokens'):
            finish = 'length'
        elif calls and finish in ('tool_calls', 'function_call', 'stop', 'end_turn', None):
            finish = 'tool_calls'
        elif finish in ('stop', 'end_turn', None):
            finish = 'stop'
        else:
            raise GatewayError('ydata_incomplete', '模型没有正常完成回答；未发布不完整结论，可重试或换用其他模型。', 502)
        result = {'content': turn['content'], 'finish': finish, 'reasoning_chars': turn['thinking'], 'model': model['id']}
        if finish == 'tool_calls':
            result['tool_calls'] = calls
        if tools and turn['reasoning']:
            result['reasoning'] = turn['reasoning']
        return result
    except GatewayError as exc:
        _failed(model['id'], exc, started)
        raise


def chat_json(system: str, payload: dict, selection: dict, *, client: httpx.Client | None = None) -> dict:
    model = _prepare(selection, client)
    if model['provider'] == 'anthropic':
        from legal import anthropic_gateway
        return anthropic_gateway.chat_json(system, payload, model, client=client)
    key = _key_for_family(model['family'])
    messages = [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]
    # JSON is required by the prompt and checked locally. Do not impose an unsupported
    # response_format/temperature/thinking option on every gateway model family.
    started = time.monotonic()
    try:
        turn = _exchange(model, key, messages, None, None, client)
        content, finish, thinking = turn['content'], turn['finish'], turn['thinking']
        if finish in ('length', 'max_tokens'):
            if thinking > len(content):
                raise GatewayError('ydata_truncated', '模型推理占用了大部分输出上限，结构化结果被截断；未发布不完整结论，可重试或换用其他模型。', 502)
            raise GatewayError('ydata_truncated', '模型输出超过长度上限被截断；未发布不完整结论，可缩小范围后重试。', 502)
        try:
            if finish not in ('stop', 'end_turn'):
                raise ValueError('incomplete response')
            return _json_object(content.strip())
        except (KeyError, IndexError, TypeError, ValueError):
            raise GatewayError('ydata_invalid_json', INCOMPLETE, 502) from None
    except GatewayError as exc:
        _failed(model['id'], exc, started)
        raise
