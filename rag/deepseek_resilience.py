"""Shared cache and circuit breaker for low-latency DeepSeek routing calls."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Dict, Optional, Tuple

from configs.settings import (
    DEEPSEEK_CACHE_ENABLED,
    DEEPSEEK_CACHE_TTL_SECONDS,
    DEEPSEEK_CIRCUIT_BREAK_SECONDS,
    DEEPSEEK_CIRCUIT_FAILURE_THRESHOLD,
    DEEPSEEK_FAILURE_CACHE_TTL_SECONDS,
)

try:
    from chat_memory_service import RedisUnavailableError, chat_memory_service
except Exception:  # pragma: no cover - import safety for isolated tooling
    RedisUnavailableError = RuntimeError  # type: ignore
    chat_memory_service = None  # type: ignore


_CACHE_VERSION = "v1"
_FAILURE_MARKER = {"__deepseek_failure__": True}
_memory_cache: Dict[str, Tuple[float, Any]] = {}
_memory_circuit: Dict[str, Dict[str, float]] = {}
_lock = threading.Lock()


def cache_lookup(namespace: str, payload: Dict[str, Any]) -> Tuple[bool, Any]:
    """Return (hit, value). A failure-cache hit returns (True, None)."""
    if not DEEPSEEK_CACHE_ENABLED:
        return False, None
    key = _cache_key(namespace, payload)
    raw = _redis_get(key)
    if raw is None:
        raw = _memory_get(key)
    if raw is None:
        return False, None
    value = _loads(raw)
    if value == _FAILURE_MARKER:
        return True, None
    return True, value


def cache_store(namespace: str, payload: Dict[str, Any], value: Any, ttl_seconds: Optional[int] = None) -> None:
    if not DEEPSEEK_CACHE_ENABLED or value is None:
        return
    ttl = int(ttl_seconds or DEEPSEEK_CACHE_TTL_SECONDS)
    key = _cache_key(namespace, payload)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True)
    _memory_set(key, raw, ttl)
    _redis_set(key, raw, ttl)


def cache_failure(namespace: str, payload: Dict[str, Any], ttl_seconds: Optional[int] = None) -> None:
    if not DEEPSEEK_CACHE_ENABLED:
        return
    ttl = int(ttl_seconds or DEEPSEEK_FAILURE_CACHE_TTL_SECONDS)
    key = _cache_key(namespace, payload)
    raw = json.dumps(_FAILURE_MARKER, sort_keys=True)
    _memory_set(key, raw, ttl)
    _redis_set(key, raw, ttl)


def circuit_is_open(namespace: str) -> bool:
    state = _circuit_get(namespace)
    opened_until = float(state.get("opened_until") or 0.0)
    return opened_until > time.time()


def record_success(namespace: str) -> None:
    _circuit_delete(namespace)


def record_failure(namespace: str) -> None:
    now = time.time()
    state = _circuit_get(namespace)
    failures = int(state.get("failures") or 0) + 1
    opened_until = float(state.get("opened_until") or 0.0)
    if failures >= DEEPSEEK_CIRCUIT_FAILURE_THRESHOLD:
        opened_until = now + DEEPSEEK_CIRCUIT_BREAK_SECONDS
    _circuit_set(namespace, {"failures": failures, "opened_until": opened_until})


def reset_state() -> None:
    """Test helper: clear process-local state. Redis state is intentionally untouched."""
    with _lock:
        _memory_cache.clear()
        _memory_circuit.clear()


def _cache_key(namespace: str, payload: Dict[str, Any]) -> str:
    body = json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    safe_namespace = "".join(ch if ch.isalnum() or ch in ":-_" else "_" for ch in str(namespace or "default"))
    return f"cg:deepseek:{_CACHE_VERSION}:{safe_namespace}:{digest}"


def _circuit_key(namespace: str) -> str:
    safe_namespace = "".join(ch if ch.isalnum() or ch in ":-_" else "_" for ch in str(namespace or "default"))
    return f"cg:deepseek:{_CACHE_VERSION}:circuit:{safe_namespace}"


def _loads(raw: Any) -> Any:
    try:
        return json.loads(str(raw or ""))
    except json.JSONDecodeError:
        return None


def _memory_get(key: str) -> Any:
    now = time.time()
    with _lock:
        item = _memory_cache.get(key)
        if item is None:
            return None
        expires_at, raw = item
        if expires_at <= now:
            _memory_cache.pop(key, None)
            return None
        return raw


def _memory_set(key: str, raw: str, ttl_seconds: int) -> None:
    with _lock:
        _memory_cache[key] = (time.time() + max(1, int(ttl_seconds)), raw)
        if len(_memory_cache) > 2048:
            expired = [item_key for item_key, (expires_at, _) in _memory_cache.items() if expires_at <= time.time()]
            for item_key in expired[:256]:
                _memory_cache.pop(item_key, None)
            while len(_memory_cache) > 2048:
                _memory_cache.pop(next(iter(_memory_cache)), None)


def _redis_available() -> bool:
    return bool(chat_memory_service and getattr(chat_memory_service, "enabled", False))


def _redis_get(key: str) -> Any:
    if not _redis_available():
        return None
    try:
        return chat_memory_service.client.execute("GET", key)
    except RedisUnavailableError:
        return None


def _redis_set(key: str, raw: str, ttl_seconds: int) -> None:
    if not _redis_available():
        return
    try:
        chat_memory_service.client.execute("SET", key, raw, "EX", max(1, int(ttl_seconds)))
    except RedisUnavailableError:
        return


def _redis_delete(key: str) -> None:
    if not _redis_available():
        return
    try:
        chat_memory_service.client.execute("DEL", key)
    except RedisUnavailableError:
        return


def _circuit_get(namespace: str) -> Dict[str, float]:
    key = _circuit_key(namespace)
    raw = _redis_get(key)
    parsed = _loads(raw) if raw is not None else None
    if isinstance(parsed, dict):
        return {
            "failures": float(parsed.get("failures") or 0),
            "opened_until": float(parsed.get("opened_until") or 0),
        }
    with _lock:
        return dict(_memory_circuit.get(namespace) or {})


def _circuit_set(namespace: str, state: Dict[str, float]) -> None:
    key = _circuit_key(namespace)
    ttl = max(DEEPSEEK_FAILURE_CACHE_TTL_SECONDS, DEEPSEEK_CIRCUIT_BREAK_SECONDS)
    raw = json.dumps(state, sort_keys=True)
    with _lock:
        _memory_circuit[namespace] = dict(state)
    _redis_set(key, raw, ttl)


def _circuit_delete(namespace: str) -> None:
    key = _circuit_key(namespace)
    with _lock:
        _memory_circuit.pop(namespace, None)
    _redis_delete(key)
