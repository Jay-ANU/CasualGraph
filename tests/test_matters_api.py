"""WP1-C HTTP surface: /matters routes, membership enforcement, document links, uploads into a
matter (sync, text and async), ``GET /documents?matter_id=`` and deletion clean-up."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app
import document_registry
from api.routers import documents as documents_router
from services import auth as auth_service
from services import db as db_service
from services import document_access, matters


@pytest.fixture
def api(monkeypatch, tmp_path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(db_service, "_DB_PATH", str(db_path))
    monkeypatch.setenv("AUTH_DB_PATH", str(db_path))
    monkeypatch.setattr(document_registry, "DOCUMENT_REGISTRY_FILE", tmp_path / "registry.json")
    monkeypatch.setattr(document_access, "CHUNK_DIR", tmp_path / "chunks")
    monkeypatch.setattr(documents_router, "_UPLOAD_SPOOL_DIR", tmp_path / "spool")
    monkeypatch.setattr(matters, "_PENDING_UPLOADS", {})  # async-upload links are process state
    asyncio.run(db_service._init_auth_db())
    return SimpleNamespace(db=db_path, tmp=tmp_path, client=TestClient(app.app))


def _user(api, user_id: str, role: str = "user") -> dict:
    email = f"{user_id}@example.com"
    with sqlite3.connect(api.db) as conn:
        conn.execute(
            "INSERT INTO users (id, email, username, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, email, user_id.title(), "x", role, "2026-01-01T00:00:00+00:00"),
        )
    return {"Authorization": f"Bearer {auth_service._make_token(user_id, email)}"}


def _register(tmp_path: Path, document_id: str, owner_user_id: str, *, title: str = "") -> None:
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    chunks_path = chunks_dir / f"{document_id}_chunks.jsonl"
    chunks_path.write_text(json.dumps({"chunk_id": "chunk_1", "document_id": document_id, "text": "1. Term."}) + "\n", encoding="utf-8")
    vector_dir = tmp_path / "vector_store" / document_id
    vector_dir.mkdir(parents=True, exist_ok=True)
    (vector_dir / "metadata.json").write_text("[]", encoding="utf-8")
    document_registry.register({
        "document_id": document_id,
        "title": title or f"Contract {document_id}",
        "domain": "general",
        "source": f"{document_id}.pdf",
        "source_type": "uploaded_file",
        "document_group": "user_private",
        "owner_user_id": owner_user_id,
        "visibility_scope": "private",
        "ingested_at": "2026-02-01T00:00:00+00:00",
        "paths": {"chunks": str(chunks_path), "vector_store": str(vector_dir), "processed_text": ""},
    })


def _events(api, action: str) -> list:
    with sqlite3.connect(api.db) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM audit_events WHERE action = ? ORDER BY id", (action,))]


def _keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def _create(api, headers, name: str = "Supply dispute") -> dict:
    response = api.client.post("/matters", json={"name": name, "client_ref": "C-1", "description": "d"}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["matter"]


# ── CRUD ─────────────────────────────────────────────────────────────────────


def test_matter_crud_over_http(api):
    lead = _user(api, "lead")

    listing = api.client.get("/matters", headers=lead)
    created = _create(api, lead)
    detail = api.client.get(f"/matters/{created['id']}", headers=lead)
    patched = api.client.patch(f"/matters/{created['id']}", json={"name": "Supply dispute 2026", "description": ""}, headers=lead)
    archived = api.client.delete(f"/matters/{created['id']}", headers=lead)
    active = api.client.get("/matters", headers=lead)
    everything = api.client.get("/matters", params={"include_archived": "true"}, headers=lead)

    [default] = listing.json()["matters"]
    assert default["name"] == "未分类" and default["is_default"] is True and default["role"] == "lead"
    assert set(detail.json()["matter"]) == {
        "id", "name", "client_ref", "description", "status", "org_id", "role", "document_count",
        "member_count", "created_at", "updated_at", "is_default", "can_manage",
    }
    assert detail.json()["matter"]["org_id"] == default["org_id"]  # created in the personal org
    assert patched.status_code == 200 and patched.json()["matter"]["name"] == "Supply dispute 2026"
    assert patched.json()["matter"]["description"] == ""
    assert archived.status_code == 200 and archived.json()["matter"]["status"] == "archived"
    assert [item["id"] for item in active.json()["matters"]] == [default["id"]]
    assert {item["id"] for item in everything.json()["matters"]} == {default["id"], created["id"]}
    assert api.client.delete(f"/matters/{default['id']}", headers=lead).json()["error"] == "default_matter"
    assert api.client.post("/matters", json={"name": " "}, headers=lead).status_code == 400
    assert api.client.get("/matters/no-such-matter", headers=lead).status_code == 404
    assert api.client.get("/matters").status_code == 401


# ── membership enforcement ───────────────────────────────────────────────────


def test_membership_is_enforced_on_every_route(api):
    lead, member, viewer, outsider = (_user(api, name) for name in ("lead", "member", "viewer", "outsider"))
    admin = _user(api, "admin", role="admin")
    matter = _create(api, lead)
    base = f"/matters/{matter['id']}"
    assert api.client.post(f"{base}/members", json={"email": "MEMBER@example.com"}, headers=lead).json()["member"]["role"] == "member"
    assert api.client.post(f"{base}/members", json={"user_id": "viewer", "role": "viewer"}, headers=lead).status_code == 200

    for headers in (outsider, admin):  # platform admins are not implicitly members
        for method, path in (("get", base), ("get", f"{base}/members"), ("get", f"{base}/documents"), ("get", f"{base}/audit")):
            response = getattr(api.client, method)(path, headers=headers)
            assert response.status_code == 403 and response.json()["error"] == "matter_forbidden", (path, response.text)
        assert api.client.get("/documents", params={"matter_id": matter["id"]}, headers=headers).status_code == 403
        assert api.client.patch(base, json={"name": "x"}, headers=headers).status_code == 403
        assert api.client.delete(base, headers=headers).status_code == 403

    # A member can read but not manage.
    assert api.client.get(f"{base}/documents", headers=member).status_code == 200
    assert api.client.post(f"{base}/members", json={"user_id": "outsider"}, headers=member).status_code == 403
    assert api.client.delete(f"{base}/members", params={"user_id": "viewer"}, headers=member).status_code == 403
    assert api.client.patch(base, json={"name": "x"}, headers=member).status_code == 403
    assert api.client.get(f"{base}/audit", headers=member).status_code == 403
    # A viewer cannot add documents.
    assert api.client.post(f"{base}/documents", json={"document_id": "anything"}, headers=viewer).status_code == 403

    members = api.client.get(f"{base}/members", headers=viewer).json()["members"]
    assert [(item["user_id"], item["role"]) for item in members] == [("lead", "lead"), ("member", "member"), ("viewer", "viewer")]
    assert members[0]["email"] == "lead@example.com"
    removed = api.client.request("DELETE", f"{base}/members", json={"user_id": "viewer"}, headers=lead)
    assert removed.status_code == 200 and removed.json()["removed"] is True
    assert api.client.get(base, headers=viewer).status_code == 403
    assert api.client.delete(f"{base}/members", params={"user_id": "lead"}, headers=lead).json()["error"] == "last_lead"
    assert api.client.post(f"{base}/members", json={"email": "nobody@example.com"}, headers=lead).status_code == 404


# ── documents in a matter ────────────────────────────────────────────────────


def test_attach_detach_filter_and_access_through_the_matter(api):
    owner, colleague, outsider = _user(api, "owner"), _user(api, "colleague"), _user(api, "outsider")
    matter = _create(api, owner)
    base = f"/matters/{matter['id']}"
    api.client.post(f"{base}/members", json={"user_id": "colleague", "role": "viewer"}, headers=owner)
    for document_id in ("nda", "msa", "lease"):
        _register(api.tmp, document_id, "owner")

    attached = api.client.post(f"{base}/documents", json={"document_id": "nda", "document_ids": ["msa", "nda"]}, headers=owner)
    stolen = api.client.post(f"{base}/documents", json={"document_id": "lease"}, headers=colleague)
    listed = api.client.get(f"{base}/documents", headers=colleague)
    filtered = api.client.get("/documents", params={"matter_id": matter["id"]}, headers=colleague)
    unfiltered = api.client.get("/documents", headers=colleague)

    assert [(item["document_id"], item["attached"]) for item in attached.json()["documents"]] == [("nda", True), ("msa", True)]
    assert stolen.status_code == 403  # viewers cannot add documents
    documents = listed.json()["documents"]
    assert sorted(item["id"] for item in documents) == ["msa", "nda"]
    assert all(item["status"] == "ready" and item["redaction"] == {"status": "skipped_legacy"} for item in documents)
    assert all(item["matter_link"]["added_by"] == "owner" for item in documents)
    assert not [key for key in _keys(listed.json()) if key.endswith("_path") or key == "paths"]
    assert sorted(item["id"] for item in filtered.json()["documents"]) == ["msa", "nda"]
    assert sorted(item["id"] for item in unfiltered.json()["documents"]) == ["msa", "nda"]  # not the lease
    assert api.client.get("/documents", headers=outsider).json()["documents"] == []
    # The access rule extension: a viewer opens the owner's document through the matter.
    assert api.client.get("/documents/nda", headers=colleague).status_code == 200
    assert api.client.get("/documents/lease", headers=colleague).status_code == 403
    assert api.client.get("/documents/nda", headers=outsider).status_code == 403
    assert api.client.get(base, headers=owner).json()["matter"]["document_count"] == 2

    detached = api.client.delete(f"{base}/documents/msa", headers=owner)
    assert detached.status_code == 200 and detached.json()["detached"] is True
    assert api.client.delete(f"{base}/documents/msa", headers=owner).json()["error"] == "document_not_in_matter"
    assert [item["id"] for item in api.client.get(f"{base}/documents", headers=owner).json()["documents"]] == ["nda"]
    assert api.client.get("/documents/msa", headers=colleague).status_code == 403
    assert api.client.post(f"{base}/documents", json={}, headers=owner).status_code == 400


def test_matter_documents_carry_processing_status_even_before_indexing(api):
    owner = _user(api, "owner")
    matter = _create(api, owner)
    # A WP1-A style entry awaiting redaction review: no chunks or vectors yet, which the
    # valid_only registry readers would prune, so the matter listing must not depend on them.
    registry = {"version": 1, "entries": [{
        "document_id": "pending_doc", "title": "采购合同", "document_group": "user_private",
        "owner_user_id": "owner", "visibility_scope": "private", "schema_version": 2,
        "status": "pending_redaction", "status_message": "", "language": "zh", "page_count": 3,
        "redaction": {"status": "pending", "counts_by_category": {"org": 2}},
        "paths": {"raw": str(api.tmp / "raw" / "pending_doc" / "original.docx.enc")},
    }]}
    Path(document_registry.DOCUMENT_REGISTRY_FILE).write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")

    attached = api.client.post(f"/matters/{matter['id']}/documents", json={"document_id": "pending_doc"}, headers=owner)
    [document] = api.client.get(f"/matters/{matter['id']}/documents", headers=owner).json()["documents"]

    assert attached.status_code == 200
    assert document["id"] == "pending_doc" and document["status"] == "pending_redaction"
    assert document["redaction"] == {"status": "pending", "counts_by_category": {"org": 2}}
    assert document["language"] == "zh" and document["page_count"] == 3
    assert not [key for key in _keys(document) if key.endswith("_path") or key == "paths"]
    assert document_registry.get_entry("pending_doc", valid_only=False) is not None  # never pruned


def test_matter_audit_route_pages_newest_first(api):
    lead, member = _user(api, "lead"), _user(api, "member")
    matter = _create(api, lead)
    base = f"/matters/{matter['id']}"
    api.client.post(f"{base}/members", json={"user_id": "member"}, headers=lead)
    for document_id in ("d1", "d2"):
        _register(api.tmp, document_id, "lead")
        api.client.post(f"{base}/documents", json={"document_id": document_id}, headers=lead)

    first = api.client.get(f"{base}/audit", params={"limit": 2}, headers=lead).json()
    second = api.client.get(f"{base}/audit", params={"limit": 2, "before": first["next_before"]}, headers=lead).json()

    assert [event["action"] for event in first["events"]] == ["document.attached", "document.attached"]
    assert [event["action"] for event in second["events"]] == ["matter.member_added", "matter.created"]
    assert second["next_before"] == second["events"][-1]["id"]
    assert api.client.get(f"{base}/audit", headers=member).status_code == 403
    assert "Supply" not in json.dumps(first) + json.dumps(second)


# ── uploads into a matter ────────────────────────────────────────────────────


@pytest.fixture
def fake_ingest(api, monkeypatch):
    calls = []

    def ingest(*, title, domain="general", source="", content="", document_group="user_upload", source_type="",
               owner_user_id="", visibility_scope="global", filename=None, file_bytes=None, file_path=None,
               raw_hash=None, progress_callback=None, matter_id=""):
        calls.append({"title": title, "owner_user_id": owner_user_id, "matter_id": matter_id, "file": bool(file_path)})
        document_id = f"upload_{len(calls)}"
        _register(api.tmp, document_id, owner_user_id, title=title)
        return {"document": {"id": document_id, "title": title}, "stats": {"chunk_count": 3}, "neo4j": {}}

    monkeypatch.setattr(documents_router, "ingest_uploaded_document", ingest)
    return calls


def test_upload_with_matter_id_links_the_document(api, fake_ingest):
    lead, viewer = _user(api, "lead"), _user(api, "viewer")
    matter = _create(api, lead)
    api.client.post(f"/matters/{matter['id']}/members", json={"user_id": "viewer", "role": "viewer"}, headers=lead)

    response = api.client.post(
        "/documents/upload",
        data={"title": "Master services agreement", "matter_id": matter["id"]},
        files={"file": ("msa.txt", b"1. Services. The Supplier provides services.", "text/plain")},
        headers=lead,
    )
    denied = api.client.post("/documents/upload", data={"title": "x", "content": "y", "matter_id": matter["id"]}, headers=viewer)

    assert response.status_code == 200, response.text
    assert response.json()["matter_id"] == matter["id"]
    assert fake_ingest[0] == {"title": "Master services agreement", "owner_user_id": "lead", "matter_id": matter["id"], "file": True}
    assert matters.matter_document_ids(matter["id"]) == ["upload_1"]
    [uploaded] = _events(api, "document.uploaded")
    assert uploaded["matter_id"] == matter["id"] and uploaded["target_id"] == "upload_1"
    assert json.loads(uploaded["details_json"]) == {"chunk_count": 3, "duplicate": False}
    assert denied.status_code == 403 and denied.json()["error"] == "matter_forbidden"
    assert len(fake_ingest) == 1  # nothing was ingested for the refused upload
    assert not list((api.tmp / "spool").glob("*"))


def test_upload_without_matter_goes_to_the_default_matter_and_archived_matters_refuse(api, fake_ingest):
    lead = _user(api, "lead")
    matter = _create(api, lead)
    api.client.delete(f"/matters/{matter['id']}", headers=lead)

    plain = api.client.post("/documents/upload", data={"title": "Lease", "content": "1. Rent."}, headers=lead)
    archived = api.client.post("/documents/upload", data={"title": "x", "content": "y", "matter_id": matter["id"]}, headers=lead)
    missing = api.client.post("/documents/upload", data={"title": "x", "content": "y", "matter_id": "nope"}, headers=lead)

    default_id = matters.ensure_personal_workspace({"id": "lead"})["matter_id"]
    assert plain.status_code == 200 and plain.json()["matter_id"] == default_id
    assert matters.matter_document_ids(default_id) == ["upload_1"]
    assert archived.status_code == 409 and archived.json()["error"] == "matter_archived"
    assert missing.status_code == 404 and missing.json()["error"] == "matter_not_found"
    assert len(fake_ingest) == 1


def test_ingest_text_accepts_matter_id(api, fake_ingest):
    lead, outsider = _user(api, "lead"), _user(api, "outsider")
    matter = _create(api, lead)

    response = api.client.post("/documents/ingest-text", json={"title": "Memo", "content": "1. Advice.", "matter_id": matter["id"]}, headers=lead)
    denied = api.client.post("/documents/ingest-text", json={"title": "Memo", "content": "1.", "matter_id": matter["id"]}, headers=outsider)

    assert response.status_code == 200 and response.json()["matter_id"] == matter["id"]
    assert matters.matter_document_ids(matter["id"]) == ["upload_1"]
    assert denied.status_code == 403 and len(fake_ingest) == 1


def test_matter_id_is_only_passed_to_ingestion_that_accepts_it(api, monkeypatch):
    lead = _user(api, "lead")
    matter = _create(api, lead)
    seen = []

    def legacy_ingest(title, domain="general", source="", content="", document_group="user_upload", source_type="",
                      owner_user_id="", visibility_scope="global", filename=None, file_bytes=None, file_path=None,
                      raw_hash=None, progress_callback=None):
        seen.append(title)
        return {"document": {"id": "legacy_doc"}, "stats": {"chunk_count": 1}}

    monkeypatch.setattr(documents_router, "ingest_uploaded_document", legacy_ingest)
    response = api.client.post("/documents/ingest-text", json={"title": "Old", "content": "1.", "matter_id": matter["id"]}, headers=lead)

    assert response.status_code == 200 and seen == ["Old"]
    assert matters.matter_document_ids(matter["id"]) == ["legacy_doc"]


def test_async_upload_is_linked_when_the_finished_job_is_first_read(api, monkeypatch):
    lead = _user(api, "lead")
    matter = _create(api, lead)
    jobs = {}
    started = []

    def start(**kwargs):  # today's signature has no matter_id, so none is passed
        started.append(kwargs)
        jobs["job-1"] = {"job_id": "job-1", "status": "queued", "stage": "queued", "progress": 0, "result": None, "error": None}
        return dict(jobs["job-1"])

    monkeypatch.setattr(documents_router, "start_ingestion_job", start)
    monkeypatch.setattr(documents_router, "get_ingestion_job", lambda job_id: dict(jobs[job_id]) if job_id in jobs else None)
    monkeypatch.setattr(documents_router, "get_upload", lambda job_id: None)

    queued = api.client.post("/documents/upload-async", data={"title": "SPA", "content": "1. Shares.", "matter_id": matter["id"]}, headers=lead)
    still_running = api.client.get("/documents/jobs/job-1", headers=lead)
    jobs["job-1"].update(status="completed", stage="completed", progress=100,
                         result={"document": {"id": "spa_doc"}, "stats": {"chunk_count": 2}})
    finished = api.client.get("/documents/jobs/job-1", headers=lead)
    polled_again = api.client.get("/documents/jobs/job-1", headers=lead)

    assert queued.status_code == 200 and queued.json()["matter_id"] == matter["id"]
    assert "matter_id" not in started[0]
    assert still_running.json()["status"] == "queued" and "matter_id" not in still_running.json()
    assert finished.json()["matter_id"] == matter["id"]
    assert polled_again.status_code == 200 and "matter_id" not in polled_again.json()
    assert matters.matter_document_ids(matter["id"]) == ["spa_doc"]
    [uploaded] = _events(api, "document.uploaded")
    assert json.loads(uploaded["details_json"]) == {"chunk_count": 2, "duplicate": False, "job_id": "job-1"}


def test_async_duplicate_and_reserved_document_ids_link_at_job_start(api, monkeypatch):
    lead = _user(api, "lead")
    matter = _create(api, lead)
    returned = iter([
        {"job_id": "dup", "status": "completed", "result": {"duplicate": True, "document": {"id": "existing"}, "stats": {"chunk_count": 5}}},
        {"job_id": "reserved", "status": "queued", "document_id": "future_doc", "result": None},
    ])
    received = []

    def start(*, matter_id="", **kwargs):  # a WP1-A style signature that takes matter_id
        received.append(matter_id)
        return next(returned)

    monkeypatch.setattr(documents_router, "start_ingestion_job", start)
    for title in ("dup", "reserved"):
        api.client.post("/documents/upload-async", data={"title": title, "content": "1.", "matter_id": matter["id"]}, headers=lead)

    assert received == [matter["id"], matter["id"]]
    assert sorted(matters.matter_document_ids(matter["id"])) == ["existing", "future_doc"]
    details = [json.loads(event["details_json"]) for event in _events(api, "document.uploaded")]
    assert details == [{"chunk_count": 5, "duplicate": True, "job_id": "dup"}, {"job_id": "reserved"}]


# ── deletion ─────────────────────────────────────────────────────────────────


def test_deleting_a_document_detaches_it_from_every_matter(api, monkeypatch):
    owner, colleague = _user(api, "owner"), _user(api, "colleague")
    first, second = _create(api, owner, "One"), _create(api, owner, "Two")
    _register(api.tmp, "doc", "owner")
    for matter in (first, second):
        api.client.post(f"/matters/{matter['id']}/documents", json={"document_id": "doc"}, headers=owner)
    api.client.post(f"/matters/{first['id']}/members", json={"user_id": "colleague", "role": "member"}, headers=owner)
    monkeypatch.setattr(
        documents_router,
        "delete_uploaded_document",
        lambda upload: {"deleted_paths": [], "warnings": [], "neo4j": {"enabled": False, "deleted": False, "reason": "neo4j_unavailable"}},
    )

    refused = api.client.delete("/documents/doc", headers=colleague)
    deleted = api.client.delete("/documents/doc", headers=owner)

    assert refused.status_code == 403 and "matter" in refused.json()["message"]
    assert deleted.status_code == 200 and deleted.json()["detached_matter_count"] == 2
    assert matters.document_matter_ids("doc") == []
    assert sorted(event["matter_id"] for event in _events(api, "document.deleted")) == sorted([first["id"], second["id"]])
    assert api.client.get(f"/matters/{first['id']}", headers=owner).json()["matter"]["document_count"] == 0
