from __future__ import annotations

import smtplib
from contextlib import ExitStack
from unittest.mock import patch

import pytest
from fastapi import HTTPException

import app as api


class FakeSMTP:
    instances: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.calls = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.calls.append(("send", message["To"]))
        return {}


def _mail_settings(stack: ExitStack, **overrides) -> None:
    settings = {
        "_MAIL_ENABLED": True,
        "_MAIL_SMTP_HOST": "smtp.example.com",
        "_MAIL_SMTP_PORT": 465,
        "_MAIL_SMTP_SSL": True,
        "_MAIL_SMTP_STARTTLS": False,
        "_MAIL_SMTP_USER": "sender@example.com",
        "_MAIL_SMTP_PASSWORD": "secret",
        "_MAIL_FROM": "sender@example.com",
    }
    settings.update(overrides)
    for name, value in settings.items():
        stack.enter_context(patch(f"app.{name}", value))


def test_verification_code_email_goes_through_the_shared_smtp_sender():
    FakeSMTP.instances = []
    with ExitStack() as stack:
        _mail_settings(stack)
        stack.enter_context(patch("app.smtplib.SMTP_SSL", FakeSMTP))
        api._deliver_email_verification_code(email="New.User@Example.com", code="123456")

    [smtp] = FakeSMTP.instances
    assert (smtp.host, smtp.port) == ("smtp.example.com", 465)
    assert smtp.calls == [("login", "sender@example.com", "secret"), ("send", "new.user@example.com")]


def test_starttls_sender_and_failure_mapping():
    FakeSMTP.instances = []
    with ExitStack() as stack:
        _mail_settings(stack, _MAIL_SMTP_SSL=False, _MAIL_SMTP_STARTTLS=True, _MAIL_SMTP_PORT=587)
        stack.enter_context(patch("app.smtplib.SMTP", FakeSMTP))
        api._deliver_email_verification_code(email="a@example.com", code="654321")
        with patch("app._send_mail_message", side_effect=smtplib.SMTPServerDisconnected("gone")):
            with pytest.raises(HTTPException) as exc:
                api._deliver_email_verification_code(email="a@example.com", code="654321")

    assert FakeSMTP.instances[0].calls[0] == "starttls"
    assert exc.value.status_code == 502


def test_missing_mail_settings_are_reported_before_connecting():
    with ExitStack() as stack:
        _mail_settings(stack, _MAIL_SMTP_PASSWORD="", _MAIL_FROM="")
        with pytest.raises(HTTPException) as exc:
            api._deliver_email_verification_code(email="a@example.com", code="111111")

    assert exc.value.status_code == 503
    assert "MAIL_SMTP_PASSWORD" in exc.value.detail and "MAIL_FROM" in exc.value.detail
