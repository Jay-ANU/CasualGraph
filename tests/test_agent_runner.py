from rag.agent_runner import AgentRunner
from rag.agent_types import AgentBudget, AgentToolObservation


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def call(self, tool_name, arguments):
        self.calls.append((tool_name, arguments))
        if tool_name == "search_documents":
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
