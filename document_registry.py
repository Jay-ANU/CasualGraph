"""Persistent registry mapping content hashes to ingested documents."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from configs.settings import DOCUMENT_DEDUP_ENABLED, DOCUMENT_REGISTRY_FILE


_REGISTRY_LOCK = Lock()
_WHITESPACE = re.compile(r"\s+")


def compute_raw_hash(file_bytes: Optional[bytes], content: str) -> Optional[str]:
    if file_bytes:
        return "sha256:" + hashlib.sha256(file_bytes).hexdigest()
    text = (content or "").strip()
    if not text:
        return None
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_text_hash(cleaned_text: str) -> str:
    normalized = _WHITESPACE.sub(" ", cleaned_text or "").strip()
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def lookup(
    *,
    raw_hash: Optional[str],
    text_hash: Optional[str],
    document_group: Optional[str] = None,
    owner_user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not DOCUMENT_DEDUP_ENABLED:
        return None
    with _REGISTRY_LOCK:
        data = _read_registry()
        entries: List[Dict[str, Any]] = data.get("entries", [])
        if raw_hash:
            for entry in entries:
                if entry.get("raw_hash") == raw_hash and _entry_visibility_matches(
                    entry, document_group=document_group, owner_user_id=owner_user_id
                ):
                    if _verify_paths(entry):
                        return {**entry, "matched_by": "raw_hash"}
                    _remove_locked(data, entry.get("document_id"))
                    _write_registry(data)
        if text_hash:
            for entry in entries:
                if entry.get("text_hash") == text_hash and _entry_visibility_matches(
                    entry, document_group=document_group, owner_user_id=owner_user_id
                ):
                    if _verify_paths(entry):
                        return {**entry, "matched_by": "text_hash"}
                    _remove_locked(data, entry.get("document_id"))
                    _write_registry(data)
    return None


def register(entry: Dict[str, Any]) -> None:
    document_id = str(entry.get("document_id") or "").strip()
    if not document_id:
        return
    payload = {
        "document_id": document_id,
        "title": entry.get("title", ""),
        "domain": entry.get("domain", ""),
        "source": entry.get("source", ""),
        "source_type": entry.get("source_type", ""),
        "document_group": entry.get("document_group", ""),
        "owner_user_id": entry.get("owner_user_id", ""),
        "visibility_scope": entry.get("visibility_scope", ""),
        "raw_hash": entry.get("raw_hash"),
        "text_hash": entry.get("text_hash"),
        "ingested_at": entry.get("ingested_at") or datetime.now(timezone.utc).isoformat(),
        "paths": dict(entry.get("paths") or {}),
        "neo4j_sync": dict(entry.get("neo4j_sync") or {}),
    }
    with _REGISTRY_LOCK:
        data = _read_registry()
        entries: List[Dict[str, Any]] = data.get("entries", [])
        entries = [item for item in entries if item.get("document_id") != document_id]
        entries.append(payload)
        data["entries"] = entries
        _write_registry(data)


def remove(document_id: str) -> None:
    document_id = str(document_id or "").strip()
    if not document_id:
        return
    with _REGISTRY_LOCK:
        data = _read_registry()
        if _remove_locked(data, document_id):
            _write_registry(data)


def get_entry(document_id: str, *, valid_only: bool = True) -> Optional[Dict[str, Any]]:
    document_id = str(document_id or "").strip()
    if not document_id:
        return None
    with _REGISTRY_LOCK:
        data = _read_registry()
        entries: List[Dict[str, Any]] = data.get("entries", [])
        changed = False
        for entry in entries:
            if str(entry.get("document_id") or "").strip() != document_id:
                continue
            if valid_only and not _verify_paths(entry):
                _remove_locked(data, document_id)
                changed = True
                break
            return dict(entry)
        if changed:
            _write_registry(data)
    return None


def update_metadata(document_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    document_id = str(document_id or "").strip()
    if not document_id:
        return None

    allowed = {"title", "domain", "source_type", "source"}
    normalized = {
        key: str(updates.get(key) or "").strip()
        for key in allowed
        if key in updates
    }
    if not normalized:
        return get_entry(document_id, valid_only=False)

    with _REGISTRY_LOCK:
        data = _read_registry()
        entries: List[Dict[str, Any]] = data.get("entries", [])
        for index, entry in enumerate(entries):
            if str(entry.get("document_id") or "").strip() != document_id:
                continue
            next_entry = dict(entry)
            next_entry.update(normalized)
            entries[index] = next_entry
            data["entries"] = entries
            _write_registry(data)
            return dict(next_entry)
    return None


def list_entries(*, valid_only: bool = True) -> List[Dict[str, Any]]:
    with _REGISTRY_LOCK:
        data = _read_registry()
        entries: List[Dict[str, Any]] = list(data.get("entries", []))
        results: List[Dict[str, Any]] = []
        changed = False

        for entry in entries:
            document_id = str(entry.get("document_id") or "").strip()
            if not document_id:
                continue
            if valid_only and not _verify_paths(entry):
                if _remove_locked(data, document_id):
                    changed = True
                continue
            results.append(dict(entry))

        if changed:
            _write_registry(data)

    return results


def _remove_locked(data: Dict[str, Any], document_id: Optional[str]) -> bool:
    if not document_id:
        return False
    entries = data.get("entries", [])
    new_entries = [item for item in entries if item.get("document_id") != document_id]
    if len(new_entries) == len(entries):
        return False
    data["entries"] = new_entries
    return True


def _verify_paths(entry: Dict[str, Any]) -> bool:
    paths = entry.get("paths") or {}
    chunks_path = Path(str(paths.get("chunks") or ""))
    graph_path = Path(str(paths.get("graph") or ""))
    vector_dir = Path(str(paths.get("vector_store") or ""))
    if not chunks_path.is_file():
        return False
    if not graph_path.is_file():
        return False
    if not vector_dir.is_dir():
        return False
    if not (vector_dir / "metadata.json").exists():
        return False
    return True


def _entry_visibility_matches(
    entry: Dict[str, Any],
    *,
    document_group: Optional[str],
    owner_user_id: Optional[str],
) -> bool:
    expected_group = str(document_group or "").strip()
    if expected_group and str(entry.get("document_group") or "").strip() != expected_group:
        return False
    if expected_group == "user_private":
        expected_owner = str(owner_user_id or "").strip()
        entry_owner = str(entry.get("owner_user_id") or "").strip()
        return bool(expected_owner) and expected_owner == entry_owner
    return True


def _read_registry() -> Dict[str, Any]:
    path = Path(DOCUMENT_REGISTRY_FILE)
    if not path.exists():
        return {"version": 1, "entries": []}
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return {"version": 1, "entries": []}
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {"version": 1, "entries": []}
        data.setdefault("version", 1)
        data.setdefault("entries", [])
        if not isinstance(data["entries"], list):
            data["entries"] = []
        return data
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "entries": []}


def _write_registry(data: Dict[str, Any]) -> None:
    path = Path(DOCUMENT_REGISTRY_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)
