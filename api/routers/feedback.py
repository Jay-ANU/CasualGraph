"""/feedback and /admin/feedback/recent: answer ratings."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.deps import get_current_user, require_admin
from services import db as db_service

router = APIRouter()


_FEEDBACK_REASON_TAGS = {"missing_evidence", "wrong_citation", "hallucination", "irrelevant", "other"}


class FeedbackRequest(BaseModel):
    session_id: str
    message_id: str
    query: str
    answer: str
    rating: Literal["up", "down"]
    reason_tags: List[str] = Field(default_factory=list)
    reason_text: Optional[str] = ""
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    timings_ms: Optional[Dict[str, Any]] = None


@router.post("/feedback")
async def submit_answer_feedback(
    request: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    session_id = str(request.session_id or "").strip()
    message_id = str(request.message_id or "").strip()
    query = str(request.query or "").strip()
    answer = str(request.answer or "").strip()
    reason_text = str(request.reason_text or "").strip()
    reason_tags = [
        str(tag).strip().lower()
        for tag in (request.reason_tags or [])
        if str(tag).strip().lower() in _FEEDBACK_REASON_TAGS
    ]
    reason_tags = list(dict.fromkeys(reason_tags))

    if not session_id or not message_id or not query or not answer:
        raise HTTPException(status_code=422, detail="session_id, message_id, query, and answer are required")
    if request.rating == "down" and not reason_tags and not reason_text:
        raise HTTPException(status_code=422, detail="Downvote feedback requires at least one reason tag or free-text reason")

    try:
        async with aiosqlite.connect(db_service._FEEDBACK_DB_PATH) as db:
            cursor = await db.execute(
                """
                INSERT INTO answer_feedback (
                    user_id, session_id, message_id, query, answer, rating,
                    reason_tags, reason_text, sources_json, timings_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(current_user["id"]),
                    session_id,
                    message_id,
                    query,
                    answer,
                    request.rating,
                    json.dumps(reason_tags, ensure_ascii=False),
                    reason_text,
                    json.dumps(request.sources or [], ensure_ascii=False),
                    json.dumps(request.timings_ms or {}, ensure_ascii=False),
                ),
            )
            await db.commit()
            return JSONResponse(content={"ok": True, "id": cursor.lastrowid})
    except aiosqlite.IntegrityError:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": "feedback_duplicate", "message": "Feedback already submitted for this answer."},
        )


@router.get("/admin/feedback/recent")
async def admin_recent_answer_feedback(
    rating: Optional[Literal["up", "down"]] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_admin),
):
    _ = current_user
    clauses: List[str] = []
    params: List[Any] = []
    if rating:
        clauses.append("rating = ?")
        params.append(rating)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    async with aiosqlite.connect(db_service._FEEDBACK_DB_PATH) as db:
        cursor = await db.execute(
            f"""
            SELECT id, user_id, session_id, message_id, query, answer, rating,
                   reason_tags, reason_text, sources_json, timings_json, created_at
            FROM answer_feedback
            {where_sql}
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            tuple(params),
        )
        rows = await cursor.fetchall()

    feedback = []
    for row in rows:
        try:
            reason_tags = json.loads(row[7] or "[]")
        except json.JSONDecodeError:
            reason_tags = []
        try:
            sources = json.loads(row[9] or "[]")
        except json.JSONDecodeError:
            sources = []
        try:
            timings_ms = json.loads(row[10] or "{}")
        except json.JSONDecodeError:
            timings_ms = {}
        feedback.append({
            "id": row[0],
            "user_id": row[1],
            "session_id": row[2],
            "message_id": row[3],
            "query": row[4],
            "answer": row[5],
            "rating": row[6],
            "reason_tags": reason_tags,
            "reason_text": row[8],
            "sources": sources,
            "timings_ms": timings_ms,
            "created_at": row[11],
        })

    return JSONResponse(content={"feedback": feedback})
