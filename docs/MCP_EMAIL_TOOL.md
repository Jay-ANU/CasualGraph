# MCP Email Tool

The MCP email server exposes one controlled tool, `send_email`, backed by the
same SMTP settings used by the app.

## Safety Model

- Actual sending requires `MCP_EMAIL_ENABLED=true`.
- Actual sending also requires `MAIL_ENABLED=true` and complete `MAIL_SMTP_*`
  settings.
- Recipients must match `MCP_EMAIL_ALLOWED_RECIPIENTS` unless
  `MCP_EMAIL_ALLOW_ALL=true`.
- Every request writes a JSONL audit row to `MCP_EMAIL_AUDIT_PATH`.
- Keep `MCP_EMAIL_DRY_RUN=true` while testing.

Allowlist entries can be exact emails or domains:

```env
MCP_EMAIL_ALLOWED_RECIPIENTS=admin@example.com,@example.org
```

## Run

Install dependencies, then start the MCP server:

```bash
python3 -m mcp_tools.email_server
```

Tool schema:

```json
{
  "to": ["admin@example.com"],
  "subject": "Evidence review",
  "body": "Please review the evidence gap.",
  "reason": "Agent escalation after unsupported answer.",
  "evidence_refs": ["chunk_1"],
  "dry_run": true
}
```
