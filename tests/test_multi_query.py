from unittest.mock import patch

from rag.retriever import retrieve_context, retrieve_context_multi


def _row(document_id, chunk_id, text, score=1.0):
    return {"document_id": document_id, "chunk_id": chunk_id, "text": text, "score": score}


def test_multi_query_rrf_dedupes_and_ranks():
    def fake_search(query, top_k, filters=None):
        if query == "q1":
            return [_row("d1", "c1", "alpha"), _row("d1", "c2", "beta")]
        return [_row("d1", "c2", "beta"), _row("d1", "c3", "gamma")]

    with patch("rag.retriever.search", side_effect=fake_search), patch("rag.retriever.RAG_HYBRID_ENABLED", False):
        results = retrieve_context_multi(["q1", "q2"], top_k=3)

    assert [item["chunk_id"] for item in results] == ["c2", "c1", "c3"]
    assert results[0]["fusion_score"] > results[1]["fusion_score"]


def test_single_query_path_calls_vector_once():
    with patch("rag.retriever.search", return_value=[_row("d1", "c1", "alpha")]) as mocked:
        results = retrieve_context("plain", top_k=1)

    assert results[0]["chunk_id"] == "c1"
    assert mocked.call_count == 1
