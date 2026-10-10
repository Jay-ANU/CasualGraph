"""Anthropic-native transport regressions. Every HTTP response is synthetic."""
import json

import httpx
import pytest

from legal import anthropic_gateway as anthropic, ydata


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    for name in ('YDATA_API_KEY', 'YDATA_CLAUDE_API_KEY', *ydata.FAMILY_KEY_ENVS.values(),
                 'LEGAL_YDATA_MODELS', 'LEGAL_YDATA_DEFAULT_MODEL', 'LEGAL_ANTHROPIC_MAX_TOKENS', 'LEGAL_ANTHROPIC_STREAM'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'synthetic-official-key')
    monkeypatch.setenv('LEGAL_ANTHROPIC_MODELS', '["claude-test"]')
    ydata.clear_cache()
    yield
    ydata.clear_cache()


def page(*ids, more=False, last=None):
    return {'data': [{'id': mid, 'type': 'model', 'lifecycle': 'active'} for mid in ids],
            'has_more': more, 'last_id': last or (ids[-1] if ids else None), 'first_id': ids[0] if ids else None}


def message(text='{"ok": true}', reason='end_turn', blocks=None):
    return {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant', 'model': 'claude-test',
            'content': blocks if blocks is not None else [{'type': 'text', 'text': text}],
            'stop_reason': reason, 'stop_sequence': None, 'usage': {'input_tokens': 10, 'output_tokens': 8}}


def chat(handler, *, selection=None, client_options=None):
    with httpx.Client(transport=httpx.MockTransport(handler), **(client_options or {})) as client:
        return ydata.chat_json('Return complete JSON.', {'contract': '【脱敏1】应按约付款。'},
                               selection or {'id': 'claude-test', 'provider': 'anthropic'}, client=client)


def test_claude_uses_only_native_official_endpoint_and_headers(monkeypatch):
    monkeypatch.setenv('YDATA_API_KEY', 'never-send-ydata-key')
    monkeypatch.setenv('YDATA_CLAUDE_API_KEY', 'never-send-retired-claude-key')
    monkeypatch.setenv('LEGAL_YDATA_MODELS', '["glm-test", "claude-old"]')
    monkeypatch.setenv('ANTHROPIC_BASE_URL', 'https://evil.test')
    monkeypatch.setenv('LEGAL_ANTHROPIC_BASE_URL', 'https://evil.test')
    sent = []

    def handler(request):
        sent.append(request)
        assert str(request.url) == 'https://api.anthropic.com/v1/messages'
        assert request.headers['x-api-key'] == 'synthetic-official-key'
        assert request.headers['anthropic-version'] == '2023-06-01'
        assert 'authorization' not in request.headers
        body = json.loads(request.content)
        assert body['model'] == 'claude-test' and body['system'] == 'Return complete JSON.'
        assert body['max_tokens'] == 8192 and body['stream'] is True
        assert [entry['role'] for entry in body['messages']] == ['user']
        assert json.loads(body['messages'][0]['content']) == {'contract': '【脱敏1】应按约付款。'}
        assert not any(name in body for name in ('temperature', 'top_p', 'response_format', 'output_format', 'tools'))
        assert 'key' not in request.content.decode()
        return httpx.Response(200, json=message())

    assert chat(handler) == {'ok': True}
    assert len(sent) == 1


def test_catalog_merges_official_claude_with_four_ydata_families(monkeypatch):
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    monkeypatch.setenv('YDATA_API_KEY', 'synthetic-ydata-key')
    seen = []

    def handler(request):
        seen.append(request.url.host)
        assert request.method == 'GET' and request.url.path == '/v1/models'
        if request.url.host == 'www.ydata.space':
            assert request.headers['authorization'] == 'Bearer synthetic-ydata-key'
            assert 'x-api-key' not in request.headers
            return httpx.Response(200, json={'data': [{'id': mid} for mid in ('gpt-test', 'claude-poison', 'deepseek-test', 'kimi-test', 'glm-test')]})
        assert request.headers['x-api-key'] == 'synthetic-official-key' and 'authorization' not in request.headers
        return httpx.Response(200, json=page('claude-official-test'))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        catalog = ydata.model_catalog(client=client)
    assert seen == ['www.ydata.space', 'api.anthropic.com']
    assert catalog['provider'] == 'mixed' and catalog['available_families'] == list(ydata.FAMILIES)
    assert 'claude-poison' not in [model['id'] for model in catalog['models']]
    assert [model['provider'] for model in catalog['models']] == ['ydata', 'anthropic', 'ydata', 'ydata', 'ydata']


def test_native_catalog_uses_all_pages_and_ignores_retired_models(monkeypatch):
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    cursors = []

    def handler(request):
        cursors.append(request.url.params.get('after_id'))
        assert request.url.params['limit'] == '100'
        if len(cursors) == 1:
            return httpx.Response(200, json=page('claude-first', more=True))
        result = page('claude-deprecated', 'claude-retired', 'claude-last')
        result['data'][0]['lifecycle'] = 'deprecated'
        result['data'][1]['lifecycle'] = 'retired'
        result['data'][2].update(max_tokens=4096, display_name='Claude test')
        return httpx.Response(200, json=result)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        catalog = ydata.model_catalog(client=client)
        selected = next(model for model in catalog['models'] if model['id'] == 'claude-last')
    assert cursors == [None, 'claude-first']
    assert catalog['provider'] == 'anthropic' and catalog['catalog_source'] == 'official_api'
    assert {model['id'] for model in catalog['models']} == {'claude-first', 'claude-deprecated', 'claude-last'}
    assert selected['max_output_tokens'] == 4096


@pytest.mark.parametrize('bad', [
    {'data': [], 'has_more': True, 'last_id': 'claude-test'},
    {'data': [{'id': 'claude-test'}], 'has_more': True, 'last_id': None},
    {'data': [{'id': 'claude-test'}]},
    {'data': 'wrong', 'has_more': False},
])
def test_malformed_catalog_never_yields_partial_models(monkeypatch, bad):
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=bad))) as client:
        with pytest.raises(ydata.GatewayError) as error:
            ydata.model_catalog(client=client)
    assert error.value.code == 'anthropic_catalog_invalid'


@pytest.mark.parametrize('limit', ['cursor', 'pages', 'models'])
def test_catalog_pagination_has_a_bound_and_never_silently_truncates(monkeypatch, limit):
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    monkeypatch.setattr(anthropic, 'MAX_CATALOG_PAGES', 2)
    if limit == 'models':
        monkeypatch.setattr(anthropic, 'MAX_CATALOG_MODELS', 1)
    calls = []

    def handler(request):
        calls.append(request)
        identifier = 'claude-repeat' if limit == 'cursor' else 'claude-page-' + str(len(calls))
        return httpx.Response(200, json=page(identifier, more=True))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ydata.GatewayError) as error:
            ydata.model_catalog(client=client)
    assert error.value.code == 'anthropic_catalog_invalid' and len(calls) <= 2


def test_admin_inventory_is_explicitly_configured_not_claimed_as_discovered():
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail('manual inventory did discovery'))) as client:
        selected = ydata.select_model('claude-test', client=client)
    assert selected['provider'] == 'anthropic' and selected['catalog_source'] == 'configured'


@pytest.mark.parametrize('inventory', ['[]', '{}', '["gpt-test"]', '["https://evil.test"]', '["anthropic/claude-test"]', 'not json'])
def test_invalid_official_inventory_fails_without_inventing_model_ids(monkeypatch, inventory):
    monkeypatch.setenv('LEGAL_ANTHROPIC_MODELS', inventory)
    with pytest.raises(ydata.GatewayError) as error:
        ydata.model_catalog()
    assert error.value.code == 'anthropic_catalog_invalid'


def test_retired_ydata_claude_key_cannot_configure_or_call_claude(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY')
    monkeypatch.setenv('YDATA_CLAUDE_API_KEY', 'retired-secret')
    assert ydata.configured() is False
    with pytest.raises(ydata.GatewayError) as error:
        chat(lambda request: pytest.fail('retired credential sent to a provider'))
    assert error.value.code == 'anthropic_not_configured'


@pytest.mark.parametrize('selection', [{'id': 'claude-test', 'provider': 'ydata'}, {'id': 'glm-test', 'provider': 'anthropic'}])
def test_saved_provider_mismatch_fails_before_any_network_request(selection):
    with pytest.raises(ydata.GatewayError) as error:
        chat(lambda request: pytest.fail('silently changed processing provider'), selection=selection)
    assert error.value.code == 'legacy_review_restart_required' and error.value.status_code == 409


def test_one_provider_failure_keeps_other_provider_available_and_exposes_reason(monkeypatch):
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    monkeypatch.setenv('YDATA_GLM_API_KEY', 'ydata-glm-secret')
    monkeypatch.setenv('LEGAL_YDATA_MODELS', '["glm-test"]')
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(529, text='private upstream error'))) as client:
        result = ydata.model_catalog(client=client)
        with pytest.raises(ydata.GatewayError) as error:
            ydata.select_model('claude-test', client=client)
    assert result['models'] == [{'id': 'glm-test', 'family': 'GLM', 'provider': 'ydata'}]
    assert result['provider_errors'][0]['code'] == 'anthropic_overloaded'
    assert result['unavailable_families'] == ['Claude'] and error.value.code == 'anthropic_overloaded'
    assert 'private' not in json.dumps(result)


def test_official_models_remain_available_when_ydata_is_misconfigured(monkeypatch):
    monkeypatch.setenv('YDATA_GPT_API_KEY', 'duplicate')
    monkeypatch.setenv('YDATA_GLM_API_KEY', 'duplicate')
    catalog = ydata.model_catalog()
    assert catalog['provider'] == 'anthropic' and catalog['provider_errors'][0]['code'] == 'ydata_key_conflict'
    assert ydata.configured() is True


def test_catalog_cache_is_scoped_to_official_key_and_manual_inventory(monkeypatch):
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    seen = []

    def handler(request):
        seen.append(request.headers['x-api-key'])
        return httpx.Response(200, json=page('claude-first' if len(seen) == 1 else 'claude-second'))

    monkeypatch.setattr(anthropic, '_client', lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    assert ydata.model_catalog()['models'][0]['id'] == 'claude-first'
    assert ydata.model_catalog()['models'][0]['id'] == 'claude-first'
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'rotated-synthetic-key')
    assert ydata.model_catalog()['models'][0]['id'] == 'claude-second'
    monkeypatch.setenv('LEGAL_ANTHROPIC_MODELS', '["claude-manual"]')
    assert ydata.model_catalog()['models'][0]['id'] == 'claude-manual'
    assert seen == ['synthetic-official-key', 'rotated-synthetic-key']


def test_claude_selection_and_message_never_wait_for_ydata_discovery(monkeypatch):
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    for family, env_name in ydata.FAMILY_KEY_ENVS.items():
        monkeypatch.setenv(env_name, 'synthetic-' + family)
    calls = []

    def handler(request):
        assert request.url.host == 'api.anthropic.com'
        calls.append(request.method)
        return httpx.Response(200, json=page('claude-test') if request.method == 'GET' else message())

    monkeypatch.setattr(anthropic, '_client', lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(ydata, '_client', lambda: pytest.fail('Claude waited for unrelated YData discovery'))
    selected = ydata.select_model('claude-test')
    monkeypatch.setenv('YDATA_GPT_API_KEY', 'rotated-unrelated-gpt-key')
    assert ydata.chat_json('JSON', {}, selected) == {'ok': True}
    assert calls == ['GET', 'POST']


def test_ydata_selection_and_message_never_wait_for_official_discovery(monkeypatch):
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    by_key = {}
    for family, env_name in ydata.FAMILY_KEY_ENVS.items():
        secret = 'synthetic-' + family
        monkeypatch.setenv(env_name, secret)
        by_key[secret] = {'GPT': 'gpt-test', 'DeepSeek': 'deepseek-test', 'Kimi': 'kimi-test', 'GLM': 'glm-test'}[family]
    calls = []

    def handler(request):
        assert request.url.host == 'www.ydata.space'
        calls.append(request.method)
        if request.method == 'GET':
            secret = request.headers['authorization'].removeprefix('Bearer ')
            return httpx.Response(200, json={'data': [{'id': by_key[secret]}]})
        assert json.loads(request.content)['model'] == 'glm-test'
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}]})

    monkeypatch.setattr(ydata, '_client', lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(anthropic, '_client', lambda: pytest.fail('YData waited for unrelated official discovery'))
    selected = ydata.select_model('glm-test')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'rotated-unrelated-official-key')
    assert ydata.chat_json('JSON', {}, selected) == {'ok': True}
    assert calls == ['GET'] * 4 + ['POST']


def test_provider_selection_cache_does_not_replace_mixed_ui_inventory_and_clear_resets_both(monkeypatch):
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    monkeypatch.setenv('YDATA_GLM_API_KEY', 'synthetic-glm-key')
    calls = []

    def handler(request):
        calls.append(request.url.host)
        assert request.method == 'GET'
        return httpx.Response(200, json=page('claude-test') if request.url.host == 'api.anthropic.com' else {'data': [{'id': 'glm-test'}]})

    factory = lambda: httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(ydata, '_client', factory)
    monkeypatch.setattr(anthropic, '_client', factory)
    assert ydata.select_model('claude-test')['provider'] == 'anthropic'
    assert ydata.model_catalog()['provider'] == 'mixed'
    assert ydata.select_model('glm-test')['provider'] == 'ydata'
    assert ydata.model_catalog()['provider'] == 'mixed'
    assert calls == ['api.anthropic.com', 'www.ydata.space']
    monkeypatch.setenv('LEGAL_ANTHROPIC_MODELS', '["claude-new"]')
    assert ydata.select_model('claude-new')['catalog_source'] == 'configured'
    updated = ydata.model_catalog()
    assert updated['provider'] == 'mixed' and {model['id'] for model in updated['models']} == {'claude-new', 'glm-test'}
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    ydata.clear_cache()
    assert ydata.model_catalog()['provider'] == 'mixed'
    assert calls == ['api.anthropic.com', 'www.ydata.space', 'www.ydata.space', 'api.anthropic.com']


class Pieces(httpx.SyncByteStream):
    def __init__(self, body: bytes):
        self.body = body

    def __iter__(self):
        for index in range(0, len(self.body), 7):
            yield self.body[index:index + 7]


def events(text='{"ok": true}', finish='end_turn'):
    return [
        {'type': 'message_start', 'message': message(blocks=[], reason=None)},
        {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}},
        *[{'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'text_delta', 'text': text[index:index + 3]}}
          for index in range(0, len(text), 3)],
        {'type': 'content_block_stop', 'index': 0},
        {'type': 'message_delta', 'delta': {'stop_reason': finish, 'stop_sequence': None}, 'usage': {'output_tokens': 11}},
        {'type': 'message_stop'},
    ]


def streamed(values):
    body = ''.join('event: ' + item['type'] + '\r\ndata: ' + json.dumps(item, ensure_ascii=False) + '\r\n\r\n' for item in values).encode()
    return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=Pieces(body))


def test_native_sse_collects_full_unicode_answer_and_ignores_ping_unknown_events():
    data = events('{"title": "付款与验收"}')
    data.insert(2, {'type': 'ping'})
    data.insert(3, {'type': 'future_event', 'value': 'not part of the answer'})
    assert chat(lambda request: streamed(data)) == {'title': '付款与验收'}


def test_native_sse_does_not_put_thinking_in_the_json_answer():
    data = events()
    for item in data:
        if 'index' in item:
            item['index'] = 1
    data[1:1] = [
        {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'thinking', 'thinking': ''}},
        {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'thinking_delta', 'thinking': '{"wrong":true}'}},
        {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'signature_delta', 'signature': 'synthetic'}},
        {'type': 'content_block_stop', 'index': 0},
    ]
    assert chat(lambda request: streamed(data)) == {'ok': True}


@pytest.mark.parametrize('removed', ['message_start', 'content_block_start', 'content_block_stop', 'message_delta', 'message_stop'])
def test_native_sse_never_publishes_valid_json_from_an_incomplete_message(removed):
    data = [item for item in events() if item['type'] != removed]
    with pytest.raises(ydata.GatewayError) as error:
        chat(lambda request: streamed(data))
    assert error.value.code == 'anthropic_incomplete'


@pytest.mark.parametrize('reason,code', [('max_tokens', 'anthropic_truncated'), ('model_context_window_exceeded', 'anthropic_truncated'),
                                        ('tool_use', 'anthropic_incomplete'), ('pause_turn', 'anthropic_incomplete'),
                                        ('stop_sequence', 'anthropic_incomplete'), ('refusal', 'anthropic_refused')])
@pytest.mark.parametrize('stream', [False, True])
def test_native_stop_reasons_are_checked_even_when_text_is_valid_json(reason, code, stream):
    with pytest.raises(ydata.GatewayError) as error:
        chat(lambda request: streamed(events(finish=reason)) if stream else httpx.Response(200, json=message(reason=reason)))
    assert error.value.code == code


@pytest.mark.parametrize('status,code', [(400, 'anthropic_invalid_request'), (401, 'anthropic_unauthorized'),
                                        (402, 'anthropic_billing_error'),
                                        (403, 'anthropic_unauthorized'), (404, 'anthropic_model_unavailable'),
                                        (413, 'anthropic_request_too_large'), (429, 'anthropic_rate_limited'),
                                        (500, 'anthropic_request_failed'), (529, 'anthropic_overloaded'), (302, 'anthropic_request_failed')])
def test_official_errors_are_sanitized_never_retried_or_redirected(status, code, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text='secret-upstream-contract-body synthetic-official-key',
                              headers={'Location': 'https://evil.test/capture', 'retry-after': '120'})

    with pytest.raises(ydata.GatewayError) as error:
        chat(handler, client_options={'follow_redirects': True})
    assert error.value.code == code and error.value.upstream_status == status
    assert len(calls) == 1 and calls[0].url.host == 'api.anthropic.com'
    assert 'secret-upstream' not in str(error.value) + caplog.text and 'synthetic-official-key' not in caplog.text
    if status == 429:
        assert error.value.retry_after == 60


def test_native_sse_error_overrides_partial_valid_json_without_leaking_body():
    data = events()
    data.insert(-1, {'type': 'error', 'error': {'type': 'overloaded_error', 'message': 'private-body'}})
    with pytest.raises(ydata.GatewayError) as error:
        chat(lambda request: streamed(data))
    assert error.value.code == 'anthropic_overloaded' and error.value.upstream_status == 200
    assert 'private-body' not in str(error.value)


@pytest.mark.parametrize('text', ['not JSON', '[]', '{"partial":'])
def test_complete_message_still_requires_a_json_object(text):
    with pytest.raises(ydata.GatewayError) as error:
        chat(lambda request: httpx.Response(200, json=message(text=text)))
    assert error.value.code == 'anthropic_invalid_json'


def test_explicit_nonstream_uses_native_messages_once(monkeypatch):
    monkeypatch.setenv('LEGAL_ANTHROPIC_STREAM', '0')
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=message())

    assert chat(handler) == {'ok': True} and len(calls) == 1 and calls[0]['stream'] is False


def test_discovered_output_limit_caps_requested_tokens(monkeypatch):
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    monkeypatch.setenv('LEGAL_ANTHROPIC_MAX_TOKENS', '32768')

    def handler(request):
        if request.method == 'GET':
            data = page('claude-test')
            data['data'][0]['max_tokens'] = 4096
            return httpx.Response(200, json=data)
        assert json.loads(request.content)['max_tokens'] == 4096
        return httpx.Response(200, json=message())

    assert chat(handler) == {'ok': True}


@pytest.mark.parametrize('budget', ['stream_bytes', 'response_bytes', 'reply_characters', 'deadline'])
def test_official_stream_and_response_budgets_are_enforced(monkeypatch, budget):
    if budget == 'stream_bytes':
        monkeypatch.setattr(anthropic, 'MAX_STREAM_BYTES', 12)
    elif budget == 'response_bytes':
        monkeypatch.setattr(anthropic, 'MAX_RESPONSE_BYTES', 12)
    elif budget == 'reply_characters':
        monkeypatch.setattr(anthropic, 'MAX_REPLY_CHARACTERS', 3)
    else:
        monkeypatch.setattr(anthropic, 'STREAM_SECONDS', -1)
    with pytest.raises(ydata.GatewayError) as error:
        chat(lambda request: httpx.Response(200, json=message()) if budget == 'response_bytes' else streamed(events()))
    assert error.value.code == ('anthropic_unavailable' if budget == 'deadline' else 'anthropic_response_too_large')


def test_official_timeout_is_sanitized_and_not_automatically_retried():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('contains-private-prompt-and-key', request=request)

    with pytest.raises(ydata.GatewayError) as error:
        chat(handler)
    assert error.value.code == 'anthropic_unavailable' and len(calls) == 1
    assert 'private-prompt' not in str(error.value)


class Dropped(httpx.SyncByteStream):
    """A streamed body whose connection drops after the given bytes."""
    def __init__(self, body: bytes):
        self.body = body

    def __iter__(self):
        yield self.body
        raise httpx.ReadError('connection reset by peer')


def chat_turn(handler, messages=None, **options):
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return ydata.chat(messages or [{'role': 'system', 'content': '审查说明'}, {'role': 'user', 'content': '合同全文'}],
                          {'id': 'claude-test', 'provider': 'anthropic'}, client=client, **options)


def test_a_chat_turn_for_claude_goes_to_the_official_api_as_a_native_conversation():
    sent, seen = [], []

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        assert str(request.url) == 'https://api.anthropic.com/v1/messages' and 'authorization' not in request.headers
        return streamed(events('<review_memo>意见书</review_memo>'))
    history = [{'role': 'system', 'content': '审查说明'}, {'role': 'user', 'content': '合同全文'},
               {'role': 'assistant', 'content': '已写部分'}, {'role': 'user', 'content': '继续'}]
    result = chat_turn(handler, history, max_tokens=32768, on_delta=lambda piece, reasoned: seen.append(piece))
    assert result == {'content': '<review_memo>意见书</review_memo>', 'finish': 'stop', 'reasoning_chars': 0, 'model': 'claude-test'}
    assert sent[0]['system'] == '审查说明' and sent[0]['max_tokens'] == 32768
    assert sent[0]['messages'] == [{'role': 'user', 'content': '合同全文'}, {'role': 'assistant', 'content': '已写部分'},
                                   {'role': 'user', 'content': '继续'}]
    assert ''.join(seen) == '<review_memo>意见书</review_memo>'


def test_a_chat_turn_for_claude_that_reaches_the_output_limit_can_be_continued():
    assert chat_turn(lambda request: streamed(events('半篇意见', 'max_tokens')))['finish'] == 'length'
    assert chat_turn(lambda request: httpx.Response(200, json=message('半篇意见', 'max_tokens')))['finish'] == 'length'


def test_a_chat_turn_for_claude_cut_off_mid_answer_keeps_what_was_written():
    body = ''.join('event: ' + item['type'] + '\r\ndata: ' + json.dumps(item, ensure_ascii=False) + '\r\n\r\n'
                   for item in events('已写的意见')[:-3]).encode()
    result = chat_turn(lambda request: httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=Dropped(body)))
    assert result['content'] == '已写的意见' and result['finish'] == 'length'
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={'content-type': 'text/event-stream'},
                                                                                   stream=Dropped(body)))) as client:
        with pytest.raises(ydata.GatewayError) as exc:
            ydata.chat_json('JSON', {}, {'id': 'claude-test', 'provider': 'anthropic'}, client=client)
    assert exc.value.code == 'anthropic_unavailable'


@pytest.mark.parametrize('reason,code', [('refusal', 'anthropic_refused'), ('model_context_window_exceeded', 'anthropic_truncated')])
def test_a_chat_turn_for_claude_that_stops_for_another_reason_is_not_published(reason, code):
    with pytest.raises(ydata.GatewayError) as exc:
        chat_turn(lambda request: streamed(events('部分', reason)))
    assert exc.value.code == code


def test_a_chat_turn_for_claude_respects_the_models_own_output_limit(monkeypatch):
    monkeypatch.delenv('LEGAL_ANTHROPIC_MODELS')
    sent = []

    def handler(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': 'claude-test', 'type': 'model', 'max_tokens': 16000}], 'has_more': False,
                                             'last_id': 'claude-test', 'first_id': 'claude-test'})
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=message('好'))
    chat_turn(handler, max_tokens=32768)
    assert sent[0]['max_tokens'] == 16000


def test_a_claude_review_saved_for_ydata_never_reaches_a_new_recipient():
    with httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail('nothing may be sent'))) as client:
        with pytest.raises(ydata.GatewayError) as exc:
            ydata.chat([{'role': 'user', 'content': '合同'}], {'id': 'claude-test', 'provider': 'ydata'}, client=client)
    assert exc.value.code == 'legacy_review_restart_required'
