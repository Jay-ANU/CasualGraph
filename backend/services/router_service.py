"""Rule-based query router for RAG vs Graph RAG."""

from __future__ import annotations

import re


class RouterService:
    GRAPH_PATTERN = re.compile(
        r"\b(impact|impacts|affect|affects|why|how|cause|causes|caused|relationship|risk|trend|compare|comparison|driver|drivers)\b",
        re.IGNORECASE,
    )

    def route(self, question: str) -> str:
        return "graph-rag" if self.GRAPH_PATTERN.search(question) else "rag"


router_service = RouterService()
