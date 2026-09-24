"""Offer letters that admins send to recruitment candidates by email.

The admin recruitment page writes a letter template containing
``{{placeholders}}`` and fills in the offer details (position, salary,
benefits and so on). This module validates the draft, fills the placeholders
for one candidate, renders the plain-text and HTML versions of the email and
stores every offer in the auth database. Each offer gets a private link to
its offer page, where the candidate sees the full details and can accept or
decline; the admin page tracks views and replies.
SMTP delivery itself lives in ``app.py`` next to the other mail settings.
"""

from __future__ import annotations

import html
import json
import re
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import aiosqlite


ORGANISATION_NAME = "CausalGraph AI"
LANGUAGES = ("en", "zh")
OFFER_STATUSES = ("sending", "sent", "failed", "accepted", "declined", "withdrawn")
# Statuses an admin can set by hand once the offer has been delivered.
MANUAL_STATUSES = ("sent", "accepted", "declined", "withdrawn")
RESENDABLE_STATUSES = ("sent", "failed")
# What the candidate can do on the offer page, and the status each choice records.
CANDIDATE_DECISIONS = {"accept": "accepted", "decline": "declined"}
# A send still marked "sending" after this long was cut off (e.g. by a restart).
SENDING_TIMEOUT_SECONDS = 180
INTERRUPTED_ERROR = "Delivery was interrupted, so the email may or may not have reached the candidate."

# Animated banner embedded in every offer email (see scripts/generate_offer_assets.py).
HERO_IMAGE_PATH = Path(__file__).resolve().parent / "assets" / "recruitment" / "offer-hero.gif"
HERO_CID = "offer-hero@causalgraph.ai"

MAX_NAME_CHARS = 120
MAX_EMAIL_CHARS = 254
MAX_POSITION_CHARS = 160
MAX_DETAIL_CHARS = 120
MAX_EXTRA_COMPENSATION_CHARS = 200
MAX_BENEFITS = 12
MAX_BENEFIT_CHARS = 120
MAX_SUBJECT_CHARS = 200
MAX_LETTER_CHARS = 10_000
MAX_NOTE_CHARS = 1_000
MAX_SALARY = Decimal("10000000000")

# Candidates can be anywhere; keep in sync with CURRENCIES in the offer page's offerContent.ts.
CURRENCIES = (
    "AUD", "USD", "EUR", "GBP", "CNY", "HKD", "SGD", "JPY", "CAD", "NZD",
    "AED", "BRL", "CHF", "CZK", "DKK", "IDR", "ILS", "INR", "KRW", "MXN",
    "MYR", "NOK", "PHP", "PLN", "SAR", "SEK", "THB", "TRY", "TWD", "VND",
    "ZAR",
)
SALARY_PERIODS = ("year", "month", "week", "day", "hour")
EMPLOYMENT_TYPES = ("full_time", "part_time", "internship", "contract", "casual")

PLACEHOLDER_LABELS: Dict[str, str] = {
    "candidate_name": "candidate name",
    "position": "position",
    "team": "team",
    "location": "location",
    "salary": "salary",
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
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")

_EN_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_EN_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_ZH_WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")

_COPY: Dict[str, Dict[str, Any]] = {
    "en": {
        "heading": "Offer of employment",
        "confidential": "Private and confidential",
        "preheader": "Your offer of employment from {organisation}.",
        "prepared_for": "Prepared for {name}",
        "reference": "Reference",
        "position": "Position",
        "team": "Team",
        "employment_type": "Employment",
        "location": "Location",
        "start_date": "Start date",
        "respond_by": "Please reply by",
        "cta": "View your offer",
        "link_hint": "If the button does not open, copy this link into your browser:",
        "text_link": "Your offer page, with the full details including compensation and benefits:",
        "separator": ": ",
        "footer": (
            "Sent by {sender} on behalf of {organisation}. Reply to this email with any questions. "
            "The offer page is for you alone; please don’t forward the link."
        ),
        "employment_types": {
            "full_time": "Full-time",
            "part_time": "Part-time",
            "internship": "Internship",
            "contract": "Contract",
            "casual": "Casual",
        },
        "periods": {"year": "per year", "month": "per month", "week": "per week", "day": "per day", "hour": "per hour"},
    },
    "zh": {
        "heading": "录用通知",
        "confidential": "私人机密",
        "preheader": "来自 {organisation} 的录用通知。",
        "prepared_for": "致 {name}",
        "reference": "编号",
        "position": "职位",
        "team": "团队",
        "employment_type": "用工类型",
        "location": "工作地点",
        "start_date": "入职日期",
        "respond_by": "回复截止日期",
        "cta": "查看录用详情",
        "link_hint": "按钮无法打开？请将此链接复制到浏览器：",
        "text_link": "查看完整录用详情（含薪酬与福利）：",
        "separator": "：",
        "footer": "本邮件由 {sender} 代表 {organisation} 发送。如有疑问，请直接回复本邮件。录用页面仅供您本人查看，请勿转发链接。",
        "employment_types": {
            "full_time": "全职",
            "part_time": "兼职",
            "internship": "实习",
            "contract": "合同制",
            "casual": "临时",
        },
        "periods": {"year": "年", "month": "月", "week": "周", "day": "日", "hour": "小时"},
    },
}

# The email is set like the offer page: warm paper, graphite ink, hairlines, a serif for the
# letter. Only fonts the reader already has are named; nothing is fetched from the network.
_FONT_SANS = (
    "'IBM Plex Sans',-apple-system,BlinkMacSystemFont,'Segoe UI','Helvetica Neue',Arial,"
    "'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif"
)
_FONT_SERIF = "'Newsreader','Iowan Old Style','Palatino Linotype',Georgia,'Times New Roman','Songti SC',serif"
_FONT_MONO = "'IBM Plex Mono','SFMono-Regular',Menlo,Consolas,'Liberation Mono',monospace"
_PARAGRAPH_STYLE = (
    f"margin:0 0 16px;font-family:{_FONT_SERIF};font-size:17px;line-height:1.65;color:#3D3B36;"
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
    team: str = ""
    location: str = ""
    employment_type: str = ""
    reports_to: str = ""
    salary_amount: str = ""
    salary_currency: str = "AUD"
    salary_period: str = "year"
    extra_compensation: str = ""
    benefits: Tuple[str, ...] = field(default_factory=tuple)


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


def parse_salary_amount(value: Any) -> str:
    """A plain decimal string such as "95000" or "42.5", or "" when no salary is given."""
    text = str(value if value is not None else "").strip().replace(",", "").replace(" ", "")
    if not text:
        return ""
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise OfferValidationError("Salary must be a number.") from exc
    if not amount.is_finite() or amount < 0 or amount >= MAX_SALARY:
        raise OfferValidationError("Salary must be a positive number.")
    return format(amount.quantize(Decimal("0.01")).normalize(), "f")


def format_salary(amount: str, currency: str, period: str, language: str) -> str:
    if not amount:
        return ""
    value = Decimal(amount)
    number = f"{value:,.0f}" if value == value.to_integral_value() else f"{value:,.2f}"
    periods = _COPY.get(language, _COPY["en"])["periods"]
    if language == "zh":
        return f"{currency} {number} / {periods.get(period, period)}"
    return f"{currency} {number} {periods.get(period, period)}"


def clean_benefits(values: Any) -> Tuple[str, ...]:
    raw = values.split("\n") if isinstance(values, str) else list(values or [])
    items = tuple(item for item in (clean_line(value) for value in raw) if item)
    if len(items) > MAX_BENEFITS:
        raise OfferValidationError(f"List at most {MAX_BENEFITS} benefits.")
    for item in items:
        if len(item) > MAX_BENEFIT_CHARS:
            raise OfferValidationError(f"Each benefit must be {MAX_BENEFIT_CHARS} characters or fewer.")
    return items


def new_offer_token() -> str:
    return secrets.token_urlsafe(24)


def is_offer_token(value: str) -> bool:
    return bool(_TOKEN_PATTERN.match(str(value or "")))


@lru_cache(maxsize=1)
def hero_image_bytes() -> Optional[bytes]:
    try:
        return HERO_IMAGE_PATH.read_bytes()
    except OSError:
        return None


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
    team: Any = "",
    location: Any = "",
    employment_type: Any = "",
    reports_to: Any = "",
    salary_amount: Any = "",
    salary_currency: Any = "AUD",
    salary_period: Any = "year",
    extra_compensation: Any = "",
    benefits: Any = (),
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
        team=clean_line(team),
        location=clean_line(location),
        employment_type=clean_line(employment_type).lower(),
        reports_to=clean_line(reports_to),
        salary_amount=parse_salary_amount(salary_amount),
        salary_currency=clean_line(salary_currency).upper() or "AUD",
        salary_period=clean_line(salary_period).lower() or "year",
        extra_compensation=clean_line(extra_compensation),
        benefits=clean_benefits(benefits),
    )
    if draft.language not in LANGUAGES:
        raise OfferValidationError("Language must be English (en) or Chinese (zh).")
    if draft.salary_currency not in CURRENCIES:
        raise OfferValidationError(f"Currency must be one of {', '.join(CURRENCIES)}.")
    if draft.salary_period not in SALARY_PERIODS:
        raise OfferValidationError("Salary period must be year, month, week, day or hour.")
    if draft.employment_type and draft.employment_type not in EMPLOYMENT_TYPES:
        raise OfferValidationError("Employment type is not recognised.")
    # These values can reach email headers (directly or through a placeholder in the subject),
    # where "=?...?=" is decoded as an RFC 2047 encoded word and could smuggle in line breaks
    # or extra addresses.
    for label, value in (
        ("Candidate name", draft.candidate_name),
        ("Position", draft.position),
        ("Subject", draft.subject),
        ("Team", draft.team),
        ("Location", draft.location),
    ):
        if "=?" in value:
            raise OfferValidationError(f'{label} can\'t contain "=?".')
    for label, value, limit in (
        ("Candidate name", draft.candidate_name, MAX_NAME_CHARS),
        ("Candidate email", draft.candidate_email, MAX_EMAIL_CHARS),
        ("Position", draft.position, MAX_POSITION_CHARS),
        ("Team", draft.team, MAX_DETAIL_CHARS),
        ("Location", draft.location, MAX_DETAIL_CHARS),
        ("Reports to", draft.reports_to, MAX_DETAIL_CHARS),
        ("Extra compensation", draft.extra_compensation, MAX_EXTRA_COMPENSATION_CHARS),
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
        "team": draft.team,
        "location": draft.location,
        "salary": format_salary(draft.salary_amount, draft.salary_currency, draft.salary_period, draft.language),
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


def render_offer(draft: OfferDraft, *, offer_url: str) -> RenderedOffer:
    values = placeholder_values(draft)
    subject_segments, subject_missing, subject_unknown = fill_placeholders(draft.subject, values)
    letter_segments, letter_missing, letter_unknown = fill_placeholders(draft.letter, values)
    subject = segments_to_text(subject_segments)
    text, html_body = compose_email_bodies(
        candidate_name=draft.candidate_name,
        position=draft.position,
        team=draft.team,
        location=draft.location,
        employment_type=draft.employment_type,
        start_date=draft.start_date,
        respond_by=draft.respond_by,
        language=draft.language,
        sender_name=draft.sender_name,
        subject=subject,
        letter_segments=letter_segments,
        offer_url=offer_url,
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
    offer_url: str,
    team: str = "",
    location: str = "",
    employment_type: str = "",
) -> Tuple[str, str]:
    """Build the plain-text and HTML bodies around an already filled letter.

    The HTML shows the animated banner from the ``cid:`` part that ``app.py`` attaches,
    and a button to the candidate's offer page. Compensation is left to that page.
    """
    copy = _COPY.get(language, _COPY["en"])
    details = [
        (copy["team"], team),
        (copy["employment_type"], copy["employment_types"].get(employment_type, "")),
        (copy["location"], location),
        (copy["start_date"], format_offer_date(start_date, language)),
        (copy["respond_by"], format_offer_date(respond_by, language)),
    ]
    details = [(label, value) for label, value in details if value]
    footer = copy["footer"].format(sender=sender_name or ORGANISATION_NAME, organisation=ORGANISATION_NAME)
    preheader = copy["preheader"].format(organisation=ORGANISATION_NAME)

    def reference_for(token: str) -> str:
        """The same short reference the offer page derives from the token (FNV-1a, Crockford base 32)."""

        def fnv1a(text: str) -> int:
            value = 0x811C9DC5
            for char in text:
                value = ((value ^ ord(char)) * 0x01000193) & 0xFFFFFFFF
            return value

        alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
        first = fnv1a(token)
        second = fnv1a(f"{token}\0{first}")
        chars = "".join(alphabet[(first >> (i * 5)) & 31] for i in range(4))
        chars += "".join(alphabet[(second >> (i * 5)) & 31] for i in range(4))
        return f"{chars[:4]}-{chars[4:]}"

    token = offer_url.rstrip("/").rsplit("/", 1)[-1]
    reference = reference_for(token) if is_offer_token(token) else ""

    text_lines = [segments_to_text(letter_segments).strip(), "", copy["text_link"], offer_url, "", "----"]
    text_lines.append(f"{copy['position']}{copy['separator']}{position or '[position]'}")
    text_lines.extend(f"{label}{copy['separator']}{value}" for label, value in details)
    if reference:
        text_lines.append(f"{copy['reference']}{copy['separator']}{reference}")
    text_lines.extend(["", footer])
    text = "\n".join(text_lines) + "\n"

    position_html = html.escape(position) if position else _missing_html(PLACEHOLDER_LABELS["position"])
    prepared_for = copy["prepared_for"].format(name=candidate_name) if candidate_name else ""
    prepared_html = f'<p style="margin:0 0 24px;font-size:14px;color:#5E5B54;">{html.escape(prepared_for)}</p>\n' if prepared_for else ""
    kicker_html = html.escape(copy["heading"])
    if reference:
        kicker_html += (
            f'&nbsp;&nbsp;·&nbsp;&nbsp;{html.escape(copy["reference"])} '
            f'<span style="font-family:{_FONT_MONO};color:#5E5B54;">{reference}</span>'
        )
    detail_rows = "".join(
        "<tr>"
        f'<td style="padding:10px 16px 10px 0;border-top:1px solid #E7E4DD;font-size:13px;color:#87837A;'
        f'white-space:nowrap;vertical-align:top;">{html.escape(label)}</td>'
        f'<td style="padding:10px 0;border-top:1px solid #E7E4DD;font-size:14px;color:#1A1915;'
        f'vertical-align:top;">{html.escape(value)}</td>'
        "</tr>"
        for label, value in details
    )
    details_html = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:0 0 28px;border-bottom:1px solid #E7E4DD;">{detail_rows}</table>'
        if detail_rows
        else ""
    )
    safe_url = html.escape(offer_url, quote=True)
    hero_html = (
        '<tr><td style="padding:0;line-height:0;font-size:0;background-color:#F5F3EF;border-radius:12px 12px 0 0;">'
        f'<img src="cid:{HERO_CID}" width="600" alt="" '
        'style="display:block;width:100%;max-width:600px;height:auto;border:0;border-radius:12px 12px 0 0;"></td></tr>'
        if hero_image_bytes()
        else ""
    )
    html_body = f"""<!DOCTYPE html>
<html lang="{'zh-CN' if language == 'zh' else 'en'}" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{html.escape(subject)}</title>
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
<style>
body {{ margin: 0; padding: 0; }}
@media (max-width: 620px) {{ .cg-pad {{ padding-left: 24px !important; padding-right: 24px !important; }} }}
</style>
</head>
<body style="margin:0;padding:0;background-color:#EFEDE7;">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{html.escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#EFEDE7;">
<tr>
<td align="center" style="padding:28px 12px 36px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;font-family:{_FONT_SANS};">
<tr>
<td style="padding:0 4px 14px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td style="font-size:15px;font-weight:600;color:#1A1915;">{ORGANISATION_NAME}</td>
<td align="right" style="font-size:12px;color:#87837A;">{html.escape(copy['confidential'])}</td>
</tr>
</table>
</td>
</tr>
<tr>
<td style="border:1px solid #E7E4DD;border-radius:12px;background-color:#FFFFFF;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
{hero_html}
<tr>
<td class="cg-pad" style="padding:30px 36px 10px;">
<p style="margin:0 0 10px;font-size:13px;line-height:1.5;color:#87837A;">{kicker_html}</p>
<h1 style="margin:0 0 {"6px" if prepared_for else "24px"};font-family:{_FONT_SERIF};font-size:30px;font-weight:400;line-height:1.2;letter-spacing:-0.2px;color:#1A1915;">{position_html}</h1>
{prepared_html}{details_html}
{_letter_html(letter_segments)}
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:14px 0 18px;">
<tr>
<td align="center" bgcolor="#1A1915" style="border-radius:8px;background-color:#1A1915;">
<a href="{safe_url}" target="_blank" style="display:inline-block;padding:13px 26px;font-family:{_FONT_SANS};font-size:15px;font-weight:600;color:#FFFFFF;text-decoration:none;border-radius:8px;">{html.escape(copy['cta'])}</a>
</td>
</tr>
</table>
<p style="margin:0 0 24px;font-size:12px;line-height:1.6;color:#87837A;">{html.escape(copy['link_hint'])} <a href="{safe_url}" target="_blank" style="color:#5E5B54;word-break:break-all;">{html.escape(offer_url)}</a></p>
</td>
</tr>
</table>
</td>
</tr>
<tr>
<td style="padding:18px 4px 0;font-size:12px;line-height:1.6;color:#87837A;">{html.escape(footer)}</td>
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
    "team",
    "location",
    "employment_type",
    "reports_to",
    "salary_amount",
    "salary_currency",
    "salary_period",
    "extra_compensation",
    "benefits",
    "token",
    "offer_url",
    "viewed_at",
    "view_count",
    "responded_at",
    "response_note",
)
_SELECT_OFFER = f"SELECT {', '.join(_OFFER_COLUMNS)} FROM recruitment_offers"
# Columns added after the table first shipped; older databases get them on startup.
_ADDED_COLUMNS = (
    ("team", "TEXT"),
    ("location", "TEXT"),
    ("employment_type", "TEXT"),
    ("reports_to", "TEXT"),
    ("salary_amount", "TEXT"),
    ("salary_currency", "TEXT"),
    ("salary_period", "TEXT"),
    ("extra_compensation", "TEXT"),
    ("benefits", "TEXT"),
    ("token", "TEXT"),
    ("offer_url", "TEXT"),
    ("viewed_at", "TEXT"),
    ("view_count", "INTEGER NOT NULL DEFAULT 0"),
    ("responded_at", "TEXT"),
    ("response_note", "TEXT"),
)


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
    cursor = await db.execute("PRAGMA table_info(recruitment_offers)")
    existing = {str(row[1]) for row in await cursor.fetchall()}
    for column, definition in _ADDED_COLUMNS:
        if column not in existing:
            await db.execute(f"ALTER TABLE recruitment_offers ADD COLUMN {column} {definition}")
    await db.execute("CREATE INDEX IF NOT EXISTS recruitment_offers_created_at_idx ON recruitment_offers(created_at)")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS recruitment_offers_candidate_idx ON recruitment_offers(candidate_email, created_at)"
    )
    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS recruitment_offers_token_idx ON recruitment_offers(token)")


def _benefits_list(raw: Any) -> List[str]:
    try:
        value = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def _salary_payload(record: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    amount = str(record.get("salary_amount") or "")
    if not amount:
        return None
    currency = str(record.get("salary_currency") or "AUD")
    period = str(record.get("salary_period") or "year")
    return {
        "amount": float(Decimal(amount)),
        "currency": currency,
        "period": period,
        "formatted": format_salary(amount, currency, period, str(record.get("language") or "en")),
    }


def offer_payload(row: Sequence[Any]) -> Dict[str, Any]:
    """What the admin page sees (everything except the internal user id and raw Bcc)."""
    record = dict(zip(_OFFER_COLUMNS, row))
    record["copy_to_sender"] = bool(record.pop("bcc"))
    record.pop("created_by_user_id", None)
    record.pop("token", None)
    record["send_count"] = int(record.get("send_count") or 0)
    record["view_count"] = int(record.get("view_count") or 0)
    record["benefits"] = _benefits_list(record.get("benefits"))
    record["salary"] = _salary_payload(record)
    return record


def public_offer_payload(record: Mapping[str, Any]) -> Dict[str, Any]:
    """What the candidate's offer page shows. No email addresses or internal fields."""
    status = str(record.get("status") or "")
    public_status = status if status in ("accepted", "declined", "withdrawn") else "open"
    payload: Dict[str, Any] = {
        "organisation": ORGANISATION_NAME,
        "status": public_status,
        "language": record.get("language") or "en",
        "candidate_name": record.get("candidate_name") or "",
        "position": record.get("position") or "",
        "sender_name": record.get("sender_name") or "",
        "responded_at": record.get("responded_at"),
    }
    if public_status == "withdrawn":
        return payload
    payload.update(
        {
            "team": record.get("team") or "",
            "location": record.get("location") or "",
            "employment_type": record.get("employment_type") or "",
            "reports_to": record.get("reports_to") or "",
            "salary": _salary_payload(record),
            "extra_compensation": record.get("extra_compensation") or "",
            "benefits": _benefits_list(record.get("benefits")),
            "start_date": record.get("start_date") or "",
            "respond_by": record.get("respond_by") or "",
            "letter": record.get("letter") or "",
            "sent_at": record.get("sent_at"),
        }
    )
    return payload


def draft_preview_record(draft: OfferDraft, rendered: RenderedOffer) -> Dict[str, Any]:
    """The offer page's data for a draft, so admins can preview the page before sending."""
    return public_offer_payload(
        {
            "status": "sent",
            "language": draft.language,
            "candidate_name": draft.candidate_name,
            "position": draft.position,
            "sender_name": draft.sender_name,
            "team": draft.team,
            "location": draft.location,
            "employment_type": draft.employment_type,
            "reports_to": draft.reports_to,
            "salary_amount": draft.salary_amount,
            "salary_currency": draft.salary_currency,
            "salary_period": draft.salary_period,
            "extra_compensation": draft.extra_compensation,
            "benefits": json.dumps(list(draft.benefits), ensure_ascii=False),
            "start_date": draft.start_date,
            "respond_by": draft.respond_by,
            "letter": rendered.letter,
        }
    )


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


async def get_offer_row_by_token(db: aiosqlite.Connection, token: str) -> Optional[Dict[str, Any]]:
    if not is_offer_token(token):
        return None
    cursor = await db.execute(f"{_SELECT_OFFER} WHERE token = ?", (token,))
    row = await cursor.fetchone()
    return dict(zip(_OFFER_COLUMNS, row)) if row else None


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
    token: str,
    offer_url: str,
    reply_to: Optional[str],
    bcc: Optional[str],
    created_by_user_id: str,
    created_by_email: str,
) -> Dict[str, Any]:
    """Record the offer as "sending" before delivery starts."""
    offer_id = str(uuid.uuid4())
    now = _utc_now_iso()
    values = {
        "id": offer_id,
        "candidate_name": draft.candidate_name,
        "candidate_email": draft.candidate_email,
        "position": draft.position,
        "start_date": draft.start_date or None,
        "respond_by": draft.respond_by or None,
        "language": draft.language,
        "subject": rendered.subject,
        "letter": rendered.letter,
        "sender_name": draft.sender_name,
        "reply_to": reply_to,
        "bcc": bcc,
        "status": "sending",
        "delivery": None,
        "last_error": None,
        "send_count": 0,
        "created_by_user_id": created_by_user_id,
        "created_by_email": created_by_email,
        "created_at": now,
        "sent_at": None,
        "updated_at": now,
        "team": draft.team or None,
        "location": draft.location or None,
        "employment_type": draft.employment_type or None,
        "reports_to": draft.reports_to or None,
        "salary_amount": draft.salary_amount or None,
        "salary_currency": draft.salary_currency if draft.salary_amount else None,
        "salary_period": draft.salary_period if draft.salary_amount else None,
        "extra_compensation": draft.extra_compensation or None,
        "benefits": json.dumps(list(draft.benefits), ensure_ascii=False),
        "token": token,
        "offer_url": offer_url,
        "viewed_at": None,
        "view_count": 0,
        "responded_at": None,
        "response_note": None,
    }
    await db.execute(
        f"""
        INSERT INTO recruitment_offers ({', '.join(_OFFER_COLUMNS)})
        VALUES ({', '.join('?' for _ in _OFFER_COLUMNS)})
        """,
        tuple(values[column] for column in _OFFER_COLUMNS),
    )
    await db.commit()
    return await get_offer(db, offer_id)


async def record_delivery(db: aiosqlite.Connection, offer_id: str, *, delivery: str) -> Dict[str, Any]:
    """Mark a finished delivery. A reply the candidate sent meanwhile is kept."""
    now = _utc_now_iso()
    await db.execute(
        """
        UPDATE recruitment_offers
        SET status = CASE WHEN status = 'sending' THEN 'sent' ELSE status END,
            delivery = ?, last_error = NULL, send_count = send_count + 1, sent_at = ?, updated_at = ?
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
        SET status = CASE
                WHEN status != 'sending' THEN status
                WHEN sent_at IS NULL THEN 'failed'
                ELSE 'sent'
            END,
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
    """Set the status by hand. None if the offer is being sent right now.

    Setting it back to 'sent' reopens the offer, so the candidate can reply on the page again.
    """
    reopen = status == "sent"
    cursor = await db.execute(
        """
        UPDATE recruitment_offers
        SET status = ?, updated_at = ?,
            responded_at = CASE WHEN ? THEN NULL ELSE responded_at END,
            response_note = CASE WHEN ? THEN NULL ELSE response_note END
        WHERE id = ? AND status != 'sending'
        """,
        (status, _utc_now_iso(), reopen, reopen, str(offer_id)),
    )
    await db.commit()
    return await get_offer(db, offer_id) if cursor.rowcount > 0 else None


async def record_view(db: aiosqlite.Connection, offer_id: str) -> None:
    await db.execute(
        "UPDATE recruitment_offers SET viewed_at = COALESCE(viewed_at, ?), view_count = view_count + 1 WHERE id = ?",
        (_utc_now_iso(), str(offer_id)),
    )
    await db.commit()


async def record_response(
    db: aiosqlite.Connection,
    offer_id: str,
    *,
    status: str,
    note: str,
) -> Optional[Dict[str, Any]]:
    """Record the candidate's answer from the offer page. None unless the offer is still open."""
    now = _utc_now_iso()
    cursor = await db.execute(
        """
        UPDATE recruitment_offers
        SET status = ?, responded_at = ?, response_note = ?, updated_at = ?
        WHERE id = ? AND status IN ('sent', 'sending') AND sent_at IS NOT NULL
        """,
        (status, now, note or None, now, str(offer_id)),
    )
    await db.commit()
    return await get_offer_row(db, offer_id) if cursor.rowcount > 0 else None


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
