from __future__ import annotations

import unittest
import sys
from pathlib import Path
import asyncio
import json

from starlette.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as api


def _request_with_query(query: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/kg-view",
            "query_string": query.encode("utf-8"),
            "headers": [],
            "client": ("198.51.100.10", 443),
            "server": ("casualgraph.fly.dev", 443),
            "scheme": "https",
        }
    )


class KgViewTicketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user = {
            "id": "user-123",
            "email": "admin@example.com",
            "username": "Graph Admin",
            "role": "admin",
        }

    def test_ticket_carries_authenticated_user_into_backend_kg_view(self) -> None:
        payload = api.KgViewTicketRequest(document_id="doc-abc")
        response = asyncio.run(api.create_kg_view_ticket(payload, _request_with_query(""), self.user))

        self.assertEqual(response.status_code, 200)
        ticket = json.loads(response.body)["ticket"]

        effective_user = api._kg_view_effective_user(_request_with_query(f"ticket={ticket}"), None)
        self.assertIsNotNone(effective_user)
        self.assertEqual(effective_user["id"], self.user["id"])
        self.assertEqual(effective_user["role"], "admin")
        self.assertEqual(api._kg_view_raw_document_id(_request_with_query(f"ticket={ticket}")), "doc-abc")


if __name__ == "__main__":
    unittest.main()
