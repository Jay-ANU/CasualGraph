"""/graph/neo4j/* (admin): optional Neo4j inspection."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.deps import require_admin
from configs.settings import NEO4J_AUTO_SYNC, neo4j_configured
from graph.neo4j_store import assert_neo4j_ready, get_neo4j_store, neo4j_sdk_available

router = APIRouter()


class Neo4jQuestionRequest(BaseModel):
    question: str
    hops: int = 2
    limit: int = 10


@router.get("/graph/neo4j/status")
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


@router.get("/graph/neo4j/entity/{entity_name}")
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


@router.get("/graph/neo4j/subgraph")
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


@router.post("/graph/neo4j/question")
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
