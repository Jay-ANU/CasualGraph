"""
Data storage service for CausalGraph.AI platform
Handles document and knowledge graph persistence
"""

import uuid
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
import aiosqlite
from database import get_db
from models import Document, DocumentCreate, KnowledgeGraph, KnowledgeGraphCreate, AnalysisResult

class StorageService:
    def __init__(self):
        pass
    
    async def save_document(self, document_data: DocumentCreate, db: aiosqlite.Connection) -> Document:
        """Save uploaded document to database"""
        doc_id = str(uuid.uuid4())
        await db.execute("""
            INSERT INTO documents (id, title, file_type, file_size, content, original_filename, user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id, document_data.title, document_data.file_type, document_data.file_size,
            document_data.content, document_data.original_filename, document_data.user_id, datetime.utcnow()
        ))
        
        await db.commit()
        
        return Document(
            id=doc_id,
            title=document_data.title,
            file_type=document_data.file_type,
            file_size=document_data.file_size,
            content=document_data.content,
            original_filename=document_data.original_filename,
            user_id=document_data.user_id,
            created_at=datetime.utcnow()
        )
    
    async def get_user_documents(self, user_id: str, db: aiosqlite.Connection) -> List[Document]:
        """Get all documents for a specific user"""
        cursor = await db.execute("""
            SELECT id, title, file_type, file_size, content, original_filename, user_id, created_at, processed_at
            FROM documents WHERE user_id = ? ORDER BY created_at DESC
        """, (user_id,))
        
        documents = []
        async for row in cursor:
            documents.append(Document(
                id=row[0],  # id
                title=row[1],  # title
                file_type=row[2],  # file_type
                file_size=row[3],  # file_size
                content=row[4],  # content
                original_filename=row[5],  # original_filename
                user_id=row[6],  # user_id
                created_at=datetime.fromisoformat(row[7]),  # created_at
                processed_at=datetime.fromisoformat(row[8]) if row[8] else None  # processed_at
            ))
        
        return documents
    
    async def get_document_by_id(self, document_id: str, user_id: str, db: aiosqlite.Connection) -> Optional[Document]:
        """Get specific document by ID for a user"""
        cursor = await db.execute("""
            SELECT id, title, file_type, file_size, content, original_filename, user_id, created_at, processed_at
            FROM documents WHERE id = ? AND user_id = ?
        """, (document_id, user_id))
        
        row = await cursor.fetchone()
        if not row:
            return None
        
        return Document(
            id=row[0],  # id
            title=row[1],  # title
            file_type=row[2],  # file_type
            file_size=row[3],  # file_size
            content=row[4],  # content
            original_filename=row[5],  # original_filename
            user_id=row[6],  # user_id
            created_at=datetime.fromisoformat(row[7]),  # created_at
            processed_at=datetime.fromisoformat(row[8]) if row[8] else None  # processed_at
        )
    
    async def mark_document_processed(self, document_id: str, db: aiosqlite.Connection):
        """Mark document as processed"""
        await db.execute("""
            UPDATE documents SET processed_at = ? WHERE id = ?
        """, (datetime.utcnow(), document_id))
        await db.commit()
    
    async def save_knowledge_graph(self, graph_data: KnowledgeGraphCreate, db: aiosqlite.Connection) -> KnowledgeGraph:
        """Save knowledge graph to database"""
        graph_id = str(uuid.uuid4())
        
        # Extract statistics from metadata if available
        metadata = graph_data.metadata.copy()
        statistics = metadata.pop("statistics", {})
        
        await db.execute("""
            INSERT INTO knowledge_graphs (id, title, description, user_id, document_id, nodes, edges, metadata, statistics, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            graph_id, graph_data.title, graph_data.description, graph_data.user_id, graph_data.document_id,
            json.dumps(graph_data.nodes), json.dumps(graph_data.edges), 
            json.dumps(metadata), json.dumps(statistics), datetime.utcnow()
        ))
        
        await db.commit()
        
        return KnowledgeGraph(
            id=graph_id,
            title=graph_data.title,
            description=graph_data.description,
            user_id=graph_data.user_id,
            document_id=graph_data.document_id,
            nodes=graph_data.nodes,
            edges=graph_data.edges,
            metadata=metadata,
            statistics=statistics,
            created_at=datetime.utcnow()
        )
    
    async def get_user_knowledge_graphs(self, user_id: str, db: aiosqlite.Connection) -> List[KnowledgeGraph]:
        """Get all knowledge graphs for a specific user"""
        cursor = await db.execute("""
            SELECT id, title, description, user_id, document_id, nodes, edges, metadata, statistics, created_at
            FROM knowledge_graphs WHERE user_id = ? ORDER BY created_at DESC
        """, (user_id,))
        
        graphs = []
        async for row in cursor:
            graphs.append(KnowledgeGraph(
                id=row[0],  # id
                title=row[1],  # title
                description=row[2],  # description
                user_id=row[3],  # user_id
                document_id=row[4],  # document_id
                nodes=json.loads(row[5]),  # nodes
                edges=json.loads(row[6]),  # edges
                metadata=json.loads(row[7]),  # metadata
                statistics=json.loads(row[8]),  # statistics
                created_at=datetime.fromisoformat(row[9])  # created_at
            ))
        
        return graphs
    
    async def get_knowledge_graph_by_id(self, graph_id: str, user_id: str, db: aiosqlite.Connection) -> Optional[KnowledgeGraph]:
        """Get specific knowledge graph by ID for a user"""
        cursor = await db.execute("""
            SELECT id, title, description, user_id, document_id, nodes, edges, metadata, statistics, created_at
            FROM knowledge_graphs WHERE id = ? AND user_id = ?
        """, (graph_id, user_id))
        
        row = await cursor.fetchone()
        if not row:
            return None
        
        return KnowledgeGraph(
            id=row[0],  # id
            title=row[1],  # title
            description=row[2],  # description
            user_id=row[3],  # user_id
            document_id=row[4],  # document_id
            nodes=json.loads(row[5]),  # nodes
            edges=json.loads(row[6]),  # edges
            metadata=json.loads(row[7]),  # metadata
            statistics=json.loads(row[8]),  # statistics
            created_at=datetime.fromisoformat(row[9])  # created_at
        )
    
    async def save_analysis_result(self, result_data: AnalysisResult, db: aiosqlite.Connection) -> AnalysisResult:
        """Save analysis result to database"""
        result_id = str(uuid.uuid4())
        
        await db.execute("""
            INSERT INTO analysis_results (id, document_id, user_id, relationships, quality_metrics, processing_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            result_id, result_data.document_id, result_data.user_id,
            json.dumps(result_data.relationships), json.dumps(result_data.quality_metrics),
            result_data.processing_time, datetime.utcnow()
        ))
        
        await db.commit()
        
        return AnalysisResult(
            id=result_id,
            document_id=result_data.document_id,
            user_id=result_data.user_id,
            relationships=result_data.relationships,
            quality_metrics=result_data.quality_metrics,
            processing_time=result_data.processing_time,
            created_at=datetime.utcnow()
        )
    
    async def get_user_analysis_results(self, user_id: str, db: aiosqlite.Connection) -> List[AnalysisResult]:
        """Get all analysis results for a specific user"""
        cursor = await db.execute("""
            SELECT id, document_id, user_id, relationships, quality_metrics, processing_time, created_at
            FROM analysis_results WHERE user_id = ? ORDER BY created_at DESC
        """, (user_id,))
        
        results = []
        async for row in cursor:
            results.append(AnalysisResult(
                id=row[0],  # id
                document_id=row[1],  # document_id
                user_id=row[2],  # user_id
                relationships=json.loads(row[3]),  # relationships
                quality_metrics=json.loads(row[4]),  # quality_metrics
                processing_time=row[5],  # processing_time
                created_at=datetime.fromisoformat(row[6])  # created_at
            ))
        
        return results
    
    async def delete_document(self, document_id: str, user_id: str, db: aiosqlite.Connection) -> bool:
        """Delete document and related data"""
        try:
            # Delete RAG/indexing artifacts first
            await db.execute("DELETE FROM chunk_embeddings WHERE document_id = ? AND user_id = ?", (document_id, user_id))
            await db.execute("DELETE FROM graph_relations WHERE document_id = ? AND user_id = ?", (document_id, user_id))
            await db.execute("DELETE FROM graph_entities WHERE document_id = ? AND user_id = ?", (document_id, user_id))
            await db.execute("DELETE FROM document_chunks WHERE document_id = ? AND user_id = ?", (document_id, user_id))

            # Delete related analysis results first
            await db.execute("DELETE FROM analysis_results WHERE document_id = ? AND user_id = ?", (document_id, user_id))
            
            # Delete related knowledge graphs
            await db.execute("DELETE FROM knowledge_graphs WHERE document_id = ? AND user_id = ?", (document_id, user_id))
            
            # Delete the document
            cursor = await db.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id))
            
            await db.commit()
            
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting document: {e}")
            return False

# Global storage service instance
storage_service = StorageService()
