"""Long-term user memory glue for answers: prompt injection and background extraction."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from services import db as db_service
from user_memory_service import (
    format_memories_for_prompt,
    get_relevant_user_memories,
    init_user_memory_db,
    remember_exchange,
)


async def _load_long_term_memory_context(
    db: aiosqlite.Connection,
    current_user: Optional[dict],
    query: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    if not current_user:
        return "", []
    user_id = str(current_user.get("id") or "").strip()
    if not user_id:
        return "", []
    try:
        memories = await get_relevant_user_memories(db, user_id, query)
    except Exception as exc:
        print(f"[memory] retrieval skipped: {type(exc).__name__}: {exc}")
        return "", []
    return format_memories_for_prompt(memories), memories


def _history_with_long_term_memory(history: Optional[List[Dict[str, Any]]], memory_context: str) -> List[Dict[str, Any]]:
    normalized = list(history or [])
    if not memory_context:
        return normalized
    return [{"role": "assistant", "content": memory_context}, *normalized]


def _remember_exchange_later(
    *,
    user_id: Optional[str],
    user_message: str,
    assistant_message: str,
    source: str,
) -> None:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id or not str(user_message or "").strip() or not str(assistant_message or "").strip():
        return

    def _worker() -> None:
        async def _run() -> None:
            async with aiosqlite.connect(db_service._DB_PATH) as memory_db:
                await init_user_memory_db(memory_db)
                await remember_exchange(
                    memory_db,
                    user_id=normalized_user_id,
                    user_message=user_message,
                    assistant_message=assistant_message,
                    source=source,
                )

        try:
            asyncio.run(_run())
        except Exception as exc:
            print(f"[memory] background store skipped: {type(exc).__name__}: {exc}")

    threading.Thread(target=_worker, daemon=True).start()
