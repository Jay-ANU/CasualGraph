"""Optional cross-encoder reranking for retrieved RAG chunks."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

from configs.settings import (
    RERANKER_ENABLED,
    RERANKER_MODEL,
    RERANKER_TOP_K_AFTER,
    RERANKER_TOP_K_BEFORE,
)
from rag.source_titles import display_document_title


_RERANKER: Optional["Reranker"] = None
_RERANKER_LOCK = threading.Lock()
_RERANKER_ERROR_LOGGED = False


class Reranker:
    def __init__(self, model_name: str = RERANKER_MODEL):
        self.model_name = model_name
        self._model = None
        self._load_lock = threading.Lock()

    def _load_model(self):
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name)
            return self._model

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = RERANKER_TOP_K_AFTER) -> List[Dict[str, Any]]:
        if not query.strip() or not candidates:
            return candidates[:top_k]

        model = self._load_model()
        pairs = [[query, _candidate_text(item)] for item in candidates]
        started = time.perf_counter()
        scores = model.predict(pairs, batch_size=min(16, max(1, len(pairs))))
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)

        scored = []
        for index, (item, score) in enumerate(zip(candidates, scores)):
            row = dict(item)
            row["rerank_score"] = float(score)
            row["rerank_model"] = self.model_name
            row["rerank_ms"] = elapsed_ms
            row["rerank_input_rank"] = index + 1
            scored.append(row)
        scored.sort(key=lambda item: float(item.get("rerank_score") or 0.0), reverse=True)
        for rank, item in enumerate(scored, start=1):
            item["rerank_rank"] = rank
        return scored[:top_k]


def reranker_candidate_limit(top_k: int) -> int:
    if not RERANKER_ENABLED:
        return top_k
    return max(top_k, RERANKER_TOP_K_BEFORE)


def reranker_output_limit(top_k: int) -> int:
    if not RERANKER_ENABLED:
        return top_k
    if top_k <= RERANKER_TOP_K_AFTER:
        return min(top_k, RERANKER_TOP_K_AFTER)
    return top_k


def rerank_candidates_if_enabled(query: str, candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    if not RERANKER_ENABLED:
        return candidates[:top_k]
    if not candidates:
        return []
    limited_candidates = candidates[:reranker_candidate_limit(top_k)]
    try:
        reranker = _get_reranker()
        return reranker.rerank(query=query, candidates=limited_candidates, top_k=reranker_output_limit(top_k))
    except Exception as exc:
        _log_reranker_error_once(exc)
        return candidates[:top_k]


def _get_reranker() -> Reranker:
    global _RERANKER
    if _RERANKER is not None:
        return _RERANKER
    with _RERANKER_LOCK:
        if _RERANKER is None:
            _RERANKER = Reranker()
        return _RERANKER


def _candidate_text(item: Dict[str, Any]) -> str:
    title = display_document_title(item)
    text = str(item.get("text") or item.get("content") or "").strip()
    if title and text:
        return f"{title}\n\n{text}"
    return text or title


def _log_reranker_error_once(exc: Exception) -> None:
    global _RERANKER_ERROR_LOGGED
    if _RERANKER_ERROR_LOGGED:
        return
    print(f"[rag.reranker] disabled for this process after error: {type(exc).__name__}: {exc}")
    _RERANKER_ERROR_LOGGED = True
