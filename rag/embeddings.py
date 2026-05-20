"""Embedding helpers with an offline-safe local fallback."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re
from functools import lru_cache
from typing import Any, List, Optional

from configs.settings import (
    DEEPINFRA_API_KEY,
    DEEPINFRA_BASE_URL,
    DEEPINFRA_EMBEDDING_MODEL,
    EMBEDDING_BACKEND,
    EMBEDDING_ALLOW_DOWNLOAD,
    EMBEDDING_FALLBACK_DIM,
    EMBEDDING_LOCAL_FILES_ONLY,
    EMBEDDING_MODEL,
    EMBEDDING_MODEL_PATH,
)


_EMBEDDING_MODEL: Optional[Any] = None
_EMBEDDING_BACKEND = "uninitialized"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_%./-]*")
_DEEPINFRA_BATCH_SIZE = 96
_BGE_M3_DIMENSION = 1024


def _set_backend(name: str) -> None:
    global _EMBEDDING_BACKEND
    _EMBEDDING_BACKEND = name


def get_embedding_backend() -> str:
    """Return the embedding backend currently in use."""
    return _EMBEDDING_BACKEND


def embedding_backend_is_real() -> bool:
    """True iff embeddings come from a real semantic backend."""
    return not _EMBEDDING_BACKEND.startswith("hash-fallback")


def get_embedding_model() -> Optional[Any]:
    """Load the sentence-transformer model once when available."""
    global _EMBEDDING_MODEL
    if EMBEDDING_BACKEND == "deepinfra":
        _set_backend(f"deepinfra:{DEEPINFRA_EMBEDDING_MODEL}")
        return None

    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL

    local_files_only = EMBEDDING_LOCAL_FILES_ONLY or not EMBEDDING_ALLOW_DOWNLOAD
    model_path = Path(EMBEDDING_MODEL_PATH)
    if local_files_only and not model_path.exists():
        _set_backend(f"hash-fallback:{EMBEDDING_FALLBACK_DIM}")
        print(
            f"[embeddings] CRITICAL: degraded to hash-fallback dim={EMBEDDING_FALLBACK_DIM}, "
            "Pinecone will reject queries"
        )
        return None

    try:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. Set EMBEDDING_BACKEND=deepinfra "
                "for production, or install sentence-transformers for local embeddings."
            ) from exc

        sentence_transformer_kwargs = {"local_files_only": local_files_only}

        # Only force ONNX when the local bundle lacks standard PyTorch weights.
        has_pytorch_weights = any(
            (model_path / filename).exists()
            for filename in ("pytorch_model.bin", "model.safetensors")
        )
        if (
            model_path.exists()
            and not has_pytorch_weights
            and (model_path / "onnx" / "model.onnx").exists()
        ):
            sentence_transformer_kwargs["backend"] = "onnx"

        _EMBEDDING_MODEL = SentenceTransformer(EMBEDDING_MODEL_PATH, **sentence_transformer_kwargs)
        backend_name = sentence_transformer_kwargs.get("backend", "sentence-transformers")
        _set_backend(f"{backend_name}:{EMBEDDING_MODEL_PATH}")
        return _EMBEDDING_MODEL
    except Exception as exc:
        print(
            f"[embeddings] SentenceTransformer load failed for {EMBEDDING_MODEL_PATH!r}; "
            f"falling back to hash embeddings. Reason: {type(exc).__name__}: {exc}"
        )
        print(
            f"[embeddings] CRITICAL: degraded to hash-fallback dim={EMBEDDING_FALLBACK_DIM}, "
            "Pinecone will reject queries"
        )
        _EMBEDDING_MODEL = None
        _set_backend(f"hash-fallback:{EMBEDDING_FALLBACK_DIM}")
        return None


@lru_cache(maxsize=1)
def _get_deepinfra_client():
    if not DEEPINFRA_API_KEY:
        raise RuntimeError("DEEPINFRA_API_KEY is not set; required when EMBEDDING_BACKEND=deepinfra.")
    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError("openai SDK is required for EMBEDDING_BACKEND=deepinfra.") from exc
    return OpenAI(api_key=DEEPINFRA_API_KEY, base_url=DEEPINFRA_BASE_URL)


def _embed_texts_deepinfra(texts: List[str]) -> List[List[float]]:
    client = _get_deepinfra_client()
    all_vectors: List[List[float]] = []
    for start in range(0, len(texts), _DEEPINFRA_BATCH_SIZE):
        batch = texts[start : start + _DEEPINFRA_BATCH_SIZE]
        response = client.embeddings.create(model=DEEPINFRA_EMBEDDING_MODEL, input=batch)
        vectors = [list(item.embedding) for item in response.data]
        for vector in vectors:
            if len(vector) != _BGE_M3_DIMENSION:
                raise RuntimeError(
                    f"DeepInfra embedding dimension mismatch: expected {_BGE_M3_DIMENSION}, got {len(vector)}. "
                    "Check DEEPINFRA_EMBEDDING_MODEL before writing/querying Pinecone."
                )
        all_vectors.extend(vectors)
    _set_backend(f"deepinfra:{DEEPINFRA_EMBEDDING_MODEL}")
    return all_vectors


def _normalize(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def _hash_embed_text(text: str, dimension: int = EMBEDDING_FALLBACK_DIM) -> List[float]:
    """Create a deterministic local embedding for offline-only environments."""
    vector = [0.0] * dimension
    tokens = _TOKEN_PATTERN.findall((text or "").lower())
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:8], "big") % dimension
        sign = 1.0 if digest[8] % 2 == 0 else -1.0
        weight = 1.0 + (digest[9] / 255.0)
        vector[index] += sign * weight

    return _normalize(vector)


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts using sentence-transformers or a local fallback."""
    if not texts:
        return []

    if EMBEDDING_BACKEND == "deepinfra":
        return _embed_texts_deepinfra(texts)
    if EMBEDDING_BACKEND != "local":
        raise RuntimeError(f"Unsupported EMBEDDING_BACKEND={EMBEDDING_BACKEND!r}; expected 'local' or 'deepinfra'.")

    model = get_embedding_model()
    if model is not None:
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()

    return [_hash_embed_text(text) for text in texts]


def embed_query(query: str) -> List[float]:
    """Embed a single query string."""
    return embed_texts([query])[0]


_set_backend(f"pending:{EMBEDDING_BACKEND}:{EMBEDDING_MODEL}")
