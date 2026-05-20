"""Provider-switchable vector store with local and Pinecone backends."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
import json
import os
import pickle
import math

import numpy as np

try:
    import faiss  # type: ignore
except Exception:
    faiss = None

from configs.settings import (
    ACTIVE_VECTOR_STORE_FILE,
    PINECONE_NAMESPACE,
    PINECONE_QUERY_TOP_K_CAP,
    VECTOR_DIR,
    VECTOR_STORE_PROVIDER,
    ensure_directories,
)
from rag.embeddings import embed_query, embed_texts
from rag.pinecone_store import pinecone_available, query_vectors, upsert_vectors


_LOADED_STORE = None
_LOADED_STORE_KEY = None


def build_vector_store(chunks: List[Dict], persist_path: str) -> None:
    """Build a vector store using the configured provider."""
    provider = _get_provider()
    if provider == "pinecone":
        _build_pinecone_store(chunks, persist_path)
        return
    _build_local_store(chunks, persist_path)


def load_vector_store(persist_path: Optional[str] = None):
    """Load the configured vector store from the active marker or explicit location."""
    global _LOADED_STORE, _LOADED_STORE_KEY
    ensure_directories()

    manifest = _read_active_manifest(persist_path)
    provider = manifest.get("provider", _get_provider())
    location = manifest.get("location", persist_path or "")
    namespace = manifest.get("namespace", PINECONE_NAMESPACE)
    document_id = manifest.get("document_id") or (Path(location).resolve().name if location else "")

    cache_key = json.dumps(
        {"provider": provider, "location": location, "namespace": namespace, "document_id": document_id},
        sort_keys=True,
    )
    if _LOADED_STORE is not None and _LOADED_STORE_KEY == cache_key:
        return _LOADED_STORE

    if provider == "pinecone":
        metadata = _load_pinecone_metadata(location)
        _LOADED_STORE = {
            "provider": provider,
            "metadata": metadata,
            "location": location,
            "namespace": namespace,
            "document_id": document_id,
        }
        _LOADED_STORE_KEY = cache_key
        return _LOADED_STORE

    path = Path(location).resolve()
    metadata_path = path / "metadata.json"
    index_path = path / "index.faiss"
    pickle_path = path / "index.pkl"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Vector store metadata missing under {path}")

    if faiss is not None and index_path.exists():
        index = faiss.read_index(str(index_path))
    elif pickle_path.exists():
        with open(pickle_path, "rb") as handle:
            index = pickle.load(handle)
    else:
        raise FileNotFoundError(f"Vector store index missing under {path}")

    with open(metadata_path, "r", encoding="utf-8") as handle:
        metadata = json.load(handle)

    _LOADED_STORE = {"provider": provider, "index": index, "metadata": metadata, "location": str(path)}
    _LOADED_STORE_KEY = cache_key
    return _LOADED_STORE


def search(
    query: str,
    top_k: int = 5,
    persist_path: Optional[str] = None,
    filters: Optional[Dict] = None,
) -> List[Dict]:
    """Search the current vector store and return top-k chunks with scores."""
    store = load_vector_store(persist_path)
    vector = np.array([embed_query(query)], dtype="float32")
    effective_filters = dict(filters or {})

    if store["provider"] == "pinecone":
        return _search_pinecone(
            vector=vector[0].tolist(),
            top_k=top_k,
            store=store,
            filters=effective_filters,
        )

    results = []
    local_filters = _strip_preference_filters(effective_filters)
    expanded_top_k = max(top_k * 8, 20) if local_filters else top_k
    if faiss is not None and hasattr(store["index"], "search"):
        scores, indices = store["index"].search(vector, expanded_top_k)
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(store["metadata"]):
                continue
            row = dict(store["metadata"][idx])
            row["score"] = float(score)
            results.append(row)
        if local_filters:
            results = _apply_local_filters(results, local_filters)
        return results[:top_k]

    matrix = np.array(store["index"], dtype="float32")
    scores = matrix @ vector[0]
    ranked = np.argsort(scores)[::-1][:expanded_top_k]
    for idx in ranked:
        row = dict(store["metadata"][int(idx)])
        row["score"] = float(scores[int(idx)])
        results.append(row)
    if local_filters:
        results = _apply_local_filters(results, local_filters)
    return results[:top_k]


def _build_local_store(chunks: List[Dict], persist_path: str) -> None:
    ensure_directories()
    path = Path(persist_path)
    path.mkdir(parents=True, exist_ok=True)

    texts = [chunk["text"] for chunk in chunks]
    embeddings = embed_texts(texts)
    if not embeddings:
        raise ValueError("No chunks available to build vector store")

    matrix = np.array(embeddings, dtype="float32")
    if faiss is not None:
        dimension = matrix.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(matrix)
        faiss.write_index(index, str(path / "index.faiss"))
    else:
        index = matrix
        with open(path / "index.pkl", "wb") as handle:
            pickle.dump(matrix, handle)

    with open(path / "metadata.json", "w", encoding="utf-8") as handle:
        json.dump(chunks, handle, ensure_ascii=False, indent=2)

    _write_active_manifest({"provider": "local", "location": str(path.resolve())})
    global _LOADED_STORE, _LOADED_STORE_KEY
    _LOADED_STORE = {"provider": "local", "index": index, "metadata": chunks, "location": str(path.resolve())}
    _LOADED_STORE_KEY = json.dumps({"provider": "local", "location": str(path.resolve())}, sort_keys=True)


def _build_pinecone_store(chunks: List[Dict], persist_path: str) -> None:
    if not pinecone_available():
        raise RuntimeError("Pinecone provider selected but the Pinecone SDK is not installed.")

    ensure_directories()
    path = Path(persist_path)
    path.mkdir(parents=True, exist_ok=True)

    texts = [chunk["text"] for chunk in chunks]
    embeddings = embed_texts(texts)
    if not embeddings:
        raise ValueError("No chunks available to build vector store")

    vectors = []
    metadata_rows = []
    prefix = path.name or "document"
    for chunk, embedding in zip(chunks, embeddings):
        metadata = dict(chunk)
        metadata["document_id"] = metadata.get("document_id") or prefix
        metadata_rows.append(metadata)
        vectors.append(
            {
                "id": f"{prefix}:{chunk['chunk_id']}",
                "values": embedding,
                "metadata": metadata,
            }
        )

    upsert_vectors(vectors=vectors, namespace=PINECONE_NAMESPACE)

    with open(path / "metadata.json", "w", encoding="utf-8") as handle:
        json.dump(metadata_rows, handle, ensure_ascii=False, indent=2)

    manifest = {
        "provider": "pinecone",
        "location": str(path.resolve()),
        "namespace": PINECONE_NAMESPACE,
        "document_id": prefix,
    }
    _write_active_manifest(manifest)
    global _LOADED_STORE, _LOADED_STORE_KEY
    _LOADED_STORE = {
        "provider": "pinecone",
        "metadata": metadata_rows,
        "location": str(path.resolve()),
        "namespace": PINECONE_NAMESPACE,
        "document_id": prefix,
    }
    _LOADED_STORE_KEY = json.dumps(manifest, sort_keys=True)


def _load_pinecone_metadata(location: str) -> List[Dict]:
    metadata_path = Path(location).resolve() / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Pinecone metadata snapshot missing under {location}")
    with open(metadata_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _get_provider() -> str:
    provider = VECTOR_STORE_PROVIDER.strip().lower()
    return provider if provider in {"local", "pinecone"} else "local"


def _write_active_manifest(manifest: Dict) -> None:
    target = ACTIVE_VECTOR_STORE_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _read_active_manifest(persist_path: Optional[str]) -> Dict:
    if persist_path is not None:
        resolved = Path(persist_path).resolve()
        return {"provider": _get_provider(), "location": str(resolved), "document_id": resolved.name}

    if not ACTIVE_VECTOR_STORE_FILE.exists():
        raise FileNotFoundError("No active vector store found. Build an index first.")

    raw = ACTIVE_VECTOR_STORE_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        raise FileNotFoundError("The active vector store marker is empty.")

    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError:
        return {"provider": "local", "location": raw}

    if not isinstance(manifest, dict):
        raise ValueError("Invalid active vector store manifest format.")
    return manifest


def _build_pinecone_filter(filters: Optional[Dict]) -> Optional[Dict]:
    if not filters:
        return None

    clauses = []
    document_ids = [item for item in filters.get("document_ids", []) if item]
    if len(document_ids) == 1:
        clauses.append({"document_id": {"$eq": document_ids[0]}})
    elif len(document_ids) > 1:
        clauses.append({"document_id": {"$in": document_ids}})

    for key in ("document_group", "source_type", "domain", "visibility_scope"):
        value = filters.get(key)
        if value:
            clauses.append({key: {"$eq": value}})
    owner_user_id = str(filters.get("owner_user_id") or "").strip()
    if owner_user_id:
        clauses.append(
            {
                "$or": [
                    {"owner_user_id": {"$eq": owner_user_id}},
                    {"visibility_scope": {"$eq": "global"}},
                    {"document_group": {"$eq": "global_kb"}},
                ]
            }
        )

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _search_pinecone(vector: List[float], top_k: int, store: Dict, filters: Optional[Dict]) -> List[Dict]:
    base_filters = dict(filters or {})
    explicit_document_ids = [item for item in base_filters.get("document_ids", []) if item]
    preferred_document_id = str(base_filters.get("preferred_document_id") or "").strip()
    active_document_id = str(store.get("document_id") or "").strip()
    active_group = _active_document_group(store)

    if explicit_document_ids:
        return _query_pinecone_branch(
            vector=vector,
            top_k=top_k,
            namespace=store.get("namespace"),
            filters=base_filters,
        )

    primary_document_id = preferred_document_id or active_document_id
    should_mix_corpus = (
        bool(primary_document_id)
        and not base_filters.get("document_group")
        and (active_group == "user_upload" or bool(preferred_document_id))
    )
    if not should_mix_corpus:
        return _query_pinecone_branch(
            vector=vector,
            top_k=top_k,
            namespace=store.get("namespace"),
            filters=base_filters,
        )

    branch_top_k = max(top_k * 3, 8)
    primary_quota = max(1, math.ceil(top_k * 0.67))
    secondary_quota = max(1, top_k - primary_quota)
    primary_filters = dict(base_filters)
    primary_filters["document_ids"] = [primary_document_id]
    primary_results = _query_pinecone_branch(
        vector=vector,
        top_k=branch_top_k,
        namespace=store.get("namespace"),
        filters=primary_filters,
        score_boost=0.1,
        retrieval_scope="preferred_document",
    )

    secondary_filters = dict(base_filters)
    secondary_results = _query_pinecone_branch(
        vector=vector,
        top_k=branch_top_k,
        namespace=store.get("namespace"),
        filters=secondary_filters,
        exclude_document_ids=[primary_document_id],
        retrieval_scope="global_corpus",
    )

    return _compose_mixed_results(
        primary_results=primary_results,
        secondary_results=secondary_results,
        top_k=top_k,
        primary_quota=primary_quota,
        secondary_quota=secondary_quota,
    )


def _query_pinecone_branch(
    vector: List[float],
    top_k: int,
    namespace: Optional[str],
    filters: Optional[Dict],
    score_boost: float = 0.0,
    exclude_document_ids: Optional[List[str]] = None,
    retrieval_scope: str = "",
) -> List[Dict]:
    branch_filters = _strip_preference_filters(filters)
    metadata_filter = _build_pinecone_filter(branch_filters)
    expanded_top_k = max(top_k * 4, 20) if branch_filters else top_k
    expanded_top_k = min(expanded_top_k, PINECONE_QUERY_TOP_K_CAP)
    results = query_vectors(
        vector=vector,
        top_k=expanded_top_k,
        namespace=namespace,
        metadata_filter=metadata_filter,
    )
    if branch_filters:
        results = _apply_local_filters(results, branch_filters)
    if exclude_document_ids:
        blocked = {item for item in exclude_document_ids if item}
        results = [row for row in results if row.get("document_id") not in blocked]

    normalized = []
    for row in results:
        item = dict(row)
        item["score"] = float(item.get("score", 0.0)) + score_boost
        if retrieval_scope:
            item["retrieval_scope"] = retrieval_scope
        normalized.append(item)
    normalized.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return normalized[:top_k]


def _compose_mixed_results(
    primary_results: List[Dict],
    secondary_results: List[Dict],
    top_k: int,
    primary_quota: int,
    secondary_quota: int,
) -> List[Dict]:
    primary_pick = primary_results[:primary_quota]
    secondary_pick = secondary_results[:secondary_quota]
    merged = _merge_ranked_results(primary_pick, secondary_pick)

    if len(merged) >= top_k:
        return merged[:top_k]

    remaining_primary = primary_results[primary_quota:]
    remaining_secondary = secondary_results[secondary_quota:]
    remainder = _merge_ranked_results(remaining_primary, remaining_secondary)
    return _merge_ranked_results(merged, remainder)[:top_k]


def _merge_ranked_results(*result_sets: List[Dict]) -> List[Dict]:
    merged: List[Dict] = []
    seen = set()
    for result_set in result_sets:
        for row in result_set:
            key = (str(row.get("document_id") or ""), str(row.get("chunk_id") or ""), str(row.get("id") or ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
    merged.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return merged


def _active_document_group(store: Dict) -> str:
    metadata = store.get("metadata") or []
    if not metadata:
        return ""
    first_row = metadata[0] if isinstance(metadata, list) and metadata else {}
    return str(first_row.get("document_group") or "").strip()


def _strip_preference_filters(filters: Optional[Dict]) -> Optional[Dict]:
    if not filters:
        return None
    cleaned = {key: value for key, value in filters.items() if key != "preferred_document_id"}
    return cleaned or None


def _apply_local_filters(rows: List[Dict], filters: Optional[Dict]) -> List[Dict]:
    if not filters:
        return rows

    document_ids = {item for item in filters.get("document_ids", []) if item}
    filtered = []
    for row in rows:
        if document_ids and row.get("document_id") not in document_ids:
            continue
        if filters.get("document_group") and row.get("document_group") != filters["document_group"]:
            continue
        if filters.get("source_type") and row.get("source_type") != filters["source_type"]:
            continue
        if filters.get("domain") and row.get("domain") != filters["domain"]:
            continue
        owner_user_id = str(filters.get("owner_user_id") or "").strip()
        if owner_user_id:
            row_owner = str(row.get("owner_user_id") or "").strip()
            row_scope = str(row.get("visibility_scope") or "").strip().lower()
            row_group = str(row.get("document_group") or "").strip().lower()
            if row_owner != owner_user_id and row_scope != "global" and row_group != "global_kb":
                continue
        if filters.get("visibility_scope") and row.get("visibility_scope") != filters["visibility_scope"]:
            continue
        filtered.append(row)
    return filtered
