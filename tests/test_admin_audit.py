import os
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from admin_audit import record_upload_completed, record_upload_created


def test_record_upload_completed_persists_document_and_stats():
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "auth.db"
        with patch.dict(os.environ, {"AUTH_DB_PATH": str(db_path)}):
            record_upload_created(
                job_id="job-1",
                title="Example document",
                filename="example.pdf",
                domain="academic",
                source_type="peer_reviewed",
                source="example.pdf",
                uploader={"id": "u1", "email": "user@example.com", "username": "user"},
            )

            record_upload_completed(
                "job-1",
                {
                    "document": {
                        "id": "doc-1",
                        "processed_text_path": "data/processed/doc-1.txt",
                        "chunks_path": "data/chunks/doc-1_chunks.jsonl",
                        "extractions_path": "data/extractions/doc-1_extractions.jsonl",
                        "graph_path": "data/graph/doc-1_graph.json",
                        "vector_store_path": "data/vector_store/doc-1",
                        "content_hash": "sha256:test",
                    },
                    "stats": {
                        "chunk_count": 12,
                        "entity_count": 34,
                        "relation_count": 56,
                    },
                },
            )

            with sqlite3.connect(db_path) as db:
                row = db.execute(
                    """
                    SELECT document_id, chunk_count, entity_count, relation_count,
                           processed_text_path, chunks_path, extractions_path,
                           graph_path, vector_store_path, content_hash
                    FROM upload_audit
                    WHERE job_id = ?
                    """,
                    ("job-1",),
                ).fetchone()

        assert row == (
            "doc-1",
            12,
            34,
            56,
            "data/processed/doc-1.txt",
            "data/chunks/doc-1_chunks.jsonl",
            "data/extractions/doc-1_extractions.jsonl",
            "data/graph/doc-1_graph.json",
            "data/vector_store/doc-1",
            "sha256:test",
        )
