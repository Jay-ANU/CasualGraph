"""Health checks and the public model-configuration status."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/models/status")
def model_status():
    """Configuration-only check. No API call, credentials, or quota consumption."""
    from rag.model_status import get_model_status
    return get_model_status()


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})


@router.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})
