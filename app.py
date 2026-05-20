"""FastAPI entrypoint for the ESG QLoRA extraction service."""

from __future__ import annotations

import os
import io
import time
import base64
import random
import queue
import secrets
import string
import threading
import uuid
import json
import re
import bcrypt
import jwt
import aiosqlite
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Depends, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

# ── Auth config ──────────────────────────────────────────────────────────────
_DEFAULT_JWT_SECRET = "esg-demo-secret-change-in-prod"
_APP_ENV = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).strip().lower()
_JWT_SECRET = os.getenv("JWT_SECRET", _DEFAULT_JWT_SECRET).strip() or _DEFAULT_JWT_SECRET
_JWT_ALGORITHM = "HS256"
_TOKEN_MINUTES = 60 * 24  # 1 day
_DB_PATH = os.getenv("AUTH_DB_PATH", os.path.join(os.path.dirname(__file__), "auth.db"))
_FEEDBACK_DB_PATH = os.getenv(
    "CAUSALGRAPH_DB_PATH",
    os.path.join(os.path.dirname(__file__), "backend", "causalgraph.db"),
)
_CORS_ALLOW_ORIGINS_RAW = os.getenv("CORS_ALLOW_ORIGINS") or os.getenv("CORS_ALLOWED_ORIGINS", "")
_security = HTTPBearer(auto_error=False)
_CLEANUP_EXECUTOR = ThreadPoolExecutor(max_workers=1)
_ENTITY_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9&.-]*")
_ENTITY_OF_PATTERN = re.compile(
    r"\b(?:of|for|about|by|from|at|on)\s+([A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3})"
)
_ENTITY_POSSESSIVE_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){0,3})['’]s\b")
_ENTITY_ACRONYM_PATTERN = re.compile(r"\b[A-Z]{2,8}\b")
_ENTITY_TITLE_PHRASE_PATTERN = re.compile(r"\b([A-Z][A-Za-z0-9&.-]*(?:\s+[A-Z][A-Za-z0-9&.-]*){1,4})\b")
_ENTITY_SPLIT_PATTERN = re.compile(r"[^A-Za-z0-9&]+")
_ENTITY_ALIAS_MAP: Dict[str, Tuple[str, ...]] = {
    "american flight": ("american airlines", "american airline", "aa"),
    "american flights": ("american airlines", "american airline", "aa"),
    "american airline": ("american airlines", "aa"),
    "american airlines": ("american airline", "aa"),
}
_DOCUMENT_ENTITY_TERMS_CACHE: Dict[str, Tuple[float, set[str]]] = {}
_ENTITY_STOP_WORDS = {
    "a",
    "about",
    "and",
    "annual",
    "be",
    "can",
    "company",
    "across",
    "compare",
    "could",
    "document",
    "esg",
    "effects",
    "explain",
    "for",
    "from",
    "give",
    "governance",
    "i",
    "in",
    "inc",
    "is",
    "its",
    "know",
    "limited",
    "llc",
    "ltd",
    "me",
    "of",
    "on",
    "please",
    "price",
    "report",
    "reports",
    "responsibility",
    "share",
    "show",
    "something",
    "strategy",
    "summarise",
    "summarize",
    "sustainability",
    "tell",
    "that",
    "these",
    "this",
    "those",
    "the",
    "to",
    "want",
    "what",
    "would",
    "year",
}


def _is_production_like_env(value: Optional[str] = None) -> bool:
    env = str(value if value is not None else _APP_ENV).strip().lower()
    return env in {"prod", "production", "staging"}


def _validate_startup_security_config(*, app_env: Optional[str] = None, jwt_secret: Optional[str] = None) -> None:
    env = str(app_env if app_env is not None else _APP_ENV).strip().lower()
    secret = str(jwt_secret if jwt_secret is not None else _JWT_SECRET).strip()
    if not _is_production_like_env(env):
        if secret == _DEFAULT_JWT_SECRET:
            print("[startup] WARNING: using demo JWT_SECRET; set a strong JWT_SECRET before deployment.")
        return

    if not secret or secret == _DEFAULT_JWT_SECRET:
        raise RuntimeError("JWT_SECRET must be set to a strong non-default value when APP_ENV=production/staging.")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters when APP_ENV=production/staging.")


def _validate_startup_cors_config(*, app_env: Optional[str] = None, cors_allow_origins_raw: Optional[str] = None) -> None:
    if not _is_production_like_env(app_env):
        return
    raw = _CORS_ALLOW_ORIGINS_RAW if cors_allow_origins_raw is None else str(cors_allow_origins_raw)
    if not raw.strip():
        raise RuntimeError("CORS_ALLOW_ORIGINS must be set when APP_ENV=production/staging.")


def _parse_cors_origins(raw: Optional[str]) -> List[str]:
    origins = [item.strip() for item in str(raw or "").split(",") if item.strip()]
    if origins:
        return origins
    return [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    ]


_CORS_ALLOW_ORIGINS = _parse_cors_origins(_CORS_ALLOW_ORIGINS_RAW)
_CORS_ALLOW_ORIGIN_REGEX = os.getenv(
    "CORS_ALLOW_ORIGIN_REGEX",
    r"https://.*\.ngrok-free\.app|https://.*\.ngrok\.app",
).strip() or None


async def _get_db():
    async with aiosqlite.connect(_DB_PATH) as db:
        yield db


async def _init_auth_db():
    Path(_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_invite_codes (
                id TEXT PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                created_by_user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                used_by_user_id TEXT
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS admin_invite_codes_expires_at_idx ON admin_invite_codes(expires_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS admin_invite_codes_used_at_idx ON admin_invite_codes(used_at)")
        await _ensure_column(db, "users", "role", "TEXT NOT NULL DEFAULT 'user'")
        await db.execute("UPDATE users SET role = 'user' WHERE role IS NULL OR lower(role) NOT IN ('admin', 'user')")
        admin_emails = sorted(_admin_email_set())
        if admin_emails:
            placeholders = ",".join("?" for _ in admin_emails)
            await db.execute(
                f"UPDATE users SET role = 'admin' WHERE lower(email) IN ({placeholders})",
                tuple(admin_emails),
            )
        await db.execute("DELETE FROM admin_invite_codes WHERE datetime(expires_at) <= datetime('now') OR used_at IS NOT NULL")
        await db.commit()


async def _init_feedback_db():
    Path(_FEEDBACK_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(_FEEDBACK_DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS answer_feedback (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       TEXT NOT NULL,
                session_id    TEXT NOT NULL,
                message_id    TEXT NOT NULL,
                query         TEXT NOT NULL,
                answer        TEXT NOT NULL,
                rating        TEXT NOT NULL,
                reason_tags   TEXT,
                reason_text   TEXT,
                sources_json  TEXT,
                timings_json  TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_feedback_rating ON answer_feedback(rating, created_at)")
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_feedback_user_message ON answer_feedback(user_id, message_id)")
        await db.commit()


async def _ensure_column(db: aiosqlite.Connection, table_name: str, column_name: str, definition: str) -> None:
    cursor = await db.execute(f"PRAGMA table_info({table_name})")
    rows = await cursor.fetchall()
    existing = {str(row[1]) for row in rows}
    if column_name not in existing:
        await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def _normalize_role(role: str) -> str:
    value = str(role or "").strip().lower()
    return value if value in {"admin", "user"} else "user"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_in_minutes_iso(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _check_pw(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _make_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_MINUTES),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: aiosqlite.Connection = Depends(_get_db),
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_token(credentials.credentials)
    user_id = payload.get("sub")
    cursor = await db.execute(
        "SELECT id, email, username, role, created_at FROM users WHERE id = ?", (user_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="User not found")
    return {"id": row[0], "email": row[1], "username": row[2], "role": _normalize_role(row[3]), "created_at": row[4]}


async def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: aiosqlite.Connection = Depends(_get_db),
):
    if credentials is None:
        return None
    try:
        payload = _decode_token(credentials.credentials)
    except HTTPException:
        return None
    user_id = payload.get("sub")
    cursor = await db.execute(
        "SELECT id, email, username, role, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "username": row[2], "role": _normalize_role(row[3]), "created_at": row[4]}


def _admin_email_set() -> set[str]:
    return {
        email.strip().lower()
        for email in os.getenv("ADMIN_EMAILS", "").split(",")
        if email.strip()
    }


def _is_local_request(request: Request) -> bool:
    if request.headers.get("x-forwarded-for") or request.headers.get("x-forwarded-host"):
        return False
    host_header = request.headers.get("host", "")
    if "ngrok" in host_header:
        return False
    host = request.client.host if request.client else ""
    return host in {"127.0.0.1", "::1", "localhost"}


async def require_admin(current_user: dict = Depends(get_current_user)):
    if _normalize_role(current_user.get("role", "")) == "admin":
        return current_user
    raise HTTPException(status_code=403, detail="Admin access required")


# ── Captcha ──────────────────────────────────────────────────────────────────
_CAPTCHA_STORE: Dict[str, Tuple[str, float]] = {}
_CAPTCHA_TTL = 300  # 5 minutes


def _gen_captcha_image(code: str) -> bytes:
    width, height = 160, 60
    img = Image.new("RGB", (width, height), color=(245, 245, 250))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
    except Exception:
        font = ImageFont.load_default()
    for i, char in enumerate(code):
        x = 18 + i * 30 + random.randint(-3, 3)
        y = 12 + random.randint(-6, 6)
        color = (random.randint(20, 80), random.randint(20, 80), random.randint(80, 150))
        draw.text((x, y), char, fill=color, font=font)
    for _ in range(5):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=(180, 180, 200), width=1)
    for _ in range(40):
        x, y = random.randint(0, width - 1), random.randint(0, height - 1)
        draw.point((x, y), fill=(150, 150, 180))
    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _cleanup_captchas():
    now = time.time()
    for key in [k for k, (_, exp) in _CAPTCHA_STORE.items() if exp < now]:
        _CAPTCHA_STORE.pop(key, None)


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    captcha_id: str
    captcha_code: str
    role: str = "user"
    admin_invite_code: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AdminInviteCreateRequest(BaseModel):
    ttl_minutes: int = 5


async def _consume_admin_invite(code: str, user_id: str, db: aiosqlite.Connection) -> None:
    invite_code = str(code or "").strip()
    if not invite_code:
        raise HTTPException(status_code=400, detail="Admin registration requires an invitation code")
    cursor = await db.execute(
        """
        SELECT id, expires_at, used_at
        FROM admin_invite_codes
        WHERE code = ?
        """,
        (invite_code,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid admin invitation code")
    if row[2]:
        raise HTTPException(status_code=400, detail="Admin invitation code has already been used")
    expires_at = datetime.fromisoformat(str(row[1]))
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Admin invitation code has expired")

    await db.execute(
        """
        UPDATE admin_invite_codes
        SET used_at = ?, used_by_user_id = ?
        WHERE id = ?
        """,
        (_utc_now_iso(), user_id, row[0]),
    )

from ai_service.extractor import extract_esg
from ai_service.schemas import EsgExtractionRequest, EsgExtractionResponse
from chat_memory_service import RedisUnavailableError, chat_memory_service
from configs.settings import (
    CHUNK_DIR,
    EMBEDDING_FALLBACK_DIM,
    GRAPH_DIR,
    INGESTION_ENABLED,
    NEO4J_AUTO_SYNC,
    VECTOR_DIR,
    VECTOR_STORE_PROVIDER,
    neo4j_configured,
)
import document_registry
from graph.causal_reasoning import CausalReasoner
from graph.neo4j_store import assert_neo4j_ready, get_neo4j_store, neo4j_sdk_available
from admin_audit import (
    admin_overview,
    get_upload,
    get_latest_upload_by_document_id,
    init_admin_db,
    list_latest_uploads_by_document_id,
    list_uploads,
    mark_upload_deleted,
    record_upload_cleanup,
    update_upload_metadata,
)
from ingestion_jobs import get_ingestion_job, start_ingestion_job
from pipeline_runtime import (
    delete_uploaded_document,
    ingest_uploaded_document,
    load_registered_document,
    rebuild_document_graph,
    summarize_registered_document,
)
from rag.bm25_index import warm_bm25_index
from rag.embeddings import embedding_backend_is_real, get_embedding_backend, get_embedding_model
from rag.rag_pipeline import answer_question, stream_answer_question
from scripts.run_pdf_pipeline import run_pdf_pipeline


app = FastAPI(title="ESG QLoRA Extraction API", version="1.0.0")

_APP_ROOT = Path(__file__).resolve().parent
_KG_VIEW_TEMPLATE = _APP_ROOT / "kg_view" / "templates" / "index.html"
_KG_VIEW_STATIC = _APP_ROOT / "kg_view" / "static"


def _assert_embedding_dim_matches_pinecone() -> None:
    if VECTOR_STORE_PROVIDER != "pinecone":
        return
    get_embedding_model()
    if not embedding_backend_is_real():
        print(
            f"[startup] WARNING: embedding backend={get_embedding_backend()} "
            f"(dim={EMBEDDING_FALLBACK_DIM}) does NOT match Pinecone 1024-d index. "
            "Vector retrieval will be skipped; BM25-only fallback active."
        )


def _ensure_neo4j_schema_startup() -> None:
    try:
        from graph.neo4j_store import get_neo4j_store, neo4j_enabled

        if neo4j_enabled():
            store = get_neo4j_store()
            if store is not None:
                store.setup_schema()
                print("[startup] Neo4j schema (indexes + fulltext) ensured.")
    except Exception as exc:
        print(f"[startup] Neo4j schema setup skipped: {type(exc).__name__}: {exc}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ALLOW_ORIGINS,
    allow_origin_regex=_CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/kg-static", StaticFiles(directory=str(_KG_VIEW_STATIC)), name="kg-static")


@app.on_event("startup")
async def startup():
    _validate_startup_security_config()
    _validate_startup_cors_config()
    await _init_auth_db()
    await _init_feedback_db()
    init_admin_db()
    warm_bm25_index()
    _ensure_neo4j_schema_startup()
    _assert_embedding_dim_matches_pinecone()


@app.get("/auth/captcha")
async def get_captcha():
    _cleanup_captchas()
    code = "".join(random.choices(string.digits, k=4))
    captcha_id = str(uuid.uuid4())
    _CAPTCHA_STORE[captcha_id] = (code, time.time() + _CAPTCHA_TTL)
    img_b64 = base64.b64encode(_gen_captcha_image(code)).decode()
    return {"captcha_id": captcha_id, "image": f"data:image/png;base64,{img_b64}"}


@app.post("/auth/register")
async def register(req: RegisterRequest, db: aiosqlite.Connection = Depends(_get_db)):
    _cleanup_captchas()
    stored = _CAPTCHA_STORE.pop(req.captcha_id, None)
    if not stored or stored[0] != req.captcha_code.strip():
        raise HTTPException(status_code=400, detail="Invalid or expired captcha")
    cursor = await db.execute("SELECT id FROM users WHERE email = ?", (req.email,))
    if await cursor.fetchone():
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    role = _normalize_role(req.role)
    if role == "admin":
        await _consume_admin_invite(req.admin_invite_code or "", user_id, db)
    await db.execute(
        "INSERT INTO users (id, email, username, password_hash, role, created_at) VALUES (?,?,?,?,?,?)",
        (user_id, req.email, req.username, _hash_pw(req.password), role, _utc_now_iso()),
    )
    await db.commit()
    token = _make_token(user_id, req.email)
    return {
        "token": token,
        "user": {
            "id": user_id,
            "email": req.email,
            "username": req.username,
            "role": role,
            "created_at": _utc_now_iso(),
        },
    }


@app.post("/auth/login")
async def login(req: LoginRequest, db: aiosqlite.Connection = Depends(_get_db)):
    cursor = await db.execute(
        "SELECT id, email, username, password_hash, role, created_at FROM users WHERE email = ?", (req.email,)
    )
    row = await cursor.fetchone()
    if not row or not _check_pw(req.password, row[3]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = _make_token(row[0], row[1])
    return {
        "token": token,
        "user": {
            "id": row[0],
            "email": row[1],
            "username": row[2],
            "role": _normalize_role(row[4]),
            "created_at": row[5],
        },
    }


@app.get("/auth/me")
async def me(current_user: dict = Depends(get_current_user)):
    return current_user


@app.get("/admin/overview")
async def admin_dashboard_overview(
    days: int = Query(default=14, ge=1, le=90),
    current_user: dict = Depends(require_admin),
):
    return JSONResponse(content=admin_overview(days=days))


@app.get("/admin/uploads")
async def admin_uploads(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_admin),
):
    return JSONResponse(content={"uploads": list_uploads(limit=limit, offset=offset)})


@app.post("/admin/invite-codes")
async def create_admin_invite_code(
    request: AdminInviteCreateRequest,
    current_user: dict = Depends(require_admin),
    db: aiosqlite.Connection = Depends(_get_db),
):
    ttl_minutes = max(1, min(int(request.ttl_minutes), 5))
    code = f"ADM-{secrets.token_urlsafe(8).replace('-', '').replace('_', '')[:10].upper()}"
    invite_id = str(uuid.uuid4())
    now = _utc_now_iso()
    expires_at = _utc_in_minutes_iso(ttl_minutes)
    await db.execute(
        """
        INSERT INTO admin_invite_codes (
            id, code, created_by_user_id, created_at, expires_at, used_at, used_by_user_id
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL)
        """,
        (invite_id, code, str(current_user.get("id") or ""), now, expires_at),
    )
    await db.commit()
    return {
        "invite_code": code,
        "expires_at": expires_at,
        "ttl_minutes": ttl_minutes,
        "single_use": True,
    }


class AdminUploadUpdateRequest(BaseModel):
    title: Optional[str] = None
    domain: Optional[str] = None
    source_type: Optional[str] = None
    source: Optional[str] = None


@app.patch("/admin/uploads/{job_id}")
async def admin_update_upload(
    job_id: str,
    request: AdminUploadUpdateRequest,
    current_user: dict = Depends(require_admin),
):
    updates = request.dict(exclude_unset=True)
    updated = update_upload_metadata(job_id, updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Upload record not found")
    document_id = str(updated.get("document_id") or "").strip()
    if document_id:
        document_registry.update_metadata(document_id, updates)
    return JSONResponse(content={"upload": updated})


@app.delete("/admin/uploads/{job_id}")
async def admin_delete_upload(
    job_id: str,
    reason: str = Query(default=""),
    current_user: dict = Depends(require_admin),
):
    upload = get_upload(job_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload record not found")
    status = str(upload.get("status") or "")
    if status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Running or queued uploads cannot be deleted until processing finishes")
    deleted = mark_upload_deleted(
        job_id,
        deleted_by=str(current_user.get("email") or current_user.get("username") or ""),
        reason=reason,
        status="deleted",
        cleanup_status="cleanup_skipped" if status == "rejected" else "cleanup_pending",
        cleanup_detail="Rejected upload has no indexed resources." if status == "rejected" else "Cleanup queued.",
    )
    if deleted is None:
        raise HTTPException(status_code=404, detail="Upload record not found")
    if status != "rejected":
        _CLEANUP_EXECUTOR.submit(
            _cleanup_deleted_upload,
            job_id,
            upload,
            str(current_user.get("email") or current_user.get("username") or ""),
            reason,
        )
    return JSONResponse(
        content={
            "upload": deleted,
            "cleanup": {
                "queued": status != "rejected",
                "warnings": [],
                "neo4j": {"enabled": False, "deleted": False, "reason": "background_cleanup_queued"},
            },
        }
    )


def _cleanup_deleted_upload(job_id: str, upload: Dict[str, Any], deleted_by: str, reason: str) -> None:
    try:
        cleanup = delete_uploaded_document(upload)
        document_id = str(upload.get("document_id") or "").strip()
        if document_id:
            document_registry.remove(document_id)
        warnings = list(cleanup.get("warnings") or [])
        neo4j_result = cleanup.get("neo4j") or {}
        if neo4j_result.get("enabled") and neo4j_result.get("deleted") is False and neo4j_result.get("reason") not in {
            "missing_document_id",
        }:
            warnings.append(f"neo4j: {neo4j_result.get('reason') or 'delete_not_confirmed'}")
        if warnings:
            record_upload_cleanup(
                job_id,
                cleanup_status="cleanup_failed",
                cleanup_detail=f"Cleanup warnings: {'; '.join(warnings[:5])}",
                status="deleted_with_warnings",
            )
        else:
            deleted_count = len(cleanup.get("deleted_paths") or [])
            record_upload_cleanup(
                job_id,
                cleanup_status="cleanup_completed",
                cleanup_detail=f"Deleted {deleted_count} local path(s). Neo4j: {neo4j_result.get('reason') or neo4j_result.get('deleted')}.",
                status="deleted",
            )
    except Exception as exc:
        record_upload_cleanup(
            job_id,
            cleanup_status="cleanup_failed",
            cleanup_detail=f"Cleanup failed: {type(exc).__name__}: {exc}",
            status="deleted_with_warnings",
        )


class RagAskRequest(BaseModel):
    question: str
    top_k: int = 5
    history: List[Dict[str, Any]] = []
    session_id: Optional[str] = None
    document_ids: List[str] = []
    preferred_document_id: Optional[str] = None
    document_group: Optional[str] = None
    source_type: Optional[str] = None
    domain: Optional[str] = None
    # Deprecated: legacy intent selector (ask | predict | graph). The pipeline
    # now drives behavior entirely off `reasoning_mode` (flash | deep). Kept on
    # the schema so older clients don't fail validation; the value is ignored.
    mode: Optional[str] = "ask"
    reasoning_mode: Optional[str] = "flash"


def _normalize_entity_token(value: str) -> str:
    return str(value or "").strip(" .,!?:;()[]{}\"'’").lower()


def _filtered_entity_tokens(value: str) -> List[str]:
    normalized = _ENTITY_SPLIT_PATTERN.sub(" ", str(value or ""))
    tokens = [_normalize_entity_token(match.group(0)) for match in _ENTITY_TOKEN_PATTERN.finditer(normalized)]
    return [token for token in tokens if len(token) >= 2 and token not in _ENTITY_STOP_WORDS]


def _append_entity_term(terms: List[str], value: str) -> None:
    normalized = " ".join(_filtered_entity_tokens(value))
    if normalized and normalized not in terms:
        terms.append(normalized)


def _alias_terms_for_entity(tokens: List[str], joined: str) -> List[str]:
    keys = {joined, *tokens}
    if "american" in tokens and any(token in {"flight", "flights", "airline", "airlines"} for token in tokens):
        keys.add("american flight")
    aliases: List[str] = []
    for key in keys:
        aliases.extend(_ENTITY_ALIAS_MAP.get(key, ()))
    return aliases


def _terms_from_document_value(value: str) -> set[str]:
    tokens = _filtered_entity_tokens(value)
    terms = set(tokens)
    if 1 < len(tokens) <= 16:
        max_size = min(4, len(tokens))
        for size in range(2, max_size + 1):
            for index in range(0, len(tokens) - size + 1):
                terms.add(" ".join(tokens[index:index + size]))
    return terms


def _graph_entity_terms(graph_path: str) -> set[str]:
    if not graph_path:
        return set()
    path = Path(graph_path)
    if not path.exists() or not path.is_file():
        return set()

    try:
        mtime = path.stat().st_mtime
    except OSError:
        return set()

    cache_key = str(path.resolve())
    cached = _DOCUMENT_ENTITY_TERMS_CACHE.get(cache_key)
    if cached and cached[0] == mtime:
        return set(cached[1])

    terms: set[str] = set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _DOCUMENT_ENTITY_TERMS_CACHE[cache_key] = (mtime, terms)
        return terms

    nodes = payload.get("nodes") if isinstance(payload, dict) else []
    if not isinstance(nodes, list):
        nodes = []
    for node in nodes[:500]:
        if not isinstance(node, dict):
            continue
        for key in ("id", "name", "label", "title"):
            terms.update(_terms_from_document_value(str(node.get(key) or "")))
        properties = node.get("properties") or node.get("metadata") or {}
        if isinstance(properties, dict):
            for key in ("name", "display_name", "label", "title"):
                terms.update(_terms_from_document_value(str(properties.get(key) or "")))

    _DOCUMENT_ENTITY_TERMS_CACHE[cache_key] = (mtime, terms)
    return set(terms)


def _extract_query_entity_terms(question: str) -> List[str]:
    text = str(question or "")
    terms: List[str] = []

    def add_phrase(phrase: str) -> None:
        tokens = _filtered_entity_tokens(phrase)
        if not tokens:
            return
        # Keep both phrase-level and token-level keys so "Apple Inc." can match
        # either "apple inc" or an uploaded file named "apple-report.pdf".
        joined = " ".join(tokens)
        candidates = [joined, *tokens, *_alias_terms_for_entity(tokens, joined)]
        for value in candidates:
            if value and value not in terms:
                _append_entity_term(terms, value)

    for pattern in (_ENTITY_OF_PATTERN, _ENTITY_POSSESSIVE_PATTERN, _ENTITY_TITLE_PHRASE_PATTERN):
        for match in pattern.finditer(text):
            add_phrase(match.group(1))

    lowered = text.lower()
    for alias in _ENTITY_ALIAS_MAP:
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            add_phrase(alias)

    for match in _ENTITY_ACRONYM_PATTERN.finditer(text):
        token = _normalize_entity_token(match.group(0))
        if token and token not in _ENTITY_STOP_WORDS and token not in terms:
            terms.append(token)

    return terms


def _document_entity_terms(entry: Dict[str, Any]) -> set[str]:
    values = [
        entry.get("document_id", ""),
        entry.get("title", ""),
        entry.get("source", ""),
    ]
    paths = entry.get("paths") or {}
    values.extend([paths.get("processed_text", ""), paths.get("chunks", ""), paths.get("graph", ""), paths.get("vector_store", "")])

    terms: set[str] = set()
    for value in values:
        terms.update(_terms_from_document_value(str(value or "")))
    terms.update(_graph_entity_terms(str(paths.get("graph") or "")))
    return terms


def _scope_document_ids_for_query(question: str, entries: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
    query_terms = _extract_query_entity_terms(question)
    if not query_terms:
        return [], []

    phrase_terms = {term for term in query_terms if " " in term}
    alias_terms = {
        term for term in query_terms
        if " " not in term and any(term in aliases for aliases in _ENTITY_ALIAS_MAP.values())
    }
    phrase_matched_ids: List[str] = []
    alias_matched_ids: List[str] = []
    fallback_matched_ids: List[str] = []
    for entry in entries:
        document_id = str(entry.get("document_id") or "").strip()
        if not document_id:
            continue
        document_terms = _document_entity_terms(entry)
        if phrase_terms and any(term in document_terms for term in phrase_terms):
            phrase_matched_ids.append(document_id)
        elif alias_terms and any(term in document_terms for term in alias_terms):
            alias_matched_ids.append(document_id)
        elif any(term in document_terms for term in query_terms):
            fallback_matched_ids.append(document_id)

    return phrase_matched_ids or alias_matched_ids or fallback_matched_ids, query_terms


def _question_with_recent_user_context(question: str, history: Optional[List[Dict[str, Any]]]) -> str:
    recent_user_turns: List[str] = []
    for item in reversed(history or []):
        if str(item.get("role") or "").strip().lower() != "user":
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        recent_user_turns.append(content)
        if len(recent_user_turns) >= 2:
            break
    parts = [*reversed(recent_user_turns), str(question or "").strip()]
    return "\n".join(part for part in parts if part)


def _no_accessible_documents_response() -> Dict[str, Any]:
    return {"error_response": JSONResponse(
        status_code=403,
        content={"answer": "", "sources": [], "error": "no_accessible_documents", "message": "No accessible documents for this account."},
    )}


def _resolve_rag_request_context(request: RagAskRequest, current_user: Optional[dict]) -> Dict[str, Any]:
    effective_document_ids = [str(item).strip() for item in (request.document_ids or []) if str(item).strip()]
    preferred_document_id = str(request.preferred_document_id or "").strip() or None
    entity_scope_miss = False
    entity_scope_terms: List[str] = []
    history = request.history
    memory_backend = "disabled"
    if request.session_id and current_user:
        try:
            history = chat_memory_service.get_recent_history(
                user_id=str(current_user["id"]),
                session_id=str(request.session_id),
            )
            memory_backend = "redis"
        except RedisUnavailableError:
            memory_backend = "disabled"
    scope_question = _question_with_recent_user_context(request.question, history)
    if current_user and not _is_admin_user(current_user):
        retrievable_entries = _retrievable_registry_entries(current_user)
        allowed_ids = {str(entry.get("document_id") or "").strip() for entry in retrievable_entries if str(entry.get("document_id") or "").strip()}
        broad_retrievable_scope = False
        if effective_document_ids or preferred_document_id:
            scoped_ids, scoped_terms = _scope_document_ids_for_query(scope_question, retrievable_entries)
            scoped_allowed_ids = sorted(set(scoped_ids) & allowed_ids)
            requested_ids = set(effective_document_ids)
            if preferred_document_id:
                requested_ids.add(preferred_document_id)
            if scoped_allowed_ids and requested_ids and requested_ids.isdisjoint(scoped_allowed_ids):
                effective_document_ids = scoped_allowed_ids
                preferred_document_id = None
                entity_scope_terms = scoped_terms
        if preferred_document_id:
            if preferred_document_id not in allowed_ids:
                return _no_accessible_documents_response()
            if not effective_document_ids:
                effective_document_ids = [preferred_document_id]
        if effective_document_ids:
            effective_document_ids = [doc_id for doc_id in effective_document_ids if doc_id in allowed_ids]
        else:
            scoped_ids, entity_scope_terms = _scope_document_ids_for_query(scope_question, retrievable_entries)
            if scoped_ids:
                effective_document_ids = sorted(set(scoped_ids) & allowed_ids)
            elif entity_scope_terms and not preferred_document_id:
                global_ids = {
                    str(entry.get("document_id") or "").strip()
                    for entry in retrievable_entries
                    if _is_global_entry(entry) and str(entry.get("document_id") or "").strip()
                }
                if global_ids:
                    # Global KB should remain searchable even when the target entity
                    # is not encoded in the document title/source metadata.
                    effective_document_ids = sorted(global_ids & allowed_ids)
                else:
                    entity_scope_miss = True
                    effective_document_ids = []
            else:
                # Broad user search is already safely constrained by owner/global
                # metadata filters in the vector store. Do not enumerate every
                # accessible document ID here; large $in filters can make Pinecone
                # slow or exceed request limits.
                broad_retrievable_scope = bool(allowed_ids)
                effective_document_ids = []
        if not effective_document_ids:
            if not entity_scope_miss and not broad_retrievable_scope:
                return _no_accessible_documents_response()
    elif current_user and _is_admin_user(current_user) and not effective_document_ids and not preferred_document_id:
        scoped_ids, entity_scope_terms = _scope_document_ids_for_query(scope_question, _retrievable_registry_entries(current_user))
        if scoped_ids:
            effective_document_ids = scoped_ids
        elif entity_scope_terms:
            entity_scope_miss = True
    elif not current_user:
        public_entries = [entry for entry in _collect_document_entries() if _can_retrieve_entry(None, entry)]
        public_ids = {str(entry.get("document_id") or "").strip() for entry in public_entries if str(entry.get("document_id") or "").strip()}
        if preferred_document_id:
            if preferred_document_id not in public_ids:
                return _no_accessible_documents_response()
            effective_document_ids = [preferred_document_id]
        elif effective_document_ids:
            effective_document_ids = [doc_id for doc_id in effective_document_ids if doc_id in public_ids]
            if not effective_document_ids:
                return _no_accessible_documents_response()
        else:
            scoped_ids, entity_scope_terms = _scope_document_ids_for_query(scope_question, public_entries)
            if scoped_ids:
                effective_document_ids = scoped_ids
            elif entity_scope_terms:
                entity_scope_miss = True
            else:
                # Anonymous requests do not carry owner_user_id, so public/global
                # access must be enforced by explicit document IDs.
                effective_document_ids = sorted(public_ids)
        if not effective_document_ids and not entity_scope_miss:
            return _no_accessible_documents_response()

    filters = {
        "document_ids": effective_document_ids,
        "preferred_document_id": preferred_document_id,
        "document_group": request.document_group,
        "source_type": request.source_type,
        "domain": request.domain,
    }
    if current_user and not _is_admin_user(current_user):
        filters["owner_user_id"] = str(current_user.get("id") or "")
    if entity_scope_miss:
        filters["entity_scope_miss"] = True
        filters["entity_scope_terms"] = entity_scope_terms

    return {
        "filters": filters,
        "history": history,
        "memory_backend": memory_backend,
        "user_id": str(current_user["id"]) if current_user else None,
        "error_response": None,
    }


class PipelinePdfRequest(BaseModel):
    pdf_path: str
    name: str


class ManualDocumentRequest(BaseModel):
    title: str
    content: str
    domain: str = "general"
    source: str = ""
    source_type: str = ""


class RebuildDocumentGraphRequest(BaseModel):
    id: str
    title: str
    domain: str = "general"
    source: str = ""
    document_group: str = "user_upload"
    source_type: str = ""
    processed_text_path: str = ""
    chunks_path: str = ""
    extractions_path: str = ""
    graph_path: str = ""
    vector_store_path: str = ""


class ChatSessionCreateRequest(BaseModel):
    title: str = ""
    selected_document_id: str = ""
    mode: str = "ask"


class ChatSessionUpdateRequest(BaseModel):
    title: Optional[str] = None
    selected_document_id: Optional[str] = None
    mode: Optional[str] = None


class ChatSessionMessageRequest(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


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


@app.post("/feedback")
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
        async with aiosqlite.connect(_FEEDBACK_DB_PATH) as db:
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


@app.get("/admin/feedback/recent")
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

    async with aiosqlite.connect(_FEEDBACK_DB_PATH) as db:
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


@app.get("/chat/sessions")
async def list_chat_sessions(current_user: dict = Depends(get_current_user)):
    try:
        sessions = chat_memory_service.list_sessions(user_id=str(current_user["id"]))
        return JSONResponse(content={"sessions": sessions, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        return JSONResponse(
            content={"sessions": [], "warning": str(exc), "memory_backend": "disabled"},
        )


@app.post("/chat/sessions")
async def create_chat_session(
    request: ChatSessionCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        session = chat_memory_service.create_session(
            user_id=str(current_user["id"]),
            title=request.title,
            selected_document_id=request.selected_document_id,
            mode=request.mode,
        )
        return JSONResponse(content={"session": session, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        return JSONResponse(
            status_code=503,
            content={"error": "chat_memory_unavailable", "message": str(exc), "memory_backend": "disabled"},
        )


@app.get("/chat/sessions/{session_id}")
async def get_chat_session(session_id: str, current_user: dict = Depends(get_current_user)):
    try:
        payload = chat_memory_service.get_session(user_id=str(current_user["id"]), session_id=session_id, include_messages=True)
        return JSONResponse(content={**payload, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        status = 404 if "not found" in str(exc).lower() else 503
        return JSONResponse(
            status_code=status,
            content={"error": "chat_session_unavailable", "message": str(exc), "memory_backend": "disabled"},
        )


@app.patch("/chat/sessions/{session_id}")
async def update_chat_session(
    session_id: str,
    request: ChatSessionUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        session = chat_memory_service.update_session(
            user_id=str(current_user["id"]),
            session_id=session_id,
            title=request.title,
            selected_document_id=request.selected_document_id,
            mode=request.mode,
        )
        return JSONResponse(content={"session": session, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        status = 404 if "not found" in str(exc).lower() else 503
        return JSONResponse(
            status_code=status,
            content={"error": "chat_session_update_failed", "message": str(exc), "memory_backend": "disabled"},
        )


@app.post("/chat/sessions/{session_id}/messages")
async def append_chat_message(
    session_id: str,
    request: ChatSessionMessageRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        session = chat_memory_service.append_message(
            user_id=str(current_user["id"]),
            session_id=session_id,
            message=request.model_dump(),
        )
        return JSONResponse(content={"session": session, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        status = 404 if "not found" in str(exc).lower() else 503
        return JSONResponse(
            status_code=status,
            content={"error": "chat_message_append_failed", "message": str(exc), "memory_backend": "disabled"},
        )


@app.delete("/chat/sessions/{session_id}")
async def delete_chat_session(session_id: str, current_user: dict = Depends(get_current_user)):
    try:
        chat_memory_service.delete_session(user_id=str(current_user["id"]), session_id=session_id)
        return JSONResponse(content={"deleted": True, "memory_backend": "redis"})
    except RedisUnavailableError as exc:
        status = 404 if "not found" in str(exc).lower() else 503
        return JSONResponse(
            status_code=status,
            content={"error": "chat_session_delete_failed", "message": str(exc), "memory_backend": "disabled"},
        )


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
    if not graph_path or not chunks_path or not vector_store_path:
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


def _is_admin_user(user: Optional[Dict[str, Any]]) -> bool:
    return _normalize_role((user or {}).get("role", "")) == "admin"


def _is_global_entry(entry: Dict[str, Any]) -> bool:
    group = str(entry.get("document_group") or "").strip().lower()
    visibility = str(entry.get("visibility_scope") or "").strip().lower()
    return group in {"global_kb", "global", "shared"} or visibility == "global"


def _can_access_entry(user: Dict[str, Any], entry: Dict[str, Any]) -> bool:
    if _is_admin_user(user):
        return True
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


class Neo4jQuestionRequest(BaseModel):
    question: str
    hops: int = 2
    limit: int = 10


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


def _ensure_ingestion_enabled() -> None:
    if not INGESTION_ENABLED:
        raise HTTPException(status_code=503, detail="Document ingestion is disabled in this deployment.")


@app.get("/kg-view", response_class=HTMLResponse)
async def kg_view(current_user: dict = Depends(require_admin)) -> HTMLResponse:
    if not _KG_VIEW_TEMPLATE.exists():
        raise HTTPException(status_code=404, detail="KG view template not found")
    return HTMLResponse(
        _KG_VIEW_TEMPLATE.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/kg-api/filters")
async def kg_filters(document_id: Optional[str] = None, current_user: dict = Depends(require_admin)):
    try:
        store = get_neo4j_store()
        if store is None:
            return JSONResponse(
                status_code=400,
                content={"error": "neo4j_unavailable", "message": "Neo4j is not configured or unavailable."},
            )
        return JSONResponse(content=store.get_visualization_filters(document_id=document_id))
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "kg_filters_failed", "message": str(exc)},
        )


@app.get("/kg-api/graph")
async def kg_graph(
    document_id: Optional[str] = None,
    years: List[str] = Query(default=[]),
    companies: List[str] = Query(default=[]),
    esg_domains: List[str] = Query(default=[]),
    limit: int = 1000,
    current_user: dict = Depends(require_admin),
):
    try:
        store = get_neo4j_store()
        if store is None:
            return JSONResponse(
                status_code=400,
                content={"error": "neo4j_unavailable", "message": "Neo4j is not configured or unavailable."},
            )
        return JSONResponse(
            content=store.get_visualization_graph(
                years=years or None,
                companies=companies or None,
                esg_domains=esg_domains or None,
                limit=limit,
                document_id=document_id,
            )
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "kg_graph_failed", "message": str(exc)},
        )


@app.get("/kg-api/stats")
async def kg_stats(document_id: Optional[str] = None, current_user: dict = Depends(require_admin)):
    try:
        store = get_neo4j_store()
        if store is None:
            return JSONResponse(
                status_code=400,
                content={"error": "neo4j_unavailable", "message": "Neo4j is not configured or unavailable."},
            )
        return JSONResponse(content=store.get_visualization_stats(document_id=document_id))
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "kg_stats_failed", "message": str(exc)},
        )


@app.get("/graph/neo4j/status")
async def neo4j_status(current_user: dict = Depends(require_admin)):
    if not neo4j_sdk_available():
        return JSONResponse(content={"enabled": False, "connected": False, "reason": "neo4j_sdk_missing"})
    if not neo4j_configured():
        return JSONResponse(content={"enabled": False, "connected": False, "reason": "neo4j_not_configured"})
    try:
        assert_neo4j_ready()
        store = get_neo4j_store()
        if store is None:
            return JSONResponse(content={"enabled": False, "connected": False, "reason": "neo4j_unavailable"})
        status = store.ping()
        status["auto_sync"] = NEO4J_AUTO_SYNC
        status["stats"] = store.get_stats()
        return JSONResponse(content=status)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"enabled": True, "connected": False, "reason": "neo4j_error", "message": str(exc)},
        )


@app.get("/graph/neo4j/entity/{entity_name}")
async def neo4j_entity(entity_name: str, limit: int = 20, current_user: dict = Depends(require_admin)):
    try:
        store = get_neo4j_store()
        if store is None:
            return JSONResponse(
                status_code=400,
                content={"error": "neo4j_unavailable", "message": "Neo4j is not configured or the SDK is missing."},
            )
        return JSONResponse(content=store.get_entity(entity_name, limit=limit))
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "neo4j_entity_failed", "message": str(exc)},
        )


@app.get("/graph/neo4j/subgraph")
async def neo4j_subgraph(entity: str, hops: int = 2, limit: int = 50, current_user: dict = Depends(require_admin)):
    try:
        store = get_neo4j_store()
        if store is None:
            return JSONResponse(
                status_code=400,
                content={"error": "neo4j_unavailable", "message": "Neo4j is not configured or the SDK is missing."},
            )
        return JSONResponse(content=store.get_subgraph(entity=entity, hops=hops, limit=limit))
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "neo4j_subgraph_failed", "message": str(exc)},
        )


@app.post("/graph/neo4j/question")
async def neo4j_question(request: Neo4jQuestionRequest, current_user: dict = Depends(require_admin)):
    try:
        store = get_neo4j_store()
        if store is None:
            return JSONResponse(
                status_code=400,
                content={"error": "neo4j_unavailable", "message": "Neo4j is not configured or the SDK is missing."},
            )
        return JSONResponse(
            content=store.find_relevant_subgraph(
                question=request.question,
                hops=request.hops,
                limit=request.limit,
            )
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "neo4j_question_failed", "message": str(exc)},
        )


@app.get("/graph/causal/backward")
async def causal_backward(entity: str, depth: int = 3, limit: int = 20):
    try:
        store = get_neo4j_store()
        if store is None:
            return JSONResponse(status_code=400, content={"error": "neo4j_unavailable", "message": "Neo4j is not configured or unavailable."})
        return JSONResponse(content=CausalReasoner(store).backward_chain(entity, depth=depth, limit=limit))
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": "causal_backward_failed", "message": str(exc)})


@app.get("/graph/causal/forward")
async def causal_forward(entity: str, depth: int = 3, limit: int = 20):
    try:
        store = get_neo4j_store()
        if store is None:
            return JSONResponse(status_code=400, content={"error": "neo4j_unavailable", "message": "Neo4j is not configured or unavailable."})
        return JSONResponse(content=CausalReasoner(store).forward_chain(entity, depth=depth, limit=limit))
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": "causal_forward_failed", "message": str(exc)})


@app.get("/graph/causal/path")
async def causal_path(source: str, target: str, max_depth: int = 5):
    try:
        store = get_neo4j_store()
        if store is None:
            return JSONResponse(status_code=400, content={"error": "neo4j_unavailable", "message": "Neo4j is not configured or unavailable."})
        return JSONResponse(content=CausalReasoner(store).shortest_path(source, target, max_depth=max_depth))
    except Exception as exc:
        return JSONResponse(status_code=500, content={"error": "causal_path_failed", "message": str(exc)})


@app.post("/extract", response_model=EsgExtractionResponse)
async def extract(request: EsgExtractionRequest):
    try:
        result = extract_esg(request.text)
        return EsgExtractionResponse(**result)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "entities": [],
                "relations": [],
                "error": "extraction_failed",
                "message": str(exc),
            },
        )


@app.post("/rag/ask")
async def rag_ask(request: RagAskRequest, current_user: Optional[dict] = Depends(get_optional_current_user)):
    try:
        context = _resolve_rag_request_context(request, current_user)
        if context["error_response"] is not None:
            return context["error_response"]
        result = answer_question(
            request.question,
            top_k=request.top_k,
            history=context["history"],
            retrieval_filters=context["filters"],
            mode=request.mode or "ask",
            reasoning_mode=request.reasoning_mode or "flash",
            user_id=context["user_id"],
        )
        result["memory_backend"] = context["memory_backend"]
        if request.session_id:
            result["session_id"] = request.session_id
        return JSONResponse(content=result)
    except FileNotFoundError as exc:
        return JSONResponse(
            status_code=400,
            content={"answer": "", "sources": [], "error": "vector_store_missing", "message": str(exc)},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"answer": "", "sources": [], "error": "rag_failed", "message": str(exc)},
        )


def _encode_sse_event(event: Dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _build_streaming_response(
    *,
    request: RagAskRequest,
    stream_factory,
    fallback_factory,
) -> StreamingResponse:
    event_queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()

    def _producer() -> None:
        try:
            try:
                iterator = stream_factory()
                for event in iterator:
                    event_queue.put(event)
            except NotImplementedError:
                event_queue.put({"type": "done", "payload": fallback_factory()})
        except Exception as exc:
            event_queue.put({"type": "error", "message": str(exc)})
        finally:
            event_queue.put(None)

    def _event_stream():
        thread = threading.Thread(target=_producer, daemon=True)
        thread.start()
        while True:
            try:
                item = event_queue.get(timeout=15.0)
            except queue.Empty:
                yield ": heartbeat\n\n"
                continue
            if item is None:
                break
            yield _encode_sse_event(item)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/rag/ask/stream")
async def rag_ask_stream(request: RagAskRequest, current_user: Optional[dict] = Depends(get_optional_current_user)):
    try:
        context = _resolve_rag_request_context(request, current_user)
        if context["error_response"] is not None:
            return context["error_response"]

        def _stream_factory():
            for event in stream_answer_question(
                request.question,
                top_k=request.top_k,
                history=context["history"],
                retrieval_filters=context["filters"],
                mode=request.mode or "ask",
                reasoning_mode=request.reasoning_mode or "flash",
                user_id=context["user_id"],
            ):
                if event.get("type") == "done":
                    payload = dict(event.get("payload") or {})
                    payload["memory_backend"] = context["memory_backend"]
                    if request.session_id:
                        payload["session_id"] = request.session_id
                    yield {"type": "done", "payload": payload}
                else:
                    if event.get("type") == "meta":
                        payload = dict(event.get("payload") or {})
                        if request.session_id:
                            payload["session_id"] = request.session_id
                        yield {"type": "meta", "payload": payload}
                    else:
                        yield event

        def _fallback_factory():
            result = answer_question(
                request.question,
                top_k=request.top_k,
                history=context["history"],
                retrieval_filters=context["filters"],
                mode=request.mode or "ask",
                reasoning_mode=request.reasoning_mode or "flash",
                user_id=context["user_id"],
            )
            result["memory_backend"] = context["memory_backend"]
            if request.session_id:
                result["session_id"] = request.session_id
            return result

        return _build_streaming_response(
            request=request,
            stream_factory=_stream_factory,
            fallback_factory=_fallback_factory,
        )
    except FileNotFoundError as exc:
        return JSONResponse(
            status_code=400,
            content={"answer": "", "sources": [], "error": "vector_store_missing", "message": str(exc)},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"answer": "", "sources": [], "error": "rag_failed", "message": str(exc)},
        )


@app.post("/pipeline/pdf")
async def pipeline_pdf(request: PipelinePdfRequest, current_user: dict = Depends(get_current_user)):
    _ensure_ingestion_enabled()
    try:
        result = run_pdf_pipeline(request.pdf_path, request.name)
        return JSONResponse(content=result)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(exc)},
        )


@app.get("/documents")
async def list_documents(current_user: dict = Depends(get_current_user)):
    try:
        audit_index = list_latest_uploads_by_document_id()
        entries = [entry for entry in _collect_document_entries() if _can_access_entry(current_user, entry)]
        documents: List[Dict[str, Any]] = []
        for entry in entries:
            document_id = str(entry.get("document_id") or "").strip()
            if not document_id:
                continue
            audit = audit_index.get(document_id)
            if audit and str(audit.get("status") or "") in {"deleted", "deleted_with_warnings"}:
                continue
            try:
                documents.append(summarize_registered_document(entry, audit=audit))
            except Exception as exc:
                print(f"[documents] Summary load failed for {document_id}: {type(exc).__name__}: {exc}")
        return JSONResponse(content={"documents": documents})
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "document_list_failed", "message": str(exc)},
        )


@app.post("/documents/upload")
async def upload_document(
    title: str = Form(""),
    domain: str = Form("general"),
    source_type: str = Form(""),
    source: str = Form(""),
    content: str = Form(""),
    file: Optional[UploadFile] = File(default=None),
    current_user: dict = Depends(get_current_user),
):
    _ensure_ingestion_enabled()
    try:
        file_bytes = await file.read() if file is not None else None
        is_admin = _is_admin_user(current_user)
        document_group = "global_kb" if is_admin else "user_private"
        visibility_scope = "global" if is_admin else "private"
        result = ingest_uploaded_document(
            title=title or (file.filename if file else "Uploaded document"),
            domain=domain,
            source=source,
            source_type=source_type,
            content=content,
            filename=file.filename if file else None,
            file_bytes=file_bytes,
            document_group=document_group,
            owner_user_id=str(current_user.get("id") or ""),
            visibility_scope=visibility_scope,
        )
        return JSONResponse(content=result)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "document_upload_failed", "message": str(exc)},
        )


@app.post("/documents/upload-async")
async def upload_document_async(
    title: str = Form(""),
    domain: str = Form("general"),
    source_type: str = Form(""),
    source: str = Form(""),
    content: str = Form(""),
    file: Optional[UploadFile] = File(default=None),
    current_user: dict = Depends(get_current_user),
):
    _ensure_ingestion_enabled()
    try:
        assert_neo4j_ready()
        file_bytes = await file.read() if file is not None else None
        is_admin = _is_admin_user(current_user)
        document_group = "global_kb" if is_admin else "user_private"
        visibility_scope = "global" if is_admin else "private"
        job = start_ingestion_job(
            title=title or (file.filename if file else "Uploaded document"),
            domain=domain,
            source=source,
            source_type=source_type,
            content=content,
            filename=file.filename if file else None,
            file_bytes=file_bytes,
            document_group=document_group,
            uploader=current_user,
            owner_user_id=str(current_user.get("id") or ""),
            visibility_scope=visibility_scope,
        )
        return JSONResponse(content=job)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "document_upload_failed", "message": str(exc)},
        )


@app.get("/documents/jobs/{job_id}")
async def get_document_job(job_id: str, current_user: dict = Depends(get_current_user)):
    upload = get_upload(job_id)
    if upload is not None and not _is_admin_user(current_user):
        uploader = upload.get("uploader") or {}
        if str(uploader.get("id") or "").strip() != str(current_user.get("id") or "").strip():
            return JSONResponse(
                status_code=403,
                content={"error": "job_forbidden", "message": "You do not have access to this ingestion job."},
            )
    job = get_ingestion_job(job_id)
    if job is None:
        return JSONResponse(
            status_code=404,
            content={"error": "job_not_found", "message": f"No ingestion job found for id {job_id}."},
        )
    return JSONResponse(content=job)


@app.get("/documents/{document_id}")
async def get_document(document_id: str, current_user: dict = Depends(get_current_user)):
    try:
        entry = document_registry.get_entry(document_id, valid_only=True)
        audit = get_latest_upload_by_document_id(document_id)
        if entry is None and audit is not None:
            entry = _entry_from_upload(audit)
        if entry is None:
            return JSONResponse(
                status_code=404,
                content={"error": "document_not_found", "message": f"No document found for id {document_id}."},
            )
        if not _can_access_entry(current_user, entry):
            return JSONResponse(
                status_code=403,
                content={"error": "document_forbidden", "message": "You do not have access to this document."},
            )
        if audit and str(audit.get("status") or "") in {"deleted", "deleted_with_warnings"}:
            return JSONResponse(
                status_code=404,
                content={"error": "document_not_found", "message": f"No document found for id {document_id}."},
            )
        return JSONResponse(content={"document": load_registered_document(entry, audit=audit)})
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "document_load_failed", "message": str(exc)},
        )


@app.delete("/documents/{document_id}")
async def delete_document(document_id: str, current_user: dict = Depends(get_current_user)):
    try:
        entry = document_registry.get_entry(document_id, valid_only=False)
        audit = get_latest_upload_by_document_id(document_id)
        if entry is None and audit is not None:
            entry = _entry_from_upload(audit)
        if entry is None:
            return JSONResponse(
                status_code=404,
                content={"error": "document_not_found", "message": f"No document found for id {document_id}."},
            )
        if not _can_access_entry(current_user, entry):
            return JSONResponse(
                status_code=403,
                content={"error": "document_forbidden", "message": "You do not have access to this document."},
            )
        if not _is_admin_user(current_user):
            entry_owner = str(entry.get("owner_user_id") or "").strip()
            if entry_owner != str(current_user.get("id") or "").strip():
                return JSONResponse(
                    status_code=403,
                    content={"error": "document_forbidden", "message": "Only admins can delete global knowledge base documents."},
                )
        if audit and str(audit.get("status") or "") in {"deleted", "deleted_with_warnings"}:
            return JSONResponse(
                status_code=404,
                content={"error": "document_not_found", "message": f"No document found for id {document_id}."},
            )

        upload = audit or {
            "document_id": document_id,
            "status": "completed",
            "paths": {
                "processed_text_path": str((entry.get("paths") or {}).get("processed_text") or ""),
                "chunks_path": str((entry.get("paths") or {}).get("chunks") or ""),
                "extractions_path": str((entry.get("paths") or {}).get("extractions") or ""),
                "graph_path": str((entry.get("paths") or {}).get("graph") or ""),
                "vector_store_path": str((entry.get("paths") or {}).get("vector_store") or ""),
            },
        }

        if audit:
            mark_upload_deleted(
                audit["job_id"],
                deleted_by=str(current_user.get("email") or current_user.get("username") or ""),
                reason="user_deleted",
                status="deleted",
                cleanup_status="cleanup_pending",
                cleanup_detail="User deletion in progress.",
            )

        cleanup = delete_uploaded_document(upload)
        document_registry.remove(document_id)

        warnings = list(cleanup.get("warnings") or [])
        neo4j_result = cleanup.get("neo4j") or {}
        if neo4j_result.get("enabled") and neo4j_result.get("deleted") is False and neo4j_result.get("reason") not in {
            "missing_document_id",
        }:
            warnings.append(f"neo4j: {neo4j_result.get('reason') or 'delete_not_confirmed'}")

        if audit:
            if warnings:
                record_upload_cleanup(
                    audit["job_id"],
                    cleanup_status="cleanup_failed",
                    cleanup_detail=f"Cleanup warnings: {'; '.join(warnings[:5])}",
                    status="deleted_with_warnings",
                )
            else:
                deleted_count = len(cleanup.get("deleted_paths") or [])
                record_upload_cleanup(
                    audit["job_id"],
                    cleanup_status="cleanup_completed",
                    cleanup_detail=f"Deleted {deleted_count} local path(s). Neo4j: {neo4j_result.get('reason') or neo4j_result.get('deleted')}.",
                    status="deleted",
                )

        return JSONResponse(
            content={
                "deleted": True,
                "document_id": document_id,
                "cleanup": cleanup,
            }
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"error": "document_delete_failed", "message": str(exc)},
        )


@app.post("/documents/ingest-text")
async def ingest_text_document(request: ManualDocumentRequest, current_user: dict = Depends(get_current_user)):
    _ensure_ingestion_enabled()
    try:
        is_admin = _is_admin_user(current_user)
        result = ingest_uploaded_document(
            title=request.title,
            domain=request.domain,
            source=request.source,
            source_type=request.source_type,
            content=request.content,
            document_group="global_kb" if is_admin else "user_private",
            owner_user_id=str(current_user.get("id") or ""),
            visibility_scope="global" if is_admin else "private",
        )
        return JSONResponse(content=result)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "document_ingest_failed", "message": str(exc)},
        )


@app.post("/documents/rebuild-graph")
async def rebuild_graph(request: RebuildDocumentGraphRequest, current_user: dict = Depends(get_current_user)):
    _ensure_ingestion_enabled()
    try:
        result = rebuild_document_graph(request.model_dump())
        return JSONResponse(content=result)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "document_rebuild_failed", "message": str(exc)},
        )
