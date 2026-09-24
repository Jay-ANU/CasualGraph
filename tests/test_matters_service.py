"""WP1-C service layer: schema, personal workspaces, matter CRUD, membership, document links,
the extended access rule and the migration. Everything runs against a tmp_path auth DB."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi import HTTPException

import document_registry
from services import audit
from services import db as db_service
from services import document_access
from services import matters


@pytest.fixture
def auth_db(monkeypatch, tmp_path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(db_service, "_DB_PATH", str(db_path))
    monkeypatch.setenv("AUTH_DB_PATH", str(db_path))  # admin_audit resolves its DB at call time
    monkeypatch.setattr(document_registry, "DOCUMENT_REGISTRY_FILE", tmp_path / "registry.json")
    monkeypatch.setattr(document_access, "CHUNK_DIR", tmp_path / "chunks")
    monkeypatch.setattr(matters, "_PENDING_UPLOADS", {})  # async-upload links are process state
    asyncio.run(db_service._init_auth_db())
    return db_path


def _add_user(db_path: Path, user_id: str, *, email: str = "", username: str = "", role: str = "user") -> dict:
    email = email or f"{user_id}@example.com"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO users (id, email, username, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, email, username, "x", role, f"2026-01-01T00:00:0{len(user_id) % 10}+00:00"),
        )
    return {"id": user_id, "email": email, "username": username, "role": role}


def _register(tmp_path: Path, document_id: str, owner_user_id: str, *, group: str = "user_private", visibility: str = "private") -> dict:
    """A registry entry with real chunk and vector files so ``valid_only=True`` readers keep it."""
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    chunks_path = chunks_dir / f"{document_id}_chunks.jsonl"
    chunks_path.write_text(json.dumps({"chunk_id": "chunk_1", "document_id": document_id, "text": "1. Term."}) + "\n", encoding="utf-8")
    vector_dir = tmp_path / "vector_store" / document_id
    vector_dir.mkdir(parents=True, exist_ok=True)
    (vector_dir / "metadata.json").write_text("[]", encoding="utf-8")
    entry = {
        "document_id": document_id,
        "title": f"Contract {document_id}",
        "domain": "general",
        "source": f"{document_id}.pdf",
        "source_type": "uploaded_file",
        "document_group": group,
        "owner_user_id": owner_user_id,
        "visibility_scope": visibility,
        "ingested_at": "2026-02-01T00:00:00+00:00",
        "paths": {"chunks": str(chunks_path), "vector_store": str(vector_dir), "processed_text": ""},
    }
    document_registry.register(entry)
    return document_registry.get_entry(document_id, valid_only=False)


def _count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _events(db_path: Path, action: str | None = None) -> list:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        sql = "SELECT * FROM audit_events" + (" WHERE action = ?" if action else "") + " ORDER BY id"
        return [dict(row) for row in conn.execute(sql, (action,) if action else ())]


def _error_code(excinfo) -> str:
    return excinfo.value.detail["error"]


# ── schema ───────────────────────────────────────────────────────────────────


def test_auth_db_init_creates_matter_tables_and_indexes(auth_db):
    with sqlite3.connect(auth_db) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'index')")}
        conn.execute("INSERT INTO organizations (id, name, created_at) VALUES ('o', 'Org', 'now')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO org_members (org_id, user_id, role, created_at) VALUES ('o', 'u', 'boss', 'now')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO matters (id, org_id, name, status, created_by, created_at, updated_at)"
                " VALUES ('m', 'o', 'M', 'deleted', 'u', 'now', 'now')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO matter_members (matter_id, user_id, role, added_by, created_at) VALUES ('m', 'u', 'owner', 'u', 'now')")

    assert {"organizations", "org_members", "matters", "matter_members", "matter_documents", "audit_events"} <= names
    assert {"matter_members_user_id_idx", "matter_documents_document_id_idx", "audit_events_matter_created_idx"} <= names
    asyncio.run(db_service._init_auth_db())  # idempotent


# ── personal workspace ───────────────────────────────────────────────────────


def test_personal_workspace_is_provisioned_once(auth_db):
    user = _add_user(auth_db, "u1", username="Counsel")

    first = matters.ensure_personal_workspace(user)
    second = matters.ensure_personal_workspace(user)

    assert first == second and set(first) == {"org_id", "matter_id"}
    assert _count(auth_db, "organizations") == 1 and _count(auth_db, "matters") == 1
    [view] = matters.list_matters(user)
    assert view["id"] == first["matter_id"] and view["name"] == "未分类"
    assert view["role"] == "lead" and view["is_default"] is True and view["can_manage"] is True
    with sqlite3.connect(auth_db) as conn:
        org_name, = conn.execute("SELECT name FROM organizations").fetchone()
        org_role, = conn.execute("SELECT role FROM org_members WHERE user_id = 'u1'").fetchone()
    assert org_name == "Counsel 的工作区" and org_role == "owner"
    assert [event["target_id"] for event in _events(auth_db, "matter.created")] == [first["matter_id"]]


def test_concurrent_first_requests_provision_a_single_workspace(auth_db):
    user = _add_user(auth_db, "u1")
    barrier = threading.Barrier(6)
    results, errors = [], []

    def provision() -> None:
        barrier.wait()
        try:
            results.append(matters.ensure_personal_workspace(user))
        except Exception as exc:  # pragma: no cover - surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=provision) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == [] and len({tuple(sorted(item.items())) for item in results}) == 1
    assert _count(auth_db, "organizations") == 1 and _count(auth_db, "matters") == 1


def test_personal_workspace_name_falls_back_to_email(auth_db):
    user = _add_user(auth_db, "u2", email="lawyer@example.com", username="")

    matters.ensure_personal_workspace(user)

    with sqlite3.connect(auth_db) as conn:
        assert conn.execute("SELECT name FROM organizations").fetchone()[0] == "lawyer@example.com 的工作区"


# ── CRUD ─────────────────────────────────────────────────────────────────────


def test_matter_crud_archive_and_listing(auth_db):
    lead = _add_user(auth_db, "lead")

    created = matters.create_matter(lead, name="  Acme supply dispute ", client_ref="C-17", description="Supply terms")
    updated = matters.update_matter(created["id"], lead, name="Acme supply", description="Renegotiation")
    unchanged = matters.update_matter(created["id"], lead, name="Acme supply")
    archived = matters.archive_matter(created["id"], lead)

    assert created["name"] == "Acme supply dispute" and created["client_ref"] == "C-17"
    assert created["role"] == "lead" and created["member_count"] == 1 and created["document_count"] == 0
    assert set(created) >= {"id", "name", "client_ref", "description", "status", "org_id", "role",
                            "document_count", "member_count", "created_at", "updated_at"}
    assert updated["name"] == "Acme supply" and updated["description"] == "Renegotiation"
    assert unchanged["updated_at"] == updated["updated_at"]
    assert archived["status"] == "archived"
    assert matters.get_matter(created["id"])["status"] == "archived"  # soft delete: the row stays
    active_ids = [item["id"] for item in matters.list_matters(lead)]
    all_ids = [item["id"] for item in matters.list_matters(lead, include_archived=True)]
    assert created["id"] not in active_ids and created["id"] in all_ids
    restored = matters.update_matter(created["id"], lead, status="active")
    assert restored["status"] == "active"
    actions = [event["action"] for event in _events(auth_db) if event["matter_id"] == created["id"]]
    assert actions == ["matter.created", "matter.updated", "matter.archived", "matter.updated"]
    # Audit rows name the changed fields, never their values.
    assert "Acme" not in json.dumps(_events(auth_db)) and "Renegotiation" not in json.dumps(_events(auth_db))


def test_matter_validation_and_default_matter_protection(auth_db):
    user = _add_user(auth_db, "u1")
    workspace = matters.ensure_personal_workspace(user)

    with pytest.raises(HTTPException) as blank:
        matters.create_matter(user, name="   ")
    with pytest.raises(HTTPException) as bad_status:
        matters.update_matter(workspace["matter_id"], user, status="deleted")
    with pytest.raises(HTTPException) as default:
        matters.archive_matter(workspace["matter_id"], user)
    with pytest.raises(HTTPException) as foreign_org:
        other = _add_user(auth_db, "u2")
        matters.create_matter(other, name="Sneaky", org_id=workspace["org_id"])

    assert blank.value.status_code == 400 and bad_status.value.status_code == 400
    assert default.value.status_code == 409 and _error_code(default) == "default_matter"
    assert foreign_org.value.status_code == 403 and _error_code(foreign_org) == "org_forbidden"


# ── membership ───────────────────────────────────────────────────────────────


def test_membership_roles_are_enforced(auth_db):
    lead = _add_user(auth_db, "lead")
    member = _add_user(auth_db, "member", email="Member@Example.com")
    viewer = _add_user(auth_db, "viewer")
    outsider = _add_user(auth_db, "outsider")
    admin = _add_user(auth_db, "admin", role="admin")
    matter = matters.create_matter(lead, name="Matter")

    added = matters.add_member(matter["id"], lead, email="member@example.com", role="member")
    matters.add_member(matter["id"], lead, member_user_id="viewer", role="viewer")

    assert added["user_id"] == "member" and added["role"] == "member"
    assert matters.require_matter_member(matter["id"], viewer)["role"] == "viewer"
    assert matters.get_matter_for_user(matter["id"], viewer)["role"] == "viewer"
    for user in (outsider, admin):  # platform admins are not implicitly members
        with pytest.raises(HTTPException) as denied:
            matters.require_matter_member(matter["id"], user)
        assert denied.value.status_code == 403 and _error_code(denied) == "matter_forbidden"
        with pytest.raises(HTTPException):
            matters.get_matter_for_user(matter["id"], user)
    with pytest.raises(HTTPException) as too_low:
        matters.require_matter_member(matter["id"], viewer, "member")
    with pytest.raises(HTTPException) as not_lead:
        matters.add_member(matter["id"], member, member_user_id="outsider")
    with pytest.raises(HTTPException) as not_lead_remove:
        matters.remove_member(matter["id"], member, "viewer")
    with pytest.raises(HTTPException) as missing:
        matters.require_matter_member("no-such-matter", lead)
    with pytest.raises(HTTPException) as unknown_user:
        matters.add_member(matter["id"], lead, email="nobody@example.com")
    assert too_low.value.status_code == 403
    assert not_lead.value.status_code == 403 and not_lead_remove.value.status_code == 403
    assert missing.value.status_code == 404 and unknown_user.value.status_code == 404
    assert [item["user_id"] for item in matters.list_members(matter["id"], viewer)] == ["lead", "member", "viewer"]

    # Role change, self-removal, and the last lead stays.
    assert matters.add_member(matter["id"], lead, member_user_id="viewer", role="member")["role"] == "member"
    assert matters.remove_member(matter["id"], viewer, "viewer")["removed"] is True
    with pytest.raises(HTTPException) as last_lead:
        matters.remove_member(matter["id"], lead, "lead")
    with pytest.raises(HTTPException) as demote_last_lead:
        matters.add_member(matter["id"], lead, member_user_id="lead", role="member")
    assert _error_code(last_lead) == "last_lead" and _error_code(demote_last_lead) == "last_lead"
    assert matters.user_matter_ids("viewer") == []
    events = _events(auth_db)
    added_events = [event for event in events if event["action"] == "matter.member_added"]
    assert [json.loads(event["details_json"]) for event in added_events] == [
        {"role": "member"},
        {"role": "viewer"},
        {"previous_role": "viewer", "role": "member"},
    ]
    assert [event["target_id"] for event in events if event["action"] == "matter.member_removed"] == ["viewer"]


def test_org_admin_manages_without_seeing_documents(auth_db, tmp_path):
    owner = _add_user(auth_db, "owner")
    colleague = _add_user(auth_db, "colleague")
    workspace = matters.ensure_personal_workspace(owner)
    with sqlite3.connect(auth_db) as conn:
        conn.execute(
            "INSERT INTO org_members (org_id, user_id, role, created_at) VALUES (?, 'colleague', 'admin', 'now')",
            (workspace["org_id"],),
        )
    matter = matters.create_matter(owner, name="Board minutes")
    entry = _register(tmp_path, "minutes", "owner")
    matters.attach_document(matter["id"], "minutes", owner)

    view = matters.get_matter_for_user(matter["id"], colleague)
    renamed = matters.update_matter(matter["id"], colleague, name="Board minutes 2026")

    assert view["role"] is None and view["can_manage"] is True
    assert renamed["name"] == "Board minutes 2026"
    assert matters.list_members(matter["id"], colleague)
    assert not document_access._can_access_entry(colleague, entry)
    assert document_access.accessible_document_ids_for_matter(colleague, matter["id"]) == []
    with pytest.raises(HTTPException):
        matters.require_matter_member(matter["id"], colleague)
    # Adding themselves is possible and audited; then the documents open.
    matters.add_member(matter["id"], colleague, member_user_id="colleague", role="viewer")
    assert document_access._can_access_entry(colleague, entry)


# ── documents ────────────────────────────────────────────────────────────────


def test_attach_and_detach_documents(auth_db, tmp_path):
    lead = _add_user(auth_db, "lead")
    member = _add_user(auth_db, "member")
    viewer = _add_user(auth_db, "viewer")
    matter = matters.create_matter(lead, name="Matter")
    matters.add_member(matter["id"], lead, member_user_id="member", role="member")
    matters.add_member(matter["id"], lead, member_user_id="viewer", role="viewer")
    _register(tmp_path, "lead_doc", "lead")
    _register(tmp_path, "member_doc", "member")

    first = matters.attach_document(matter["id"], "lead_doc", lead)
    again = matters.attach_document(matter["id"], "lead_doc", lead)
    by_member = matters.attach_document(matter["id"], "member_doc", member)

    assert first["attached"] is True and again["attached"] is False and by_member["attached"] is True
    assert set(matters.matter_document_ids(matter["id"])) == {"lead_doc", "member_doc"}
    assert matters.document_matter_ids("lead_doc") == [matter["id"]]
    assert matters.user_matter_document_ids("viewer") == {"lead_doc", "member_doc"}
    assert matters.get_matter_for_user(matter["id"], lead)["document_count"] == 2
    with pytest.raises(HTTPException) as viewer_attach:
        matters.attach_document(matter["id"], "lead_doc", viewer)
    with pytest.raises(HTTPException) as unknown:
        matters.attach_document(matter["id"], "no_such_doc", lead)
    other = matters.create_matter(member, name="Member's other matter")
    with pytest.raises(HTTPException) as not_owner:
        # member can read lead_doc through the shared matter but may not carry it into another one
        matters.attach_document(other["id"], "lead_doc", member)
    assert viewer_attach.value.status_code == 403
    assert unknown.value.status_code == 404 and _error_code(unknown) == "document_not_found"
    assert not_owner.value.status_code == 403 and _error_code(not_owner) == "document_forbidden"

    detached = matters.detach_document(matter["id"], "member_doc", member)
    with pytest.raises(HTTPException) as detach_again:
        matters.detach_document(matter["id"], "member_doc", member)
    assert detached["detached"] is True and detach_again.value.status_code == 404
    assert matters.matter_document_ids(matter["id"]) == ["lead_doc"]

    matters.archive_matter(matter["id"], lead)
    with pytest.raises(HTTPException) as archived_attach:
        matters.attach_document(matter["id"], "member_doc", member)
    with pytest.raises(HTTPException) as archived_detach:
        matters.detach_document(matter["id"], "lead_doc", lead)
    assert _error_code(archived_attach) == "matter_archived" and _error_code(archived_detach) == "matter_archived"
    actions = [event["action"] for event in _events(auth_db) if event["target_type"] == "document"]
    assert actions == ["document.attached", "document.attached", "document.detached"]


def test_deleted_document_is_detached_from_every_matter(auth_db, tmp_path):
    owner = _add_user(auth_db, "owner")
    first = matters.create_matter(owner, name="One")
    second = matters.create_matter(owner, name="Two")
    _register(tmp_path, "doc", "owner")
    matters.attach_document(first["id"], "doc", owner)
    matters.attach_document(second["id"], "doc", owner)

    detached = matters.detach_deleted_document("doc", actor_user_id="owner")

    assert sorted(detached) == sorted([first["id"], second["id"]])
    assert matters.document_matter_ids("doc") == []
    deleted = _events(auth_db, "document.deleted")
    assert sorted(event["matter_id"] for event in deleted) == sorted(detached)


# ── access rule extension ────────────────────────────────────────────────────


def test_member_can_access_a_document_owned_by_someone_else_through_the_matter(auth_db, tmp_path):
    owner = _add_user(auth_db, "owner")
    colleague = _add_user(auth_db, "colleague")
    outsider = _add_user(auth_db, "outsider")
    entry = _register(tmp_path, "nda", "owner")
    matter = matters.create_matter(owner, name="NDA review")

    assert not document_access._can_access_entry(colleague, entry)
    assert not document_access._can_retrieve_entry(colleague, entry)

    matters.attach_document(matter["id"], "nda", owner)
    matters.add_member(matter["id"], owner, member_user_id="colleague", role="viewer")

    assert document_access._can_access_entry(colleague, entry)
    assert document_access._can_retrieve_entry(colleague, entry)
    assert not document_access._can_access_entry(outsider, entry)
    assert not document_access._can_retrieve_entry(None, entry)
    assert [item["document_id"] for item in document_access._accessible_registry_entries(colleague)] == ["nda"]
    assert [item["document_id"] for item in document_access._retrievable_registry_entries(colleague)] == ["nda"]
    assert document_access._accessible_registry_entries(outsider) == []
    assert document_access.accessible_document_ids_for_matter(colleague, matter["id"]) == ["nda"]
    assert document_access.accessible_document_ids_for_matter(outsider, matter["id"]) == []
    assert document_access.accessible_document_ids_for_matter(None, matter["id"]) == []

    matters.remove_member(matter["id"], owner, "colleague")
    assert not document_access._can_access_entry(colleague, entry)
    # The owner keeps the Phase 0 rule regardless of matters.
    matters.detach_document(matter["id"], "nda", owner)
    assert document_access._can_access_entry(owner, entry)


def test_access_checks_fail_closed_without_matter_tables(monkeypatch, tmp_path):
    monkeypatch.setattr(db_service, "_DB_PATH", str(tmp_path / "missing" / "auth.db"))

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("no such table: matter_documents")

    monkeypatch.setattr(matters, "is_document_in_user_matters", broken)
    monkeypatch.setattr(matters, "user_matter_document_ids", broken)
    entry = {"document_id": "d", "document_group": "user_private", "owner_user_id": "someone", "visibility_scope": "private"}

    assert document_access._can_access_entry({"id": "u"}, entry) is False
    assert ("d" in document_access._MatterDocumentIndex({"id": "u"})) is False


# ── uploads into a matter ────────────────────────────────────────────────────


def test_async_upload_is_linked_once_when_the_finished_job_is_read(auth_db):
    user = _add_user(auth_db, "u1")
    matter = matters.create_matter(user, name="Matter")
    matters.remember_pending_upload("job-1", matter_id=matter["id"], user_id="u1")
    running = {"job_id": "job-1", "status": "running", "result": None}
    done = {"job_id": "job-1", "status": "completed", "result": {"document": {"id": "doc-9"}, "stats": {"chunk_count": 4}}}

    assert matters.link_finished_upload(running) is None
    assert matters.link_finished_upload(done) == {"matter_id": matter["id"], "document_id": "doc-9"}
    assert matters.link_finished_upload(done) is None  # second poll: already handled

    assert matters.matter_document_ids(matter["id"]) == ["doc-9"]
    [uploaded] = _events(auth_db, "document.uploaded")
    assert json.loads(uploaded["details_json"]) == {"chunk_count": 4, "duplicate": False, "job_id": "job-1"}
    matters.remember_pending_upload("job-2", matter_id=matter["id"], user_id="u1")
    assert matters.link_finished_upload({"job_id": "job-2", "status": "failed", "error": "boom"}) is None
    assert matters.pending_upload("job-2") is None


# ── migration ────────────────────────────────────────────────────────────────


def _state(db_path: Path) -> dict:
    return {table: _count(db_path, table) for table in ("organizations", "org_members", "matters", "matter_members", "matter_documents")}


def test_migration_is_idempotent_and_dry_run_writes_nothing(auth_db, tmp_path):
    alice = _add_user(auth_db, "alice", username="Alice")
    _add_user(auth_db, "bob", username="Bob")
    _register(tmp_path, "alice_1", "alice")
    _register(tmp_path, "alice_2", "alice")
    _register(tmp_path, "bob_1", "bob")
    _register(tmp_path, "kb_1", "", group="global_kb", visibility="global")
    _register(tmp_path, "ghost_1", "deleted-user")
    filed = matters.create_matter(alice, name="Already filed")  # also provisions alice's workspace
    matters.attach_document(filed["id"], "alice_2", alice)
    before = _state(auth_db)

    dry = matters.migrate_existing_documents(dry_run=True)
    assert _state(auth_db) == before
    first = matters.migrate_existing_documents()
    after_first = _state(auth_db)
    second = matters.migrate_existing_documents()

    expected = {
        "users": 2,
        "workspaces_created": 1,
        "workspaces_existing": 1,
        "documents_seen": 5,
        "documents_attached": 2,
        "documents_already_in_matter": 1,
        "documents_without_owner": 1,
        "documents_owner_unknown": 1,
    }
    assert dry == {**expected, "dry_run": True}
    assert first == {**expected, "dry_run": False}
    assert second == {**expected, "workspaces_created": 0, "workspaces_existing": 2,
                      "documents_attached": 0, "documents_already_in_matter": 3, "dry_run": False}
    assert _state(auth_db) == after_first
    alice_default = matters.ensure_personal_workspace(alice)["matter_id"]
    bob_default = matters.ensure_personal_workspace({"id": "bob"})["matter_id"]
    assert matters.matter_document_ids(alice_default) == ["alice_1"]
    assert matters.matter_document_ids(bob_default) == ["bob_1"]
    assert matters.document_matter_ids("alice_2") == [filed["id"]]
    migrated = [event for event in _events(auth_db, "document.attached") if event["actor_user_id"] == matters.SYSTEM_ACTOR]
    assert sorted(event["target_id"] for event in migrated) == ["alice_1", "bob_1"]


def test_migration_dry_run_on_an_empty_database_creates_nothing(monkeypatch, tmp_path):
    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr(db_service, "_DB_PATH", str(db_path))
    monkeypatch.setattr(document_registry, "DOCUMENT_REGISTRY_FILE", tmp_path / "registry.json")

    counts = matters.migrate_existing_documents(dry_run=True)

    assert counts["users"] == 0 and counts["documents_seen"] == 0 and counts["dry_run"] is True
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0


def test_audit_rows_from_services_never_hold_names(auth_db, tmp_path):
    lead = _add_user(auth_db, "lead")
    matter = matters.create_matter(lead, name="Project Falcon — ACME Holdings", client_ref="ACME-7", description="Share purchase")
    matters.update_matter(matter["id"], lead, description="Confidential SPA negotiation")
    _register(tmp_path, "spa", "lead")
    matters.attach_document(matter["id"], "spa", lead)

    events = audit.list_events(matter["id"])

    dumped = json.dumps(events, ensure_ascii=False)
    for secret in ("Falcon", "ACME", "Share purchase", "Confidential"):
        assert secret not in dumped
    assert [event["action"] for event in events] == ["document.attached", "matter.updated", "matter.created"]


def test_migration_script_dry_run_then_apply(auth_db, tmp_path, capsys):
    from scripts import migrate_phase1_matters

    _add_user(auth_db, "carol", username="Carol")
    _register(tmp_path, "carol_1", "carol")

    def run(*argv: str) -> dict:
        assert migrate_phase1_matters.main(list(argv)) == 0
        output = capsys.readouterr().out
        return json.loads(output[output.index("{"):])

    dry = run("--dry-run")
    assert _count(auth_db, "matter_documents") == 0
    applied = run()
    again = run()

    assert dry["documents_attached"] == applied["documents_attached"] == 1 and dry["dry_run"] is True
    assert again["documents_attached"] == 0 and again["documents_already_in_matter"] == 1
    assert _count(auth_db, "matter_documents") == 1
