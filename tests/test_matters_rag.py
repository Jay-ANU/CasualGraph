"""WP1-C RAG scoping: ``RagAskRequest.matter_id`` restricts the resolvers to the matter's documents,
refuses non-members (403 ``matter_forbidden``) and applies the intersection rule."""

from __future__ import annotations

import asyncio
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

import app
import document_registry
from api.routers import rag as rag_router
from services import auth as auth_service
from services import db as db_service
from services import matters, rag_context


@pytest.fixture
def auth_db(monkeypatch, tmp_path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(db_service, "_DB_PATH", str(db_path))
    monkeypatch.setenv("AUTH_DB_PATH", str(db_path))
    monkeypatch.setattr(document_registry, "DOCUMENT_REGISTRY_FILE", tmp_path / "registry.json")
    asyncio.run(db_service._init_auth_db())
    # No model calls from the resolvers.
    monkeypatch.setattr(rag_context, "_resolve_document_ids_with_deepseek", lambda question, candidates, query_terms: [])
    monkeypatch.setattr(rag_context, "_route_request_with_deepseek", lambda question, entries: None)
    return db_path


def _user(db_path, user_id: str, role: str = "user") -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO users (id, email, username, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, f"{user_id}@example.com", user_id, "x", role, "2026-01-01T00:00:00+00:00"),
        )
    return {"id": user_id, "email": f"{user_id}@example.com", "username": user_id, "role": role}


def _entry(document_id: str, owner: str, title: str, *, group: str = "user_private", visibility: str = "private") -> dict:
    return {
        "document_id": document_id,
        "title": title,
        "source": f"{document_id}.pdf",
        "document_group": group,
        "owner_user_id": owner,
        "visibility_scope": visibility,
        "paths": {},
    }


ENTRIES = [
    _entry("a_in", "alice", "Supply agreement"),
    _entry("a_out", "alice", "Office lease"),
    _entry("b_in", "bob", "Supply agreement schedule"),
    _entry("kb", "admin", "Contract law primer", group="global_kb", visibility="global"),
]


@pytest.fixture
def scoped(auth_db, monkeypatch):
    """alice leads a matter holding a_in and bob's b_in; a_out and the global kb stay outside."""
    alice, bob = _user(auth_db, "alice"), _user(auth_db, "bob")
    outsider, admin = _user(auth_db, "outsider"), _user(auth_db, "admin", role="admin")
    matter = matters.create_matter(alice, name="Supply dispute")
    matters.add_member(matter["id"], alice, member_user_id="bob", role="member")
    with sqlite3.connect(auth_db) as conn:
        conn.executemany(
            "INSERT INTO matter_documents (matter_id, document_id, added_by, added_at) VALUES (?, ?, 'alice', 'now')",
            [(matter["id"], "a_in"), (matter["id"], "b_in")],
        )
    monkeypatch.setattr(rag_context, "_retrievable_registry_entries", lambda current_user, include_invalid=False: list(ENTRIES))
    return {"matter": matter, "alice": alice, "bob": bob, "outsider": outsider, "admin": admin}


def _ask(question: str = "What are the delivery obligations?", **fields) -> rag_context.RagAskRequest:
    return rag_context.RagAskRequest(question=question, **fields)


def _forbidden(context) -> dict:
    response = context["error_response"]
    assert response is not None and response.status_code == 403
    return json.loads(response.body)


def test_member_with_matter_is_restricted_to_the_matter_documents(scoped):
    matter_id = scoped["matter"]["id"]

    context = rag_context._resolve_rag_request_context(_ask(matter_id=matter_id), scoped["bob"])
    unscoped = rag_context._resolve_rag_request_context(_ask(), scoped["bob"])

    assert context["error_response"] is None
    assert context["filters"]["document_ids"] == ["a_in", "b_in"]
    assert context["filters"]["owner_user_id"] == "bob"  # the Phase 0 owner filter stays
    assert context["matter_id"] == matter_id and context["filters"]["matter_id"] == matter_id
    # Without a matter the old broad behaviour is unchanged.
    assert unscoped["filters"]["document_ids"] == [] and unscoped["matter_id"] is None
    assert "matter_id" not in unscoped["filters"]


def test_explicit_documents_are_intersected_with_the_matter(scoped):
    matter_id = scoped["matter"]["id"]

    partial = rag_context._resolve_rag_request_context(
        _ask(matter_id=matter_id, document_ids=["a_in", "a_out"], preferred_document_id="a_out"), scoped["alice"]
    )
    outside = rag_context._resolve_rag_request_context(_ask(matter_id=matter_id, document_ids=["a_out", "kb"]), scoped["alice"])
    preferred_outside = rag_context._resolve_rag_request_context(_ask(matter_id=matter_id, preferred_document_id="a_out"), scoped["alice"])

    assert partial["error_response"] is None
    assert partial["filters"]["document_ids"] == ["a_in"]
    assert partial["filters"]["preferred_document_id"] is None
    assert _forbidden(outside)["error"] == "matter_forbidden"
    assert _forbidden(preferred_outside)["error"] == "matter_forbidden"


def test_non_members_anonymous_callers_and_platform_admins_are_refused(scoped):
    request = _ask(matter_id=scoped["matter"]["id"])

    for user in (scoped["outsider"], None, scoped["admin"]):
        context = rag_context._resolve_rag_request_context(request, user)
        general = rag_context._resolve_general_rag_request_context(request, user, [], "disabled")
        body = _forbidden(context)
        assert body["error"] == "matter_forbidden" and body["answer"] == "" and body["sources"] == []
        assert _forbidden(general)["error"] == "matter_forbidden"
        assert context["matter_id"] == scoped["matter"]["id"]
    unknown = rag_context._resolve_rag_request_context(_ask(matter_id="no-such-matter"), scoped["alice"])
    assert _forbidden(unknown)["error"] == "matter_forbidden"


def test_general_resolver_applies_the_same_scope(scoped):
    matter_id = scoped["matter"]["id"]

    context = rag_context._resolve_general_rag_request_context(
        _ask(matter_id=matter_id, document_ids=["a_in", "a_out"]), scoped["alice"], [], "disabled"
    )
    outside = rag_context._resolve_general_rag_request_context(
        _ask(matter_id=matter_id, document_ids=["a_out"]), scoped["alice"], [], "disabled"
    )

    assert context["error_response"] is None
    assert context["filters"]["document_ids"] == ["a_in"]
    assert context["filters"]["owner_user_id"] == "alice"
    assert context["matter_id"] == matter_id and context["filters"]["answer_mode"] == "general"
    assert _forbidden(outside)["error"] == "matter_forbidden"


def test_an_entity_no_title_names_still_searches_the_whole_matter(scoped):
    question = "What does Zenith Mobility owe under the schedule?"

    in_matter = rag_context._resolve_rag_request_context(_ask(question, matter_id=scoped["matter"]["id"]), scoped["alice"])
    without_matter = rag_context._resolve_rag_request_context(_ask(question), scoped["alice"])

    assert in_matter["error_response"] is None
    assert in_matter["filters"]["document_ids"] == ["a_in", "b_in"]
    assert not in_matter["filters"].get("entity_scope_miss")
    # Outside a matter the Phase 0 behaviour stays: fall back to the global KB.
    assert without_matter["filters"]["document_ids"] == ["kb"]


def test_admin_member_is_scoped_to_the_matter_not_the_whole_corpus(scoped):
    matter_id = scoped["matter"]["id"]
    matters.add_member(matter_id, scoped["alice"], member_user_id="admin", role="viewer")

    context = rag_context._resolve_rag_request_context(_ask(matter_id=matter_id), scoped["admin"])

    assert context["error_response"] is None
    assert context["filters"]["document_ids"] == ["a_in", "b_in"]
    assert "owner_user_id" not in context["filters"]


def test_a_matter_without_retrievable_documents_is_refused_not_widened(scoped):
    empty = matters.create_matter(scoped["alice"], name="Empty matter")

    context = rag_context._resolve_rag_request_context(_ask(matter_id=empty["id"]), scoped["alice"])
    general = rag_context._resolve_general_rag_request_context(_ask(matter_id=empty["id"]), scoped["alice"], [], "disabled")

    assert _forbidden(context)["error"] == "no_accessible_documents"
    # General answers do not retrieve without a resolved document scope, so an empty scope is safe there.
    assert general["error_response"] is None and general["filters"]["document_ids"] == []


def test_rag_ask_route_passes_matter_id_through_and_returns_403(scoped, monkeypatch):
    monkeypatch.setattr(rag_router, "classify_answer_intent", lambda query, history_block="": {"mode": "evidence"})
    token = auth_service._make_token("outsider", "outsider@example.com")

    response = TestClient(app.app).post(
        "/rag/ask",
        json={"question": "What are the delivery obligations?", "matter_id": scoped["matter"]["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["error"] == "matter_forbidden"
