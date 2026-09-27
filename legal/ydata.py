"""Server-only YData chat gateway with per-model-family credential routing."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

BASE_URL = 'https://www.ydata.space/v1'
FAMILIES = ('GPT', 'Claude', 'DeepSeek', 'Kimi', 'GLM')
FAMILY_KEY_ENVS = {
    'GPT': 'YDATA_GPT_API_KEY',
    'Claude': 'YDATA_CLAUDE_API_KEY',
    'DeepSeek': 'YDATA_DEEPSEEK_API_KEY',
    'Kimi': 'YDATA_KIMI_API_KEY',
    'GLM': 'YDATA_GLM_API_KEY',
}
TTL_SECONDS = 120
_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {}
_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._/-]{0,159}$')
_PLACEHOLDER_KEYS = {'...', 'your-api-key', 'replace-me', 'bearer ...'}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
# A streamed reply carries every token in its own event, many times the size of the text itself.
MAX_STREAM_BYTES = 48 * 1024 * 1024
MAX_REPLY_CHARACTERS = 1024 * 1024
STREAM_SECONDS = 900
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
    try:
        _bindings()
        return True
    except GatewayError:
        return False


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


def _client() -> httpx.Client:
    # The read timeout is the longest silence allowed: between two chunks of a streamed reply, or
    # for the whole answer when a gateway does not stream.
    return httpx.Client(timeout=httpx.Timeout(300, connect=10, pool=10, write=30),
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


def _cache_fingerprint(manual: str) -> str:
    values = {
        'legacy': _legacy_key() or '',
        'manual': manual,
        'default': os.getenv('LEGAL_YDATA_DEFAULT_MODEL', ''),
        **{family: _read_key(env_name) or '' for family, env_name in FAMILY_KEY_ENVS.items()},
    }
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def model_catalog(*, client: httpx.Client | None = None) -> dict:
    bindings = _bindings()
    manual = os.getenv('LEGAL_YDATA_MODELS', '').strip()
    cache_key = _cache_fingerprint(manual)
    with _LOCK:
        if client is None and _CACHE.get('key') == cache_key and _CACHE.get('until', 0) > time.monotonic():
            return json.loads(json.dumps(_CACHE['catalog']))

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
                _key_for_family(family)
                models[mid] = {'id': mid, 'family': family}
        except GatewayError:
            raise
        except (ValueError, TypeError):
            raise GatewayError('ydata_catalog_invalid', 'LEGAL_YDATA_MODELS 必须是五个支持系列中确切模型 ID 的 JSON 数组。') from None
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
                        if not family:
                            continue
                        if family_hint is not None and family != family_hint:
                            continue
                        # A dedicated family credential is authoritative for that family. Do not
                        # silently source the same family from the legacy credential.
                        if family_hint is None and family in dedicated:
                            continue
                        models[mid] = {'id': mid, 'family': family}
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
        raise GatewayError('ydata_no_chat_models', '当前 YData 凭据未列出支持的 GPT、Claude、DeepSeek、Kimi 或 GLM 聊天型号。')

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
    if client is None:
        with _LOCK:
            _CACHE.update(key=cache_key, until=time.monotonic() + TTL_SECONDS, catalog=result)
    return json.loads(json.dumps(result))


def select_model(model_id: str, *, client: httpx.Client | None = None) -> dict:
    catalog = model_catalog(client=client)
    match = next((m for m in catalog['models'] if m['id'] == model_id), None)
    if match is None:
        raise GatewayError('legal_model_not_allowed', '所选模型不在当前可用列表，请刷新并重新选择。', 422)
    _key_for_family(match['family'])
    return {'provider': 'ydata', **match, 'catalog_source': catalog['catalog_source']}


def _output_tokens() -> int:
    """8192 by default; operators may raise it for model families that support longer answers."""
    try:
        return max(1024, min(65536, int(os.getenv('LEGAL_YDATA_MAX_TOKENS', '8192'))))
    except ValueError:
        return 8192


def _token_budget(model: str) -> dict:
    name = model.rsplit('/', 1)[-1].lower()
    if re.match(r'^(?:gpt-(?:[5-9]|[1-9]\d)|o\d)', name):
        return {'max_completion_tokens': _output_tokens()}
    return {'max_tokens': _output_tokens()}


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
            raise GatewayError('ydata_unavailable', UNAVAILABLE, 502)
        *lines, buffer = (buffer + part).split(b'\n')
        for line in lines:
            if line.startswith(b'data:'):
                yield line[5:].strip().decode('utf-8')
    if buffer.startswith(b'data:'):
        yield buffer[5:].strip().decode('utf-8')


def _reply(data: dict) -> tuple[str, str | None, int]:
    """Text, finish reason and reasoning length of an ordinary (not streamed) completion."""
    try:
        choice = data['choices'][0]
        finish = choice.get('finish_reason')
        message = choice.get('message') or {}
    except (KeyError, IndexError, TypeError, AttributeError):
        raise GatewayError('ydata_invalid_json', INCOMPLETE, 502) from None
    if not isinstance(message, dict):
        return '', finish, 0
    content = message.get('content')
    thinking = sum(len(message[k]) for k in ('reasoning_content', 'reasoning') if isinstance(message.get(k), str))
    return content if isinstance(content, str) else '', finish, thinking


def _stream_reply(client: httpx.Client, key: str, request: dict) -> tuple[str, str | None, int]:
    """A completion read while it is written. Bytes keep arriving as the model works, so a long
    structured answer is not cut off by an idle timeout on the way; it is used only once complete."""
    deadline = time.monotonic() + STREAM_SECONDS
    try:
        with client.stream('POST', BASE_URL + '/chat/completions', headers=_headers(key, 'text/event-stream'),
                            json={**request, 'stream': True}) as response:
            if not response.is_success:
                raise _status_error(response)
            if 'text/event-stream' not in response.headers.get('content-type', '').lower():
                # A gateway that ignores the stream flag answers with an ordinary completion.
                return _reply(_read_json(response))
            text, length, thinking, finish, done = [], 0, 0, None, False
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
                        # Reasoning is streamed beside the answer by some models; it is never part of it.
                        thinking += sum(len(delta[k]) for k in ('reasoning_content', 'reasoning') if isinstance(delta.get(k), str))
                    finish = choice.get('finish_reason') or finish
                if length > MAX_REPLY_CHARACTERS:
                    raise GatewayError('ydata_response_too_large', 'YData 响应超出限制。', 502)
    except GatewayError:
        raise
    except (httpx.HTTPError, ValueError, UnicodeError):
        raise GatewayError('ydata_unavailable', UNAVAILABLE, 502) from None
    if finish is None and not done:
        raise GatewayError('ydata_unavailable', 'YData 连接在模型输出完成前中断；未发布不完整结论，可重试。', 502)
    return ''.join(text), finish or 'stop', thinking


def _complete(client: httpx.Client, key: str, request: dict) -> tuple[str, str | None, int]:
    if _streaming():
        try:
            return _stream_reply(client, key, request)
        except GatewayError as exc:
            # A route that refuses a streamed request may still answer an ordinary one.
            if exc.code != 'ydata_request_failed' or not 400 <= (exc.upstream_status or 0) < 500:
                raise
    return _reply(_request(client, 'POST', '/chat/completions', key, json={**request, 'stream': False}))


def chat_json(system: str, payload: dict, selection: dict, *, client: httpx.Client | None = None) -> dict:
    if not isinstance(selection, dict) or selection.get('provider') != 'ydata':
        raise GatewayError('legacy_review_restart_required', '旧任务未记录 YData 模型及授权，请选择模型并新建审查。', 409)
    model = select_model(selection.get('id', ''), client=client)
    request = {'model': model['id'],
               'messages': [{'role': 'system', 'content': system},
                            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
               **_token_budget(model['id'])}
    key = _key_for_family(model['family'])
    # JSON is required by the prompt and checked locally. Do not impose an unsupported
    # response_format/temperature/thinking option on every gateway model family.
    started = time.monotonic()
    try:
        if client is None:
            with _client() as owned:
                content, finish, thinking = _complete(owned, key, request)
        else:
            content, finish, thinking = _complete(client, key, request)
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
        # Codes, sizes and timing only: never the prompt, the reply or a key.
        log.warning('ydata chat failed: model=%s code=%s upstream=%s seconds=%.1f', model['id'], exc.code,
                    exc.upstream_status, time.monotonic() - started)
        raise
