from rag.agent_runner import AgentRunner
from rag.agent_types import AgentBudget, AgentToolObservation


class FakeRegistry:
    def __init__(self, filters=None):
        self.calls = []
        self.filters = filters or {}

    def call(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if tool_name == "search_documents":
            expected_entity = str(arguments.get("expected_entity") or "")
            if expected_entity == "American Airlines":
                return AgentToolObservation(
                    tool=tool_name,
                    ok=True,
                    summary="Found 1 relevant source chunk.",
                    data={
                        "sources": [
                            {
                                "chunk_id": "aa_chunk",
                                "document_id": "aa_doc",
                                "document_title": "American Airlines sustainability",
                                "text": "American Airlines discloses aviation fuel emissions.",
                            }
                        ]
                    },
                )
            if expected_entity == "Apple":
                return AgentToolObservation(
                    tool=tool_name,
                    ok=True,
                    summary="Found 1 relevant source chunk.",
                    data={
                        "sources": [
                            {
                                "chunk_id": "apple_chunk",
                                "document_id": "apple_doc",
                                "document_title": "Apple ESG",
                                "text": "Apple discloses operational emissions reductions.",
                            }
                        ]
                    },
                )
            return AgentToolObservation(
                tool=tool_name,
                ok=True,
                summary="Found 1 relevant source chunk.",
                data={"sources": [{"chunk_id": "chunk_1", "document_id": "doc_1", "text": "Apple discloses governance oversight."}]},
            )
        if tool_name == "get_graph_context":
            return AgentToolObservation(
                tool=tool_name,
                ok=False,
                summary="Graph returned 0 edges.",
                data={"graph": {"text": "", "edges": [], "nodes": [], "matched_entities": []}},
                error="no_entity_match",
            )
        return AgentToolObservation(tool=tool_name, ok=True, summary="ok", data={})


def test_runner_respects_max_steps():
    registry = FakeRegistry()
    runner = AgentRunner(registry=registry, budget=AgentBudget(max_steps=1, deadline_seconds=90))
    result = runner.run(question="Compare governance risks", reasoning_mode="deep", history_block="")
    assert len(registry.calls) == 1
    assert result.partial is True
    assert result.partial_reason == "max_steps_reached"


def test_runner_collects_sources_and_trace():
    registry = FakeRegistry()
    runner = AgentRunner(registry=registry, budget=AgentBudget(max_steps=3, deadline_seconds=90))
    result = runner.run(question="Compare governance risks", reasoning_mode="deep", history_block="")
    assert result.sources[0]["chunk_id"] == "chunk_1"
    assert any(step.tool == "search_documents" and step.status == "completed" for step in result.trace)
    assert result.answer


def test_runner_trace_exposes_plan_execute_react_and_reflexion_phases():
    registry = FakeRegistry(
        filters={
            "routing_hint": {
                "needs_agent": True,
                "entities": ["American Airlines", "Apple"],
                "target_document_ids": ["aa_doc", "apple_doc"],
                "sub_questions": [
                    "Find carbon emission evidence for American Airlines.",
                    "Find carbon emission evidence for Apple.",
                ],
            }
        }
    )
    runner = AgentRunner(registry=registry, budget=AgentBudget(max_steps=5, deadline_seconds=90))

    result = runner.run(
        question="Across between American Airlines and Apple, what is the main difference in carbon emission?",
        reasoning_mode="flash",
        history_block="",
        answer_intent="hybrid",
    )

    events = [step.to_dict() for step in result.trace]
    assert events[0]["phase"] == "plan"
    assert events[0]["plan"][0]["tool"] == "search_documents"
    assert events[0]["plan"][0]["expected_entity"] == "American Airlines"
    assert events[0]["plan"][1]["expected_entity"] == "Apple"

    action_count = len(registry.calls)
    for plan_step in range(1, action_count + 1):
        phases = [event["phase"] for event in events if event.get("plan_step") == plan_step]
        assert phases[:3] == ["thought", "action", "observation"]

    assert not [event for event in events if event.get("status") == "running"]

    reflexion_events = [event for event in events if event.get("phase") == "reflexion"]
    assert reflexion_events
    assert reflexion_events[-1]["reflexion"]["status"] == "complete"
    assert result.reflexion["status"] == "complete"


def test_runner_replans_searches_from_routing_sub_questions():
    registry = FakeRegistry(
        filters={
            "routing_hint": {
                "needs_agent": True,
                "sub_questions": [
                    "Find carbon emission evidence for American Airlines.",
                    "Find carbon emission evidence for Apple.",
                ],
            }
        }
    )
    runner = AgentRunner(registry=registry, budget=AgentBudget(max_steps=4, deadline_seconds=90))

    runner.run(
        question="Across between American Airlines and Apple, what is the main difference in carbon emission?",
        reasoning_mode="flash",
        history_block="",
        answer_intent="hybrid",
    )

    search_queries = [arguments["query"] for tool, arguments in registry.calls if tool == "search_documents"]
    assert search_queries[:2] == [
        "Find carbon emission evidence for American Airlines.",
        "Find carbon emission evidence for Apple.",
    ]


def test_runner_scopes_entity_sub_questions_to_target_documents():
    registry = FakeRegistry(
        filters={
            "routing_hint": {
                "needs_agent": True,
                "entities": ["American Airlines", "Apple"],
                "target_document_ids": ["aa_doc", "apple_doc"],
                "sub_questions": [
                    "Find carbon emission evidence for American Airlines.",
                    "Find carbon emission evidence for Apple.",
                ],
            }
        }
    )
    runner = AgentRunner(registry=registry, budget=AgentBudget(max_steps=4, deadline_seconds=90))

    runner.run(
        question="Across between American Airlines and Apple, what is the main difference in carbon emission?",
        reasoning_mode="flash",
        history_block="",
        answer_intent="hybrid",
    )

    search_args = [arguments for tool, arguments in registry.calls if tool == "search_documents"]
    assert search_args[0]["expected_entity"] == "American Airlines"
    assert search_args[0]["document_ids"] == ["aa_doc"]
    assert search_args[1]["expected_entity"] == "Apple"
    assert search_args[1]["document_ids"] == ["apple_doc"]


def test_runner_scopes_graph_queries_to_target_documents():
    registry = FakeRegistry(
        filters={
            "routing_hint": {
                "needs_agent": True,
                "entities": ["American Airlines", "Apple"],
                "target_document_ids": ["aa_doc", "apple_doc"],
                "sub_questions": [
                    "Find carbon emission evidence for American Airlines.",
                    "Find carbon emission evidence for Apple.",
                ],
            }
        }
    )
    runner = AgentRunner(registry=registry, budget=AgentBudget(max_steps=5, deadline_seconds=90))

    runner.run(
        question="Across between American Airlines and Apple, what is the main difference in carbon emission?",
        reasoning_mode="flash",
        history_block="",
        answer_intent="hybrid",
    )

    graph_args = [arguments for tool, arguments in registry.calls if tool == "get_graph_context"]
    assert [args.get("expected_entity") for args in graph_args] == ["American Airlines", "Apple"]
    assert [args.get("document_ids") for args in graph_args] == [["aa_doc"], ["apple_doc"]]


def test_runner_replans_missing_entity_before_synthesis():
    class ReplanningRegistry:
        def __init__(self):
            self.calls = []
            self.filters = {
                "routing_hint": {
                    "needs_agent": True,
                    "entities": ["American Airlines", "Apple"],
                    "sub_questions": [
                        "Find carbon emission evidence for American Airlines.",
                        "Find carbon emission evidence for Apple.",
                    ],
                }
            }

        def call(self, tool_name, arguments):
            self.calls.append((tool_name, arguments))
            if tool_name == "search_documents":
                if str(arguments.get("expected_entity") or "").lower() == "apple":
                    if arguments.get("replan_reason") != "missing_entity_evidence":
                        return AgentToolObservation(
                            tool=tool_name,
                            ok=False,
                            summary="No Apple evidence in first pass.",
                            data={"sources": []},
                            error="no_sources",
                        )
                    return AgentToolObservation(
                        tool=tool_name,
                        ok=True,
                        summary="Found Apple evidence.",
                        data={
                            "sources": [
                                {
                                    "chunk_id": "apple_chunk",
                                    "document_id": "apple_doc",
                                    "document_title": "Apple ESG",
                                    "text": "Apple reports carbon emission reductions in its operations.",
                                }
                            ]
                        },
                    )
                return AgentToolObservation(
                    tool=tool_name,
                    ok=True,
                    summary="Found AA evidence.",
                    data={
                        "sources": [
                            {
                                "chunk_id": "aa_chunk",
                                "document_id": "aa_doc",
                                "document_title": "American Airlines sustainability",
                                "text": "American Airlines reports aviation fuel carbon emissions.",
                            }
                        ]
                    },
                )
            if tool_name == "get_graph_context":
                return AgentToolObservation(
                    tool=tool_name,
                    ok=False,
                    summary="Graph returned 0 edges.",
                    data={"graph": {"text": "", "edges": [], "nodes": [], "matched_entities": []}},
                    error="no_entity_match",
                )
            return AgentToolObservation(tool=tool_name, ok=True, summary="ok", data={})

    registry = ReplanningRegistry()
    runner = AgentRunner(registry=registry, budget=AgentBudget(max_steps=5, deadline_seconds=90))

    result = runner.run(
        question="Across between American Airlines and Apple, what is the main difference in carbon emission?",
        reasoning_mode="flash",
        history_block="",
        answer_intent="hybrid",
    )

    search_args = [arguments for tool, arguments in registry.calls if tool == "search_documents"]
    apple_searches = [arguments for arguments in search_args if arguments.get("expected_entity") == "Apple"]
    assert len(apple_searches) == 2
    assert apple_searches[-1]["replan_reason"] == "missing_entity_evidence"
    replan_events = [step.to_dict() for step in result.trace if step.to_dict().get("phase") == "replan"]
    assert replan_events
    assert replan_events[0]["plan"][0]["expected_entity"] == "Apple"
    assert [source["document_id"] for source in result.sources] == ["aa_doc", "apple_doc"]
    assert result.partial is False


def test_runner_hybrid_synthesis_replaces_bare_insufficient_answer(monkeypatch):
    def fake_generate(**kwargs):
        assert kwargs["answer_intent"] == "hybrid"
        assert kwargs["allow_speculation"] is True
        return "The provided reports do not contain enough information to answer this question."

    monkeypatch.setattr("rag.agent_runner._openai_answering_available", lambda: True)
    monkeypatch.setattr("rag.openai_answering.generate_openai_rag_answer", fake_generate)

    registry = FakeRegistry()
    runner = AgentRunner(registry=registry, budget=AgentBudget(max_steps=3, deadline_seconds=90))
    result = runner.run(
        question="Compare the climate transition risks across all reports and explain uncertainty with evidence.",
        reasoning_mode="flash",
        history_block="",
        answer_intent="hybrid",
    )

    assert result.backend == "openai+hybrid_fallback"
    assert "not broad enough" in result.answer
    assert "Available evidence" in result.answer
