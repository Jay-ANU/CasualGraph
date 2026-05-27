import time

import rag.rag_pipeline as pipeline


def _prepared_context():
    return {
        "timings": {"rewrite": 0.0, "route": 0.0, "retrieval": 0.0, "graph": 0.0},
        "resolved_mode": "ask",
        "answer_intent": {"mode": "hybrid", "confidence": 0.9},
        "history_block": "",
        "reasoning_mode": "deep",
        "total_started": time.perf_counter(),
        "strategy": "layered",
        "routing": {"strategy": "layered", "reason": "test", "backend": "test"},
        "sources": [],
        "graph_ctx": {},
        "retrieval_query": "Compare Apple and Microsoft climate risks.",
        "rewrite_result": {"rewrite_applied": False, "rewrite_backend": "test"},
        "queries": [],
        "retrieval_result": {"strategy": "layered"},
        "retrieval_metadata": {},
        "tier": "deep",
        "graph_context_text": "",
        "allow_speculation": True,
        "query": "Compare Apple and Microsoft climate risks.",
    }


def test_entity_scoped_general_intent_still_uses_retrieval(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "route_query",
        lambda **kwargs: {"strategy": "vector_only", "reason": "test", "backend": "test", "fallback_chain": []},
    )
    monkeypatch.setattr(pipeline, "graph_context_enabled", lambda: False)
    monkeypatch.setattr(
        pipeline,
        "_run_routed_retrieval",
        lambda **kwargs: {
            "sources": [
                {
                    "document_id": "aa_sustainability_report_2022_20260501043104",
                    "chunk_id": "chunk_1",
                    "document_title": "aa-sustainability-report-2022",
                    "text": "American Airlines operates a major network carrier.",
                    "score": 1.0,
                }
            ],
            "metadata": {},
            "strategy": "vector_only",
        },
    )
    monkeypatch.setattr(pipeline, "filter_sources_by_relevance", lambda query, sources: sources)

    prepared = pipeline._prepare_answer_context(
        query="Hi, What should I notice about American Flight?",
        top_k=3,
        history=[],
        retrieval_filters={
            "document_ids": ["aa_sustainability_report_2022_20260501043104"],
            "document_scope_source": "entity_resolver",
        },
        mode="ask",
        reasoning_mode="flash",
        user_id="user_1",
        answer_intent={"mode": "general", "needs_retrieval": False, "needs_citations": False},
    )

    assert prepared["answer_intent"]["mode"] == "evidence"
    assert prepared["routing"]["strategy"] == "vector_only"
    assert prepared["sources"][0]["document_id"] == "aa_sustainability_report_2022_20260501043104"


def test_agent_path_delegates_to_runner(monkeypatch):
    def fail_prepare(**kwargs):
        raise AssertionError("agent path must not prepare retrieval context before routing")

    monkeypatch.setattr(pipeline, "_prepare_answer_context", fail_prepare)
    monkeypatch.setattr(
        pipeline,
        "decide_hybrid_path",
        lambda **kwargs: pipeline.HybridRouteDecision(
            path="agent",
            reason="test",
            confidence=0.9,
            budget=pipeline.AgentBudget(max_steps=1, deadline_seconds=90),
        ),
    )

    class FakeRunner:
        def __init__(self, registry, budget):
            self.registry = registry
            self.budget = budget

        def run(self, question, reasoning_mode, history_block, answer_intent="evidence", progress_callback=None):
            assert answer_intent == "hybrid"
            return pipeline.AgentRunResult(
                answer="Agent answer",
                backend="agent_test",
                sources=[{"chunk_id": "chunk_1", "text": "evidence"}],
                graph_sources={"text": "", "edges": [], "nodes": [], "matched_entities": []},
                trace=[],
                reflexion={"status": "complete", "covered_entities": ["apple"], "missing_entities": []},
            )

    monkeypatch.setattr(pipeline, "AgentRunner", FakeRunner)
    result = pipeline.answer_question(
        "Compare Apple and Microsoft climate risks.",
        reasoning_mode="deep",
        retrieval_filters={"document_ids": ["a", "b"]},
        answer_intent={"mode": "hybrid", "confidence": 0.9},
    )
    assert result["answer"] == "Agent answer"
    assert result["path"] == "agent"
    assert result["backend"] == "agent_test"
    assert result["routing"]["strategy"] == "agent"
    assert result["routing"]["reflexion"]["status"] == "complete"
    assert result["timings_ms"]["generate"] >= 0.0


def test_routing_hint_forces_agent_even_when_router_prefers_rag(monkeypatch):
    def fail_prepare(**kwargs):
        raise AssertionError("agent hint must route before normal RAG preparation")

    monkeypatch.setattr(pipeline, "_prepare_answer_context", fail_prepare)
    monkeypatch.setattr(
        pipeline,
        "decide_hybrid_path",
        lambda **kwargs: pipeline.HybridRouteDecision(
            path="rag",
            reason="router_prefers_rag",
            confidence=0.8,
            budget=pipeline.AgentBudget(max_steps=0, deadline_seconds=12),
        ),
    )

    class FakeRunner:
        def __init__(self, registry, budget):
            self.registry = registry
            self.budget = budget

        def run(self, question, reasoning_mode, history_block, answer_intent="evidence", progress_callback=None):
            return pipeline.AgentRunResult(
                answer="Agent comparison answer",
                backend="agent_test",
                sources=[{"chunk_id": "chunk_aa", "document_id": "aa", "text": "AA evidence"}],
                graph_sources={},
                trace=[],
            )

    monkeypatch.setattr(pipeline, "AgentRunner", FakeRunner)

    result = pipeline.answer_question(
        "Across between American Airlines and Apple, what is the main difference in carbon emission?",
        reasoning_mode="flash",
        retrieval_filters={
            "document_ids": ["aa", "apple"],
            "routing_hint": {
                "needs_agent": True,
                "entities": ["american airlines", "apple"],
                "target_document_ids": ["aa", "apple"],
                "sub_questions": ["Find carbon emission evidence for American Airlines.", "Find carbon emission evidence for Apple."],
            },
        },
        answer_intent={"mode": "hybrid", "confidence": 0.9},
    )

    assert result["path"] == "agent"
    assert result["routing"]["reason"] == "routing_hint_needs_agent"
    assert result["answer"] == "Agent comparison answer"


def test_agent_reflexion_marks_missing_entities_without_discarding_partial_answer(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "decide_hybrid_path",
        lambda **kwargs: pipeline.HybridRouteDecision(
            path="rag",
            reason="router_prefers_rag",
            confidence=0.8,
            budget=pipeline.AgentBudget(max_steps=0, deadline_seconds=12),
        ),
    )

    class FakeRunner:
        def __init__(self, registry, budget):
            self.registry = registry
            self.budget = budget

        def run(self, question, reasoning_mode, history_block, answer_intent="evidence", progress_callback=None):
            return pipeline.AgentRunResult(
                answer="AA reports fuel-related emissions evidence; Apple evidence was not found in this run.",
                backend="agent_test",
                sources=[
                    {
                        "chunk_id": "chunk_aa",
                        "document_id": "aa",
                        "document_title": "American Airlines sustainability",
                        "text": "American Airlines discusses aviation fuel emissions.",
                    }
                ],
                graph_sources={},
                trace=[],
            )

    monkeypatch.setattr(pipeline, "AgentRunner", FakeRunner)

    result = pipeline.answer_question(
        "Across between American Airlines and Apple, what is the main difference in carbon emission?",
        reasoning_mode="flash",
        retrieval_filters={
            "document_ids": ["aa", "apple"],
            "routing_hint": {
                "needs_agent": True,
                "entities": ["american airlines", "apple"],
                "target_document_ids": ["aa", "apple"],
                "sub_questions": ["Find carbon emission evidence for American Airlines.", "Find carbon emission evidence for Apple."],
            },
        },
        answer_intent={"mode": "hybrid", "confidence": 0.9},
    )

    assert result["answer"].startswith("AA reports")
    assert result["backend"] == "agent_test"
    assert result["routing"]["reflexion"]["missing_entities"] == ["apple"]


def test_stream_agent_path_emits_agent_done_payload(monkeypatch):
    def fail_prepare(**kwargs):
        raise AssertionError("agent stream path must not prepare retrieval context before routing")

    monkeypatch.setattr(pipeline, "_prepare_answer_context", fail_prepare)
    monkeypatch.setattr(
        pipeline,
        "decide_hybrid_path",
        lambda **kwargs: pipeline.HybridRouteDecision(
            path="agent",
            reason="test",
            confidence=0.9,
            budget=pipeline.AgentBudget(max_steps=1, deadline_seconds=90),
        ),
    )

    class FakeRunner:
        def __init__(self, registry, budget):
            self.registry = registry
            self.budget = budget

        def run(self, question, reasoning_mode, history_block, answer_intent="evidence", progress_callback=None):
            assert answer_intent == "hybrid"
            return pipeline.AgentRunResult(
                answer="Streamed agent answer",
                backend="agent_stream_test",
                sources=[],
                graph_sources={},
                trace=[],
            )

    monkeypatch.setattr(pipeline, "AgentRunner", FakeRunner)
    events = list(
        pipeline.stream_answer_question(
            "Compare Apple and Microsoft climate risks.",
            reasoning_mode="deep",
            retrieval_filters={"document_ids": ["a", "b"]},
            answer_intent={"mode": "hybrid", "confidence": 0.9},
        )
    )
    assert any(event.get("type") == "token" and event.get("text") == "Streamed agent answer" for event in events)
    done = [event for event in events if event.get("type") == "done"][-1]
    assert done["payload"]["path"] == "agent"
    assert done["payload"]["routing"]["strategy"] == "agent"


def test_rag_path_does_not_create_agent_runner(monkeypatch):
    prepare_called = {"value": False}

    def fake_prepare(**kwargs):
        prepare_called["value"] = True
        prepared = _prepared_context()
        prepared["answer_intent"] = {"mode": "evidence", "confidence": 0.8}
        prepared["allow_speculation"] = False
        return prepared

    monkeypatch.setattr(pipeline, "_prepare_answer_context", fake_prepare)
    monkeypatch.setattr(
        pipeline,
        "decide_hybrid_path",
        lambda **kwargs: pipeline.HybridRouteDecision(
            path="rag",
            reason="direct",
            confidence=0.8,
            budget=pipeline.AgentBudget(max_steps=0, deadline_seconds=25),
        ),
    )
    class FailRunner:
        def __init__(self, registry, budget):
            raise AssertionError("rag path must not create an agent runner")

    monkeypatch.setattr(pipeline, "AgentRunner", FailRunner)
    result = pipeline.answer_question(
        "What is the emissions target in this report?",
        reasoning_mode="flash",
        retrieval_filters={"document_ids": ["doc_costco"], "preferred_document_id": "doc_costco"},
        answer_intent={"mode": "evidence", "confidence": 0.8},
    )
    assert prepare_called["value"] is True
    assert result.get("path") != "agent"
    assert result["backend"] == "no_context"


def test_cross_report_evidence_agent_uses_hybrid_synthesis(monkeypatch):
    seen = {}

    def fail_prepare(**kwargs):
        raise AssertionError("agent path must not prepare retrieval context before routing")

    monkeypatch.setattr(pipeline, "_prepare_answer_context", fail_prepare)
    monkeypatch.setattr(
        pipeline,
        "decide_hybrid_path",
        lambda **kwargs: pipeline.HybridRouteDecision(
            path="agent",
            reason="cross_report",
            confidence=0.9,
            budget=pipeline.AgentBudget(max_steps=1, deadline_seconds=90),
        ),
    )

    class FakeRunner:
        def __init__(self, registry, budget):
            self.registry = registry
            self.budget = budget

        def run(self, question, reasoning_mode, history_block, answer_intent="evidence", progress_callback=None):
            seen["answer_intent"] = answer_intent
            return pipeline.AgentRunResult(
                answer="Limited comparison answer",
                backend="agent_test",
                sources=[],
                graph_sources={},
                trace=[],
            )

    monkeypatch.setattr(pipeline, "AgentRunner", FakeRunner)
    result = pipeline.answer_question(
        "Compare the climate transition risks across all reports and explain uncertainty with evidence.",
        reasoning_mode="deep",
        retrieval_filters={"document_ids": ["doc_costco"], "preferred_document_id": "doc_costco"},
        answer_intent={"mode": "evidence", "confidence": 0.9},
    )

    assert seen["answer_intent"] == "hybrid"
    assert result["answer_mode"] == "hybrid"
    assert result["answer"] == "Limited comparison answer"


def test_hybrid_insufficient_model_answer_gets_analysis_fallback(monkeypatch):
    def fake_prepare(**kwargs):
        prepared = _prepared_context()
        prepared["tier"] = "flash"
        prepared["reasoning_mode"] = "flash"
        prepared["answer_intent"] = {"mode": "hybrid", "confidence": 0.9}
        prepared["allow_speculation"] = True
        prepared["sources"] = [
            {
                "chunk_id": "chunk_1",
                "text": "The company discusses water risk and packaging initiatives.",
                "document_title": "coca cola",
            }
        ]
        return prepared

    monkeypatch.setattr(pipeline, "_prepare_answer_context", fake_prepare)
    monkeypatch.setattr(
        pipeline,
        "decide_hybrid_path",
        lambda **kwargs: pipeline.HybridRouteDecision(
            path="rag",
            reason="direct",
            confidence=0.8,
            budget=pipeline.AgentBudget(max_steps=0, deadline_seconds=12),
        ),
    )
    monkeypatch.setattr(pipeline, "RAG_ANSWER_MODE", "openai")
    monkeypatch.setattr(pipeline, "openai_answering_available", lambda: True)
    monkeypatch.setattr(pipeline, "generate_openai_rag_answer", lambda **kwargs: pipeline.INSUFFICIENT_CONTEXT_ANSWER)
    monkeypatch.setattr(
        pipeline,
        "_notify_unanswerable",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("hybrid fallback should not notify as unanswerable")),
    )

    result = pipeline.answer_question(
        "Predict the ESG score for cola",
        reasoning_mode="flash",
        retrieval_filters={"document_ids": []},
        answer_intent={"mode": "hybrid", "confidence": 0.9},
    )

    assert result["backend"] == "openai+hybrid_fallback"
    assert "General analysis" in result["answer"]
    assert "reliable ESG score" in result["answer"]


def test_stream_hybrid_insufficient_done_payload_gets_analysis_fallback(monkeypatch):
    def fake_prepare(**kwargs):
        prepared = _prepared_context()
        prepared["tier"] = "flash"
        prepared["reasoning_mode"] = "flash"
        prepared["answer_intent"] = {"mode": "hybrid", "confidence": 0.9}
        prepared["allow_speculation"] = True
        prepared["sources"] = [
            {
                "chunk_id": "chunk_1",
                "text": "The company discusses water risk and packaging initiatives.",
                "document_title": "coca cola",
            }
        ]
        return prepared

    monkeypatch.setattr(pipeline, "_prepare_answer_context", fake_prepare)
    monkeypatch.setattr(
        pipeline,
        "decide_hybrid_path",
        lambda **kwargs: pipeline.HybridRouteDecision(
            path="rag",
            reason="direct",
            confidence=0.8,
            budget=pipeline.AgentBudget(max_steps=0, deadline_seconds=12),
        ),
    )
    monkeypatch.setattr(pipeline, "RAG_ANSWER_MODE", "openai")
    monkeypatch.setattr(pipeline, "openai_answering_available", lambda: True)
    monkeypatch.setattr(pipeline, "stream_openai_rag_answer", lambda **kwargs: iter([pipeline.INSUFFICIENT_CONTEXT_ANSWER]))
    monkeypatch.setattr(
        pipeline,
        "_notify_unanswerable",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("hybrid fallback should not notify as unanswerable")),
    )

    events = list(
        pipeline.stream_answer_question(
            "Predict the ESG score for cola",
            reasoning_mode="flash",
            retrieval_filters={"document_ids": []},
            answer_intent={"mode": "hybrid", "confidence": 0.9},
        )
    )
    done = [event for event in events if event.get("type") == "done"][-1]

    assert done["payload"]["backend"] == "openai+hybrid_fallback"
    assert "General analysis" in done["payload"]["answer"]
    assert "reliable ESG score" in done["payload"]["answer"]
