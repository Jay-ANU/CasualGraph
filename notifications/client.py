"""Fire-and-forget client for unanswered-query notifications."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from configs.settings import NOTIFICATIONS_ENABLED


_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="notify")


def notify_unanswerable_async(**kwargs) -> None:
    """Fire-and-forget. Never raises. Never blocks."""
    if not NOTIFICATIONS_ENABLED:
        return
    try:
        _executor.submit(_safe_record, kwargs)
    except Exception as exc:
        print(f"[notify] submit failed: {type(exc).__name__}: {exc}")


def _safe_record(kwargs: dict) -> None:
    try:
        from notifications.store import record_unanswered

        record_unanswered(**kwargs)
    except Exception as exc:
        print(f"[notify] record failed: {type(exc).__name__}: {exc}")

