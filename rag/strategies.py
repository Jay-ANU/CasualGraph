"""Retrieval strategy implementations."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from configs.settings import RAG_DECOMPOSE_ENABLED, RAG_DECOMPOSE_MAX_SUBQ, RAG_MULTI_QUERY_N
from rag.hyde import attach_hyde_metadata, maybe_generate_hyde_query
from rag.multi_query import generate_query_variants
from rag.query_decomposer import decompose_query
from rag.reranker import rerank_candidates_if_enabled, reranker_candidate_limit
from rag.retriever import retrieve_context_multi, retrieve_hybrid, retrieve_layered_context
from rag.vector_store import search


class RetrievalStrategy:
    name = "base"

    def run(self, query: str, top_k: int, filters: Optional[Dict], history_block: str = "") -> Dict:
        raise NotImplementedError


class VectorOnlyStrategy(RetrievalStrategy):
    name = "vector_only"

    def run(self, query: str, top_k: int, filters: Optional[Dict], history_block: str = "") -> Dict:
        candidate_top_k = max(top_k * 4, reranker_candidate_limit(top_k), top_k)
        hyde = maybe_generate_hyde_query(query, context=history_block)
        vector_query = str(hyde.get("query") or query)
        candidates = _dedupe(
            [attach_hyde_metadata(item, hyde) for item in search(query=vector_query, top_k=candidate_top_k, filters=filters)],
            candidate_top_k,
        )
        return {"sources": rerank_candidates_if_enabled(query=query, candidates=candidates, top_k=top_k), "metadata": {}}


class HybridStrategy(RetrievalStrategy):
    name = "hybrid"

    def run(self, query: str, top_k: int, filters: Optional[Dict], history_block: str = "") -> Dict:
        return {
            "sources": retrieve_hybrid(query=query, top_k=top_k, filters=filters, history_block=history_block),
            "metadata": {"fusion_method": "hybrid"},
        }


class MultiQueryStrategy(RetrievalStrategy):
    name = "multi_query"

    def run(self, query: str, top_k: int, filters: Optional[Dict], history_block: str = "", use_hyde: bool = False) -> Dict:
        mq = generate_query_variants(query=query, history_block=history_block, n_variants=RAG_MULTI_QUERY_N)
        queries = mq.get("variants") or [query]
        return {
            "sources": retrieve_context_multi(
                queries=[str(item) for item in queries],
                top_k=top_k,
                filters=filters,
                use_hyde=use_hyde,
                history_block=history_block,
            ),
            "metadata": {"sub_queries": queries, "multi_query_backend": mq.get("backend")},
        }


class DecompositionStrategy(RetrievalStrategy):
    name = "decomposition"

    def run(self, query: str, top_k: int, filters: Optional[Dict], history_block: str = "") -> Dict:
        decomposition = decompose_query(question=query, history_block=history_block, max_subquestions=RAG_DECOMPOSE_MAX_SUBQ)
        subquestions = [str(item) for item in (decomposition.get("subquestions") or [query])]
        max_workers = max(1, min(len(subquestions), 4))

        def _run_subquestion(index: int, subquestion: str):
            started = time.perf_counter()
            try:
                result = MultiQueryStrategy().run(subquestion, top_k=top_k, filters=filters, history_block=history_block, use_hyde=True)
                elapsed_ms = (time.perf_counter() - started) * 1000
                print(f"[rag.timing] subq={index} took_ms={elapsed_ms:.0f}")
                return index, subquestion, result
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                print(f"[rag.timing] subq={index} took_ms={elapsed_ms:.0f}")
                print(f"[rag.strategy] decomposition subq failed: idx={index} {type(exc).__name__}: {exc}")
                return index, subquestion, {"sources": [], "metadata": {"sub_queries": []}}

        sources: List[Dict] = []
        sub_queries: List[str] = []
        ordered_results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for item in executor.map(lambda args: _run_subquestion(*args), list(enumerate(subquestions))):
                ordered_results.append(item)
        ordered_results.sort(key=lambda row: row[0])
        for _, subquestion, result in ordered_results:
            sub_queries.extend([str(item) for item in result.get("metadata", {}).get("sub_queries", [])])
            sources.extend({**item, "sub_question": subquestion} for item in result.get("sources", []))
        candidates = _dedupe(sources, max(top_k, reranker_candidate_limit(top_k)))
        return {
            "sources": rerank_candidates_if_enabled(query=query, candidates=candidates, top_k=top_k),
            "metadata": {"decomposition": decomposition, "sub_queries": _dedupe_strings(sub_queries)},
        }


class GraphFirstStrategy(RetrievalStrategy):
    name = "graph_first"

    def run(self, query: str, top_k: int, filters: Optional[Dict], history_block: str = "") -> Dict:
        result = HybridStrategy().run(query, top_k=top_k, filters=filters, history_block=history_block)
        result["metadata"]["graph_first"] = True
        return result


class LayeredStrategy(RetrievalStrategy):
    name = "layered"

    def run(self, query: str, top_k: int, filters: Optional[Dict], history_block: str = "") -> Dict:
        decomposition = None
        primary_queries = None
        if RAG_DECOMPOSE_ENABLED:
            decomposition = decompose_query(question=query, history_block=history_block, max_subquestions=RAG_DECOMPOSE_MAX_SUBQ)
            subquestions = [str(item) for item in (decomposition.get("subquestions") or [query])]
            layered = _retrieve_decomposed(subquestions, top_k=top_k, filters=filters, history_block=history_block)
        else:
            mq = generate_query_variants(query=query, history_block=history_block, n_variants=RAG_MULTI_QUERY_N)
            primary_queries = [str(item) for item in (mq.get("variants") or [query])]
            layered = retrieve_layered_context(
                query=query,
                top_k=top_k,
                filters=filters,
                primary_queries=primary_queries,
                use_hyde=True,
                history_block=history_block,
            )
        return {
            "sources": layered.get("primary", []),
            "metadata": {
                "layered_context": layered,
                "decomposition": decomposition,
                "sub_queries": primary_queries or layered.get("sub_queries") or [query],
            },
        }


STRATEGY_REGISTRY = {
    "vector_only": VectorOnlyStrategy(),
    "hybrid": HybridStrategy(),
    "multi_query": MultiQueryStrategy(),
    "decomposition": DecompositionStrategy(),
    "graph_first": GraphFirstStrategy(),
    "layered": LayeredStrategy(),
}


def _retrieve_decomposed(subquestions: List[str], top_k: int, filters: Optional[Dict], history_block: str) -> Dict[str, List[Dict]]:
    primary: List[Dict] = []
    priors: List[Dict] = []
    regulatory: List[Dict] = []
    max_workers = max(1, min(len(subquestions), 4))

    def _run_subquestion(index: int, subquestion: str):
        started = time.perf_counter()
        try:
            mq = generate_query_variants(subquestion, history_block=history_block, n_variants=RAG_MULTI_QUERY_N)
            sub_queries = [str(item) for item in (mq.get("variants") or [subquestion])]
            layered = retrieve_layered_context(
                query=subquestion,
                top_k=top_k,
                filters=filters,
                primary_queries=sub_queries,
                use_hyde=True,
                history_block=history_block,
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(f"[rag.timing] subq={index} took_ms={elapsed_ms:.0f}")
            return index, subquestion, sub_queries, layered
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(f"[rag.timing] subq={index} took_ms={elapsed_ms:.0f}")
            print(f"[rag.strategy] layered subq failed: idx={index} {type(exc).__name__}: {exc}")
            return index, subquestion, [subquestion], {"primary": [], "priors": [], "regulatory": []}

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for item in executor.map(lambda args: _run_subquestion(*args), list(enumerate(subquestions))):
            results.append(item)

    results.sort(key=lambda row: row[0])
    sub_query_layers: List[List[str]] = []
    for _, subquestion, sub_queries, layered in results:
        sub_query_layers.append(sub_queries)
        primary.extend({**item, "sub_question": subquestion} for item in layered.get("primary", []))
        priors.extend({**item, "sub_question": subquestion} for item in layered.get("priors", []))
        regulatory.extend({**item, "sub_question": subquestion} for item in layered.get("regulatory", []))
    combined_query = " ".join(subquestions)
    primary_candidates = _dedupe(primary, max(top_k, reranker_candidate_limit(top_k)))
    prior_top_k = max(3, top_k)
    prior_candidates = _dedupe(priors, max(prior_top_k, reranker_candidate_limit(prior_top_k)))
    regulatory_candidates = _dedupe(regulatory, max(prior_top_k, reranker_candidate_limit(prior_top_k)))
    return {
        "primary": rerank_candidates_if_enabled(query=combined_query, candidates=primary_candidates, top_k=top_k),
        "priors": rerank_candidates_if_enabled(query=combined_query, candidates=prior_candidates, top_k=prior_top_k),
        "regulatory": rerank_candidates_if_enabled(query=combined_query, candidates=regulatory_candidates, top_k=prior_top_k),
        "sub_queries": sub_query_layers,
    }


def _dedupe(rows: List[Dict], top_k: int) -> List[Dict]:
    output = []
    seen = set()
    for item in rows:
        key = _source_key(item)
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= top_k:
            break
    return output


def _source_key(item: Dict) -> str:
    return "||".join([str(item.get("document_id") or ""), str(item.get("chunk_id") or ""), str(item.get("text") or "")])


def _dedupe_strings(values: List[str]) -> List[str]:
    output = []
    seen = set()
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(value.strip())
    return output
