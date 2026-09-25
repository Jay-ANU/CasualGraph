"""Server-only YData chat gateway with per-model-family credential routing."""
from __future__ import annotations

import hashlib
import json
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


class GatewayError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 503):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


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
    return httpx.Client(timeout=httpx.Timeout(150, connect=10, pool=10, write=30),
                        follow_redirects=False, trust_env=False)


def _request(client: httpx.Client, method: str, path: str, key: str, **kwargs) -> dict:
    try:
        with client.stream(method, BASE_URL + path,
                           headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                                    'Accept': 'application/json'}, **kwargs) as response:
            if not response.is_success:
                status = response.status_code
                if status in (401, 403):
                    raise GatewayError('ydata_unauthorized', 'YData 拒绝访问，请管理员检查密钥及模型授权。')
                if status == 429:
                    raise GatewayError('ydata_rate_limited', 'YData 请求限额已达到，请稍后重试。', 429)
                raise GatewayError('ydata_request_failed', 'YData 请求失败，请检查网关及所选模型的聊天接口支持。', 502)
            parts, size = [], 0
            for part in response.iter_bytes():
                size += len(part)
                if size > 2 * 1024 * 1024:
                    raise GatewayError('ydata_response_too_large', 'YData 响应超出限制。', 502)
                parts.append(part)
        data = json.loads(b''.join(parts))
        if not isinstance(data, dict):
            raise ValueError('not an object')
        return data
    except GatewayError:
        raise
    except (httpx.HTTPError, ValueError, UnicodeError):
        # Never expose upstream response bodies, authorization headers or contract prompts.
        raise GatewayError('ydata_unavailable', 'YData 连接超时或响应无效；没有自动切换其他模型。', 502) from None


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


def _token_budget(model: str) -> dict:
    name = model.rsplit('/', 1)[-1].lower()
    if re.match(r'^(?:gpt-(?:[5-9]|[1-9]\d)|o\d)', name):
        return {'max_completion_tokens': 8192}
    return {'max_tokens': 8192}


def chat_json(system: str, payload: dict, selection: dict, *, client: httpx.Client | None = None) -> dict:
    if not isinstance(selection, dict) or selection.get('provider') != 'ydata':
        raise GatewayError('legacy_review_restart_required', '旧任务未记录 YData 模型及授权，请选择模型并新建审查。', 409)
    model = select_model(selection.get('id', ''), client=client)
    request = {'model': model['id'], 'stream': False,
               'messages': [{'role': 'system', 'content': system},
                            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
               **_token_budget(model['id'])}
    key = _key_for_family(model['family'])
    # JSON is required by the prompt and checked locally. Do not impose an unsupported
    # response_format/temperature/thinking option on every gateway model family.
    if client is None:
        with _client() as owned:
            response = _request(owned, 'POST', '/chat/completions', key, json=request)
    else:
        response = _request(client, 'POST', '/chat/completions', key, json=request)
    try:
        choice = response['choices'][0]
        if choice.get('finish_reason') != 'stop':
            raise ValueError('incomplete response')
        content = choice['message']['content']
        if not isinstance(content, str):
            raise ValueError('no text response')
        text = content.strip()
        fenced = re.fullmatch(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL | re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError('not an object')
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        raise GatewayError('ydata_invalid_json', '模型未返回完整的结构化审查结果；任务已保留，可重试，不会发布截断结论。', 502) from None
