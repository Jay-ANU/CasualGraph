import app


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
