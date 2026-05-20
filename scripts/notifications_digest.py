"""CLI to render and optionally send unanswered-query digests."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from configs.settings import NOTIFICATIONS_ADMIN_EMAILS, NOTIFICATIONS_SMTP_URL
from notifications.digest import build_digest, build_subject
from notifications.mailer import send_digest
from notifications.store import get_stats, list_pending, mark_sent


def main() -> int:
    parser = argparse.ArgumentParser(description="Render or send unanswered-query digests.")
    parser.add_argument("--dry-run", action="store_true", help="Print digest to stdout without marking rows sent.")
    parser.add_argument("--window-hours", type=int, default=24, help="Look back window for pending rows.")
    args = parser.parse_args()

    since = datetime.now(timezone.utc) - timedelta(hours=max(1, int(args.window_hours)))
    pending = list_pending(limit=100, since=since)
    stats = get_stats(window_hours=args.window_hours)
    digest_text = build_digest(pending, window_hours=args.window_hours, stats=stats)

    if args.dry_run:
        print(digest_text)
        return 0

    if not pending:
        print(digest_text)
        return 0

    subject = build_subject(pending, window_hours=args.window_hours)
    recipients = [item.strip() for item in NOTIFICATIONS_ADMIN_EMAILS.split(",") if item.strip()]
    try:
        mode, recipient_count = send_digest(
            subject=subject,
            body=digest_text,
            smtp_url=NOTIFICATIONS_SMTP_URL,
            recipients=recipients,
        )
        print(f"[notifications] delivered via {mode} to {recipient_count} recipients")
        if mode == "smtp":
            mark_sent([int(item["id"]) for item in pending])
        else:
            print("[notifications] SMTP not configured; rows left pending")
    except Exception as exc:
        print(f"[notifications] digest failed: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
