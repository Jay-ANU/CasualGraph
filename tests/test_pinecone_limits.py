from __future__ import annotations

from unittest.mock import patch

import pytest

import rag.pinecone_store as pinecone_store
import rag.vector_store as vector_store
from rag.pinecone_store import PineconePayloadTooLargeError, query_vectors, upsert_vectors


class _FakeIndex:
    def __init__(self):
        self.upsert_calls = []
        self.query_calls = []

    def upsert(self, *, vectors, namespace=None):
        self.upsert_calls.append((list(vectors), namespace))

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        raise Exception("Error, decoded message length too large: found 8151339 bytes, the limit is: 4194304 bytes")


def test_upsert_vectors_batches_pinecone_payloads(monkeypatch):
    fake_index = _FakeIndex()
    vectors = [{"id": str(i), "values": [0.1], "metadata": {"text": "x"}} for i in range(5)]
    monkeypatch.setattr(pinecone_store, "PINECONE_UPSERT_BATCH_SIZE", 2)

    with patch("rag.embeddings.get_embedding_backend", return_value="sentence-transformers:test"), patch(
        "rag.pinecone_store.get_pinecone_index", return_value=fake_index
    ):
        upsert_vectors(vectors, namespace="ns")

    assert [len(call[0]) for call in fake_index.upsert_calls] == [2, 2, 1]
    assert {call[1] for call in fake_index.upsert_calls} == {"ns"}


def test_query_vectors_converts_pinecone_message_limit_error():
    fake_index = _FakeIndex()

    with patch("rag.embeddings.embedding_backend_is_real", return_value=True), patch(
        "rag.pinecone_store.get_pinecone_index", return_value=fake_index
    ):
        with pytest.raises(PineconePayloadTooLargeError):
            query_vectors(vector=[0.1], top_k=99, namespace="ns")


def test_query_pinecone_branch_caps_expanded_top_k(monkeypatch):
    captured = {}

    def fake_query_vectors(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(vector_store, "PINECONE_QUERY_TOP_K_CAP", 7)

    with patch("rag.vector_store.query_vectors", side_effect=fake_query_vectors):
        vector_store._query_pinecone_branch(
            vector=[0.1],
            top_k=10,
            namespace="ns",
            filters={"domain": "academic"},
        )

    assert captured["top_k"] == 7
