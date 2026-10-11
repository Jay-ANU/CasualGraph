"""Anthropic's native Messages transport for Claude, with no gateway fallback.

Only ANTHROPIC_API_KEY is used and the API origin is fixed. Model discovery is
read-only; chat_json makes exactly one request and publishes only a complete JSON
reply. chat runs one turn of a chat-style review and returns what was written,
so the caller can continue an answer that stopped at a limit, or run the tools
the model asked for. Retries remain visible to the review worker's existing
attempt budget.
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
# A chat turn may write a whole review: allow it longer, and keep what was written when time runs out.
CHAT_STREAM_SECONDS = 1800
CHAT_IDLE_SECONDS = 600
_ID = re.compile(r'^claude-[A-Za-z0-9][A-Za-z0-9._-]{0,151}$')
INCOMPLETE = 'Anthropic 未返回完整的结构化结果；本次结果未发布，可重试。'
UNAVAILABLE = 'Anthropic 连接超时或响应无效；没有自动切换其他提供方或模型。'
log = logging.getLogger(__name__)


class StreamDeadline(ydata.GatewayError):
    """A streamed reply still running when its time was up."""

    def __init__(self):
        super().__init__('anthropic_unavailable', UNAVAILABLE, 502)


def configured() -> bool:
    return ydata._read_key('ANTHROPIC_API_KEY') is not None


def key() -> str:
    value = ydata._read_key('ANTHROPIC_API_KEY')
    if not value:
        raise ydata.GatewayError('anthropic_not_configured', 'Claude 官方 API 未配置，请管理员设置 ANTHROPIC_API_KEY。')
    return value


def _client(idle: float = 300) -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(idle, connect=10, pool=10, write=30),
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


def default_output_tokens() -> int:
    """LEGAL_ANTHROPIC_MAX_TOKENS, 8192 by default."""
    try:
        return max(1, min(65536, int(os.getenv('LEGAL_ANTHROPIC_MAX_TOKENS', '8192'))))
    except ValueError:
        return 8192


def _output_tokens(model: dict, requested: int | None = None) -> int:
    budget = requested or default_output_tokens()
    discovered = model.get('max_output_tokens')
    return min(budget, discovered) if type(discovered) is int and discovered > 0 else budget


def _finish(reason: object):
    if reason in ('max_tokens', 'model_context_window_exceeded'):
        raise ydata.GatewayError('anthropic_truncated', 'Claude 输出因长度或上下文上限停止；未发布不完整结论，可缩小范围后重试。', 502)
    if reason == 'refusal':
        raise ydata.GatewayError('anthropic_refused', 'Claude 未能提供本次审查结果；请检查请求内容后重试。', 422)
    if reason != 'end_turn':
        raise ydata.GatewayError('anthropic_incomplete', INCOMPLETE, 502)


def _message(data: dict, strict: bool = True, tools: bool = False) -> tuple[str, object, int, list[dict]]:
    """Text, stop reason, reasoning length and tool calls of a complete (not streamed) message.

    Strict, as for a JSON reply, any stop other than the end of the turn is an error. A tool call
    is accepted only when tools were offered.
    """
    if data.get('type') != 'message' or data.get('role') != 'assistant' or not isinstance(data.get('content'), list):
        raise ydata.GatewayError('anthropic_incomplete', INCOMPLETE, 502)
    if strict:
        _finish(data.get('stop_reason'))
    parts, reasoning, calls = [], 0, []
    for block in data['content']:
        if not isinstance(block, dict):
            raise ydata.GatewayError('anthropic_incomplete', INCOMPLETE, 502)
        if block.get('type') == 'text' and isinstance(block.get('text'), str):
            parts.append(block['text'])
        elif block.get('type') in ('thinking', 'redacted_thinking'):
            reasoning += len(block['thinking']) if isinstance(block.get('thinking'), str) else 0
        elif (block.get('type') == 'tool_use' and tools and isinstance(block.get('id'), str) and isinstance(block.get('name'), str)
              and isinstance(block.get('input'), dict)):
            calls.append({'id': block['id'], 'name': block['name'], 'arguments': json.dumps(block['input'], ensure_ascii=False)})
        else:
            raise ydata.GatewayError('anthropic_incomplete', INCOMPLETE, 502)
    content = ''.join(parts)
    if len(content) > MAX_REPLY_CHARACTERS:
        raise ydata.GatewayError('anthropic_response_too_large', 'Anthropic 响应超出限制。', 502)
    return content, data.get('stop_reason'), reasoning, calls


def _reply(data: dict) -> str:
    return _message(data)[0]


def _events(response: httpx.Response, deadline: float):
    """Parse SSE framing across arbitrary UTF-8 chunks, including multiline data."""
    buffer, size, event, data = b'', 0, '', []
    for part in response.iter_bytes():
        size += len(part)
        if size > MAX_STREAM_BYTES:
            raise ydata.GatewayError('anthropic_response_too_large', 'Anthropic 响应超出限制。', 502)
        if time.monotonic() > deadline:
            raise StreamDeadline()
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


def _read_stream(response: httpx.Response, deadline: float, on_delta: ydata.Progress | None = None,
                 partial: bool = False, tools: bool = False) -> tuple[str, object, int, list[dict]]:
    """Text, stop reason, reasoning length and tool calls of a streamed message, checked event by event.

    on_delta sees text and reasoning as they arrive, for progress only. With partial, a message cut
    off by a dropped connection or the deadline is returned as far as it got, as if stopped at the
    output limit, so the conversation can continue from there; a tool call still being written is
    dropped. Tool calls are accepted only when tools were offered.
    """
    blocks: dict[int, dict] = {}
    reasoning = [0]

    def written() -> str:
        return ''.join(''.join(blocks[index]['parts']) for index in sorted(blocks) if blocks[index]['type'] == 'text')

    try:
        stopped, finish = _read_events(response, deadline, blocks, reasoning, on_delta, tools)
    except (StreamDeadline, httpx.HTTPError):
        if partial and written().strip():
            return written(), 'max_tokens', reasoning[0], []
        raise
    if not stopped:
        if partial and written().strip():
            return written(), 'max_tokens', reasoning[0], []
        # Even syntactically valid JSON is unusable if the native message never completed.
        raise ydata.GatewayError('anthropic_incomplete', INCOMPLETE, 502)
    calls = []
    for index in sorted(blocks):
        block = blocks[index]
        if block['type'] == 'tool_use':
            calls.append({'id': block['id'], 'name': block['name'],
                          'arguments': ''.join(block['parts']) or json.dumps(block['input'], ensure_ascii=False)})
    return written(), finish, reasoning[0], calls


def _stream_reply(response: httpx.Response, deadline: float) -> str:
    content, finish, _, _ = _read_stream(response, deadline)
    _finish(finish)
    return content


def _read_events(response: httpx.Response, deadline: float, blocks: dict, reasoning: list,
                 on_delta: ydata.Progress | None, tools: bool = False) -> tuple[bool, object]:
    known = {'message_start', 'content_block_start', 'content_block_delta', 'content_block_stop',
             'message_delta', 'message_stop', 'error'}
    started, stopped, finish, length = False, False, None, 0
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
                if block_type == 'tool_use' and tools:
                    if not isinstance(block.get('id'), str) or not isinstance(block.get('name'), str) or not isinstance(block.get('input', {}), dict):
                        raise ValueError('invalid tool call')
                    blocks[index] = {'type': block_type, 'id': block['id'], 'name': block['name'], 'input': block.get('input', {}),
                                     'parts': [], 'closed': False}
                    continue
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
                        if on_delta and piece:
                            on_delta(piece, 0)
                    elif delta.get('type') == 'input_json_delta':
                        piece = delta.get('partial_json')
                        if block['type'] != 'tool_use' or not isinstance(piece, str):
                            raise ValueError('invalid tool input delta')
                        block['parts'].append(piece)
                        length += len(piece)
                    elif delta.get('type') == 'thinking_delta' and isinstance(delta.get('thinking'), str):
                        # Reasoning is counted for progress; it is never part of the answer.
                        reasoning[0] += len(delta['thinking'])
                        if on_delta and delta['thinking']:
                            on_delta('', len(delta['thinking']))
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
    return stopped, finish


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


def _blocks(content) -> list[dict]:
    if isinstance(content, list):
        return content
    return [{'type': 'text', 'text': content}] if content else []


def _arguments(value) -> dict:
    try:
        parsed = json.loads(value) if isinstance(value, str) and value.strip() else {}
    except ValueError:
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def _conversation(messages: list[dict]) -> tuple[str, list[dict]]:
    """OpenAI-style messages as Anthropic's system prompt and alternating user and assistant turns.

    An assistant message that asked for tools becomes tool_use blocks, and each tool message a
    tool_result block in the user turn that follows.
    """
    system = '\n\n'.join(m['content'] for m in messages if m.get('role') == 'system' and isinstance(m.get('content'), str))
    turns: list[dict] = []

    def add(role: str, content) -> None:
        if turns and turns[-1]['role'] == role:
            last = turns[-1]['content']
            turns[-1]['content'] = (last + '\n\n' + content if isinstance(last, str) and isinstance(content, str)
                                    else _blocks(last) + _blocks(content))
        else:
            turns.append({'role': role, 'content': content})

    for m in messages:
        role = m.get('role')
        if role == 'tool':
            add('user', [{'type': 'tool_result', 'tool_use_id': str(m.get('tool_call_id') or ''),
                          'content': m['content'] if isinstance(m.get('content'), str) else ''}])
        elif role == 'assistant' and m.get('tool_calls'):
            text = m.get('content') if isinstance(m.get('content'), str) and m['content'].strip() else ''
            add('assistant', _blocks(text) + [{'type': 'tool_use', 'id': str(call.get('id') or ''), 'name': str((call.get('function') or {}).get('name') or ''),
                                                'input': _arguments((call.get('function') or {}).get('arguments'))}
                                               for call in m['tool_calls'] if isinstance(call, dict)])
        elif role in ('user', 'assistant') and isinstance(m.get('content'), str):
            add(role, m['content'])
    if not turns or turns[0]['role'] != 'user' or turns[-1]['role'] != 'user':
        raise ydata.GatewayError('legal_conversation_invalid', '审查对话格式无效，未发送请求。', 500)
    return system, turns


def _cached(turn: dict) -> dict:
    """The turn with a prompt-cache breakpoint at its end."""
    blocks = [dict(block) for block in _blocks(turn['content'])]
    if blocks:
        blocks[-1]['cache_control'] = {'type': 'ephemeral'}
    return {**turn, 'content': blocks}


def chat(messages: list[dict], model: dict, *, max_tokens: int | None = None, on_delta: ydata.Progress | None = None,
         client: httpx.Client | None = None, tools: list[dict] | None = None) -> dict:
    """One turn of a chat-style review, returned as Claude wrote it.

    An answer stopped at the output limit, or cut off by the deadline or a dropped connection, is
    returned with finish="length" so the caller can ask Claude to continue. With tools
    (OpenAI-style function definitions) Claude may ask for them instead: finish="tool_calls" with
    tool_calls [{id, name, arguments}]. Each request of such a conversation repeats the contract,
    so the contract and the latest turn are marked for Anthropic's prompt cache. A refusal, a full
    context window or any other stop is an error, as in chat_json.
    """
    if model.get('provider') != 'anthropic' or not isinstance(model.get('id'), str) or not _ID.fullmatch(model['id']):
        raise ydata.GatewayError('legacy_review_restart_required', 'Claude 接收方已变更为 Anthropic 官方，请重新选择模型并授权后新建审查。', 409)
    secret = key()
    system, turns = _conversation(messages)
    stream = os.getenv('LEGAL_ANTHROPIC_STREAM', '1').strip().lower() not in ('0', 'false', 'no', 'off')
    request = {'model': model['id'], 'max_tokens': _output_tokens(model, max_tokens), 'stream': stream, 'messages': turns,
               **({'system': system} if system else {})}
    if tools:
        request['tools'] = [{'name': f['function']['name'], 'description': f['function'].get('description', ''),
                             'input_schema': f['function'].get('parameters') or {'type': 'object', 'properties': {}}} for f in tools]
        request['messages'] = [_cached(turn) if i in (0, len(turns) - 1) else turn for i, turn in enumerate(turns)]
    started = time.monotonic()
    owned = _client(CHAT_IDLE_SECONDS) if client is None else None
    active = client if client is not None else owned
    try:
        with active.stream('POST', BASE_URL + '/messages', headers=_headers(secret, stream), json=request,
                           follow_redirects=False) as response:
            if not response.is_success:
                raise _status_error(response.status_code, response.headers.get('retry-after'))
            if 'text/event-stream' in response.headers.get('content-type', '').lower():
                content, finish, reasoning, calls = _read_stream(response, started + CHAT_STREAM_SECONDS, on_delta, partial=True, tools=bool(tools))
            else:
                content, finish, reasoning, calls = _message(_read_json(response), strict=False, tools=bool(tools))
                if on_delta and (content or reasoning):
                    on_delta(content, reasoning)
        if finish == 'max_tokens':
            state = 'length'
        elif finish == 'tool_use' and calls:
            state = 'tool_calls'
        elif finish in ('end_turn', 'stop_sequence'):
            state = 'stop'
        else:
            _finish(finish)
            state = 'stop'
        result = {'content': content, 'finish': state, 'reasoning_chars': reasoning, 'model': model['id']}
        if state == 'tool_calls':
            result['tool_calls'] = calls
        return result
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
