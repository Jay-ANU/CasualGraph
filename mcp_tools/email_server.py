"""MCP server exposing a controlled email sending tool."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp_tools.email_tool import send_mcp_email


def create_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:
        raise RuntimeError("Install the optional 'mcp' package to run this server") from exc

    server = FastMCP("causalgraph-email")

    @server.tool()
    def send_email(
        to: List[str],
        subject: str,
        body: str,
        reason: str,
        evidence_refs: Optional[List[str]] = None,
        dry_run: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Send or dry-run an allowlisted email with audit logging."""

        return send_mcp_email(
            to=to,
            subject=subject,
            body=body,
            reason=reason,
            evidence_refs=evidence_refs or [],
            dry_run=dry_run,
            metadata={"tool": "mcp.send_email"},
        )

    return server


if __name__ == "__main__":
    create_server().run()
