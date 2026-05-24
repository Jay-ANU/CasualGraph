import json

import pytest

import mcp_tools.email_tool as email_tool


def test_dry_run_email_requires_allowlisted_recipient(monkeypatch, tmp_path):
    audit_path = tmp_path / "email_audit.jsonl"
    monkeypatch.setattr(email_tool, "MCP_EMAIL_ALLOWED_RECIPIENTS", "admin@example.com,@example.org")
    monkeypatch.setattr(email_tool, "MCP_EMAIL_ALLOW_ALL", False)
    monkeypatch.setattr(email_tool, "MCP_EMAIL_DRY_RUN", True)
    monkeypatch.setattr(email_tool, "MCP_EMAIL_ENABLED", False)
    monkeypatch.setattr(email_tool, "MCP_EMAIL_AUDIT_PATH", audit_path)

    result = email_tool.send_mcp_email(
        to=["ADMIN@example.com"],
        subject="ESG follow-up",
        body="Please review this evidence gap.",
        reason="User requested an analyst follow-up.",
        evidence_refs=["chunk_1"],
    )

    assert result["mode"] == "dry_run"
    assert result["sent"] is False
    row = json.loads(audit_path.read_text(encoding="utf-8").strip())
    assert row["recipients"] == ["admin@example.com"]
    assert row["evidence_refs"] == ["chunk_1"]


def test_blocks_unallowlisted_recipient(monkeypatch, tmp_path):
    monkeypatch.setattr(email_tool, "MCP_EMAIL_ALLOWED_RECIPIENTS", "admin@example.com")
    monkeypatch.setattr(email_tool, "MCP_EMAIL_ALLOW_ALL", False)
    monkeypatch.setattr(email_tool, "MCP_EMAIL_AUDIT_PATH", tmp_path / "email_audit.jsonl")

    with pytest.raises(email_tool.EmailToolError, match="not allowlisted"):
        email_tool.send_mcp_email(
            to="person@other.com",
            subject="ESG follow-up",
            body="Body",
            reason="Audit reason",
        )


def test_non_dry_run_uses_smtp_factory(monkeypatch, tmp_path):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port):
            self.host = host
            self.port = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def login(self, username, password):
            self.username = username
            self.password = password

        def send_message(self, message):
            sent_messages.append(message)

    monkeypatch.setattr(email_tool, "MCP_EMAIL_ALLOWED_RECIPIENTS", "@example.com")
    monkeypatch.setattr(email_tool, "MCP_EMAIL_ALLOW_ALL", False)
    monkeypatch.setattr(email_tool, "MCP_EMAIL_DRY_RUN", False)
    monkeypatch.setattr(email_tool, "MCP_EMAIL_ENABLED", True)
    monkeypatch.setattr(email_tool, "MCP_EMAIL_AUDIT_PATH", tmp_path / "email_audit.jsonl")
    monkeypatch.setenv("MAIL_ENABLED", "true")
    monkeypatch.setenv("MAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("MAIL_SMTP_PORT", "465")
    monkeypatch.setenv("MAIL_SMTP_USER", "sender@example.com")
    monkeypatch.setenv("MAIL_SMTP_PASSWORD", "secret")
    monkeypatch.setenv("MAIL_FROM", "sender@example.com")

    result = email_tool.send_mcp_email(
        to=["analyst@example.com"],
        subject="Evidence review",
        body="Please review the attached evidence summary.",
        reason="Agent escalation after unsupported answer.",
        dry_run=False,
        smtp_factory=FakeSMTP,
    )

    assert result["mode"] == "smtp"
    assert result["sent"] is True
    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "analyst@example.com"
