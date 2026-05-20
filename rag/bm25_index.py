"""Local BM25 index for hybrid retrieval."""

from __future__ import annotations

import os
import pickle
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional

from rag.vector_store import _apply_local_filters, load_vector_store

try:
    from rank_bm25 import BM25Okapi
except Exception:
    BM25Okapi = None

try:
    import jieba
except Exception:
    jieba = None


_WORD_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)

# Eagerly load jieba's dictionary so the first concurrent lcut() call doesn't
# race during lazy init under multi-threaded servers.
if jieba is not None:
    try:
        jieba.initialize()
    except Exception:
        pass

_index_cache: Dict[str, Dict] = {}
_index_cache_lock = threading.Lock()


def build_bm25_index(chunks: List[Dict], persist_path: str) -> None:
    path = Path(persist_path)
    path.mkdir(parents=True, exist_ok=True)
    payload = {"tokens": [_tokenize(str(chunk.get("text") or "")) for chunk in chunks], "metadata": chunks}
    target = path / "bm25.pkl"
    tmp = path / f"bm25.pkl.tmp.{os.getpid()}"
    try:
        with tmp.open("wb") as handle:
            pickle.dump(payload, handle)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def load_bm25_index(persist_path: Optional[str] = None) -> Dict:
    if persist_path:
        path = Path(persist_path).resolve()
        fallback_metadata = None
    else:
        store = load_vector_store(None)
        path = Path(str(store.get("location") or "")).resolve()
        fallback_metadata = store.get("metadata")

    index_path = path / "bm25.pkl"
    if not index_path.exists():
        raise FileNotFoundError(f"BM25 index missing under {path}")

    mtime = index_path.stat().st_mtime_ns
    cache_key = str(path)

    cached = _index_cache.get(cache_key)
    if cached and cached.get("mtime") == mtime:
        return cached["index"]

    with _index_cache_lock:
        cached = _index_cache.get(cache_key)
        if cached and cached.get("mtime") == mtime:
            return cached["index"]

        with index_path.open("rb") as handle:
            payload = pickle.load(handle)
        tokens = payload.get("tokens") or []
        rows = payload.get("metadata") or fallback_metadata or []
        bm25 = BM25Okapi(tokens) if BM25Okapi is not None and tokens else None
        index = {"bm25": bm25, "metadata": rows, "tokens": tokens, "location": str(path)}
        _index_cache[cache_key] = {"mtime": mtime, "index": index}
        return index


def search_bm25(query: str, top_k: int, filters: Optional[Dict] = None) -> List[Dict]:
    index = load_bm25_index()
    rows = [dict(row) for row in (index.get("metadata") or [])]
    tokens = index.get("tokens") or []
    if not rows:
        return []
    if filters:
        rows_with_index = [{**row, "_bm25_index": idx} for idx, row in enumerate(rows)]
        rows_with_index = _apply_local_filters(rows_with_index, filters)
        candidate_indices = [int(row["_bm25_index"]) for row in rows_with_index]
    else:
        candidate_indices = list(range(len(rows)))

    if not candidate_indices:
        return []

    query_tokens = _tokenize(query)
    scores = _score(index.get("bm25"), tokens, query_tokens)
    ranked = sorted(candidate_indices, key=lambda idx: scores[idx] if idx < len(scores) else 0.0, reverse=True)
    output = []
    for idx in ranked[:top_k]:
        row = dict(rows[idx])
        row["bm25_score"] = float(scores[idx] if idx < len(scores) else 0.0)
        row["score"] = row["bm25_score"]
        row["retrieval_channel"] = "bm25"
        output.append(row)
    return output


def _score(bm25, corpus_tokens: List[List[str]], query_tokens: List[str]) -> List[float]:
    if bm25 is not None:
        return [float(score) for score in bm25.get_scores(query_tokens)]
    query_terms = set(query_tokens)
    return [float(len(query_terms & set(tokens))) for tokens in corpus_tokens]


def _tokenize(text: str) -> List[str]:
    lowered = str(text or "").lower()
    tokens = _WORD_PATTERN.findall(lowered)
    if jieba is not None and re.search(r"[\u4e00-\u9fff]", lowered):
        tokens.extend(token.strip().lower() for token in jieba.lcut(lowered) if token.strip())
    elif re.search(r"[\u4e00-\u9fff]", lowered):
        tokens.extend(char for char in lowered if "\u4e00" <= char <= "\u9fff")
    return [token for token in tokens if token]


def warm_bm25_index() -> None:
    """Best-effort warmup to avoid first-query pickle load latency."""
    try:
        load_bm25_index()
        print("[rag.bm25] warmup completed")
    except FileNotFoundError as exc:
        print(f"[rag.bm25] warmup skipped: {exc}")
    except Exception as exc:
        print(f"[rag.bm25] warmup failed: {type(exc).__name__}: {exc}")
