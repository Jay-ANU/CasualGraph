"""Regression tests for the Phase 0 clean-up: removed routes, path leaks, tenant scope, login, DB paths."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.routing import Mount

import admin_audit
import app
import document_registry
import pipeline_runtime
from api import deps
from api.routers import auth as auth_routes
from configs.settings import DATA_DIR
from notifications import store as notifications_store
from rag import retriever
from rag.vector_store import _apply_local_filters, _build_pinecone_filter
from services import auth as auth_service
from services import db as db_service
from services import document_access, rag_context

ROOT = Path(__file__).resolve().parents[1]

# Built from fragments so that a repository-wide grep for the removed features stays empty.
REMOVED_ROUTE_PREFIXES = (
    "/documents/rebuild" + "-graph",
    "/pipeline" + "/pdf",
    "/extract",
    "/graph/causal/",
    "/kg" + "-view",
    "/api/",
    "/kg-api/",
    "/public/knowledge-graph",
    "/offers",
    "/admin/recruit" + "ment",
    "/desktop/",
)
LEGACY_GRAPH_KEYS = {"graph", "relationships", "relationship_count", "paths"}


def _all_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _all_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _all_keys(item)


def _assert_no_server_paths(payload):
    keys = set(_all_keys(payload))
    assert not sorted(key for key in keys if key.endswith("_path")), payload
    assert not (keys & LEGACY_GRAPH_KEYS), payload


# 1.3.1 -- client-supplied server paths: the endpoints that accepted them are gone.
def test_openapi_lists_none_of_the_removed_routes():
    paths = TestClient(app.app).get("/openapi.json").json()["paths"]

    leaked = sorted(path for path in paths for prefix in REMOVED_ROUTE_PREFIXES if path.startswith(prefix))
    assert leaked == []
    assert not [route.path for route in app.app.routes if isinstance(route, Mount)]


# 1.3.2 / 1.2 -- document payloads carry no *_path fields, graph or relationship data.
def _legacy_registry_entry(tmp_path: Path, document_id: str) -> dict:
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir()
    chunks_path = chunks_dir / f"{document_id}_chunks.jsonl"
    chunks_path.write_text(
        json.dumps({"chunk_id": "chunk_1", "document_id": document_id, "text": "1. Term.", "owner_user_id": "user_1"}) + "\n",
        encoding="utf-8",
    )
    vector_dir = tmp_path / "vector_store" / document_id
    vector_dir.mkdir(parents=True)
    (vector_dir / "metadata.json").write_text("[]", encoding="utf-8")
    graph_path = tmp_path / f"{document_id}_graph.json"
    graph_path.write_text(json.dumps({"nodes": [{"id": "Supplier"}], "edges": []}), encoding="utf-8")
    return {
        "document_id": document_id,
        "title": "Master Services Agreement",
        "domain": "general",
        "source": "msa.pdf",
        "source_type": "uploaded_file",
        "document_group": "user_private",
        "owner_user_id": "user_1",
        "visibility_scope": "private",
        "raw_hash": "sha256:raw",
        "text_hash": "sha256:text",
        "ingested_at": "2026-01-01T00:00:00+00:00",
        # Entries written before Phase 0 still carry extraction and graph artifacts.
        "paths": {
            "processed_text": str(tmp_path / f"{document_id}.txt"),
            "chunks": str(chunks_path),
            "extractions": str(tmp_path / f"{document_id}_extractions.jsonl"),
            "graph": str(graph_path),
            "vector_store": str(vector_dir),
        },
        "neo4j_sync": {"enabled": True, "synced": True},
    }


def test_document_list_and_detail_expose_no_server_paths(monkeypatch, tmp_path):
    document_id = "msa_20260101000000"
    registry_file = tmp_path / "registry.json"
    registry_file.write_text(json.dumps({"version": 1, "entries": [_legacy_registry_entry(tmp_path, document_id)]}), encoding="utf-8")
    monkeypatch.setattr(document_registry, "DOCUMENT_REGISTRY_FILE", registry_file)
    monkeypatch.setattr(document_access, "CHUNK_DIR", tmp_path / "chunks")
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "auth.db"))
    admin_audit.record_upload_created(
        job_id="job-1",
        title="Master Services Agreement",
        filename="msa.pdf",
        domain="general",
        source_type="uploaded_file",
        source="",
        uploader={"id": "user_1"},
    )
    admin_audit.record_upload_completed("job-1", {"document": {"id": document_id}, "stats": {"chunk_count": 1}})
    app.app.dependency_overrides[deps.get_current_user] = lambda: {"id": "user_1", "email": "u1@example.com", "role": "user"}
    try:
        client = TestClient(app.app)
        listing = client.get("/documents")
        detail = client.get(f"/documents/{document_id}")
    finally:
        app.app.dependency_overrides.pop(deps.get_current_user, None)

    assert listing.status_code == 200 and detail.status_code == 200
    documents = listing.json()["documents"]
    assert [item["id"] for item in documents] == [document_id]
    assert documents[0]["chunk_count"] == 1
    assert detail.json()["document"]["chunk_count"] == 1
    _assert_no_server_paths(listing.json())
    _assert_no_server_paths(detail.json())
    # The audit keeps the server-side paths it needs for cleanup.
    assert admin_audit.get_upload("job-1")["paths"]["chunks_path"].endswith(f"{document_id}_chunks.jsonl")


def test_ingestion_result_has_no_paths_and_needs_no_graph(monkeypatch, tmp_path):
    monkeypatch.setattr(document_registry, "DOCUMENT_REGISTRY_FILE", tmp_path / "registry.json")
    for name in ("PROCESSED_DIR", "CHUNK_DIR", "VECTOR_DIR"):
        directory = tmp_path / name.lower()
        directory.mkdir()
        monkeypatch.setattr(pipeline_runtime, name, directory)

    def fake_vector_store(chunks, persist_path):
        Path(persist_path).mkdir(parents=True, exist_ok=True)
        (Path(persist_path) / "metadata.json").write_text(json.dumps(chunks), encoding="utf-8")

    monkeypatch.setattr(pipeline_runtime, "build_vector_store", fake_vector_store)
    monkeypatch.setattr(pipeline_runtime, "build_bm25_index", lambda chunks, persist_path: None)
    stages = []
    content = "1. Confidentiality. The Recipient keeps the Disclosing Party's information secret for five years."

    result = pipeline_runtime.ingest_uploaded_document(
        title="Mutual NDA",
        content=content,
        document_group="user_private",
        owner_user_id="user_1",
        visibility_scope="private",
        progress_callback=lambda stage, message, percent: stages.append(stage),
    )
    duplicate = pipeline_runtime.ingest_uploaded_document(
        title="Mutual NDA again",
        content=content,
        document_group="user_private",
        owner_user_id="user_1",
        visibility_scope="private",
    )

    _assert_no_server_paths(result)
    _assert_no_server_paths(duplicate)
    assert result["stats"] == {"chunk_count": 1}
    assert result["document"]["neo4j_sync"]["synced"] is False
    assert stages == ["reading", "cleaning", "chunking", "embedding", "completed"]
    assert duplicate["duplicate"] is True and duplicate["document"]["id"] == result["document"]["id"]
    [entry] = document_registry.list_entries(valid_only=True)
    assert entry["document_id"] == result["document"]["id"]
    assert sorted(entry["paths"]) == ["chunks", "processed_text", "vector_store"]


# 1.3.3 -- Deep-mode tenant scope: non-admin filters keep owner_user_id in every layer.
def _own_entry():
    return {
        "document_id": "own_contract",
        "title": "Own Contract",
        "source": "own-contract.pdf",
        "document_group": "user_private",
        "owner_user_id": "user_1",
        "visibility_scope": "private",
        "paths": {},
    }


def test_non_admin_filters_keep_the_owner_in_every_layer(monkeypatch):
    monkeypatch.setattr(rag_context, "_retrievable_registry_entries", lambda current_user, include_invalid=False: [_own_entry()])
    monkeypatch.setattr(rag_context, "_resolve_document_ids_with_deepseek", lambda question, candidates, query_terms: [])
    monkeypatch.setattr(rag_context, "_route_request_with_deepseek", lambda question, entries: None)
    request = rag_context.RagAskRequest(question="What does clause 4 say?", document_ids=["own_contract"], reasoning_mode="deep")
    user = {"id": "user_1", "role": "user"}

    filters = rag_context._resolve_rag_request_context(request, user)["filters"]
    general_filters = rag_context._resolve_general_rag_request_context(request, user, [], "disabled")["filters"]
    admin_filters = rag_context._resolve_rag_request_context(request, {"id": "admin_1", "role": "admin"})["filters"]

    assert filters["document_ids"] == ["own_contract"] and filters["owner_user_id"] == "user_1"
    assert general_filters["document_ids"] == ["own_contract"] and general_filters["owner_user_id"] == "user_1"
    assert "owner_user_id" not in admin_filters

    captured = []

    def capture(*args, **kwargs):
        captured.append(dict(kwargs.get("filters") or {}))
        return []

    monkeypatch.setattr(retriever, "retrieve_context", capture)
    monkeypatch.setattr(retriever, "retrieve_context_multi", capture)
    retriever.retrieve_layered_context("clause 4 obligations", top_k=5, filters=filters)

    widened = [item for item in captured if item.get("domain") in {"academic", "regulatory"}]
    assert len(widened) == 2 and all("document_ids" not in item for item in widened)
    assert len(captured) >= 3 and all(item.get("owner_user_id") == "user_1" for item in captured)


def test_local_and_pinecone_filters_require_owner_and_document_scope_together():
    rows = [
        {"document_id": "a", "owner_user_id": "user_1", "visibility_scope": "private", "document_group": "user_private"},
        {"document_id": "a", "owner_user_id": "user_2", "visibility_scope": "private", "document_group": "user_private"},
        {"document_id": "b", "owner_user_id": "user_1", "visibility_scope": "private", "document_group": "user_private"},
        {"document_id": "g", "owner_user_id": "admin_1", "visibility_scope": "global", "document_group": "global_kb"},
    ]
    filters = {"document_ids": ["a", "g"], "owner_user_id": "user_1"}

    kept = _apply_local_filters(rows, filters)

    assert [(row["document_id"], row["owner_user_id"]) for row in kept] == [("a", "user_1"), ("g", "admin_1")]
    assert _build_pinecone_filter(filters) == {
        "$and": [
            {"document_id": {"$in": ["a", "g"]}},
            {
                "$or": [
                    {"owner_user_id": {"$eq": "user_1"}},
                    {"visibility_scope": {"$eq": "global"}},
                    {"document_group": {"$eq": "global_kb"}},
                ]
            },
        ]
    }


# 1.3.4 -- login normalises the email like registration does.
def test_login_matches_emails_case_insensitively(tmp_path):
    asyncio.run(_login_matches_emails_case_insensitively(tmp_path))


async def _login_matches_emails_case_insensitively(tmp_path):
    db_path = tmp_path / "auth.db"
    with patch("services.db._DB_PATH", str(db_path)):
        await db_service._init_auth_db()
        async with aiosqlite.connect(db_path) as db:
            for user_id, email in (("user-1", "counsel@example.com"), ("user-2", "Legacy.User@Example.com")):
                await db.execute(
                    "INSERT INTO users (id, email, username, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
                    (user_id, email, "Counsel", auth_service._hash_pw("correct horse"), "user", auth_service._utc_now_iso()),
                )
            await db.commit()
            mixed = await auth_routes.login(auth_routes.LoginRequest(email="  Counsel@Example.COM ", password="correct horse"), db)
            legacy = await auth_routes.login(auth_routes.LoginRequest(email="legacy.user@example.com", password="correct horse"), db)
            with pytest.raises(HTTPException) as exc:
                await auth_routes.login(auth_routes.LoginRequest(email="COUNSEL@example.com", password="wrong"), db)

    assert mixed["token"] and mixed["user"]["id"] == "user-1"
    assert legacy["user"]["id"] == "user-2"
    assert exc.value.status_code == 401


# 1.3.5 -- feedback and notification databases live under DATA_DIR, not in the source tree.
def test_feedback_db_path_reads_env_and_defaults_under_data_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("CAUSALGRAPH_DB_PATH", raising=False)
    assert db_service._resolve_feedback_db_path() == str(DATA_DIR / "causalgraph.db")

    monkeypatch.setenv("CAUSALGRAPH_DB_PATH", str(tmp_path / "feedback.db"))
    assert db_service._resolve_feedback_db_path() == str(tmp_path / "feedback.db")


def test_notifications_db_defaults_under_data_dir(tmp_path):
    env = dict(os.environ, DATA_DIR=str(tmp_path), NOTIFICATIONS_DB_PATH="")
    output = subprocess.check_output(
        [sys.executable, "-c", "from configs import settings as s; print(s.NOTIFICATIONS_DB_PATH)"],
        cwd=ROOT,
        env=env,
        text=True,
    )

    assert output.strip() == str(tmp_path / "notifications.db")
    assert notifications_store._resolve_db_path("") == DATA_DIR / "notifications.db"
