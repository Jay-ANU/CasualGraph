"""/rag/ask and /rag/ask/stream, including the SSE streaming plumbing."""

from __future__ import annotations

import json
import queue
import threading
from typing import Any, Dict, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from api.deps import get_db, get_optional_current_user
from rag.answer_intent import classify_answer_intent
from rag.query_rewriter import format_history
from rag.rag_pipeline import answer_question, stream_answer_question
from services.memory import _history_with_long_term_memory, _load_long_term_memory_context, _remember_exchange_later
from services.rag_context import (
    RagAskRequest,
    _load_request_history_for_rag,
    _resolve_general_rag_request_context,
    _resolve_rag_request_context,
)
from services.rate_limit import _enforce_rag_rate_limit

router = APIRouter()


@router.post("/rag/ask")
async def rag_ask(
    request: RagAskRequest,
    current_user: Optional[dict] = Depends(get_optional_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        if not current_user:
            await _enforce_rag_rate_limit(db, current_user, request.reasoning_mode)
        pre_history, pre_memory_backend = _load_request_history_for_rag(request, current_user)
        answer_intent = classify_answer_intent(
            query=request.question,
            history_block=format_history(pre_history, current_query=request.question),
        )
        if str(answer_intent.get("mode") or "") in {"general", "chitchat"}:
            context = _resolve_general_rag_request_context(request, current_user, pre_history, pre_memory_backend)
        else:
            context = _resolve_rag_request_context(request, current_user)
        if context["error_response"] is not None:
            return context["error_response"]
        quota = await _enforce_rag_rate_limit(db, current_user, request.reasoning_mode) if current_user else None
        memory_context, injected_memories = await _load_long_term_memory_context(db, current_user, request.question)
        answer_history = _history_with_long_term_memory(context["history"], memory_context)
        result = answer_question(
            request.question,
            top_k=request.top_k,
            history=answer_history,
            retrieval_filters=context["filters"],
            mode=request.mode or "ask",
            reasoning_mode=request.reasoning_mode or "flash",
            user_id=context["user_id"],
            answer_intent=answer_intent,
        )
        result["memory_backend"] = context["memory_backend"]
        result["long_term_memory"] = {
            "backend": "sqlite+vector",
            "injected": len(injected_memories),
            "auto_extract": bool(current_user),
        }
        if quota and not quota.get("bypassed"):
            result["quota"] = quota
        if request.session_id:
            result["session_id"] = request.session_id
        if current_user:
            _remember_exchange_later(
                user_id=str(current_user.get("id") or ""),
                user_message=request.question,
                assistant_message=str(result.get("answer") or ""),
                source="rag",
            )
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        return JSONResponse(
            status_code=400,
            content={"answer": "", "sources": [], "error": "vector_store_missing", "message": str(exc)},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"answer": "", "sources": [], "error": "rag_failed", "message": str(exc)},
        )


def _encode_sse_event(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _is_recoverable_stream_error(exc: Exception) -> bool:
    if isinstance(exc, (BrokenPipeError, ConnectionResetError, TimeoutError)):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in {32, 54, 104}:
        return True
    message = str(exc).lower()
    return "broken pipe" in message or "connection reset" in message or "stream disconnected" in message


def _remember_stream_context(context: Dict[str, Any], event: Dict[str, Any]) -> None:
    if event.get("type") not in {"meta", "done"}:
        return
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return
    for key in ("sources", "graph_sources", "agent_path", "path", "agent_trace"):
        if key in payload and payload[key] not in (None, ""):
            context[key] = payload[key]


def _stream_interrupted_done_payload(request: RagAskRequest, context: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "answer": (
            "The answer stream was interrupted before a final response was available. "
            "Please retry the question."
        ),
        "sources": context.get("sources") if isinstance(context.get("sources"), list) else [],
        "backend": "stream_recovery",
        "partial": True,
        "partial_reason": "stream_interrupted",
    }
    for key in ("graph_sources", "agent_path", "path", "agent_trace"):
        if key in context:
            payload[key] = context[key]
    if request.session_id:
        payload["session_id"] = request.session_id
    return payload


def _build_streaming_response(
    *,
    request: RagAskRequest,
    stream_factory,
    fallback_factory,
) -> StreamingResponse:
    event_queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()

    def _producer() -> None:
        stream_context: Dict[str, Any] = {}
        try:
            try:
                iterator = stream_factory()
                for event in iterator:
                    if isinstance(event, dict):
                        _remember_stream_context(stream_context, event)
                    event_queue.put(event)
            except NotImplementedError:
                event_queue.put({"type": "done", "payload": fallback_factory()})
            except Exception as exc:
                if not _is_recoverable_stream_error(exc):
                    raise
                print(f"[rag.stream] recoverable stream failure, using fallback: {type(exc).__name__}: {exc}")
                try:
                    event_queue.put({"type": "done", "payload": fallback_factory()})
                except Exception as fallback_exc:
                    if not _is_recoverable_stream_error(fallback_exc):
                        raise
                    print(
                        "[rag.stream] fallback also hit recoverable stream failure; "
                        f"returning partial recovery payload: {type(fallback_exc).__name__}: {fallback_exc}"
                    )
                    event_queue.put({"type": "done", "payload": _stream_interrupted_done_payload(request, stream_context)})
        except Exception as exc:
            event_queue.put({"type": "error", "message": str(exc)})
        finally:
            event_queue.put(None)

    def _event_stream():
        thread = threading.Thread(target=_producer, daemon=True)
        thread.start()
        while True:
            try:
                item = event_queue.get(timeout=15.0)
            except queue.Empty:
                yield ": heartbeat\n\n"
                continue
            if item is None:
                break
            yield _encode_sse_event(item)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/rag/ask/stream")
async def rag_ask_stream(
    request: RagAskRequest,
    current_user: Optional[dict] = Depends(get_optional_current_user),
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        if not current_user:
            await _enforce_rag_rate_limit(db, current_user, request.reasoning_mode)
        pre_history, pre_memory_backend = _load_request_history_for_rag(request, current_user)
        answer_intent = classify_answer_intent(
            query=request.question,
            history_block=format_history(pre_history, current_query=request.question),
        )
        if str(answer_intent.get("mode") or "") in {"general", "chitchat"}:
            context = _resolve_general_rag_request_context(request, current_user, pre_history, pre_memory_backend)
        else:
            context = _resolve_rag_request_context(request, current_user)
        if context["error_response"] is not None:
            return context["error_response"]
        quota = await _enforce_rag_rate_limit(db, current_user, request.reasoning_mode) if current_user else None
        memory_context, injected_memories = await _load_long_term_memory_context(db, current_user, request.question)
        answer_history = _history_with_long_term_memory(context["history"], memory_context)

        def _stream_factory():
            for event in stream_answer_question(
                request.question,
                top_k=request.top_k,
                history=answer_history,
                retrieval_filters=context["filters"],
                mode=request.mode or "ask",
                reasoning_mode=request.reasoning_mode or "flash",
                user_id=context["user_id"],
                answer_intent=answer_intent,
            ):
                if event.get("type") == "done":
                    payload = dict(event.get("payload") or {})
                    payload["memory_backend"] = context["memory_backend"]
                    payload["long_term_memory"] = {
                        "backend": "sqlite+vector",
                        "injected": len(injected_memories),
                        "auto_extract": bool(current_user),
                    }
                    if quota and not quota.get("bypassed"):
                        payload["quota"] = quota
                    if request.session_id:
                        payload["session_id"] = request.session_id
                    if current_user:
                        _remember_exchange_later(
                            user_id=str(current_user.get("id") or ""),
                            user_message=request.question,
                            assistant_message=str(payload.get("answer") or ""),
                            source="rag_stream",
                        )
                    yield {"type": "done", "payload": payload}
                else:
                    if event.get("type") == "meta":
                        payload = dict(event.get("payload") or {})
                        if request.session_id:
                            payload["session_id"] = request.session_id
                        yield {"type": "meta", "payload": payload}
                    else:
                        yield event

        def _fallback_factory():
            result = answer_question(
                request.question,
                top_k=request.top_k,
                history=answer_history,
                retrieval_filters=context["filters"],
                mode=request.mode or "ask",
                reasoning_mode=request.reasoning_mode or "flash",
                user_id=context["user_id"],
                answer_intent=answer_intent,
            )
            result["memory_backend"] = context["memory_backend"]
            result["long_term_memory"] = {
                "backend": "sqlite+vector",
                "injected": len(injected_memories),
                "auto_extract": bool(current_user),
            }
            if quota and not quota.get("bypassed"):
                result["quota"] = quota
            if request.session_id:
                result["session_id"] = request.session_id
            if current_user:
                _remember_exchange_later(
                    user_id=str(current_user.get("id") or ""),
                    user_message=request.question,
                    assistant_message=str(result.get("answer") or ""),
                    source="rag_stream_fallback",
                )
            return result

        return _build_streaming_response(
            request=request,
            stream_factory=_stream_factory,
            fallback_factory=_fallback_factory,
        )
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        return JSONResponse(
            status_code=400,
            content={"answer": "", "sources": [], "error": "vector_store_missing", "message": str(exc)},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"answer": "", "sources": [], "error": "rag_failed", "message": str(exc)},
        )
