from __future__ import annotations

import asyncio
import re
import smtplib
from contextlib import ExitStack, contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import patch

import aiosqlite
import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient

import app as api
import recruitment_offers as offers


ADMIN = {"id": "admin-1", "email": "Hiring@Example.com", "username": "Jay", "role": "admin"}
ORIGIN = "http://localhost:3000"  # an allowed CORS origin by default
OFFER_URL = "https://app.example.com/offer/abc"
LETTER = (
    "Dear {{candidate_name}},\n\n"
    "We are pleased to offer you the position of {{position}}.\n"
    "Please reply by {{respond_by}}.\n\n"
    "Kind regards,\n{{sender_name}}"
)


def _offer_request(**overrides) -> api.RecruitmentOfferRequest:
    fields = {
        "candidate_name": "Ada Lovelace",
        "candidate_email": "Ada@Example.org",
        "position": "Research assistant",
        "start_date": "2099-10-05",
        "respond_by": "2099-09-28",
        "language": "en",
        "subject": "Offer: {{position}} at CausalGraph AI",
        "letter": LETTER,
        "reply_to_sender": True,
        "copy_to_sender": False,
    }
    fields.update(overrides)
    return api.RecruitmentOfferRequest(**fields)


class FakeMailer:
    def __init__(self, error: Exception | None = None, refused: dict | None = None):
        self.error = error
        self.refused = refused or {}
        self.messages = []

    def __call__(self, message):
        if self.error is not None:
            raise self.error
        self.messages.append(message)
        return self.refused


@contextmanager
def _backend(tmp_path, *, mailer: FakeMailer | None = None, mail_enabled: bool = True, app_env: str = "development"):
    with ExitStack() as stack:
        stack.enter_context(patch("app._DB_PATH", str(tmp_path / "auth.db")))
        stack.enter_context(patch("app._APP_ENV", app_env))
        stack.enter_context(patch("app._MAIL_ENABLED", mail_enabled))
        stack.enter_context(patch("app._MAIL_SMTP_HOST", "smtp.example.com"))
        stack.enter_context(patch("app._MAIL_SMTP_USER", "offers@example.com"))
        stack.enter_context(patch("app._MAIL_SMTP_PASSWORD", "secret"))
        stack.enter_context(patch("app._MAIL_FROM", "offers@example.com"))
        stack.enter_context(patch("app._MAIL_FROM_NAME", "CausalGraph AI"))
        stack.enter_context(patch("app._send_mail_message", mailer or FakeMailer()))
        yield


def _draft(**overrides) -> offers.OfferDraft:
    fields = {
        "candidate_name": "Ada Lovelace",
        "candidate_email": "ada@example.org",
        "position": "Research assistant",
        "start_date": "2026-10-05",
        "respond_by": "",
        "language": "en",
        "subject": "Offer: {{position}}",
        "letter": LETTER,
        "sender_name": "Jay",
        "strict": True,
    }
    fields.update(overrides)
    return offers.build_draft(**fields)


def test_render_fills_placeholders_and_escapes_html():
    rendered = offers.render_offer(
        offer_url=OFFER_URL, draft=_draft(candidate_name="Ada <script>alert(1)</script>", respond_by="2026-09-28")
    )

    assert rendered.subject == "Offer: Research assistant"
    assert rendered.missing == [] and rendered.unknown == []
    assert "Dear Ada <script>alert(1)</script>," in rendered.letter
    assert "Please reply by Monday 28 September 2026." in rendered.text
    assert "Start date: Monday 5 October 2026" in rendered.text
    assert "<script>" not in rendered.html
    assert "Dear Ada &lt;script&gt;alert(1)&lt;/script&gt;," in rendered.html
    assert "{{" not in rendered.html


def test_chinese_offer_uses_chinese_dates_and_labels():
    rendered = offers.render_offer(
        offer_url=OFFER_URL, draft=_draft(language="zh", letter="{{candidate_name}}，您好：\n\n请于{{respond_by}}前回复。", respond_by="2026-10-01")
    )

    assert "请于2026年10月1日（星期四）前回复。" in rendered.letter
    assert "入职日期：2026年10月5日（星期一）" in rendered.text
    assert 'lang="zh-CN"' in rendered.html
    assert "录用通知" in rendered.html


def test_render_reports_missing_and_unknown_placeholders():
    rendered = offers.render_offer(
        offer_url=OFFER_URL,
        draft=_draft(start_date="", letter="Hi {{candidate_name}}, you start {{ start_date }}. Bonus: {{bonus}}. Pay: {{salary}}."),
    )

    assert rendered.missing == ["start_date", "salary"]
    assert rendered.unknown == ["{{bonus}}"]
    assert "you start [start date]. Bonus: {{bonus}}. Pay: [salary]." in rendered.letter
    assert offers.missing_placeholder_messages(rendered) == [
        "Add the start date or remove {{start_date}} from the email.",
        "Add the salary or remove {{salary}} from the email.",
        "{{bonus}} is not a placeholder this page can fill.",
    ]


def test_strict_draft_validation_and_header_safety():
    with pytest.raises(offers.OfferValidationError, match="valid email"):
        _draft(candidate_email="not-an-email")
    with pytest.raises(offers.OfferValidationError, match="candidate's name"):
        _draft(candidate_name="   ")
    with pytest.raises(offers.OfferValidationError, match="YYYY-MM-DD"):
        _draft(start_date="next Monday")
    with pytest.raises(offers.OfferValidationError, match="Language"):
        _draft(language="fr")
    with pytest.raises(offers.OfferValidationError, match="160 characters"):
        _draft(position="x" * 161)

    draft = _draft(subject="Offer\r\nBcc: attacker@example.com", candidate_name="Ada\nLovelace")
    assert draft.subject == "Offer Bcc: attacker@example.com"
    assert draft.candidate_name == "Ada Lovelace"

    lenient = _draft(candidate_name="", candidate_email="", position="", strict=False)
    assert lenient.candidate_email == ""


def test_date_warnings_are_advisory():
    draft = _draft(start_date="2026-09-01", respond_by="2026-09-10")
    assert offers.date_warnings(draft, today=date(2026, 9, 24)) == [
        "The start date is in the past.",
        "The reply date is in the past.",
        "The reply date is after the start date.",
    ]
    assert offers.date_warnings(_draft(start_date="2026-10-05", respond_by="2026-09-28"), today=date(2026, 9, 24)) == []


def test_send_offer_delivers_multipart_email_and_records_it(tmp_path):
    asyncio.run(_send_offer_delivers_multipart_email_and_records_it(tmp_path))


async def _send_offer_delivers_multipart_email_and_records_it(tmp_path):
    mailer = FakeMailer()
    with _backend(tmp_path, mailer=mailer):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            result = await api.send_recruitment_offer(_offer_request(copy_to_sender=True), ADMIN, db, ORIGIN)
            listed = await api.list_recruitment_offers(200, ADMIN, db)

    offer = result["offer"]
    assert result["delivery"] == "smtp"
    assert offer["status"] == "sent"
    assert offer["candidate_email"] == "ada@example.org"
    assert offer["subject"] == "Offer: Research assistant at CausalGraph AI"
    assert offer["send_count"] == 1
    assert offer["sent_at"]
    assert offer["reply_to"] == "hiring@example.com"
    assert offer["copy_to_sender"] is True
    assert offer["created_by_email"] == "hiring@example.com"
    assert "Please reply by Monday 28 September 2099." in offer["letter"]

    assert len(mailer.messages) == 1
    message = mailer.messages[0]
    assert message["To"] == "Ada Lovelace <ada@example.org>"
    assert message["From"] == "CausalGraph AI <offers@example.com>"
    assert message["Reply-To"] == "hiring@example.com"
    assert message["Bcc"] == "hiring@example.com"
    assert message["Subject"] == "Offer: Research assistant at CausalGraph AI"
    assert message["Message-ID"].endswith("@example.com>")
    assert message.get_body(("plain",)).get_content().startswith("Dear Ada Lovelace,")
    assert "Research assistant</h1>" in message.get_body(("html",)).get_content()

    assert [item["id"] for item in listed["offers"]] == [offer["id"]]
    assert listed["mail"] == {"mode": "smtp", "sender": "CausalGraph AI <offers@example.com>", "detail": ""}


def test_failed_delivery_is_recorded_and_can_be_retried(tmp_path):
    asyncio.run(_failed_delivery_is_recorded_and_can_be_retried(tmp_path))


async def _failed_delivery_is_recorded_and_can_be_retried(tmp_path):
    failing = FakeMailer(error=smtplib.SMTPAuthenticationError(535, b"Login fail"))
    with _backend(tmp_path, mailer=failing):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            with pytest.raises(HTTPException) as exc:
                await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN)
            [failed] = (await api.list_recruitment_offers(200, ADMIN, db))["offers"]

            with pytest.raises(HTTPException) as accept_exc:
                await api.update_recruitment_offer_status(
                    failed["id"], api.RecruitmentOfferStatusRequest(status="accepted"), ADMIN, db
                )

            working = FakeMailer()
            with patch("app._send_mail_message", working):
                retried = await api.resend_recruitment_offer(failed["id"], ADMIN, db)

    assert exc.value.status_code == 502
    assert "rejected the sender credentials" in exc.value.detail
    assert failed["status"] == "failed"
    assert failed["sent_at"] is None
    assert failed["last_error"] == "The mail server rejected the sender credentials."
    assert accept_exc.value.status_code == 409

    assert retried["offer"]["status"] == "sent"
    assert retried["offer"]["last_error"] is None
    assert retried["offer"]["send_count"] == 1
    message = working.messages[0]
    assert message["To"] == "Ada Lovelace <ada@example.org>"
    assert message["Reply-To"] == "hiring@example.com"
    assert message["Bcc"] is None
    assert "Dear Ada Lovelace," in message.get_body(("plain",)).get_content()


def test_refused_candidate_is_a_failure_even_when_the_bcc_copy_is_accepted(tmp_path):
    asyncio.run(_refused_candidate_is_a_failure_even_when_the_bcc_copy_is_accepted(tmp_path))


async def _refused_candidate_is_a_failure_even_when_the_bcc_copy_is_accepted(tmp_path):
    mailer = FakeMailer(refused={"ada@example.org": (550, b"No such user")})
    with _backend(tmp_path, mailer=mailer):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            with pytest.raises(HTTPException) as exc:
                await api.send_recruitment_offer(_offer_request(copy_to_sender=True), ADMIN, db, ORIGIN)
            [offer] = (await api.list_recruitment_offers(200, ADMIN, db))["offers"]

    assert exc.value.status_code == 502
    assert "refused the candidate's address" in exc.value.detail
    assert offer["status"] == "failed"


def test_offer_with_unfilled_placeholders_is_not_sent(tmp_path):
    asyncio.run(_offer_with_unfilled_placeholders_is_not_sent(tmp_path))


async def _offer_with_unfilled_placeholders_is_not_sent(tmp_path):
    mailer = FakeMailer()
    with _backend(tmp_path, mailer=mailer):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            with pytest.raises(HTTPException) as exc:
                await api.send_recruitment_offer(_offer_request(respond_by=""), ADMIN, db, ORIGIN)
            with pytest.raises(HTTPException) as invalid:
                await api.send_recruitment_offer(_offer_request(candidate_email="ada@"), ADMIN, db, ORIGIN)
            listed = await api.list_recruitment_offers(200, ADMIN, db)

    assert exc.value.status_code == 400
    assert "{{respond_by}}" in exc.value.detail
    assert invalid.value.status_code == 400
    assert mailer.messages == []
    assert listed["offers"] == []


def test_double_submit_is_rejected(tmp_path):
    asyncio.run(_double_submit_is_rejected(tmp_path))


async def _double_submit_is_rejected(tmp_path):
    mailer = FakeMailer()
    with _backend(tmp_path, mailer=mailer):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN)
            with pytest.raises(HTTPException) as exc:
                await api.send_recruitment_offer(_offer_request(position="research ASSISTANT"), ADMIN, db, ORIGIN)
            other_role = await api.send_recruitment_offer(_offer_request(position="Data engineer"), ADMIN, db, ORIGIN)

    assert exc.value.status_code == 409
    assert other_role["offer"]["status"] == "sent"
    assert len(mailer.messages) == 2


def test_production_without_mail_refuses_to_send(tmp_path):
    asyncio.run(_production_without_mail_refuses_to_send(tmp_path))


async def _production_without_mail_refuses_to_send(tmp_path):
    mailer = FakeMailer()
    with _backend(tmp_path, mailer=mailer, mail_enabled=False, app_env="production"):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            with pytest.raises(HTTPException) as exc:
                await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN)
            listed = await api.list_recruitment_offers(200, ADMIN, db)

    assert exc.value.status_code == 503
    assert listed["offers"] == []
    assert listed["mail"]["mode"] == "unavailable"
    assert mailer.messages == []


def test_development_without_mail_logs_the_offer(tmp_path, capsys):
    asyncio.run(_development_without_mail_logs_the_offer(tmp_path))
    assert "offer" in capsys.readouterr().out


async def _development_without_mail_logs_the_offer(tmp_path):
    mailer = FakeMailer()
    with _backend(tmp_path, mailer=mailer, mail_enabled=False, app_env="development"):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            result = await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN)
            listed = await api.list_recruitment_offers(200, ADMIN, db)

    assert result["delivery"] == "log"
    assert result["offer"]["status"] == "sent"
    assert listed["mail"]["mode"] == "log"
    assert mailer.messages == []


def test_status_updates_resend_rules_and_delete(tmp_path):
    asyncio.run(_status_updates_resend_rules_and_delete(tmp_path))


async def _status_updates_resend_rules_and_delete(tmp_path):
    with _backend(tmp_path):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            offer = (await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN))["offer"]

            with pytest.raises(HTTPException) as cooldown:
                await api.resend_recruitment_offer(offer["id"], ADMIN, db)
            with pytest.raises(HTTPException) as bad_status:
                await api.update_recruitment_offer_status(
                    offer["id"], api.RecruitmentOfferStatusRequest(status="failed"), ADMIN, db
                )
            accepted = await api.update_recruitment_offer_status(
                offer["id"], api.RecruitmentOfferStatusRequest(status="Accepted"), ADMIN, db
            )
            with pytest.raises(HTTPException) as resend_accepted:
                await api.resend_recruitment_offer(offer["id"], ADMIN, db)

            deleted = await api.delete_recruitment_offer(offer["id"], ADMIN, db)
            with pytest.raises(HTTPException) as missing:
                await api.delete_recruitment_offer(offer["id"], ADMIN, db)

    assert cooldown.value.status_code == 429
    assert bad_status.value.status_code == 400
    assert accepted["offer"]["status"] == "accepted"
    assert resend_accepted.value.status_code == 409
    assert deleted == {"deleted": True, "id": offer["id"]}
    assert missing.value.status_code == 404


def test_preview_shows_the_email_without_sending(tmp_path):
    asyncio.run(_preview_shows_the_email_without_sending(tmp_path))


async def _preview_shows_the_email_without_sending(tmp_path):
    mailer = FakeMailer()
    with _backend(tmp_path, mailer=mailer):
        preview = await api.preview_recruitment_offer(
            _offer_request(candidate_name="", candidate_email="", respond_by="", start_date="2000-01-03"),
            ADMIN,
            ORIGIN,
        )

    assert preview["subject"] == "Offer: Research assistant at CausalGraph AI"
    assert preview["from"] == "CausalGraph AI <offers@example.com>"
    assert preview["to"] == ""
    assert preview["reply_to"] == "hiring@example.com"
    assert preview["bcc"] is None
    assert preview["missing"] == ["candidate_name", "respond_by"]
    assert preview["unknown"] == []
    assert preview["warnings"] == ["The start date is in the past."]
    assert "[candidate name]" in preview["html"]
    assert mailer.messages == []


def test_recruitment_routes_require_admin():
    routes = [route for route in api.app.routes if getattr(route, "path", "").startswith("/admin/recruitment")]
    assert len(routes) == 6
    for route in routes:
        assert api.require_admin in {dependency.call for dependency in route.dependant.dependencies}, route.path


def test_http_admin_can_send_and_regular_user_is_forbidden(tmp_path):
    mailer = FakeMailer()
    with _backend(tmp_path, mailer=mailer):
        asyncio.run(api._init_auth_db())
        asyncio.run(_insert_user(tmp_path, "admin-1", "hiring@example.com", "admin"))
        asyncio.run(_insert_user(tmp_path, "user-1", "someone@example.com", "user"))
        client = TestClient(api.app)
        admin_headers = {"Authorization": f"Bearer {api._make_token('admin-1', 'hiring@example.com')}"}
        user_headers = {"Authorization": f"Bearer {api._make_token('user-1', 'someone@example.com')}"}
        payload = _offer_request().model_dump()

        forbidden = client.post("/admin/recruitment/offers", json=payload, headers=user_headers)
        anonymous = client.get("/admin/recruitment/offers")
        sent = client.post("/admin/recruitment/offers", json=payload, headers=admin_headers)
        listed = client.get("/admin/recruitment/offers", headers=admin_headers)

    assert forbidden.status_code == 403
    assert anonymous.status_code == 401
    assert sent.status_code == 200, sent.text
    assert sent.json()["offer"]["status"] == "sent"
    assert [item["candidate_email"] for item in listed.json()["offers"]] == ["ada@example.org"]
    assert len(mailer.messages) == 1


async def _insert_user(tmp_path, user_id: str, email: str, role: str) -> None:
    async with aiosqlite.connect(tmp_path / "auth.db") as db:
        await db.execute(
            "INSERT INTO users (id, email, username, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, email, email.split("@")[0], "x", role, "2026-01-01T00:00:00+00:00"),
        )
        await db.commit()


def test_encoded_words_in_header_fields_are_rejected_before_anything_is_stored(tmp_path):
    asyncio.run(_encoded_words_in_header_fields_are_rejected_before_anything_is_stored(tmp_path))


async def _encoded_words_in_header_fields_are_rejected_before_anything_is_stored(tmp_path):
    mailer = FakeMailer()
    hostile = {
        "candidate_name": "=?utf-8?b?QWRhDQpY?=",  # decodes to "Ada\r\nX"
        "position": "=?utf-8?b?ZXZpbEBhdHRhY2tlci5jb20sIHg=?=",  # decodes to an extra address
        "subject": "Offer =?utf-8?q?x?=",
    }
    with _backend(tmp_path, mailer=mailer):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            errors = {}
            for field, value in hostile.items():
                with pytest.raises(HTTPException) as exc:
                    await api.send_recruitment_offer(_offer_request(**{field: value}), ADMIN, db, ORIGIN)
                errors[field] = exc.value
            signed = await api.send_recruitment_offer(
                _offer_request(subject="Offer from {{sender_name}}"),
                {**ADMIN, "username": "=?utf-8?b?QWRhDQpY?="},
                db,
                ORIGIN,
            )
            listed = await api.list_recruitment_offers(200, ADMIN, db)

    assert {field: error.status_code for field, error in errors.items()} == {
        "candidate_name": 400,
        "position": 400,
        "subject": 400,
    }
    assert 'can\'t contain "=?"' in errors["candidate_name"].detail
    assert signed["offer"]["subject"] == "Offer from = ?utf-8?b?QWRhDQpY?="
    assert [offer["id"] for offer in listed["offers"]] == [signed["offer"]["id"]]
    assert len(mailer.messages) == 1


def test_unusable_headers_become_a_client_error():
    with patch("app._MAIL_FROM", "offers@example.com"):
        with pytest.raises(HTTPException) as exc:
            api._build_recruitment_message(
                subject="Offer",
                text="Body",
                html_body="<p>Body</p>",
                candidate_name="=?utf-8?b?QWRhDQpY?=",
                candidate_email="ada@example.org",
                reply_to=None,
                bcc=None,
            )

    assert exc.value.status_code == 400


def test_a_failed_send_can_be_sent_again_straight_away(tmp_path):
    asyncio.run(_a_failed_send_can_be_sent_again_straight_away(tmp_path))


async def _a_failed_send_can_be_sent_again_straight_away(tmp_path):
    with _backend(tmp_path, mailer=FakeMailer(error=TimeoutError("timed out"))):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            with pytest.raises(HTTPException) as exc:
                await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN)
            with patch("app._send_mail_message", FakeMailer()):
                again = await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN)
            listed = await api.list_recruitment_offers(200, ADMIN, db)

    assert exc.value.status_code == 502
    assert "did not respond in time" in exc.value.detail
    assert again["offer"]["status"] == "sent"
    assert sorted(offer["status"] for offer in listed["offers"]) == ["failed", "sent"]


def test_an_offer_being_sent_is_locked_until_delivery_finishes_or_expires(tmp_path):
    asyncio.run(_an_offer_being_sent_is_locked_until_delivery_finishes_or_expires(tmp_path))


async def _an_offer_being_sent_is_locked_until_delivery_finishes_or_expires(tmp_path):
    mailer = FakeMailer()
    with _backend(tmp_path, mailer=mailer):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            with patch("app._send_mail_message", FakeMailer(error=TimeoutError())):
                with pytest.raises(HTTPException):
                    await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN)
            [failed] = (await api.list_recruitment_offers(200, ADMIN, db))["offers"]

            # Another request claims the retry first; everything else must wait for it.
            assert await offers.claim_for_resend(db, failed["id"], cooldown_seconds=60) is True
            assert await offers.claim_for_resend(db, failed["id"], cooldown_seconds=60) is False
            [sending] = (await api.list_recruitment_offers(200, ADMIN, db))["offers"]
            blocked = []
            for call in (
                api.resend_recruitment_offer(failed["id"], ADMIN, db),
                api.update_recruitment_offer_status(
                    failed["id"], api.RecruitmentOfferStatusRequest(status="withdrawn"), ADMIN, db
                ),
                api.delete_recruitment_offer(failed["id"], ADMIN, db),
            ):
                with pytest.raises(HTTPException) as exc:
                    await call
                blocked.append(exc.value.status_code)

            # A send cut off by a restart stops blocking the offer after the timeout.
            await db.execute("UPDATE recruitment_offers SET updated_at = '2000-01-01T00:00:00+00:00'")
            await db.commit()
            [expired] = (await api.list_recruitment_offers(200, ADMIN, db))["offers"]
            retried = await api.resend_recruitment_offer(failed["id"], ADMIN, db)

    assert failed["status"] == "failed"
    assert sending["status"] == "sending"
    assert blocked == [409, 409, 409]
    assert expired["status"] == "failed"
    assert expired["last_error"] == offers.INTERRUPTED_ERROR
    assert retried["offer"]["status"] == "sent"
    assert len(mailer.messages) == 1


def test_a_failed_resend_of_a_delivered_offer_keeps_it_awaiting_reply(tmp_path):
    asyncio.run(_a_failed_resend_of_a_delivered_offer_keeps_it_awaiting_reply(tmp_path))


async def _a_failed_resend_of_a_delivered_offer_keeps_it_awaiting_reply(tmp_path):
    with _backend(tmp_path):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            offer = (await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN))["offer"]
            await db.execute("UPDATE recruitment_offers SET sent_at = '2000-01-01T00:00:00+00:00'")
            await db.commit()
            with patch("app._send_mail_message", FakeMailer(error=smtplib.SMTPServerDisconnected("gone"))):
                with pytest.raises(HTTPException) as exc:
                    await api.resend_recruitment_offer(offer["id"], ADMIN, db)
            [after] = (await api.list_recruitment_offers(200, ADMIN, db))["offers"]

    assert exc.value.status_code == 502
    assert after["status"] == "sent"
    assert after["send_count"] == 1
    assert after["last_error"] == "Email delivery failed (SMTPServerDisconnected)."


RICH_OFFER = {
    "team": "Research & Engineering",
    "location": "Canberra, ACT",
    "employment_type": "full_time",
    "reports_to": "Dr Grace Hopper",
    "salary_amount": "95,000",
    "salary_currency": "AUD",
    "salary_period": "year",
    "extra_compensation": "10% annual bonus",
    "benefits": ["Flexible hours", "  ", "Conference budget"],
}


def _token_of(offer: dict) -> str:
    return offer["offer_url"].rsplit("/", 1)[1]


def test_salary_parsing_and_formatting():
    assert offers.parse_salary_amount("95,000") == "95000"
    assert offers.parse_salary_amount(42.5) == "42.5"
    assert offers.parse_salary_amount("") == ""
    for bad in ("abc", "-1", "1e12", "NaN"):
        with pytest.raises(offers.OfferValidationError):
            offers.parse_salary_amount(bad)
    assert offers.format_salary("95000", "AUD", "year", "en") == "AUD 95,000 per year"
    assert offers.format_salary("42.5", "USD", "hour", "en") == "USD 42.50 per hour"
    assert offers.format_salary("25000", "CNY", "month", "zh") == "CNY 25,000 / 月"
    with pytest.raises(offers.OfferValidationError, match="Currency"):
        _draft(salary_amount="1", salary_currency="XYZ")
    with pytest.raises(offers.OfferValidationError, match="Employment type"):
        _draft(employment_type="forever")
    with pytest.raises(offers.OfferValidationError, match="benefits"):
        _draft(benefits=[f"Perk {n}" for n in range(13)])
    with pytest.raises(offers.OfferValidationError, match="Team"):
        _draft(team="=?utf-8?q?x?=")


def test_offer_email_embeds_the_banner_and_links_to_the_offer_page(tmp_path):
    asyncio.run(_offer_email_embeds_the_banner_and_links_to_the_offer_page(tmp_path))


async def _offer_email_embeds_the_banner_and_links_to_the_offer_page(tmp_path):
    mailer = FakeMailer()
    letter = LETTER + "\n\nYour salary: {{salary}} in {{team}}, {{location}}."
    with _backend(tmp_path, mailer=mailer):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            result = await api.send_recruitment_offer(_offer_request(letter=letter, **RICH_OFFER), ADMIN, db, ORIGIN)

    offer = result["offer"]
    assert offer["offer_url"].startswith("http://localhost:3000/offer/")
    assert offers.is_offer_token(_token_of(offer))
    assert "token" not in offer
    assert offer["salary"] == {"amount": 95000.0, "currency": "AUD", "period": "year", "formatted": "AUD 95,000 per year"}
    assert offer["benefits"] == ["Flexible hours", "Conference budget"]
    assert "Your salary: AUD 95,000 per year in Research & Engineering, Canberra, ACT." in offer["letter"]

    message = mailer.messages[0]
    html_part = message.get_body(("html",))
    html = html_part.get_content()
    assert f'src="cid:{offers.HERO_CID}"' in html
    assert f'href="{offer["offer_url"]}"' in html
    assert "Research &amp; Engineering" in html and "Full-time" in html
    assert "Flexible hours" not in html  # benefits live on the offer page
    [image] = [part for part in message.walk() if part.get_content_type() == "image/gif"]
    assert image["Content-ID"] == f"<{offers.HERO_CID}>"
    assert image.get_content() == offers.hero_image_bytes()
    assert offer["offer_url"] in message.get_body(("plain",)).get_content()


def test_offer_page_shows_the_details_without_private_fields_and_counts_views(tmp_path):
    asyncio.run(_offer_page_shows_the_details_without_private_fields_and_counts_views(tmp_path))


async def _offer_page_shows_the_details_without_private_fields_and_counts_views(tmp_path):
    with _backend(tmp_path):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            offer = (await api.send_recruitment_offer(_offer_request(**RICH_OFFER), ADMIN, db, ORIGIN))["offer"]
            page = await api.view_recruitment_offer(_token_of(offer), db)
            await api.view_recruitment_offer(_token_of(offer), db)
            [listed] = (await api.list_recruitment_offers(200, ADMIN, db))["offers"]
            missing = []
            for token in ("x" * 32, "../../etc/passwd", ""):
                with pytest.raises(HTTPException) as exc:
                    await api.view_recruitment_offer(token, db)
                missing.append(exc.value.status_code)

    assert page["status"] == "open"
    assert page["candidate_name"] == "Ada Lovelace"
    assert page["position"] == "Research assistant"
    assert page["team"] == "Research & Engineering"
    assert page["employment_type"] == "full_time"
    assert page["reports_to"] == "Dr Grace Hopper"
    assert page["salary"]["formatted"] == "AUD 95,000 per year"
    assert page["extra_compensation"] == "10% annual bonus"
    assert page["benefits"] == ["Flexible hours", "Conference budget"]
    assert page["respond_by"] == "2099-09-28"
    assert page["letter"].startswith("Dear Ada Lovelace,")
    serialized = str(page)
    assert "ada@example.org" not in serialized and "hiring@example.com" not in serialized
    assert listed["view_count"] == 2 and listed["viewed_at"]
    assert missing == [404, 404, 404]


def test_candidate_accepts_once_and_the_sender_is_told(tmp_path):
    asyncio.run(_candidate_accepts_once_and_the_sender_is_told(tmp_path))


async def _candidate_accepts_once_and_the_sender_is_told(tmp_path):
    mailer = FakeMailer()
    with _backend(tmp_path, mailer=mailer):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            offer = (await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN))["offer"]
            tasks = BackgroundTasks()
            page = await api.respond_to_recruitment_offer(
                _token_of(offer), api.OfferResponseRequest(decision="Accept", note="Thrilled to join!"), tasks, db
            )
            await tasks()
            with pytest.raises(HTTPException) as again:
                await api.respond_to_recruitment_offer(
                    _token_of(offer), api.OfferResponseRequest(decision="decline"), BackgroundTasks(), db
                )
            with pytest.raises(HTTPException) as invalid:
                await api.respond_to_recruitment_offer(
                    _token_of(offer), api.OfferResponseRequest(decision="maybe"), BackgroundTasks(), db
                )
            [listed] = (await api.list_recruitment_offers(200, ADMIN, db))["offers"]
            reopened = await api.update_recruitment_offer_status(
                offer["id"], api.RecruitmentOfferStatusRequest(status="sent"), ADMIN, db
            )

    assert page["status"] == "accepted" and page["responded_at"]
    assert listed["status"] == "accepted"
    assert listed["response_note"] == "Thrilled to join!"
    assert again.value.status_code == 409
    assert again.value.detail["offer"]["status"] == "accepted"
    assert invalid.value.status_code == 400
    assert reopened["offer"]["responded_at"] is None and reopened["offer"]["response_note"] is None

    [offer_email, notification] = mailer.messages
    assert notification["To"] == "hiring@example.com"
    assert notification["Subject"] == "Ada Lovelace accepted the offer for Research assistant"
    body = notification.get_content()
    assert "Thrilled to join!" in body
    assert "http://localhost:3000/admin/recruitment" in body


def test_declines_withdrawn_and_undelivered_offers(tmp_path):
    asyncio.run(_declines_withdrawn_and_undelivered_offers(tmp_path))


async def _declines_withdrawn_and_undelivered_offers(tmp_path):
    with _backend(tmp_path):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            declined = (await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN))["offer"]
            page = await api.respond_to_recruitment_offer(
                _token_of(declined), api.OfferResponseRequest(decision="decline"), BackgroundTasks(), db
            )

            withdrawn = (
                await api.send_recruitment_offer(_offer_request(**RICH_OFFER, position="Data engineer"), ADMIN, db, ORIGIN)
            )["offer"]
            await api.update_recruitment_offer_status(
                withdrawn["id"], api.RecruitmentOfferStatusRequest(status="withdrawn"), ADMIN, db
            )
            withdrawn_page = await api.view_recruitment_offer(_token_of(withdrawn), db)
            with pytest.raises(HTTPException) as closed:
                await api.respond_to_recruitment_offer(
                    _token_of(withdrawn), api.OfferResponseRequest(decision="accept"), BackgroundTasks(), db
                )

            with patch("app._send_mail_message", FakeMailer(error=TimeoutError())):
                with pytest.raises(HTTPException):
                    await api.send_recruitment_offer(_offer_request(position="Designer"), ADMIN, db, ORIGIN)
            undelivered = [
                item for item in (await api.list_recruitment_offers(200, ADMIN, db))["offers"] if item["status"] == "failed"
            ][0]
            with pytest.raises(HTTPException) as not_valid:
                await api.view_recruitment_offer(_token_of(undelivered), db)

    assert page["status"] == "declined"
    assert withdrawn_page == {
        "organisation": "CausalGraph AI",
        "status": "withdrawn",
        "language": "en",
        "candidate_name": "Ada Lovelace",
        "position": "Data engineer",
        "sender_name": "Jay",
        "responded_at": None,
    }
    assert closed.value.status_code == 409
    assert not_valid.value.status_code == 404


def test_a_reply_during_a_resend_is_kept(tmp_path):
    asyncio.run(_a_reply_during_a_resend_is_kept(tmp_path))


async def _a_reply_during_a_resend_is_kept(tmp_path):
    with _backend(tmp_path):
        await api._init_auth_db()
        async with aiosqlite.connect(tmp_path / "auth.db") as db:
            offer = (await api.send_recruitment_offer(_offer_request(), ADMIN, db, ORIGIN))["offer"]
            await db.execute("UPDATE recruitment_offers SET sent_at = '2000-01-01T00:00:00+00:00'")
            await db.commit()
            assert await offers.claim_for_resend(db, offer["id"], cooldown_seconds=60)
            await api.respond_to_recruitment_offer(
                _token_of(offer), api.OfferResponseRequest(decision="accept"), BackgroundTasks(), db
            )
            after_delivery = await offers.record_delivery(db, offer["id"], delivery="smtp")

    assert after_delivery["status"] == "accepted"
    assert after_delivery["send_count"] == 2


def test_offer_links_use_the_configured_or_requesting_site():
    with patch("app._RECRUITMENT_PUBLIC_URL", ""), patch(
        "app._CORS_ALLOW_ORIGINS", ["https://casualgraphai.vercel.app", "https://preview.vercel.app"]
    ), patch("app._CORS_ALLOW_ORIGIN_REGEX", r"https://.*\.ngrok\.app"):
        assert api._recruitment_public_base("https://preview.vercel.app/") == "https://preview.vercel.app"
        assert api._recruitment_public_base("https://demo.ngrok.app") == "https://demo.ngrok.app"
        assert api._recruitment_public_base("https://evil.example") == "https://casualgraphai.vercel.app"
        assert api._recruitment_public_base(None) == "https://casualgraphai.vercel.app"
    with patch("app._RECRUITMENT_PUBLIC_URL", "https://jobs.example.org"):
        assert api._recruitment_public_base("https://preview.vercel.app") == "https://jobs.example.org"


def test_tables_from_the_first_release_gain_the_new_columns(tmp_path):
    asyncio.run(_tables_from_the_first_release_gain_the_new_columns(tmp_path))


async def _tables_from_the_first_release_gain_the_new_columns(tmp_path):
    async with aiosqlite.connect(tmp_path / "auth.db") as db:
        await db.execute(
            "CREATE TABLE recruitment_offers (id TEXT PRIMARY KEY, candidate_name TEXT NOT NULL, "
            "candidate_email TEXT NOT NULL, position TEXT NOT NULL, start_date TEXT, respond_by TEXT, "
            "language TEXT NOT NULL DEFAULT 'en', subject TEXT NOT NULL, letter TEXT NOT NULL, "
            "sender_name TEXT NOT NULL, reply_to TEXT, bcc TEXT, status TEXT NOT NULL, delivery TEXT, "
            "last_error TEXT, send_count INTEGER NOT NULL DEFAULT 0, created_by_user_id TEXT NOT NULL, "
            "created_by_email TEXT NOT NULL, created_at TEXT NOT NULL, sent_at TEXT, updated_at TEXT NOT NULL)"
        )
        await db.execute(
            "INSERT INTO recruitment_offers (id, candidate_name, candidate_email, position, subject, letter, "
            "sender_name, status, created_by_user_id, created_by_email, created_at, updated_at) "
            "VALUES ('old', 'Ada', 'ada@example.org', 'Analyst', 'Offer', 'Hi', 'Jay', 'sent', 'a', 'a@example.com', "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        await db.commit()
        await offers.init_recruitment_db(db)
        [old] = await offers.list_offers(db)

    assert old["view_count"] == 0 and old["benefits"] == [] and old["salary"] is None and old["offer_url"] is None


def test_http_offer_page_round_trip(tmp_path):
    mailer = FakeMailer()
    with _backend(tmp_path, mailer=mailer):
        asyncio.run(api._init_auth_db())
        asyncio.run(_insert_user(tmp_path, "admin-1", "hiring@example.com", "admin"))
        client = TestClient(api.app)
        admin_headers = {
            "Authorization": f"Bearer {api._make_token('admin-1', 'hiring@example.com')}",
            "Origin": "http://localhost:3000",
        }
        sent = client.post("/admin/recruitment/offers", json=_offer_request(**RICH_OFFER).model_dump(), headers=admin_headers)
        token = sent.json()["offer"]["offer_url"].rsplit("/", 1)[1]
        page = client.get(f"/offers/{token}")
        answer = client.post(f"/offers/{token}/respond", json={"decision": "accept", "note": "Yes!"})
        repeat = client.post(f"/offers/{token}/respond", json={"decision": "decline"})
        hero = client.get("/recruitment-assets/offer-hero.gif")
        preview = client.post(
            "/admin/recruitment/offers/preview", json=_offer_request(**RICH_OFFER).model_dump(), headers=admin_headers
        )

    assert sent.status_code == 200, sent.text
    assert page.status_code == 200 and page.json()["salary"]["formatted"] == "AUD 95,000 per year"
    assert answer.status_code == 200 and answer.json()["status"] == "accepted"
    assert repeat.status_code == 409 and repeat.json()["detail"]["offer"]["status"] == "accepted"
    assert len(mailer.messages) == 2  # the offer, then the reply notification
    assert hero.status_code == 200 and hero.headers["content-type"] == "image/gif"
    assert preview.json()["page"]["benefits"] == ["Flexible hours", "Conference budget"]
    assert "http://localhost:3000/offer/preview" in preview.json()["html"]


def test_frontend_lists_match_the_backend():
    """The admin form and offer page offer exactly the currencies and placeholders the backend accepts."""
    root = Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages"
    content = (root / "offer" / "offerContent.ts").read_text(encoding="utf-8")
    currencies = re.search(r"export const CURRENCIES = \[(.*?)\];", content, re.S).group(1)
    assert tuple(re.findall(r"'([A-Z]{3})'", currencies)) == offers.CURRENCIES
    templates = (root / "recruitment" / "offerTemplates.ts").read_text(encoding="utf-8")
    placeholders = re.search(r"export const OFFER_PLACEHOLDERS[^=]*= \[(.*?)\];", templates, re.S).group(1)
    assert re.findall(r"key: '([a-z_]+)'", placeholders) == list(offers.PLACEHOLDER_LABELS)
