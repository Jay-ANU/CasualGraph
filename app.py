"""FastAPI entrypoint: settings validation, middleware, startup hooks and router registration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

load_dotenv(Path(__file__).resolve().parent / ".env")

from admin_audit import init_admin_db  # noqa: E402
from api.routers.admin import router as admin_router  # noqa: E402
from api.routers.auth import router as auth_router  # noqa: E402
from api.routers.chat import router as chat_router  # noqa: E402
from api.routers.documents import router as documents_router  # noqa: E402
from api.routers.feedback import router as feedback_router  # noqa: E402
from api.routers.graph import router as graph_router  # noqa: E402
from api.routers.memory import router as memory_router  # noqa: E402
from api.routers.rag import router as rag_router  # noqa: E402
from api.routers.system import router as system_router  # noqa: E402
from configs.settings import EMBEDDING_FALLBACK_DIM, VECTOR_STORE_PROVIDER  # noqa: E402
from rag.bm25_index import warm_bm25_index  # noqa: E402
from rag.embeddings import embedding_backend_is_real, get_embedding_backend, get_embedding_model  # noqa: E402
from services.auth import _APP_ENV, _DEFAULT_JWT_SECRET, _JWT_SECRET, _is_production_like_env  # noqa: E402
from services.db import _init_auth_db, _init_feedback_db  # noqa: E402

# Roughly the declaration order of the pre-split app.py; no route pattern overlaps across routers.
ROUTERS = (
    system_router,
    auth_router,
    admin_router,
    feedback_router,
    chat_router,
    memory_router,
    graph_router,
    rag_router,
    documents_router,
)

# Phase 1 routers are delivered by parallel work packages. Whichever modules exist are
# included, so no work package has to edit this file. Each module exposes ``router``.
OPTIONAL_ROUTER_MODULES = (
    "api.routers.document_content",  # clauses, canonical text, original file (WP1-A)
    "api.routers.redaction",  # de-identification review and confirmation (WP1-B)
    "api.routers.matters",  # matters, membership, audit (WP1-C)
)


def _optional_routers():
    import importlib

    found = []
    for module_name in OPTIONAL_ROUTER_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            raise
        found.append(module.router)
    return tuple(found)


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


_CORS_ALLOW_ORIGINS = _parse_cors_origins(os.getenv("CORS_ALLOW_ORIGINS", ""))
_CORS_ALLOW_ORIGIN_REGEX = os.getenv(
    "CORS_ALLOW_ORIGIN_REGEX",
    r"https://.*\.ngrok-free\.app|https://.*\.ngrok\.app",
).strip() or None


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


async def startup():
    _validate_startup_security_config()
    await _init_auth_db()
    await _init_feedback_db()
    init_admin_db()
    warm_bm25_index()
    _ensure_neo4j_schema_startup()
    _assert_embedding_dim_matches_pinecone()


def create_app() -> FastAPI:
    application = FastAPI(title="CausalGraph API", version="1.0.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ALLOW_ORIGINS,
        allow_origin_regex=_CORS_ALLOW_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(GZipMiddleware, minimum_size=1024)
    application.on_event("startup")(startup)
    for router in (*ROUTERS, *_optional_routers()):
        application.include_router(router)
    return application


app = create_app()
