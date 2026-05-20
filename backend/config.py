"""
Configuration module for CausalGraph platform
Provides centralized configuration management for the application
"""

import os
from typing import Optional, List
from dotenv import load_dotenv


load_dotenv()

class Config:
    """
    Centralized configuration class for the CausalGraph platform
    Manages environment variables and application settings
    """
    
    # API Configuration
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.1"))
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "1500"))
    OPENAI_EMBEDDING_MODEL: str = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    MOCK_MODE: bool = os.getenv("MOCK_MODE", "False").lower() == "true"
    AI_SERVICE_URL: str = os.getenv("AI_SERVICE_URL", "http://localhost:8000")
    AI_SERVICE_TIMEOUT: float = float(os.getenv("AI_SERVICE_TIMEOUT", "120"))
    PREFER_LOCAL_AI_EXTRACTION: bool = os.getenv("PREFER_LOCAL_AI_EXTRACTION", "True").lower() == "true"
    
    # CDK Configuration
    CDK_ENABLED: bool = os.getenv("CDK_ENABLED", "True").lower() == "true"
    CDK_CODES: List[str] = os.getenv("CDK_CODES", "DEMO123,PRO123,ENTERPRISE456").split(",")
    CDK_EXPIRY_DAYS: int = int(os.getenv("CDK_EXPIRY_DAYS", "365"))
    
    # Server Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    
    # CORS Configuration
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ]
    
    # Graph Processing Configuration
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.8"))
    MAX_GRAPH_SIZE: int = int(os.getenv("MAX_GRAPH_SIZE", "10000"))
    GRAPH_DEFAULT_DEPTH: int = int(os.getenv("GRAPH_DEFAULT_DEPTH", "2"))

    # Text Processing Configuration
    MIN_CONCEPT_LENGTH: int = int(os.getenv("MIN_CONCEPT_LENGTH", "3"))
    MAX_CONCEPT_LENGTH: int = int(os.getenv("MAX_CONCEPT_LENGTH", "100"))
    ENABLE_SPACY: bool = os.getenv("ENABLE_SPACY", "True").lower() == "true"
    DEFAULT_CHUNK_SIZE: int = int(os.getenv("DEFAULT_CHUNK_SIZE", "1400"))
    DEFAULT_CHUNK_OVERLAP: int = int(os.getenv("DEFAULT_CHUNK_OVERLAP", "200"))
    DEFAULT_TOP_K: int = int(os.getenv("DEFAULT_TOP_K", "5"))
    MIN_RAG_SCORE: float = float(os.getenv("MIN_RAG_SCORE", "0.15"))
    HASH_EMBEDDING_DIM: int = int(os.getenv("HASH_EMBEDDING_DIM", "256"))

    # File Processing Configuration
    MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB
    SUPPORTED_FILE_TYPES: List[str] = ["pdf", "docx", "txt", "rtf", "md", "markdown"]
    
    @classmethod
    def validate(cls) -> bool:
        """
        Validate essential configuration parameters
        
        Returns:
            bool: True if configuration is valid, False otherwise
        """
        if not cls.OPENAI_API_KEY:
            print("Warning: OPENAI_API_KEY environment variable not set")
            return False
        return True
    
    @classmethod
    def get_openai_config(cls) -> dict:
        """
        Get OpenAI configuration parameters as dictionary
        
        Returns:
            dict: OpenAI configuration parameters
        """
        return {
            "model": cls.OPENAI_MODEL,
            "temperature": cls.OPENAI_TEMPERATURE,
            "max_tokens": cls.OPENAI_MAX_TOKENS
        }

    @classmethod
    def use_mock_mode(cls) -> bool:
        """Return True when the system should avoid external LLM dependencies."""
        return cls.MOCK_MODE or not cls.OPENAI_API_KEY
