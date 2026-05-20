from __future__ import annotations

import sqlite3

from notifications import store


def _sample_kwargs(**overrides):
    payload = {
        "query": "What is the moon's ESG score in 2099?",
        "rewritten_query": "What is the moon's ESG score in 2099?",
        "failure_reason": "no_context",
        "retrieval_strategy": "hybrid",
        "filters": {},
        "mode": "ask",
        "user_id": "user-1",
        "top_sources_preview": [{"chunk_id": "chunk_1", "document_id": "doc_1", "score": 0.91}],
    }
    payload.update(overrides)
    return payload


def test_record_unanswered_inserts_and_dedups(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(store, "NOTIFICATIONS_DB_PATH", str(db_path))
    store.init_db(str(db_path))

    row_id = store.record_unanswered(**_sample_kwargs())
    same_row_id = store.record_unanswered(**_sample_kwargs(user_id="user-2"))

    assert row_id == same_row_id

    rows = store.list_pending(limit=10)
    assert len(rows) == 1
    assert rows[0]["occurrence_count"] == 2
    assert sorted(rows[0]["user_ids"]) == sorted(
        [
            store._anonymize_user_id("user-1"),
            store._anonymize_user_id("user-2"),
        ]
    )


def test_mark_sent_then_new_pending_row(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(store, "NOTIFICATIONS_DB_PATH", str(db_path))
    store.init_db(str(db_path))

    first_id = store.record_unanswered(**_sample_kwargs())
    store.mark_sent([first_id])
    second_id = store.record_unanswered(**_sample_kwargs(user_id="user-3"))

    assert second_id != first_id

    pending = store.list_pending(limit=10)
    assert len(pending) == 1
    assert pending[0]["id"] == second_id

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status FROM unanswered_notifications WHERE id = ?",
            (first_id,),
        ).fetchone()
    assert row[0] == "sent"


def test_list_pending_orders_by_last_seen_desc(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(store, "NOTIFICATIONS_DB_PATH", str(db_path))
    store.init_db(str(db_path))

    first_id = store.record_unanswered(**_sample_kwargs(query="first", rewritten_query="first"))
    second_id = store.record_unanswered(**_sample_kwargs(query="second", rewritten_query="second"))
    store.record_unanswered(**_sample_kwargs(query="first", rewritten_query="first", user_id="user-9"))

    rows = store.list_pending(limit=10)
    assert [item["id"] for item in rows] == [first_id, second_id]

