import asyncio
import json

import app


def _decode_sse_payloads(chunks):
    text = "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk) for chunk in chunks)
    payloads = []
    for frame in text.split("\n\n"):
        frame = frame.strip()
        if not frame.startswith("data:"):
            continue
        payloads.append(json.loads(frame[5:].strip()))
    return payloads


def _collect_streaming_response(response):
    async def _collect():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return chunks

    return asyncio.run(_collect())


def test_streaming_response_falls_back_when_stream_breaks_with_broken_pipe():
    response = app._build_streaming_response(
        request=app.RagAskRequest(question="q"),
        stream_factory=lambda: (_ for _ in ()).throw(BrokenPipeError(32, "Broken pipe")),
        fallback_factory=lambda: {"answer": "fallback answer", "sources": [], "backend": "fallback"},
    )

    payloads = _decode_sse_payloads(_collect_streaming_response(response))

    assert payloads == [{"type": "done", "payload": {"answer": "fallback answer", "sources": [], "backend": "fallback"}}]


def test_streaming_response_returns_recovery_done_when_stream_and_fallback_break():
    response = app._build_streaming_response(
        request=app.RagAskRequest(question="q"),
        stream_factory=lambda: (_ for _ in ()).throw(BrokenPipeError(32, "Broken pipe")),
        fallback_factory=lambda: (_ for _ in ()).throw(BrokenPipeError(32, "Broken pipe")),
    )

    payloads = _decode_sse_payloads(_collect_streaming_response(response))

    assert len(payloads) == 1
    assert payloads[0]["type"] == "done"
    assert payloads[0]["payload"]["partial"] is True
    assert payloads[0]["payload"]["partial_reason"] == "stream_interrupted"
    assert "Broken pipe" not in json.dumps(payloads[0])


def test_streaming_response_preserves_context_when_recovering_from_broken_pipe():
    def stream_factory():
        yield {
            "type": "meta",
            "payload": {
                "stream_stage": "context_ready",
                "sources": [{"chunk_id": "chunk_1", "document_title": "Apple ESG"}],
                "agent_path": "agent",
            },
        }
        raise BrokenPipeError(32, "Broken pipe")

    response = app._build_streaming_response(
        request=app.RagAskRequest(question="q"),
        stream_factory=stream_factory,
        fallback_factory=lambda: (_ for _ in ()).throw(BrokenPipeError(32, "Broken pipe")),
    )

    payloads = _decode_sse_payloads(_collect_streaming_response(response))

    assert payloads[-1]["type"] == "done"
    assert payloads[-1]["payload"]["sources"] == [{"chunk_id": "chunk_1", "document_title": "Apple ESG"}]
    assert payloads[-1]["payload"]["agent_path"] == "agent"
