"""Optional OpenAI-backed grounded answer generation for the root RAG pipeline."""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from configs.settings import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL,
    OPENAI_TIMEOUT,
    OPENAI_TEMPERATURE,
    openai_configured,
)
from rag.openai_client import get_openai_client
from rag.openai_compat import chat_token_kwargs


INSUFFICIENT_CONTEXT_ANSWER = "The provided reports do not contain enough information to answer this question."

_TRUNCATION_NOTICE = (
    "\n\n_[Response truncated at the OPENAI_MAX_TOKENS limit. "
    "Ask a follow-up to continue, or raise OPENAI_MAX_TOKENS in your .env.]_"
)


def _extract_answer(response, *, legacy_sdk: bool = False) -> Optional[str]:
    """Pull text + finish_reason out of a chat completion. Append a notice
    when the model was cut off mid-response so the user (and the log) sees it
    rather than a silent half-sentence."""
    if legacy_sdk:
        choice = response["choices"][0]
        content = (choice.get("message", {}).get("content") or "").strip()
        finish_reason = choice.get("finish_reason")
        usage = response.get("usage") or {}
    else:
        choice = response.choices[0]
        content = (choice.message.content or "").strip()
        finish_reason = getattr(choice, "finish_reason", None)
        usage = getattr(response, "usage", None)
        if usage is not None and not isinstance(usage, dict):
            try:
                usage = usage.model_dump()
            except Exception:
                usage = {"completion_tokens": getattr(usage, "completion_tokens", None)}
    completion_tokens = (usage or {}).get("completion_tokens")
    print(
        f"[answering] finish_reason={finish_reason!r} "
        f"content_chars={len(content)} completion_tokens={completion_tokens} "
        f"max_tokens_cap={OPENAI_MAX_TOKENS}"
    )
    if not content:
        print(f"[answering] EMPTY content returned. finish_reason={finish_reason!r}, raw_choice={choice!r}")
        return None
    if finish_reason == "length":
        print(f"[answering] Output truncated by max_tokens. Last 80 chars: {content[-80:]!r}")
        content = content + _TRUNCATION_NOTICE
    elif finish_reason == "content_filter":
        print(f"[answering] Output stopped by content_filter. Last 80 chars: {content[-80:]!r}")
        content = content + "\n\n_[Response stopped by content filter.]_"
    elif finish_reason not in ("stop", None):
        print(f"[answering] Unexpected finish_reason={finish_reason!r}. Last 80 chars: {content[-80:]!r}")
    return content


def openai_answering_available() -> bool:
    """Return whether OpenAI-backed answering is configured."""
    return openai_configured()


def _build_openai_messages(
    *,
    question: str,
    sources: List[Dict],
    history_block: str,
    graph_context: Optional[str],
    allow_speculation: bool,
) -> List[Dict]:
    context = "\n\n".join(f"[{item['chunk_id']}] {item['text']}" for item in sources) if sources else "No relevant report excerpts were retrieved."
    history_section = f"\nConversation history:\n{history_block}\n" if history_block else ""
    graph_section = f"\nGraph context:\n{graph_context}\n" if graph_context else ""
    if allow_speculation:
        system_prompt = (
            "You are an ESG report question answering assistant. "
            "Use the retrieved report evidence first when it is available. "
            "If the evidence is incomplete or missing, say that clearly and then provide a clearly labeled "
            "'Tentative hypothesis' based on general knowledge and the user's question. "
            "Only cite chunk ids like [chunk_0] for claims supported by retrieved excerpts. "
            "Do not present guesses as if they were grounded in the report."
        )
    else:
        system_prompt = (
            "You are an ESG report question answering assistant. "
            "Answer only from the provided evidence. "
            "If the evidence is insufficient, answer exactly: "
            f"{INSUFFICIENT_CONTEXT_ANSWER} "
            "Cite supporting chunk ids like [chunk_0] when you make factual claims. "
            "Do not invent metrics, dates, or company statements."
        )
    user_prompt = (
        f"{history_section}"
        f"{graph_section}"
        f"\nQuestion:\n{question}\n\n"
        f"Report excerpts:\n{context}\n\n"
        "Answer:"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def generate_openai_rag_answer(
    question: str,
    sources: List[Dict],
    history_block: str = "",
    graph_context: Optional[str] = None,
    allow_speculation: bool = False,
) -> Optional[str]:
    """Generate a grounded answer with OpenAI, or return None on failure."""
    if not openai_answering_available():
        return None

    try:
        import openai
    except Exception:
        return None

    messages = _build_openai_messages(
        question=question,
        sources=sources,
        history_block=history_block,
        graph_context=graph_context,
        allow_speculation=allow_speculation,
    )

    if hasattr(openai, "OpenAI"):
        client = get_openai_client()
        if client is None:
            return None
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=OPENAI_TEMPERATURE,
            messages=messages,
            **chat_token_kwargs(OPENAI_MODEL, OPENAI_MAX_TOKENS),
        )
        return _extract_answer(response)

    openai.api_key = OPENAI_API_KEY
    if OPENAI_BASE_URL:
        openai.api_base = OPENAI_BASE_URL
    response = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        temperature=OPENAI_TEMPERATURE,
        messages=messages,
        request_timeout=OPENAI_TIMEOUT,
        **chat_token_kwargs(OPENAI_MODEL, OPENAI_MAX_TOKENS),
    )
    return _extract_answer(response, legacy_sdk=True)


def stream_openai_rag_answer(
    question: str,
    sources: List[Dict],
    history_block: str = "",
    graph_context: Optional[str] = None,
    allow_speculation: bool = False,
) -> Iterator[str]:
    """Stream a grounded OpenAI answer token-by-token when supported."""
    if not openai_answering_available():
        return

    try:
        import openai
    except Exception:
        return

    messages = _build_openai_messages(
        question=question,
        sources=sources,
        history_block=history_block,
        graph_context=graph_context,
        allow_speculation=allow_speculation,
    )

    if not hasattr(openai, "OpenAI"):
        answer = generate_openai_rag_answer(
            question=question,
            sources=sources,
            history_block=history_block,
            graph_context=graph_context,
            allow_speculation=allow_speculation,
        )
        if answer:
            yield answer
        return

    client = get_openai_client()
    if client is None:
        return

    finish_reason = None
    parts: List[str] = []
    stream = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=OPENAI_TEMPERATURE,
        messages=messages,
        stream=True,
        **chat_token_kwargs(OPENAI_MODEL, OPENAI_MAX_TOKENS),
    )
    for chunk in stream:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        choice = choices[0]
        delta = getattr(getattr(choice, "delta", None), "content", None)
        if delta:
            text = str(delta)
            parts.append(text)
            yield text
        if getattr(choice, "finish_reason", None) is not None:
            finish_reason = choice.finish_reason

    content = "".join(parts).strip()
    print(
        f"[answering.stream] finish_reason={finish_reason!r} "
        f"content_chars={len(content)} completion_tokens=None max_tokens_cap={OPENAI_MAX_TOKENS}"
    )
    if not content:
        print(f"[answering.stream] EMPTY content returned. finish_reason={finish_reason!r}")
        return
    if finish_reason == "length":
        print(f"[answering.stream] Output truncated by max_tokens. Last 80 chars: {content[-80:]!r}")
        yield _TRUNCATION_NOTICE
    elif finish_reason == "content_filter":
        print(f"[answering.stream] Output stopped by content_filter. Last 80 chars: {content[-80:]!r}")
        yield "\n\n_[Response stopped by content filter.]_"
    elif finish_reason not in ("stop", None):
        print(f"[answering.stream] Unexpected finish_reason={finish_reason!r}. Last 80 chars: {content[-80:]!r}")
