"""Chunk ESG report text with section-aware, overlap-preserving windows."""

from __future__ import annotations

from typing import Dict, List
import re

from configs.settings import CHUNK_OVERLAP, CHUNK_SIZE


_TOKEN_PATTERN = re.compile(r"\S+")
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[Dict]:
    """Split report text into section-aware chunks with lightweight metadata."""
    if not text or not text.strip():
        return []

    normalized = text.strip()
    blocks = _split_blocks(normalized)
    if not blocks:
        return []

    chunks: List[Dict] = []
    current_section = "Document"
    current_text = ""
    current_start = 0
    current_categories: List[str] = []
    current_paragraphs = 0

    for block_index, block in enumerate(blocks):
        block_text = block["text"]
        category = _classify_block(block_text)
        section_title = _extract_section_title(block_text) if category == "heading" else None

        if category == "heading":
            if current_text.strip():
                _append_chunk(
                    chunks=chunks,
                    text=current_text,
                    start=current_start,
                    section=current_section,
                    categories=current_categories,
                    paragraph_count=current_paragraphs,
                )
                current_text = ""
                current_categories = []
                current_paragraphs = 0

            current_section = section_title or current_section

            next_block = blocks[block_index + 1] if block_index + 1 < len(blocks) else None
            if next_block and len(block_text) <= max(80, chunk_size // 4):
                current_text = block_text
                current_start = block["start"]
                current_categories = ["heading"]
                current_paragraphs = 1
            continue

        if len(block_text) > chunk_size:
            if current_text.strip():
                _append_chunk(
                    chunks=chunks,
                    text=current_text,
                    start=current_start,
                    section=current_section,
                    categories=current_categories,
                    paragraph_count=current_paragraphs,
                )
                current_text = ""
                current_categories = []
                current_paragraphs = 0

            oversized_chunks = _split_oversized_block(
                block_text=block_text,
                block_start=block["start"],
                chunk_size=chunk_size,
                overlap=overlap,
                section=current_section,
                category=category,
            )
            chunks.extend(oversized_chunks)
            continue

        proposed_text = f"{current_text}\n\n{block_text}".strip() if current_text else block_text
        if current_text and len(proposed_text) > chunk_size:
            _append_chunk(
                chunks=chunks,
                text=current_text,
                start=current_start,
                section=current_section,
                categories=current_categories,
                paragraph_count=current_paragraphs,
            )

            overlap_text = current_text[-overlap:].strip() if overlap > 0 else ""
            current_text = f"{overlap_text}\n\n{block_text}".strip() if overlap_text else block_text
            current_start = max(block["start"] - len(overlap_text), 0) if overlap_text else block["start"]
            current_categories = (["overlap"] if overlap_text else []) + [category]
            current_paragraphs = 1 + (1 if overlap_text else 0)
        else:
            if not current_text:
                current_start = block["start"]
            current_text = proposed_text
            current_categories.append(category)
            current_paragraphs += 1

    if current_text.strip():
        _append_chunk(
            chunks=chunks,
            text=current_text,
            start=current_start,
            section=current_section,
            categories=current_categories,
            paragraph_count=current_paragraphs,
        )

    for index, chunk in enumerate(chunks):
        chunk["chunk_id"] = f"chunk_{index}"

    return [chunk for chunk in chunks if chunk["text"].strip()]


def _split_blocks(text: str) -> List[Dict]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not parts:
        return []

    blocks: List[Dict] = []
    cursor = 0
    for part in parts:
        start = text.find(part, cursor)
        if start < 0:
            start = cursor
        end = start + len(part)
        blocks.append({"text": part, "start": start, "end": end})
        cursor = end
    return blocks


def _append_chunk(
    chunks: List[Dict],
    text: str,
    start: int,
    section: str,
    categories: List[str],
    paragraph_count: int,
) -> None:
    chunk_text_value = text.strip()
    if not chunk_text_value:
        return

    category = _merge_categories(categories)
    chunks.append(
        {
            "chunk_id": f"chunk_{len(chunks)}",
            "text": chunk_text_value,
            "start": start,
            "end": start + len(chunk_text_value),
            "section": section,
            "category": category,
            "approx_tokens": _approx_token_count(chunk_text_value),
            "paragraph_count": max(paragraph_count, 1),
        }
    )


def _split_oversized_block(
    block_text: str,
    block_start: int,
    chunk_size: int,
    overlap: int,
    section: str,
    category: str,
) -> List[Dict]:
    sentences = [part.strip() for part in _SENTENCE_SPLIT_PATTERN.split(block_text) if part.strip()]
    if not sentences:
        sentences = [block_text]

    chunks: List[Dict] = []
    current = ""
    current_start = block_start
    sentence_cursor = block_start

    for sentence in sentences:
        sentence_start = block_text.find(sentence, max(sentence_cursor - block_start, 0)) + block_start
        if sentence_start < block_start:
            sentence_start = sentence_cursor

        proposed = f"{current} {sentence}".strip() if current else sentence
        if current and len(proposed) > chunk_size:
            _append_chunk(
                chunks=chunks,
                text=current,
                start=current_start,
                section=section,
                categories=[category],
                paragraph_count=1,
            )
            overlap_text = current[-overlap:].strip() if overlap > 0 else ""
            current = f"{overlap_text} {sentence}".strip() if overlap_text else sentence
            current_start = max(sentence_start - len(overlap_text), block_start) if overlap_text else sentence_start
        else:
            if not current:
                current_start = sentence_start
            current = proposed

        sentence_cursor = sentence_start + len(sentence)

    if current.strip():
        _append_chunk(
            chunks=chunks,
            text=current,
            start=current_start,
            section=section,
            categories=[category],
            paragraph_count=1,
        )

    return chunks


def _classify_block(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "narrative"

    if len(lines) >= 2 and sum(1 for line in lines if _looks_table_like(line)) >= max(2, len(lines) // 2):
        return "table_like"

    if any(char in text for char in ["|", "\t"]) and len(lines) >= 2:
        return "table_like"

    if _is_heading(text):
        return "heading"

    return "narrative"


def _is_heading(text: str) -> bool:
    raw_lines = [part.strip() for part in text.splitlines() if part.strip()]
    if len(raw_lines) > 2:
        return False

    line = " ".join(raw_lines)
    if not line or len(line) > 120:
        return False

    if line.endswith((".", "!", "?", ";", ":")):
        return False

    if re.match(r"^(\d+(\.\d+)*|[A-Z])\s+.+", line):
        return True

    words = line.split()
    if 1 <= len(words) <= 12 and all(word[:1].isupper() or word.isupper() or any(ch.isdigit() for ch in word) for word in words):
        return True

    if line.isupper() and len(words) <= 12:
        return True

    return False


def _looks_table_like(line: str) -> bool:
    if "|" in line or "\t" in line:
        return True

    digit_groups = len(re.findall(r"\d[\d,.\-%]*", line))
    column_gaps = len(re.findall(r"\s{2,}", line))
    return digit_groups >= 2 and column_gaps >= 1


def _extract_section_title(text: str) -> str:
    title = " ".join(part.strip() for part in text.splitlines() if part.strip())
    title = re.sub(r"\s+", " ", title).strip()
    return title[:120] or "Document"


def _merge_categories(categories: List[str]) -> str:
    filtered = [category for category in categories if category and category != "overlap"]
    if not filtered:
        return "narrative"
    unique = list(dict.fromkeys(filtered))
    if len(unique) == 1:
        return unique[0]
    if "table_like" in unique:
        return "mixed_table"
    return "mixed"


def _approx_token_count(text: str) -> int:
    return len(_TOKEN_PATTERN.findall(text))
