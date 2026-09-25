"""Shared types for the de-identification pipeline.

Flow:  detect(parsed, policy) -> RedactionReview  (candidates, all "pending" or
       auto-accepted)  ->  user reviews  ->  apply(parsed, review) -> RedactionResult
       (redacted ParsedDocument + RedactionMapping).

Coordinates: ``Occurrence`` offsets are *block-relative* and refer to the ORIGINAL
block text. Applying a review rewrites block texts in place; block ids, pages and
bounding boxes are untouched, so the viewer can still highlight the original file.

Placeholders look like ``[ORG_1]``, ``[PERSON_2]``, ``[ID_1]``. The same entity always
gets the same placeholder throughout a document so the model can reason about
"[ORG_1] (甲方)" across clauses. ``RedactionMapping.legend()`` renders a prompt-safe
legend (roles only, never the original values).

This file is shared by several work packages. Changes must stay additive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ingest.models import ParsedDocument

# Category id -> placeholder prefix. Keep ids stable: they are stored on disk and in audits.
CATEGORIES: Dict[str, str] = {
    "org": "ORG",  # companies, institutions, law firms
    "person": "PERSON",  # natural persons (signatories, contacts, legal representatives)
    "id_number": "ID",  # 身份证 and similar national id numbers
    "uscc": "USCC",  # 统一社会信用代码
    "phone": "PHONE",
    "email": "EMAIL",
    "address": "ADDRESS",
    "bank_account": "BANK",
    "passport": "PASSPORT",
    "license_plate": "PLATE",
    "amount": "AMOUNT",  # off by default — reviewers usually need the numbers
    "date": "DATE",  # off by default
    "custom": "CUSTOM",  # user-supplied terms
}

PLACEHOLDER_PATTERN = re.compile(r"\[(" + "|".join(sorted(set(CATEGORIES.values()), key=len, reverse=True)) + r")_(\d+)\]")

DECISIONS = ("pending", "accepted", "rejected")
REVIEW_STATUSES = ("pending", "confirmed", "skipped")


class RedactionPendingError(RuntimeError):
    """Raised when a document that has not passed the redaction gate is about to reach a model."""

    def __init__(self, document_id: str, status: str = "pending") -> None:
        super().__init__(f"document {document_id} has not been de-identified (status={status})")
        self.document_id = document_id
        self.status = status


@dataclass
class RedactionPolicy:
    enabled_categories: List[str]
    auto_confirm: bool = False  # True: accept all detections and confirm without a human step
    custom_terms: List[str] = field(default_factory=list)  # extra literal strings to redact
    keep_party_roles: bool = True  # keep 甲方/乙方/Party A words; they are roles, not identities
    min_confidence: float = 0.5  # detections below this are still listed, but start as "rejected"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled_categories": list(self.enabled_categories),
            "auto_confirm": self.auto_confirm,
            "custom_terms": list(self.custom_terms),
            "keep_party_roles": self.keep_party_roles,
            "min_confidence": self.min_confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RedactionPolicy":
        return cls(
            enabled_categories=[str(v) for v in data.get("enabled_categories") or []],
            auto_confirm=bool(data.get("auto_confirm", False)),
            custom_terms=[str(v) for v in data.get("custom_terms") or []],
            keep_party_roles=bool(data.get("keep_party_roles", True)),
            min_confidence=float(data.get("min_confidence", 0.5)),
        )

    @classmethod
    def default(cls) -> "RedactionPolicy":
        from configs.settings import REDACTION_DEFAULT_CATEGORIES, REDACTION_REQUIRE_CONFIRMATION

        return cls(
            enabled_categories=list(REDACTION_DEFAULT_CATEGORIES),
            auto_confirm=not REDACTION_REQUIRE_CONFIRMATION,
        )


@dataclass
class Occurrence:
    block_id: str
    start: int  # block-relative, original text
    end: int

    def to_dict(self) -> Dict[str, Any]:
        return {"block_id": self.block_id, "start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Occurrence":
        return cls(block_id=str(data["block_id"]), start=int(data["start"]), end=int(data["end"]))


@dataclass
class EntityCandidate:
    entity_id: str  # "ent_0001"
    category: str  # key of CATEGORIES
    value: str  # original surface form (ONLY ever stored encrypted)
    placeholder: str  # "[ORG_1]"
    occurrences: List[Occurrence]
    confidence: float
    detector: str  # "regex:uscc", "party_header", "signature_block", "jieba:nr", "user", ...
    role_hint: Optional[str] = None  # "甲方", "乙方", "Party A", "Licensor" ...
    decision: str = "pending"  # one of DECISIONS
    aliases: List[str] = field(default_factory=list)  # other surface forms mapped to the same placeholder

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "category": self.category,
            "value": self.value,
            "placeholder": self.placeholder,
            "occurrences": [o.to_dict() for o in self.occurrences],
            "confidence": self.confidence,
            "detector": self.detector,
            "role_hint": self.role_hint,
            "decision": self.decision,
            "aliases": list(self.aliases),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EntityCandidate":
        return cls(
            entity_id=str(data["entity_id"]),
            category=str(data["category"]),
            value=str(data.get("value") or ""),
            placeholder=str(data["placeholder"]),
            occurrences=[Occurrence.from_dict(o) for o in data.get("occurrences") or []],
            confidence=float(data.get("confidence", 0.0)),
            detector=str(data.get("detector") or ""),
            role_hint=data.get("role_hint"),
            decision=str(data.get("decision") or "pending"),
            aliases=[str(v) for v in data.get("aliases") or []],
        )


@dataclass
class RedactionReview:
    """Detection results plus the reviewer's decisions. Stored ENCRYPTED (contains original values)."""

    document_id: str
    status: str  # one of REVIEW_STATUSES
    policy: RedactionPolicy
    candidates: List[EntityCandidate]
    created_at: str
    confirmed_at: Optional[str] = None
    confirmed_by: Optional[str] = None
    detector_versions: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def accepted(self) -> List[EntityCandidate]:
        return [c for c in self.candidates if c.decision == "accepted"]

    def counts_by_category(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for candidate in self.accepted():
            counts[candidate.category] = counts.get(candidate.category, 0) + len(candidate.occurrences)
        return counts

    def public_summary(self) -> Dict[str, Any]:
        """Audit-safe summary: categories and counts, never values."""
        return {
            "document_id": self.document_id,
            "status": self.status,
            "candidate_count": len(self.candidates),
            "accepted_count": len(self.accepted()),
            "counts_by_category": self.counts_by_category(),
            "confirmed_at": self.confirmed_at,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "status": self.status,
            "policy": self.policy.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
            "created_at": self.created_at,
            "confirmed_at": self.confirmed_at,
            "confirmed_by": self.confirmed_by,
            "detector_versions": dict(self.detector_versions),
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RedactionReview":
        return cls(
            document_id=str(data["document_id"]),
            status=str(data.get("status") or "pending"),
            policy=RedactionPolicy.from_dict(data.get("policy") or {}),
            candidates=[EntityCandidate.from_dict(c) for c in data.get("candidates") or []],
            created_at=str(data.get("created_at") or ""),
            confirmed_at=data.get("confirmed_at"),
            confirmed_by=data.get("confirmed_by"),
            detector_versions=dict(data.get("detector_versions") or {}),
            warnings=[str(v) for v in data.get("warnings") or []],
        )


@dataclass
class MappingEntry:
    placeholder: str
    value: str
    category: str
    entity_id: str
    role_hint: Optional[str] = None
    aliases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "placeholder": self.placeholder,
            "value": self.value,
            "category": self.category,
            "entity_id": self.entity_id,
            "role_hint": self.role_hint,
            "aliases": list(self.aliases),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MappingEntry":
        return cls(
            placeholder=str(data["placeholder"]),
            value=str(data.get("value") or ""),
            category=str(data.get("category") or "custom"),
            entity_id=str(data.get("entity_id") or ""),
            role_hint=data.get("role_hint"),
            aliases=[str(v) for v in data.get("aliases") or []],
        )


@dataclass
class RedactionMapping:
    """placeholder <-> original value table for one document. Stored ENCRYPTED."""

    document_id: str
    entries: List[MappingEntry]

    def forward(self, text: str) -> str:
        """Replace original values (and aliases) with placeholders; longest strings first."""
        pairs = []
        for entry in self.entries:
            for surface in [entry.value, *entry.aliases]:
                if surface:
                    pairs.append((surface, entry.placeholder))
        pairs.sort(key=lambda p: len(p[0]), reverse=True)
        out = text
        for surface, placeholder in pairs:
            out = out.replace(surface, placeholder)
        return out

    def reverse(self, text: str) -> str:
        """Replace placeholders with the original values (for display and export only)."""
        table = {entry.placeholder: entry.value for entry in self.entries}
        return PLACEHOLDER_PATTERN.sub(lambda m: table.get(m.group(0), m.group(0)), text)

    def legend(self) -> str:
        """Prompt-safe legend: placeholders and roles, never the values."""
        lines = []
        for entry in self.entries:
            if entry.role_hint:
                lines.append(f"{entry.placeholder} = {entry.role_hint}")
            else:
                lines.append(f"{entry.placeholder} = {entry.category}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {"document_id": self.document_id, "entries": [e.to_dict() for e in self.entries]}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RedactionMapping":
        return cls(
            document_id=str(data["document_id"]),
            entries=[MappingEntry.from_dict(e) for e in data.get("entries") or []],
        )


@dataclass
class RedactionResult:
    redacted_document: ParsedDocument  # block texts rewritten with placeholders; ids/pages/bboxes unchanged
    mapping: RedactionMapping
    stats: Dict[str, int]  # category -> replaced occurrence count
    warnings: List[str] = field(default_factory=list)


def contains_placeholders(text: str) -> bool:
    return bool(PLACEHOLDER_PATTERN.search(text or ""))


__all__ = [
    "CATEGORIES",
    "DECISIONS",
    "EntityCandidate",
    "MappingEntry",
    "Occurrence",
    "PLACEHOLDER_PATTERN",
    "REVIEW_STATUSES",
    "RedactionMapping",
    "RedactionPendingError",
    "RedactionPolicy",
    "RedactionResult",
    "RedactionReview",
    "contains_placeholders",
]
