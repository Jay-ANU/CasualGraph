from rag.agent_tools import AgentToolRegistry


def test_search_documents_returns_typed_observation(monkeypatch):
    def fake_retrieve_context(query, top_k, filters, use_hyde=False, history_block=""):
        return [{"chunk_id": "chunk_1", "document_id": "doc_1", "text": "Apple reports Scope 1 progress.", "score": 0.9}]

    monkeypatch.setattr("rag.agent_tools.retrieve_context", fake_retrieve_context)
    registry = AgentToolRegistry(filters={"document_ids": ["doc_1"]}, history_block="")
    observation = registry.call("search_documents", {"query": "Apple Scope 1", "top_k": 3, "strategy": "vector"})
    assert observation.ok is True
    assert observation.tool == "search_documents"
    assert observation.data["sources"][0]["chunk_id"] == "chunk_1"


def test_search_documents_rejects_wrong_entity_chunk_when_expected_entity_is_set(monkeypatch):
    def fake_retrieve_context(query, top_k, filters, use_hyde=False, history_block=""):
        return [
            {
                "chunk_id": "aa_chunk",
                "document_id": "aa_doc",
                "document_title": "American Airlines sustainability",
                "text": "American Airlines reports carbon emission reductions from aviation fuel efficiency.",
                "score": 0.94,
            }
        ]

    monkeypatch.setattr("rag.agent_tools.retrieve_context", fake_retrieve_context)
    registry = AgentToolRegistry(filters={"document_ids": ["aa_doc", "apple_doc"]}, history_block="")

    observation = registry.call(
        "search_documents",
        {
            "query": "Find carbon emission evidence for Apple.",
            "top_k": 3,
            "strategy": "vector",
            "expected_entity": "Apple",
            "document_ids": ["apple_doc"],
        },
    )

    assert observation.ok is False
    assert observation.error == "no_sources"
    assert observation.data["sources"] == []


def test_get_graph_context_handles_disabled_graph(monkeypatch):
    def fake_graph_context(question, filters=None, hops=None, limit=None, max_triples=None):
        return {"text": "", "matched_entities": [], "nodes": [], "edges": [], "skipped_reason": "neo4j_not_configured"}

    monkeypatch.setattr("rag.agent_tools.build_graph_context", fake_graph_context)
    registry = AgentToolRegistry(filters={}, history_block="")
    observation = registry.call("get_graph_context", {"question": "Apple governance risk", "limit": 10})
    assert observation.ok is False
    assert observation.error == "neo4j_not_configured"


def test_unknown_tool_fails_without_exception():
    registry = AgentToolRegistry(filters={}, history_block="")
    observation = registry.call("missing_tool", {})
    assert observation.ok is False
    assert "Unknown tool" in str(observation.error)
