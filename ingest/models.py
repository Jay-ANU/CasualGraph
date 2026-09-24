"""Shared document model for Phase 1.

Everything downstream (clause segmentation, chunking, redaction, citations, the
document viewer) is built on these three ideas:

* A **Block** is the anchoring unit: a paragraph, heading, list item or table as it
  appears in the source file. Blocks have stable ids, a page number and, for PDFs, a
  bounding box. Redaction replaces text *inside* blocks, so block ids and boxes stay
  valid after de-identification and can drive highlighting in the original file.
* The **canonical text** of a document is ``ParsedDocument.full_text()``: the block
  texts in reading order joined by a single newline. Every character offset in chunks,
  clauses and citations refers to the canonical text of the *redacted* document (or of
  the original document when no redaction has happened yet).
* A **ClauseTree** organises blocks into numbered articles / clauses / sub-clauses.
  Chunks are cut along clause boundaries, and citations point at clauses and pages.

This file is shared by several work packages. Changes must stay additive
(new optional fields with defaults); never rename or remove a field here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEMA_VERSION = 2

BLOCK_KINDS = ("paragraph", "heading", "list_item", "table", "signature", "other")
CLAUSE_KINDS = (
    "title",
    "preamble",
    "recital",
    "definitions",
    "article",
    "clause",
    "subclause",
    "annex",
    "signature",
    "other",
)
SOURCE_FORMATS = ("pdf", "docx", "txt", "md")
LANGUAGES = ("zh", "en", "mixed", "unknown")

BLOCK_SEPARATOR = "\n"


@dataclass
class Block:
    """One paragraph-like unit of the source file."""

    block_id: str  # PDF: "p{page}:b{index}", DOCX/TXT: "b{index}". Stable for the document's life.
    order: int  # global reading order, 0-based
    text: str  # block text; after redaction this holds placeholders instead of PII
    kind: str = "paragraph"  # one of BLOCK_KINDS
    page_no: Optional[int] = None  # 1-based; None when the format has no pages (DOCX, TXT)
    bbox: Optional[Tuple[float, float, float, float]] = None  # (x0, top, x1, bottom) in PDF points
    meta: Dict[str, Any] = field(default_factory=dict)
    # meta conventions (all optional):
    #   docx: {"style": "Heading 1", "numbering_label": "1.1", "is_numbered": True, "table_index": 0}
    #   pdf:  {"font_size": 10.5, "bold": False}
    #   any:  {"numbering_label": "第三条"} when a label was recognised from the text itself

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "order": self.order,
            "text": self.text,
            "kind": self.kind,
            "page_no": self.page_no,
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Block":
        bbox = data.get("bbox")
        return cls(
            block_id=str(data["block_id"]),
            order=int(data.get("order", 0)),
            text=str(data.get("text") or ""),
            kind=str(data.get("kind") or "paragraph"),
            page_no=data.get("page_no"),
            bbox=tuple(float(v) for v in bbox) if bbox else None,  # type: ignore[arg-type]
            meta=dict(data.get("meta") or {}),
        )


@dataclass
class Page:
    page_no: int  # 1-based
    block_ids: List[str] = field(default_factory=list)
    width: Optional[float] = None
    height: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"page_no": self.page_no, "block_ids": list(self.block_ids), "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Page":
        return cls(
            page_no=int(data["page_no"]),
            block_ids=[str(v) for v in data.get("block_ids") or []],
            width=data.get("width"),
            height=data.get("height"),
        )


@dataclass
class ParsedDocument:
    """A parsed source file. Produced by ``ingest.parsers``; consumed by everything else."""

    document_id: str
    source_format: str  # one of SOURCE_FORMATS
    blocks: List[Block]
    pages: List[Page] = field(default_factory=list)  # empty for formats without pages
    language: str = "unknown"  # one of LANGUAGES
    meta: Dict[str, Any] = field(default_factory=dict)
    # meta conventions: {"title_guess": str, "parser": "pdfplumber", "parser_version": str,
    #                    "warnings": [str], "page_count": int, "original_filename": str,
    #                    "redacted": bool, "redaction_stats": {category: count}}
    schema_version: int = SCHEMA_VERSION

    # ---- canonical text -------------------------------------------------------------
    def ordered_blocks(self) -> List[Block]:
        return sorted(self.blocks, key=lambda b: b.order)

    def full_text(self) -> str:
        """Canonical text: block texts in reading order joined by BLOCK_SEPARATOR."""
        return BLOCK_SEPARATOR.join(block.text for block in self.ordered_blocks())

    def block_offsets(self) -> Dict[str, Tuple[int, int]]:
        """Map block_id -> (start, end) character offsets into ``full_text()``."""
        offsets: Dict[str, Tuple[int, int]] = {}
        cursor = 0
        for block in self.ordered_blocks():
            start = cursor
            end = start + len(block.text)
            offsets[block.block_id] = (start, end)
            cursor = end + len(BLOCK_SEPARATOR)
        return offsets

    def block_by_id(self, block_id: str) -> Optional[Block]:
        for block in self.blocks:
            if block.block_id == block_id:
                return block
        return None

    def page_of_block(self, block_id: str) -> Optional[int]:
        block = self.block_by_id(block_id)
        return block.page_no if block else None

    def page_text(self, page_no: int) -> str:
        return BLOCK_SEPARATOR.join(b.text for b in self.ordered_blocks() if b.page_no == page_no)

    def blocks_in_range(self, char_start: int, char_end: int) -> List[str]:
        """Block ids overlapping a canonical character range, in reading order."""
        hits: List[str] = []
        for block_id, (start, end) in self.block_offsets().items():
            if end > char_start and start < char_end:
                hits.append(block_id)
        return hits

    # ---- serialisation ----------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "source_format": self.source_format,
            "language": self.language,
            "meta": dict(self.meta),
            "pages": [p.to_dict() for p in self.pages],
            "blocks": [b.to_dict() for b in self.ordered_blocks()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParsedDocument":
        return cls(
            document_id=str(data["document_id"]),
            source_format=str(data.get("source_format") or "txt"),
            blocks=[Block.from_dict(b) for b in data.get("blocks") or []],
            pages=[Page.from_dict(p) for p in data.get("pages") or []],
            language=str(data.get("language") or "unknown"),
            meta=dict(data.get("meta") or {}),
            schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
        )


@dataclass
class ClauseNode:
    """A numbered unit of a contract (article, clause, sub-clause) or a structural part."""

    clause_id: str  # opaque, stable within the document, e.g. "cl_0007"
    kind: str  # one of CLAUSE_KINDS
    level: int  # 0 = top-level article / part, 1 = clause, 2 = sub-clause, ...
    number_label: str  # as written: "第三条", "3.2", "(a)", "Article 5", "" when unnumbered
    normalized_number: str  # dotted path with arabic numerals / letters: "3", "3.2", "3.2.a"; "" if none
    title: Optional[str]  # heading text without the label, if any
    block_ids: List[str]  # blocks belonging to this node itself (not to its children)
    char_start: int  # canonical offsets covering the node AND its descendants
    char_end: int
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    confidence: float = 1.0  # segmenter confidence that this boundary is real
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clause_id": self.clause_id,
            "kind": self.kind,
            "level": self.level,
            "number_label": self.number_label,
            "normalized_number": self.normalized_number,
            "title": self.title,
            "block_ids": list(self.block_ids),
            "char_start": self.char_start,
            "char_end": self.char_end,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "parent_id": self.parent_id,
            "children": list(self.children),
            "confidence": self.confidence,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClauseNode":
        return cls(
            clause_id=str(data["clause_id"]),
            kind=str(data.get("kind") or "other"),
            level=int(data.get("level", 0)),
            number_label=str(data.get("number_label") or ""),
            normalized_number=str(data.get("normalized_number") or ""),
            title=data.get("title"),
            block_ids=[str(v) for v in data.get("block_ids") or []],
            char_start=int(data.get("char_start", 0)),
            char_end=int(data.get("char_end", 0)),
            page_start=data.get("page_start"),
            page_end=data.get("page_end"),
            parent_id=data.get("parent_id"),
            children=[str(v) for v in data.get("children") or []],
            confidence=float(data.get("confidence", 1.0)),
            meta=dict(data.get("meta") or {}),
        )


@dataclass
class ClauseTree:
    document_id: str
    nodes: Dict[str, ClauseNode]
    roots: List[str]  # top-level clause ids in document order
    meta: Dict[str, Any] = field(default_factory=dict)  # {"segmenter": str, "version": str, "warnings": [...]}
    schema_version: int = SCHEMA_VERSION

    def ordered(self) -> List[ClauseNode]:
        """Depth-first, document order."""
        out: List[ClauseNode] = []

        def walk(ids: Iterable[str]) -> None:
            for clause_id in ids:
                node = self.nodes.get(clause_id)
                if node is None:
                    continue
                out.append(node)
                walk(node.children)

        walk(self.roots)
        return out

    def leaves(self) -> List[ClauseNode]:
        return [node for node in self.ordered() if not node.children]

    def path_label(self, clause_id: str) -> str:
        """Human label such as "第三条 保密义务 › 3.2"."""
        parts: List[str] = []
        node = self.nodes.get(clause_id)
        while node is not None:
            label = node.number_label or node.title or ""
            if node.title and node.number_label:
                label = f"{node.number_label} {node.title}"
            if label:
                parts.append(label)
            node = self.nodes.get(node.parent_id) if node.parent_id else None
        return " › ".join(reversed(parts))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "roots": list(self.roots),
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClauseTree":
        return cls(
            document_id=str(data["document_id"]),
            nodes={str(k): ClauseNode.from_dict(v) for k, v in (data.get("nodes") or {}).items()},
            roots=[str(v) for v in data.get("roots") or []],
            meta=dict(data.get("meta") or {}),
            schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
        )


# ---- chunk rows -------------------------------------------------------------------------
# Chunks stay plain dicts because the retrieval code, JSONL files and vector metadata all
# treat them as dicts. Schema v2 is a superset of the v1 rows already on disk.

CHUNK_V1_FIELDS = (
    "chunk_id",  # "chunk_{N}", N = index within the document (kept for backward compatibility)
    "text",
    "start",  # canonical offsets
    "end",
    "section",
    "category",
    "approx_tokens",
    "paragraph_count",
    "document_id",
    "document_title",
    "document_group",
    "owner_user_id",
    "visibility_scope",
    "source_type",
    "domain",
    "source",
)

CHUNK_V2_FIELDS = (
    "schema_version",  # 2
    "chunk_uid",  # f"{document_id}::{N:04d}" — globally unique
    "page_start",  # Optional[int]
    "page_end",  # Optional[int]
    "block_ids",  # List[str]
    "clause_id",  # Optional[str]  (the deepest clause containing the chunk)
    "clause_label",  # str, e.g. "第三条 保密义务 › 3.2"
    "clause_number",  # str, normalized, e.g. "3.2"
    "language",  # zh | en | mixed | unknown
)


def make_chunk_uid(document_id: str, index: int) -> str:
    return f"{document_id}::{index:04d}"


def validate_chunk_row(row: Dict[str, Any]) -> List[str]:
    """Return a list of problems for a v2 chunk row (empty list == valid)."""
    problems: List[str] = []
    for key in ("chunk_id", "text", "start", "end", "document_id"):
        if key not in row:
            problems.append(f"missing {key}")
    if int(row.get("schema_version") or 1) >= 2:
        for key in ("chunk_uid", "block_ids", "page_start", "page_end", "clause_id", "clause_label", "clause_number", "language"):
            if key not in row:
                problems.append(f"missing v2 field {key}")
        if not isinstance(row.get("block_ids"), list):
            problems.append("block_ids must be a list")
    if "start" in row and "end" in row and int(row["end"]) < int(row["start"]):
        problems.append("end < start")
    return problems


__all__ = [
    "BLOCK_KINDS",
    "BLOCK_SEPARATOR",
    "Block",
    "CHUNK_V1_FIELDS",
    "CHUNK_V2_FIELDS",
    "CLAUSE_KINDS",
    "ClauseNode",
    "ClauseTree",
    "LANGUAGES",
    "Page",
    "ParsedDocument",
    "SCHEMA_VERSION",
    "SOURCE_FORMATS",
    "make_chunk_uid",
    "validate_chunk_row",
]
