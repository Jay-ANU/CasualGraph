# Deployment Plan — CausalGraph Production Launch

> Self-contained brief for codex. Codex has not seen the conversation that produced this plan; read all sections before starting.

---

## 1. Context

CausalGraph is an ESG research RAG application:

- **Backend** — FastAPI (`app.py`) + RAG pipeline in `rag/` + ingestion in `ai_service/` + Neo4j graph in `graph/`.
- **Frontend** — React (CRA-style, `frontend/`).
- **Storage** — SQLite (`backend/causalgraph.db` for sessions, `auth.db` for users), local file uploads in `data/documents/`, FAISS files in `data/vector_stores/`.
- **External services already wired** — OpenAI (Flash tier + ask path), Anthropic Claude (Deep tier), Pinecone (vector store, optional), Neo4j Aura (graph, optional), DeepSeek (extraction fallback).
- **Today's heavy local dependencies** — `torch`, `transformers`, `peft`, `accelerate`, `bitsandbytes`, `sentence-transformers`, `faiss-cpu`. These are used for (a) local QLoRA answering and (b) the bge-m3 embedding model. We are dropping (a) entirely and moving (b) to a hosted API so the production container is small.

The Flash/Deep refactor (replacing the old Predict mode) is already merged. The Anthropic key, OpenAI key, Pinecone, and Neo4j Aura are all in the user's `.env` and working locally.

## 2. Goal

Deploy publicly under **`causalgraph.com`** at the **lowest viable cost** (~$3–6/month infra + per-call LLM usage):

| Layer | Service | Cost |
|---|---|---|
| Frontend (`causalgraph.com`, `www.causalgraph.com`) | Vercel Hobby | $0 |
| Backend (`api.causalgraph.com`) | Fly.io `shared-cpu-1x@512MB` | ~$2–5/mo (free allowance covers most of it) |
| Persistent volume (SQLite + uploads) | Fly Volume 3 GB | ~$0.45/mo |
| Vector store | Pinecone Starter (existing 1024-d index, **must stay** so we don't re-ingest) | $0 |
| Graph | Neo4j Aura Free | $0 |
| Embeddings | **DeepInfra API hosting `BAAI/bge-m3`** | ≈$0.01 per 1M tokens, effectively free at our scale |
| LLM | Existing OpenAI + Anthropic keys | per call |
| Domain | Cloudflare Registrar `causalgraph.com` | ~$10/year |

Critical constraint: we keep the **same bge-m3 embedding model** (DeepInfra hosts it). Vectors stay compatible with the existing Pinecone index, so **no re-ingest is required**.

## 3. Architecture decisions (already made — do not re-litigate)

1. **Trim local ML dependencies**: remove `torch`, `transformers`, `peft`, `accelerate`, `bitsandbytes`, `sentence-transformers`, `faiss-cpu` from production install. Shrinks image from ~5 GB → ~400 MB and RAM from ~4 GB → ~512 MB.
2. **Embeddings via DeepInfra HTTP API**: do NOT bundle bge-m3 into the container. Call DeepInfra's OpenAI-compatible `/v1/openai/embeddings` endpoint with model `BAAI/bge-m3`. Same model = same vector space as current Pinecone index.
3. **Local QLoRA path stays in the code but never executes in prod**. Force `RAG_ANSWER_MODE=openai` so the `local_qlora` branch is skipped. Make the `torch` / `transformers` imports lazy so an absent SDK never breaks startup.
4. **Extraction in production uses the remote extractor** (DeepSeek or OpenAI) via `ai_service/remote_extractor.py`. The local QLoRA-based `ai_service/extractor.py` is import-gated.
5. **Production is upload-capable** (users can upload PDFs and they're ingested live). Extraction must therefore work without `torch`. If this is too risky, ingestion can be disabled via a `INGESTION_ENABLED=false` flag — leave that flag as an opt-out.
6. **Fly auto-stop is on** (`auto_stop_machines = "stop"`, `min_machines_running = 0`). First request after idle takes 5–10s cold start. Acceptable for a demo/research deploy.
7. **CORS** must allow `https://causalgraph.com` and `https://www.causalgraph.com`.

## 4. Tasks

### Task 1 — Trim `requirements.txt`

**File**: `requirements.txt`

**Remove these lines**:
```
torch
transformers
peft
accelerate
bitsandbytes
sentence-transformers
faiss-cpu
```

**Add**:
```
python-dotenv>=1.0.0
requests>=2.31.0
```

(`python-dotenv` is needed because the current code reads `.env` via dotenv in dev but it isn't pinned; `requests` is for the DeepInfra HTTP call. If `httpx` is already a transitive dep, prefer it over `requests`.)

### Task 2 — Add DeepInfra embedding backend

**File**: `rag/embeddings.py`

Current implementation uses `sentence-transformers` to load bge-m3 locally. Refactor so the embedding source is selected by `EMBEDDING_BACKEND`:

- `EMBEDDING_BACKEND=local` (default for dev) — existing path, lazy-imports `sentence-transformers`. If the package is missing, raise a clear error.
- `EMBEDDING_BACKEND=deepinfra` — new path that calls DeepInfra's OpenAI-compatible embeddings endpoint.

**DeepInfra integration shape** (use the existing `openai` SDK rather than raw HTTP — DeepInfra is OpenAI-compatible):

```python
from openai import OpenAI
client = OpenAI(api_key=os.getenv("DEEPINFRA_API_KEY"),
                base_url="https://api.deepinfra.com/v1/openai")
resp = client.embeddings.create(model="BAAI/bge-m3", input=texts)
vectors = [d.embedding for d in resp.data]
```

Notes:
- Batch in chunks of ≤96 texts per call (DeepInfra limit) to avoid 413 errors.
- Cache the client across calls (`functools.lru_cache(maxsize=1)`).
- The vector dimension is 1024 — assert this in dev so a misconfig (wrong model name) doesn't silently corrupt the Pinecone index.
- Add settings entries in `configs/settings.py`: `EMBEDDING_BACKEND`, `DEEPINFRA_API_KEY`, `DEEPINFRA_EMBEDDING_MODEL = "BAAI/bge-m3"`, `DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"`.

Update `.env.example` with the four new keys (placeholders only — no secrets).

### Task 3 — Make local ML imports lazy

Today these files import `torch` / `transformers` at module top:
- `ai_service/model_loader.py`
- `ai_service/extractor.py`
- `rag/rag_pipeline.py` (imports `torch`, plus `from ai_service.model_loader import get_model_and_tokenizer`)

**Goal**: importing these modules at app startup must NOT require torch/transformers to be installed.

Move every `import torch` / `from transformers …` / `from peft …` etc. inside the function that uses it. The `get_model_and_tokenizer()` call inside `rag/rag_pipeline.py`'s local-QLoRA branch should be the only entry point, and that branch is unreachable when `RAG_ANSWER_MODE=openai`. After this refactor, `python -c "import app"` must succeed with torch absent.

Same treatment for `ai_service/extractor.py` if `app.py` imports it at module load. If ingestion code unconditionally pulls in `extractor`, gate it behind a runtime check of `ESG_EXTRACTION_BACKEND` (new env var, default `remote`).

Add new settings in `configs/settings.py`:
- `ESG_EXTRACTION_BACKEND = os.getenv("ESG_EXTRACTION_BACKEND", "remote")` — `local` | `remote`
- `INGESTION_ENABLED = os.getenv("INGESTION_ENABLED", "true").lower() in {"1","true","yes"}`

If `INGESTION_ENABLED=false`, return HTTP 503 from the ingest endpoints in `app.py` so users see a clear "uploads disabled" message rather than a crash.

### Task 4 — Production-only env file

**New file**: `.env.production.example`

Document the exact env vars the production backend needs. Do NOT commit real secrets.

```
# Required in production
RAG_ANSWER_MODE=openai
EMBEDDING_BACKEND=deepinfra
ESG_EXTRACTION_BACKEND=remote
INGESTION_ENABLED=true

OPENAI_API_KEY=
ANTHROPIC_API_KEY=
DEEPINFRA_API_KEY=
DEEPSEEK_API_KEY=

VECTOR_STORE_PROVIDER=pinecone
PINECONE_API_KEY=
PINECONE_INDEX_NAME=
PINECONE_INDEX_HOST=
PINECONE_NAMESPACE=esg-demo

NEO4J_URI=
NEO4J_USER=neo4j
NEO4J_PASSWORD=
NEO4J_DATABASE=ESG

# Storage paths point at the Fly volume mount
NOTIFICATIONS_DB_PATH=/data/notifications.db
ESG_METRICS_DB_PATH=/data/esg_metrics.sqlite
EXTRACTION_CACHE_PATH=/data/extraction_cache.sqlite
TRACE_PATH=/data/traces.jsonl

# CORS
CORS_ALLOWED_ORIGINS=https://causalgraph.com,https://www.causalgraph.com
```

You may also need to plumb `CORS_ALLOWED_ORIGINS` through to `app.py`'s `CORSMiddleware` config — check whether it's currently hard-coded.

**SQLite paths**: the auth/session DBs (`backend/causalgraph.db`, `auth.db`) are currently relative paths. Either:
- (a) Symlink `/app/backend` and `/app/auth.db` to volume locations at container startup (entrypoint script), OR
- (b) Add env vars `AUTH_DB_PATH` and `CAUSALGRAPH_DB_PATH` and update the code that opens them.

Pick (b) — cleaner.

### Task 5 — `Dockerfile` for backend

**New file**: `Dockerfile`

```dockerfile
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# build-essential needed for some pure-python wheels (jieba etc.).
# Slim it down again afterwards.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Healthcheck endpoint — confirm app.py has /healthz; add it if not.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/healthz || exit 1

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

If `/healthz` doesn't exist in `app.py`, add it: returns `{"status": "ok"}` without touching the DB.

### Task 6 — `.dockerignore`

**New file**: `.dockerignore`

Exclude everything that doesn't belong in the image. Keep it conservative — small misses inflate the image dramatically.

```
.git
.github
.claude
.venv
venv
env
node_modules
frontend
models/
data/
*.db
*.db-journal
*.sqlite
*.bak*
__pycache__
*.pyc
.pytest_cache
.mypy_cache
.coverage
*.log
docs/
design/
evals/
"CausalGraph Design System/"
TASKS_FOR_CODEX*.md
RAG_LATENCY_OPTIMIZATION.md
.env
.env.*
!.env.example
!.env.production.example
```

### Task 7 — `fly.toml`

**New file**: `fly.toml`

```toml
app = "causalgraph-api"
primary_region = "iad"   # pick the region closest to your users / Neo4j Aura instance

[build]

[env]
  PORT = "8000"
  # All other env values are set via `flyctl secrets set` (see runbook below).

[mounts]
  source = "causalgraph_data"
  destination = "/data"
  initial_size = "3gb"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0
  processes = ["app"]

  [http_service.concurrency]
    type = "requests"
    soft_limit = 20
    hard_limit = 25

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 512
```

If 512 MB OOMs once Pinecone + Neo4j + OpenAI clients are all warm, bump to 1024 MB (`memory_mb = 1024`). Cost difference is ~$3/month.

### Task 8 — Frontend deploy config

**Vercel project setup** (no file change required, but document):
- Root directory: `frontend`
- Build command: `npm run build`
- Output directory: `build`
- Environment variables:
  - `REACT_APP_ESG_API_BASE=https://api.causalgraph.com`
  - any other `REACT_APP_*` keys the app reads (check `frontend/src` for `process.env.REACT_APP_`)
- Custom domain: `causalgraph.com` and `www.causalgraph.com`

**Optional new file**: `frontend/vercel.json`

```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

(SPA fallback so direct-link routes like `/agent` don't 404.)

### Task 9 — CORS & host config in backend

**File**: `app.py`

Find the `CORSMiddleware` block (or add one if absent). Make `allow_origins` read from `CORS_ALLOWED_ORIGINS` env var (comma-separated). Default to `*` in dev only — fail loudly in prod if the env var is missing.

Also ensure session cookies (if any) have `secure=True` and `samesite="none"` when behind HTTPS, since frontend and backend are on different subdomains.

### Task 10 — DNS at Cloudflare

After Fly deploys (`flyctl deploy`), retrieve the app's IPv4 and IPv6 (`flyctl ips list`). At Cloudflare:

- `causalgraph.com` → A/AAAA records pointing at Vercel's anycast IPs (Vercel docs show current values), proxied OFF (or use CNAME flattening to `cname.vercel-dns.com`).
- `www.causalgraph.com` → CNAME `cname.vercel-dns.com`, proxied OFF.
- `api.causalgraph.com` → A record to Fly's IPv4, AAAA to Fly's IPv6, proxied OFF (Fly handles its own TLS).

In Fly: `flyctl certs add api.causalgraph.com` so Fly provisions an LE cert.
In Vercel: add `causalgraph.com` and `www.causalgraph.com` in Project → Settings → Domains; Vercel will give DNS instructions and provision certs.

### Task 11 — Runbook (one-shot deploy commands)

Add to a new `docs/DEPLOY_RUNBOOK.md` so future deploys are reproducible:

```bash
# Pre-req: flyctl, vercel CLI installed; logged in.

# --- Backend ---
flyctl launch --no-deploy --copy-config --name causalgraph-api
flyctl volume create causalgraph_data --size 3 --region iad

# Secrets (one-time)
flyctl secrets set \
  OPENAI_API_KEY=... \
  ANTHROPIC_API_KEY=... \
  DEEPINFRA_API_KEY=... \
  DEEPSEEK_API_KEY=... \
  PINECONE_API_KEY=... \
  PINECONE_INDEX_NAME=... \
  PINECONE_INDEX_HOST=... \
  PINECONE_NAMESPACE=esg-demo \
  NEO4J_URI=... \
  NEO4J_USER=neo4j \
  NEO4J_PASSWORD=... \
  NEO4J_DATABASE=ESG \
  RAG_ANSWER_MODE=openai \
  EMBEDDING_BACKEND=deepinfra \
  ESG_EXTRACTION_BACKEND=remote \
  INGESTION_ENABLED=true \
  CORS_ALLOWED_ORIGINS=https://causalgraph.com,https://www.causalgraph.com \
  AUTH_DB_PATH=/data/auth.db \
  CAUSALGRAPH_DB_PATH=/data/causalgraph.db

flyctl deploy
flyctl certs add api.causalgraph.com

# --- Frontend ---
cd frontend
vercel --prod
# Then add custom domain in Vercel dashboard.
```

### Task 12 — Verification checklist

After deploy, codex must verify each item:

- [ ] `curl https://api.causalgraph.com/healthz` returns `{"status":"ok"}` within 1s after warm-up.
- [ ] `python -c "import app"` succeeds locally even with torch uninstalled (test in a fresh venv with the trimmed `requirements.txt`).
- [ ] The Docker image is under 600 MB (`docker images causalgraph-api`).
- [ ] First request to `/rag/ask/stream` with `reasoning_mode=flash` returns a streamed answer within 8s (cold) / 3s (warm).
- [ ] First request with `reasoning_mode=deep` streams from Claude within 15s (cold).
- [ ] Visiting `https://causalgraph.com/agent` loads the Agent page; toggling Flash/Deep + sending a question works end-to-end.
- [ ] Uploading a small PDF (if `INGESTION_ENABLED=true`) writes to `/data/documents/` on the Fly volume and shows up in the document list after refresh.
- [ ] Pinecone vector count goes up after upload (confirms DeepInfra embedding wiring).
- [ ] Neo4j Aura sees new nodes after ingest (run a Cypher query from Aura console).
- [ ] SSL is valid on both `causalgraph.com` and `api.causalgraph.com`.
- [ ] No `torch` / `transformers` warnings in `flyctl logs`.

## 5. Open questions to confirm with the user BEFORE deploying

1. **Region**: `iad` (Virginia, US East) is the cheapest Fly region with lowest median latency to Neo4j Aura's default US deployments. Pick another if the user's audience is APAC (e.g. `nrt` Tokyo). Cost is identical.
2. **Pinecone index**: confirm with the user which existing index name + host should be used. If they want a fresh prod-only index, they need to create it (1024-d, cosine, dimension MUST match bge-m3).
3. **SQLite migration**: the existing dev `auth.db` has the user's accounts. Should it be uploaded to the Fly volume (`fly ssh sftp shell` + `put auth.db /data/auth.db`) or start fresh?
4. **`ingestion_jobs.py`** uses Python `ThreadPoolExecutor` for concurrent ingest. On a 512 MB / 1-vCPU Fly machine this could OOM under load. Default `INGESTION_JOB_MAX_WORKERS=1` in prod to be safe.

## 6. Out of scope (do NOT do)

- Don't change the Flash/Deep refactor — that's already merged and validated.
- Don't add a CI/CD pipeline yet — manual `flyctl deploy` + `vercel --prod` is fine for v1.
- Don't migrate from Pinecone or Neo4j Aura — they're free and working.
- Don't add monitoring/observability (Sentry, etc.) yet — first prove it runs.

## 7. Definition of done

- `https://causalgraph.com` loads the React app.
- `https://api.causalgraph.com/healthz` returns 200.
- The Agent page can answer one Flash and one Deep query end-to-end, streamed.
- All twelve verification checks in Task 12 pass.
- Repo has the new files (`Dockerfile`, `.dockerignore`, `fly.toml`, `frontend/vercel.json`, `.env.production.example`, `docs/DEPLOY_RUNBOOK.md`) committed.
- Total monthly cost (excluding LLM usage) ≤ $8.
