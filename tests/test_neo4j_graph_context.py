from __future__ import annotations

from unittest.mock import patch

from graph.neo4j_store import Neo4jGraphStore, _build_fulltext_query, _fulltext_index_missing
from rag.graph_context import build_graph_context


class _SessionContext:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


class _RecordingSession:
    def __init__(self, *, fail_fulltext: bool = False, fail_all: bool = False, error_type=RuntimeError):
        self.fail_fulltext = fail_fulltext
        self.fail_all = fail_all
        self.error_type = error_type
        self.queries = []

    def run(self, query, **params):
        self.queries.append((query, params))
        if self.fail_all:
            raise RuntimeError("boom")
        if self.fail_fulltext and "CREATE FULLTEXT INDEX" in query:
            raise self.error_type("legacy fulltext syntax required")
        return self

    def data(self):
        return []


def _make_store(session):
    store = object.__new__(Neo4jGraphStore)
    store._session = lambda: _SessionContext(session)
    store._run_with_reconnect = lambda operation: operation()
    return store


def test_build_fulltext_query_escapes_terms():
    query = _build_fulltext_query(["bhp", 'scope"1', r"risk\term"])

    assert query == '"bhp" OR "scope\\"1" OR "risk\\\\term"'


def test_fulltext_index_missing_detects_index_errors():
    assert _fulltext_index_missing(Exception("NoSuchIndex entity_name_fulltext"))
    assert _fulltext_index_missing(Exception("fulltext index error: no such index"))
    assert not _fulltext_index_missing(Exception("different failure"))


def test_setup_schema_falls_back_to_legacy_fulltext_index(monkeypatch):
    class FakeClientError(Exception):
        pass

    session = _RecordingSession(fail_fulltext=True, error_type=FakeClientError)
    store = _make_store(session)
    monkeypatch.setattr("graph.neo4j_store.ClientError", FakeClientError)

    store.setup_schema()

    assert any("CREATE FULLTEXT INDEX entity_name_fulltext" in query for query, _ in session.queries)
    assert any("db.index.fulltext.createNodeIndex" in query for query, _ in session.queries)


def test_setup_schema_swallow_errors_and_logs(capsys):
    session = _RecordingSession(fail_all=True)
    store = _make_store(session)

    store.setup_schema()

    captured = capsys.readouterr()
    assert "[neo4j.schema] setup skipped:" in captured.out


def test_build_graph_context_logs_timing_and_formats_edges(capsys):
    fake_subgraph = {
        "matched_entities": [{"id": "bhp", "name": "BHP", "type": "ORG", "score": 1.0}],
        "nodes": [
            {"id": "bhp", "name": "BHP"},
            {"id": "scope_1", "name": "Scope 1 emissions"},
        ],
        "edges": [
            {
                "source": "bhp",
                "target": "scope_1",
                "relation_type": "reports",
                "confidence": 0.91,
                "chunk_id": "chunk-1",
                "evidence": "BHP reports Scope 1 emissions.",
            }
        ],
    }

    class FakeStore:
        def find_relevant_subgraph(self, **kwargs):
            return fake_subgraph

    with patch("rag.graph_context.graph_context_enabled", return_value=True), patch(
        "graph.neo4j_store.neo4j_enabled", return_value=True
    ), patch("graph.neo4j_store.get_neo4j_store", return_value=FakeStore()):
        result = build_graph_context("What does BHP report?")

    captured = capsys.readouterr()
    assert "[rag.graph.timing]" in captured.out
    assert "entities=1" in captured.out
    assert "nodes=2" in captured.out
    assert "edges=1" in captured.out
    assert "BHP" in result["text"]
    assert "reports" in result["text"]
    assert len(result["edges"]) == 1


def test_build_graph_context_no_entity_match_logs_timing(capsys):
    class FakeStore:
        def find_relevant_subgraph(self, **kwargs):
            return {"matched_entities": [], "nodes": [], "edges": []}

    with patch("rag.graph_context.graph_context_enabled", return_value=True), patch(
        "graph.neo4j_store.neo4j_enabled", return_value=True
    ), patch("graph.neo4j_store.get_neo4j_store", return_value=FakeStore()):
        result = build_graph_context("Unknown entity?")

    captured = capsys.readouterr()
    assert result["skipped_reason"] == "no_entity_match"
    assert "[rag.graph.timing]" in captured.out
    assert "entities=0" in captured.out
