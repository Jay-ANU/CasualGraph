from __future__ import annotations

import json
from unittest.mock import patch

from app import (
    RagAskRequest,
    _can_access_entry,
    _can_retrieve_entry,
    _collect_orphan_chunk_entries,
    _extract_query_entity_terms,
    _retrievable_registry_entries,
    _resolve_rag_request_context,
    _scope_document_ids_for_query,
)
import rag.vector_store as vector_store
from rag.rag_pipeline import INSUFFICIENT_CONTEXT_ANSWER, _graph_filters_from_retrieval_filters, answer_question


def _entry(document_id: str, title: str):
    return {
        "document_id": document_id,
        "title": title,
        "source": f"{title}.pdf",
        "paths": {},
    }


def test_extract_query_entity_terms_from_company_question():
    assert "apple" in _extract_query_entity_terms("I want to know the ESG strategy of Apple!")
    assert "costco" in _extract_query_entity_terms("What is Costco's ESG strategy?")
    assert "bhp" in _extract_query_entity_terms("What is BHP 2024 scope 1 emissions?")
    assert "american airlines" in _extract_query_entity_terms("American Airlines ESG strategy")
    assert "aa" in _extract_query_entity_terms("Tell me something about American Flight?")


def test_scope_document_ids_matches_requested_company():
    entries = [
        _entry("costco_doc", "Costco sustainability report 2025"),
        _entry("apple_doc", "Apple ESG report 2024"),
    ]

    matched_ids, terms = _scope_document_ids_for_query("I want to know the ESG strategy of Apple!", entries)

    assert "apple" in terms
    assert matched_ids == ["apple_doc"]


def test_scope_document_ids_matches_american_flight_alias_from_graph(tmp_path):
    graph_path = tmp_path / "airline_graph.json"
    graph_path.write_text(
        json.dumps({"nodes": [{"id": "American Airlines Group", "type": "Company"}]}),
        encoding="utf-8",
    )
    entries = [{
        "document_id": "airline_doc",
        "title": "uploaded sustainability report",
        "source": "report.pdf",
        "paths": {"graph": str(graph_path)},
    }]

    matched_ids, terms = _scope_document_ids_for_query("Tell me something about American Flight?", entries)

    assert "american airlines" in terms
    assert matched_ids == ["airline_doc"]


def test_scope_document_ids_returns_miss_for_unavailable_company():
    entries = [_entry("costco_doc", "Costco sustainability report 2025")]

    matched_ids, terms = _scope_document_ids_for_query("I want to know the ESG strategy of Apple!", entries)

    assert "apple" in terms
    assert matched_ids == []


def test_answer_question_entity_scope_miss_does_not_retrieve():
    with patch("rag.rag_pipeline._run_routed_retrieval") as retrieval_mock:
        result = answer_question(
            "I want to know the ESG strategy of Apple!",
            retrieval_filters={"entity_scope_miss": True, "entity_scope_terms": ["apple"]},
            history=[],
        )

    retrieval_mock.assert_not_called()
    assert result["answer"] == INSUFFICIENT_CONTEXT_ANSWER
    assert result["sources"] == []
    assert result["graph_sources"]["skipped_reason"] == "entity_scope_miss"


def test_anonymous_rag_context_marks_unavailable_company_as_scope_miss():
    request = RagAskRequest(question="I want to know the ESG strategy of Apple!", top_k=3)
    entries = [
        {"document_id": "costco-doc", "title": "Costco report", "document_group": "global_kb", "visibility_scope": "global"},
    ]

    with patch("app._collect_document_entries", return_value=entries):
        context = _resolve_rag_request_context(request, current_user=None)

    assert context["error_response"] is None
    assert context["filters"]["entity_scope_miss"] is True
    assert "apple" in context["filters"]["entity_scope_terms"]


def test_regular_user_cannot_list_global_kb_but_can_retrieve_it():
    user = {"id": "user-1", "role": "user"}
    global_entry = {"document_id": "global-doc", "document_group": "global_kb", "owner_user_id": "admin-1"}
    own_private_entry = {"document_id": "own-doc", "document_group": "user_private", "owner_user_id": "user-1"}
    other_private_entry = {"document_id": "other-doc", "document_group": "user_private", "owner_user_id": "user-2"}

    assert not _can_access_entry(user, global_entry)
    assert _can_access_entry(user, own_private_entry)
    assert not _can_access_entry(user, other_private_entry)
    assert _can_retrieve_entry(user, global_entry)
    assert _can_retrieve_entry(user, own_private_entry)
    assert not _can_retrieve_entry(user, other_private_entry)


def test_regular_user_rag_context_can_use_global_and_own_private_docs():
    request = RagAskRequest(question="Compare ESG strategy across reports", top_k=3)
    user = {"id": "user-1", "role": "user"}
    entries = [
        {"document_id": "global-doc", "title": "Global ESG prior", "document_group": "global_kb", "visibility_scope": "global", "owner_user_id": "admin-1"},
        {"document_id": "own-doc", "title": "User report", "document_group": "user_private", "owner_user_id": "user-1"},
    ]

    with patch("app._retrievable_registry_entries", return_value=entries):
        context = _resolve_rag_request_context(request, current_user=user)

    assert context["error_response"] is None
    assert context["filters"]["document_ids"] == []
    assert context["filters"]["owner_user_id"] == "user-1"


def test_regular_user_rag_context_includes_upload_audit_only_global_doc():
    request = RagAskRequest(question="Compare ESG strategy across reports", top_k=3)
    user = {"id": "user-1", "role": "user"}
    upload = {
        "document_id": "audit-global-doc",
        "title": "Global ESG prior",
        "filename": "global.pdf",
        "status": "completed",
        "document_group": "global_kb",
        "uploader": {"id": "admin-1"},
        "paths": {
            "processed_text_path": "data/processed/global.txt",
            "chunks_path": "data/chunks/global.json",
            "graph_path": "data/graph/global.json",
            "vector_store_path": "data/vector_store/global",
        },
    }

    with patch("app.document_registry.list_entries", return_value=[]), patch(
        "app.list_latest_uploads_by_document_id", return_value={"audit-global-doc": upload}
    ), patch("app._collect_orphan_chunk_entries", return_value=[]):
        entries = _retrievable_registry_entries(user)
        context = _resolve_rag_request_context(request, current_user=user)

    assert [entry["document_id"] for entry in entries] == ["audit-global-doc"]
    assert context["error_response"] is None
    assert context["filters"]["document_ids"] == []
    assert context["filters"]["owner_user_id"] == "user-1"


def test_collect_orphan_chunk_entries_builds_registry_fallback(tmp_path):
    chunks_path = tmp_path / "aa_sustainability_report_2022_20260501043104_chunks.jsonl"
    chunks_path.write_text(
        json.dumps({
            "chunk_id": "chunk_0",
            "text": "SUSTAINABILITY REPORT 2022",
            "document_id": "aa_sustainability_report_2022_20260501043104",
            "document_title": "aa-sustainability-report-2022",
            "document_group": "user_upload",
            "source_type": "uploaded_file",
            "domain": "general",
            "source": "aa-sustainability-report-2022.pdf",
        }) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "aa_sustainability_report_2022_20260501043104_graph.json").write_text(
        json.dumps({"nodes": [{"id": "American Airlines", "type": "Company"}]}),
        encoding="utf-8",
    )
    (tmp_path / "aa_sustainability_report_2022_20260501043104").mkdir()

    with patch("app.CHUNK_DIR", tmp_path), patch("app.GRAPH_DIR", tmp_path), patch("app.VECTOR_DIR", tmp_path):
        entries = _collect_orphan_chunk_entries(set())

    assert [entry["document_id"] for entry in entries] == ["aa_sustainability_report_2022_20260501043104"]
    assert entries[0]["paths"]["graph"].endswith("_graph.json")


def test_regular_user_explicit_document_ids_drop_other_private_docs():
    request = RagAskRequest(question="Compare selected reports", top_k=3, document_ids=["own-doc", "other-doc", "global-doc"])
    user = {"id": "user-1", "role": "user"}
    entries = [
        {"document_id": "global-doc", "title": "Global ESG prior", "document_group": "global_kb", "visibility_scope": "global", "owner_user_id": "admin-1"},
        {"document_id": "own-doc", "title": "User report", "document_group": "user_private", "owner_user_id": "user-1"},
    ]

    with patch("app._retrievable_registry_entries", return_value=entries):
        context = _resolve_rag_request_context(request, current_user=user)

    assert context["error_response"] is None
    assert context["filters"]["document_ids"] == ["own-doc", "global-doc"]
    assert context["filters"]["owner_user_id"] == "user-1"


def test_regular_user_inaccessible_preferred_document_is_rejected():
    request = RagAskRequest(question="Summarise this report", top_k=3, preferred_document_id="other-doc")
    user = {"id": "user-1", "role": "user"}
    entries = [
        {"document_id": "own-doc", "title": "User report", "document_group": "user_private", "owner_user_id": "user-1"},
    ]

    with patch("app._retrievable_registry_entries", return_value=entries):
        context = _resolve_rag_request_context(request, current_user=user)

    assert context["error_response"].status_code == 403


def test_regular_user_allowed_preferred_document_scopes_retrieval_and_graph():
    request = RagAskRequest(question="Summarise this report", top_k=3, preferred_document_id="own-doc")
    user = {"id": "user-1", "role": "user"}
    entries = [
        {"document_id": "global-doc", "title": "Global ESG prior", "document_group": "global_kb", "visibility_scope": "global", "owner_user_id": "admin-1"},
        {"document_id": "own-doc", "title": "User report", "document_group": "user_private", "owner_user_id": "user-1"},
    ]

    with patch("app._retrievable_registry_entries", return_value=entries):
        context = _resolve_rag_request_context(request, current_user=user)

    assert context["error_response"] is None
    assert context["filters"]["document_ids"] == ["own-doc"]
    assert context["filters"]["preferred_document_id"] == "own-doc"
    graph_filters = _graph_filters_from_retrieval_filters(context["filters"])
    assert graph_filters["document_ids"] == ["own-doc"]


def test_regular_user_entity_query_falls_back_to_global_kb_search():
    request = RagAskRequest(question="What would be the effects to Apple's share price according to its ESG strategy?", top_k=3)
    user = {"id": "user-1", "role": "user"}
    entries = [
        {"document_id": "global-doc", "title": "Global ESG prior", "document_group": "global_kb", "visibility_scope": "global", "owner_user_id": "admin-1"},
        {"document_id": "own-doc", "title": "User report", "document_group": "user_private", "owner_user_id": "user-1"},
    ]

    with patch("app._retrievable_registry_entries", return_value=entries):
        context = _resolve_rag_request_context(request, current_user=user)

    assert context["error_response"] is None
    assert context["filters"]["document_ids"] == ["global-doc"]
    assert context["filters"].get("entity_scope_miss") is not True


def test_admin_can_access_global_kb_entries():
    admin = {"id": "admin-1", "role": "admin"}
    global_entry = {"document_id": "global-doc", "document_group": "global_kb", "owner_user_id": "admin-1"}

    assert _can_access_entry(admin, global_entry)


def test_anonymous_explicit_private_document_id_is_rejected():
    request = RagAskRequest(question="Summarise hidden report", top_k=3, document_ids=["private-doc"])
    entries = [
        {"document_id": "global-doc", "title": "Global ESG prior", "document_group": "global_kb", "visibility_scope": "global", "owner_user_id": "admin-1"},
        {"document_id": "private-doc", "title": "Private report", "document_group": "user_private", "owner_user_id": "user-1"},
    ]

    with patch("app._collect_document_entries", return_value=entries):
        context = _resolve_rag_request_context(request, current_user=None)

    assert context["error_response"].status_code == 403


def test_anonymous_broad_query_is_limited_to_public_document_ids():
    request = RagAskRequest(question="Compare ESG strategy across reports", top_k=3)
    entries = [
        {"document_id": "global-doc", "title": "Global ESG prior", "document_group": "global_kb", "visibility_scope": "global", "owner_user_id": "admin-1"},
        {"document_id": "private-doc", "title": "Private report", "document_group": "user_private", "owner_user_id": "user-1"},
    ]

    with patch("app._collect_document_entries", return_value=entries):
        context = _resolve_rag_request_context(request, current_user=None)

    assert context["error_response"] is None
    assert context["filters"]["document_ids"] == ["global-doc"]


def test_local_vector_filters_allow_global_but_not_other_private_docs():
    rows = [
        {"document_id": "own-doc", "owner_user_id": "user-1", "document_group": "user_private"},
        {"document_id": "other-doc", "owner_user_id": "user-2", "document_group": "user_private"},
        {"document_id": "global-doc", "owner_user_id": "admin-1", "document_group": "global_kb", "visibility_scope": "global"},
    ]

    filtered = vector_store._apply_local_filters(rows, {"owner_user_id": "user-1"})

    assert [row["document_id"] for row in filtered] == ["own-doc", "global-doc"]


def test_pinecone_filter_enforces_owner_or_global_scope():
    metadata_filter = vector_store._build_pinecone_filter({"owner_user_id": "user-1"})

    assert metadata_filter == {
        "$or": [
            {"owner_user_id": {"$eq": "user-1"}},
            {"visibility_scope": {"$eq": "global"}},
            {"document_group": {"$eq": "global_kb"}},
        ]
    }
