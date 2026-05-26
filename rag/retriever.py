"""Retriever wrapper for ESG RAG."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
from typing import Dict, List, Optional

from configs.settings import (
    CHUNK_DIR,
    RAG_HYBRID_BM25_WEIGHT,
    RAG_HYBRID_ENABLED,
    RAG_HYBRID_FUSION,
    RAG_RRF_BM25_WEIGHT,
    RAG_RRF_DIVERSITY_PENALTY,
    RAG_RRF_K,
    RAG_RRF_TERM_BOOST,
    RAG_RRF_VECTOR_WEIGHT,
)
from rag.bm25_index import search_bm25
from rag.hyde import attach_hyde_metadata, maybe_generate_hyde_query
from rag.pinecone_store import EmbeddingDimensionMismatchError, PineconePayloadTooLargeError
from rag.reranker import rerank_candidates_if_enabled, reranker_candidate_limit
from rag.vector_store import _apply_local_filters, search

_WORD_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
_RRF_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "how",
    "in",
    "is",
    "of",
    "on",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
}
_LOCAL_FALLBACK_STOP_WORDS = _RRF_STOP_WORDS | {
    "about",
    "document",
    "documents",
    "hello",
    "hi",
    "notice",
    "report",
    "reports",
    "should",
}
_EMBEDDING_SKIP_LOGGED = False


def _source_key(item: Dict) -> str:
    document_id = str(item.get("document_id") or "").strip()
    chunk_id = str(item.get("chunk_id") or "").strip()
    text = str(item.get("text") or "").strip()
    return "||".join([document_id, chunk_id, text])


def retrieve_context(
    query: str,
    top_k: int = 5,
    filters: Optional[Dict] = None,
    *,
    use_hyde: bool = False,
    history_block: str = "",
) -> List[Dict]:
    """Retrieve the most relevant chunks for a query."""
    candidate_top_k = max(top_k * 4, reranker_candidate_limit(top_k), top_k)
    raw_results = _single_query_retrieve(
        query=query,
        top_k=candidate_top_k,
        filters=filters,
        use_hyde=use_hyde,
        history_block=history_block,
    )
    ranked_results = rerank_candidates_if_enabled(query=query, candidates=raw_results, top_k=top_k)
    return _dedupe_results(ranked_results, top_k=top_k)


def retrieve_context_multi(
    queries: List[str],
    top_k: int = 5,
    filters: Optional[Dict] = None,
    *,
    use_hyde: bool = False,
    history_block: str = "",
) -> List[Dict]:
    """Run retrieval for each query in parallel and fuse with RRF."""
    clean_queries = []
    seen_queries = set()
    for query in queries or []:
        value = str(query or "").strip()
        key = value.lower()
        if value and key not in seen_queries:
            seen_queries.add(key)
            clean_queries.append(value)
    if not clean_queries:
        return []
    if len(clean_queries) == 1:
        return retrieve_context(clean_queries[0], top_k=top_k, filters=filters, use_hyde=use_hyde, history_block=history_block)

    candidate_top_k = max(top_k * 4, reranker_candidate_limit(top_k), top_k)
    results_by_query: Dict[str, List[Dict]] = {}
    with ThreadPoolExecutor(max_workers=len(clean_queries)) as executor:
        futures = {
            executor.submit(_single_query_retrieve, query, candidate_top_k, filters, use_hyde, history_block): query
            for query in clean_queries
        }
        for future in as_completed(futures):
            query = futures[future]
            try:
                results = future.result()
            except Exception as exc:
                print(f"[rag] multi_query retrieval fell back for query={query!r}: {type(exc).__name__}: {exc}")
                continue
            results_by_query[query] = results

    result_sets = [results_by_query.get(query, []) for query in clean_queries]
    fused = _rrf_fusion(
        result_sets,
        top_k=max(top_k, reranker_candidate_limit(top_k)),
        fusion_method="rrf_multi_query",
        query=" ".join(clean_queries),
        labels=clean_queries,
        record_matched_queries=True,
    )
    return rerank_candidates_if_enabled(query=" ".join(clean_queries), candidates=fused, top_k=top_k)


def retrieve_layered_context(
    query: str,
    top_k: int = 5,
    filters: Optional[Dict] = None,
    primary_queries: Optional[List[str]] = None,
    *,
    use_hyde: bool = False,
    history_block: str = "",
) -> Dict[str, List[Dict]]:
    """Retrieve ESG report evidence plus academic and regulatory priors."""
    base_filters = dict(filters or {})
    prior_k = max(3, top_k * 2 // 3)

    def _run_primary() -> List[Dict]:
        primary_filters = dict(base_filters)
        if not primary_filters.get("domain"):
            primary_filters["domain"] = "esg_report"
        if primary_queries:
            primary = retrieve_context_multi(
                queries=primary_queries,
                top_k=top_k,
                filters=primary_filters,
                use_hyde=use_hyde,
                history_block=history_block,
            )
        else:
            primary = retrieve_context(query=query, top_k=top_k, filters=primary_filters, use_hyde=use_hyde, history_block=history_block)
        if not primary and not (filters or {}).get("domain"):
            fallback_filters = dict(base_filters)
            fallback_filters.pop("domain", None)
            if primary_queries:
                primary = retrieve_context_multi(
                    queries=primary_queries,
                    top_k=top_k,
                    filters=fallback_filters,
                    use_hyde=use_hyde,
                    history_block=history_block,
                )
            else:
                primary = retrieve_context(query=query, top_k=top_k, filters=fallback_filters, use_hyde=use_hyde, history_block=history_block)
        return primary

    def _run_priors() -> List[Dict]:
        prior_filters = dict(base_filters)
        prior_filters.pop("document_ids", None)
        prior_filters.pop("preferred_document_id", None)
        prior_filters["domain"] = "academic"
        return retrieve_context(query=query, top_k=prior_k, filters=prior_filters, use_hyde=use_hyde, history_block=history_block)

    def _run_regulatory() -> List[Dict]:
        regulatory_filters = dict(base_filters)
        regulatory_filters.pop("document_ids", None)
        regulatory_filters.pop("preferred_document_id", None)
        regulatory_filters["domain"] = "regulatory"
        return retrieve_context(query=query, top_k=prior_k, filters=regulatory_filters, use_hyde=use_hyde, history_block=history_block)

    layers: Dict[str, List[Dict]] = {"primary": [], "priors": [], "regulatory": []}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_run_primary): "primary",
            executor.submit(_run_priors): "priors",
            executor.submit(_run_regulatory): "regulatory",
        }
        for future in as_completed(futures):
            layer_name = futures[future]
            try:
                layers[layer_name] = future.result()
            except Exception as exc:
                print(f"[rag.layered] layer={layer_name} failed: {type(exc).__name__}: {exc}")
                layers[layer_name] = []

    return {"primary": layers["primary"], "priors": layers["priors"], "regulatory": layers["regulatory"]}


def retrieve_hybrid(
    query: str,
    top_k: int = 5,
    filters: Optional[Dict] = None,
    *,
    use_hyde: bool = False,
    history_block: str = "",
) -> List[Dict]:
    """Retrieve with vector + BM25 and fuse results."""
    vector_results: List[Dict] = []
    bm25_results: List[Dict] = []
    candidate_top_k = reranker_candidate_limit(top_k)
    search_top_k = max(candidate_top_k, top_k * 6) if candidate_top_k > top_k else top_k
    hyde = maybe_generate_hyde_query(query, context=history_block, force=use_hyde)
    vector_query = str(hyde.get("query") or query)
    with ThreadPoolExecutor(max_workers=2) as executor:
        vector_future = executor.submit(_search_with_payload_retry, query=vector_query, top_k=search_top_k, filters=filters)
        bm25_future = executor.submit(search_bm25, query=query, top_k=search_top_k, filters=filters)
        try:
            vector_results = vector_future.result()
        except EmbeddingDimensionMismatchError:
            _log_embedding_skip_once()
        except PineconePayloadTooLargeError as exc:
            print(f"[rag] hybrid vector skipped: {exc}")
        except Exception as exc:
            print(f"[rag] hybrid vector fell back: {type(exc).__name__}: {exc}")
        try:
            bm25_results = bm25_future.result()
        except FileNotFoundError as exc:
            print(f"[rag] hybrid fell back: {exc}")
            vector_only = [attach_hyde_metadata(dict(item, fusion_method="vector_only_bm25_missing"), hyde) for item in vector_results]
            return rerank_candidates_if_enabled(query=query, candidates=vector_only, top_k=top_k)
        except Exception as exc:
            print(f"[rag] hybrid bm25 fell back: {type(exc).__name__}: {exc}")
            vector_only = [attach_hyde_metadata(item, hyde) for item in vector_results]
            return rerank_candidates_if_enabled(query=query, candidates=vector_only, top_k=top_k)

    if not vector_results and not bm25_results:
        return _scoped_local_chunk_fallback(query=query, top_k=top_k, filters=filters)
    if not vector_results and bm25_results:
        bm25_only = [dict(item, fusion_method="bm25_only_degraded_embeddings") for item in bm25_results]
        return rerank_candidates_if_enabled(query=query, candidates=bm25_only, top_k=top_k)
    if RAG_HYBRID_FUSION == "weighted":
        fused = _weighted_fusion(vector_results, bm25_results, top_k=candidate_top_k)
        fused = [attach_hyde_metadata(item, hyde) for item in fused] if vector_results else fused
        return rerank_candidates_if_enabled(query=query, candidates=fused, top_k=top_k)
    fused = _rrf_fusion(
        [vector_results, bm25_results],
        top_k=candidate_top_k,
        fusion_method="rrf_hybrid",
        query=query,
        labels=["vector", "bm25"],
        channel_weights=[RAG_RRF_VECTOR_WEIGHT, RAG_RRF_BM25_WEIGHT],
    )
    fused = [attach_hyde_metadata(item, hyde) for item in fused] if vector_results else fused
    return rerank_candidates_if_enabled(query=query, candidates=fused, top_k=top_k)


def _single_query_retrieve(
    query: str,
    top_k: int,
    filters: Optional[Dict],
    use_hyde: bool = False,
    history_block: str = "",
) -> List[Dict]:
    if RAG_HYBRID_ENABLED:
        return retrieve_hybrid(query=query, top_k=top_k, filters=filters, use_hyde=use_hyde, history_block=history_block)
    hyde = maybe_generate_hyde_query(query, context=history_block, force=use_hyde)
    vector_query = str(hyde.get("query") or query)
    try:
        results = [attach_hyde_metadata(item, hyde) for item in _search_with_payload_retry(query=vector_query, top_k=top_k, filters=filters)]
        return results or _scoped_local_chunk_fallback(query=query, top_k=top_k, filters=filters)
    except EmbeddingDimensionMismatchError:
        _log_embedding_skip_once()
        return [dict(item, fusion_method="bm25_only_degraded_embeddings") for item in search_bm25(query=query, top_k=top_k, filters=filters)]
    except PineconePayloadTooLargeError as exc:
        print(f"[rag] vector skipped: {exc}")
        return [dict(item, fusion_method="bm25_only_pinecone_payload_too_large") for item in search_bm25(query=query, top_k=top_k, filters=filters)]


def _search_with_payload_retry(query: str, top_k: int, filters: Optional[Dict]) -> List[Dict]:
    """Retry Pinecone vector search once with a smaller top_k before falling back.

    Pinecone can reject large responses even when the query is valid. A reduced
    retry preserves vector recall in common cases and only falls through to BM25
    if Pinecone still rejects the smaller response.
    """
    try:
        return search(query=query, top_k=top_k, filters=filters)
    except PineconePayloadTooLargeError as exc:
        retry_top_k = max(1, int(top_k) // 2)
        if retry_top_k >= int(top_k):
            raise
        print(f"[rag] vector payload too large at top_k={top_k}; retrying top_k={retry_top_k}: {exc}")
        results = search(query=query, top_k=retry_top_k, filters=filters)
        return [dict(item, retrieval_retry="pinecone_top_k_reduced") for item in results]


def _scoped_local_chunk_fallback(query: str, top_k: int, filters: Optional[Dict]) -> List[Dict]:
    document_ids = [str(item).strip() for item in (filters or {}).get("document_ids", []) if str(item).strip()]
    if not document_ids:
        return []

    rows: List[Dict] = []
    for document_id in document_ids:
        chunks_path = CHUNK_DIR / f"{document_id}_chunks.jsonl"
        if not chunks_path.exists():
            continue
        try:
            with chunks_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(row, dict):
                        rows.append(row)
        except OSError as exc:
            print(f"[rag] scoped local fallback skipped {document_id}: {exc}")

    if not rows:
        return []

    filtered = _apply_local_filters([dict(row) for row in rows], filters or {})
    if not filtered:
        return []

    query_terms = _fallback_query_terms(query)
    ranked = []
    for index, row in enumerate(filtered):
        haystack = " ".join(
            str(row.get(key) or "")
            for key in ("document_title", "title", "source", "text", "chunk_id", "domain", "source_type")
        ).lower()
        score = sum(1 for term in query_terms if term in haystack)
        item = dict(row)
        item["score"] = float(score)
        item["local_fallback_rank"] = index
        item["retrieval_channel"] = "local_scoped_fallback"
        item["fusion_method"] = "local_scoped_fallback"
        ranked.append(item)

    ranked.sort(key=lambda item: (-float(item.get("score") or 0.0), int(item.get("local_fallback_rank") or 0)))
    return ranked[:top_k]


def _fallback_query_terms(query: str) -> set[str]:
    terms = {
        term.lower()
        for term in _WORD_PATTERN.findall(str(query or ""))
        if len(term) > 1 and term.lower() not in _LOCAL_FALLBACK_STOP_WORDS
    }
    if "american" in terms and terms & {"flight", "flights", "airline", "airlines"}:
        terms.update({"american airlines", "american airline", "airlines", "airline"})
        terms.discard("flight")
        terms.discard("flights")
    return terms


def _dedupe_results(raw_results: List[Dict], top_k: int) -> List[Dict]:
    deduped: List[Dict] = []
    seen = set()

    for item in raw_results:
        key = _source_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= top_k:
            break

    return deduped


def _rrf_fusion(
    result_sets: List[List[Dict]],
    top_k: int,
    fusion_method: str,
    query: str = "",
    labels: Optional[List[str]] = None,
    channel_weights: Optional[List[float]] = None,
    record_matched_queries: bool = False,
) -> List[Dict]:
    fused: Dict[str, Dict] = {}
    for set_index, results in enumerate(result_sets):
        label = labels[set_index] if labels and set_index < len(labels) else f"ranker_{set_index}"
        weight = float(channel_weights[set_index]) if channel_weights and set_index < len(channel_weights) else 1.0
        if weight <= 0:
            continue
        for rank, item in enumerate(results, start=1):
            key = _source_key(item)
            if not key:
                continue
            if key not in fused:
                fused[key] = dict(item)
                fused[key]["fusion_score"] = 0.0
                fused[key]["fusion_channels"] = []
                if record_matched_queries:
                    fused[key]["matched_queries"] = []
            fused[key]["fusion_score"] = float(fused[key].get("fusion_score") or 0.0) + weight / (RAG_RRF_K + rank)
            fused[key]["fusion_method"] = fusion_method
            fused[key]["fusion_channels"].append(label)
            if record_matched_queries:
                fused[key]["matched_queries"].append(label)

    query_terms = _query_terms(query)
    ranked = []
    for item in fused.values():
        coverage = _term_coverage(item, query_terms)
        if coverage > 0 and RAG_RRF_TERM_BOOST > 0:
            item["fusion_score"] = float(item.get("fusion_score") or 0.0) + coverage * RAG_RRF_TERM_BOOST
            item["term_coverage"] = coverage
        ranked.append(item)

    ranked.sort(key=lambda item: float(item.get("fusion_score") or 0.0), reverse=True)
    return _apply_document_diversity(ranked, top_k=top_k)


def _query_terms(query: str) -> set[str]:
    return {
        term.lower()
        for term in _WORD_PATTERN.findall(str(query or ""))
        if len(term) > 1 and term.lower() not in _RRF_STOP_WORDS
    }


def _term_coverage(item: Dict, query_terms: set[str]) -> float:
    if not query_terms:
        return 0.0
    haystack = " ".join(
        str(item.get(key) or "")
        for key in ("document_title", "title", "text", "chunk_id", "domain", "source_type")
    ).lower()
    if not haystack:
        return 0.0
    matched = sum(1 for term in query_terms if term in haystack)
    return matched / max(1, len(query_terms))


def _apply_document_diversity(ranked: List[Dict], top_k: int) -> List[Dict]:
    if RAG_RRF_DIVERSITY_PENALTY <= 0:
        return ranked[:top_k]

    selected: List[Dict] = []
    remaining = list(ranked)
    doc_counts: Dict[str, int] = {}
    while remaining and len(selected) < top_k:
        best_index = 0
        best_score = float("-inf")
        for index, item in enumerate(remaining):
            document_id = str(item.get("document_id") or "").strip()
            penalty = doc_counts.get(document_id, 0) * RAG_RRF_DIVERSITY_PENALTY if document_id else 0.0
            adjusted = float(item.get("fusion_score") or 0.0) - penalty
            if adjusted > best_score:
                best_index = index
                best_score = adjusted
        picked = remaining.pop(best_index)
        if picked.get("document_id"):
            doc_id = str(picked.get("document_id"))
            doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1
        selected.append(picked)
    return selected


def _weighted_fusion(vector_results: List[Dict], bm25_results: List[Dict], top_k: int) -> List[Dict]:
    vector_scores = _normalize_scores(vector_results, "score")
    bm25_scores = _normalize_scores(bm25_results, "bm25_score")
    merged: Dict[str, Dict] = {}

    for item in vector_results:
        key = _source_key(item)
        merged[key] = dict(item)
    for item in bm25_results:
        key = _source_key(item)
        merged.setdefault(key, dict(item))

    weight = min(1.0, max(0.0, RAG_HYBRID_BM25_WEIGHT))
    for key, item in merged.items():
        item["fusion_score"] = vector_scores.get(key, 0.0) * (1.0 - weight) + bm25_scores.get(key, 0.0) * weight
        item["fusion_method"] = "weighted_hybrid"

    ranked = list(merged.values())
    ranked.sort(key=lambda item: float(item.get("fusion_score") or 0.0), reverse=True)
    return ranked[:top_k]


def _normalize_scores(results: List[Dict], score_key: str) -> Dict[str, float]:
    values = [float(item.get(score_key) or 0.0) for item in results]
    if not values:
        return {}
    low = min(values)
    high = max(values)
    span = high - low
    output = {}
    for item in results:
        key = _source_key(item)
        score = float(item.get(score_key) or 0.0)
        output[key] = 1.0 if span == 0 else (score - low) / span
    return output


def _log_embedding_skip_once() -> None:
    global _EMBEDDING_SKIP_LOGGED
    if _EMBEDDING_SKIP_LOGGED:
        return
    print("[rag.embed] vector skipped: degraded embedding backend")
    _EMBEDDING_SKIP_LOGGED = True
