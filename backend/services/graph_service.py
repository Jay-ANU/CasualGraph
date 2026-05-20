"""Persistence and query helpers for ESG entities, relations, and chunks."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import aiosqlite

from models import DocumentChunk, GraphEntity, GraphRelation


class GraphService:
    async def replace_chunks(
        self,
        db: aiosqlite.Connection,
        document_id: str,
        user_id: str,
        chunks: List[Dict],
    ) -> List[DocumentChunk]:
        await db.execute("DELETE FROM chunk_embeddings WHERE document_id = ? AND user_id = ?", (document_id, user_id))
        await db.execute("DELETE FROM document_chunks WHERE document_id = ? AND user_id = ?", (document_id, user_id))

        for chunk in chunks:
            await db.execute(
                """
                INSERT INTO document_chunks (id, document_id, user_id, content, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    chunk["id"],
                    document_id,
                    user_id,
                    chunk["content"],
                    json.dumps(chunk["metadata"]),
                ),
            )
        await db.commit()
        return await self.get_chunks(db, document_id, user_id)

    async def get_chunks(self, db: aiosqlite.Connection, document_id: str, user_id: str) -> List[DocumentChunk]:
        cursor = await db.execute(
            """
            SELECT id, document_id, user_id, content, metadata, created_at
            FROM document_chunks
            WHERE document_id = ? AND user_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (document_id, user_id),
        )
        rows = await cursor.fetchall()
        return [
            DocumentChunk(
                id=row[0],
                document_id=row[1],
                user_id=row[2],
                content=row[3],
                metadata=json.loads(row[4]),
                created_at=datetime.fromisoformat(row[5]),
            )
            for row in rows
        ]

    async def replace_graph(
        self,
        db: aiosqlite.Connection,
        document_id: str,
        user_id: str,
        entities: List[Dict],
        relations: List[Dict],
    ) -> Tuple[List[GraphEntity], List[GraphRelation]]:
        await db.execute("DELETE FROM graph_relations WHERE document_id = ? AND user_id = ?", (document_id, user_id))
        await db.execute("DELETE FROM graph_entities WHERE document_id = ? AND user_id = ?", (document_id, user_id))

        entity_map: Dict[str, str] = {}
        entity_rows: List[GraphEntity] = []
        dedup_entities: Dict[str, Dict] = {}
        for entity in entities:
            dedup_entities[entity["entity_key"]] = entity

        for entity in dedup_entities.values():
            entity_id = str(uuid.uuid4())
            entity_map[entity["entity_key"]] = entity_id
            await db.execute(
                """
                INSERT INTO graph_entities
                (id, document_id, user_id, name, entity_type, normalized_name, description, chunk_id, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    document_id,
                    user_id,
                    entity["name"],
                    entity["type"],
                    entity["normalized_name"],
                    entity["description"],
                    entity.get("source_chunk_id"),
                    entity["confidence"],
                    json.dumps(entity.get("metadata", {})),
                ),
            )

        dedup_relations: Dict[Tuple[str, str, str], Dict] = {}
        for relation in relations:
            key = (relation["source_key"], relation["target_key"], relation["relation_type"])
            dedup_relations[key] = relation

        for relation in dedup_relations.values():
            source_id = entity_map.get(relation["source_key"])
            target_id = entity_map.get(relation["target_key"])
            if not source_id or not target_id:
                continue
            await db.execute(
                """
                INSERT INTO graph_relations
                (id, document_id, user_id, source_entity_id, target_entity_id, relation_type, evidence, chunk_id, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    document_id,
                    user_id,
                    source_id,
                    target_id,
                    relation["relation_type"],
                    relation.get("evidence", ""),
                    relation.get("chunk_id"),
                    relation.get("confidence", 0.0),
                    json.dumps(relation.get("metadata", {})),
                ),
            )

        await db.commit()
        entity_rows = await self.list_entities(db, user_id, document_id=document_id)
        relation_rows = await self.list_relations(db, user_id, document_id=document_id)
        return entity_rows, relation_rows

    async def list_entities(
        self,
        db: aiosqlite.Connection,
        user_id: str,
        document_id: Optional[str] = None,
        company: Optional[str] = None,
        limit: int = 200,
    ) -> List[GraphEntity]:
        params: List = [user_id]
        query = """
            SELECT id, document_id, user_id, name, entity_type, normalized_name, description, chunk_id, confidence, metadata, created_at
            FROM graph_entities
            WHERE user_id = ?
        """
        if document_id:
            query += " AND document_id = ?"
            params.append(document_id)
        if company:
            query += " AND (entity_type = 'COMPANY' AND lower(name) LIKE ?)"
            params.append(f"%{company.lower()}%")
        query += " ORDER BY confidence DESC, created_at ASC LIMIT ?"
        params.append(limit)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [self._entity_from_row(row) for row in rows]

    async def list_relations(
        self,
        db: aiosqlite.Connection,
        user_id: str,
        document_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[GraphRelation]:
        params: List = [user_id]
        query = """
            SELECT id, document_id, user_id, source_entity_id, target_entity_id, relation_type, evidence, chunk_id, confidence, metadata, created_at
            FROM graph_relations
            WHERE user_id = ?
        """
        if document_id:
            query += " AND document_id = ?"
            params.append(document_id)
        if entity_id:
            query += " AND (source_entity_id = ? OR target_entity_id = ?)"
            params.extend([entity_id, entity_id])
        query += " ORDER BY confidence DESC, created_at ASC LIMIT ?"
        params.append(limit)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [self._relation_from_row(row) for row in rows]

    async def get_entity(self, db: aiosqlite.Connection, user_id: str, entity_id: str) -> Optional[GraphEntity]:
        cursor = await db.execute(
            """
            SELECT id, document_id, user_id, name, entity_type, normalized_name, description, chunk_id, confidence, metadata, created_at
            FROM graph_entities WHERE id = ? AND user_id = ?
            """,
            (entity_id, user_id),
        )
        row = await cursor.fetchone()
        return self._entity_from_row(row) if row else None

    async def find_entity_ids_for_question(
        self, db: aiosqlite.Connection, user_id: str, question: str, document_id: Optional[str] = None
    ) -> List[str]:
        tokens = [token for token in question.lower().split() if len(token) > 2][:8]
        if not tokens:
            return []

        matched: List[str] = []
        for token in tokens:
            params: List = [user_id, f"%{token}%"]
            query = "SELECT id FROM graph_entities WHERE user_id = ? AND lower(name) LIKE ?"
            if document_id:
                query += " AND document_id = ?"
                params.append(document_id)
            query += " LIMIT 5"
            cursor = await db.execute(query, params)
            matched.extend([row[0] for row in await cursor.fetchall()])
        return list(dict.fromkeys(matched))

    async def get_subgraph(
        self,
        db: aiosqlite.Connection,
        user_id: str,
        entity_id: Optional[str] = None,
        question: Optional[str] = None,
        document_id: Optional[str] = None,
        depth: int = 2,
        limit: int = 50,
    ) -> Dict:
        matched_ids = [entity_id] if entity_id else []
        if question and not matched_ids:
            matched_ids = await self.find_entity_ids_for_question(db, user_id, question, document_id=document_id)
        if not matched_ids:
            return {"entities": [], "relations": [], "matched_entity_ids": []}

        visited = set(matched_ids)
        frontier = set(matched_ids)
        relation_rows: List[GraphRelation] = []

        for _ in range(max(1, depth)):
            if not frontier:
                break
            placeholders = ",".join("?" for _ in frontier)
            params: List = [user_id]
            if document_id:
                relation_filter = " AND document_id = ?"
                params.append(document_id)
            else:
                relation_filter = ""
            params.extend(list(frontier))
            params.extend(list(frontier))
            params.append(limit)
            cursor = await db.execute(
                f"""
                SELECT id, document_id, user_id, source_entity_id, target_entity_id, relation_type, evidence, chunk_id, confidence, metadata, created_at
                FROM graph_relations
                WHERE user_id = ? {relation_filter}
                AND (source_entity_id IN ({placeholders}) OR target_entity_id IN ({placeholders}))
                ORDER BY confidence DESC
                LIMIT ?
                """,
                params,
            )
            rows = [self._relation_from_row(row) for row in await cursor.fetchall()]
            relation_rows.extend(rows)

            next_frontier = set()
            for relation in rows:
                if relation.source_entity_id not in visited:
                    next_frontier.add(relation.source_entity_id)
                if relation.target_entity_id not in visited:
                    next_frontier.add(relation.target_entity_id)
            visited.update(next_frontier)
            frontier = next_frontier

        entity_rows: List[GraphEntity] = []
        if visited:
            placeholders = ",".join("?" for _ in visited)
            cursor = await db.execute(
                f"""
                SELECT id, document_id, user_id, name, entity_type, normalized_name, description, chunk_id, confidence, metadata, created_at
                FROM graph_entities
                WHERE user_id = ? AND id IN ({placeholders})
                """,
                [user_id, *visited],
            )
            entity_rows = [self._entity_from_row(row) for row in await cursor.fetchall()]

        unique_relations = {(rel.id, rel.relation_type): rel for rel in relation_rows}
        return {
            "entities": entity_rows,
            "relations": list(unique_relations.values()),
            "matched_entity_ids": matched_ids,
        }

    @staticmethod
    def _entity_from_row(row) -> GraphEntity:
        return GraphEntity(
            id=row[0],
            document_id=row[1],
            user_id=row[2],
            name=row[3],
            entity_type=row[4],
            normalized_name=row[5],
            description=row[6] or "",
            chunk_id=row[7],
            confidence=row[8] or 0.0,
            metadata=json.loads(row[9]),
            created_at=datetime.fromisoformat(row[10]),
        )

    @staticmethod
    def _relation_from_row(row) -> GraphRelation:
        return GraphRelation(
            id=row[0],
            document_id=row[1],
            user_id=row[2],
            source_entity_id=row[3],
            target_entity_id=row[4],
            relation_type=row[5],
            evidence=row[6] or "",
            chunk_id=row[7],
            confidence=row[8] or 0.0,
            metadata=json.loads(row[9]),
            created_at=datetime.fromisoformat(row[10]),
        )


graph_service = GraphService()
