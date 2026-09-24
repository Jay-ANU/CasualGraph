"""WP1-C audit log: safe details only (ids and counts), sync record_event, listing and paging."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading

import pytest

import document_registry
from services import audit
from services import db as db_service
from services import matters


@pytest.fixture
def auth_db(monkeypatch, tmp_path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(db_service, "_DB_PATH", str(db_path))
    monkeypatch.setenv("AUTH_DB_PATH", str(db_path))
    monkeypatch.setattr(document_registry, "DOCUMENT_REGISTRY_FILE", tmp_path / "registry.json")
    asyncio.run(db_service._init_auth_db())
    return db_path


def _rows(db_path) -> list:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM audit_events ORDER BY id")]


def _matter(db_path, user_id: str = "lead") -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO users (id, email, username, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, f"{user_id}@example.com", user_id, "x", "user", "2026-01-01T00:00:00+00:00"),
        )
    return matters.create_matter({"id": user_id}, name="Matter")


def test_record_event_writes_ids_and_counts_and_fills_the_org(auth_db):
    matter = _matter(auth_db)

    event_id = audit.record_event(
        actor_user_id="lead",
        action="redaction.confirmed",
        target_type="document",
        target_id="doc_1",
        matter_id=matter["id"],
        details={"document_id": "doc_1", "accepted_count": 3, "counts_by_category": {"org": 2, "person": 1},
                 "confirmed_at": "2026-09-24T00:00:00+00:00", "flags": {"auto": False}, "ids": ("a", "b")},
    )

    row = _rows(auth_db)[-1]
    assert row["id"] == event_id and row["org_id"] == matter["org_id"] and row["matter_id"] == matter["id"]
    assert row["action"] == "redaction.confirmed" and row["actor_user_id"] == "lead"
    assert json.loads(row["details_json"])["counts_by_category"] == {"org": 2, "person": 1}
    assert json.loads(row["details_json"])["ids"] == ["a", "b"]
    assert row["created_at"]


@pytest.mark.parametrize(
    "details",
    [
        {"text": "甲方：北京某某科技有限公司"},
        {"Content": "clause body"},
        {"quote": "the Supplier shall"},
        {"value": "13800138000"},
        {"values": ["a"]},
        {"summary": {"nested": [{"original_text": "secret"}]}},
        {"block_content": "x"},
        {"new_value": "x"},
        {"question": "What does Acme owe?"},
        {"answer": "Acme owes ..."},
    ],
)
def test_record_event_rejects_text_like_keys_anywhere(auth_db, details):
    with pytest.raises(audit.AuditDetailsError) as excinfo:
        audit.record_event(actor_user_id="u", action="rag.asked", target_type="matter", target_id="m", details=details)

    assert isinstance(excinfo.value, ValueError)
    assert _rows(auth_db) == []
    for leaked in ("北京", "clause body", "Supplier", "13800138000", "secret", "Acme"):
        assert leaked not in str(excinfo.value)


@pytest.mark.parametrize(
    "details",
    [
        {"note": "x" * (audit.MAX_DETAIL_STRING_LENGTH + 1)},
        {"blob": b"bytes"},
        {"score": float("nan")},
        {1: "non-string key"},
        {"ids": ["x" * 400] * 40},
        "not a dict",
    ],
)
def test_record_event_rejects_long_strings_and_non_json_details(auth_db, details):
    with pytest.raises(audit.AuditDetailsError) as excinfo:
        audit.record_event(actor_user_id="u", action="document.uploaded", target_type="document", target_id="d", details=details)

    assert "xxxxxxxx" not in str(excinfo.value)
    assert _rows(auth_db) == []


def test_record_event_validates_the_envelope(auth_db):
    for bad in ({"action": "Matter Created"}, {"action": "created"}, {"actor_user_id": ""}, {"target_type": " "}):
        arguments = {"actor_user_id": "u", "action": "matter.created", "target_type": "matter", "target_id": "m", **bad}
        with pytest.raises(ValueError):
            audit.record_event(**arguments)
    assert _rows(auth_db) == []


def test_write_event_rolls_back_with_its_transaction(auth_db):
    with pytest.raises(RuntimeError):
        with db_service.auth_db_transaction() as conn:
            audit.write_event(conn, actor_user_id="u", action="matter.updated", target_type="matter", target_id="m")
            raise RuntimeError("the change failed")

    assert _rows(auth_db) == []


def test_record_event_is_safe_from_worker_threads(auth_db):
    errors = []

    def worker(index: int) -> None:
        try:
            audit.record_event(actor_user_id=f"u{index}", action="rag.asked", target_type="matter", target_id="m",
                               matter_id="m", details={"document_count": index})
        except Exception as exc:  # pragma: no cover - surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == [] and len(_rows(auth_db)) == 8


def test_list_events_is_newest_first_with_an_id_cursor(auth_db):
    matter = _matter(auth_db)
    for index in range(5):
        audit.record_event(actor_user_id="lead", action="document.attached", target_type="document",
                           target_id=f"doc_{index}", matter_id=matter["id"])
    audit.record_event(actor_user_id="lead", action="document.attached", target_type="document",
                       target_id="elsewhere", matter_id="another-matter")

    page_one = audit.list_events(matter["id"], limit=3)
    page_two = audit.list_events(matter["id"], limit=3, before=page_one[-1]["id"])

    assert [event["target_id"] for event in page_one] == ["doc_4", "doc_3", "doc_2"]
    assert [event["target_id"] for event in page_two] == ["doc_1", "doc_0", matter["id"]]
    assert page_two[-1]["action"] == "matter.created"
    assert all(event["matter_id"] == matter["id"] for event in page_one + page_two)
    assert set(page_one[0]) == {"id", "org_id", "matter_id", "actor_user_id", "action", "target_type", "target_id", "details", "created_at"}
    assert audit.list_events("") == []
    with pytest.raises(ValueError):
        audit.list_events(matter["id"], before="not-an-id")
