"""RAG and Graph RAG orchestration."""

from __future__ import annotations

from typing import Dict, Optional

import aiosqlite

from config import Config
from services.embedding_service import embedding_service
from services.graph_service import graph_service
from services.llm_service import llm_service
from services.vector_store_service import vector_store_service


class RAGService:
    async def answer_rag(
        self,
        db: aiosqlite.Connection,
        user_id: str,
        question: str,
        document_id: Optional[str] = None,
        top_k: int = 5,
    ) -> Dict:
        query_vector = embedding_service.embed_text(question)
        retrieved = await vector_store_service.search(
            db=db,
            user_id=user_id,
            query_vector=query_vector,
            document_id=document_id,
            top_k=top_k,
        )
        citations = [item for item in retrieved if item["score"] >= Config.MIN_RAG_SCORE]
        answer = llm_service.answer_question(question=question, citations=citations, route="rag")
        return {
            "answer": answer["answer"],
            "route": "rag",
            "citations": [
                {
                    "chunk_id": item["chunk_id"],
                    "document_id": item["document_id"],
                    "score": round(item["score"], 4),
                    "excerpt": item["content"][:280],
                    "metadata": item["metadata"],
                }
                for item in citations
            ],
            "used_mock": answer["used_mock"],
            "enough_context": answer["enough_context"],
        }

    async def answer_graph_rag(
        self,
        db: aiosqlite.Connection,
        user_id: str,
        question: str,
        document_id: Optional[str] = None,
        top_k: int = 5,
        depth: int = 2,
    ) -> Dict:
        query_vector = embedding_service.embed_text(question)
        retrieved = await vector_store_service.search(
            db=db,
            user_id=user_id,
            query_vector=query_vector,
            document_id=document_id,
            top_k=top_k,
        )
        citations = [item for item in retrieved if item["score"] >= Config.MIN_RAG_SCORE]
        subgraph = await graph_service.get_subgraph(
            db=db,
            user_id=user_id,
            question=question,
            document_id=document_id,
            depth=depth,
        )
        graph_context = self._subgraph_summary(subgraph)
        answer = llm_service.answer_question(
            question=question,
            citations=citations,
            route="graph-rag",
            graph_context=graph_context,
        )
        return {
            "answer": answer["answer"],
            "route": "graph-rag",
            "citations": [
                {
                    "chunk_id": item["chunk_id"],
                    "document_id": item["document_id"],
                    "score": round(item["score"], 4),
                    "excerpt": item["content"][:280],
                    "metadata": item["metadata"],
                }
                for item in citations
            ],
            "graph": {
                "matched_entity_ids": subgraph["matched_entity_ids"],
                "entities": [entity.dict() for entity in subgraph["entities"]],
                "relations": [relation.dict() for relation in subgraph["relations"]],
            },
            "used_mock": answer["used_mock"],
            "enough_context": answer["enough_context"],
        }

    @staticmethod
    def _subgraph_summary(subgraph: Dict) -> str:
        if not subgraph["entities"]:
            return "No relevant graph entities were matched."

        entity_lookup = {entity.id: entity.name for entity in subgraph["entities"]}
        relation_lines = []
        for relation in subgraph["relations"][:15]:
            relation_lines.append(
                f"{entity_lookup.get(relation.source_entity_id, relation.source_entity_id)} "
                f"-[{relation.relation_type}]-> "
                f"{entity_lookup.get(relation.target_entity_id, relation.target_entity_id)}"
            )
        return "\n".join(relation_lines) if relation_lines else "Matched entities but no explicit relations found."


rag_service = RAGService()
