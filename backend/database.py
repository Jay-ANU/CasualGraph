"""
Database configuration and connection management
Handles SQLite database setup and session management with async support
"""

import aiosqlite
import os
from pathlib import Path
from typing import AsyncGenerator
import json
from datetime import datetime
import uuid

class DatabaseManager:
    def __init__(self, db_path: str = "causalgraph.db"):
        self.db_path = db_path
    
    async def init_database(self):
        """Initialize database tables"""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            # Users table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            
            # Documents table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # Knowledge graphs table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_graphs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    user_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    nodes TEXT NOT NULL,
                    edges TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    statistics TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (document_id) REFERENCES documents (id)
                )
            """)
            
            # Analysis results table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS analysis_results (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    relationships TEXT NOT NULL,
                    quality_metrics TEXT NOT NULL,
                    processing_time REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # CDK activations table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cdk_activations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    cdk_code TEXT NOT NULL,
                    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # RAG chunks table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # Chunk embeddings table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chunk_embeddings (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    vector TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chunk_id) REFERENCES document_chunks (id) ON DELETE CASCADE,
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # ESG entities table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_entities (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    chunk_id TEXT,
                    confidence REAL DEFAULT 0,
                    metadata TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
                    FOREIGN KEY (chunk_id) REFERENCES document_chunks (id) ON DELETE SET NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # ESG relations table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_relations (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    source_entity_id TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    evidence TEXT DEFAULT '',
                    chunk_id TEXT,
                    confidence REAL DEFAULT 0,
                    metadata TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
                    FOREIGN KEY (chunk_id) REFERENCES document_chunks (id) ON DELETE SET NULL,
                    FOREIGN KEY (source_entity_id) REFERENCES graph_entities (id) ON DELETE CASCADE,
                    FOREIGN KEY (target_entity_id) REFERENCES graph_entities (id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # Create indexes for better performance
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_graphs_user_id ON knowledge_graphs(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_results_user_id ON analysis_results(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_cdk_activations_user_id ON cdk_activations(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON document_chunks(document_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_user_id ON document_chunks(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_document_id ON chunk_embeddings(document_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_document_id ON graph_entities(document_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_user_id ON graph_entities(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_entities_normalized_name ON graph_entities(normalized_name)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_relations_document_id ON graph_relations(document_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_relations_source_id ON graph_relations(source_entity_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_relations_target_id ON graph_relations(target_entity_id)")
            
            await conn.commit()

# Global database manager instance
db_manager = DatabaseManager()

async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async dependency to get database connection"""
    async with aiosqlite.connect(db_manager.db_path) as conn:
        # Enable foreign key support
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn
