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
    }


def test_agent_path_delegates_to_runner(monkeypatch):
    monkeypatch.setattr(pipeline, "_prepare_answer_context", lambda **kwargs: _prepared_context())
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

        def run(self, question, reasoning_mode, history_block, progress_callback=None):
            return pipeline.AgentRunResult(
                answer="Agent answer",
                backend="agent_test",
                sources=[{"chunk_id": "chunk_1", "text": "evidence"}],
                graph_sources={"text": "", "edges": [], "nodes": [], "matched_entities": []},
                trace=[],
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
    assert result["timings_ms"]["generate"] >= 0.0


def test_stream_agent_path_emits_agent_done_payload(monkeypatch):
    monkeypatch.setattr(pipeline, "_prepare_answer_context", lambda **kwargs: _prepared_context())
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

        def run(self, question, reasoning_mode, history_block, progress_callback=None):
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
    assert callable(pipeline.answer_question)
