"""Document registry listing and per-user access rules (list/open vs. retrieve).

A user may open or retrieve a document when the Phase 0 owner/global rules allow it **or** the
user is a member of a matter that contains it (contracts §8: extend, do not replace).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import document_registry
from admin_audit import get_latest_upload_by_document_id, list_latest_uploads_by_document_id
from configs.settings import CHUNK_DIR, GRAPH_DIR, VECTOR_DIR
from services import matters as matter_service
from services.auth import _is_admin_user

_DELETED_UPLOAD_STATUSES = frozenset({"deleted", "deleted_with_warnings"})


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


def _owner_rules_allow_access(user: Dict[str, Any], entry: Dict[str, Any]) -> bool:
    """Phase 0 open/list rule: admins, the owner, and any signed-in user for legacy unowned uploads."""
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


def _owner_rules_allow_retrieval(user: Optional[Dict[str, Any]], entry: Dict[str, Any]) -> bool:
    """Phase 0 retrieval rule: the open/list rule plus global documents for everyone."""
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


class _MatterDocumentIndex:
    """Ids of every document in the user's matters, loaded on the first lookup.

    Pass one as ``matter_document_ids`` when checking many entries for one user: a listing then
    costs at most one query, and none when the owner rules already decide every entry.
    """

    def __init__(self, user: Optional[Dict[str, Any]]):
        self._user_id = str((user or {}).get("id") or "").strip()
        self._ids: Optional[Set[str]] = None

    def __contains__(self, document_id: object) -> bool:
        if not self._user_id:
            return False
        if self._ids is None:
            self._ids = _user_matter_document_ids(self._user_id)
        return str(document_id or "").strip() in self._ids


def _user_matter_document_ids(user_id: str) -> Set[str]:
    try:
        return matter_service.user_matter_document_ids(user_id)
    except (sqlite3.Error, OSError) as exc:
        # Fail closed: without the matter tables nothing is shared through a matter.
        print(f"[document_access] matter membership lookup failed: {type(exc).__name__}")
        return set()


def _shared_through_matter(
    user: Optional[Dict[str, Any]],
    entry: Dict[str, Any],
    matter_document_ids: Optional[Any] = None,
) -> bool:
    user_id = str((user or {}).get("id") or "").strip()
    document_id = str(entry.get("document_id") or "").strip()
    if not user_id or not document_id:
        return False
    if matter_document_ids is not None:
        return document_id in matter_document_ids
    try:
        return matter_service.is_document_in_user_matters(user_id, document_id)
    except (sqlite3.Error, OSError) as exc:
        print(f"[document_access] matter membership lookup failed: {type(exc).__name__}")
        return False


def _can_access_entry(
    user: Dict[str, Any],
    entry: Dict[str, Any],
    *,
    matter_document_ids: Optional[Any] = None,
) -> bool:
    """Open/list: the owner rules, or membership of a matter containing the document.

    ``matter_document_ids`` (a set or ``_MatterDocumentIndex``) avoids one query per entry.
    """
    return _owner_rules_allow_access(user, entry) or _shared_through_matter(user, entry, matter_document_ids)


def _can_retrieve_entry(
    user: Optional[Dict[str, Any]],
    entry: Dict[str, Any],
    *,
    matter_document_ids: Optional[Any] = None,
) -> bool:
    """Retrieve (RAG): the owner/global rules, or membership of a matter containing the document."""
    return _owner_rules_allow_retrieval(user, entry) or _shared_through_matter(user, entry, matter_document_ids)


def _accessible_registry_entries(user: Dict[str, Any], include_invalid: bool = False) -> List[Dict[str, Any]]:
    entries = document_registry.list_entries(valid_only=not include_invalid)
    shared = _MatterDocumentIndex(user)
    return [entry for entry in entries if _can_access_entry(user, entry, matter_document_ids=shared)]


def _retrievable_registry_entries(user: Optional[Dict[str, Any]], include_invalid: bool = False) -> List[Dict[str, Any]]:
    entries = document_registry.list_entries(valid_only=False) if include_invalid else _collect_document_entries()
    shared = _MatterDocumentIndex(user)
    return [entry for entry in entries if _can_retrieve_entry(user, entry, matter_document_ids=shared)]


def _accessible_document_ids(user: Dict[str, Any]) -> List[str]:
    output = []
    for entry in _accessible_registry_entries(user):
        document_id = str(entry.get("document_id") or "").strip()
        if document_id:
            output.append(document_id)
    return output


def accessible_document_ids_for_matter(user: Optional[Dict[str, Any]], matter_id: str) -> List[str]:
    """Ids of the documents in ``matter_id`` the user may access.

    Membership (any role) grants every document linked to the matter; non-members, anonymous
    callers and unknown matters get ``[]``. Ids are returned even when the document is still
    being processed; retrieval callers intersect them with retrievable entries.
    """
    user_id = str((user or {}).get("id") or "").strip()
    matter_value = str(matter_id or "").strip()
    if not user_id or not matter_value:
        return []
    try:
        if matter_service.member_role(matter_value, user_id) is None:
            return []
        return matter_service.matter_document_ids(matter_value)
    except (sqlite3.Error, OSError) as exc:
        print(f"[document_access] matter document lookup failed: {type(exc).__name__}")
        return []


def _is_deleted_upload(upload: Optional[Dict[str, Any]]) -> bool:
    return bool(upload) and str(upload.get("status") or "") in _DELETED_UPLOAD_STATUSES


def _find_document_entry(document_id: str) -> Optional[Dict[str, Any]]:
    """The registry entry in any status, else the upload-audit fallback; None if unknown or deleted."""
    document_value = str(document_id or "").strip()
    if not document_value:
        return None
    upload = get_latest_upload_by_document_id(document_value)
    if _is_deleted_upload(upload):
        return None
    entry = document_registry.get_entry(document_value, valid_only=False)
    if entry is None and upload is not None:
        entry = _entry_from_upload(upload)
    return entry


def _document_entries_by_id(
    document_ids: Iterable[str],
    uploads: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Registry entries (any status, the registry is never pruned here) or upload-audit fallbacks
    for these ids; deleted documents and unknown ids are left out."""
    wanted = [str(item or "").strip() for item in document_ids if str(item or "").strip()]
    if not wanted:
        return {}
    if uploads is None:
        uploads = list_latest_uploads_by_document_id()
    registry = {
        str(entry.get("document_id") or "").strip(): entry
        for entry in document_registry.list_entries(valid_only=False)
    }
    found: Dict[str, Dict[str, Any]] = {}
    for document_id in wanted:
        upload = uploads.get(document_id)
        if _is_deleted_upload(upload):
            continue
        entry = registry.get(document_id)
        if entry is None and upload is not None:
            entry = _entry_from_upload(upload)
        if entry is not None:
            found[document_id] = entry
    return found


_ENTRY_STATUS_FIELDS = ("status_message", "language", "page_count", "clause_count", "source_format", "original_filename")


def summarize_matter_documents(matter_id: str) -> List[Dict[str, Any]]:
    """List payloads for the documents linked to a matter, most recently added first.

    Same fields as ``GET /documents`` (no server paths) plus the processing ``status`` and
    ``redaction`` summary (contracts §3: entries without ``status`` are legacy, i.e. ``ready`` /
    ``skipped_legacy``) and ``matter_link`` (who added it and when). Callers check membership.
    """
    from pipeline_runtime import summarize_registered_document  # heavy import, only listings need it

    links = matter_service.matter_document_links(matter_id)
    if not links:
        return []
    uploads = list_latest_uploads_by_document_id()
    entries = _document_entries_by_id((link["document_id"] for link in links), uploads)
    documents: List[Dict[str, Any]] = []
    for link in links:
        document_id = link["document_id"]
        entry = entries.get(document_id)
        if entry is None:
            continue
        try:
            summary = dict(summarize_registered_document(entry, audit=uploads.get(document_id)))
        except Exception as exc:
            print(f"[document_access] Summary load failed for a matter document: {type(exc).__name__}")
            continue
        legacy = "status" not in entry
        summary.setdefault("status", "ready" if legacy else entry.get("status"))
        for key in _ENTRY_STATUS_FIELDS:
            if key in entry and key not in summary:
                summary[key] = entry[key]
        if "redaction" not in summary:
            redaction = entry.get("redaction")
            if isinstance(redaction, dict):
                summary["redaction"] = dict(redaction)
            elif legacy:
                summary["redaction"] = {"status": "skipped_legacy"}
        summary["matter_link"] = {"added_by": link["added_by"], "added_at": link["added_at"]}
        documents.append(summary)
    return documents
