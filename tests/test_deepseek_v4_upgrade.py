"""No-network migration contracts; no provider credits or real credentials required."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from configs import settings
from rag import deep_answering as deep
from rag.model_status import get_model_status
from rag.openai_compat import chat_token_kwargs

ROOT = Path(__file__).resolve().parents[1]


def configured_settings(tmp_path, **overrides):
    env = dict(os.environ)
    for name in list(env):
        if name.startswith(('LLM_', 'OPENAI_', 'ANTHROPIC_', 'DEEPSEEK_', 'RAG_', 'VISION_', 'HYDE_', 'CHAT_')):
            env.pop(name)
    env.update(DATA_DIR=str(tmp_path), **overrides)
    output = subprocess.check_output([sys.executable, '-c', '''
import json
from configs import settings as s
print(json.dumps({
    "provider": s.LLM_PROVIDER, "key": s.OPENAI_API_KEY,
    "base": s.OPENAI_BASE_URL, "model": s.OPENAI_MODEL,
    "deep_model": s.RAG_DEEP_MODEL, "mode": s.RAG_ANSWER_MODE,
    "hyde": s.HYDE_MODEL, "prediction": s.RAG_PREDICTION_MODEL,
    "configured": s.openai_configured(), "deep_budget": s.RAG_DEEP_MAX_TOKENS,
}))
'''], cwd=ROOT, env=env, text=True)
    return json.loads(output)


def test_default_migration_ignores_old_provider_keys_and_model_names(tmp_path):
    data = configured_settings(tmp_path, DEEPSEEK_API_KEY='unit-deepseek', OPENAI_API_KEY='unit-old',
                               ANTHROPIC_API_KEY='unit-claude', OPENAI_MODEL='gpt-old',
                               RAG_DEEP_MODEL='claude-old', HYDE_MODEL='gpt-old',
                               RAG_PREDICTION_MODEL='gpt-old', RAG_ANSWER_MODE='openai')
    assert data['provider'] == 'deepseek'
    assert data['key'] == 'unit-deepseek'
    assert data['base'] == 'https://api.deepseek.com'
    assert {data[k] for k in ['model', 'deep_model', 'hyde', 'prediction']} == {'deepseek-v4-pro'}
    assert data['mode'] == 'deepseek'
    assert data['deep_budget'] == 16384


def test_missing_deepseek_key_does_not_borrow_old_key_or_load_local_model(tmp_path):
    data = configured_settings(tmp_path, OPENAI_API_KEY='unit-old', ANTHROPIC_API_KEY='unit-claude')
    assert data['configured'] is False
    assert data['key'] == ''
    assert data['mode'] == 'deepseek'


def test_explicit_legacy_rollback_is_respected(tmp_path):
    data = configured_settings(tmp_path, LLM_PROVIDER='openai', OPENAI_API_KEY='unit-old',
                               OPENAI_MODEL='gpt-test', RAG_DEEP_MODEL='claude-test')
    assert data['model'] == 'gpt-test'
    assert data['key'] == 'unit-old'
    assert data['deep_model'] == 'claude-test'


@pytest.mark.parametrize('model', ['deepseek-v4-pro', 'deepseek-v4-flash'])
def test_fast_and_small_budget_requests_explicitly_disable_thinking(model):
    assert chat_token_kwargs(model, 240) == {
        'max_tokens': 240, 'extra_body': {'thinking': {'type': 'disabled'}},
    }


def test_legacy_token_parameter_is_unchanged():
    assert chat_token_kwargs('gpt-5-test', 120) == {'max_completion_tokens': 120}
    assert chat_token_kwargs('gpt-4', 120) == {'max_tokens': 120}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(deep, 'LLM_PROVIDER', 'deepseek')
    monkeypatch.setattr(deep, 'RAG_DEEP_MODEL', 'deepseek-v4-pro')
    value = NS(chat=NS(completions=NS(create=Mock())))
    monkeypatch.setattr(deep, 'get_openai_client', lambda: value)
    # A populated/available Claude client must still never be selected.
    import rag.claude_answering as legacy
    monkeypatch.setattr(legacy, 'generate_claude_deep_rag_answer', Mock(side_effect=AssertionError('Claude was invoked')))
    monkeypatch.setattr(legacy, 'stream_claude_deep_rag_answer', Mock(side_effect=AssertionError('Claude was invoked')))
    return value


def test_deep_sync_preserves_citations_and_drops_reasoning(client):
    client.chat.completions.create.return_value = NS(choices=[NS(
        message=NS(content='A supported answer [chunk_1].', reasoning_content='private scratch text'),
        finish_reason='stop',
    )])
    assert deep.generate_deep_rag_answer('What changed?', [{'chunk_id': 'chunk_1', 'text': 'disclosed evidence'}]) == 'A supported answer [chunk_1].'
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs['model'] == 'deepseek-v4-pro'
    assert kwargs['extra_body'] == {'thinking': {'type': 'enabled'}}
    assert kwargs['reasoning_effort'] == 'high'
    assert 'temperature' not in kwargs
    assert '[chunk_1]' in kwargs['messages'][1]['content']


class Stream:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def __iter__(self):
        for item in self.events:
            if isinstance(item, Exception):
                raise item
            yield item

    def close(self):
        self.closed = True


def event(text=None, reason=None, reasoning=None):
    return NS(choices=[NS(delta=NS(content=text, reasoning_content=reasoning), finish_reason=reason)])


def test_deep_stream_only_emits_answer_and_closes(client):
    stream = Stream([event(reasoning='hidden thoughts'), NS(choices=[]), event('Evidence '), event('[chunk_1]', 'stop')])
    client.chat.completions.create.return_value = stream
    assert ''.join(deep.stream_deep_rag_answer('q', [])) == 'Evidence [chunk_1]'
    assert stream.closed


def test_partial_stream_is_marked_not_replaced(client):
    stream = Stream([event('A partial answer'), TimeoutError('mock timeout')])
    client.chat.completions.create.return_value = stream
    assert ''.join(deep.stream_deep_rag_answer('q', [])) == 'A partial answer' + deep.INTERRUPTION_NOTICE
    assert stream.closed
    assert client.chat.completions.create.call_count == 1


def test_error_before_output_allows_same_provider_fast_fallback(client):
    stream = Stream([TimeoutError('mock timeout')])
    client.chat.completions.create.return_value = stream
    assert list(deep.stream_deep_rag_answer('q', [])) == []
    assert stream.closed


def test_truncation_and_cancellation_are_explicit(client):
    stream = Stream([event('short', 'length')])
    client.chat.completions.create.return_value = stream
    assert ''.join(deep.stream_deep_rag_answer('q', [])) == 'short' + deep.TRUNCATION_NOTICE
    stream = Stream([event('first'), event('not consumed', 'stop')])
    client.chat.completions.create.return_value = stream
    output = deep.stream_deep_rag_answer('q', [])
    assert next(output) == 'first'
    output.close()
    assert stream.closed


def test_status_exposes_configuration_not_credentials_or_connectivity(monkeypatch):
    monkeypatch.setattr(settings, 'OPENAI_API_KEY', 'unit-secret-not-public')
    monkeypatch.setattr(settings, 'LLM_PROVIDER', 'deepseek')
    status = get_model_status()
    assert status['configured'] is True
    assert status['connectivity_verified'] is False
    assert status['modes']['deep']['thinking'] is True
    serialized = json.dumps(status)
    assert 'unit-secret-not-public' not in serialized
    assert 'api_key' not in serialized.lower()
    assert 'base_url' not in serialized.lower()


def test_vision_requires_independent_explicit_configuration(monkeypatch):
    from rag.openai_client import get_vision_client
    monkeypatch.setattr(settings, 'VISION_API_KEY', '')
    monkeypatch.setattr(settings, 'VISION_BASE_URL', '')
    monkeypatch.setattr(settings, 'VISION_MODEL', '')
    assert get_vision_client() is None


def test_blank_deepseek_endpoint_cannot_send_its_key_to_openai(tmp_path):
    data = configured_settings(tmp_path, DEEPSEEK_API_KEY='unit-deepseek',
                               DEEPSEEK_BASE_URL=' ', DEEPSEEK_MODEL=' ',
                               OPENAI_BASE_URL='https://unrelated.example.invalid')
    assert data['base'] == 'https://api.deepseek.com'
    assert data['model'] == 'deepseek-v4-pro'
