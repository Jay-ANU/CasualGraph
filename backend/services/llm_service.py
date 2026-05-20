"""LLM answer generation with mock fallback."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from config import Config

logger = logging.getLogger(__name__)


def _call_openai(model: str, messages: list, temperature: float, max_tokens: int) -> str:
    """Call OpenAI chat API, compatible with both openai v0.x and v1.x."""
    import openai as _openai

    if hasattr(_openai, "OpenAI"):
        client_kwargs: dict = {"api_key": Config.OPENAI_API_KEY}
        client = _openai.OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    _openai.api_key = Config.OPENAI_API_KEY
    response = _openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (response["choices"][0]["message"]["content"] or "").strip()


class LLMService:
    def __init__(self) -> None:
        self.use_mock = Config.use_mock_mode()

    def answer_question(
        self,
        question: str,
        citations: List[Dict],
        route: str = "rag",
        graph_context: Optional[str] = None,
    ) -> Dict:
        enough_context = len(citations) > 0
        if not enough_context:
            return {
                "answer": "I am not confident enough to answer from the indexed ESG material. Please upload more relevant content or refine the question.",
                "used_mock": True,
                "enough_context": False,
            }

        if self.use_mock:
            return self._mock_answer(question, citations, route, graph_context)

        try:
            context = "\n\n".join(
                f"[{item['chunk_id']}] {item['content']}" for item in citations
            )
            system_prompt = (
                "You answer questions about ESG reports using only the provided evidence. "
                "If the evidence is insufficient, explicitly say you are not certain. "
                "Always cite chunk ids like [chunk_id] in the answer."
            )
            if route == "graph-rag" and graph_context:
                system_prompt += "\nUse both the graph summary and text evidence when answering."

            user_prompt = f"Question: {question}\n\n"
            if graph_context:
                user_prompt += f"Graph summary:\n{graph_context}\n\n"
            user_prompt += f"Evidence:\n{context}\n"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            answer = _call_openai(
                model=Config.OPENAI_MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=min(Config.OPENAI_MAX_TOKENS, 900),
            )
            return {"answer": answer, "used_mock": False, "enough_context": True}
        except Exception as exc:
            logger.warning("OpenAI call failed (%s), falling back to mock for this request.", exc)
            return self._mock_answer(question, citations, route, graph_context)

    @staticmethod
    def _mock_answer(question: str, citations: List[Dict], route: str, graph_context: Optional[str]) -> Dict:
        top = citations[: min(3, len(citations))]
        evidence_lines = [f"[{item['chunk_id']}] {item['content'][:220].strip()}" for item in top]
        parts = [
            f"Working in {route} mock mode, I found the most relevant evidence for: {question}",
            " ".join(evidence_lines),
        ]
        if graph_context:
            parts.append(f"Graph summary: {graph_context}")
        parts.append("This answer is extractive and should be treated as a draft until a full LLM backend is configured.")
        return {"answer": "\n\n".join(parts), "used_mock": True, "enough_context": True}


llm_service = LLMService()
