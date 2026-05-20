"""Pydantic schemas for ESG extraction requests and responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EsgExtractionRequest(BaseModel):
    text: str


class EsgExtractionResponse(BaseModel):
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    relations: List[Dict[str, Any]] = Field(default_factory=list)
    raw: Optional[str] = None
