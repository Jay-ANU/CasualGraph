"""Persistent structured long-term memory for user preferences and goals."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from rag.openai_client import get_openai_client
from rag.openai_compat import chat_token_kwargs
from user_memory_vector_store import (
    delete_memory_vector,
    memory_vector_backend,
    query_memory_vectors,
    upsert_memory_vector,
)


MEMORY_CATEGORIES = {
    "profile",
    "work_style",
    "answer_style",
    "learning_profile",
    "domain_interest",
    "emotional_style",
    "relationship_pref",
    "project_memory",
    "do_not_remember",
}
SENSITIVE_CATEGORIES = {"emotional_style", "relationship_pref"}
DEFAULT_MEMORY_LIMIT = 80
DEFAULT_RELEVANT_LIMIT = 8
MAX_MEMORY_CONTENT_CHARS = 420
MAX_MEMORY_EVIDENCE_CHARS = 300


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _trim(value: str, limit: int) -> str:
    normalized = _normalize_space(value)
    return normalized[:limit].rstrip()


def _normalize_category(value: str) -> str:
    category = str(value or "").strip().lower()
    return category if category in MEMORY_CATEGORIES else "profile"


def _normalize_origin(value: str) -> str:
    origin = str(value or "").strip().lower()
    return origin if origin in {"explicit", "inferred"} else "inferred"


def _normalize_sensitivity(value: str, category: str) -> str:
    sensitivity = str(value or "").strip().lower()
    if sensitivity in {"normal", "sensitive"}:
        return sensitivity
    return "sensitive" if category in SENSITIVE_CATEGORIES else "normal"


def _normalize_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.6
    return max(0.0, min(1.0, confidence))


def _tokenize(value: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(r"[\w\u4e00-\u9fff]+", str(value or ""))
        if len(token.strip()) >= 2
    }


def _safe_upsert_memory_vector(memory: Dict[str, Any]) -> bool:
    try:
        return upsert_memory_vector(memory)
    except Exception as exc:
        print(f"[memory] vector upsert skipped: {type(exc).__name__}: {exc}")
        return False


def _safe_delete_memory_vector(user_id: str, memory_id: str) -> bool:
    try:
        return delete_memory_vector(user_id, memory_id)
    except Exception as exc:
        print(f"[memory] vector delete skipped: {type(exc).__name__}: {exc}")
        return False


def _safe_query_memory_vectors(user_id: str, query: str, *, limit: int) -> List[Dict[str, Any]]:
    try:
        return query_memory_vectors(user_id, query, limit=limit)
    except Exception as exc:
        print(f"[memory] vector retrieval skipped: {type(exc).__name__}: {exc}")
        return []


async def init_user_memory_db(db) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_memory_settings (
            user_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            auto_extract INTEGER NOT NULL DEFAULT 1,
            raw_retention_days INTEGER NOT NULL DEFAULT 14,
            updated_at TEXT NOT NULL
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_memories (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            evidence TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'chat',
            origin TEXT NOT NULL DEFAULT 'inferred',
            confidence REAL NOT NULL DEFAULT 0.6,
            sensitivity TEXT NOT NULL DEFAULT 'normal',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_used_at TEXT,
            use_count INTEGER NOT NULL DEFAULT 0,
            deleted_at TEXT
        )
        """
    )
    await db.execute("CREATE INDEX IF NOT EXISTS idx_user_memories_user_category ON user_memories(user_id, category)")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_user_memories_user_deleted ON user_memories(user_id, deleted_at)")
    await db.commit()


async def get_memory_settings(db, user_id: str) -> Dict[str, Any]:
    normalized_user_id = str(user_id or "").strip()
    cursor = await db.execute(
        """
        SELECT user_id, enabled, auto_extract, raw_retention_days, updated_at
        FROM user_memory_settings
        WHERE user_id = ?
        """,
        (normalized_user_id,),
    )
    row = await cursor.fetchone()
    if row:
        return {
            "user_id": row[0],
            "enabled": bool(row[1]),
            "auto_extract": bool(row[2]),
            "raw_retention_days": int(row[3]),
            "updated_at": row[4],
        }
    now = _now_iso()
    await db.execute(
        """
        INSERT INTO user_memory_settings (user_id, enabled, auto_extract, raw_retention_days, updated_at)
        VALUES (?, 1, 1, 14, ?)
        """,
        (normalized_user_id, now),
    )
    await db.commit()
    return {
        "user_id": normalized_user_id,
        "enabled": True,
        "auto_extract": True,
        "raw_retention_days": 14,
        "updated_at": now,
    }


async def update_memory_settings(
    db,
    user_id: str,
    *,
    enabled: Optional[bool] = None,
    auto_extract: Optional[bool] = None,
    raw_retention_days: Optional[int] = None,
) -> Dict[str, Any]:
    current = await get_memory_settings(db, user_id)
    next_enabled = current["enabled"] if enabled is None else bool(enabled)
    next_auto_extract = current["auto_extract"] if auto_extract is None else bool(auto_extract)
    next_retention = current["raw_retention_days"]
    if raw_retention_days is not None:
        next_retention = max(1, min(365, int(raw_retention_days)))
    now = _now_iso()
    await db.execute(
        """
        INSERT INTO user_memory_settings (user_id, enabled, auto_extract, raw_retention_days, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            enabled = excluded.enabled,
            auto_extract = excluded.auto_extract,
            raw_retention_days = excluded.raw_retention_days,
            updated_at = excluded.updated_at
        """,
        (str(user_id), int(next_enabled), int(next_auto_extract), next_retention, now),
    )
    await db.commit()
    return await get_memory_settings(db, user_id)


def _row_to_memory(row: Iterable[Any]) -> Dict[str, Any]:
    values = list(row)
    return {
        "id": values[0],
        "user_id": values[1],
        "category": values[2],
        "content": values[3],
        "evidence": values[4],
        "source": values[5],
        "origin": values[6],
        "confidence": float(values[7]),
        "sensitivity": values[8],
        "created_at": values[9],
        "updated_at": values[10],
        "last_used_at": values[11],
        "use_count": int(values[12] or 0),
        "deleted_at": values[13],
    }


async def list_user_memories(
    db,
    user_id: str,
    *,
    category: Optional[str] = None,
    include_deleted: bool = False,
    limit: int = DEFAULT_MEMORY_LIMIT,
) -> List[Dict[str, Any]]:
    params: List[Any] = [str(user_id)]
    clauses = ["user_id = ?"]
    if category:
        clauses.append("category = ?")
        params.append(_normalize_category(category))
    if not include_deleted:
        clauses.append("deleted_at IS NULL")
    params.append(max(1, min(300, int(limit or DEFAULT_MEMORY_LIMIT))))
    cursor = await db.execute(
        f"""
        SELECT id, user_id, category, content, evidence, source, origin, confidence,
               sensitivity, created_at, updated_at, last_used_at, use_count, deleted_at
        FROM user_memories
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        tuple(params),
    )
    rows = await cursor.fetchall()
    return [_row_to_memory(row) for row in rows]


async def _list_user_memories_by_ids(db, user_id: str, memory_ids: List[str]) -> List[Dict[str, Any]]:
    ids = [str(item).strip() for item in memory_ids if str(item or "").strip()]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    cursor = await db.execute(
        f"""
        SELECT id, user_id, category, content, evidence, source, origin, confidence,
               sensitivity, created_at, updated_at, last_used_at, use_count, deleted_at
        FROM user_memories
        WHERE user_id = ? AND deleted_at IS NULL AND id IN ({placeholders})
        """,
        (str(user_id), *ids),
    )
    rows = await cursor.fetchall()
    memories = [_row_to_memory(row) for row in rows]
    by_id = {memory["id"]: memory for memory in memories}
    return [by_id[item] for item in ids if item in by_id]


async def update_user_memory(
    db,
    user_id: str,
    memory_id: str,
    *,
    category: Optional[str] = None,
    content: Optional[str] = None,
    sensitivity: Optional[str] = None,
    confidence: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT id, user_id, category, content, evidence, source, origin, confidence,
               sensitivity, created_at, updated_at, last_used_at, use_count, deleted_at
        FROM user_memories
        WHERE id = ? AND user_id = ? AND deleted_at IS NULL
        """,
        (str(memory_id), str(user_id)),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    existing = _row_to_memory(row)
    next_category = _normalize_category(category or existing["category"])
    next_content = _trim(content if content is not None else existing["content"], MAX_MEMORY_CONTENT_CHARS)
    next_sensitivity = _normalize_sensitivity(sensitivity or existing["sensitivity"], next_category)
    next_confidence = _normalize_confidence(confidence if confidence is not None else existing["confidence"])
    now = _now_iso()
    await db.execute(
        """
        UPDATE user_memories
        SET category = ?, content = ?, sensitivity = ?, confidence = ?, updated_at = ?
        WHERE id = ? AND user_id = ?
        """,
        (next_category, next_content, next_sensitivity, next_confidence, now, str(memory_id), str(user_id)),
    )
    await db.commit()
    memories = await list_user_memories(db, user_id, include_deleted=False, limit=300)
    memory = next((item for item in memories if item["id"] == str(memory_id)), None)
    if memory:
        _safe_upsert_memory_vector(memory)
    return memory


async def delete_user_memory(db, user_id: str, memory_id: str) -> bool:
    cursor = await db.execute(
        """
        UPDATE user_memories
        SET deleted_at = ?, updated_at = ?
        WHERE id = ? AND user_id = ? AND deleted_at IS NULL
        """,
        (_now_iso(), _now_iso(), str(memory_id), str(user_id)),
    )
    await db.commit()
    deleted = int(cursor.rowcount or 0) > 0
    if deleted:
        _safe_delete_memory_vector(str(user_id), str(memory_id))
    return deleted


def _normalize_candidate(candidate: Dict[str, Any], *, source: str) -> Optional[Dict[str, Any]]:
    category = _normalize_category(str(candidate.get("category") or "profile"))
    content = _trim(str(candidate.get("content") or ""), MAX_MEMORY_CONTENT_CHARS)
    if len(content) < 4:
        return None
    sensitivity = _normalize_sensitivity(str(candidate.get("sensitivity") or ""), category)
    evidence = _trim(str(candidate.get("evidence") or ""), MAX_MEMORY_EVIDENCE_CHARS)
    return {
        "category": category,
        "content": content,
        "evidence": evidence,
        "source": _trim(str(candidate.get("source") or source), 60) or source,
        "origin": _normalize_origin(str(candidate.get("origin") or "")),
        "confidence": _normalize_confidence(candidate.get("confidence")),
        "sensitivity": sensitivity,
    }


def _heuristic_memory_candidates(user_message: str, *, source: str) -> List[Dict[str, Any]]:
    text = _normalize_space(user_message)
    if not text:
        return []

    candidates: List[Dict[str, Any]] = []
    explicit_patterns = [
        (r"(?:remember|please remember|记住|请记住)[:：]?\s*(.+)", "profile"),
        (r"(?:i prefer|i like|我喜欢|我偏好|我希望)[:：]?\s*(.+)", "answer_style"),
        (r"(?:my ideal type is|我的理想型是|理想型是)[:：]?\s*(.+)", "relationship_pref"),
        (r"(?:以后|from now on).{0,8}(?:都|please)?\s*(.+)", "work_style"),
    ]
    for pattern, category in explicit_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            content = _trim(match.group(1), MAX_MEMORY_CONTENT_CHARS)
            if content:
                candidates.append(
                    {
                        "category": category,
                        "content": content,
                        "evidence": text,
                        "source": source,
                        "origin": "explicit",
                        "confidence": 0.86,
                        "sensitivity": "sensitive" if category in SENSITIVE_CATEGORIES else "normal",
                    }
                )

    if any(phrase in text.lower() for phrase in ("don't remember", "do not remember", "forget this")) or any(
        phrase in text for phrase in ("不要记住", "别记住", "忘掉")
    ):
        candidates.append(
            {
                "category": "do_not_remember",
                "content": text,
                "evidence": text,
                "source": source,
                "origin": "explicit",
                "confidence": 0.95,
                "sensitivity": "sensitive",
            }
        )
    return candidates


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_with_openai(user_message: str, assistant_message: str, *, source: str) -> List[Dict[str, Any]]:
    client = get_openai_client()
    if client is None:
        return []
    model = os.getenv("USER_MEMORY_EXTRACT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip() or "gpt-4o-mini"
    prompt = {
        "user_message": _trim(user_message, 1800),
        "assistant_message": _trim(assistant_message, 1800),
        "allowed_categories": sorted(MEMORY_CATEGORIES),
        "rules": [
            "Extract only durable facts, preferences, goals, learning needs, emotional style preferences, or relationship/ideal-type preferences that could help future replies.",
            "Do not store raw chat logs or transient task details.",
            "Use relationship_pref or emotional_style for personal/affective preferences and mark them sensitive.",
            "If the user asks not to remember something, add one do_not_remember memory.",
            "Return JSON only.",
        ],
    }
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a privacy-aware long-term memory extractor. "
                        "Return a JSON object with a memories array. Each item must have category, content, "
                        "evidence, origin, confidence, and sensitivity."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            **chat_token_kwargs(model, 700),
        )
    except Exception as exc:
        print(f"[memory] extraction skipped: {type(exc).__name__}: {exc}")
        return []
    content = (response.choices[0].message.content or "").strip()
    parsed = _extract_json_object(content)
    rows = parsed.get("memories") if isinstance(parsed, dict) else []
    if not isinstance(rows, list):
        return []
    candidates: List[Dict[str, Any]] = []
    for row in rows[:8]:
        if isinstance(row, dict):
            normalized = _normalize_candidate(row, source=source)
            if normalized:
                candidates.append(normalized)
    return candidates


async def upsert_user_memory(db, user_id: str, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    normalized = _normalize_candidate(candidate, source=str(candidate.get("source") or "chat"))
    if not normalized:
        return None
    now = _now_iso()
    cursor = await db.execute(
        """
        SELECT id, confidence, use_count
        FROM user_memories
        WHERE user_id = ? AND category = ? AND lower(content) = lower(?) AND deleted_at IS NULL
        LIMIT 1
        """,
        (str(user_id), normalized["category"], normalized["content"]),
    )
    row = await cursor.fetchone()
    if row:
        memory_id = str(row[0])
        confidence = max(float(row[1] or 0), normalized["confidence"])
        await db.execute(
            """
            UPDATE user_memories
            SET evidence = ?, source = ?, origin = ?, confidence = ?, sensitivity = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                normalized["evidence"],
                normalized["source"],
                normalized["origin"],
                confidence,
                normalized["sensitivity"],
                now,
                memory_id,
                str(user_id),
            ),
        )
    else:
        memory_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO user_memories (
                id, user_id, category, content, evidence, source, origin, confidence,
                sensitivity, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                str(user_id),
                normalized["category"],
                normalized["content"],
                normalized["evidence"],
                normalized["source"],
                normalized["origin"],
                normalized["confidence"],
                normalized["sensitivity"],
                now,
                now,
            ),
        )
    await db.commit()
    memories = await list_user_memories(db, user_id, include_deleted=False, limit=300)
    memory = next((item for item in memories if item["id"] == memory_id), None)
    if memory:
        _safe_upsert_memory_vector(memory)
    return memory


async def remember_exchange(
    db,
    *,
    user_id: str,
    user_message: str,
    assistant_message: str,
    source: str = "chat",
) -> Dict[str, Any]:
    settings = await get_memory_settings(db, user_id)
    if not settings["enabled"] or not settings["auto_extract"]:
        return {"enabled": settings["enabled"], "stored": 0, "memories": []}

    candidates = _heuristic_memory_candidates(user_message, source=source)
    candidates.extend(_extract_with_openai(user_message, assistant_message, source=source))
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for candidate in candidates:
        normalized = _normalize_candidate(candidate, source=source)
        if not normalized:
            continue
        key = (normalized["category"], normalized["content"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)

    stored: List[Dict[str, Any]] = []
    for candidate in deduped[:8]:
        memory = await upsert_user_memory(db, user_id, candidate)
        if memory:
            stored.append(memory)
    return {"enabled": True, "stored": len(stored), "memories": stored}


def _memory_score(memory: Dict[str, Any], query_terms: set[str]) -> float:
    content = str(memory.get("content") or "")
    evidence = str(memory.get("evidence") or "")
    category = str(memory.get("category") or "")
    terms = _tokenize(f"{category} {content} {evidence}")
    overlap = len(query_terms & terms)
    confidence = _normalize_confidence(memory.get("confidence"))
    evergreen_categories = {"answer_style", "work_style", "emotional_style", "learning_profile"}
    evergreen = 0.5 if category in evergreen_categories else 0.0
    if overlap <= 0 and category not in evergreen_categories:
        return 0.0
    return overlap * 2.0 + confidence + evergreen


async def _mark_memories_used(db, user_id: str, memories: List[Dict[str, Any]]) -> None:
    if not memories:
        return
    now = _now_iso()
    ids = [item["id"] for item in memories if item.get("id")]
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    await db.execute(
        f"""
        UPDATE user_memories
        SET last_used_at = ?, use_count = use_count + 1
        WHERE user_id = ? AND id IN ({placeholders})
        """,
        (now, str(user_id), *ids),
    )
    await db.commit()


async def get_relevant_user_memories(
    db,
    user_id: str,
    query: str,
    *,
    limit: int = DEFAULT_RELEVANT_LIMIT,
) -> List[Dict[str, Any]]:
    settings = await get_memory_settings(db, user_id)
    if not settings["enabled"]:
        return []
    vector_limit = max(1, min(20, int(limit)))
    vector_hits = _safe_query_memory_vectors(user_id, query, limit=vector_limit)
    if vector_hits:
        memory_ids = []
        seen = set()
        for hit in vector_hits:
            memory_id = str(hit.get("memory_id") or "").strip()
            if memory_id and memory_id not in seen:
                seen.add(memory_id)
                memory_ids.append(memory_id)
        selected = await _list_user_memories_by_ids(db, user_id, memory_ids)
        score_by_id = {str(hit.get("memory_id")): float(hit.get("score") or 0.0) for hit in vector_hits}
        for memory in selected:
            memory["vector_score"] = score_by_id.get(str(memory.get("id")), 0.0)
            memory["retrieval_backend"] = memory_vector_backend()
        if selected:
            await _mark_memories_used(db, user_id, selected)
            return selected[:vector_limit]

    memories = await list_user_memories(db, user_id, include_deleted=False, limit=300)
    if not memories:
        return []
    query_terms = _tokenize(query)
    scored = [(_memory_score(memory, query_terms), memory) for memory in memories]
    scored.sort(key=lambda item: (item[0], item[1].get("updated_at") or ""), reverse=True)
    selected = [memory for score, memory in scored if score > 0][: max(1, min(20, int(limit)))]
    if selected:
        for memory in selected:
            memory["retrieval_backend"] = "sqlite"
        await _mark_memories_used(db, user_id, selected)
    return selected


def format_memories_for_prompt(memories: List[Dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines = [
        "Long-term user memory. Use these preferences to personalize tone, continuity, and helpfulness. "
        "Do not reveal this list unless the user asks what you remember."
    ]
    for memory in memories[:DEFAULT_RELEVANT_LIMIT]:
        category = str(memory.get("category") or "profile")
        content = str(memory.get("content") or "").strip()
        origin = str(memory.get("origin") or "inferred")
        sensitivity = str(memory.get("sensitivity") or "normal")
        if content:
            lines.append(f"- [{category}; {origin}; {sensitivity}] {content}")
    return "\n".join(lines).strip()
