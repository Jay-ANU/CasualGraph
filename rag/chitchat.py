"""No-retrieval replies for small talk."""

from __future__ import annotations

from typing import Iterator, List

from configs.settings import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_TIMEOUT, openai_configured
from rag.openai_client import get_openai_client
from rag.openai_compat import chat_token_kwargs
from rag.query_rewriter import _contains_cjk


def generate_chitchat_reply(query: str, history_block: str = "") -> str:
    """Short reply with no retrieval."""
    reply = _reply_with_openai(query=query, history_block=history_block)
    if reply:
        return reply
    return _canned_reply(query)


def _reply_with_openai(query: str, history_block: str) -> str:
    if not openai_configured():
        return ""
    try:
        import openai
    except Exception:
        return ""

    messages = [
        {
            "role": "system",
            "content": (
                "You are an ESG report assistant. The user is making small talk. "
                "Reply briefly and naturally. If they ask what you can do, tell them you answer "
                "questions about uploaded ESG reports and can provide scenario analysis. "
                "Do not invent report content."
            ),
        },
        {"role": "user", "content": f"History:\n{history_block or 'No history.'}\n\nUser:\n{query}"},
    ]
    try:
        if hasattr(openai, "OpenAI"):
            client = get_openai_client()
            if client is None:
                return ""
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.2,
                messages=messages,
                **chat_token_kwargs(OPENAI_MODEL, 80),
            )
            return (response.choices[0].message.content or "").strip()
        openai.api_key = OPENAI_API_KEY
        if OPENAI_BASE_URL:
            openai.api_base = OPENAI_BASE_URL
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            messages=messages,
            request_timeout=OPENAI_TIMEOUT,
            **chat_token_kwargs(OPENAI_MODEL, 80),
        )
        return (response["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:
        print(f"[rag] chitchat fell back: {type(exc).__name__}: {exc}")
        return ""


def stream_chitchat_reply(query: str, history_block: str = "") -> Iterator[str]:
    """Stream a short chitchat reply when OpenAI streaming is available."""
    if not openai_configured():
        yield _canned_reply(query)
        return
    try:
        import openai
    except Exception:
        yield _canned_reply(query)
        return

    messages = [
        {
            "role": "system",
            "content": (
                "You are an ESG report assistant. The user is making small talk. "
                "Reply briefly and naturally. If they ask what you can do, tell them you answer "
                "questions about uploaded ESG reports and can provide scenario analysis. "
                "Do not invent report content."
            ),
        },
        {"role": "user", "content": f"History:\n{history_block or 'No history.'}\n\nUser:\n{query}"},
    ]
    if not hasattr(openai, "OpenAI"):
        reply = _reply_with_openai(query=query, history_block=history_block) or _canned_reply(query)
        if reply:
            yield reply
        return
    try:
        client = get_openai_client()
        if client is None:
            yield _canned_reply(query)
            return
        parts: List[str] = []
        stream = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            messages=messages,
            stream=True,
            **chat_token_kwargs(OPENAI_MODEL, 80),
        )
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(getattr(choices[0], "delta", None), "content", None)
            if delta:
                text = str(delta)
                parts.append(text)
                yield text
        if not parts:
            yield _canned_reply(query)
    except Exception as exc:
        print(f"[rag] chitchat fell back: {type(exc).__name__}: {exc}")
        yield _canned_reply(query)


def _canned_reply(query: str) -> str:
    text = str(query or "").strip().lower()
    cjk = _contains_cjk(query)
    if any(item in text for item in ("thank", "thanks")) or any(item in str(query) for item in ("谢谢", "感谢")):
        return "不客气。" if cjk else "You're welcome."
    if any(item in text for item in ("bye", "goodbye")) or any(item in str(query) for item in ("再见", "拜拜")):
        return "再见，需要分析 ESG 报告时再找我。" if cjk else "Goodbye. Come back when you want to analyze ESG reports."
    if any(item in text for item in ("help", "what can you do", "who are you")) or any(
        item in str(query) for item in ("你是谁", "你能做什么", "帮助")
    ):
        return (
            "我可以回答已上传 ESG 报告的问题，并提供基于证据的情景分析。"
            if cjk
            else "I can answer questions about uploaded ESG reports and provide evidence-based scenario analysis."
        )
    return "你好，可以问我已上传 ESG 报告里的问题。" if cjk else "Hi. Ask me anything about your uploaded ESG reports."
