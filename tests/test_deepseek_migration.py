"""Offline migration contract tests; no production credentials or services used."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from configs.deepseek_config import load_deepseek_config
from rag.openai_compat import chat_token_kwargs

ROOT = Path(__file__).resolve().parents[1]


def test_default_profile_and_secret_redaction():
    config = load_deepseek_config({"DEEPSEEK_API_KEY": "test-secret"})
    assert config.model == "deepseek-v4-pro"
    assert config.base_url == "https://api.deepseek.com"
    assert config.anthropic_base_url == "https://api.deepseek.com/anthropic"
    assert config.configured
    assert "test-secret" not in repr(config)


@pytest.mark.parametrize("suffix", ["", "/", "/v1", "/v1/", "/anthropic", "/anthropic/"])
def test_endpoint_normalization(suffix):
    config = load_deepseek_config({"DEEPSEEK_BASE_URL": "https://api.deepseek.com" + suffix})
    assert config.base_url == "https://api.deepseek.com"
    assert config.anthropic_base_url == "https://api.deepseek.com/anthropic"


@pytest.mark.parametrize("value", ["http://api.deepseek.com", "https://user:secret@example.com", "https://api.deepseek.com?key=secret", "https://api.deepseek.com#fragment", "not-a-url"])
def test_reject_unsafe_urls(value):
    with pytest.raises(ValueError):
        load_deepseek_config({"DEEPSEEK_BASE_URL": value})


def test_local_proxy_and_explicit_compat_endpoint():
    config = load_deepseek_config({"DEEPSEEK_BASE_URL": "http://127.0.0.1:8001/v1", "DEEPSEEK_ANTHROPIC_BASE_URL": "http://127.0.0.1:8002/anthropic"})
    assert config.base_url == "http://127.0.0.1:8001"
    assert config.anthropic_base_url == "http://127.0.0.1:8002/anthropic"


@pytest.mark.parametrize("model", ["claude-opus-4-7", "gpt-4", "deepseek-v4-pr0", "deepseek-chat"])
def test_no_silent_model_mapping(model):
    with pytest.raises(ValueError):
        load_deepseek_config({"DEEPSEEK_MODEL": model})


def test_missing_deepseek_key_never_uses_legacy_keys():
    config = load_deepseek_config({"OPENAI_API_KEY": "old-openai", "ANTHROPIC_API_KEY": "old-claude"})
    assert not config.configured
    assert not config.api_key


@pytest.mark.parametrize("key", ["", "new-deepseek-key"])
def test_settings_aliases_override_stale_provider_configuration(tmp_path, key):
    code = '''
import json
import dotenv
dotenv.load_dotenv = lambda *args, **kwargs: False
from configs import settings as s
names = ["OPENAI_MODEL", "RAG_FLASH_MODEL", "RAG_DEEP_MODEL", "HYDE_MODEL", "RAG_PREDICTION_MODEL", "DEEPSEEK_EXTRACTION_MODEL", "RAG_ROUTER_MODEL", "RAG_ANSWER_INTENT_ROUTER_MODEL", "RAG_HYBRID_AGENT_ROUTER_MODEL"]
print(json.dumps({"models": [getattr(s, name) for name in names], "openai_key": s.OPENAI_API_KEY, "anthropic_key": s.ANTHROPIC_API_KEY, "bases": [s.OPENAI_BASE_URL, s.ANTHROPIC_BASE_URL], "configured": [s.openai_configured(), s.anthropic_configured(), s.deepseek_configured()], "embedding": s.EMBEDDING_MODEL, "tokens": [s.OPENAI_MAX_TOKENS, s.RAG_DEEP_MAX_TOKENS]}))
'''
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT), "DATA_DIR": str(tmp_path), "DEEPSEEK_API_KEY": key, "OPENAI_API_KEY": "old-openai", "ANTHROPIC_API_KEY": "old-claude", "OPENAI_BASE_URL": "https://api.openai.com/v1", "ANTHROPIC_BASE_URL": "https://api.anthropic.com", "OPENAI_MODEL": "gpt-4", "RAG_DEEP_MODEL": "claude-opus-4-7", "HYDE_MODEL": "gpt-5.4-mini", "RAG_ROUTER_MODEL": "deepseek-v4-flash"}
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    data = json.loads(result.stdout)
    assert set(data["models"]) == {"deepseek-v4-pro"}
    assert data["openai_key"] == data["anthropic_key"] == key
    assert data["bases"] == ["https://api.deepseek.com", "https://api.deepseek.com/anthropic"]
    assert data["configured"] == [bool(key)] * 3
    assert data["embedding"] == "BAAI/bge-m3"
    assert data["tokens"] == [2048, 8192]


def test_flash_parameters_disable_reasoning_and_keep_visible_budget():
    assert chat_token_kwargs("deepseek-v4-pro", 200) == {"max_tokens": 200, "extra_body": {"thinking": {"type": "disabled"}}}
    assert chat_token_kwargs("gpt-5", 200) == {"max_completion_tokens": 200}
    assert chat_token_kwargs("gpt-4", 200) == {"max_tokens": 200}


@pytest.mark.parametrize("module_name,sdk_name,constructor_name", [("rag.openai_client", "openai", "OpenAI"), ("rag.anthropic_client", "anthropic", "Anthropic")])
def test_transports_are_explicit_and_bounded(monkeypatch, module_name, sdk_name, constructor_name):
    import importlib
    factory = importlib.import_module(module_name)
    constructor = MagicMock()
    monkeypatch.setitem(sys.modules, sdk_name, SimpleNamespace(**{constructor_name: constructor}))
    factory._build_client.cache_clear()
    base = "https://api.deepseek.com" + ("/anthropic" if sdk_name == "anthropic" else "")
    factory._build_client("test-key", base, 120)
    constructor.assert_called_once_with(api_key="test-key", base_url=base, timeout=120, max_retries=factory.DEEPSEEK_MAX_RETRIES)
    assert 0 <= factory.DEEPSEEK_MAX_RETRIES <= 3
    with pytest.raises(ValueError):
        factory._build_client("test-key", "", 120)
    factory._build_client.cache_clear()


@pytest.fixture
def deep_client(monkeypatch):
    from rag import claude_answering as deep
    client = MagicMock()
    monkeypatch.setattr(deep, "claude_answering_available", lambda: True)
    monkeypatch.setattr(deep, "get_anthropic_client", lambda: client)
    return deep, client


def test_deep_sync_preserves_source_blocks_and_uses_pro(deep_client):
    deep, client = deep_client
    client.messages.create.return_value = SimpleNamespace(content=[SimpleNamespace(text="Supported [chunk_0].")], stop_reason="end_turn")
    answer = deep.generate_claude_deep_rag_answer("What changed?", [{"chunk_id": "chunk_0", "text": "Current passage"}], history_block="History", priors=[{"chunk_id": "prior_0", "text": "Prior passage"}], regulatory=[{"chunk_id": "reg_0", "text": "Regulation"}], graph_context="[G_0] related entity")
    assert answer == "Supported [chunk_0]."
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "deepseek-v4-pro"
    assert kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
    payload = kwargs["messages"][0]["content"]
    for expected in ["[chunk_0]", "[prior_0]", "[reg_0]", "[G_0]", "History"]:
        assert expected in payload


def test_deep_sync_failure_keeps_existing_fallback_contract(deep_client):
    deep, client = deep_client
    client.messages.create.side_effect = TimeoutError("private provider details")
    assert deep.generate_claude_deep_rag_answer("Question", []) is None


def test_deep_sync_reports_truncation(deep_client):
    deep, client = deep_client
    client.messages.create.return_value = SimpleNamespace(content=[SimpleNamespace(text="Partial")], stop_reason="max_tokens")
    assert "truncated" in deep.generate_claude_deep_rag_answer("Question", [])


def test_deep_stream_preserves_text_and_closes(deep_client):
    deep, client = deep_client
    manager = client.messages.stream.return_value
    stream = manager.__enter__.return_value
    stream.text_stream = iter(["Supported ", "[chunk_0]."])
    stream.get_final_message.return_value = SimpleNamespace(stop_reason="end_turn")
    assert list(deep.stream_claude_deep_rag_answer("Question", [])) == ["Supported ", "[chunk_0]."]
    manager.__exit__.assert_called_once()


def test_failure_before_first_token_allows_flash_fallback(deep_client):
    deep, client = deep_client
    client.messages.stream.side_effect = TimeoutError()
    assert list(deep.stream_claude_deep_rag_answer("Question", [])) == []


def test_interrupted_stream_is_not_silently_complete(deep_client):
    deep, client = deep_client
    def tokens():
        yield "Partial [chunk_0]"
        raise ConnectionError("private diagnostics")
    manager = client.messages.stream.return_value
    manager.__enter__.return_value.text_stream = tokens()
    chunks = list(deep.stream_claude_deep_rag_answer("Question", []))
    assert chunks[0] == "Partial [chunk_0]"
    assert "incomplete" in chunks[-1]
    assert "private diagnostics" not in "".join(chunks)
    manager.__exit__.assert_called_once()


@pytest.mark.parametrize("intent", ["evidence", "general", "hybrid"])
def test_answer_intent_contracts_are_retained(intent):
    from rag import claude_answering as deep
    payload = deep._build_claude_request(question="Question", sources=[], priors=None, regulatory=None, graph_context=None, history_block="", answer_intent=intent)
    user = payload["messages"][0]["content"]
    if intent == "evidence":
        assert "No relevant report excerpts" in user
    elif intent == "general":
        assert "do not cite uploaded-report markers" in user
    else:
        assert "General analysis" in user


def test_openai_wire_contract_with_mock_http():
    openai = pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")
    def handler(request):
        assert request.url.host == "api.deepseek.com"
        assert request.headers["authorization"] == "Bearer test-only"
        data = json.loads(request.content)
        assert data["model"] == "deepseek-v4-pro"
        assert data["thinking"] == {"type": "disabled"}
        return httpx.Response(200, json={"id": "test-completion", "object": "chat.completion", "created": 0, "model": data["model"], "choices": [{"index": 0, "message": {"role": "assistant", "content": "Evidence [chunk_0]"}, "finish_reason": "stop"}]})
    with openai.OpenAI(api_key="test-only", base_url="https://api.deepseek.com", http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        response = client.chat.completions.create(model="deepseek-v4-pro", messages=[{"role": "user", "content": "Test"}], **chat_token_kwargs("deepseek-v4-pro", 200))
    assert response.choices[0].message.content == "Evidence [chunk_0]"


def test_anthropic_wire_contract_with_mock_http():
    anthropic = pytest.importorskip("anthropic")
    httpx = pytest.importorskip("httpx")
    def handler(request):
        assert request.url.host == "api.deepseek.com"
        assert request.url.path == "/anthropic/v1/messages"
        assert request.headers["x-api-key"] == "test-only"
        body = json.loads(request.content)
        assert body["model"] == "deepseek-v4-pro"
        assert body["thinking"] == {"type": "enabled"}
        return httpx.Response(200, json={"id": "test-message", "type": "message", "role": "assistant", "model": body["model"], "content": [{"type": "text", "text": "Evidence [chunk_0]"}], "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})
    from rag.claude_answering import _messages_kwargs
    with anthropic.Anthropic(api_key="test-only", base_url="https://api.deepseek.com/anthropic", http_client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        response = client.messages.create(**_messages_kwargs({"system": "Test", "messages": [{"role": "user", "content": "Test"}]}))
    assert response.content[0].text == "Evidence [chunk_0]"
