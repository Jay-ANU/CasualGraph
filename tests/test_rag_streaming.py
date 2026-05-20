from __future__ import annotations

import time
from unittest.mock import patch

from rag.rag_pipeline import INSUFFICIENT_CONTEXT_ANSWER, answer_question, stream_answer_question


def _prepared_state(**overrides):
    payload = {
        "query": "What is the answer?",
        "top_k": 3,
        "history": [],
        "retrieval_filters": {},
        "user_id": None,
        "resolved_mode": "ask",
        "rewrite_result": {"query": "What is the answer?", "rewrite_applied": False, "rewrite_backend": "test"},
        "retrieval_query": "What is the answer?",
        "history_block": "",
        "routing": {"strategy": "hybrid", "reason": "rule", "backend": "heuristic", "fallback_chain": []},
        "retrieval_result": {"strategy": "hybrid", "metadata": {}, "fallbacks_used": []},
        "graph_ctx": {"text": "", "matched_entities": [], "nodes": [], "edges": [], "skipped_reason": "disabled"},
        "sources": [{"chunk_id": "chunk_1", "text": "alpha", "document_id": "doc_1"}],
        "retrieval_metadata": {},
        "queries": ["What is the answer?"],
        "layered_context": None,
        "decomposition": None,
        "allow_speculation": False,
        "graph_context_text": None,
        "timings": {"rewrite": 1.0, "route": 2.0, "retrieval": 3.0, "graph": 4.0, "generate": 0.0, "total": 0.0},
        "total_started": time.perf_counter(),
        "strategy": "hybrid",
    }
    payload.update(overrides)
    return payload


def test_stream_answer_question_yields_meta_tokens_and_done():
    prepared = _prepared_state()

    with patch("rag.rag_pipeline._prepare_answer_context", return_value=prepared), patch(
        "rag.rag_pipeline.openai_answering_available", return_value=True
    ), patch("rag.rag_pipeline.stream_openai_rag_answer", return_value=iter(["Hello", " world"])):
        events = list(stream_answer_question("What is the answer?", top_k=3))

    assert [event["type"] for event in events] == ["meta", "meta", "token", "token", "done"]
    assert events[0]["payload"]["stream_stage"] == "routing"
    assert events[1]["payload"]["retrieval_strategy"] == "hybrid"
    assert events[2]["text"] == "Hello"
    assert events[3]["text"] == " world"
    assert events[4]["payload"]["answer"] == "Hello world"
    assert events[4]["payload"]["backend"] == "openai"
    assert events[4]["payload"]["timings_ms"]["generate"] >= 0.0


def test_stream_answer_question_no_context_still_emits_token_and_done():
    prepared = _prepared_state(sources=[], retrieval_result={"strategy": "vector_only", "metadata": {}, "fallbacks_used": []}, strategy="vector_only")

    with patch("rag.rag_pipeline._prepare_answer_context", return_value=prepared), patch(
        "rag.rag_pipeline._notify_unanswerable"
    ) as notify_mock:
        events = list(stream_answer_question("What is the answer?", top_k=3))

    assert [event["type"] for event in events] == ["meta", "meta", "token", "done"]
    assert events[2]["text"] == INSUFFICIENT_CONTEXT_ANSWER
    assert events[3]["payload"]["backend"] == "no_context"
    notify_mock.assert_called_once()


def test_answer_question_uses_graph_context_even_without_chunk_sources():
    prepared = _prepared_state(
        sources=[],
        graph_context_text="Apple -> supplier audits: carbon-neutral targets increase audit scrutiny.",
        graph_ctx={
            "text": "Apple -> supplier audits: carbon-neutral targets increase audit scrutiny.",
            "matched_entities": [],
            "nodes": [],
            "edges": [],
        },
        retrieval_result={"strategy": "graph_first", "metadata": {}, "fallbacks_used": []},
        strategy="graph_first",
    )

    with patch("rag.rag_pipeline._prepare_answer_context", return_value=prepared), patch(
        "rag.rag_pipeline.openai_answering_available", return_value=True
    ), patch("rag.rag_pipeline.generate_openai_rag_answer", return_value="Graph-grounded answer") as answer_mock, patch(
        "rag.rag_pipeline._notify_unanswerable"
    ) as notify_mock:
        result = answer_question("How does this affect audits?", top_k=3)

    assert result["answer"] == "Graph-grounded answer"
    assert result["backend"] == "openai+graph"
    answer_mock.assert_called_once()
    notify_mock.assert_not_called()


def test_stream_answer_question_legacy_predict_mode_streams_markdown():
    prepared = _prepared_state()

    with patch("rag.rag_pipeline._prepare_answer_context", return_value=prepared), patch(
        "rag.rag_pipeline.openai_answering_available", return_value=True
    ), patch("rag.rag_pipeline.stream_openai_rag_answer", return_value=iter(["Legacy-compatible answer"])):
        events = list(stream_answer_question("Predict this", mode="predict"))

    assert [event["type"] for event in events] == ["meta", "meta", "token", "done"]
    assert events[3]["payload"]["answer"] == "Legacy-compatible answer"
    assert events[3]["payload"]["reasoning_mode"] == "flash"
