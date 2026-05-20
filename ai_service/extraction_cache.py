"""SQLite-backed cache for expensive ESG extraction calls."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, Optional

from ai_service.extractor import extract_esg
from configs.settings import (
    ADAPTER_PATH,
    BASE_MODEL_PATH,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_EXTRACTION_MODEL,
    DEEPSEEK_MODEL,
    EXTRACTION_CACHE_ENABLED,
    EXTRACTION_CACHE_PATH,
)


_LOCK = Lock()


def cached_extract_esg(text: str) -> Dict[str, Any]:
    """Return a cached extraction result when available, otherwise run extraction."""
    if not EXTRACTION_CACHE_ENABLED:
        return extract_esg(text)

    normalized_text = (text or "").strip()
    if not normalized_text:
        return extract_esg(text)

    init_extraction_cache()
    text_hash = _hash_text(normalized_text)
    extractor_key = _extractor_key()
    cached = _get_cached(text_hash, extractor_key)
    if cached is not None:
        cached["cache_hit"] = True
        return cached

    result = extract_esg(normalized_text)
    _set_cached(text_hash, extractor_key, result)
    result["cache_hit"] = False
    return result


def init_extraction_cache() -> None:
    EXTRACTION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS extraction_cache (
                text_hash TEXT NOT NULL,
                extractor_key TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (text_hash, extractor_key)
            )
            """
        )
        db.commit()


def _get_cached(text_hash: str, extractor_key: str) -> Optional[Dict[str, Any]]:
    with _LOCK, _connect() as db:
        row = db.execute(
            "SELECT result_json FROM extraction_cache WHERE text_hash = ? AND extractor_key = ?",
            (text_hash, extractor_key),
        ).fetchone()
        if row is None:
            return None
        db.execute(
            """
            UPDATE extraction_cache
            SET hit_count = hit_count + 1, updated_at = ?
            WHERE text_hash = ? AND extractor_key = ?
            """,
            (_now(), text_hash, extractor_key),
        )
        db.commit()

    try:
        parsed = json.loads(row["result_json"])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _set_cached(text_hash: str, extractor_key: str, result: Dict[str, Any]) -> None:
    now = _now()
    payload = json.dumps(result, ensure_ascii=False)
    with _LOCK, _connect() as db:
        db.execute(
            """
            INSERT INTO extraction_cache (text_hash, extractor_key, result_json, created_at, updated_at, hit_count)
            VALUES (?, ?, ?, ?, ?, 0)
            ON CONFLICT(text_hash, extractor_key)
            DO UPDATE SET result_json = excluded.result_json, updated_at = excluded.updated_at
            """,
            (text_hash, extractor_key, payload, now, now),
        )
        db.commit()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extractor_key() -> str:
    raw = {
        "version": 5,
        "base_model": BASE_MODEL_PATH,
        "adapter": ADAPTER_PATH,
        "deepseek_base_url": DEEPSEEK_BASE_URL,
        "deepseek_model": DEEPSEEK_MODEL,
        "deepseek_extraction_model": DEEPSEEK_EXTRACTION_MODEL,
    }
    return hashlib.sha256(json.dumps(raw, sort_keys=True).encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    db = sqlite3.connect(str(EXTRACTION_CACHE_PATH))
    db.row_factory = sqlite3.Row
    return db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
