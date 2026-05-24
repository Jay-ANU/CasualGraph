"""Controlled email sender used by the MCP email tool."""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

from configs.settings import (
    MCP_EMAIL_ALLOWED_RECIPIENTS,
    MCP_EMAIL_ALLOW_ALL,
    MCP_EMAIL_AUDIT_PATH,
    MCP_EMAIL_DRY_RUN,
    MCP_EMAIL_ENABLED,
    MCP_EMAIL_MAX_BODY_CHARS,
)


class EmailToolError(ValueError):
    """Raised when a controlled email request is invalid or blocked."""


@dataclass
class EmailSendResult:
    mode: str
    recipients: List[str]
    subject: str
    audit_id: str
    sent: bool
    dry_run: bool
    reason: str


def send_mcp_email(
    *,
    to: Union[Sequence[str], str],
    subject: str,
    body: str,
    reason: str,
    evidence_refs: Optional[Sequence[str]] = None,
    dry_run: Optional[bool] = None,
    metadata: Optional[Dict[str, Any]] = None,
    smtp_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    """Validate, audit, and optionally send an email for an MCP caller."""

    recipients = _normalize_recipients(to)
    clean_subject = _validate_subject(subject)
    clean_body = _validate_body(body)
    clean_reason = _validate_reason(reason)
    _assert_recipients_allowed(recipients)

    effective_dry_run = bool(dry_run) or MCP_EMAIL_DRY_RUN or not MCP_EMAIL_ENABLED
    mode = "dry_run"
    sent = False
    if not effective_dry_run:
        _send_smtp(
            recipients=recipients,
            subject=clean_subject,
            body=clean_body,
            smtp_factory=smtp_factory,
        )
        mode = "smtp"
        sent = True

    audit_id = _write_audit(
        mode=mode,
        recipients=recipients,
        subject=clean_subject,
        body=clean_body,
        reason=clean_reason,
        evidence_refs=list(evidence_refs or []),
        metadata=metadata or {},
    )
    result = EmailSendResult(
        mode=mode,
        recipients=recipients,
        subject=clean_subject,
        audit_id=audit_id,
        sent=sent,
        dry_run=effective_dry_run,
        reason=clean_reason,
    )
    return asdict(result)


def _normalize_recipients(value: Union[Sequence[str], str]) -> List[str]:
    raw_items: Iterable[str]
    if isinstance(value, str):
        raw_items = value.replace(";", ",").split(",")
    else:
        raw_items = value
    recipients: List[str] = []
    seen = set()
    for item in raw_items:
        email = str(item or "").strip().lower()
        if not email:
            continue
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise EmailToolError(f"Invalid recipient: {item}")
        if email not in seen:
            recipients.append(email)
            seen.add(email)
    if not recipients:
        raise EmailToolError("At least one recipient is required")
    return recipients


def _validate_subject(value: str) -> str:
    subject = str(value or "").strip()
    if not subject:
        raise EmailToolError("Subject is required")
    if len(subject) > 180:
        raise EmailToolError("Subject is too long")
    if "\n" in subject or "\r" in subject:
        raise EmailToolError("Subject must be a single line")
    return subject


def _validate_body(value: str) -> str:
    body = str(value or "").strip()
    if not body:
        raise EmailToolError("Body is required")
    if len(body) > MCP_EMAIL_MAX_BODY_CHARS:
        raise EmailToolError(f"Body exceeds {MCP_EMAIL_MAX_BODY_CHARS} characters")
    return body


def _validate_reason(value: str) -> str:
    reason = str(value or "").strip()
    if not reason:
        raise EmailToolError("Reason is required for audit")
    if len(reason) > 500:
        raise EmailToolError("Reason is too long")
    return reason


def _assert_recipients_allowed(recipients: Sequence[str]) -> None:
    if MCP_EMAIL_ALLOW_ALL:
        return
    allowlist = _allowed_recipient_tokens()
    if not allowlist:
        raise EmailToolError("MCP_EMAIL_ALLOWED_RECIPIENTS is empty; refusing to send email")
    blocked = [email for email in recipients if not _recipient_allowed(email, allowlist)]
    if blocked:
        raise EmailToolError(f"Recipient is not allowlisted: {', '.join(blocked)}")


def _allowed_recipient_tokens() -> List[str]:
    return [
        token.strip().lower()
        for token in str(MCP_EMAIL_ALLOWED_RECIPIENTS or "").replace(";", ",").split(",")
        if token.strip()
    ]


def _recipient_allowed(email: str, allowlist: Sequence[str]) -> bool:
    domain = email[email.index("@") :]
    return any(token == email or token == domain for token in allowlist)


def _send_smtp(
    *,
    recipients: Sequence[str],
    subject: str,
    body: str,
    smtp_factory: Optional[Any] = None,
) -> None:
    mail_enabled = _env_flag("MAIL_ENABLED", False)
    if not mail_enabled:
        raise EmailToolError("MAIL_ENABLED must be true for non-dry-run email")
    host = os.getenv("MAIL_SMTP_HOST", "").strip()
    port = int(os.getenv("MAIL_SMTP_PORT", "465"))
    use_ssl = _env_flag("MAIL_SMTP_SSL", True)
    use_starttls = _env_flag("MAIL_SMTP_STARTTLS", False)
    username = os.getenv("MAIL_SMTP_USER", "").strip()
    password = os.getenv("MAIL_SMTP_PASSWORD", "").strip()
    from_addr = os.getenv("MAIL_FROM", username).strip()
    from_name = os.getenv("MAIL_FROM_NAME", "CausalGraph AI").strip()
    missing = [
        name
        for name, value in {
            "MAIL_SMTP_HOST": host,
            "MAIL_SMTP_USER": username,
            "MAIL_SMTP_PASSWORD": password,
            "MAIL_FROM": from_addr,
        }.items()
        if not value
    ]
    if missing:
        raise EmailToolError(f"Email delivery is missing configuration: {', '.join(missing)}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((from_name, from_addr))
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    if smtp_factory is not None:
        with smtp_factory(host, port) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
        return

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
        return

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        if use_starttls:
            smtp.starttls(context=context)
        smtp.login(username, password)
        smtp.send_message(message)


def _write_audit(
    *,
    mode: str,
    recipients: Sequence[str],
    subject: str,
    body: str,
    reason: str,
    evidence_refs: Sequence[str],
    metadata: Dict[str, Any],
) -> str:
    audit_path = Path(MCP_EMAIL_AUDIT_PATH).expanduser()
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    audit_id = f"email_{uuid.uuid4().hex}"
    row = {
        "id": audit_id,
        "created_at": now.isoformat(),
        "mode": mode,
        "recipients": list(recipients),
        "subject": subject,
        "reason": reason,
        "evidence_refs": list(evidence_refs),
        "body_chars": len(body),
        "body_preview": body[:500],
        "metadata": metadata,
    }
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return audit_id


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}
