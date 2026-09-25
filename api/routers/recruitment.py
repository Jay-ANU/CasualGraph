"""Existing recruitment and candidate routes, restored without changing auth."""
from __future__ import annotations
from fastapi import APIRouter
from datetime import datetime, timedelta, timezone
import recruitment_offers
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union
import asyncio
from pydantic import BaseModel, Field
from fastapi import BackgroundTasks, FastAPI, File, Form, Header, UploadFile, HTTPException, Depends, Query, Request
import re
from pathlib import Path
import os
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
import aiosqlite
import smtplib
from services import db as db_service
from services.auth import _MAIL_ENABLED
from services.auth import _MAIL_FROM
from services.auth import _MAIL_FROM_NAME
from services.auth import _is_production_like_env
from services.auth import _mail_missing_config
from services.auth import _normalize_email
from services.auth import _parse_utc_iso
from services.auth import _send_mail_message
from api.deps import require_admin

router = APIRouter()

def _parse_cors_origins(raw: Optional[str]) -> List[str]:
    origins = [item.strip() for item in str(raw or '').split(',') if item.strip()]
    if origins:
        return origins
    return ['http://127.0.0.1:3000', 'http://localhost:3000', 'http://127.0.0.1:3001', 'http://localhost:3001']

_CORS_ALLOW_ORIGINS = _parse_cors_origins(os.getenv('CORS_ALLOW_ORIGINS', ''))

_CORS_ALLOW_ORIGIN_REGEX = os.getenv('CORS_ALLOW_ORIGIN_REGEX', 'https://.*\\.ngrok-free\\.app|https://.*\\.ngrok\\.app').strip() or None

_get_db = db_service.get_db

async def initialize_recruitment():
    async for db in db_service.get_db():
        await recruitment_offers.init_recruitment_db(db)
        await db.commit()

_RECRUITMENT_RESEND_COOLDOWN_SECONDS = 60

_RECRUITMENT_PUBLIC_URL = os.getenv('RECRUITMENT_PUBLIC_URL', '').strip().rstrip('/')

class RecruitmentOfferRequest(BaseModel):
    candidate_name: str = ''
    candidate_email: str = ''
    position: str = ''
    start_date: Optional[str] = ''
    respond_by: Optional[str] = ''
    language: str = 'en'
    subject: str = ''
    letter: str = ''
    reply_to_sender: bool = True
    copy_to_sender: bool = False
    team: str = ''
    location: str = ''
    employment_type: str = ''
    reports_to: str = ''
    salary_amount: Optional[Union[str, float, int]] = ''
    salary_currency: str = 'AUD'
    salary_period: str = 'year'
    extra_compensation: str = ''
    benefits: List[str] = Field(default_factory=list)

class RecruitmentOfferStatusRequest(BaseModel):
    status: str

class OfferResponseRequest(BaseModel):
    decision: str
    note: Optional[str] = ''

def _recruitment_public_base(origin: Optional[str]) -> str:
    """Base URL of the frontend that serves /offer/<token>.

    RECRUITMENT_PUBLIC_URL wins; otherwise the origin of the admin console that sent the
    request, as long as it is an allowed CORS origin, so links match the site in use.
    """
    if _RECRUITMENT_PUBLIC_URL:
        return _RECRUITMENT_PUBLIC_URL
    candidate = origin.strip().rstrip('/') if isinstance(origin, str) else ''
    if candidate and (candidate in _CORS_ALLOW_ORIGINS or (_CORS_ALLOW_ORIGIN_REGEX and re.fullmatch(_CORS_ALLOW_ORIGIN_REGEX, candidate))):
        return candidate
    return _CORS_ALLOW_ORIGINS[0].rstrip('/')

def _recruitment_mail_status() -> Dict[str, Any]:
    if _MAIL_ENABLED:
        missing = _mail_missing_config()
        if missing:
            return {'mode': 'unavailable', 'sender': None, 'detail': f"Email delivery is missing configuration: {', '.join(missing)}."}
        return {'mode': 'smtp', 'sender': f'{_MAIL_FROM_NAME} <{_MAIL_FROM}>', 'detail': ''}
    if _is_production_like_env():
        return {'mode': 'unavailable', 'sender': None, 'detail': 'Email delivery is not configured on this server.'}
    return {'mode': 'log', 'sender': None, 'detail': 'MAIL_ENABLED is false, so offers are written to the server log instead of being emailed.'}

def _recruitment_mail_mode() -> str:
    status = _recruitment_mail_status()
    if status['mode'] == 'unavailable':
        raise HTTPException(status_code=503, detail=status['detail'])
    return status['mode']

def _recruitment_sender_name(current_user: dict) -> str:
    username = str(current_user.get('username') or '').strip()
    return username or _normalize_email(str(current_user.get('email') or '')).split('@')[0]

def _recruitment_draft(request: RecruitmentOfferRequest, current_user: dict, *, strict: bool) -> recruitment_offers.OfferDraft:
    try:
        return recruitment_offers.build_draft(candidate_name=request.candidate_name, candidate_email=request.candidate_email, position=request.position, start_date=request.start_date, respond_by=request.respond_by, language=request.language, subject=request.subject, letter=request.letter, sender_name=_recruitment_sender_name(current_user), strict=strict, team=request.team, location=request.location, employment_type=request.employment_type, reports_to=request.reports_to, salary_amount=request.salary_amount, salary_currency=request.salary_currency, salary_period=request.salary_period, extra_compensation=request.extra_compensation, benefits=request.benefits)
    except recruitment_offers.OfferValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

def _recruitment_reply_addresses(request: RecruitmentOfferRequest, current_user: dict) -> Tuple[Optional[str], Optional[str]]:
    """Reply-To and Bcc addresses, both the signed-in admin's own email when requested."""
    admin_email = _normalize_email(str(current_user.get('email') or ''))
    if not recruitment_offers.is_valid_email(admin_email):
        return (None, None)
    return (admin_email if request.reply_to_sender else None, admin_email if request.copy_to_sender else None)

def _build_recruitment_message(*, subject: str, text: str, html_body: str, candidate_name: str, candidate_email: str, reply_to: Optional[str], bcc: Optional[str]) -> EmailMessage:
    message = EmailMessage()
    try:
        message['Subject'] = subject
        message['From'] = formataddr((_MAIL_FROM_NAME, _MAIL_FROM))
        message['To'] = formataddr((candidate_name, candidate_email))
        if reply_to:
            message['Reply-To'] = reply_to
        if bcc:
            message['Bcc'] = bcc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"The offer can't be sent as an email: {exc}") from exc
    message['Date'] = formatdate(usegmt=True)
    message['Message-ID'] = make_msgid(domain=_MAIL_FROM.rpartition('@')[2] or None)
    message.set_content(text)
    message.add_alternative(html_body, subtype='html')
    hero = recruitment_offers.hero_image_bytes()
    if hero:
        message.get_payload()[1].add_related(hero, maintype='image', subtype='gif', cid=f'<{recruitment_offers.HERO_CID}>', filename='offer-hero.gif', disposition='inline')
    return message

def _describe_mail_error(exc: BaseException) -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return 'The mail server rejected the sender credentials.'
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The mail server refused the candidate's address."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return 'The mail server refused the sender address.'
    if isinstance(exc, smtplib.SMTPResponseException):
        reply = exc.smtp_error.decode(errors='replace') if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error)
        return f'The mail server replied {exc.smtp_code}: {reply[:200]}'
    if isinstance(exc, smtplib.SMTPException):
        return f'Email delivery failed ({type(exc).__name__}).'
    if isinstance(exc, TimeoutError):
        return 'The mail server did not respond in time.'
    return 'Could not connect to the mail server.'

async def _deliver_recruitment_offer(db: aiosqlite.Connection, offer_id: str, message: EmailMessage, *, candidate_email: str, mode: str) -> Dict[str, Any]:
    try:
        if mode == 'log':
            plain = message.get_body(preferencelist=('plain',))
            print(f"[recruitment] MAIL_ENABLED=false; offer {offer_id} was not emailed.\nTo: {message['To']}\nSubject: {message['Subject']}\n\n{(plain.get_content() if plain else '')}")
        else:
            refused = await asyncio.to_thread(_send_mail_message, message) or {}
            if candidate_email.lower() in {str(address).lower() for address in refused}:
                raise smtplib.SMTPRecipientsRefused(refused)
    except (smtplib.SMTPException, OSError) as exc:
        reason = _describe_mail_error(exc)
        print(f'[recruitment] offer {offer_id} delivery failed: {type(exc).__name__}: {exc}')
        await recruitment_offers.record_failure(db, offer_id, error=reason)
        raise HTTPException(status_code=502, detail=f'The offer was not sent. {reason}') from exc
    offer = await recruitment_offers.record_delivery(db, offer_id, delivery=mode)
    return {'offer': offer, 'delivery': mode}

@router.get('/admin/recruitment/offers')
async def list_recruitment_offers(limit: int=Query(default=200, ge=1, le=500), current_user: dict=Depends(require_admin), db: aiosqlite.Connection=Depends(_get_db)):
    await recruitment_offers.expire_stale_sends(db)
    return {'offers': await recruitment_offers.list_offers(db, limit=limit), 'mail': _recruitment_mail_status()}

@router.post('/admin/recruitment/offers/preview')
async def preview_recruitment_offer(request: RecruitmentOfferRequest, current_user: dict=Depends(require_admin), origin: Optional[str]=Header(default=None)):
    draft = _recruitment_draft(request, current_user, strict=False)
    offer_url = f'{_recruitment_public_base(origin)}/offer/preview'
    rendered = recruitment_offers.render_offer(draft, offer_url=offer_url)
    reply_to, bcc = _recruitment_reply_addresses(request, current_user)
    recipient = draft.candidate_email
    if recipient and draft.candidate_name:
        recipient = f'{draft.candidate_name} <{recipient}>'
    return {'subject': rendered.subject, 'html': rendered.html, 'text': rendered.text, 'from': _recruitment_mail_status()['sender'], 'to': recipient, 'reply_to': reply_to, 'bcc': bcc, 'missing': rendered.missing, 'unknown': rendered.unknown, 'warnings': recruitment_offers.date_warnings(draft), 'hero_cid': recruitment_offers.HERO_CID, 'page': recruitment_offers.draft_preview_record(draft, rendered)}

@router.post('/admin/recruitment/offers')
async def send_recruitment_offer(request: RecruitmentOfferRequest, current_user: dict=Depends(require_admin), db: aiosqlite.Connection=Depends(_get_db), origin: Optional[str]=Header(default=None)):
    draft = _recruitment_draft(request, current_user, strict=True)
    token = recruitment_offers.new_offer_token()
    offer_url = f'{_recruitment_public_base(origin)}/offer/{token}'
    rendered = recruitment_offers.render_offer(draft, offer_url=offer_url)
    problems = recruitment_offers.missing_placeholder_messages(rendered)
    if problems:
        raise HTTPException(status_code=400, detail=' '.join(problems))
    mode = _recruitment_mail_mode()
    duplicate = await recruitment_offers.find_recent_duplicate(db, candidate_email=draft.candidate_email, position=draft.position)
    if duplicate:
        raise HTTPException(status_code=409, detail=f'An offer for {draft.position} was sent to {draft.candidate_email} less than a minute ago.')
    reply_to, bcc = _recruitment_reply_addresses(request, current_user)
    message = _build_recruitment_message(subject=rendered.subject, text=rendered.text, html_body=rendered.html, candidate_name=draft.candidate_name, candidate_email=draft.candidate_email, reply_to=reply_to, bcc=bcc)
    offer = await recruitment_offers.insert_offer(db, draft=draft, rendered=rendered, token=token, offer_url=offer_url, reply_to=reply_to, bcc=bcc, created_by_user_id=str(current_user.get('id') or ''), created_by_email=_normalize_email(str(current_user.get('email') or '')))
    return await _deliver_recruitment_offer(db, offer['id'], message, candidate_email=draft.candidate_email, mode=mode)

@router.post('/admin/recruitment/offers/{offer_id}/resend')
async def resend_recruitment_offer(offer_id: str, current_user: dict=Depends(require_admin), db: aiosqlite.Connection=Depends(_get_db)):
    await recruitment_offers.expire_stale_sends(db)
    stored = await recruitment_offers.get_offer_row(db, offer_id)
    if stored is None:
        raise HTTPException(status_code=404, detail='Offer not found')
    if stored['status'] == 'sending':
        raise HTTPException(status_code=409, detail='This offer is being sent right now.')
    if stored['status'] not in recruitment_offers.RESENDABLE_STATUSES:
        raise HTTPException(status_code=409, detail='Only offers that are awaiting a reply or were not delivered can be sent again.')
    if stored['status'] == 'sent' and stored['sent_at']:
        elapsed = (datetime.now(timezone.utc) - _parse_utc_iso(stored['sent_at'])).total_seconds()
        if elapsed < _RECRUITMENT_RESEND_COOLDOWN_SECONDS:
            raise HTTPException(status_code=429, detail='This offer was sent less than a minute ago.')
    mode = _recruitment_mail_mode()
    text, html_body = recruitment_offers.compose_email_bodies(candidate_name=stored['candidate_name'], position=stored['position'], team=stored['team'] or '', location=stored['location'] or '', employment_type=stored['employment_type'] or '', start_date=stored['start_date'] or '', respond_by=stored['respond_by'] or '', language=stored['language'], sender_name=stored['sender_name'], subject=stored['subject'], letter_segments=[('text', stored['letter'])], offer_url=stored['offer_url'] or '')
    message = _build_recruitment_message(subject=stored['subject'], text=text, html_body=html_body, candidate_name=stored['candidate_name'], candidate_email=stored['candidate_email'], reply_to=stored['reply_to'], bcc=stored['bcc'])
    if not await recruitment_offers.claim_for_resend(db, offer_id, cooldown_seconds=_RECRUITMENT_RESEND_COOLDOWN_SECONDS):
        raise HTTPException(status_code=409, detail='This offer is being sent right now or was just sent.')
    return await _deliver_recruitment_offer(db, offer_id, message, candidate_email=stored['candidate_email'], mode=mode)

@router.patch('/admin/recruitment/offers/{offer_id}')
async def update_recruitment_offer_status(offer_id: str, request: RecruitmentOfferStatusRequest, current_user: dict=Depends(require_admin), db: aiosqlite.Connection=Depends(_get_db)):
    status = str(request.status or '').strip().lower()
    if status not in recruitment_offers.MANUAL_STATUSES:
        raise HTTPException(status_code=400, detail='Status must be sent, accepted, declined or withdrawn.')
    await recruitment_offers.expire_stale_sends(db)
    offer = await recruitment_offers.get_offer(db, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail='Offer not found')
    if offer['status'] == 'sending':
        raise HTTPException(status_code=409, detail='This offer is being sent right now.')
    if not offer.get('sent_at') and status != 'withdrawn':
        raise HTTPException(status_code=409, detail='This offer has not reached the candidate yet. Send it again or withdraw it.')
    updated = await recruitment_offers.update_status(db, offer_id, status)
    if updated is None:
        raise HTTPException(status_code=409, detail='This offer is being sent right now.')
    return {'offer': updated}

@router.delete('/admin/recruitment/offers/{offer_id}')
async def delete_recruitment_offer(offer_id: str, current_user: dict=Depends(require_admin), db: aiosqlite.Connection=Depends(_get_db)):
    await recruitment_offers.expire_stale_sends(db)
    offer = await recruitment_offers.get_offer(db, offer_id)
    if offer is None:
        raise HTTPException(status_code=404, detail='Offer not found')
    if offer['status'] == 'sending' or not await recruitment_offers.delete_offer(db, offer_id):
        raise HTTPException(status_code=409, detail='This offer is being sent right now.')
    return {'deleted': True, 'id': offer_id}

def _offer_response_notification(offer: Dict[str, Any]) -> Optional[EmailMessage]:
    recipients: List[str] = []
    for address in (offer.get('created_by_email'), offer.get('reply_to')):
        email = _normalize_email(str(address or ''))
        if recruitment_offers.is_valid_email(email) and email not in recipients:
            recipients.append(email)
    if not recipients:
        return None
    verb = 'accepted' if offer.get('status') == 'accepted' else 'declined'
    lines = [f"{offer['candidate_name']} ({offer['candidate_email']}) {verb} the offer for {offer['position']}.", '']
    if offer.get('response_note'):
        lines += ['Their message:', str(offer['response_note']), '']
    offer_url = str(offer.get('offer_url') or '')
    if '/offer/' in offer_url:
        lines += [f"Recruitment page: {offer_url.split('/offer/')[0]}/admin/recruitment", '']
    lines.append('Sent automatically by CausalGraph AI.')
    message = EmailMessage()
    try:
        message['Subject'] = f"{offer['candidate_name']} {verb} the offer for {offer['position']}"
        message['From'] = formataddr((_MAIL_FROM_NAME, _MAIL_FROM))
        message['To'] = ', '.join(recipients)
    except ValueError:
        return None
    message['Date'] = formatdate(usegmt=True)
    message['Message-ID'] = make_msgid(domain=_MAIL_FROM.rpartition('@')[2] or None)
    message.set_content('\n'.join(lines) + '\n')
    return message

async def _notify_offer_response(offer: Dict[str, Any]) -> None:
    """Best effort: tell the admin who sent the offer that the candidate replied."""
    message = _offer_response_notification(offer)
    if message is None:
        return
    mode = _recruitment_mail_status()['mode']
    try:
        if mode == 'smtp':
            await asyncio.to_thread(_send_mail_message, message)
        elif mode == 'log':
            print(f'[recruitment] MAIL_ENABLED=false; reply notification not emailed:\n{message.get_content()}')
    except (smtplib.SMTPException, OSError) as exc:
        print(f"[recruitment] reply notification for offer {offer.get('id')} failed: {type(exc).__name__}: {exc}")

@router.get('/offers/{token}')
async def view_recruitment_offer(token: str, db: aiosqlite.Connection=Depends(_get_db)):
    offer = await recruitment_offers.get_offer_row_by_token(db, token)
    if offer is None or not offer.get('sent_at'):
        raise HTTPException(status_code=404, detail="This offer link isn't valid.")
    await recruitment_offers.record_view(db, offer['id'])
    return recruitment_offers.public_offer_payload(offer)

@router.post('/offers/{token}/respond')
async def respond_to_recruitment_offer(token: str, request: OfferResponseRequest, background_tasks: BackgroundTasks, db: aiosqlite.Connection=Depends(_get_db)):
    status = recruitment_offers.CANDIDATE_DECISIONS.get(str(request.decision or '').strip().lower())
    if status is None:
        raise HTTPException(status_code=400, detail='Choose to accept or decline the offer.')
    note = recruitment_offers.clean_letter(request.note)
    if len(note) > recruitment_offers.MAX_NOTE_CHARS:
        raise HTTPException(status_code=400, detail=f'Keep the message to {recruitment_offers.MAX_NOTE_CHARS:,} characters or fewer.')
    offer = await recruitment_offers.get_offer_row_by_token(db, token)
    if offer is None or not offer.get('sent_at'):
        raise HTTPException(status_code=404, detail="This offer link isn't valid.")
    updated = await recruitment_offers.record_response(db, offer['id'], status=status, note=note)
    if updated is None:
        current = await recruitment_offers.get_offer_row(db, offer['id']) or offer
        raise HTTPException(status_code=409, detail={'message': 'This offer is no longer open for a reply.', 'offer': recruitment_offers.public_offer_payload(current)})
    background_tasks.add_task(_notify_offer_response, updated)
    return recruitment_offers.public_offer_payload(updated)
