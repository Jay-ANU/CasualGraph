"""Vector retrieval helpers for per-user long-term memories."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from configs.settings import PINECONE_NAMESPACE, VECTOR_DIR, VECTOR_STORE_PROVIDER
from rag.embeddings import embed_query, embed_texts
from rag.pinecone_store import (
    EmbeddingDimensionMismatchError,
    delete_vectors_by_ids,
    pinecone_available,
    query_vectors,
    upsert_vectors,
)


DEFAULT_MEMORY_VECTOR_LIMIT = 8
MEMORY_RECORD_TYPE = "user_memory"


def memory_vectors_enabled() -> bool:
    return os.getenv("USER_MEMORY_VECTOR_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def memory_vector_backend() -> str:
    configured = os.getenv("USER_MEMORY_VECTOR_PROVIDER", VECTOR_STORE_PROVIDER).strip().lower()
    if configured == "pinecone" and pinecone_available():
        return "pinecone"
    return "local"


def memory_vector_namespace() -> str:
    return os.getenv("USER_MEMORY_VECTOR_NAMESPACE", f"{PINECONE_NAMESPACE}-memory").strip() or "user-memory"


def memory_vector_id(user_id: str, memory_id: str) -> str:
    raw = f"{str(user_id).strip()}:{str(memory_id).strip()}".encode("utf-8")
    return f"memory:{hashlib.sha256(raw).hexdigest()}"


def upsert_memory_vector(memory: Dict[str, Any]) -> bool:
    if not memory_vectors_enabled():
        return False
    user_id = str(memory.get("user_id") or "").strip()
    memory_id = str(memory.get("id") or "").strip()
    content = str(memory.get("content") or "").strip()
    if not user_id or not memory_id or not content:
        return False

    vector_id = memory_vector_id(user_id, memory_id)
    text = _memory_embedding_text(memory)
    values = embed_texts([text])[0]
    metadata = _memory_metadata(memory, vector_id=vector_id)

    if memory_vector_backend() == "pinecone":
        upsert_vectors(
            vectors=[{"id": vector_id, "values": values, "metadata": metadata}],
            namespace=memory_vector_namespace(),
        )
        return True

    _upsert_local_vector(user_id, {"id": vector_id, "values": values, "metadata": metadata})
    return True


def delete_memory_vector(user_id: str, memory_id: str) -> bool:
    if not memory_vectors_enabled():
        return False
    normalized_user_id = str(user_id or "").strip()
    normalized_memory_id = str(memory_id or "").strip()
    if not normalized_user_id or not normalized_memory_id:
        return False

    vector_id = memory_vector_id(normalized_user_id, normalized_memory_id)
    if memory_vector_backend() == "pinecone":
        delete_vectors_by_ids([vector_id], namespace=memory_vector_namespace())
        return True

    return _delete_local_vector(normalized_user_id, vector_id)


def query_memory_vectors(user_id: str, query: str, *, limit: int = DEFAULT_MEMORY_VECTOR_LIMIT) -> List[Dict[str, Any]]:
    if not memory_vectors_enabled():
        return []
    normalized_user_id = str(user_id or "").strip()
    normalized_query = str(query or "").strip()
    if not normalized_user_id or not normalized_query:
        return []

    top_k = max(1, min(30, int(limit or DEFAULT_MEMORY_VECTOR_LIMIT)))
    vector = embed_query(normalized_query)
    if memory_vector_backend() == "pinecone":
        try:
            return _query_pinecone_memory_vectors(normalized_user_id, vector, top_k)
        except EmbeddingDimensionMismatchError:
            return []

    return _query_local_memory_vectors(normalized_user_id, vector, top_k)


def _memory_embedding_text(memory: Dict[str, Any]) -> str:
    category = str(memory.get("category") or "profile").strip()
    content = str(memory.get("content") or "").strip()
    evidence = str(memory.get("evidence") or "").strip()
    origin = str(memory.get("origin") or "inferred").strip()
    return "\n".join(
        line
        for line in (
            f"Category: {category}",
            f"Memory: {content}",
            f"Origin: {origin}",
            f"Evidence: {evidence}" if evidence else "",
        )
        if line
    )


def _memory_metadata(memory: Dict[str, Any], *, vector_id: str) -> Dict[str, Any]:
    return {
        "record_type": MEMORY_RECORD_TYPE,
        "owner_user_id": str(memory.get("user_id") or "").strip(),
        "memory_id": str(memory.get("id") or "").strip(),
        "category": str(memory.get("category") or "profile").strip(),
        "content": str(memory.get("content") or "").strip(),
        "evidence": str(memory.get("evidence") or "").strip(),
        "source": str(memory.get("source") or "chat").strip(),
        "origin": str(memory.get("origin") or "inferred").strip(),
        "sensitivity": str(memory.get("sensitivity") or "normal").strip(),
        "confidence": float(memory.get("confidence") or 0.0),
        "updated_at": str(memory.get("updated_at") or "").strip(),
        "vector_id": vector_id,
    }


def _query_pinecone_memory_vectors(user_id: str, vector: List[float], top_k: int) -> List[Dict[str, Any]]:
    metadata_filter = {
        "$and": [
            {"record_type": {"$eq": MEMORY_RECORD_TYPE}},
            {"owner_user_id": {"$eq": user_id}},
        ]
    }
    rows = query_vectors(
        vector=vector,
        top_k=top_k,
        namespace=memory_vector_namespace(),
        metadata_filter=metadata_filter,
    )
    hits = []
    for row in rows:
        hit = _normalize_hit(row)
        if hit.get("memory_id"):
            hits.append(hit)
    return hits


def _query_local_memory_vectors(user_id: str, vector: List[float], top_k: int) -> List[Dict[str, Any]]:
    rows = _read_local_vectors(user_id)
    hits = []
    for row in rows:
        metadata = dict(row.get("metadata") or {})
        if metadata.get("record_type") != MEMORY_RECORD_TYPE:
            continue
        if str(metadata.get("owner_user_id") or "") != user_id:
            continue
        score = _cosine(vector, row.get("values") or [])
        if score <= 0.000001:
            continue
        hit = _normalize_hit({**metadata, "id": row.get("id"), "score": score})
        hits.append(hit)
    hits.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return hits[:top_k]


def _normalize_hit(row: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(row or {})
    normalized["memory_id"] = str(normalized.get("memory_id") or "").strip()
    normalized["score"] = float(normalized.get("score") or 0.0)
    return normalized


def _cosine(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _memory_vector_dir() -> Path:
    configured = os.getenv("USER_MEMORY_VECTOR_DIR", "").strip()
    path = Path(configured).expanduser() if configured else VECTOR_DIR / "user_memories"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _local_vector_file(user_id: str) -> Path:
    digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()
    return _memory_vector_dir() / f"{digest}.json"


def _read_local_vectors(user_id: str) -> List[Dict[str, Any]]:
    path = _local_vector_file(user_id)
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return rows if isinstance(rows, list) else []


def _write_local_vectors(user_id: str, rows: List[Dict[str, Any]]) -> None:
    path = _local_vector_file(user_id)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _upsert_local_vector(user_id: str, row: Dict[str, Any]) -> None:
    rows = [item for item in _read_local_vectors(user_id) if item.get("id") != row.get("id")]
    rows.append(row)
    _write_local_vectors(user_id, rows)


def _delete_local_vector(user_id: str, vector_id: str) -> bool:
    rows = _read_local_vectors(user_id)
    next_rows = [item for item in rows if item.get("id") != vector_id]
    if len(next_rows) == len(rows):
        return False
    _write_local_vectors(user_id, next_rows)
    return True
