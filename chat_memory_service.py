"""Redis-backed short-term chat memory with a zero-dependency RESP client."""

from __future__ import annotations

import json
import socket
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from configs.settings import (
    REDIS_CHAT_HISTORY_LIMIT,
    REDIS_CHAT_MAX_MESSAGES,
    REDIS_CHAT_SESSION_TTL_SECONDS,
    REDIS_ENABLED,
    REDIS_URL,
)


class RedisUnavailableError(RuntimeError):
    """Raised when Redis memory is unavailable."""


class RedisProtocolError(RuntimeError):
    """Raised on RESP or Redis command errors."""


@dataclass
class _RedisConfig:
    host: str
    port: int
    password: str
    db: int
    timeout: float


def _parse_redis_url(url: str) -> _RedisConfig:
    parsed = urlparse(url or "redis://127.0.0.1:6379/0")
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 6379)
    password = parsed.password or ""
    db_path = (parsed.path or "/0").strip("/")
    db = int(db_path or "0")
    return _RedisConfig(host=host, port=port, password=password, db=db, timeout=2.0)


class _RedisClient:
    def __init__(self, config: _RedisConfig):
        self.config = config

    def execute(self, *parts: object) -> Any:
        try:
            with closing(socket.create_connection((self.config.host, self.config.port), timeout=self.config.timeout)) as sock:
                sock.settimeout(self.config.timeout)
                reader = sock.makefile("rb")
                writer = sock.makefile("wb")
                if self.config.password:
                    self._write_command(writer, "AUTH", self.config.password)
                    self._read_response(reader)
                if self.config.db:
                    self._write_command(writer, "SELECT", self.config.db)
                    self._read_response(reader)
                self._write_command(writer, *parts)
                return self._read_response(reader)
        except (OSError, ValueError, RedisProtocolError) as exc:
            raise RedisUnavailableError(str(exc)) from exc

    def _write_command(self, writer, *parts: object) -> None:
        encoded = [str(part).encode("utf-8") for part in parts]
        writer.write(f"*{len(encoded)}\r\n".encode("utf-8"))
        for item in encoded:
            writer.write(f"${len(item)}\r\n".encode("utf-8"))
            writer.write(item + b"\r\n")
        writer.flush()

    def _read_response(self, reader) -> Any:
        prefix = reader.read(1)
        if not prefix:
            raise RedisProtocolError("empty Redis response")
        if prefix == b"+":
            return self._readline(reader)
        if prefix == b"-":
            raise RedisProtocolError(self._readline(reader))
        if prefix == b":":
            return int(self._readline(reader))
        if prefix == b"$":
            length = int(self._readline(reader))
            if length == -1:
                return None
            data = reader.read(length)
            reader.read(2)
            return data.decode("utf-8")
        if prefix == b"*":
            length = int(self._readline(reader))
            if length == -1:
                return []
            return [self._read_response(reader) for _ in range(length)]
        raise RedisProtocolError(f"unsupported RESP prefix: {prefix!r}")

    @staticmethod
    def _readline(reader) -> str:
        line = reader.readline()
        if not line:
            raise RedisProtocolError("unexpected EOF")
        return line[:-2].decode("utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _epoch_score(iso_value: str) -> float:
    try:
        return datetime.fromisoformat(iso_value).timestamp()
    except Exception:
        return datetime.now(timezone.utc).timestamp()


def _normalize_message(message: Dict[str, Any]) -> Dict[str, Any]:
    role = str(message.get("role") or message.get("type") or "user").strip().lower()
    if role == "agent":
        role = "assistant"
    if role not in {"user", "assistant"}:
        role = "assistant"
    content = str(message.get("content") or "").strip()
    return {
        "role": role,
        "content": content,
        "timestamp": str(message.get("timestamp") or _now_iso()),
        "data": dict(message.get("data") or {}),
    }


def _derive_title(meta: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
    existing = str(meta.get("title") or "").strip()
    if existing and existing != "New chat":
        return existing
    for item in messages:
        if item.get("role") == "user" and str(item.get("content") or "").strip():
            text = str(item["content"]).strip().replace("\n", " ")
            return text[:48] + ("..." if len(text) > 48 else "")
    return existing or "New chat"


class ChatMemoryService:
    def __init__(self):
        self.enabled = REDIS_ENABLED
        self.config = _parse_redis_url(REDIS_URL)
        self.client = _RedisClient(self.config)
        self.ttl_seconds = REDIS_CHAT_SESSION_TTL_SECONDS
        self.max_messages = REDIS_CHAT_MAX_MESSAGES
        self.history_limit = REDIS_CHAT_HISTORY_LIMIT

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        try:
            self.client.execute("PING")
            return True
        except RedisUnavailableError:
            return False

    def create_session(
        self,
        *,
        user_id: str,
        title: str = "",
        selected_document_id: str = "",
        mode: str = "ask",
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_available()
        session_id = session_id or str(uuid.uuid4())
        now = _now_iso()
        meta = {
            "id": session_id,
            "user_id": user_id,
            "title": title.strip() or "New chat",
            "selected_document_id": selected_document_id.strip(),
            "mode": str(mode or "ask").strip().lower() or "ask",
            "created_at": now,
            "updated_at": now,
            "message_count": 0,
            "memory_backend": "redis",
        }
        self.client.execute("SET", self._meta_key(session_id), json.dumps(meta, ensure_ascii=False))
        self.client.execute("ZADD", self._user_sessions_key(user_id), _epoch_score(now), session_id)
        self._touch_session(session_id, user_id)
        return meta

    def list_sessions(self, *, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        self._ensure_available()
        session_ids = self.client.execute("ZREVRANGE", self._user_sessions_key(user_id), 0, max(0, int(limit) - 1)) or []
        sessions: List[Dict[str, Any]] = []
        for session_id in session_ids:
            meta = self._get_meta(session_id)
            if meta is None:
                self.client.execute("ZREM", self._user_sessions_key(user_id), session_id)
                continue
            if str(meta.get("user_id") or "") != user_id:
                continue
            sessions.append(meta)
        return sessions

    def get_session(self, *, user_id: str, session_id: str, include_messages: bool = True) -> Dict[str, Any]:
        self._ensure_available()
        meta = self._require_meta(user_id, session_id)
        messages = self._load_messages(session_id) if include_messages else []
        summary = self._get_summary(session_id)
        self._touch_session(session_id, user_id)
        return {
            "session": meta,
            "messages": messages,
            "summary": summary,
        }

    def append_message(self, *, user_id: str, session_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_available()
        meta = self._require_meta(user_id, session_id)
        normalized = _normalize_message(message)
        self.client.execute("RPUSH", self._messages_key(session_id), json.dumps(normalized, ensure_ascii=False))
        current_length = int(self.client.execute("LLEN", self._messages_key(session_id)) or 0)
        if current_length > self.max_messages:
            overflow = current_length - self.max_messages
            rolled = self.client.execute("LRANGE", self._messages_key(session_id), 0, overflow - 1) or []
            self._append_summary(session_id, rolled)
            self.client.execute("LTRIM", self._messages_key(session_id), overflow, -1)

        messages = self._load_messages(session_id)
        now = _now_iso()
        meta["updated_at"] = now
        meta["message_count"] = len(messages)
        meta["title"] = _derive_title(meta, messages)
        self._save_meta(meta)
        self.client.execute("ZADD", self._user_sessions_key(user_id), _epoch_score(now), session_id)
        self._touch_session(session_id, user_id)
        return meta

    def update_session(
        self,
        *,
        user_id: str,
        session_id: str,
        title: Optional[str] = None,
        selected_document_id: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_available()
        meta = self._require_meta(user_id, session_id)
        if title is not None:
            meta["title"] = str(title).strip() or meta.get("title") or "New chat"
        if selected_document_id is not None:
            meta["selected_document_id"] = str(selected_document_id).strip()
        if mode is not None:
            meta["mode"] = str(mode).strip().lower() or meta.get("mode") or "ask"
        meta["updated_at"] = _now_iso()
        self._save_meta(meta)
        self.client.execute("ZADD", self._user_sessions_key(user_id), _epoch_score(meta["updated_at"]), session_id)
        self._touch_session(session_id, user_id)
        return meta

    def delete_session(self, *, user_id: str, session_id: str) -> None:
        self._ensure_available()
        self._require_meta(user_id, session_id)
        self.client.execute(
            "DEL",
            self._meta_key(session_id),
            self._messages_key(session_id),
            self._summary_key(session_id),
        )
        self.client.execute("ZREM", self._user_sessions_key(user_id), session_id)

    def get_recent_history(self, *, user_id: str, session_id: str, limit: Optional[int] = None) -> List[Dict[str, str]]:
        self._ensure_available()
        self._require_meta(user_id, session_id)
        normalized_limit = max(1, int(limit or self.history_limit))
        messages = self._load_messages(session_id)
        history = [{"role": item["role"], "content": item["content"]} for item in messages[-normalized_limit:]]
        summary = self._get_summary(session_id)
        if summary:
            history.insert(0, {"role": "assistant", "content": f"Conversation summary:\n{summary}"})
        self._touch_session(session_id, user_id)
        return history

    def _append_summary(self, session_id: str, raw_messages: List[str]) -> None:
        summary_lines = [str(item or "").strip() for item in raw_messages]
        normalized_lines: List[str] = []
        for raw in summary_lines:
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            role = str(parsed.get("role") or "assistant").strip().lower()
            content = str(parsed.get("content") or "").strip()
            if content:
                normalized_lines.append(f"{role}: {content}")
        if not normalized_lines:
            return
        existing = self._get_summary(session_id)
        combined = "\n".join([part for part in [existing, *normalized_lines] if part]).strip()
        if len(combined) > 2400:
            combined = combined[-2400:]
        self.client.execute("SET", self._summary_key(session_id), combined)

    def _load_messages(self, session_id: str) -> List[Dict[str, Any]]:
        rows = self.client.execute("LRANGE", self._messages_key(session_id), 0, -1) or []
        messages: List[Dict[str, Any]] = []
        for raw in rows:
            try:
                parsed = json.loads(str(raw or ""))
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                messages.append(parsed)
        return messages

    def _get_summary(self, session_id: str) -> str:
        value = self.client.execute("GET", self._summary_key(session_id))
        return str(value or "").strip()

    def _save_meta(self, meta: Dict[str, Any]) -> None:
        self.client.execute("SET", self._meta_key(str(meta["id"])), json.dumps(meta, ensure_ascii=False))

    def _get_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        raw = self.client.execute("GET", self._meta_key(session_id))
        if not raw:
            return None
        try:
            parsed = json.loads(str(raw))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _require_meta(self, user_id: str, session_id: str) -> Dict[str, Any]:
        meta = self._get_meta(session_id)
        if meta is None or str(meta.get("user_id") or "") != user_id:
            raise RedisUnavailableError("chat session not found")
        return meta

    def _touch_session(self, session_id: str, user_id: str) -> None:
        ttl = str(max(60, int(self.ttl_seconds)))
        self.client.execute("EXPIRE", self._meta_key(session_id), ttl)
        self.client.execute("EXPIRE", self._messages_key(session_id), ttl)
        self.client.execute("EXPIRE", self._summary_key(session_id), ttl)
        self.client.execute("EXPIRE", self._user_sessions_key(user_id), ttl)

    def _ensure_available(self) -> None:
        if not self.is_available():
            raise RedisUnavailableError("Redis chat memory is unavailable")

    @staticmethod
    def _meta_key(session_id: str) -> str:
        return f"cg:chat:session:{session_id}:meta"

    @staticmethod
    def _messages_key(session_id: str) -> str:
        return f"cg:chat:session:{session_id}:messages"

    @staticmethod
    def _summary_key(session_id: str) -> str:
        return f"cg:chat:session:{session_id}:summary"

    @staticmethod
    def _user_sessions_key(user_id: str) -> str:
        return f"cg:chat:user:{user_id}:sessions"


chat_memory_service = ChatMemoryService()
