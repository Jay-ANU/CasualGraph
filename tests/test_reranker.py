from __future__ import annotations

from unittest.mock import patch

import rag.reranker as reranker


class _FakeReranker:
    def rerank(self, query, candidates, top_k):
        scored = []
        for item in candidates:
            row = dict(item)
            row["rerank_score"] = float(row["score"])
            scored.append(row)
        return sorted(scored, key=lambda item: item["rerank_score"], reverse=True)[:top_k]


def test_rerank_candidates_if_enabled_reorders_candidates(monkeypatch):
    monkeypatch.setattr(reranker, "RERANKER_ENABLED", True)
    monkeypatch.setattr(reranker, "RERANKER_TOP_K_BEFORE", 3)
    monkeypatch.setattr(reranker, "RERANKER_TOP_K_AFTER", 2)
    candidates = [
        {"chunk_id": "low", "text": "alpha", "score": 0.1},
        {"chunk_id": "high", "text": "alpha", "score": 0.9},
        {"chunk_id": "mid", "text": "alpha", "score": 0.5},
    ]

    with patch("rag.reranker._get_reranker", return_value=_FakeReranker()):
        results = reranker.rerank_candidates_if_enabled("alpha", candidates, top_k=2)

    assert [item["chunk_id"] for item in results] == ["high", "mid"]
    assert results[0]["rerank_score"] == 0.9


def test_rerank_candidates_falls_back_on_model_error(monkeypatch):
    monkeypatch.setattr(reranker, "RERANKER_ENABLED", True)
    monkeypatch.setattr(reranker, "RERANKER_TOP_K_BEFORE", 3)
    candidates = [
        {"chunk_id": "first", "text": "alpha"},
        {"chunk_id": "second", "text": "alpha"},
    ]

    with patch("rag.reranker._get_reranker", side_effect=RuntimeError("model missing")):
        results = reranker.rerank_candidates_if_enabled("alpha", candidates, top_k=1)

    assert results == [candidates[0]]


def test_rerank_candidates_disabled_is_noop(monkeypatch):
    monkeypatch.setattr(reranker, "RERANKER_ENABLED", False)
    candidates = [
        {"chunk_id": "first", "text": "alpha"},
        {"chunk_id": "second", "text": "alpha"},
    ]

    assert reranker.rerank_candidates_if_enabled("alpha", candidates, top_k=1) == [candidates[0]]
