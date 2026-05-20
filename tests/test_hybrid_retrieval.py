from unittest.mock import patch

from rag.pinecone_store import EmbeddingDimensionMismatchError, PineconePayloadTooLargeError
from rag.retriever import retrieve_hybrid
import rag.retriever as retriever


def test_hybrid_falls_back_when_bm25_missing():
    vector_rows = [{"document_id": "d1", "chunk_id": "c1", "text": "alpha", "score": 0.9}]

    with patch("rag.retriever.search", return_value=vector_rows), patch(
        "rag.retriever.search_bm25", side_effect=FileNotFoundError("missing")
    ):
        results = retrieve_hybrid("alpha", top_k=1)

    assert results[0]["chunk_id"] == "c1"
    assert results[0]["fusion_method"] == "vector_only_bm25_missing"


def test_hybrid_falls_back_to_bm25_when_embeddings_degraded():
    bm25_rows = [{"document_id": "d2", "chunk_id": "c2", "text": "beta", "bm25_score": 7.5, "score": 7.5}]

    with patch("rag.retriever.search", side_effect=EmbeddingDimensionMismatchError("degraded")), patch(
        "rag.retriever.search_bm25", return_value=bm25_rows
    ):
        results = retrieve_hybrid("beta", top_k=1)

    assert results[0]["chunk_id"] == "c2"
    assert results[0]["fusion_method"] == "bm25_only_degraded_embeddings"


def test_single_query_retrieve_falls_back_to_bm25_when_embeddings_degraded():
    bm25_rows = [{"document_id": "d3", "chunk_id": "c3", "text": "gamma", "bm25_score": 4.2, "score": 4.2}]

    with patch("rag.retriever.RAG_HYBRID_ENABLED", False), patch(
        "rag.retriever.search", side_effect=EmbeddingDimensionMismatchError("degraded")
    ), patch("rag.retriever.search_bm25", return_value=bm25_rows):
        results = retriever._single_query_retrieve("gamma", top_k=1, filters=None)

    assert results[0]["chunk_id"] == "c3"
    assert results[0]["fusion_method"] == "bm25_only_degraded_embeddings"


def test_single_query_retrieve_falls_back_to_bm25_when_pinecone_payload_is_too_large():
    bm25_rows = [{"document_id": "d4", "chunk_id": "c4", "text": "delta", "bm25_score": 3.1, "score": 3.1}]

    with patch("rag.retriever.RAG_HYBRID_ENABLED", False), patch(
        "rag.retriever.search", side_effect=PineconePayloadTooLargeError("too large")
    ), patch("rag.retriever.search_bm25", return_value=bm25_rows):
        results = retriever._single_query_retrieve("delta", top_k=1, filters=None)

    assert results[0]["chunk_id"] == "c4"
    assert results[0]["fusion_method"] == "bm25_only_pinecone_payload_too_large"


def test_single_query_retrieve_retries_smaller_vector_query_before_bm25_fallback():
    vector_rows = [{"document_id": "d5", "chunk_id": "c5", "text": "epsilon", "score": 0.8}]

    with patch("rag.retriever.RAG_HYBRID_ENABLED", False), patch(
        "rag.retriever.search",
        side_effect=[PineconePayloadTooLargeError("too large"), vector_rows],
    ) as search_mock, patch("rag.retriever.search_bm25") as bm25_mock:
        results = retriever._single_query_retrieve("epsilon", top_k=8, filters=None)

    assert results[0]["chunk_id"] == "c5"
    assert results[0]["retrieval_retry"] == "pinecone_top_k_reduced"
    assert search_mock.call_args_list[0].kwargs["top_k"] == 8
    assert search_mock.call_args_list[1].kwargs["top_k"] == 4
    bm25_mock.assert_not_called()


def test_rrf_term_coverage_can_promote_more_relevant_chunk():
    irrelevant = {"document_id": "d1", "chunk_id": "c1", "text": "general governance overview"}
    relevant = {"document_id": "d2", "chunk_id": "c2", "text": "scope emissions reduction target"}

    with patch("rag.retriever.RAG_RRF_TERM_BOOST", 0.1), patch("rag.retriever.RAG_RRF_DIVERSITY_PENALTY", 0.0):
        results = retriever._rrf_fusion(
            [[irrelevant, relevant]],
            top_k=2,
            fusion_method="rrf_test",
            query="scope emissions",
        )

    assert [item["chunk_id"] for item in results] == ["c2", "c1"]
    assert results[0]["term_coverage"] == 1.0


def test_rrf_channel_weights_affect_rank_order():
    vector_row = {"document_id": "d1", "chunk_id": "vector", "text": "alpha"}
    bm25_row = {"document_id": "d2", "chunk_id": "bm25", "text": "alpha"}

    with patch("rag.retriever.RAG_RRF_TERM_BOOST", 0.0), patch("rag.retriever.RAG_RRF_DIVERSITY_PENALTY", 0.0):
        results = retriever._rrf_fusion(
            [[vector_row], [bm25_row]],
            top_k=2,
            fusion_method="rrf_test",
            labels=["vector", "bm25"],
            channel_weights=[2.0, 1.0],
        )

    assert [item["chunk_id"] for item in results] == ["vector", "bm25"]
    assert results[0]["fusion_channels"] == ["vector"]
