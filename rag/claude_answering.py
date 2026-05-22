"""Deep-tier grounded answer generation via the Anthropic Claude API.

This is the Deep counterpart to ``rag.openai_answering``. The Flash tier (and
all of the legacy "ask" path) still routes through OpenAI; Deep routes here.

Design points:

* **Free-form markdown**, not JSON. Claude is encouraged — but never forced —
  to organise analytical answers under "Evidence / Reasoning / Conclusion"
  markdown headings. The prompt is tuned for Claude's XML-tag preference for
  structured context blocks (``<sources>``, ``<priors>``, ``<graph>`` etc.).

* **Same wire format as Flash.** The streaming generator yields plain text
  chunks (``Iterator[str]``); the FastAPI route in ``app.py`` wraps each chunk
  in an SSE ``event: token`` frame. The frontend's ``readSseEvents`` therefore
  sees an identical wire shape regardless of which provider produced the
  tokens.

* **Graceful fallback.** Both the sync and the streaming entrypoints return
  ``None`` / an empty iterator when Anthropic is unconfigured or errors out.
  The caller (``rag.rag_pipeline``) is responsible for falling back to Flash
  and emitting the appropriate ``fallback_to_flash`` meta event to the FE.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from configs.settings import (
    RAG_DEEP_MAX_TOKENS,
    RAG_DEEP_MODEL,
    RAG_DEEP_TEMPERATURE,
    anthropic_configured,
)
from rag.anthropic_client import get_anthropic_client


# Shared with OpenAI side so callers can detect the same "evidence missing" string.
INSUFFICIENT_CONTEXT_ANSWER = (
    "The provided reports do not contain enough information to answer this question."
)

_TRUNCATION_NOTICE = (
    "\n\n_[Response truncated at the RAG_DEEP_MAX_TOKENS limit. "
    "Ask a follow-up to continue, or raise RAG_DEEP_MAX_TOKENS in your .env.]_"
)


_SYSTEM_PROMPT = (
    "You are an ESG research analyst working from a structured corpus of "
    "company sustainability reports.\n\n"
    "When the question is analytical, comparative, or predictive, organise "
    "your answer with markdown headings such as 'Evidence', 'Reasoning', and "
    "'Conclusion'. When the question is purely factual, give a direct answer "
    "without forcing the structure.\n\n"
    "Always cite sources inline using the markers you see in the context:\n"
    "- `[chunk_N]` for retrieved report passages\n"
    "- `[prior_N]` for historical comparisons\n"
    "- `[reg_N]` for regulatory references\n"
    "- `[G_N]` for graph entities or edges\n\n"
    "Be explicit about uncertainty. Never invent figures, dates, or company "
    "statements. If the evidence is insufficient, answer plainly: "
    f"{INSUFFICIENT_CONTEXT_ANSWER}"
)


def claude_answering_available() -> bool:
    """Return whether the Deep tier is configured + the SDK is importable."""
    if not anthropic_configured():
        return False
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    return True


def _format_source_block(label: str, sources: List[Dict]) -> str:
    """Wrap a list of retrieved chunks in a Claude-friendly XML-like tag.

    Claude responds better to ``<sources>...</sources>`` than to bare prose.
    Each source carries its own ``[chunk_N]`` / ``[prior_N]`` / ``[reg_N]``
    label so the model can cite inline.
    """
    if not sources:
        return ""
    lines = []
    for item in sources:
        chunk_id = item.get("chunk_id") or item.get("id") or ""
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{chunk_id}] {text}" if chunk_id else text)
    if not lines:
        return ""
    body = "\n\n".join(lines)
    return f"<{label}>\n{body}\n</{label}>"


def _build_claude_request(
    *,
    question: str,
    sources: List[Dict],
    priors: Optional[List[Dict]],
    regulatory: Optional[List[Dict]],
    graph_context: Optional[str],
    history_block: str,
    answer_intent: str = "evidence",
) -> Dict[str, object]:
    """Build the (system, user) payload Claude expects."""
    sections: List[str] = []
    if history_block:
        sections.append(f"<history>\n{history_block.strip()}\n</history>")
    sources_block = _format_source_block("sources", sources)
    if sources_block:
        sections.append(sources_block)
    priors_block = _format_source_block("priors", priors or [])
    if priors_block:
        sections.append(priors_block)
    reg_block = _format_source_block("regulatory", regulatory or [])
    if reg_block:
        sections.append(reg_block)
    if graph_context:
        sections.append(f"<graph>\n{graph_context.strip()}\n</graph>")
    sections.append(f"<question>\n{question.strip()}\n</question>")
    if answer_intent == "general":
        sections.append(
            "<instruction>This is a general guidance question. Answer directly without requiring report evidence, and do not cite uploaded-report markers.</instruction>"
        )
    elif answer_intent == "hybrid":
        sections.append(
            "<instruction>Use report evidence first when available. If evidence is incomplete or missing, clearly separate a General analysis section and do not present it as report-backed.</instruction>"
        )
    elif not sources_block and not priors_block and not reg_block:
        # Tell the model upfront so it follows the INSUFFICIENT_CONTEXT contract.
        sections.append(
            "<note>No relevant report excerpts were retrieved for this question.</note>"
        )
    user_content = "\n\n".join(sections)
    return {
        "system": _system_prompt_for_intent(answer_intent),
        "messages": [{"role": "user", "content": user_content}],
    }


def _system_prompt_for_intent(answer_intent: str) -> str:
    if answer_intent == "general":
        return (
            "You are a practical ESG, business, and academic research assistant. "
            "The user is asking for general guidance, not a report-grounded answer. "
            "Answer directly in concise markdown. Do not claim that your answer comes from uploaded reports, "
            "do not invent company-specific facts, and do not include report citations."
        )
    if answer_intent == "hybrid":
        return (
            _SYSTEM_PROMPT
            + "\n\nFor hybrid questions, use retrieved report evidence first and cite it. "
            "If report evidence is incomplete or missing, clearly separate a 'General analysis' section. "
            "Do not present general reasoning as report-backed."
        )
    return _SYSTEM_PROMPT


# The newer Opus 4.x models reject `temperature` as a deprecated parameter
# (API returns 400 invalid_request_error). Earlier Sonnet / Haiku tiers still
# accept it. We detect by model-name prefix and only pass temperature for
# models that still allow it.
_NO_TEMPERATURE_MODEL_PREFIXES = ("claude-opus-4",)


def _messages_kwargs(payload: Dict[str, object]) -> Dict[str, object]:
    kwargs: Dict[str, object] = {
        "model": RAG_DEEP_MODEL,
        "max_tokens": RAG_DEEP_MAX_TOKENS,
        "system": payload["system"],
        "messages": payload["messages"],
    }
    if not any(RAG_DEEP_MODEL.startswith(prefix) for prefix in _NO_TEMPERATURE_MODEL_PREFIXES):
        kwargs["temperature"] = RAG_DEEP_TEMPERATURE
    return kwargs


# ----------------------------------------------------------------------------
# Sync entry point — returns the full markdown string.
# ----------------------------------------------------------------------------

def generate_claude_deep_rag_answer(
    question: str,
    sources: List[Dict],
    history_block: str = "",
    graph_context: Optional[str] = None,
    priors: Optional[List[Dict]] = None,
    regulatory: Optional[List[Dict]] = None,
    answer_intent: str = "evidence",
) -> Optional[str]:
    """Non-streaming Deep answer. Returns markdown, or None to trigger fallback."""
    if not claude_answering_available():
        return None
    client = get_anthropic_client()
    if client is None:
        return None

    payload = _build_claude_request(
        question=question,
        sources=sources,
        priors=priors,
        regulatory=regulatory,
        graph_context=graph_context,
        history_block=history_block,
        answer_intent=answer_intent,
    )

    try:
        response = client.messages.create(
            **_messages_kwargs(payload),
        )
    except Exception as exc:
        print(f"[claude_answering] API call failed: {exc!r}")
        return None

    # response.content is a list of content blocks (mostly TextBlock with .text).
    parts: List[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    content = "".join(parts).strip()
    stop_reason = getattr(response, "stop_reason", None)
    print(
        f"[claude_answering] stop_reason={stop_reason!r} content_chars={len(content)} "
        f"max_tokens_cap={RAG_DEEP_MAX_TOKENS} model={RAG_DEEP_MODEL}"
    )
    if not content:
        return None
    if stop_reason == "max_tokens":
        content = content + _TRUNCATION_NOTICE
    return content


# ----------------------------------------------------------------------------
# Streaming entry point — yields text chunks so the FastAPI SSE layer can
# forward them as `event: token` frames, identical to the OpenAI streamer.
# ----------------------------------------------------------------------------

def stream_claude_deep_rag_answer(
    question: str,
    sources: List[Dict],
    history_block: str = "",
    graph_context: Optional[str] = None,
    priors: Optional[List[Dict]] = None,
    regulatory: Optional[List[Dict]] = None,
    answer_intent: str = "evidence",
) -> Iterator[str]:
    """Stream a Deep markdown answer token-by-token. Yields nothing on failure."""
    if not claude_answering_available():
        return
    client = get_anthropic_client()
    if client is None:
        return

    payload = _build_claude_request(
        question=question,
        sources=sources,
        priors=priors,
        regulatory=regulatory,
        graph_context=graph_context,
        history_block=history_block,
        answer_intent=answer_intent,
    )

    parts: List[str] = []
    stop_reason: Optional[str] = None
    try:
        with client.messages.stream(**_messages_kwargs(payload)) as stream:
            for text in stream.text_stream:
                if not text:
                    continue
                parts.append(text)
                yield text
            final_message = stream.get_final_message()
            stop_reason = getattr(final_message, "stop_reason", None)
    except Exception as exc:
        # Don't yield a partial answer + error chunk — the pipeline detects the
        # empty/short generator and falls back cleanly.
        print(f"[claude_answering.stream] failed: {exc!r}")
        return

    content = "".join(parts).strip()
    print(
        f"[claude_answering.stream] stop_reason={stop_reason!r} "
        f"content_chars={len(content)} max_tokens_cap={RAG_DEEP_MAX_TOKENS} "
        f"model={RAG_DEEP_MODEL}"
    )
    if stop_reason == "max_tokens":
        yield _TRUNCATION_NOTICE
