"""Central settings for the root-level ESG analysis pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv


os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _resolve_project_path(value: str) -> Path:
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


DATA_DIR = _resolve_project_path(os.getenv("DATA_DIR", "data"))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CHUNK_DIR = DATA_DIR / "chunks"
GRAPH_DIR = DATA_DIR / "graph"
VECTOR_DIR = DATA_DIR / "vector_store"

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
INGESTION_JOB_MAX_WORKERS = max(1, int(os.getenv("INGESTION_JOB_MAX_WORKERS", "4")))
INGESTION_MAX_QUEUED_JOBS = max(1, int(os.getenv("INGESTION_MAX_QUEUED_JOBS", "16")))
INGESTION_AUDIT_THROTTLE_SECONDS = max(0.0, float(os.getenv("INGESTION_AUDIT_THROTTLE_SECONDS", "2.0")))

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
LOCAL_EMBEDDING_MODEL_DIR = PROJECT_ROOT / "models" / "BAAI_bge-m3"
EMBEDDING_MODEL = DEFAULT_EMBEDDING_MODEL
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "local").strip().lower()
EMBEDDING_LOCAL_FILES_ONLY = os.getenv("ESG_EMBEDDING_LOCAL_FILES_ONLY", "False").lower() == "true"
EMBEDDING_ALLOW_DOWNLOAD = os.getenv("ESG_EMBEDDING_ALLOW_DOWNLOAD", "False").lower() == "true"
EMBEDDING_FALLBACK_DIM = int(os.getenv("ESG_EMBEDDING_FALLBACK_DIM", "384"))
DEEPINFRA_API_KEY = os.getenv("DEEPINFRA_API_KEY", "").strip()
DEEPINFRA_BASE_URL = os.getenv("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai").strip()
DEEPINFRA_EMBEDDING_MODEL = os.getenv("DEEPINFRA_EMBEDDING_MODEL", "BAAI/bge-m3").strip()

VECTOR_STORE_PROVIDER = os.getenv("VECTOR_STORE_PROVIDER", "local").strip().lower()
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "")
PINECONE_INDEX_HOST = os.getenv("PINECONE_INDEX_HOST", "")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "default")
PINECONE_METRIC = os.getenv("PINECONE_METRIC", "cosine")
PINECONE_UPSERT_BATCH_SIZE = max(1, int(os.getenv("PINECONE_UPSERT_BATCH_SIZE", "50")))
PINECONE_QUERY_TOP_K_CAP = max(1, int(os.getenv("PINECONE_QUERY_TOP_K_CAP", "20")))

NEO4J_URI = os.getenv("NEO4J_URI", "").strip()
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j").strip()
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "").strip()
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j").strip()
NEO4J_AUTO_SYNC = os.getenv("NEO4J_AUTO_SYNC", "True").lower() == "true"

ACTIVE_VECTOR_STORE_FILE = VECTOR_DIR / "active_store_path.txt"

DOCUMENT_REGISTRY_FILE = DATA_DIR / "documents" / "registry.json"
DOCUMENT_DEDUP_ENABLED = os.getenv("DOCUMENT_DEDUP_ENABLED", "true").lower() == "true"


def resolve_embedding_model_path() -> str:
    """Resolve the preferred embedding model path or model id."""
    env_path = os.getenv("ESG_EMBEDDING_MODEL_PATH")
    if env_path:
        return str(_resolve_project_path(env_path))
    if LOCAL_EMBEDDING_MODEL_DIR.exists():
        return str(LOCAL_EMBEDDING_MODEL_DIR)
    return EMBEDDING_MODEL


EMBEDDING_MODEL_PATH = resolve_embedding_model_path()


def neo4j_configured() -> bool:
    """Return whether Neo4j credentials are available."""
    return bool(NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD)


# The provider is explicit: leftover OpenAI/Anthropic secrets must not silently
# select a paid provider. OPENAI_* below are transport aliases for old callers,
# not another provider selection mechanism. Embeddings keep their own client.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
if LLM_PROVIDER not in {"deepseek", "openai"}:
    raise ValueError("LLM_PROVIDER must be deepseek or openai")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip() or "https://api.deepseek.com"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro").strip() or "deepseek-v4-pro"
DEEPSEEK_TIMEOUT = float(os.getenv("DEEPSEEK_TIMEOUT", "60"))


def chat_model_override(name: str, fallback: str) -> str:
    """Ignore stale GPT/Claude model overrides when migrating to DeepSeek."""
    value = os.getenv(name, "").strip()
    if LLM_PROVIDER == "deepseek" and not value.lower().startswith("deepseek-"):
        return fallback
    return value or fallback


OPENAI_API_KEY = DEEPSEEK_API_KEY if LLM_PROVIDER == "deepseek" else os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = DEEPSEEK_BASE_URL if LLM_PROVIDER == "deepseek" else os.getenv("OPENAI_BASE_URL", "").strip()
OPENAI_MODEL = DEEPSEEK_MODEL if LLM_PROVIDER == "deepseek" else os.getenv("OPENAI_MODEL", "gpt-4").strip()
OPENAI_TEMPERATURE = float(os.getenv("CHAT_TEMPERATURE", os.getenv("OPENAI_TEMPERATURE", "0.1")))
OPENAI_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", os.getenv("OPENAI_MAX_TOKENS", "2048")))
OPENAI_TIMEOUT = DEEPSEEK_TIMEOUT if LLM_PROVIDER == "deepseek" else float(os.getenv("OPENAI_TIMEOUT", "60"))
RAG_ANSWER_MODE = os.getenv("RAG_ANSWER_MODE", LLM_PROVIDER).strip().lower()
# Older production .env files often contain RAG_ANSWER_MODE=openai.
if LLM_PROVIDER == "deepseek" and RAG_ANSWER_MODE in {"auto", "openai"}:
    RAG_ANSWER_MODE = "deepseek"

RAG_ALLOW_SPECULATION = os.getenv("RAG_ALLOW_SPECULATION", "False").lower() == "true"
RAG_USE_GRAPH_CONTEXT = os.getenv("RAG_USE_GRAPH_CONTEXT", "True").lower() == "true"
RAG_GRAPH_CONTEXT_HOPS = int(os.getenv("RAG_GRAPH_CONTEXT_HOPS", "2"))
RAG_GRAPH_CONTEXT_LIMIT = int(os.getenv("RAG_GRAPH_CONTEXT_LIMIT", "10"))
RAG_GRAPH_CONTEXT_MAX_TRIPLES = int(os.getenv("RAG_GRAPH_CONTEXT_MAX_TRIPLES", "25"))
RAG_GRAPH_CONTEXT_MIN_SOURCES = max(0, int(os.getenv("RAG_GRAPH_CONTEXT_MIN_SOURCES", "0")))
RAG_MIN_SOURCE_RELEVANCE = max(0.0, min(1.0, float(os.getenv("RAG_MIN_SOURCE_RELEVANCE", "0.35"))))
RAG_MULTI_QUERY_ENABLED = os.getenv("RAG_MULTI_QUERY_ENABLED", "false").lower() == "true"
RAG_MULTI_QUERY_N = max(1, int(os.getenv("RAG_MULTI_QUERY_N", "3")))
RAG_HYBRID_ENABLED = os.getenv("RAG_HYBRID_ENABLED", "false").lower() == "true"
RAG_HYBRID_BM25_WEIGHT = float(os.getenv("RAG_HYBRID_BM25_WEIGHT", "0.4"))
RAG_HYBRID_FUSION = os.getenv("RAG_HYBRID_FUSION", "rrf").strip().lower()
RAG_RRF_K = max(1, int(os.getenv("RAG_RRF_K", "60")))
RAG_RRF_VECTOR_WEIGHT = max(0.0, float(os.getenv("RAG_RRF_VECTOR_WEIGHT", "1.0")))
RAG_RRF_BM25_WEIGHT = max(0.0, float(os.getenv("RAG_RRF_BM25_WEIGHT", "1.0")))
RAG_RRF_TERM_BOOST = max(0.0, float(os.getenv("RAG_RRF_TERM_BOOST", "0.01")))
RAG_RRF_DIVERSITY_PENALTY = max(0.0, float(os.getenv("RAG_RRF_DIVERSITY_PENALTY", "0.0")))
RERANKER_ENABLED = os.getenv("RERANKER_ENABLED", "false").lower() == "true"
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3").strip()
RERANKER_TOP_K_BEFORE = max(1, int(os.getenv("RERANKER_TOP_K_BEFORE", "20")))
RERANKER_TOP_K_AFTER = max(1, int(os.getenv("RERANKER_TOP_K_AFTER", "5")))
HYDE_ENABLED = os.getenv("HYDE_ENABLED", "false").lower() == "true"
HYDE_MODEL = chat_model_override("HYDE_MODEL", OPENAI_MODEL)
HYDE_MAX_TOKENS = max(32, int(os.getenv("HYDE_MAX_TOKENS", "200")))
HYDE_MIN_CHARS = max(1, int(os.getenv("HYDE_MIN_CHARS", "50")))
RAG_DECOMPOSE_ENABLED = os.getenv("RAG_DECOMPOSE_ENABLED", "false").lower() == "true"
RAG_DECOMPOSE_MAX_SUBQ = max(1, int(os.getenv("RAG_DECOMPOSE_MAX_SUBQ", "3")))
RAG_ROUTER_ENABLED = os.getenv("RAG_ROUTER_ENABLED", "true").lower() == "true"
RAG_ROUTER_LLM_ENABLED = os.getenv("RAG_ROUTER_LLM_ENABLED", "false").lower() == "true"
RAG_CHITCHAT_ENABLED = os.getenv("RAG_CHITCHAT_ENABLED", "true").lower() == "true"
RAG_ANSWER_INTENT_ROUTER_ENABLED = os.getenv("RAG_ANSWER_INTENT_ROUTER_ENABLED", "true").lower() == "true"

NOTIFICATIONS_ENABLED = os.getenv("NOTIFICATIONS_ENABLED", "false").lower() == "true"
NOTIFICATIONS_DB_PATH = os.getenv("NOTIFICATIONS_DB_PATH", "").strip() or str(DATA_DIR / "notifications.db")
NOTIFICATIONS_DEDUP_WINDOW_MINUTES = int(os.getenv("NOTIFICATIONS_DEDUP_WINDOW_MINUTES", "60"))
NOTIFICATIONS_DAILY_EMAIL_CAP = int(os.getenv("NOTIFICATIONS_DAILY_EMAIL_CAP", "8"))
NOTIFICATIONS_SMTP_URL = os.getenv("NOTIFICATIONS_SMTP_URL")
NOTIFICATIONS_ADMIN_EMAILS = os.getenv("NOTIFICATIONS_ADMIN_EMAILS", "")

MCP_EMAIL_ENABLED = os.getenv("MCP_EMAIL_ENABLED", "false").lower() == "true"
MCP_EMAIL_DRY_RUN = os.getenv("MCP_EMAIL_DRY_RUN", "true").lower() == "true"
MCP_EMAIL_ALLOWED_RECIPIENTS = os.getenv("MCP_EMAIL_ALLOWED_RECIPIENTS", "")
MCP_EMAIL_ALLOW_ALL = os.getenv("MCP_EMAIL_ALLOW_ALL", "false").lower() == "true"
MCP_EMAIL_AUDIT_PATH = Path(os.getenv("MCP_EMAIL_AUDIT_PATH", "./data/mcp_email_audit.jsonl"))
MCP_EMAIL_MAX_BODY_CHARS = max(1, int(os.getenv("MCP_EMAIL_MAX_BODY_CHARS", "12000")))

REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
REDIS_CHAT_SESSION_TTL_SECONDS = max(3600, int(os.getenv("REDIS_CHAT_SESSION_TTL_SECONDS", "604800")))
REDIS_CHAT_MAX_MESSAGES = max(6, int(os.getenv("REDIS_CHAT_MAX_MESSAGES", "20")))
REDIS_CHAT_HISTORY_LIMIT = max(4, int(os.getenv("REDIS_CHAT_HISTORY_LIMIT", "8")))


def openai_configured() -> bool:
    """Return whether the selected chat transport has credentials."""
    return bool(OPENAI_API_KEY)


# -----------------------------------------------------------------------------
# Fast / Deep share DeepSeek V4 Pro by default; Deep enables reasoning.
# Legacy Anthropic code is retained only for explicit LLM_PROVIDER=openai rollback.
# -----------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "").strip()
RAG_DEEP_MODEL = chat_model_override("RAG_DEEP_MODEL", DEEPSEEK_MODEL if LLM_PROVIDER == "deepseek" else "claude-opus-4-7")
RAG_DEEP_MAX_TOKENS = int(os.getenv("RAG_DEEP_MAX_TOKENS", "16384"))
RAG_DEEP_REASONING_EFFORT = os.getenv("RAG_DEEP_REASONING_EFFORT", "high").strip().lower()
if RAG_DEEP_REASONING_EFFORT not in {"low", "high", "max"}:
    raise ValueError("RAG_DEEP_REASONING_EFFORT must be low, high, or max")
RAG_DEEP_TEMPERATURE = float(os.getenv("RAG_DEEP_TEMPERATURE", "0.2"))
RAG_DEEP_TIMEOUT = float(os.getenv("RAG_DEEP_TIMEOUT", "120"))


def anthropic_configured() -> bool:
    """Return whether the Deep-tier Anthropic backend is configured."""
    return bool(ANTHROPIC_API_KEY)


DEEPSEEK_CACHE_ENABLED = os.getenv("DEEPSEEK_CACHE_ENABLED", "true").lower() == "true"
DEEPSEEK_CACHE_TTL_SECONDS = max(1, int(os.getenv("DEEPSEEK_CACHE_TTL_SECONDS", "1800")))
DEEPSEEK_FAILURE_CACHE_TTL_SECONDS = max(1, int(os.getenv("DEEPSEEK_FAILURE_CACHE_TTL_SECONDS", "60")))
DEEPSEEK_CIRCUIT_FAILURE_THRESHOLD = max(1, int(os.getenv("DEEPSEEK_CIRCUIT_FAILURE_THRESHOLD", "3")))
DEEPSEEK_CIRCUIT_BREAK_SECONDS = max(1, int(os.getenv("DEEPSEEK_CIRCUIT_BREAK_SECONDS", "60")))
RAG_ANSWER_INTENT_ROUTER_MODEL = os.getenv("RAG_ANSWER_INTENT_ROUTER_MODEL", DEEPSEEK_MODEL).strip()
RAG_ANSWER_INTENT_ROUTER_TIMEOUT = float(os.getenv("RAG_ANSWER_INTENT_ROUTER_TIMEOUT", "2"))
RAG_ANSWER_INTENT_ROUTER_MAX_TOKENS = int(os.getenv("RAG_ANSWER_INTENT_ROUTER_MAX_TOKENS", "240"))
RAG_HYBRID_AGENT_ROUTER_LLM_ENABLED = os.getenv("RAG_HYBRID_AGENT_ROUTER_LLM_ENABLED", "true").lower() == "true"
RAG_HYBRID_AGENT_ROUTER_MODEL = os.getenv("RAG_HYBRID_AGENT_ROUTER_MODEL", DEEPSEEK_MODEL).strip()
RAG_HYBRID_AGENT_ROUTER_TIMEOUT = float(os.getenv("RAG_HYBRID_AGENT_ROUTER_TIMEOUT", "3"))
RAG_HYBRID_AGENT_ROUTER_MAX_TOKENS = int(os.getenv("RAG_HYBRID_AGENT_ROUTER_MAX_TOKENS", "260"))
RAG_ROUTER_MODEL = os.getenv("RAG_ROUTER_MODEL", DEEPSEEK_MODEL).strip()
RAG_ROUTER_TIMEOUT = float(os.getenv("RAG_ROUTER_TIMEOUT", "2"))
RAG_ROUTER_MAX_TOKENS = int(os.getenv("RAG_ROUTER_MAX_TOKENS", "160"))


def deepseek_configured() -> bool:
    """Return whether the root pipeline has a DeepSeek extraction backend configured."""
    return bool(DEEPSEEK_API_KEY and DEEPSEEK_BASE_URL and DEEPSEEK_MODEL)


def ensure_directories() -> None:
    """Create the standard project data directories when missing."""
    for directory in (
        DATA_DIR,
        RAW_DIR,
        PROCESSED_DIR,
        CHUNK_DIR,
        GRAPH_DIR,
        VECTOR_DIR,
        DOCUMENT_REGISTRY_FILE.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)


ensure_directories()
