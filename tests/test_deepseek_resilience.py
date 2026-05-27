import pytest

import rag.deepseek_resilience as resilience


@pytest.fixture(autouse=True)
def isolated_resilience_state(monkeypatch):
    monkeypatch.setattr(resilience, "_redis_available", lambda: False)
    resilience.reset_state()
    yield
    resilience.reset_state()


def test_cache_failure_short_circuits_same_payload(monkeypatch):
    monkeypatch.setattr(resilience, "DEEPSEEK_CACHE_ENABLED", True)
    monkeypatch.setattr(resilience, "DEEPSEEK_FAILURE_CACHE_TTL_SECONDS", 30)
    payload = {"query": "What is NVIDIA ESG strategy?", "candidates": ["nvidia"]}

    assert resilience.cache_lookup("document_resolver", payload) == (False, None)

    resilience.cache_failure("document_resolver", payload)

    assert resilience.cache_lookup("document_resolver", payload) == (True, None)


def test_circuit_opens_after_consecutive_failures(monkeypatch):
    monkeypatch.setattr(resilience, "DEEPSEEK_CIRCUIT_FAILURE_THRESHOLD", 2)
    monkeypatch.setattr(resilience, "DEEPSEEK_CIRCUIT_BREAK_SECONDS", 60)
    monkeypatch.setattr(resilience.time, "time", lambda: 1000.0)

    resilience.record_failure("answer_intent")
    assert not resilience.circuit_is_open("answer_intent")

    resilience.record_failure("answer_intent")
    assert resilience.circuit_is_open("answer_intent")


def test_success_resets_circuit(monkeypatch):
    monkeypatch.setattr(resilience, "DEEPSEEK_CIRCUIT_FAILURE_THRESHOLD", 1)
    monkeypatch.setattr(resilience, "DEEPSEEK_CIRCUIT_BREAK_SECONDS", 60)
    monkeypatch.setattr(resilience.time, "time", lambda: 1000.0)

    resilience.record_failure("hybrid_agent_router")
    assert resilience.circuit_is_open("hybrid_agent_router")

    resilience.record_success("hybrid_agent_router")
    assert not resilience.circuit_is_open("hybrid_agent_router")
