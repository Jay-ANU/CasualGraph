"""
Custom exception classes for CausalGraph Platform
Provides structured error handling and meaningful error messages
"""

from typing import Optional, Dict, Any

class CausalGraphException(Exception):
    """Base exception class for CausalGraph Platform"""
    
    def __init__(self, message: str, error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary format"""
        return {
            "error": True,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details
        }

class DocumentProcessingError(CausalGraphException):
    """Exception raised when document processing fails"""
    
    def __init__(self, message: str, document_type: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "DOCUMENT_PROCESSING_ERROR", details)
        self.document_type = document_type

class TextExtractionError(CausalGraphException):
    """Exception raised when text extraction fails"""
    
    def __init__(self, message: str, extraction_method: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "TEXT_EXTRACTION_ERROR", details)
        self.extraction_method = extraction_method

class CausalRelationshipError(CausalGraphException):
    """Exception raised when causal relationship extraction fails"""
    
    def __init__(self, message: str, domain: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "CAUSAL_RELATIONSHIP_ERROR", details)
        self.domain = domain

class GraphConstructionError(CausalGraphException):
    """Exception raised when graph construction fails"""
    
    def __init__(self, message: str, graph_type: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "GRAPH_CONSTRUCTION_ERROR", details)
        self.graph_type = graph_type

class ValidationError(CausalGraphException):
    """Exception raised when data validation fails"""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Optional[Any] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "VALIDATION_ERROR", details)
        self.field = field
        self.value = value

class ConfigurationError(CausalGraphException):
    """Exception raised when configuration is invalid"""
    
    def __init__(self, message: str, config_key: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, "CONFIGURATION_ERROR", details)
        self.config_key = config_key
