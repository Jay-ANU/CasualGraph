"""Offer letters that admins send to recruitment candidates by email.

The admin recruitment page writes a letter template containing
``{{placeholders}}``. This module validates the draft, fills the placeholders
for one candidate, renders the plain-text and HTML versions of the email and
stores every offer in the auth database so the page can track replies.
SMTP delivery itself lives in ``app.py`` next to the other mail settings.
"""

from __future__ import annotations

import html
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import aiosqlite


ORGANISATION_NAME = "CausalGraph AI"
LANGUAGES = ("en", "zh")
OFFER_STATUSES = ("sending", "sent", "failed", "accepted", "declined", "withdrawn")
# Statuses an admin can set by hand once the offer has been delivered.
MANUAL_STATUSES = ("sent", "accepted", "declined", "withdrawn")
RESENDABLE_STATUSES = ("sent", "failed")
# A send still marked "sending" after this long was cut off (e.g. by a restart).
SENDING_TIMEOUT_SECONDS = 180
INTERRUPTED_ERROR = "Delivery was interrupted, so the email may or may not have reached the candidate."

MAX_NAME_CHARS = 120
MAX_EMAIL_CHARS = 254
MAX_POSITION_CHARS = 160
MAX_SUBJECT_CHARS = 200
MAX_LETTER_CHARS = 10_000

PLACEHOLDER_LABELS: Dict[str, str] = {
    "candidate_name": "candidate name",
    "position": "position",
    "start_date": "start date",
    "respond_by": "reply date",
    "sender_name": "sender name",
}

_PLACEHOLDER_PATTERN = re.compile(r"\{\{[ \t]*([A-Za-z0-9_]+)[ \t]*\}\}")
# Same shape as the browser's <input type="email"> check, but the domain must contain a dot.
_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")

_EN_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_EN_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_ZH_WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")

_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "heading": "Offer letter",
        "position": "Position",
        "start_date": "Start date",
        "respond_by": "Please reply by",
        "separator": ": ",
        "footer": "Sent by {sender} on behalf of {organisation}. Reply to this email to respond to the offer.",
    },
    "zh": {
        "heading": "录用通知",
        "position": "职位",
        "start_date": "入职日期",
        "respond_by": "回复截止日期",
        "separator": "：",
        "footer": "本邮件由 {sender} 代表 {organisation} 发送。如需答复，请直接回复本邮件。",
    },
}

_FONT_SANS = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI','Helvetica Neue',Arial,"
    "'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif"
)
_FONT_SERIF = "Georgia,'Times New Roman','Songti SC',serif"
_PARAGRAPH_STYLE = (
    "margin:0 0 16px;font-size:15px;line-height:1.65;color:#1A1915;"
    "word-wrap:break-word;overflow-wrap:break-word;"
)
_MISSING_STYLE = "background-color:#FAF1DC;color:#8A5A00;border-radius:4px;padding:1px 4px;"

# A letter is filled into segments: ("text", literal text) or ("missing", label).
Segment = Tuple[str, str]


class OfferValidationError(ValueError):
    """Raised when an offer draft cannot be sent as written."""


@dataclass(frozen=True)
class OfferDraft:
    candidate_name: str
    candidate_email: str
    position: str
    start_date: str
    respond_by: str
    language: str
    subject: str
    letter: str
    sender_name: str


@dataclass(frozen=True)
class RenderedOffer:
    subject: str
    letter: str
    text: str
    html: str
    missing: List[str]
    unknown: List[str]


def clean_line(value: Any) -> str:
    """Single-line field: control characters and line breaks become single spaces."""
    return " ".join(_CONTROL_CHARS.sub(" ", str(value or "")).split())


def clean_letter(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL_CHARS.sub("", text).strip()


def is_valid_email(value: str) -> bool:
    return len(value) <= MAX_EMAIL_CHARS and bool(_EMAIL_PATTERN.match(value))


def parse_offer_date(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise OfferValidationError(f"{label} must be a date in YYYY-MM-DD format.") from exc


def format_offer_date(iso_value: str, language: str) -> str:
    if not iso_value:
        return ""
    day = date.fromisoformat(iso_value)
    if language == "zh":
        return f"{day.year}年{day.month}月{day.day}日（星期{_ZH_WEEKDAYS[day.weekday()]}）"
    return f"{_EN_WEEKDAYS[day.weekday()]} {day.day} {_EN_MONTHS[day.month - 1]} {day.year}"


def build_draft(
    *,
    candidate_name: Any,
    candidate_email: Any,
    position: Any,
    start_date: Any,
    respond_by: Any,
    language: Any,
    subject: Any,
    letter: Any,
    sender_name: Any,
    strict: bool,
) -> OfferDraft:
    """Normalise a draft. ``strict`` also requires everything needed to send it."""
    draft = OfferDraft(
        candidate_name=clean_line(candidate_name),
        candidate_email=clean_line(candidate_email).lower(),
        position=clean_line(position),
        start_date=parse_offer_date(start_date, "Start date"),
        respond_by=parse_offer_date(respond_by, "Reply date"),
        language=str(language or "en").strip().lower(),
        subject=clean_line(subject),
        letter=clean_letter(letter),
        # The sender's name can end up in the subject; keep it from reading as an encoded word.
        sender_name=clean_line(sender_name).replace("=?", "= ?"),
    )
    if draft.language not in LANGUAGES:
        raise OfferValidationError("Language must be English (en) or Chinese (zh).")
    # These values go into email headers, where "=?...?=" is decoded as an RFC 2047 encoded word
    # and could smuggle in line breaks or extra addresses.
    for label, value in (
        ("Candidate name", draft.candidate_name),
        ("Position", draft.position),
        ("Subject", draft.subject),
    ):
        if "=?" in value:
            raise OfferValidationError(f'{label} can\'t contain "=?".')
    for label, value, limit in (
        ("Candidate name", draft.candidate_name, MAX_NAME_CHARS),
        ("Candidate email", draft.candidate_email, MAX_EMAIL_CHARS),
        ("Position", draft.position, MAX_POSITION_CHARS),
        ("Subject", draft.subject, MAX_SUBJECT_CHARS),
        ("Letter", draft.letter, MAX_LETTER_CHARS),
    ):
        if len(value) > limit:
            raise OfferValidationError(f"{label} must be {limit:,} characters or fewer.")
    if strict:
        if not draft.candidate_name:
            raise OfferValidationError("Enter the candidate's name.")
        if not is_valid_email(draft.candidate_email):
            raise OfferValidationError("Enter a valid email address for the candidate.")
        if not draft.position:
            raise OfferValidationError("Enter the position you are offering.")
        if not draft.subject:
            raise OfferValidationError("Enter a subject for the email.")
        if not draft.letter:
            raise OfferValidationError("Write the offer letter.")
    return draft


def placeholder_values(draft: OfferDraft) -> Dict[str, str]:
    return {
        "candidate_name": draft.candidate_name,
        "position": draft.position,
        "start_date": format_offer_date(draft.start_date, draft.language),
        "respond_by": format_offer_date(draft.respond_by, draft.language),
        "sender_name": draft.sender_name,
    }


def fill_placeholders(template: str, values: Mapping[str, str]) -> Tuple[List[Segment], List[str], List[str]]:
    """Split a template into segments, filling known placeholders.

    Returns the segments, the placeholder keys that have no value yet and the
    unrecognised placeholders exactly as written.
    """
    segments: List[Segment] = []
    missing: List[str] = []
    unknown: List[str] = []
    position = 0
    for match in _PLACEHOLDER_PATTERN.finditer(template):
        if match.start() > position:
            segments.append(("text", template[position:match.start()]))
        key = match.group(1).lower()
        if key not in PLACEHOLDER_LABELS:
            unknown.append(match.group(0))
            segments.append(("text", match.group(0)))
        elif values.get(key):
            segments.append(("text", values[key]))
        else:
            missing.append(key)
            segments.append(("missing", PLACEHOLDER_LABELS[key]))
        position = match.end()
    if position < len(template):
        segments.append(("text", template[position:]))
    return segments, _unique(missing), _unique(unknown)


def segments_to_text(segments: Sequence[Segment]) -> str:
    return "".join(text if kind == "text" else f"[{text}]" for kind, text in segments)


def render_offer(draft: OfferDraft) -> RenderedOffer:
    values = placeholder_values(draft)
    subject_segments, subject_missing, subject_unknown = fill_placeholders(draft.subject, values)
    letter_segments, letter_missing, letter_unknown = fill_placeholders(draft.letter, values)
    subject = segments_to_text(subject_segments)
    text, html_body = compose_email_bodies(
        candidate_name=draft.candidate_name,
        position=draft.position,
        start_date=draft.start_date,
        respond_by=draft.respond_by,
        language=draft.language,
        sender_name=draft.sender_name,
        subject=subject,
        letter_segments=letter_segments,
    )
    return RenderedOffer(
        subject=subject,
        letter=segments_to_text(letter_segments),
        text=text,
        html=html_body,
        missing=_unique(subject_missing + letter_missing),
        unknown=_unique(subject_unknown + letter_unknown),
    )


def compose_email_bodies(
    *,
    candidate_name: str,
    position: str,
    start_date: str,
    respond_by: str,
    language: str,
    sender_name: str,
    subject: str,
    letter_segments: Sequence[Segment],
) -> Tuple[str, str]:
    """Build the plain-text and HTML bodies around an already filled letter."""
    copy = _COPY.get(language, _COPY["en"])
    details = [
        (copy["start_date"], format_offer_date(start_date, language)),
        (copy["respond_by"], format_offer_date(respond_by, language)),
    ]
    details = [(label, value) for label, value in details if value]
    footer = copy["footer"].format(sender=sender_name or ORGANISATION_NAME, organisation=ORGANISATION_NAME)

    text_lines = [segments_to_text(letter_segments).strip(), "", "----"]
    text_lines.append(f"{copy['position']}{copy['separator']}{position or '[position]'}")
    text_lines.extend(f"{label}{copy['separator']}{value}" for label, value in details)
    text_lines.extend(["", footer])
    text = "\n".join(text_lines) + "\n"

    position_html = html.escape(position) if position else _missing_html(PLACEHOLDER_LABELS["position"])
    detail_rows = "".join(
        "<tr>"
        f'<td style="padding:10px 16px 10px 0;border-top:1px solid #EFEDE8;font-size:13px;color:#87837A;'
        f'white-space:nowrap;vertical-align:top;">{html.escape(label)}</td>'
        f'<td style="padding:10px 0;border-top:1px solid #EFEDE8;font-size:14px;color:#1A1915;'
        f'vertical-align:top;">{html.escape(value)}</td>'
        "</tr>"
        for label, value in details
    )
    details_html = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:0 0 24px;border-bottom:1px solid #EFEDE8;">{detail_rows}</table>'
        if detail_rows
        else ""
    )
    html_body = f"""<!DOCTYPE html>
<html lang="{'zh-CN' if language == 'zh' else 'en'}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(subject)}</title>
</head>
<body style="margin:0;padding:0;background-color:#FBFAF8;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#FBFAF8;">
<tr>
<td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;font-family:{_FONT_SANS};">
<tr>
<td style="padding:0 4px 14px;font-size:14px;font-weight:600;color:#1A1915;">{ORGANISATION_NAME}</td>
</tr>
<tr>
<td style="background-color:#FFFFFF;border:1px solid #E7E4DD;border-radius:12px;padding:32px 32px 16px;">
<p style="margin:0 0 6px;font-size:13px;color:#87837A;">{html.escape(copy['heading'])}</p>
<h1 style="margin:0 0 20px;font-family:{_FONT_SERIF};font-size:26px;font-weight:400;line-height:1.25;color:#1A1915;">{position_html}</h1>
{details_html}
{_letter_html(letter_segments)}
</td>
</tr>
<tr>
<td style="padding:16px 4px 0;font-size:12px;line-height:1.6;color:#87837A;">{html.escape(footer)}</td>
</tr>
</table>
</td>
</tr>
</table>
</body>
</html>
"""
    return text, html_body


def missing_placeholder_messages(rendered: RenderedOffer) -> List[str]:
    messages = [
        f"Add the {PLACEHOLDER_LABELS[key]} or remove {{{{{key}}}}} from the email."
        for key in rendered.missing
    ]
    messages.extend(f"{token} is not a placeholder this page can fill." for token in rendered.unknown)
    return messages


def date_warnings(draft: OfferDraft, today: Optional[date] = None) -> List[str]:
    """Advisory checks only. A day of slack keeps admins in other time zones clear of false alarms."""
    reference = (today or datetime.now(timezone.utc).date()) - timedelta(days=1)
    warnings: List[str] = []
    if draft.start_date and date.fromisoformat(draft.start_date) < reference:
        warnings.append("The start date is in the past.")
    if draft.respond_by and date.fromisoformat(draft.respond_by) < reference:
        warnings.append("The reply date is in the past.")
    if draft.start_date and draft.respond_by and draft.respond_by > draft.start_date:
        warnings.append("The reply date is after the start date.")
    return warnings


def _letter_html(segments: Sequence[Segment]) -> str:
    inline = "".join(html.escape(text) if kind == "text" else _missing_html(text) for kind, text in segments)
    paragraphs = [block.strip("\n") for block in _PARAGRAPH_BREAK.split(inline.strip())]
    return "\n".join(
        f'<p style="{_PARAGRAPH_STYLE}">{block.replace(chr(10), "<br>")}</p>'
        for block in paragraphs
        if block.strip()
    )


def _missing_html(label: str) -> str:
    return f'<span style="{_MISSING_STYLE}">[{html.escape(label)}]</span>'


def _unique(items: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(items))


# ── Storage ──────────────────────────────────────────────────────────────────

_OFFER_COLUMNS = (
    "id",
    "candidate_name",
    "candidate_email",
    "position",
    "start_date",
    "respond_by",
    "language",
    "subject",
    "letter",
    "sender_name",
    "reply_to",
    "bcc",
    "status",
    "delivery",
    "last_error",
    "send_count",
    "created_by_user_id",
    "created_by_email",
    "created_at",
    "sent_at",
    "updated_at",
)
_SELECT_OFFER = f"SELECT {', '.join(_OFFER_COLUMNS)} FROM recruitment_offers"


async def init_recruitment_db(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS recruitment_offers (
            id TEXT PRIMARY KEY,
            candidate_name TEXT NOT NULL,
            candidate_email TEXT NOT NULL,
            position TEXT NOT NULL,
            start_date TEXT,
            respond_by TEXT,
            language TEXT NOT NULL DEFAULT 'en',
            subject TEXT NOT NULL,
            letter TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            reply_to TEXT,
            bcc TEXT,
            status TEXT NOT NULL,
            delivery TEXT,
            last_error TEXT,
            send_count INTEGER NOT NULL DEFAULT 0,
            created_by_user_id TEXT NOT NULL,
            created_by_email TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    await db.execute("CREATE INDEX IF NOT EXISTS recruitment_offers_created_at_idx ON recruitment_offers(created_at)")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS recruitment_offers_candidate_idx ON recruitment_offers(candidate_email, created_at)"
    )


def offer_payload(row: Sequence[Any]) -> Dict[str, Any]:
    record = dict(zip(_OFFER_COLUMNS, row))
    record["copy_to_sender"] = bool(record.pop("bcc"))
    record.pop("created_by_user_id", None)
    record["send_count"] = int(record.get("send_count") or 0)
    return record


async def list_offers(db: aiosqlite.Connection, *, limit: int = 200) -> List[Dict[str, Any]]:
    cursor = await db.execute(f"{_SELECT_OFFER} ORDER BY created_at DESC LIMIT ?", (int(limit),))
    return [offer_payload(row) for row in await cursor.fetchall()]


async def get_offer_row(db: aiosqlite.Connection, offer_id: str) -> Optional[Dict[str, Any]]:
    """The full stored record, including the private reply-to and Bcc addresses."""
    cursor = await db.execute(f"{_SELECT_OFFER} WHERE id = ?", (str(offer_id),))
    row = await cursor.fetchone()
    return dict(zip(_OFFER_COLUMNS, row)) if row else None


async def get_offer(db: aiosqlite.Connection, offer_id: str) -> Optional[Dict[str, Any]]:
    cursor = await db.execute(f"{_SELECT_OFFER} WHERE id = ?", (str(offer_id),))
    row = await cursor.fetchone()
    return offer_payload(row) if row else None


async def find_recent_duplicate(
    db: aiosqlite.Connection,
    *,
    candidate_email: str,
    position: str,
    within_seconds: int = 60,
) -> Optional[Dict[str, Any]]:
    """An offer for the same candidate and position sent or sending moments ago, e.g. from a double submit.

    Offers whose delivery failed don't count, so the admin can send again straight away.
    """
    since = (datetime.now(timezone.utc) - timedelta(seconds=within_seconds)).isoformat()
    cursor = await db.execute(
        f"{_SELECT_OFFER} WHERE candidate_email = ? AND lower(position) = lower(?) AND created_at >= ? "
        "AND status != 'failed' ORDER BY created_at DESC LIMIT 1",
        (candidate_email, position, since),
    )
    row = await cursor.fetchone()
    return offer_payload(row) if row else None


async def insert_offer(
    db: aiosqlite.Connection,
    *,
    draft: OfferDraft,
    rendered: RenderedOffer,
    reply_to: Optional[str],
    bcc: Optional[str],
    created_by_user_id: str,
    created_by_email: str,
) -> Dict[str, Any]:
    """Record the offer as "sending" before delivery starts."""
    offer_id = str(uuid.uuid4())
    now = _utc_now_iso()
    await db.execute(
        f"""
        INSERT INTO recruitment_offers ({', '.join(_OFFER_COLUMNS)})
        VALUES ({', '.join('?' for _ in _OFFER_COLUMNS)})
        """,
        (
            offer_id,
            draft.candidate_name,
            draft.candidate_email,
            draft.position,
            draft.start_date or None,
            draft.respond_by or None,
            draft.language,
            rendered.subject,
            rendered.letter,
            draft.sender_name,
            reply_to,
            bcc,
            "sending",
            None,
            None,
            0,
            created_by_user_id,
            created_by_email,
            now,
            None,
            now,
        ),
    )
    await db.commit()
    return await get_offer(db, offer_id)


async def record_delivery(db: aiosqlite.Connection, offer_id: str, *, delivery: str) -> Dict[str, Any]:
    now = _utc_now_iso()
    await db.execute(
        """
        UPDATE recruitment_offers
        SET status = 'sent', delivery = ?, last_error = NULL, send_count = send_count + 1,
            sent_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (delivery, now, now, str(offer_id)),
    )
    await db.commit()
    return await get_offer(db, offer_id)


async def record_failure(db: aiosqlite.Connection, offer_id: str, *, error: str) -> Dict[str, Any]:
    """Keep the error. An offer that already reached the candidate once goes back to 'sent'."""
    await db.execute(
        """
        UPDATE recruitment_offers
        SET status = CASE WHEN sent_at IS NULL THEN 'failed' ELSE 'sent' END,
            last_error = ?, updated_at = ?
        WHERE id = ?
        """,
        (error[:500], _utc_now_iso(), str(offer_id)),
    )
    await db.commit()
    return await get_offer(db, offer_id)


async def claim_for_resend(db: aiosqlite.Connection, offer_id: str, *, cooldown_seconds: int) -> bool:
    """Mark an offer as sending again.

    False if another request is sending it or delivered it within the cooldown.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)).isoformat()
    cursor = await db.execute(
        """
        UPDATE recruitment_offers SET status = 'sending', updated_at = ?
        WHERE id = ? AND (status = 'failed' OR (status = 'sent' AND (sent_at IS NULL OR sent_at < ?)))
        """,
        (_utc_now_iso(), str(offer_id), cutoff),
    )
    await db.commit()
    return cursor.rowcount > 0


async def expire_stale_sends(db: aiosqlite.Connection) -> None:
    """Sends cut off mid-delivery (e.g. by a restart) stop blocking the offer."""
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=SENDING_TIMEOUT_SECONDS)).isoformat()
    await db.execute(
        """
        UPDATE recruitment_offers
        SET status = CASE WHEN sent_at IS NULL THEN 'failed' ELSE 'sent' END,
            last_error = ?, updated_at = ?
        WHERE status = 'sending' AND updated_at < ?
        """,
        (INTERRUPTED_ERROR, _utc_now_iso(), cutoff),
    )
    await db.commit()


async def update_status(db: aiosqlite.Connection, offer_id: str, status: str) -> Optional[Dict[str, Any]]:
    """Set the status by hand. None if the offer is being sent right now."""
    cursor = await db.execute(
        "UPDATE recruitment_offers SET status = ?, updated_at = ? WHERE id = ? AND status != 'sending'",
        (status, _utc_now_iso(), str(offer_id)),
    )
    await db.commit()
    return await get_offer(db, offer_id) if cursor.rowcount > 0 else None


async def delete_offer(db: aiosqlite.Connection, offer_id: str) -> bool:
    """Delete an offer record unless it is being sent right now."""
    cursor = await db.execute(
        "DELETE FROM recruitment_offers WHERE id = ? AND status != 'sending'",
        (str(offer_id),),
    )
    await db.commit()
    return cursor.rowcount > 0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
