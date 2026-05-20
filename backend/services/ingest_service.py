"""End-to-end document ingest pipeline for the MVP."""

from __future__ import annotations

from typing import Dict
import traceback

import aiosqlite

from config import Config
from services.chunk_service import chunk_service
from services.embedding_service import embedding_service
from services.esg_extraction_service import esg_extraction_service
from services.esg_model_client import esg_model_client
from services.esg_result_adapter import esg_result_adapter
from services.graph_service import graph_service
from services.vector_store_service import vector_store_service


class IngestService:
    async def ingest_document(
        self,
        db: aiosqlite.Connection,
        document,
        user_id: str,
        company: str | None = None,
        source: str = "",
        category: str = "general",
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        run_entity_extraction: bool = True,
        run_relation_extraction: bool = True,
    ) -> Dict:
        chunks = chunk_service.create_chunks(
            parsed_document=self._document_to_parsed(document),
            document_id=document.id,
            source=source or document.original_filename,
            category=category,
            max_chars=chunk_size or Config.DEFAULT_CHUNK_SIZE,
            overlap_chars=chunk_overlap if chunk_overlap is not None else Config.DEFAULT_CHUNK_OVERLAP,
        )
        stored_chunks = await graph_service.replace_chunks(db, document.id, user_id, chunks)

        vectors = embedding_service.embed_texts([chunk.content for chunk in stored_chunks])
        await vector_store_service.upsert_embeddings(
            db,
            document.id,
            user_id,
            [{"chunk_id": chunk.id, "vector": vector} for chunk, vector in zip(stored_chunks, vectors)],
            embedding_service.model_name if not embedding_service.use_mock else "hash-embedding",
        )

        all_entities = []
        all_relations = []
        extraction_backend = "heuristic_fallback"
        ai_chunks_used = 0
        heuristic_chunks_used = 0
        if run_entity_extraction:
            for chunk in stored_chunks:
                chunk_payload = {"id": chunk.id, "document_id": chunk.document_id, "content": chunk.content}
                chunk_entities = []
                chunk_relations = []

                if esg_model_client.is_enabled():
                    try:
                        model_result = esg_model_client.extract(chunk.content)
                        chunk_entities, chunk_relations = esg_result_adapter.adapt(
                            result=model_result,
                            chunk_id=chunk.id,
                            document_id=chunk.document_id,
                            company=company,
                            include_relations=run_relation_extraction,
                        )
                        if chunk_entities or chunk_relations:
                            extraction_backend = "local_ai_service"
                            ai_chunks_used += 1
                    except Exception as exc:
                        print(f"AI extraction failed for chunk {chunk.id}: {exc}")
                        print(traceback.format_exc(limit=1))

                if not chunk_entities and not chunk_relations:
                    chunk_entities = esg_extraction_service.extract_entities(chunk_payload, company=company)
                    if run_relation_extraction:
                        relation_results = esg_extraction_service.extract_relations(chunk_payload, chunk_entities, company=company)
                        synthetic_entities = [item for item in relation_results if "entity_key" in item]
                        chunk_entities.extend(synthetic_entities)
                        chunk_relations = [item for item in relation_results if "relation_type" in item]
                    heuristic_chunks_used += 1

                all_entities.extend(chunk_entities)
                all_relations.extend(chunk_relations)

        stored_entities, stored_relations = await graph_service.replace_graph(
            db,
            document.id,
            user_id,
            all_entities,
            all_relations,
        )

        return {
            "document_id": document.id,
            "chunks": len(stored_chunks),
            "entities": len(stored_entities),
            "relations": len(stored_relations),
            "embedding_model": embedding_service.model_name if not embedding_service.use_mock else "hash-embedding",
            "used_mock_embeddings": embedding_service.use_mock,
            "extraction_backend": extraction_backend,
            "ai_chunks_used": ai_chunks_used,
            "heuristic_chunks_used": heuristic_chunks_used,
        }

    @staticmethod
    def _document_to_parsed(document):
        import re
        from services.parser_service import ParsedDocument, ParsedPage

        page_matches = list(re.finditer(r"<<<PAGE:(\d+)>>>", document.content))
        pages = []
        if page_matches:
            for idx, match in enumerate(page_matches):
                page_number = int(match.group(1))
                start = match.end()
                end = page_matches[idx + 1].start() if idx + 1 < len(page_matches) else len(document.content)
                page_text = document.content[start:end].strip()
                if page_text:
                    pages.append(ParsedPage(page_number=page_number, text=page_text))
        if not pages:
            pages = [ParsedPage(page_number=1, text=document.content)]

        return ParsedDocument(
            title=document.title,
            file_type=document.file_type,
            text="\n\n".join(page.text for page in pages),
            pages=pages,
            stats={},
        )


ingest_service = IngestService()
