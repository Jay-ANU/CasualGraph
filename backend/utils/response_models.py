"""
Response models for CausalGraph Platform API
Provides structured and consistent API responses
"""

from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field
from datetime import datetime

class BaseResponse(BaseModel):
    """Base response model for all API endpoints"""
    
    success: bool = Field(..., description="Indicates if the operation was successful")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    message: Optional[str] = Field(None, description="Human-readable message")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ErrorResponse(BaseResponse):
    """Error response model"""
    
    success: bool = Field(False, description="Always false for error responses")
    error_code: str = Field(..., description="Machine-readable error code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    
    class Config:
        schema_extra = {
            "example": {
                "success": False,
                "timestamp": "2024-01-01T00:00:00Z",
                "message": "Document processing failed",
                "error_code": "DOCUMENT_PROCESSING_ERROR",
                "details": {
                    "document_type": "pdf",
                    "reason": "File corrupted"
                }
            }
        }

class SuccessResponse(BaseResponse):
    """Success response model"""
    
    success: bool = Field(True, description="Always true for success responses")
    data: Optional[Dict[str, Any]] = Field(None, description="Response data")

class CausalRelationshipResponse(BaseResponse):
    """Response model for causal relationship extraction"""
    
    success: bool = Field(True, description="Always true for success responses")
    relationships: List[Dict[str, Any]] = Field(..., description="Extracted causal relationships")
    count: int = Field(..., description="Number of relationships extracted")
    processing_time: Optional[float] = Field(None, description="Processing time in seconds")
    confidence_score: Optional[float] = Field(None, description="Overall confidence score")

class DocumentProcessingResponse(BaseResponse):
    """Response model for document processing"""
    
    success: bool = Field(True, description="Always true for success responses")
    document_id: str = Field(..., description="Unique document identifier")
    content_length: int = Field(..., description="Length of extracted content")
    file_type: str = Field(..., description="Type of processed file")
    processing_stats: Dict[str, Any] = Field(..., description="Processing statistics")

class GraphConstructionResponse(BaseResponse):
    """Response model for graph construction"""
    
    success: bool = Field(True, description="Always true for success responses")
    graph_id: str = Field(..., description="Unique graph identifier")
    node_count: int = Field(..., description="Number of nodes in the graph")
    edge_count: int = Field(..., description="Number of edges in the graph")
    graph_metadata: Dict[str, Any] = Field(..., description="Graph metadata and statistics")

class HealthCheckResponse(BaseResponse):
    """Response model for health check endpoint"""
    
    success: bool = Field(True, description="Always true for health check")
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    uptime: Optional[float] = Field(None, description="Service uptime in seconds")
    dependencies: Dict[str, str] = Field(..., description="Dependency status")

class PaginatedResponse(BaseResponse):
    """Response model for paginated results"""
    
    success: bool = Field(True, description="Always true for success responses")
    data: List[Dict[str, Any]] = Field(..., description="Paginated data")
    pagination: Dict[str, Any] = Field(..., description="Pagination information")
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "timestamp": "2024-01-01T00:00:00Z",
                "data": [],
                "pagination": {
                    "page": 1,
                    "per_page": 10,
                    "total": 0,
                    "pages": 0
                }
            }
        }
