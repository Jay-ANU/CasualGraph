"""Helpers for user-facing source labels."""

from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any, Dict, Set


_EXTENSION_RE = re.compile(r"\.[a-z0-9]{1,8}$", re.IGNORECASE)
_HASH_PREFIX_RE = re.compile(r"^[0-9a-f]{16,}[\s_-]+", re.IGNORECASE)
_SEPARATOR_RE = re.compile(r"[\s_-]+")
_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_LOW_VALUE_TITLE_TOKENS = {
    "report",
    "reports",
    "sustainability",
    "esg",
    "environmental",
    "social",
    "governance",
    "annual",
    "update",
    "full",
    "pdf",
}


def clean_source_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = PurePath(text.replace("\\", "/")).name
    text = _EXTENSION_RE.sub("", text)
    text = _HASH_PREFIX_RE.sub("", text)
    text = _SEPARATOR_RE.sub(" ", text).strip()
    return text


def display_document_title(source: Dict[str, Any]) -> str:
    title = clean_source_name(source.get("document_title") or source.get("title"))
    source_name = clean_source_name(source.get("source"))
    document_id = clean_source_name(source.get("document_id"))

    if _should_prefer_source_name(title, source_name):
        return source_name
    return title or source_name or document_id or "report"


def _should_prefer_source_name(title: str, source_name: str) -> bool:
    if not source_name:
        return False
    if not title:
        return True

    title_tokens = _meaningful_tokens(title)
    source_tokens = _meaningful_tokens(source_name)
    if not source_tokens:
        return False
    if not title_tokens:
        return True
    return title_tokens.isdisjoint(source_tokens)


def _meaningful_tokens(value: str) -> Set[str]:
    return {
        token.lower()
        for token in _WORD_RE.findall(value)
        if len(token) > 1 and not token.isdigit() and token.lower() not in _LOW_VALUE_TITLE_TOKENS
    }
