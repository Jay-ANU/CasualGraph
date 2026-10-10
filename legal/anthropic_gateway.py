"""Anthropic's native Messages transport for Claude, with no gateway fallback.

Only ANTHROPIC_API_KEY is used and the API origin is fixed. Model discovery is
read-only; chat makes exactly one request and publishes only a complete JSON
reply. Retries remain visible to the review worker's existing attempt budget.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import httpx

from legal import ydata

BASE_URL = 'https://api.anthropic.com/v1'
API_VERSION = '2023-06-01'
MAX_CATALOG_PAGES = 20
MAX_CATALOG_MODELS = 1000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_STREAM_BYTES = 48 * 1024 * 1024
MAX_REPLY_CHARACTERS = 1024 * 1024
STREAM_SECONDS = 900
_ID = re.compile(r'^claude-[A-Za-z0-9][A-Za-z0-9._-]{0,151}$')
INCOMPLETE = 'Anthropic 未返回完整的结构化结果；本次结果未发布，可重试。'
UNAVAILABLE = 'Anthropic 连接超时或响应无效；没有自动切换其他提供方或模型。'
log = logging.getLogger(__name__)


def configured() -> bool:
    return ydata._read_key('ANTHROPIC_API_KEY') is not None


def key() -> str:
    value = ydata._read_key('ANTHROPIC_API_KEY')
    if not value:
        raise ydata.GatewayError('anthropic_not_configured', 'Claude 官方 API 未配置，请管理员设置 ANTHROPIC_API_KEY。')
    return value


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(300, connect=10, pool=10, write=30),
                        follow_redirects=False, trust_env=False)


def _headers(secret: str, stream: bool = False) -> dict[str, str]:
    return {'x-api-key': secret, 'anthropic-version': API_VERSION, 'Content-Type': 'application/json',
            'Accept': 'text/event-stream' if stream else 'application/json'}


def _status_error(status: int, retry_after: str | None = None) -> ydata.GatewayError:
    if status == 402:
        return ydata.GatewayError('anthropic_billing_error', 'Anthropic 账户计费未就绪，请管理员检查余额及计费状态。', upstream_status=status)
    if status in (401, 403):
        return ydata.GatewayError('anthropic_unauthorized', 'Anthropic 拒绝访问，请管理员检查官方密钥及模型权限。', upstream_status=status)
    if status == 429:
        return ydata.GatewayError('anthropic_rate_limited', 'Anthropic 请求限额已达到，请稍后重试。', 429,
                                 retry_after=ydata._retry_after(retry_after), upstream_status=status)
    if status == 529:
        return ydata.GatewayError('anthropic_overloaded', 'Anthropic 服务暂时繁忙，请稍后重试。', 503, upstream_status=status)
    if status in (400, 404, 413):
        code, message = {
            400: ('anthropic_invalid_request', 'Anthropic 拒绝了请求参数，请检查所选模型及输出长度配置。'),
            404: ('anthropic_model_unavailable', '所选 Claude 官方型号不可用，请刷新模型列表并重新选择。'),
            413: ('anthropic_request_too_large', 'Anthropic 请求超过大小限制，请缩小审查范围。'),
        }[status]
        return ydata.GatewayError(code, message, 422, upstream_status=status)
    return ydata.GatewayError('anthropic_request_failed', f'Anthropic 请求失败（HTTP {status}）；没有自动切换模型或提供方。',
                             502, upstream_status=status)


def _read_json(response: httpx.Response) -> dict:
    parts, size = [], 0
    for part in response.iter_bytes():
        size += len(part)
        if size > MAX_RESPONSE_BYTES:
            raise ydata.GatewayError('anthropic_response_too_large', 'Anthropic 响应超出限制。', 502)
        parts.append(part)
    data = json.loads(b''.join(parts))
    if not isinstance(data, dict):
        raise ValueError('not an object')
    return data


def _get_models(client: httpx.Client, secret: str, params: dict) -> dict:
    try:
        with client.stream('GET', BASE_URL + '/models', headers=_headers(secret), params=params,
                           timeout=15, follow_redirects=False) as response:
            if not response.is_success:
                raise _status_error(response.status_code, response.headers.get('retry-after'))
            return _read_json(response)
    except ydata.GatewayError:
        raise
    except (ValueError, TypeError, UnicodeError):
        raise ydata.GatewayError('anthropic_catalog_invalid', 'Anthropic 模型列表格式无效。', 502) from None
    except httpx.HTTPError:
        raise ydata.GatewayError('anthropic_unavailable', UNAVAILABLE, 502) from None


def _catalog_invalid() -> ydata.GatewayError:
    return ydata.GatewayError('anthropic_catalog_invalid', 'Anthropic 模型列表无效或超过发现上限；未使用不完整列表。', 502)


def model_catalog(*, client: httpx.Client | None = None) -> dict:
    secret = key()
    manual = os.getenv('LEGAL_ANTHROPIC_MODELS', '').strip()
    if manual:
        try:
            ids = json.loads(manual)
            if (not isinstance(ids, list) or not ids or len(ids) > MAX_CATALOG_MODELS
                    or not all(isinstance(mid, str) and _ID.fullmatch(mid) for mid in ids)):
                raise ValueError('invalid inventory')
        except (ValueError, TypeError):
            raise ydata.GatewayError('anthropic_catalog_invalid', 'LEGAL_ANTHROPIC_MODELS 必须是 Claude 官方确切模型 ID 的非空 JSON 数组。') from None
        return {'provider': 'anthropic', 'models': [{'id': mid, 'family': 'Claude', 'provider': 'anthropic'} for mid in dict.fromkeys(ids)],
                'catalog_source': 'configured'}

    owned = _client() if client is None else None
    active = client if client is not None else owned
    models: dict[str, dict[str, Any]] = {}
    cursor, seen, count = None, set(), 0
    try:
        for _ in range(MAX_CATALOG_PAGES):
            params = {'limit': 100, **({'after_id': cursor} if cursor else {})}
            page = _get_models(active, secret, params)
            rows, more = page.get('data'), page.get('has_more')
            if not isinstance(rows, list) or not isinstance(more, bool):
                raise _catalog_invalid()
            count += len(rows)
            if count > MAX_CATALOG_MODELS:
                raise _catalog_invalid()
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get('id'), str):
                    raise _catalog_invalid()
                mid = row['id']
                if not _ID.fullmatch(mid) or row.get('lifecycle') == 'retired':
                    continue
                item = {'id': mid, 'family': 'Claude', 'provider': 'anthropic'}
                if isinstance(row.get('display_name'), str):
                    item['display_name'] = row['display_name'][:200]
                if type(row.get('max_tokens')) is int and row['max_tokens'] > 0:
                    item['max_output_tokens'] = row['max_tokens']
                models[mid] = item
            if not more:
                break
            cursor = page.get('last_id')
            if not rows or not isinstance(cursor, str) or not _ID.fullmatch(cursor) or cursor in seen:
                raise _catalog_invalid()
            seen.add(cursor)
        else:
            raise _catalog_invalid()
    finally:
        if owned is not None:
            owned.close()
    if not models:
        raise ydata.GatewayError('anthropic_no_chat_models', '当前 Anthropic 官方凭据未列出可用 Claude 型号。')
    return {'provider': 'anthropic', 'models': list(models.values()), 'catalog_source': 'official_api'}


def _output_tokens(model: dict) -> int:
    try:
        budget = max(1, min(65536, int(os.getenv('LEGAL_ANTHROPIC_MAX_TOKENS', '8192'))))
    except ValueError:
        budget = 8192
    discovered = model.get('max_output_tokens')
    return min(budget, discovered) if type(discovered) is int and discovered > 0 else budget


def _finish(reason: object):
    if reason in ('max_tokens', 'model_context_window_exceeded'):
        raise ydata.GatewayError('anthropic_truncated', 'Claude 输出因长度或上下文上限停止；未发布不完整结论，可缩小范围后重试。', 502)
    if reason == 'refusal':
        raise ydata.GatewayError('anthropic_refused', 'Claude 未能提供本次审查结果；请检查请求内容后重试。', 422)
    if reason != 'end_turn':
        raise ydata.GatewayError('anthropic_incomplete', INCOMPLETE, 502)


def _reply(data: dict) -> str:
    if data.get('type') != 'message' or data.get('role') != 'assistant' or not isinstance(data.get('content'), list):
        raise ydata.GatewayError('anthropic_incomplete', INCOMPLETE, 502)
    _finish(data.get('stop_reason'))
    parts = []
    for block in data['content']:
        if not isinstance(block, dict):
            raise ydata.GatewayError('anthropic_incomplete', INCOMPLETE, 502)
        if block.get('type') == 'text' and isinstance(block.get('text'), str):
            parts.append(block['text'])
        elif block.get('type') not in ('thinking', 'redacted_thinking'):
            raise ydata.GatewayError('anthropic_incomplete', INCOMPLETE, 502)
    content = ''.join(parts)
    if len(content) > MAX_REPLY_CHARACTERS:
        raise ydata.GatewayError('anthropic_response_too_large', 'Anthropic 响应超出限制。', 502)
    return content


def _events(response: httpx.Response, deadline: float):
    """Parse SSE framing across arbitrary UTF-8 chunks, including multiline data."""
    buffer, size, event, data = b'', 0, '', []
    for part in response.iter_bytes():
        size += len(part)
        if size > MAX_STREAM_BYTES:
            raise ydata.GatewayError('anthropic_response_too_large', 'Anthropic 响应超出限制。', 502)
        if time.monotonic() > deadline:
            raise ydata.GatewayError('anthropic_unavailable', UNAVAILABLE, 502)
        *lines, buffer = (buffer + part).split(b'\n')
        for line in lines:
            line = line.rstrip(b'\r')
            if not line:
                if data:
                    yield event, b'\n'.join(data).decode('utf-8')
                event, data = '', []
            elif line.startswith(b'event:'):
                event = line[6:].strip().decode('utf-8')
            elif line.startswith(b'data:'):
                data.append(line[5:].lstrip(b' '))


def _stream_error(chunk: dict, upstream_status: int):
    error = chunk.get('error')
    kind = error.get('type') if isinstance(error, dict) else None
    status = {'authentication_error': 401, 'billing_error': 402, 'permission_error': 403, 'rate_limit_error': 429,
              'overloaded_error': 529, 'invalid_request_error': 400, 'not_found_error': 404,
              'request_too_large': 413}.get(kind, 500)
    exc = _status_error(status)
    exc.upstream_status = upstream_status
    raise exc


def _stream_reply(response: httpx.Response, deadline: float) -> str:
    known = {'message_start', 'content_block_start', 'content_block_delta', 'content_block_stop',
             'message_delta', 'message_stop', 'error'}
    blocks, started, stopped, finish, length = {}, False, False, None, 0
    for event, raw in _events(response, deadline):
        if event and event not in known:
            continue  # Anthropic may add events; ping and unknown events carry no answer text.
        chunk = json.loads(raw)
        if not isinstance(chunk, dict):
            raise ValueError('invalid event')
        kind = chunk.get('type')
        if event and kind != event:
            raise ValueError('event type mismatch')
        if kind == 'error':
            _stream_error(chunk, response.status_code)
        if kind not in known:
            continue
        if kind == 'message_start':
            message = chunk.get('message')
            if started or not isinstance(message, dict) or message.get('type') != 'message' or message.get('role') != 'assistant' or message.get('content') != []:
                raise ValueError('invalid message start')
            started = True
            continue
        if not started:
            raise ValueError('missing message start')
        if kind in ('content_block_start', 'content_block_delta', 'content_block_stop'):
            index = chunk.get('index')
            if type(index) is not int or not 0 <= index < 1000 or finish is not None:
                raise ValueError('invalid content index')
            if kind == 'content_block_start':
                block = chunk.get('content_block')
                if index != len(blocks) or not isinstance(block, dict) or any(not existing['closed'] for existing in blocks.values()):
                    raise ValueError('invalid block start')
                block_type = block.get('type')
                if block_type not in ('text', 'thinking', 'redacted_thinking'):
                    raise ValueError('unexpected tool or content')
                initial = block.get('text', '') if block_type == 'text' else ''
                if not isinstance(initial, str):
                    raise ValueError('invalid initial text')
                blocks[index] = {'type': block_type, 'parts': [initial], 'closed': False}
                length += len(initial)
            else:
                block = blocks.get(index)
                if block is None or block['closed']:
                    raise ValueError('missing or closed content block')
                if kind == 'content_block_stop':
                    block['closed'] = True
                else:
                    delta = chunk.get('delta')
                    if not isinstance(delta, dict):
                        raise ValueError('invalid delta')
                    if delta.get('type') == 'text_delta':
                        piece = delta.get('text')
                        if block['type'] != 'text' or not isinstance(piece, str):
                            raise ValueError('invalid text delta')
                        block['parts'].append(piece)
                        length += len(piece)
        elif kind == 'message_delta':
            delta = chunk.get('delta')
            if not isinstance(delta, dict) or any(not block['closed'] for block in blocks.values()):
                raise ValueError('invalid message delta')
            reason = delta.get('stop_reason')
            if reason is not None:
                if finish is not None and finish != reason:
                    raise ValueError('conflicting stop reasons')
                finish = reason
        elif kind == 'message_stop':
            if any(not block['closed'] for block in blocks.values()):
                raise ValueError('unclosed content blocks')
            stopped = True
            break
        if length > MAX_REPLY_CHARACTERS:
            raise ydata.GatewayError('anthropic_response_too_large', 'Anthropic 响应超出限制。', 502)
    if not stopped:
        # Even syntactically valid JSON is unusable if the native message never completed.
        raise ydata.GatewayError('anthropic_incomplete', INCOMPLETE, 502)
    _finish(finish)
    return ''.join(''.join(blocks[index]['parts']) for index in sorted(blocks) if blocks[index]['type'] == 'text')


def chat_json(system: str, payload: dict, model: dict, *, client: httpx.Client | None = None) -> dict:
    if model.get('provider') != 'anthropic' or not isinstance(model.get('id'), str) or not _ID.fullmatch(model['id']):
        raise ydata.GatewayError('legacy_review_restart_required', 'Claude 接收方已变更为 Anthropic 官方，请重新选择模型并授权后新建审查。', 409)
    secret = key()
    stream = os.getenv('LEGAL_ANTHROPIC_STREAM', '1').strip().lower() not in ('0', 'false', 'no', 'off')
    request = {'model': model['id'], 'system': system, 'max_tokens': _output_tokens(model), 'stream': stream,
               'messages': [{'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]}
    started = time.monotonic()
    owned = _client() if client is None else None
    active = client if client is not None else owned
    try:
        with active.stream('POST', BASE_URL + '/messages', headers=_headers(secret, stream), json=request,
                           follow_redirects=False) as response:
            if not response.is_success:
                raise _status_error(response.status_code, response.headers.get('retry-after'))
            if 'text/event-stream' in response.headers.get('content-type', '').lower():
                content = _stream_reply(response, started + STREAM_SECONDS)
            else:
                content = _reply(_read_json(response))
        try:
            return ydata._json_object(content)
        except (ValueError, TypeError):
            raise ydata.GatewayError('anthropic_invalid_json', INCOMPLETE, 502) from None
    except ydata.GatewayError as exc:
        log.warning('anthropic chat failed: model=%s code=%s upstream=%s seconds=%.1f', model['id'], exc.code,
                    exc.upstream_status, time.monotonic() - started)
        raise
    except (ValueError, TypeError, UnicodeError):
        raise ydata.GatewayError('anthropic_incomplete', INCOMPLETE, 502) from None
    except httpx.HTTPError:
        raise ydata.GatewayError('anthropic_unavailable', UNAVAILABLE, 502) from None
    finally:
        if owned is not None:
            owned.close()
