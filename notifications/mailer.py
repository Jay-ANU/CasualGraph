"""SMTP sender for unanswered-query digests."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Iterable, Tuple
from urllib.parse import unquote, urlparse


def send_digest(*, subject: str, body: str, smtp_url: str | None, recipients: Iterable[str]) -> Tuple[str, int]:
    clean_recipients = [item.strip() for item in recipients if str(item or "").strip()]
    if not smtp_url or not clean_recipients:
        print(subject)
        print()
        print(body)
        return ("stdout", len(clean_recipients))

    parsed = urlparse(smtp_url)
    if parsed.scheme not in {"smtp", "smtps"}:
        raise ValueError("NOTIFICATIONS_SMTP_URL must use smtp:// or smtps://")
    if not parsed.hostname or not parsed.port:
        raise ValueError("NOTIFICATIONS_SMTP_URL must include host and port")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = unquote(parsed.username or "notifications@localhost")
    message["To"] = ", ".join(clean_recipients)
    message.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(parsed.hostname, parsed.port, timeout=30) as client:
        client.ehlo()
        client.starttls(context=context)
        client.ehlo()
        if parsed.username:
            client.login(unquote(parsed.username), unquote(parsed.password or ""))
        client.send_message(message)
    return ("smtp", len(clean_recipients))

