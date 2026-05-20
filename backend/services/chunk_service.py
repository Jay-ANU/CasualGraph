"""Chunking utilities for ESG documents."""

from __future__ import annotations

from typing import Dict, List
import re

from config import Config
from services.parser_service import ParsedDocument


class ChunkService:
    """Split parsed documents into retrieval-friendly chunks."""

    def create_chunks(
        self,
        parsed_document: ParsedDocument,
        document_id: str,
        source: str = "",
        category: str = "general",
        max_chars: int | None = None,
        overlap_chars: int | None = None,
    ) -> List[Dict]:
        max_chars = max_chars or Config.DEFAULT_CHUNK_SIZE
        overlap_chars = overlap_chars if overlap_chars is not None else Config.DEFAULT_CHUNK_OVERLAP

        chunks: List[Dict] = []
        chunk_index = 0

        for page in parsed_document.pages or []:
            paragraphs = self._paragraphs(page.text)
            buffer = ""
            for paragraph in paragraphs:
                if buffer and len(buffer) + len(paragraph) + 2 > max_chars:
                    chunks.append(
                        self._build_chunk(
                            document_id=document_id,
                            chunk_index=chunk_index,
                            text=buffer.strip(),
                            page_start=page.page_number,
                            page_end=page.page_number,
                            source=source,
                            category=category,
                        )
                    )
                    chunk_index += 1
                    buffer = buffer[-overlap_chars:].strip() if overlap_chars else ""
                buffer = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph

            if buffer.strip():
                chunks.append(
                    self._build_chunk(
                        document_id=document_id,
                        chunk_index=chunk_index,
                        text=buffer.strip(),
                        page_start=page.page_number,
                        page_end=page.page_number,
                        source=source,
                        category=category,
                    )
                )
                chunk_index += 1

        if not chunks and parsed_document.text.strip():
            chunks.append(
                self._build_chunk(
                    document_id=document_id,
                    chunk_index=0,
                    text=parsed_document.text.strip(),
                    page_start=1,
                    page_end=max(1, len(parsed_document.pages)),
                    source=source,
                    category=category,
                )
            )

        return chunks

    @staticmethod
    def _paragraphs(text: str) -> List[str]:
        normalized = text.replace("\r\n", "\n")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
        if paragraphs:
            return paragraphs
        return [line.strip() for line in normalized.splitlines() if line.strip()]

    @staticmethod
    def _build_chunk(
        document_id: str,
        chunk_index: int,
        text: str,
        page_start: int,
        page_end: int,
        source: str,
        category: str,
    ) -> Dict:
        words = text.split()
        return {
            "id": f"{document_id}_chunk_{chunk_index:04d}",
            "document_id": document_id,
            "content": text,
            "metadata": {
                "chunk_index": chunk_index,
                "page_start": page_start,
                "page_end": page_end,
                "source": source,
                "category": category,
                "word_count": len(words),
                "token_estimate": int(len(words) * 1.3),
            },
        }


chunk_service = ChunkService()
