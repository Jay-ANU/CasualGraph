# CausalGraph AI

> **Project direction:** this codebase is being rebuilt into a legal contract-review agent (clause-by-clause review for in-house counsel).
> The agreed direction, decisions and phase briefs are in [docs/legal-agent/00-alignment.md](docs/legal-agent/00-alignment.md).

> **Research Desk + DeepSeek V4 Pro upgrade:** the default backend no longer needs Claude or OpenAI credits. Fast answers explicitly disable thinking; Deep enables it. See [migration and verification](docs/deepseek-v4-upgrade.md) before deploying.

[GitHub Repository](https://github.com/Jay-ANU/CasualGraph) | [Live App](https://casualgraphai.vercel.app)

CausalGraph AI is an open-source ESG intelligence application for turning long-form corporate reports into searchable evidence, graph context, and cited agent answers.

The project combines a React frontend, a FastAPI backend, retrieval-augmented generation, optional graph persistence, short-term Redis chat memory, and configurable model providers. It is designed to run locally for development and on production platforms such as Vercel, Fly.io, Pinecone, Redis, and Neo4j Aura.

This repository contains the application code and configuration templates. It does not include private API keys, uploaded reports, runtime databases, hosted vector indexes, Neo4j data, or large model weights.

## Core Features

- ESG report ingestion: upload PDFs, DOCX files, or plain text and convert them into cleaned, overlapping chunks.
- Retrieval-augmented chat: answer questions from retrieved report evidence instead of unconstrained model memory.
- Streaming responses: `/rag/ask/stream` supports incremental frontend rendering for the agent page.
- Citations: responses can include retrieved chunk references, source metadata, and graph-backed evidence.
- Fast / Deep reasoning tiers: both default to DeepSeek V4 Pro over its OpenAI-compatible API; Fast disables thinking and Deep enables it. OpenAI or Anthropic are used only after an explicit `LLM_PROVIDER=openai` rollback.
- Contextual follow-ups: Redis-backed sessions preserve short-term chat state, selected document context, and recent messages.
- Entity-aware document scoping: follow-up questions can use prior conversation entities to avoid retrieving from the wrong company or report.
- Graph APIs (admin): inspect Neo4j status, entity neighborhoods, and subgraphs when Neo4j is configured.
- Hybrid retrieval controls: vector search, BM25 fusion, multi-query expansion, HyDE, reranking, graph context, and decomposition are all environment-controlled.
- Admin and audit surfaces: login, admin allowlists, upload monitoring, feedback capture, and notification hooks.
- Production deployment support: Vercel frontend, Fly.io backend, persistent Fly volume, optional embedded Redis, and external Pinecone / Neo4j services.

## Architecture

```text
React frontend
  |
  | VITE_API_BASE
  v
FastAPI backend (app.py)
  |
  |-- Auth, admin, feedback, document APIs
  |-- PDF/text ingestion and async job tracking
  |-- RAG ask / stream endpoints
  |-- Admin Neo4j graph APIs (optional)
  |
  |-- SQLite files for auth / feedback / local metadata
  |-- Redis for short-term chat memory
  |-- Local FAISS or Pinecone for vector search
  |-- Neo4j for optional graph persistence
  |-- OpenAI / Anthropic / DeepSeek / DeepInfra for model-backed work
```

The maintained public deployment currently uses:

- Frontend: Vercel, `https://casualgraphai.vercel.app`
- Backend: Fly.io, `https://casualgraph.fly.dev`
- Backend region: Sydney (`syd`)
- Persistent backend storage: Fly volume mounted at `/data`
- Redis: optional Redis server started inside the backend container when `REDIS_ENABLED=true`
- Embeddings: local model or DeepInfra, depending on deployment configuration
- Vector store: local store or Pinecone
- Graph store: optional Neo4j

## Repository Layout

```text
.
├── app.py                         # FastAPI entrypoint: create_app(), middleware, startup, routers
├── api/
│   ├── deps.py                    # Auth / DB dependencies shared by routers
│   └── routers/                   # auth, admin, documents, chat, memory, rag, feedback, graph, system
├── services/                      # db, auth, rate_limit, document_access, rag_context, memory
├── requirements.txt               # Python backend dependencies
├── pyproject.toml                 # Ruff gate (syntax errors and undefined names)
├── Dockerfile                     # Fly.io backend image
├── fly.toml                       # Fly.io backend app config
├── docker-compose.yml             # Local Neo4j helper
├── configs/
│   └── settings.py                # Runtime configuration loader
├── document_processing/           # PDF parsing, cleaning, chunking
├── graph/                         # Optional Neo4j store (admin graph APIs, graph context)
├── legal/                         # Legal-review building blocks (legacy Word review helpers)
├── rag/                           # Embeddings, vector stores, retrieval, answering
├── scripts/                       # Pipeline and deployment helper scripts
├── frontend/                      # React application
├── data/                          # Runtime data directories, mostly gitignored
└── models/                        # Optional local embedding models, gitignored
```

## Quick Start

### 1. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 -m uvicorn app:app --host 127.0.0.1 --port 8000
```

The backend listens on `http://127.0.0.1:8000` by default. Keep operational health checks private to local development or platform infrastructure.

For a useful local RAG setup, configure at least one real embedding backend and one answer model in `.env`. The fastest hosted setup is typically:

```bash
EMBEDDING_BACKEND=deepinfra
DEEPINFRA_API_KEY=your_deepinfra_key
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_MODEL=deepseek-v4-pro
VECTOR_STORE_PROVIDER=local
```

### 2. Frontend

```bash
cd frontend
npm install
VITE_API_BASE=http://127.0.0.1:8000 npm run dev
```

The React app starts on `http://localhost:3000` by default. In production, set `VITE_API_BASE` to the deployed backend URL before building.

### 3. Optional Local Neo4j

```bash
docker compose up -d neo4j
```

Then use:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j123
NEO4J_DATABASE=neo4j
NEO4J_AUTO_SYNC=true
```

## Runtime Configuration

Configuration is read from environment variables and from a local `.env` file through `configs/settings.py`. Copy `.env.example` first, then fill in only the providers you use.

Never commit `.env`, API keys, database files, report uploads, local vector stores, Redis dumps, model weights, or Pinecone / Neo4j credentials.

### Core App And Security

| Variable | Required | Description |
| --- | --- | --- |
| `APP_ENV` | Production | Use `development`, `staging`, or `production`. Production and staging enforce a strong JWT secret. |
| `JWT_SECRET` | Production | Secret used to sign auth tokens. Must be non-default and at least 32 characters in production or staging. |
| `AUTH_DB_PATH` | Optional | SQLite auth database path. Useful on Fly when pointing to `/data/auth.db`. |
| `CAUSALGRAPH_DB_PATH` | Optional | Answer-feedback SQLite path. Defaults to `DATA_DIR/causalgraph.db` (`/data/causalgraph.db` on Fly). |
| `DATA_DIR` | Optional | Runtime data root. Defaults to `data`; production can use `/data`. |
| `CORS_ALLOW_ORIGINS` | Production | Comma-separated frontend origins, for example `https://casualgraphai.vercel.app`. |
| `CORS_ALLOW_ORIGIN_REGEX` | Optional | Regex for temporary tunnel origins during demos. |
| `ADMIN_EMAILS` | Optional | Comma-separated admin allowlist for `/admin`. |

### Document Ingestion

| Variable | Default | Description |
| --- | --- | --- |
| `CHUNK_SIZE` | `1500` | Target chunk size for report text. |
| `CHUNK_OVERLAP` | `150` | Overlap between adjacent chunks. |
| `INGESTION_JOB_MAX_WORKERS` | `4` | Concurrent async ingestion jobs. |
| `INGESTION_MAX_QUEUED_JOBS` | `16` | Maximum queued ingestion jobs. |
| `INGESTION_AUDIT_THROTTLE_SECONDS` | `2.0` | Throttles ingestion audit updates. |
| `DOCUMENT_DEDUP_ENABLED` | `true` | Prevents duplicated document registry entries when supported. |

### Model Backends

| Variable | Default | Description |
| --- | --- | --- |
| `LLM_PROVIDER` | `deepseek` | Explicit chat provider. Legacy `openai` must be selected deliberately. |
| `CHAT_MAX_TOKENS` | `2048` | Normal answer output budget. |
| `OPENAI_API_KEY` | empty | Legacy only when `LLM_PROVIDER=openai`. |
| `OPENAI_MODEL` | `gpt-4` | Legacy env only. Internal OPENAI_* variables alias the selected compatible transport. |
| `OPENAI_BASE_URL` | empty | Optional OpenAI-compatible base URL. |
| `OPENAI_TEMPERATURE` | `0.1` | Default answer temperature. |
| `OPENAI_MAX_TOKENS` | `2048` | Legacy alias, overridden by `CHAT_MAX_TOKENS`. |
| `OPENAI_TIMEOUT` | `60` | Provider timeout in seconds. |
| `ANTHROPIC_API_KEY` | empty | Legacy Deep only with explicit `LLM_PROVIDER=openai`; never required by default. |
| `ANTHROPIC_BASE_URL` | empty | Optional Anthropic-compatible base URL. |
| `RAG_DEEP_MODEL` | `deepseek-v4-pro` | Deep reasoning model; stale GPT/Claude overrides are ignored with DeepSeek selected. |
| `RAG_DEEP_MAX_TOKENS` | `16384` | Combined reasoning and answer budget. |
| `RAG_DEEP_REASONING_EFFORT` | `high` | `low`, `high`, or `max`; DeepSeek thinking mode only. |
| `RAG_DEEP_TEMPERATURE` | `0.2` | Legacy only; omitted for DeepSeek thinking. |
| `RAG_DEEP_TIMEOUT` | `120` | Deep provider timeout in seconds. |
| `DEEPSEEK_API_KEY` | empty | Enables DeepSeek chat, Deep reasoning and routing. |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek OpenAI-compatible endpoint. |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | General DeepSeek model setting. |

### Embeddings And Vector Stores

| Variable | Default | Description |
| --- | --- | --- |
| `EMBEDDING_BACKEND` | `local` | `local` or `deepinfra`. Use `deepinfra` for lightweight hosted deployments. |
| `ESG_EMBEDDING_MODEL_PATH` | empty | Local embedding model path. If empty, the code looks for `models/BAAI_bge-m3`. |
| `ESG_EMBEDDING_LOCAL_FILES_ONLY` | `false` | Restrict local embedding loading to cached files. |
| `ESG_EMBEDDING_ALLOW_DOWNLOAD` | `false` | Explicit opt-in for embedding model downloads. |
| `DEEPINFRA_API_KEY` | empty | Required when `EMBEDDING_BACKEND=deepinfra`. |
| `DEEPINFRA_BASE_URL` | `https://api.deepinfra.com/v1/openai` | OpenAI-compatible DeepInfra base URL. |
| `DEEPINFRA_EMBEDDING_MODEL` | `BAAI/bge-m3` | Hosted embedding model. Expected dimension is 1024. |
| `VECTOR_STORE_PROVIDER` | `local` | `local` or `pinecone`. |
| `PINECONE_API_KEY` | empty | Required for Pinecone. |
| `PINECONE_INDEX_NAME` | empty | Pinecone index name. |
| `PINECONE_INDEX_HOST` | empty | Optional dedicated Pinecone host. Use this when Pinecone provides one. |
| `PINECONE_NAMESPACE` | `esg-demo` in example | Namespace for indexed report chunks. |
| `PINECONE_METRIC` | `cosine` | Create Pinecone indexes with cosine metric for `bge-m3`. |
| `PINECONE_UPSERT_BATCH_SIZE` | `50` | Vector upsert batch size. |
| `PINECONE_QUERY_TOP_K_CAP` | `20` | Safety cap for Pinecone query size. |

For `BAAI/bge-m3`, create a Pinecone dense index with:

- Dimension: `1024`
- Metric: `cosine`

### Retrieval And Answer Behavior

| Variable | Default | Description |
| --- | --- | --- |
| `RAG_ANSWER_MODE` | `deepseek` | Explicit remote policy; no accidental local 7B model load when a key is missing. |
| `RAG_ALLOW_SPECULATION` | `false` | When false, the agent should refuse unsupported answers instead of inventing. |
| `RAG_USE_GRAPH_CONTEXT` | `true` | Adds graph context when available. |
| `RAG_GRAPH_CONTEXT_HOPS` | `2` | Graph expansion depth. |
| `RAG_GRAPH_CONTEXT_LIMIT` | `10` | Max graph records included. |
| `RAG_GRAPH_CONTEXT_MAX_TRIPLES` | `25` | Max graph triples in prompt context. |
| `RAG_MULTI_QUERY_ENABLED` | `false` | Generates multiple retrieval queries. |
| `RAG_MULTI_QUERY_N` | `3` | Number of generated retrieval queries. |
| `RAG_HYBRID_ENABLED` | `false` | Enables vector + BM25 fusion. |
| `RAG_HYBRID_BM25_WEIGHT` | `0.4` | BM25 weight for hybrid retrieval. |
| `RAG_HYBRID_FUSION` | `rrf` | Fusion strategy. |
| `RAG_RRF_K` | `60` | Reciprocal rank fusion constant. |
| `RAG_RRF_VECTOR_WEIGHT` | `1.0` | Vector score weight. |
| `RAG_RRF_BM25_WEIGHT` | `1.0` | BM25 score weight. |
| `RAG_RRF_TERM_BOOST` | `0.01` | Term match boost. |
| `RAG_RRF_DIVERSITY_PENALTY` | `0.0` | Reduces repeated chunks from dominating results. |
| `RERANKER_ENABLED` | `false` | Enables reranking. |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | Reranker model name. |
| `RERANKER_TOP_K_BEFORE` | `20` | Candidate count before reranking. |
| `RERANKER_TOP_K_AFTER` | `5` | Candidate count after reranking. |
| `HYDE_ENABLED` | `false` | Enables hypothetical document expansion. |
| `HYDE_MODEL` | `gpt-5.4-mini` | Model used for HyDE text. |
| `HYDE_MAX_TOKENS` | `200` | HyDE generation cap. |
| `HYDE_MIN_CHARS` | `50` | Minimum query length before HyDE applies. |
| `RAG_DECOMPOSE_ENABLED` | `false` | Decomposes complex questions into subquestions. |
| `RAG_DECOMPOSE_MAX_SUBQ` | `3` | Max subquestions. |
| `RAG_ROUTER_ENABLED` | `true` | Enables route selection between chat, retrieval, prediction, and refusal paths. |
| `RAG_ROUTER_LLM_ENABLED` | `false` | Uses an LLM for routing when enabled. |
| `RAG_CHITCHAT_ENABLED` | `true` | Allows lightweight non-RAG conversation where appropriate. |

### Redis Short-Term Memory

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_ENABLED` | `false` | Enables Redis-backed chat sessions and follow-up memory. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string. |
| `REDIS_PASSWORD` | empty | Required by `scripts/fly_start.sh` when starting embedded Redis on Fly. |
| `REDIS_CHAT_SESSION_TTL_SECONDS` | `604800` | Session TTL. Minimum enforced value is one hour. |
| `REDIS_CHAT_MAX_MESSAGES` | `20` | Max stored messages per session. |
| `REDIS_CHAT_HISTORY_LIMIT` | `8` | Recent messages included for contextual follow-up rewriting. |

For Fly deployments using the bundled Redis startup script, set:

```bash
REDIS_ENABLED=true
REDIS_PASSWORD=your_strong_redis_password
REDIS_URL=redis://:your_strong_redis_password@127.0.0.1:6379/0
DATA_DIR=/data
AUTH_DB_PATH=/data/auth.db
CAUSALGRAPH_DB_PATH=/data/causalgraph.db
```

### Neo4j Graph Store

| Variable | Default | Description |
| --- | --- | --- |
| `NEO4J_URI` | empty | Bolt or Aura URI, for example `bolt://localhost:7687` or `neo4j+s://...`. |
| `NEO4J_USER` | `neo4j` | Neo4j username. |
| `NEO4J_PASSWORD` | empty | Neo4j password. |
| `NEO4J_DATABASE` | `ESG` in example | Database name. Match the actual Neo4j database. |
| `NEO4J_AUTO_SYNC` | `true` | Reported by `/graph/neo4j/status`. |

Document ingestion no longer extracts entities or writes to Neo4j. The admin `/graph/neo4j/*` routes and the optional graph context read a graph that already exists in the database.

### Notifications

| Variable | Default | Description |
| --- | --- | --- |
| `NOTIFICATIONS_ENABLED` | `false` | Enables notification hooks. |
| `NOTIFICATIONS_DB_PATH` | `DATA_DIR/notifications.db` | Notification state database. |
| `NOTIFICATIONS_DEDUP_WINDOW_MINUTES` | `60` | Notification deduplication window. |
| `NOTIFICATIONS_DAILY_EMAIL_CAP` | `8` | Daily email cap. |
| `NOTIFICATIONS_SMTP_URL` | empty | SMTP URL. |
| `NOTIFICATIONS_ADMIN_EMAILS` | empty | Notification recipients. |

### Frontend Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `VITE_API_BASE` | Production | Backend API base URL used by the React app. Example: `https://casualgraph.fly.dev`. |

Local development can omit `VITE_API_BASE` when the frontend is served from localhost because the app falls back to `http://127.0.0.1:8000` or the matching local host.

## API Surface

### Auth And Admin

```text
GET    /auth/captcha
POST   /auth/register
POST   /auth/login
GET    /auth/me
GET    /admin/overview
GET    /admin/uploads
POST   /admin/invite-codes
DELETE /admin/uploads/{job_id}
```

### Chat Sessions

```text
GET    /chat/sessions
POST   /chat/sessions
GET    /chat/sessions/{session_id}
POST   /chat/sessions/{session_id}/messages
DELETE /chat/sessions/{session_id}
```

These endpoints use Redis when `REDIS_ENABLED=true`. Without Redis, the backend returns a disabled memory backend response rather than silently pretending memory exists.

### RAG

```bash
curl -X POST http://127.0.0.1:8000/rag/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"What did the report say about renewable electricity?","top_k":5}'
```

Streaming:

```text
POST /rag/ask/stream
```

### Documents

```bash
curl -X POST http://127.0.0.1:8000/documents/upload \
  -F "title=Example ESG Report" \
  -F "domain=general" \
  -F "content=The company reported a reduction in market-based Scope 2 emissions."
```

Other document endpoints:

```text
GET    /documents
POST   /documents/upload
POST   /documents/upload-async
GET    /documents/jobs/{job_id}
GET    /documents/{document_id}
DELETE /documents/{document_id}
POST   /documents/ingest-text
```

### Neo4j Graph APIs (Admin)

```text
GET  /graph/neo4j/status
GET  /graph/neo4j/entity/{entity_name}
GET  /graph/neo4j/subgraph
POST /graph/neo4j/question
```

## Deployment Guide

### Frontend On Vercel

Set the frontend project root to `frontend/`.

Recommended Vercel settings:

```text
Build Command: npm run build
Output Directory: dist
Install Command: npm install
Environment: VITE_API_BASE=https://your-backend.example.com
```

`frontend/vercel.json` rewrites all routes to `index.html` so React Router works on refresh.

### Backend On Fly.io

The GitHub deployment uses `Dockerfile`, `fly.toml`, and `scripts/fly_start.sh`.

Important production secrets:

```bash
flyctl secrets set APP_ENV=production
flyctl secrets set JWT_SECRET=your_32_plus_character_secret
flyctl secrets set CORS_ALLOW_ORIGINS=https://your-frontend.example.com
flyctl secrets set DATA_DIR=/data
flyctl secrets set AUTH_DB_PATH=/data/auth.db
flyctl secrets set CAUSALGRAPH_DB_PATH=/data/causalgraph.db
flyctl secrets set DEEPSEEK_API_KEY=...
flyctl secrets set DEEPINFRA_API_KEY=...
flyctl secrets set REDIS_ENABLED=true
flyctl secrets set REDIS_PASSWORD=...
```

Deploy:

```bash
flyctl deploy
```

Keep health checks operational but do not publish a public health-check URL in demos, README links, or user-facing materials. The Fly image uses the container-local health check from `Dockerfile`.

If Redis is embedded in the Fly machine, keep a persistent volume mounted at `/data` so Redis AOF data and SQLite files survive restarts.

## Data And Security Notes

- `.env`, `*.env`, SQLite databases, uploaded reports, vector stores, local model weights, Redis files, and Neo4j data are intentionally gitignored.
- Public GitHub releases should include only source code, configuration examples, and documentation that is safe to share.
- Do not put provider keys in README examples, screenshots, issue comments, commits, or Fly/Vercel build logs.
- Use a strong `JWT_SECRET` before setting `APP_ENV=production` or `APP_ENV=staging`.
- Use explicit `CORS_ALLOW_ORIGINS` in production.
- Hosted vector stores and graph stores should be treated as production data systems, not as files to commit back to GitHub.

## Troubleshooting

### The frontend returns HTML instead of an API response

`VITE_API_BASE` probably points to the frontend instead of the backend. Set it to the FastAPI origin, for example `https://casualgraph.fly.dev`.

### RAG says there is not enough information

Check that documents were ingested, that a real embedding backend is active, and that the selected document/session context matches the company being asked about.

### Pinecone queries return no results

Confirm that the embedding dimension matches the index. `BAAI/bge-m3` and DeepInfra `BAAI/bge-m3` use 1024-dimensional vectors.

### Redis memory is disabled

Set `REDIS_ENABLED=true` and provide a reachable `REDIS_URL`. On Fly with embedded Redis, also set `REDIS_PASSWORD`.

### Neo4j is configured but graph answers are empty

Verify `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE`. Document ingestion no longer writes to Neo4j, so graph context only comes from a graph that already exists in the database.

## Open-Source Release Checklist

- Add or confirm the intended `LICENSE` file before accepting external reuse or contributions.
- Keep only safe public documentation in GitHub. This project intentionally keeps non-README Markdown files out of the public release unless explicitly needed.
- Rotate any API key that was ever pasted into chat, logs, screenshots, shell history, or deployment output.
- Keep `.env.example` current whenever runtime settings change.
