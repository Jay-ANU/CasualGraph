"""Matter (案件) workspaces: organizations, matters, membership, document links and migration.

Access model (contracts §8, WP1-C brief §1.2):

* A matter belongs to one organization. Every user gets a personal organization
  ("<username or email> 的工作区", org role ``owner``) holding a default matter "未分类"
  in which the user is ``lead``. Uploads without a matter land there.
* Matter roles rank ``viewer`` < ``member`` < ``lead``. Viewers read the matter, its members and
  its documents and may ask questions about them; members also upload, attach and detach
  documents; leads also edit and archive the matter, manage members and read the audit log.
* An org ``owner``/``admin`` may manage a matter of that org (metadata, members, audit) without
  being a member, but reaches its documents only by adding themselves, which is audited.
  Platform admins (``users.role == "admin"``) are not implicitly members of anything here.
* DELETE archives; nothing is hard-deleted. An archived matter is read-only for documents
  (no upload, attach or detach) and can be restored with ``status="active"``. The personal
  default matter cannot be archived.

Every function is synchronous and uses short-lived sqlite3 connections from ``services.db``
because the document access checks and the RAG scope resolver that depend on it are
synchronous. Permission failures raise ``HTTPException`` with detail
``{"error": <code>, "message": <text>}``.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException

import document_registry
from services import audit
from services import db as db_service

MATTER_ROLES: Tuple[str, ...] = ("viewer", "member", "lead")
_MATTER_ROLE_RANK = {role: rank for rank, role in enumerate(MATTER_ROLES, start=1)}
ORG_MANAGER_ROLES = frozenset({"owner", "admin"})
MATTER_STATUSES: Tuple[str, ...] = ("active", "archived")
DEFAULT_MATTER_NAME = "未分类"
PERSONAL_ORG_SUFFIX = " 的工作区"
SYSTEM_ACTOR = "system"
MAX_NAME_LENGTH = 200
MAX_CLIENT_REF_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 4000
PENDING_UPLOAD_TTL_SECONDS = 7 * 24 * 3600

_TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "rejected"})
_PENDING_UPLOADS: Dict[str, Dict[str, Any]] = {}
_PENDING_UPLOADS_LOCK = threading.Lock()


# ── small helpers ────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": code, "message": message})


def _user_id(user: Optional[Dict[str, Any]]) -> str:
    return str((user or {}).get("id") or "").strip()


def _require_user_id(user: Optional[Dict[str, Any]]) -> str:
    user_id = _user_id(user)
    if not user_id:
        raise _error(401, "not_authenticated", "Sign in to use matters.")
    return user_id


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_field(value: Any, field: str, max_length: int, *, required: bool = False) -> str:
    text = _clean(value)
    if required and not text:
        raise _error(400, "invalid_matter", f"{field} is required.")
    if len(text) > max_length:
        raise _error(400, "invalid_matter", f"{field} is longer than {max_length} characters.")
    return text


def _matter_role(value: Any) -> str:
    role = _clean(value).lower()
    if role not in _MATTER_ROLE_RANK:
        raise _error(400, "invalid_role", f"role must be one of: {', '.join(MATTER_ROLES)}.")
    return role


def _role_rank(role: Optional[str]) -> int:
    return _MATTER_ROLE_RANK.get(str(role or ""), 0)


def _load_settings(raw: Any) -> Dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _connect() -> sqlite3.Connection:
    return db_service.connect_auth_db_sync()


# ── rows and permission checks ───────────────────────────────────────────────


def _matter_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    settings = _load_settings(row["settings_json"])
    return {
        "id": row["id"],
        "org_id": row["org_id"],
        "name": row["name"],
        "client_ref": row["client_ref"] or "",
        "description": row["description"] or "",
        "status": row["status"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "is_default": bool(settings.get("default")),
    }


def _fetch_matter(conn: sqlite3.Connection, matter_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute("SELECT * FROM matters WHERE id = ?", (matter_id,)).fetchone()
    return _matter_from_row(row) if row else None


def _member_role(conn: sqlite3.Connection, matter_id: str, user_id: str) -> Optional[str]:
    row = conn.execute(
        "SELECT role FROM matter_members WHERE matter_id = ? AND user_id = ?",
        (matter_id, user_id),
    ).fetchone()
    return str(row[0]) if row else None


def _org_role(conn: sqlite3.Connection, org_id: str, user_id: str) -> Optional[str]:
    row = conn.execute(
        "SELECT role FROM org_members WHERE org_id = ? AND user_id = ?",
        (org_id, user_id),
    ).fetchone()
    return str(row[0]) if row else None


def _access(conn: sqlite3.Connection, matter_id: str, user_id: str) -> Dict[str, Any]:
    matter = _fetch_matter(conn, matter_id) if matter_id else None
    if matter is None:
        raise _error(404, "matter_not_found", "No matter found for this id.")
    role = _member_role(conn, matter_id, user_id) if user_id else None
    org_role = _org_role(conn, matter["org_id"], user_id) if user_id else None
    return {
        "matter": matter,
        "role": role,
        "org_role": org_role,
        "can_manage": role == "lead" or org_role in ORG_MANAGER_ROLES,
    }


def _require_role(conn: sqlite3.Connection, matter_id: str, user_id: str, min_role: str) -> Dict[str, Any]:
    access = _access(conn, matter_id, user_id)
    if access["role"] is None:
        raise _error(403, "matter_forbidden", "You are not a member of this matter.")
    if _role_rank(access["role"]) < _role_rank(min_role):
        raise _error(403, "matter_forbidden", f"This needs the matter role '{min_role}' or higher.")
    return access


def _require_reader(conn: sqlite3.Connection, matter_id: str, user_id: str) -> Dict[str, Any]:
    """Members, plus org owners/admins for metadata (never documents)."""
    access = _access(conn, matter_id, user_id)
    if access["role"] is None and not access["can_manage"]:
        raise _error(403, "matter_forbidden", "You are not a member of this matter.")
    return access


def _require_manager(conn: sqlite3.Connection, matter_id: str, user_id: str) -> Dict[str, Any]:
    access = _access(conn, matter_id, user_id)
    if not access["can_manage"]:
        if access["role"] is None:
            raise _error(403, "matter_forbidden", "You are not a member of this matter.")
        raise _error(403, "matter_forbidden", "Only the matter lead or an organization admin can do this.")
    return access


def _require_active(matter: Dict[str, Any]) -> None:
    if matter["status"] != "active":
        raise _error(409, "matter_archived", "This matter is archived; restore it before changing its documents.")


def require_matter_member(
    matter_id: str,
    user: Optional[Dict[str, Any]],
    min_role: str = "viewer",
    *,
    require_active: bool = False,
) -> Dict[str, Any]:
    """Return ``{"matter", "role"}`` when ``user`` holds at least ``min_role`` in the matter.

    Raises ``HTTPException`` 404 ``matter_not_found`` or 403 ``matter_forbidden`` (also for
    anonymous callers and platform admins who are not members), and 409 ``matter_archived``
    when ``require_active`` is set and the matter is archived.
    """
    if min_role not in _MATTER_ROLE_RANK:
        raise ValueError(f"min_role must be one of {MATTER_ROLES}")
    matter_value = _clean(matter_id)
    user_id = _user_id(user)
    if not matter_value:
        raise _error(404, "matter_not_found", "No matter found for this id.")
    if not user_id:
        raise _error(403, "matter_forbidden", "Sign in as a member of this matter.")
    with closing(_connect()) as conn:
        access = _require_role(conn, matter_value, user_id, min_role)
    if require_active:
        _require_active(access["matter"])
    return {"matter": access["matter"], "role": access["role"]}


def require_matter_manager(matter_id: str, user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """``{"matter", "role", "org_role"}`` when the user is the matter's lead or an owner/admin of
    its organization (edit, archive, members, audit log); raises 404/403 otherwise."""
    user_id = _require_user_id(user)
    with closing(_connect()) as conn:
        access = _require_manager(conn, _clean(matter_id), user_id)
    return {"matter": access["matter"], "role": access["role"], "org_role": access["org_role"]}


def member_role(matter_id: str, user_id: str) -> Optional[str]:
    """The user's role in the matter, or None."""
    matter_value, user_value = _clean(matter_id), _clean(user_id)
    if not matter_value or not user_value:
        return None
    with closing(_connect()) as conn:
        return _member_role(conn, matter_value, user_value)


# ── matter views ─────────────────────────────────────────────────────────────

_MATTER_VIEW_COLUMNS = """
    m.*,
    (SELECT role FROM matter_members WHERE matter_id = m.id AND user_id = :user_id) AS caller_role,
    (SELECT role FROM org_members WHERE org_id = m.org_id AND user_id = :user_id) AS caller_org_role,
    (SELECT COUNT(*) FROM matter_documents WHERE matter_id = m.id) AS document_count,
    (SELECT COUNT(*) FROM matter_members WHERE matter_id = m.id) AS member_count
"""


def _view_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    matter = _matter_from_row(row)
    role = row["caller_role"]
    return {
        "id": matter["id"],
        "name": matter["name"],
        "client_ref": matter["client_ref"],
        "description": matter["description"],
        "status": matter["status"],
        "org_id": matter["org_id"],
        "role": role,
        "document_count": int(row["document_count"] or 0),
        "member_count": int(row["member_count"] or 0),
        "created_at": matter["created_at"],
        "updated_at": matter["updated_at"],
        "is_default": matter["is_default"],
        "can_manage": role == "lead" or row["caller_org_role"] in ORG_MANAGER_ROLES,
    }


def _matter_view(conn: sqlite3.Connection, matter_id: str, user_id: str) -> Dict[str, Any]:
    row = conn.execute(
        f"SELECT {_MATTER_VIEW_COLUMNS} FROM matters m WHERE m.id = :matter_id",
        {"user_id": user_id, "matter_id": matter_id},
    ).fetchone()
    if row is None:
        raise _error(404, "matter_not_found", "No matter found for this id.")
    return _view_from_row(row)


def get_matter(matter_id: str) -> Optional[Dict[str, Any]]:
    """The stored matter (no caller-specific fields), or None."""
    matter_value = _clean(matter_id)
    if not matter_value:
        return None
    with closing(_connect()) as conn:
        return _fetch_matter(conn, matter_value)


def get_matter_for_user(matter_id: str, user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """API view of one matter for a member or an org owner/admin."""
    user_id = _require_user_id(user)
    matter_value = _clean(matter_id)
    with closing(_connect()) as conn:
        _require_reader(conn, matter_value, user_id)
        return _matter_view(conn, matter_value, user_id)


def list_matters(user: Optional[Dict[str, Any]], *, include_archived: bool = False) -> List[Dict[str, Any]]:
    """Matters the user is a member of: active first, most recently updated first."""
    user_id = _require_user_id(user)
    with closing(_connect()) as conn:
        rows = conn.execute(
            f"""
            SELECT {_MATTER_VIEW_COLUMNS}
            FROM matters m
            WHERE m.id IN (SELECT matter_id FROM matter_members WHERE user_id = :user_id)
              AND (:include_archived = 1 OR m.status = 'active')
            ORDER BY CASE m.status WHEN 'active' THEN 0 ELSE 1 END, m.updated_at DESC, m.created_at DESC
            """,
            {"user_id": user_id, "include_archived": 1 if include_archived else 0},
        ).fetchall()
    return [_view_from_row(row) for row in rows]


# ── personal workspace ───────────────────────────────────────────────────────


def _personal_org_name(user: Dict[str, Any]) -> str:
    label = _clean(user.get("username")) or _clean(user.get("email")) or _user_id(user)
    return f"{label}{PERSONAL_ORG_SUFFIX}"


def _find_personal_workspace(conn: sqlite3.Connection, user_id: str) -> Tuple[Optional[str], Optional[str]]:
    org_id: Optional[str] = None
    for row in conn.execute(
        """
        SELECT o.id, o.settings_json FROM organizations o
        JOIN org_members om ON om.org_id = o.id
        WHERE om.user_id = ? AND om.role = 'owner'
        ORDER BY o.created_at, o.id
        """,
        (user_id,),
    ):
        settings = _load_settings(row["settings_json"])
        if settings.get("personal") and settings.get("owner_user_id") == user_id:
            org_id = row["id"]
            break
    if org_id is None:
        return None, None
    for row in conn.execute("SELECT id, settings_json FROM matters WHERE org_id = ? ORDER BY created_at, id", (org_id,)):
        if _load_settings(row["settings_json"]).get("default"):
            return org_id, row["id"]
    return org_id, None


def _insert_matter(
    conn: sqlite3.Connection,
    *,
    matter_id: str,
    org_id: str,
    name: str,
    client_ref: str,
    description: str,
    created_by: str,
    settings: Dict[str, Any],
    now: str,
) -> None:
    conn.execute(
        """
        INSERT INTO matters
            (id, org_id, name, client_ref, description, status, created_by, created_at, updated_at, settings_json)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
        """,
        (matter_id, org_id, name, client_ref, description, created_by, now, now, json.dumps(settings, sort_keys=True)),
    )


def _insert_member(conn: sqlite3.Connection, matter_id: str, user_id: str, role: str, *, added_by: str, now: str) -> None:
    conn.execute(
        "INSERT INTO matter_members (matter_id, user_id, role, added_by, created_at) VALUES (?, ?, ?, ?, ?)",
        (matter_id, user_id, role, added_by, now),
    )


def _ensure_personal_workspace(
    conn: sqlite3.Connection,
    user: Dict[str, Any],
    *,
    actor_user_id: str,
) -> Tuple[Dict[str, str], bool]:
    """Inside an open write transaction: find or create the org and default matter."""
    user_id = _require_user_id(user)
    org_id, matter_id = _find_personal_workspace(conn, user_id)
    created = False
    now = _now_iso()
    if org_id is None:
        org_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO organizations (id, name, created_at, settings_json) VALUES (?, ?, ?, ?)",
            (org_id, _personal_org_name(user), now, json.dumps({"personal": True, "owner_user_id": user_id}, sort_keys=True)),
        )
        conn.execute(
            "INSERT INTO org_members (org_id, user_id, role, created_at) VALUES (?, ?, 'owner', ?)",
            (org_id, user_id, now),
        )
        created = True
    if matter_id is None:
        matter_id = str(uuid.uuid4())
        _insert_matter(
            conn,
            matter_id=matter_id,
            org_id=org_id,
            name=DEFAULT_MATTER_NAME,
            client_ref="",
            description="",
            created_by=user_id,
            settings={"default": True},
            now=now,
        )
        _insert_member(conn, matter_id, user_id, "lead", added_by=actor_user_id, now=now)
        audit.write_event(
            conn,
            actor_user_id=actor_user_id,
            action="matter.created",
            target_type="matter",
            target_id=matter_id,
            matter_id=matter_id,
            org_id=org_id,
            details={"default": True},
        )
        created = True
    return {"org_id": org_id, "matter_id": matter_id}, created


def ensure_personal_workspace(user: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """``{"org_id", "matter_id"}`` of the user's personal org and default matter, created once.

    Idempotent and safe under concurrency: the lookup is repeated inside a ``BEGIN IMMEDIATE``
    transaction before anything is created.
    """
    user_id = _require_user_id(user)
    with closing(_connect()) as conn:
        org_id, matter_id = _find_personal_workspace(conn, user_id)
    if org_id and matter_id:
        return {"org_id": org_id, "matter_id": matter_id}
    with db_service.auth_db_transaction() as conn:
        workspace, _created = _ensure_personal_workspace(conn, dict(user or {}), actor_user_id=user_id)
    return workspace


# ── matter CRUD ──────────────────────────────────────────────────────────────


def create_matter(
    user: Optional[Dict[str, Any]],
    *,
    name: str,
    client_ref: str = "",
    description: str = "",
    org_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a matter (in the user's personal org unless ``org_id`` is given); the creator is lead."""
    user_id = _require_user_id(user)
    name_value = _clean_field(name, "name", MAX_NAME_LENGTH, required=True)
    client_ref_value = _clean_field(client_ref, "client_ref", MAX_CLIENT_REF_LENGTH)
    description_value = _clean_field(description, "description", MAX_DESCRIPTION_LENGTH)
    org_value = _clean(org_id) or ensure_personal_workspace(user)["org_id"]
    matter_id = str(uuid.uuid4())
    now = _now_iso()
    with db_service.auth_db_transaction() as conn:
        if _org_role(conn, org_value, user_id) is None:
            raise _error(403, "org_forbidden", "You are not a member of this organization.")
        _insert_matter(
            conn,
            matter_id=matter_id,
            org_id=org_value,
            name=name_value,
            client_ref=client_ref_value,
            description=description_value,
            created_by=user_id,
            settings={},
            now=now,
        )
        _insert_member(conn, matter_id, user_id, "lead", added_by=user_id, now=now)
        audit.write_event(
            conn,
            actor_user_id=user_id,
            action="matter.created",
            target_type="matter",
            target_id=matter_id,
            matter_id=matter_id,
            org_id=org_value,
        )
        return _matter_view(conn, matter_id, user_id)


def update_matter(
    matter_id: str,
    user: Optional[Dict[str, Any]],
    *,
    name: Optional[str] = None,
    client_ref: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """Change name/client_ref/description/status (lead or org owner/admin). Audits field names only."""
    user_id = _require_user_id(user)
    requested: Dict[str, str] = {}
    if name is not None:
        requested["name"] = _clean_field(name, "name", MAX_NAME_LENGTH, required=True)
    if client_ref is not None:
        requested["client_ref"] = _clean_field(client_ref, "client_ref", MAX_CLIENT_REF_LENGTH)
    if description is not None:
        requested["description"] = _clean_field(description, "description", MAX_DESCRIPTION_LENGTH)
    if status is not None:
        status_value = _clean(status).lower()
        if status_value not in MATTER_STATUSES:
            raise _error(400, "invalid_matter", "status must be 'active' or 'archived'.")
        requested["status"] = status_value
    matter_value = _clean(matter_id)
    with db_service.auth_db_transaction() as conn:
        matter = _require_manager(conn, matter_value, user_id)["matter"]
        changes = {key: value for key, value in requested.items() if matter.get(key) != value}
        if changes.get("status") == "archived" and matter["is_default"]:
            raise _error(409, "default_matter", "The default matter cannot be archived.")
        if changes:
            # Column names come from the fixed whitelist above, never from the request.
            assignments = ", ".join(f"{column} = ?" for column in changes)
            conn.execute(
                f"UPDATE matters SET {assignments}, updated_at = ? WHERE id = ?",
                (*changes.values(), _now_iso(), matter_value),
            )
            details: Dict[str, Any] = {"fields": sorted(changes)}
            if "status" in changes:
                details["status"] = changes["status"]
            audit.write_event(
                conn,
                actor_user_id=user_id,
                action="matter.archived" if changes.get("status") == "archived" else "matter.updated",
                target_type="matter",
                target_id=matter_value,
                matter_id=matter_value,
                org_id=matter["org_id"],
                details=details,
            )
        return _matter_view(conn, matter_value, user_id)


def archive_matter(matter_id: str, user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Soft delete: ``status="archived"``. Idempotent; nothing is removed."""
    return update_matter(matter_id, user, status="archived")


# ── members ──────────────────────────────────────────────────────────────────


def _list_members(conn: sqlite3.Connection, matter_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT mm.user_id, mm.role, mm.added_by, mm.created_at, u.email, u.username
        FROM matter_members mm LEFT JOIN users u ON u.id = mm.user_id
        WHERE mm.matter_id = ?
        ORDER BY CASE mm.role WHEN 'lead' THEN 0 WHEN 'member' THEN 1 ELSE 2 END, mm.created_at, mm.user_id
        """,
        (matter_id,),
    ).fetchall()
    return [
        {
            "user_id": row["user_id"],
            "email": row["email"] or "",
            "username": row["username"] or "",
            "role": row["role"],
            "added_by": row["added_by"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def list_members(matter_id: str, user: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Members with email/username, leads first (members and org owners/admins may list)."""
    user_id = _require_user_id(user)
    matter_value = _clean(matter_id)
    with closing(_connect()) as conn:
        _require_reader(conn, matter_value, user_id)
        return _list_members(conn, matter_value)


def _resolve_user(conn: sqlite3.Connection, user_id: Optional[str], email: Optional[str]) -> Dict[str, str]:
    user_value, email_value = _clean(user_id), _clean(email).lower()
    if user_value:
        row = conn.execute("SELECT id, email, username FROM users WHERE id = ?", (user_value,)).fetchone()
    elif email_value:
        row = conn.execute("SELECT id, email, username FROM users WHERE lower(email) = ?", (email_value,)).fetchone()
    else:
        raise _error(400, "invalid_member", "Give the user_id or email of the person to add.")
    if row is None:
        raise _error(404, "user_not_found", "No registered user matches.")
    return {"id": row["id"], "email": row["email"] or "", "username": row["username"] or ""}


def _lead_count(conn: sqlite3.Connection, matter_id: str) -> int:
    row = conn.execute("SELECT COUNT(*) FROM matter_members WHERE matter_id = ? AND role = 'lead'", (matter_id,)).fetchone()
    return int(row[0] or 0)


def add_member(
    matter_id: str,
    user: Optional[Dict[str, Any]],
    *,
    member_user_id: Optional[str] = None,
    email: Optional[str] = None,
    role: str = "member",
) -> Dict[str, Any]:
    """Add a registered user, or change an existing member's role (lead or org owner/admin only)."""
    actor_id = _require_user_id(user)
    role_value = _matter_role(role)
    matter_value = _clean(matter_id)
    with db_service.auth_db_transaction() as conn:
        matter = _require_manager(conn, matter_value, actor_id)["matter"]
        target = _resolve_user(conn, member_user_id, email)
        previous = _member_role(conn, matter_value, target["id"])
        if previous != role_value:
            if previous == "lead" and _lead_count(conn, matter_value) <= 1:
                raise _error(409, "last_lead", "A matter needs at least one lead; add another lead first.")
            if previous is None:
                _insert_member(conn, matter_value, target["id"], role_value, added_by=actor_id, now=_now_iso())
            else:
                conn.execute(
                    "UPDATE matter_members SET role = ? WHERE matter_id = ? AND user_id = ?",
                    (role_value, matter_value, target["id"]),
                )
            details: Dict[str, Any] = {"role": role_value}
            if previous:
                details["previous_role"] = previous
            audit.write_event(
                conn,
                actor_user_id=actor_id,
                action="matter.member_added",
                target_type="user",
                target_id=target["id"],
                matter_id=matter_value,
                org_id=matter["org_id"],
                details=details,
            )
        members = _list_members(conn, matter_value)
    return next(member for member in members if member["user_id"] == target["id"])


def remove_member(matter_id: str, user: Optional[Dict[str, Any]], member_user_id: str) -> Dict[str, Any]:
    """Remove a member (lead or org owner/admin; anyone may remove themselves). Keeps one lead."""
    actor_id = _require_user_id(user)
    target_id = _clean(member_user_id)
    if not target_id:
        raise _error(400, "invalid_member", "Give the user_id of the member to remove.")
    matter_value = _clean(matter_id)
    with db_service.auth_db_transaction() as conn:
        access = _access(conn, matter_value, actor_id)
        leaving_self = target_id == actor_id and access["role"] is not None
        if not access["can_manage"] and not leaving_self:
            _require_manager(conn, matter_value, actor_id)
        previous = _member_role(conn, matter_value, target_id)
        if previous is None:
            raise _error(404, "member_not_found", "That user is not a member of this matter.")
        if previous == "lead" and _lead_count(conn, matter_value) <= 1:
            raise _error(409, "last_lead", "A matter needs at least one lead; add another lead first.")
        conn.execute("DELETE FROM matter_members WHERE matter_id = ? AND user_id = ?", (matter_value, target_id))
        audit.write_event(
            conn,
            actor_user_id=actor_id,
            action="matter.member_removed",
            target_type="user",
            target_id=target_id,
            matter_id=matter_value,
            org_id=access["matter"]["org_id"],
            details={"role": previous},
        )
    return {"user_id": target_id, "role": previous, "removed": True}


# ── document links ───────────────────────────────────────────────────────────


def _insert_link(conn: sqlite3.Connection, matter_id: str, document_id: str, *, added_by: str) -> bool:
    cursor = conn.execute(
        "INSERT OR IGNORE INTO matter_documents (matter_id, document_id, added_by, added_at) VALUES (?, ?, ?, ?)",
        (matter_id, document_id, added_by, _now_iso()),
    )
    return cursor.rowcount == 1


def matter_document_links(matter_id: str) -> List[Dict[str, str]]:
    """``{"document_id", "added_by", "added_at"}`` rows of a matter, most recently added first."""
    matter_value = _clean(matter_id)
    if not matter_value:
        return []
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT document_id, added_by, added_at FROM matter_documents WHERE matter_id = ? ORDER BY added_at DESC, document_id",
            (matter_value,),
        ).fetchall()
    return [{"document_id": row["document_id"], "added_by": row["added_by"], "added_at": row["added_at"]} for row in rows]


def matter_document_ids(matter_id: str) -> List[str]:
    """Ids of the documents linked to a matter (no permission check: callers check membership)."""
    return [link["document_id"] for link in matter_document_links(matter_id)]


def document_matter_ids(document_id: str) -> List[str]:
    document_value = _clean(document_id)
    if not document_value:
        return []
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT matter_id FROM matter_documents WHERE document_id = ? ORDER BY added_at, matter_id",
            (document_value,),
        ).fetchall()
    return [row[0] for row in rows]


def user_matter_ids(user_id: str) -> List[str]:
    """Ids of every matter (active or archived) the user is a member of."""
    user_value = _clean(user_id)
    if not user_value:
        return []
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT matter_id FROM matter_members WHERE user_id = ? ORDER BY created_at, matter_id",
            (user_value,),
        ).fetchall()
    return [row[0] for row in rows]


def user_matter_document_ids(user_id: str) -> Set[str]:
    """Ids of every document linked to any matter the user is a member of."""
    user_value = _clean(user_id)
    if not user_value:
        return set()
    with closing(_connect()) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT md.document_id FROM matter_members mm
            JOIN matter_documents md ON md.matter_id = mm.matter_id
            WHERE mm.user_id = ?
            """,
            (user_value,),
        ).fetchall()
    return {row[0] for row in rows}


def is_document_in_user_matters(user_id: str, document_id: str) -> bool:
    user_value, document_value = _clean(user_id), _clean(document_id)
    if not user_value or not document_value:
        return False
    with closing(_connect()) as conn:
        row = conn.execute(
            """
            SELECT 1 FROM matter_documents md
            JOIN matter_members mm ON mm.matter_id = md.matter_id
            WHERE md.document_id = ? AND mm.user_id = ?
            LIMIT 1
            """,
            (document_value, user_value),
        ).fetchone()
    return row is not None


def attach_documents(matter_id: str, document_ids: List[str], user: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Link existing documents to a matter, all or none.

    The caller needs role ``member`` in an active matter and must be able to open each document
    under the owner/admin rules: membership of another matter is not enough, so a document only
    crosses into a new matter by its owner's hand (matters stay walled off from each other).
    """
    from services.document_access import _find_document_entry, _owner_rules_allow_access

    actor_id = _require_user_id(user)
    matter_value = _clean(matter_id)
    wanted = list(dict.fromkeys(_clean(item) for item in document_ids if _clean(item)))
    if not wanted:
        raise _error(400, "invalid_document", "document_id is required.")
    with closing(_connect()) as conn:
        _require_active(_require_role(conn, matter_value, actor_id, "member")["matter"])
    for document_id in wanted:
        entry = _find_document_entry(document_id)
        if entry is None:
            raise _error(404, "document_not_found", "No document found for this id.")
        if not _owner_rules_allow_access(dict(user or {}), entry):
            raise _error(403, "document_forbidden", "Only the document's owner can add it to a matter.")
    results: List[Dict[str, Any]] = []
    with db_service.auth_db_transaction() as conn:
        matter = _require_role(conn, matter_value, actor_id, "member")["matter"]
        _require_active(matter)
        for document_id in wanted:
            attached = _insert_link(conn, matter_value, document_id, added_by=actor_id)
            if attached:
                audit.write_event(
                    conn,
                    actor_user_id=actor_id,
                    action="document.attached",
                    target_type="document",
                    target_id=document_id,
                    matter_id=matter_value,
                    org_id=matter["org_id"],
                )
            results.append({"matter_id": matter_value, "document_id": document_id, "attached": attached})
    return results


def attach_document(matter_id: str, document_id: str, user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Link one existing document to a matter (see ``attach_documents`` for the rules)."""
    if not _clean(document_id):
        raise _error(400, "invalid_document", "document_id is required.")
    return attach_documents(matter_id, [document_id], user)[0]


def detach_document(matter_id: str, document_id: str, user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Unlink a document from a matter (role ``member``, active matter). The document stays."""
    actor_id = _require_user_id(user)
    matter_value, document_value = _clean(matter_id), _clean(document_id)
    with db_service.auth_db_transaction() as conn:
        matter = _require_role(conn, matter_value, actor_id, "member")["matter"]
        _require_active(matter)
        cursor = conn.execute(
            "DELETE FROM matter_documents WHERE matter_id = ? AND document_id = ?",
            (matter_value, document_value),
        )
        if cursor.rowcount == 0:
            raise _error(404, "document_not_in_matter", "This document is not part of the matter.")
        audit.write_event(
            conn,
            actor_user_id=actor_id,
            action="document.detached",
            target_type="document",
            target_id=document_value,
            matter_id=matter_value,
            org_id=matter["org_id"],
        )
    return {"matter_id": matter_value, "document_id": document_value, "detached": True}


def detach_deleted_document(document_id: str, *, actor_user_id: str, details: Optional[Dict[str, Any]] = None) -> List[str]:
    """After a document is deleted: drop every matter link and audit ``document.deleted`` per matter."""
    document_value = _clean(document_id)
    if not document_value:
        return []
    with db_service.auth_db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT md.matter_id, m.org_id FROM matter_documents md
            LEFT JOIN matters m ON m.id = md.matter_id
            WHERE md.document_id = ?
            ORDER BY md.added_at, md.matter_id
            """,
            (document_value,),
        ).fetchall()
        conn.execute("DELETE FROM matter_documents WHERE document_id = ?", (document_value,))
        targets = [(row["matter_id"], row["org_id"]) for row in rows] or [(None, None)]
        for matter_id, org_id in targets:
            audit.write_event(
                conn,
                actor_user_id=actor_user_id,
                action="document.deleted",
                target_type="document",
                target_id=document_value,
                matter_id=matter_id,
                org_id=org_id,
                details=details,
            )
    return [row["matter_id"] for row in rows]


# ── uploads into a matter ────────────────────────────────────────────────────


def result_document_id(result: Any) -> str:
    """The document id of an ingestion result (``result["document"]["id"]``), or ""."""
    if not isinstance(result, dict):
        return ""
    return _clean((result.get("document") or {}).get("id"))


def upload_audit_details(result: Any, *, job_id: Optional[str] = None) -> Dict[str, Any]:
    """Counts and flags from an ingestion result for ``document.uploaded`` (never text)."""
    result = result if isinstance(result, dict) else {}
    details: Dict[str, Any] = {"duplicate": bool(result.get("duplicate"))}
    chunk_count = (result.get("stats") or {}).get("chunk_count")
    if isinstance(chunk_count, int) and not isinstance(chunk_count, bool):
        details["chunk_count"] = chunk_count
    status = (result.get("document") or {}).get("status")
    if isinstance(status, str) and status.isidentifier():
        details["status"] = status
    if job_id:
        details["job_id"] = str(job_id)
    return details


def link_uploaded_document(
    matter_id: str,
    document_id: str,
    *,
    actor_user_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """Link a just-ingested (or deduplicated) document to its matter and audit ``document.uploaded``.

    The caller checked membership (role ``member``) before ingesting. Returns True when a new
    link was created.
    """
    matter_value, document_value = _clean(matter_id), _clean(document_id)
    if not matter_value or not document_value:
        return False
    with db_service.auth_db_transaction() as conn:
        matter = _fetch_matter(conn, matter_value)
        if matter is None:
            raise _error(404, "matter_not_found", "No matter found for this id.")
        attached = _insert_link(conn, matter_value, document_value, added_by=actor_user_id)
        audit.write_event(
            conn,
            actor_user_id=actor_user_id,
            action="document.uploaded",
            target_type="document",
            target_id=document_value,
            matter_id=matter_value,
            org_id=matter["org_id"],
            details=details,
        )
    return attached


def remember_pending_upload(
    job_id: str,
    *,
    matter_id: str,
    user_id: str,
    linked_document_id: str = "",
) -> None:
    """Record which matter an async upload job belongs to until its result is linked.

    ``ingestion_jobs`` keeps jobs in memory and exposes no completion callback, so the link is
    made when the finished job is first read (``link_finished_upload``). Entries older than
    ``PENDING_UPLOAD_TTL_SECONDS`` are dropped.
    """
    job_value = _clean(job_id)
    if not job_value:
        return
    now = time.time()
    with _PENDING_UPLOADS_LOCK:
        for stale in [key for key, item in _PENDING_UPLOADS.items() if now - item["created"] > PENDING_UPLOAD_TTL_SECONDS]:
            _PENDING_UPLOADS.pop(stale, None)
        _PENDING_UPLOADS[job_value] = {
            "matter_id": _clean(matter_id),
            "user_id": _clean(user_id),
            "linked_document_id": _clean(linked_document_id),
            "created": now,
        }


def pending_upload(job_id: str) -> Optional[Dict[str, Any]]:
    with _PENDING_UPLOADS_LOCK:
        item = _PENDING_UPLOADS.get(_clean(job_id))
        return dict(item) if item else None


def link_finished_upload(job: Optional[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    """Link the document of a finished async upload job to its matter, once.

    Returns ``{"matter_id", "document_id"}`` when this call linked it; None when the job is still
    running, failed, was rejected, or was not uploaded into a matter (or already handled).
    """
    if not isinstance(job, dict):
        return None
    job_id = _clean(job.get("job_id"))
    status = _clean(job.get("status"))
    if not job_id or status not in _TERMINAL_JOB_STATUSES:
        return None
    with _PENDING_UPLOADS_LOCK:
        pending = _PENDING_UPLOADS.pop(job_id, None)
    if pending is None:
        return None
    result = job.get("result")
    document_id = result_document_id(result)
    if status != "completed" or not document_id or (isinstance(result, dict) and result.get("rejected")):
        return None
    if document_id == pending.get("linked_document_id"):
        return None
    try:
        link_uploaded_document(
            pending["matter_id"],
            document_id,
            actor_user_id=pending["user_id"],
            details=upload_audit_details(result, job_id=job_id),
        )
    except Exception:
        with _PENDING_UPLOADS_LOCK:
            _PENDING_UPLOADS.setdefault(job_id, pending)
        raise
    return {"matter_id": pending["matter_id"], "document_id": document_id}


# ── migration ────────────────────────────────────────────────────────────────


def _all_users(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone() is None:
        return []
    rows = conn.execute("SELECT id, email, username FROM users ORDER BY created_at, id").fetchall()
    return [{"id": row["id"], "email": row["email"], "username": row["username"]} for row in rows]


def migrate_existing_documents(*, dry_run: bool = False) -> Dict[str, Any]:
    """Give every user a personal workspace and file each owned legacy document into its owner's
    default matter unless it already belongs to a matter.

    Idempotent. Runs in one transaction; ``dry_run`` rolls it back, so its counts are exactly
    what a real run would do and nothing (not even the schema) is written.
    """
    entries = document_registry.list_entries(valid_only=False)
    counts: Dict[str, Any] = {
        "users": 0,
        "workspaces_created": 0,
        "workspaces_existing": 0,
        "documents_seen": 0,
        "documents_attached": 0,
        "documents_already_in_matter": 0,
        "documents_without_owner": 0,
        "documents_owner_unknown": 0,
    }
    conn = db_service.connect_auth_db_sync(ensure_schema=False)
    try:
        conn.execute("BEGIN IMMEDIATE")
        db_service.create_matter_schema_sync(conn)
        workspaces: Dict[str, Dict[str, str]] = {}
        for user in _all_users(conn):
            counts["users"] += 1
            workspace, created = _ensure_personal_workspace(conn, user, actor_user_id=SYSTEM_ACTOR)
            workspaces[str(user["id"])] = workspace
            counts["workspaces_created" if created else "workspaces_existing"] += 1
        for entry in entries:
            document_id = _clean(entry.get("document_id"))
            if not document_id:
                continue
            counts["documents_seen"] += 1
            owner_user_id = _clean(entry.get("owner_user_id"))
            if not owner_user_id:
                counts["documents_without_owner"] += 1
                continue
            workspace = workspaces.get(owner_user_id)
            if workspace is None:
                counts["documents_owner_unknown"] += 1
                continue
            if conn.execute("SELECT 1 FROM matter_documents WHERE document_id = ? LIMIT 1", (document_id,)).fetchone():
                counts["documents_already_in_matter"] += 1
                continue
            _insert_link(conn, workspace["matter_id"], document_id, added_by=SYSTEM_ACTOR)
            audit.write_event(
                conn,
                actor_user_id=SYSTEM_ACTOR,
                action="document.attached",
                target_type="document",
                target_id=document_id,
                matter_id=workspace["matter_id"],
                org_id=workspace["org_id"],
                details={"migration": True},
            )
            counts["documents_attached"] += 1
        conn.execute("ROLLBACK" if dry_run else "COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    counts["dry_run"] = bool(dry_run)
    return counts
