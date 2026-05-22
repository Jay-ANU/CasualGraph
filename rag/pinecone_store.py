"""Pinecone-backed vector store helpers."""

from __future__ import annotations

from typing import Dict, List, Optional

try:
    from pinecone import Pinecone  # type: ignore
except Exception:
    Pinecone = None

from configs.settings import (
    PINECONE_API_KEY,
    PINECONE_INDEX_HOST,
    PINECONE_INDEX_NAME,
    PINECONE_NAMESPACE,
    PINECONE_UPSERT_BATCH_SIZE,
)


_PINECONE_INDEX = None
_PINECONE_CACHE_KEY = None


class EmbeddingDimensionMismatchError(RuntimeError):
    """Raised when Pinecone is selected but embeddings have degraded dimensions."""


class PineconePayloadTooLargeError(RuntimeError):
    """Raised when Pinecone rejects a request/response above its message limit."""


def pinecone_available() -> bool:
    return Pinecone is not None


def get_pinecone_index():
    """Return a cached Pinecone index client."""
    global _PINECONE_INDEX, _PINECONE_CACHE_KEY

    if Pinecone is None:
        raise RuntimeError("Pinecone SDK is not installed. Add `pinecone` to your environment first.")
    if not PINECONE_API_KEY:
        raise RuntimeError("PINECONE_API_KEY is not set.")
    if not PINECONE_INDEX_HOST and not PINECONE_INDEX_NAME:
        raise RuntimeError("Set PINECONE_INDEX_HOST or PINECONE_INDEX_NAME to target a Pinecone index.")

    cache_key = f"{PINECONE_INDEX_HOST}|{PINECONE_INDEX_NAME}"
    if _PINECONE_INDEX is not None and _PINECONE_CACHE_KEY == cache_key:
        return _PINECONE_INDEX

    client = Pinecone(api_key=PINECONE_API_KEY)
    if PINECONE_INDEX_HOST:
        index = client.Index(host=PINECONE_INDEX_HOST)
    else:
        index = client.Index(PINECONE_INDEX_NAME)

    _PINECONE_INDEX = index
    _PINECONE_CACHE_KEY = cache_key
    return index


def upsert_vectors(vectors: List[Dict], namespace: Optional[str] = None) -> None:
    """Upsert vectors into Pinecone.

    Refuses to write when the embedding backend has degraded to the hash
    fallback. Hash vectors are dimension-mismatched garbage from Pinecone's
    perspective and will either 400 immediately or silently corrupt the
    index — fail fast at the source instead.
    """
    from rag.embeddings import get_embedding_backend

    backend = get_embedding_backend()
    if backend.startswith("hash-fallback"):
        raise RuntimeError(
            f"Refusing to upsert to Pinecone: embedding backend is {backend!r}. "
            "The real model failed to load (check stderr for the underlying SentenceTransformer error). "
            "Fix the model load (set ESG_EMBEDDING_ALLOW_DOWNLOAD=true once, or repair ./models/BAAI_bge-m3) "
            "before running ingestion against Pinecone."
        )
    index = get_pinecone_index()
    target_namespace = namespace or PINECONE_NAMESPACE
    for batch in _iter_batches(vectors, PINECONE_UPSERT_BATCH_SIZE):
        index.upsert(vectors=batch, namespace=target_namespace)


def delete_vectors_by_document_id(document_id: str, namespace: Optional[str] = None) -> None:
    """Best-effort deletion for one document's vectors."""
    index = get_pinecone_index()
    target_namespace = namespace or PINECONE_NAMESPACE
    index.delete(filter={"document_id": {"$eq": document_id}}, namespace=target_namespace)


def delete_vectors_by_ids(ids: List[str], namespace: Optional[str] = None) -> None:
    """Best-effort deletion for explicit vector IDs."""
    vector_ids = [str(item).strip() for item in ids if str(item or "").strip()]
    if not vector_ids:
        return
    index = get_pinecone_index()
    target_namespace = namespace or PINECONE_NAMESPACE
    index.delete(ids=vector_ids, namespace=target_namespace)


def query_vectors(
    vector: List[float],
    top_k: int,
    namespace: Optional[str] = None,
    metadata_filter: Optional[Dict] = None,
) -> List[Dict]:
    """Query Pinecone and normalize the matches list."""
    from rag.embeddings import embedding_backend_is_real, get_embedding_backend

    if not embedding_backend_is_real():
        raise EmbeddingDimensionMismatchError(
            f"Embedding backend degraded: {get_embedding_backend()}. Skip Pinecone vector lookup."
        )
    index = get_pinecone_index()
    target_namespace = namespace or PINECONE_NAMESPACE
    try:
        response = index.query(
            vector=vector,
            top_k=top_k,
            namespace=target_namespace,
            include_metadata=True,
            filter=metadata_filter,
        )
    except Exception as exc:
        if _looks_like_payload_too_large(exc):
            raise PineconePayloadTooLargeError(
                f"Pinecone message size limit exceeded for top_k={top_k}; reduce PINECONE_QUERY_TOP_K_CAP."
            ) from exc
        raise

    matches = []
    for match in getattr(response, "matches", []) or []:
        metadata = getattr(match, "metadata", None) or {}
        row = dict(metadata)
        row["score"] = float(getattr(match, "score", 0.0))
        row["id"] = getattr(match, "id", "")
        matches.append(row)
    return matches


def _iter_batches(items: List[Dict], batch_size: int):
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def _looks_like_payload_too_large(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "message length too large" in message
        or "decoded message length too large" in message
        or "limit is: 4194304" in message
    )
