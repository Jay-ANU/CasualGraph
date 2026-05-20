"""SQLite-backed vector retrieval for chunk embeddings."""

from __future__ import annotations

import json
from typing import Dict, List, Optional

import aiosqlite
import numpy as np


class VectorStoreService:
    async def upsert_embeddings(
        self,
        db: aiosqlite.Connection,
        document_id: str,
        user_id: str,
        embeddings: List[Dict],
        model_name: str,
    ) -> None:
        for item in embeddings:
            await db.execute(
                """
                INSERT OR REPLACE INTO chunk_embeddings
                (chunk_id, document_id, user_id, vector, model_name)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    item["chunk_id"],
                    document_id,
                    user_id,
                    json.dumps(item["vector"]),
                    model_name,
                ),
            )
        await db.commit()

    async def search(
        self,
        db: aiosqlite.Connection,
        user_id: str,
        query_vector: List[float],
        document_id: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict]:
        params = [user_id]
        query = """
            SELECT ce.chunk_id, ce.document_id, ce.vector, dc.content, dc.metadata
            FROM chunk_embeddings ce
            JOIN document_chunks dc ON dc.id = ce.chunk_id
            WHERE ce.user_id = ?
        """
        if document_id:
            query += " AND ce.document_id = ?"
            params.append(document_id)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        if not rows:
            return []

        query_vec = np.array(query_vector, dtype=float)
        query_norm = np.linalg.norm(query_vec)
        if query_norm > 0:
            query_vec = query_vec / query_norm

        scored: List[Dict] = []
        for row in rows:
            vector = np.array(json.loads(row[2]), dtype=float)
            if vector.shape != query_vec.shape:
                continue
            score = float(query_vec @ vector) if vector.size else 0.0
            scored.append(
                {
                    "chunk_id": row[0],
                    "document_id": row[1],
                    "score": score,
                    "content": row[3],
                    "metadata": json.loads(row[4]),
                }
            )

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]


vector_store_service = VectorStoreService()
