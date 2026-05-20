from __future__ import annotations

import scripts.notifications_digest as digest_script
from notifications.digest import build_digest


def test_build_digest_orders_by_distinct_users_then_occurrence():
    records = [
        {
            "id": 1,
            "query": "many users",
            "occurrence_count": 3,
            "user_ids": ["aaaa1111", "bbbb2222", "cccc3333"],
            "failure_reason": "insufficient_context",
            "retrieval_strategy": "hybrid",
            "top_sources_preview": [],
            "last_seen_at": "2026-05-15T10:00:00+00:00",
        },
        {
            "id": 2,
            "query": "same user many times",
            "occurrence_count": 5,
            "user_ids": ["aaaa1111"],
            "failure_reason": "no_context",
            "retrieval_strategy": "vector_only",
            "top_sources_preview": [{"chunk_id": "chunk_9", "document_id": "doc_9", "score": 0.99}],
            "last_seen_at": "2026-05-15T11:00:00+00:00",
        },
        {
            "id": 3,
            "query": "query singleton",
            "occurrence_count": 1,
            "user_ids": ["cccc3333"],
            "failure_reason": "extractive_fallback",
            "retrieval_strategy": "hybrid",
            "top_sources_preview": [],
            "last_seen_at": "2026-05-15T09:00:00+00:00",
        },
    ]
    stats = {"total": 3, "unique_queries": 3, "by_reason": {"no_context": 1}, "top_recurring": records[:2]}

    text = build_digest(records, window_hours=24, stats=stats)

    assert "many users" in text
    assert "same user many times" in text
    assert "query singleton" in text
    assert text.index("many users") < text.index("same user many times")
    assert text.index("same user many times") < text.index("query singleton")


def test_build_digest_empty_window():
    text = build_digest([], window_hours=24, stats={"total": 0, "unique_queries": 0, "by_reason": {}, "top_recurring": []})
    assert text == "No unanswered questions in window"


def test_digest_script_keeps_rows_pending_without_smtp(monkeypatch, capsys):
    pending = [{"id": 11, "query": "q1", "occurrence_count": 1, "user_ids": [], "last_seen_at": "2026-05-15T10:00:00+00:00"}]
    marked_ids = []

    monkeypatch.setattr(digest_script, "list_pending", lambda limit, since: pending)
    monkeypatch.setattr(
        digest_script,
        "get_stats",
        lambda window_hours: {"total": 1, "unique_queries": 1, "by_reason": {"no_context": 1}, "top_recurring": []},
    )
    monkeypatch.setattr(digest_script, "send_digest", lambda **kwargs: ("stdout", 0))
    monkeypatch.setattr(digest_script, "mark_sent", lambda ids: marked_ids.extend(ids))
    monkeypatch.setattr(digest_script, "NOTIFICATIONS_ADMIN_EMAILS", "ops@example.com")
    monkeypatch.setattr(digest_script, "NOTIFICATIONS_SMTP_URL", "")
    monkeypatch.setattr("sys.argv", ["notifications_digest.py"])

    assert digest_script.main() == 0
    assert marked_ids == []
    output = capsys.readouterr().out
    assert "SMTP not configured; rows left pending" in output


def test_digest_script_marks_rows_sent_after_smtp_delivery(monkeypatch):
    pending = [{"id": 12, "query": "q2", "occurrence_count": 1, "user_ids": [], "last_seen_at": "2026-05-15T10:00:00+00:00"}]
    marked_ids = []

    monkeypatch.setattr(digest_script, "list_pending", lambda limit, since: pending)
    monkeypatch.setattr(
        digest_script,
        "get_stats",
        lambda window_hours: {"total": 1, "unique_queries": 1, "by_reason": {"no_context": 1}, "top_recurring": []},
    )
    monkeypatch.setattr(digest_script, "send_digest", lambda **kwargs: ("smtp", 2))
    monkeypatch.setattr(digest_script, "mark_sent", lambda ids: marked_ids.extend(ids))
    monkeypatch.setattr(digest_script, "NOTIFICATIONS_ADMIN_EMAILS", "ops@example.com")
    monkeypatch.setattr(digest_script, "NOTIFICATIONS_SMTP_URL", "smtp://example")
    monkeypatch.setattr("sys.argv", ["notifications_digest.py"])

    assert digest_script.main() == 0
    assert marked_ids == [12]
