import app
import json

from rag import retriever


def _user(user_id: str = "user_1"):
    return {"id": user_id, "role": "user"}


def _legacy_aa_entry():
    return {
        "document_id": "aa_sustainability_report_2022_20260501043104",
        "title": "aa-sustainability-report-2022",
        "source": "aa-sustainability-report-2022.pdf",
        "document_group": "user_upload",
        "owner_user_id": "",
        "visibility_scope": "",
        "paths": {"graph": ""},
    }


def test_legacy_ownerless_user_upload_is_retrievable_for_logged_in_users():
    entry = _legacy_aa_entry()

    assert app._can_retrieve_entry(_user(), entry)


def test_exact_document_scope_does_not_require_vector_owner_metadata(monkeypatch):
    entry = _legacy_aa_entry()
    monkeypatch.setattr(app, "_retrievable_registry_entries", lambda current_user, include_invalid=False: [entry])

    context = app._resolve_rag_request_context(
        app.RagAskRequest(question="Hi, What should I notice about American Flight?"),
        _user(),
    )

    assert context["error_response"] is None
    assert context["filters"]["document_ids"] == ["aa_sustainability_report_2022_20260501043104"]
    assert "owner_user_id" not in context["filters"]


def test_retrieve_context_falls_back_to_scoped_local_chunks_when_vector_is_empty(monkeypatch, tmp_path):
    doc_id = "aa_sustainability_report_2022_20260501043104"
    chunks_path = tmp_path / f"{doc_id}_chunks.jsonl"
    chunks = [
        {
            "chunk_id": "chunk_1",
            "document_id": doc_id,
            "document_title": "aa-sustainability-report-2022",
            "text": "About American Airlines and this report. American Airlines operates a major network carrier.",
        },
        {
            "chunk_id": "chunk_99",
            "document_id": doc_id,
            "document_title": "aa-sustainability-report-2022",
            "text": "Unrelated appendix text.",
        },
    ]
    chunks_path.write_text("\n".join(json.dumps(row) for row in chunks), encoding="utf-8")
    monkeypatch.setattr(retriever, "CHUNK_DIR", tmp_path)
    monkeypatch.setattr(retriever, "_search_with_payload_retry", lambda **kwargs: [])

    rows = retriever.retrieve_context(
        query="Hi, What should I notice about American Flight?",
        top_k=3,
        filters={"document_ids": [doc_id]},
    )

    assert rows
    assert rows[0]["document_id"] == doc_id
    assert rows[0]["chunk_id"] == "chunk_1"
    assert rows[0]["retrieval_channel"] == "local_scoped_fallback"
