from __future__ import annotations

from unittest.mock import patch

import rag.hyde as hyde
from rag import retriever


def test_maybe_generate_hyde_query_disabled(monkeypatch):
    monkeypatch.setattr(hyde, "HYDE_ENABLED", False)

    result = hyde.maybe_generate_hyde_query("scope 1")

    assert result["enabled"] is False
    assert result["query"] == "scope 1"
    assert result["backend"] == "disabled"


def test_maybe_generate_hyde_query_caches_success(monkeypatch):
    monkeypatch.setattr(hyde, "HYDE_ENABLED", True)
    monkeypatch.setattr(hyde, "HYDE_MIN_CHARS", 5)
    hyde._hyde_cache.clear()

    with patch("rag.hyde.generate_hypothetical_doc", return_value="A detailed ESG report passage about Scope 1 emissions.") as generate:
        first = hyde.maybe_generate_hyde_query("scope 1")
        second = hyde.maybe_generate_hyde_query("scope 1")

    assert first["enabled"] is True
    assert first["query"].startswith("A detailed ESG")
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    generate.assert_called_once()


def test_maybe_generate_hyde_query_too_short_falls_back(monkeypatch):
    monkeypatch.setattr(hyde, "HYDE_ENABLED", True)
    monkeypatch.setattr(hyde, "HYDE_MIN_CHARS", 50)
    hyde._hyde_cache.clear()

    with patch("rag.hyde.generate_hypothetical_doc", return_value="too short"):
        result = hyde.maybe_generate_hyde_query("scope 1")

    assert result["enabled"] is False
    assert result["query"] == "scope 1"
    assert result["backend"] == "too_short"


def test_hybrid_uses_hyde_for_vector_and_original_query_for_bm25(monkeypatch):
    monkeypatch.setattr(retriever, "RAG_HYBRID_FUSION", "rrf")
    seen = {"vector": [], "bm25": []}

    def fake_vector(query, top_k, filters):
        seen["vector"].append(query)
        return [{"chunk_id": "v1", "document_id": "doc", "text": "vector", "score": 0.8}]

    def fake_bm25(query, top_k, filters):
        seen["bm25"].append(query)
        return [{"chunk_id": "b1", "document_id": "doc", "text": "bm25", "bm25_score": 1.0}]

    with patch("rag.retriever.maybe_generate_hyde_query", return_value={
        "query": "expanded hypothetical passage",
        "hyde_text": "expanded hypothetical passage",
        "enabled": True,
        "backend": "openai",
        "cache_hit": False,
        "hyde_ms": 12.0,
    }), patch("rag.retriever._search_with_payload_retry", side_effect=fake_vector), patch(
        "rag.retriever.search_bm25", side_effect=fake_bm25
    ):
        results = retriever.retrieve_hybrid("scope 1", top_k=2)

    assert seen["vector"] == ["expanded hypothetical passage"]
    assert seen["bm25"] == ["scope 1"]
    assert all(item["hyde_used"] for item in results)
    assert results[0]["hyde_ms"] == 12.0
