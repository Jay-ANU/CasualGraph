"""
Data models for CausalGraph.AI platform
Defines user authentication and data persistence structures
"""

from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"

class UserBase(BaseModel):
    email: EmailStr
    username: str
    role: UserRole = UserRole.USER

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(UserBase):
    id: str
    created_at: datetime
    is_active: bool = True
    
    class Config:
        from_attributes = True

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    role: UserRole
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str

class DocumentBase(BaseModel):
    title: str
    file_type: str
    file_size: int
    user_id: str

class DocumentCreate(DocumentBase):
    content: str
    original_filename: str

class Document(DocumentBase):
    id: str
    created_at: datetime
    processed_at: Optional[datetime] = None
    content: str
    original_filename: str
    
    class Config:
        from_attributes = True

class KnowledgeGraphBase(BaseModel):
    title: str
    description: Optional[str] = None
    user_id: str
    document_id: str

class KnowledgeGraphCreate(KnowledgeGraphBase):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    metadata: Dict[str, Any]

class KnowledgeGraph(KnowledgeGraphBase):
    id: str
    created_at: datetime
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    statistics: Dict[str, Any]
    
    class Config:
        from_attributes = True

class AnalysisResult(BaseModel):
    id: str
    document_id: str
    user_id: str
    relationships: List[Dict[str, Any]]
    quality_metrics: Dict[str, Any]
    processing_time: float
    created_at: datetime

class CDKActivation(BaseModel):
    id: str
    user_id: str
    cdk_code: str
    activated_at: datetime
    expires_at: datetime
    is_active: bool = True
    
    class Config:
        from_attributes = True

class CDKActivationCreate(BaseModel):
    cdk_code: str

class CDKStatus(BaseModel):
    is_activated: bool
    expires_at: Optional[datetime] = None
    remaining_days: Optional[int] = None


class DocumentUploadResponse(BaseModel):
    document_id: str
    title: str
    file_type: str
    content_length: int
    processing_stats: Dict[str, Any]


class DocumentIngestRequest(BaseModel):
    document_id: str
    company: Optional[str] = None
    source: str = ""
    category: str = "general"
    chunk_size: int = 1400
    chunk_overlap: int = 200
    run_entity_extraction: bool = True
    run_relation_extraction: bool = True


class ChunkMetadata(BaseModel):
    chunk_index: int
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    source: str = ""
    category: str = "general"
    word_count: int = 0
    token_estimate: int = 0


class DocumentChunkCreate(BaseModel):
    id: str
    document_id: str
    user_id: str
    content: str
    metadata: Dict[str, Any]


class DocumentChunk(BaseModel):
    id: str
    document_id: str
    user_id: str
    content: str
    metadata: Dict[str, Any]
    created_at: datetime


class GraphEntityCreate(BaseModel):
    document_id: str
    user_id: str
    name: str
    entity_type: str
    normalized_name: str
    description: str = ""
    chunk_id: Optional[str] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = {}


class GraphEntity(BaseModel):
    id: str
    document_id: str
    user_id: str
    name: str
    entity_type: str
    normalized_name: str
    description: str
    chunk_id: Optional[str] = None
    confidence: float
    metadata: Dict[str, Any]
    created_at: datetime


class GraphRelationCreate(BaseModel):
    document_id: str
    user_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    evidence: str = ""
    chunk_id: Optional[str] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = {}


class GraphRelation(BaseModel):
    id: str
    document_id: str
    user_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    evidence: str
    chunk_id: Optional[str] = None
    confidence: float
    metadata: Dict[str, Any]
    created_at: datetime


class RagRequest(BaseModel):
    question: str
    document_id: Optional[str] = None
    top_k: int = 5


class GraphRagRequest(RagRequest):
    depth: int = 2


class RagCitation(BaseModel):
    chunk_id: str
    document_id: str
    score: float
    excerpt: str
    metadata: Dict[str, Any]


class RagResponse(BaseModel):
    answer: str
    route: str
    citations: List[RagCitation]
    used_mock: bool = False
    enough_context: bool = True


class GraphSubgraphResponse(BaseModel):
    entities: List[GraphEntity]
    relations: List[GraphRelation]
    matched_entity_ids: List[str]
