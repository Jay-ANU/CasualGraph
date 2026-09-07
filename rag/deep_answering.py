"""Deep research with DeepSeek V4 Pro, preserving the existing text/SSE contract.

No automatic cross-provider fallback: legacy Claude is reachable only when
LLM_PROVIDER=openai was explicitly selected. Reasoning tokens never become
user-visible answer text. A partial stream is never replaced by another answer.
"""
from __future__ import annotations

import logging
from typing import Dict, Iterator, List, Optional

from configs.settings import (
    LLM_PROVIDER, RAG_DEEP_MODEL, RAG_DEEP_MAX_TOKENS,
    RAG_DEEP_TIMEOUT, RAG_DEEP_REASONING_EFFORT, openai_configured,
)
from rag.openai_client import get_openai_client
from rag.grounded_prompts import build_grounded_request

logger = logging.getLogger(__name__)
TRUNCATION_NOTICE = "\n\n_[Response reached its output limit. Ask a follow-up to continue.]_"
INTERRUPTION_NOTICE = "\n\n_[The connection was interrupted. This answer is incomplete; please retry.]_"


def deep_backend_name() -> str:
    return "deepseek_deep" if LLM_PROVIDER == "deepseek" else "claude_deep"


def deep_answering_available() -> bool:
    if LLM_PROVIDER == "deepseek":
        return openai_configured()
    from rag.claude_answering import claude_answering_available
    return claude_answering_available()


def _request(question, sources, history_block, graph_context, priors, regulatory, answer_intent):
    payload = build_grounded_request(
        question=question, sources=sources, history_block=history_block,
        graph_context=graph_context, priors=priors, regulatory=regulatory,
        answer_intent=answer_intent,
    )
    return {
        "model": RAG_DEEP_MODEL,
        "messages": [{"role": "system", "content": payload["system"]}, *payload["messages"]],
        "max_tokens": RAG_DEEP_MAX_TOKENS,
        "extra_body": {"thinking": {"type": "enabled"}},
        "reasoning_effort": RAG_DEEP_REASONING_EFFORT,
        "timeout": RAG_DEEP_TIMEOUT,
    }


def generate_deep_rag_answer(
    question: str, sources: List[Dict], history_block: str = "",
    graph_context: Optional[str] = None, priors: Optional[List[Dict]] = None,
    regulatory: Optional[List[Dict]] = None, answer_intent: str = "evidence",
) -> Optional[str]:
    if LLM_PROVIDER != "deepseek":
        from rag.claude_answering import generate_claude_deep_rag_answer
        return generate_claude_deep_rag_answer(question, sources, history_block, graph_context, priors, regulatory, answer_intent)
    client = get_openai_client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(**_request(
            question, sources, history_block, graph_context, priors, regulatory, answer_intent,
        ))
        if not response.choices:
            return None
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        if text and choice.finish_reason == "length":
            text += TRUNCATION_NOTICE
        return text or None
    except Exception as exc:
        # Never log request headers, secrets or the provider's echoed payload.
        logger.warning("Deep generation failed (%s)", type(exc).__name__)
        return None


def stream_deep_rag_answer(
    question: str, sources: List[Dict], history_block: str = "",
    graph_context: Optional[str] = None, priors: Optional[List[Dict]] = None,
    regulatory: Optional[List[Dict]] = None, answer_intent: str = "evidence",
) -> Iterator[str]:
    if LLM_PROVIDER != "deepseek":
        from rag.claude_answering import stream_claude_deep_rag_answer
        yield from stream_claude_deep_rag_answer(question, sources, history_block, graph_context, priors, regulatory, answer_intent)
        return
    client = get_openai_client()
    if client is None:
        return
    stream = None
    emitted = False
    finish_reason = None
    try:
        stream = client.chat.completions.create(stream=True, **_request(
            question, sources, history_block, graph_context, priors, regulatory, answer_intent,
        ))
        for event in stream:
            if not getattr(event, "choices", None):
                continue
            choice = event.choices[0]
            finish_reason = getattr(choice, "finish_reason", None) or finish_reason
            text = getattr(choice.delta, "content", None)
            if isinstance(text, str) and text:
                emitted = True
                yield text
        if emitted and finish_reason == "length":
            yield TRUNCATION_NOTICE
        elif emitted and finish_reason != "stop":
            yield INTERRUPTION_NOTICE
    except Exception as exc:
        logger.warning("Deep stream failed (%s)", type(exc).__name__)
        if emitted:
            yield INTERRUPTION_NOTICE
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                logger.debug("Unable to close completed model stream")
