"""Document registry listing and per-user access rules (list/open vs. retrieve)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import document_registry
from admin_audit import list_latest_uploads_by_document_id
from configs.settings import CHUNK_DIR, GRAPH_DIR, VECTOR_DIR
from services.auth import _is_admin_user


def _sort_registry_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        entries,
        key=lambda entry: str(entry.get("ingested_at") or ""),
        reverse=True,
    )


def _entry_from_upload(upload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    document_id = str(upload.get("document_id") or "").strip()
    if not document_id:
        return None
    paths = upload.get("paths") or {}
    graph_path = str(paths.get("graph_path") or "").strip()
    chunks_path = str(paths.get("chunks_path") or "").strip()
    vector_store_path = str(paths.get("vector_store_path") or "").strip()
    # Uploads ingested after graph building was removed have no graph path.
    if not chunks_path or not vector_store_path:
        return None
    owner_user_id = str((upload.get("uploader") or {}).get("id") or "")
    fallback_group = upload.get("document_group") or "global_kb"
    fallback_visibility = "private" if fallback_group == "user_private" else "global"
    return {
        "document_id": document_id,
        "title": upload.get("title", ""),
        "domain": upload.get("domain", "") or "general",
        "source": upload.get("source", "") or upload.get("filename", ""),
        "source_type": upload.get("source_type", ""),
        "document_group": fallback_group,
        "owner_user_id": owner_user_id,
        "visibility_scope": fallback_visibility,
        "ingested_at": upload.get("created_at", ""),
        "paths": {
            "processed_text": str(paths.get("processed_text_path") or ""),
            "chunks": chunks_path,
            "extractions": str(paths.get("extractions_path") or ""),
            "graph": graph_path,
            "vector_store": vector_store_path,
        },
        "neo4j_sync": {},
    }


def _entry_from_chunk_file(chunks_path: Path) -> Optional[Dict[str, Any]]:
    if chunks_path.name.startswith("."):
        return None
    try:
        with chunks_path.open("r", encoding="utf-8") as handle:
            first_line = handle.readline().strip()
    except (OSError, UnicodeDecodeError):
        return None
    if not first_line:
        return None

    try:
        first_chunk = json.loads(first_line)
    except json.JSONDecodeError:
        return None
    if not isinstance(first_chunk, dict):
        return None

    document_id = str(first_chunk.get("document_id") or chunks_path.stem.replace("_chunks", "")).strip()
    if not document_id:
        return None

    graph_path = GRAPH_DIR / f"{document_id}_graph.json"
    vector_store_path = VECTOR_DIR / document_id
    document_group = str(first_chunk.get("document_group") or "user_upload").strip() or "user_upload"
    owner_user_id = str(first_chunk.get("owner_user_id") or first_chunk.get("uploaded_by") or "").strip()
    visibility_scope = str(first_chunk.get("visibility_scope") or "").strip()
    if not visibility_scope and document_group.lower() in {"global", "global_kb", "shared"}:
        visibility_scope = "global"
    elif not visibility_scope and document_group.lower() in {"private", "user_private"}:
        visibility_scope = "private"

    return {
        "document_id": document_id,
        "title": first_chunk.get("document_title") or document_id,
        "domain": first_chunk.get("domain") or "general",
        "source": first_chunk.get("source") or chunks_path.name,
        "source_type": first_chunk.get("source_type") or "",
        "document_group": document_group,
        "owner_user_id": owner_user_id,
        "visibility_scope": visibility_scope,
        "ingested_at": first_chunk.get("ingested_at") or "",
        "paths": {
            "processed_text": "",
            "chunks": str(chunks_path),
            "extractions": "",
            "graph": str(graph_path) if graph_path.exists() else "",
            "vector_store": str(vector_store_path) if vector_store_path.exists() else "",
        },
        "neo4j_sync": {},
    }


def _collect_orphan_chunk_entries(existing_document_ids: set[str]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not CHUNK_DIR.exists():
        return entries

    for chunks_path in sorted(CHUNK_DIR.glob("*_chunks.jsonl")):
        entry = _entry_from_chunk_file(chunks_path)
        if not entry:
            continue
        document_id = str(entry.get("document_id") or "").strip()
        if document_id and document_id not in existing_document_ids:
            entries.append(entry)
    return entries


def _collect_document_entries() -> List[Dict[str, Any]]:
    audit_index = list_latest_uploads_by_document_id()
    merged: Dict[str, Dict[str, Any]] = {}

    for entry in document_registry.list_entries(valid_only=True):
        document_id = str(entry.get("document_id") or "").strip()
        if document_id:
            merged[document_id] = entry

    for document_id, upload in audit_index.items():
        if str(upload.get("status") or "") in {"deleted", "deleted_with_warnings"}:
            continue
        if document_id in merged:
            continue
        fallback = _entry_from_upload(upload)
        if fallback is not None:
            merged[document_id] = fallback

    for entry in _collect_orphan_chunk_entries(set(merged.keys())):
        document_id = str(entry.get("document_id") or "").strip()
        if document_id:
            merged[document_id] = entry

    return _sort_registry_entries(list(merged.values()))


def _is_global_entry(entry: Dict[str, Any]) -> bool:
    group = str(entry.get("document_group") or "").strip().lower()
    visibility = str(entry.get("visibility_scope") or "").strip().lower()
    return group in {"global_kb", "global", "shared"} or visibility == "global"


def _is_legacy_unowned_user_upload(entry: Dict[str, Any]) -> bool:
    group = str(entry.get("document_group") or "").strip().lower()
    owner_user_id = str(entry.get("owner_user_id") or "").strip()
    visibility = str(entry.get("visibility_scope") or "").strip().lower()
    return group == "user_upload" and not owner_user_id and not visibility


def _can_access_entry(user: Dict[str, Any], entry: Dict[str, Any]) -> bool:
    if _is_admin_user(user):
        return True
    if _is_legacy_unowned_user_upload(entry):
        return bool(str(user.get("id") or "").strip())
    group = str(entry.get("document_group") or "").strip().lower()
    owner_user_id = str(entry.get("owner_user_id") or "").strip()
    current_user_id = str(user.get("id") or "").strip()
    if group in {"user_private", "private"}:
        return bool(current_user_id) and current_user_id == owner_user_id
    return bool(current_user_id) and owner_user_id == current_user_id


def _can_retrieve_entry(user: Optional[Dict[str, Any]], entry: Dict[str, Any]) -> bool:
    if _is_admin_user(user):
        return True
    if _is_global_entry(entry):
        return True
    if not user:
        return False
    if _is_legacy_unowned_user_upload(entry):
        return bool(str(user.get("id") or "").strip())
    owner_user_id = str(entry.get("owner_user_id") or "").strip()
    current_user_id = str(user.get("id") or "").strip()
    return bool(current_user_id) and owner_user_id == current_user_id


def _accessible_registry_entries(user: Dict[str, Any], include_invalid: bool = False) -> List[Dict[str, Any]]:
    entries = document_registry.list_entries(valid_only=not include_invalid)
    return [entry for entry in entries if _can_access_entry(user, entry)]


def _retrievable_registry_entries(user: Optional[Dict[str, Any]], include_invalid: bool = False) -> List[Dict[str, Any]]:
    entries = document_registry.list_entries(valid_only=False) if include_invalid else _collect_document_entries()
    return [entry for entry in entries if _can_retrieve_entry(user, entry)]


def _accessible_document_ids(user: Dict[str, Any]) -> List[str]:
    output = []
    for entry in _accessible_registry_entries(user):
        document_id = str(entry.get("document_id") or "").strip()
        if document_id:
            output.append(document_id)
    return output
