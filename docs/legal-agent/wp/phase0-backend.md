# Phase 0 · 后端任务书：清场 + 安全修复 + 拆分（WP0.1 → WP0.2 → WP0.4）

> 执行者：一个子代理，按 WP0.1 → WP0.2 → WP0.4 顺序完成。验收人：主会话。
> 背景与理由见 `docs/legal-agent/00-alignment.md`（第 1、7 节）。本任务书是唯一的执行依据；与对齐文档冲突时以本文为准。

## 0. Ground rules

- Work in `/home/user/CasualGraph` on the current branch. **Do not commit, do not push, do not create branches.** The lead commits after acceptance.
- Python env: `. .venv/bin/activate` (already has all requirements + pytest). Run tests as `python -m pytest -q tests` from the repo root (tests `import app`; there is no conftest).
- **File ownership.** You own: every `*.py` at the repo root and under `rag/`, `graph/`, `tests/`, `scripts/` (except `scripts/research_ui_smoke.py`), `configs/`, `document_processing/`, `notifications/`, `mcp_tools/`, `evals/`, `data/taxonomy/`, `db/`, `queries/`, `kg_view/`, `text-to-kg-esg/`, `backend/`, `desktop/`, `ai_service/`, `metric_extraction/`, `assets/`, plus `README.md`, `.env.example`, `.env.production.example`, `requirements.txt`, `Dockerfile`, `.dockerignore`, `fly.toml`, `docker-compose.yml`, root `ci.yml`, `.backend-tests.yml`, root `main.js`, `.vercelignore`, `.github/workflows/*`. **Do not touch** `frontend/**`, root `vercel.json`, `CausalGraph Design System/`, `scripts/research_ui_smoke.py`, `docs/legal-agent/**`, `.gitignore` — another agent owns those.
- Behavior outside the deletions must not change. WP0.2 in particular is a pure move-and-split.
- Do not add new product features, do not rewrite prompts, do not touch the routers' ESG regexes (Phase 2 replaces them). Deletion, decoupling, security, structure only.
- When something in this brief turns out to be impossible or wrong, do the closest safe thing and write it down in your final report under "Deviations".

## 1. WP0.1 — Delete off-mission code and fix the verified security issues

### 1.1 Delete these features completely (code, routes, models, settings, tests, docs, assets)

| Feature | What to remove |
|---|---|
| Recruitment offers | `recruitment_offers.py`; `tests/test_recruitment_offers.py`; `assets/recruitment/` and `scripts/generate_offer_assets.py`; in `app.py`: the models and routes `/admin/recruitment/*`, `/offers/{token}`, `/offers/{token}/respond`, the `recruitment-assets` static mount, the recruitment table creation in the auth DB init, mail helpers used only by recruitment, `RECRUITMENT_PUBLIC_URL` handling; `.env.example` / README sections |
| Desktop companion | `desktop/` directory; root `main.js`; routes `/desktop/screenshot/summarize`, `/desktop/word/review`, `/desktop/word/export` and their request models; `DESKTOP_*` and `VISION_*` settings; `rag/openai_client.py` vision helpers if nothing else uses them. **Before deleting the Word helpers**, move the pure functions (`_parse_docx_paragraphs`, `_select_word_paragraphs_for_review`, `_normalize_word_edit_suggestions`, `_fallback_word_edit_suggestions`, `_replace_paragraph_text`, `_unique_output_name`, `_safe_word_filename`, and the suggestion-generation prompt builder) into `legal/word_review_legacy.py` as plain functions with no FastAPI/DB dependencies; strip the ESG goal/template tables down to a single neutral "general" instruction. Add `tests/test_word_review_legacy.py` that round-trips a small in-memory DOCX (python-docx) through parse → replace → save. This code seeds Phase 3 drafting. |
| Knowledge-graph explorer (ESG) | `kg_view/`; `text-to-kg-esg/`; in `app.py`: `/kg-view`, `/kg-view/ticket`, all `/api/*` routes (`filters`, `total_count`, `graph`, `cluster-graph`, `cluster-detail`, `cluster-subgraph`, `cross-domain-communities`, `cross-cluster-detail`, `stats`, `greenwashing`), `/public/knowledge-graph`, `/kg-api/*`, the `kg-static` and `static` mounts (confirm nothing else is served from `static`; if something is, keep it and report), every `_kg_view_*` / `_public_graph_cache_*` helper and their Redis/memory caches and tickets; `KG_VIEW_*` settings; `tests/test_kg_view_ticket.py` |
| Causal graph surface | routes `/graph/causal/backward|forward|path`; `graph/causal_reasoning.py`, `graph/causal_taxonomy.py`, `graph/graph_builder.py`, `graph/graph_utils.py` if unused afterwards; `scripts/build_graph.py`, `scripts/migrate_causal_types.py`; `db/`, `queries/`. **Keep** `graph/neo4j_store.py`, `rag/graph_context.py`, the admin routes `/graph/neo4j/*`, `NEO4J_*` settings and `docker-compose.yml` untouched (they no-op without `NEO4J_URI`). |
| ESG extraction and metrics | `ai_service/`; `metric_extraction/`; `data/taxonomy/`; routes `/extract` and `/pipeline/pdf`; `scripts/run_pdf_pipeline.py`, `scripts/batch_extract.py`, root `batch_extract.py`, `pipeline_demo.py`; `evals/cases/examples/metric_tools.yaml`; the local-QLoRA answer branches in `rag/rag_pipeline.py` (around lines 1118-1143 and 1458-1493) and any `ai_service` import; settings `ESG_BASE_MODEL_PATH`, `ESG_ADAPTER_PATH`, `HF_LOCAL_FILES_ONLY`, `ESG_MODEL_ALLOW_DOWNLOAD`, `ESG_EXTRACTION_BACKEND`, `EXTRACTION_*`, `DEEPSEEK_EXTRACTION_*`, `ESG_METRICS_*`; the `extraction` and `vision` blocks of `/models/status` (`rag/model_status.py`) |
| Legacy trees | `backend/` (first move the two DB paths that point there, see 1.3); root `ci.yml` and `.backend-tests.yml` (never ran) |
| Dead code | `rag/prediction.py` (unreferenced); `RAG_PREDICTION_*`, `TRACE_*`, `INGESTION_ENABLED`, `RAG_FLASH_MODEL` settings if truly unused (grep first) |

### 1.2 Ingestion must no longer depend on ESG extraction or graph building

`pipeline_runtime.ingest_uploaded_document` (and the `ingest-text` path) becomes: dedup → parse → clean → chunk → vector store + BM25 → registry entry. Remove the per-chunk extraction call, the graph JSON build, `maybe_sync_to_neo4j`'s dependence on extractions (it may simply not be called), `rebuild_document_graph`, and `/documents/rebuild-graph`. Document payloads (`/documents`, `/documents/{id}`, job results) drop `graph`, `relationships`, `relationship_count`, `extractions_path`, `graph_path` and **all other `*_path` fields** (`processed_text_path`, `chunks_path`, `vector_store_path`). Keep `chunk_count`, `stats`, `ingested_at`, ownership/visibility fields. Older registry entries may still contain the removed keys; tolerate them.

### 1.3 Security and correctness fixes (each needs a regression test)

1. **Client-supplied server paths.** With `rebuild-graph` and `/pipeline/pdf` deleted, add a test asserting that `GET /openapi.json` contains none of: `/documents/rebuild-graph`, `/pipeline/pdf`, `/extract`, `/graph/causal/`, `/kg-view`, `/api/`, `/kg-api/`, `/public/knowledge-graph`, `/offers`, `/admin/recruitment`, `/desktop/`.
2. **Path leak.** Test that `GET /documents` and `GET /documents/{id}` responses contain no key ending in `_path`.
3. **Deep-mode tenant leak.** In `app.py` `_resolve_rag_request_context`, always add `owner_user_id` for non-admin users, even when `document_ids` were resolved. In `rag/retriever.py` `retrieve_layered_context`, the `priors` and `regulatory` layers must keep `owner_user_id` (they may still drop `document_ids`). Verify the local and Pinecone filter code honours `owner_user_id` together with `document_ids` (both must hold). Test: a non-admin user's request yields filters containing their `owner_user_id` in every layer.
4. **Login case sensitivity.** Normalise the email in `/auth/login` with the existing `_normalize_email` (registration already does). Test mixed-case login.
5. **Feedback and notifications DB paths.** `_FEEDBACK_DB_PATH` must read `CAUSALGRAPH_DB_PATH` (default `DATA_DIR/causalgraph.db`); `NOTIFICATIONS_DB_PATH` default becomes `DATA_DIR/notifications.db`. Update `.env.example`, README and `fly.toml` accordingly.

### 1.4 Housekeeping

- `requirements.txt`: remove packages no longer imported anywhere (check `pint`, `networkx`, `PyPDF2` vs `pypdf`, `Pillow` is still needed by the captcha, `mcp` is still needed by `mcp_tools`, `jieba` by BM25). Prove it with a grep per package in your report.
- `fly.toml`: drop `DEEPSEEK_EXTRACTION_MODEL`, `EXTRACTION_MAX_WORKERS`. `.dockerignore`: drop entries for deleted trees. `deploy-fly.yml` path filters: drop `ai_service/**`, `backend/**`, `metric_extraction/**`.
- `.env.example` / `.env.production.example`: remove every deleted variable; keep the file organised.
- `README.md`: delete the sections for recruitment, desktop companion, extraction/pipeline endpoints, graph/causal/kg APIs, ESG metrics; fix the stale "Fast = OpenAI, Deep = Anthropic" line; add a two-line "Project direction" note near the top pointing to `docs/legal-agent/00-alignment.md`. Do not rewrite the rest.
- Delete tests that only covered removed code; adjust tests that referenced removed fields (for example the vision 503 test in `tests/test_deepseek_v4_upgrade.py`).

### 1.5 Acceptance for WP0.1 (run all; paste outputs in your report)

```bash
. .venv/bin/activate
python -m compileall -q $(git ls-files '*.py')
python -c "import app"
python -m pytest -q tests
python scripts/dump_openapi_paths.py > /tmp/after-wp01.txt && diff docs/legal-agent/wp/openapi-expected-after-wp01.txt /tmp/after-wp01.txt && echo ROUTES_OK
grep -rIl --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=docs -i -E "recruitment|greenwashing|kg_view|kg-view|metric_extraction|ai_service|esg_metrics|text-to-kg|causal_taxonomy|rebuild-graph|/pipeline/pdf" . ; echo "(the line above must print nothing)"
for d in backend text-to-kg-esg desktop kg_view metric_extraction ai_service db queries assets/recruitment data/taxonomy; do [ -e "$d" ] && echo "STILL EXISTS: $d"; done; echo "(nothing above)"
```

Expected route list after WP0.1 is in `docs/legal-agent/wp/openapi-expected-after-wp01.txt` (46 lines). If you believe a route must differ, keep the diff minimal and explain.

## 2. WP0.2 — Split `app.py` into routers and services (zero behavior change)

Target layout (create packages with `__init__.py`):

```
app.py                      # create_app(): settings validation, middleware/CORS, startup, include_router calls. < 400 lines
api/deps.py                 # get_current_user, get_optional_current_user, require_admin, get_db
api/routers/auth.py         # /auth/*
api/routers/admin.py        # /admin/*
api/routers/documents.py    # /documents/*
api/routers/chat.py         # /chat/sessions/*
api/routers/memory.py       # /memory/*
api/routers/rag.py          # /rag/ask, /rag/ask/stream (SSE plumbing lives here or in services/streaming.py)
api/routers/feedback.py     # /feedback, /admin/feedback/recent
api/routers/graph.py        # /graph/neo4j/* (admin)
api/routers/system.py       # /health, /healthz, /models/status
services/db.py              # sqlite paths, connection, schema init (auth + feedback)
services/auth.py            # JWT, password hashing, captcha, email codes, invite codes, mail sending
services/rate_limit.py      # points / plan / _enforce_rag_rate_limit
services/document_access.py # registry listing, _can_access_entry / _can_retrieve_entry, accessible ids
services/rag_context.py     # the document-scope / routing-hint / entity-term block (currently ~app.py 2374-3510)
services/memory.py          # long-term memory glue (_load_long_term_memory_context, _remember_exchange_later)
legal/word_review_legacy.py # from WP0.1
```

Rules:
- Move code, do not rewrite it. Keep function names; drop the leading underscore only where a function becomes a cross-module import (or keep it, consistency matters less than a clean diff).
- `from app import app` must keep working. Tests that import private helpers from `app` should be updated to import from the new module (preferred) or served by a small re-export block at the bottom of `app.py` (acceptable, list them in the report).
- Module-level state (captcha store, executors, caches) moves with the code that owns it. Watch for import cycles: routers import services, services never import routers or `app`.
- Beware `platform` is a stdlib module name; that is why the package is `services/`.
- Add `ruff` to the dev tooling with a minimal gate: `ruff check --select E9,F63,F7,F82 .` (syntax errors and undefined names only) and a `pyproject.toml` `[tool.ruff]` section excluding `.venv`, `node_modules`, `frontend`.

Acceptance for WP0.2:

```bash
. .venv/bin/activate
python -m pytest -q tests
python scripts/dump_openapi_paths.py > /tmp/after-wp02.txt && diff /tmp/after-wp01.txt /tmp/after-wp02.txt && echo ROUTES_UNCHANGED
wc -l app.py            # must be < 400
ruff check --select E9,F63,F7,F82 .
python -c "import app, api.routers.rag, services.auth"
```

## 3. WP0.4 — CI

- Replace `.github/workflows/upgrade-validation.yml` with `.github/workflows/ci.yml` that runs on `pull_request` and on `push` to `main` and to `claude/**` branches. Backend job: pip install requirements + `pytest pytest-asyncio httpx ruff`, then `ruff check --select E9,F63,F7,F82 .`, `python -m compileall -q $(git ls-files '*.py')`, `python -m pytest -q tests`. Frontend job: **copy the frontend steps exactly as the frontend agent leaves them** in `frontend/package.json` scripts (`npm ci`, `npm run typecheck`, `npm run lint`, `npm test -- --run`, `npm run build`, then the Playwright smoke `python scripts/research_ui_smoke.py`). Read `docs/legal-agent/wp/phase0-frontend.md` for the exact script names and the build output directory (`frontend/dist`). If the frontend work is not finished when you get here, write the job against those documented names anyway and say so.
- Update `deploy-fly.yml` path filters (see 1.4). Keep deployment behaviour unchanged.
- Validate YAML syntax (`python -c "import yaml,sys; [yaml.safe_load(open(p)) for p in sys.argv[1:]]" .github/workflows/*.yml`).

## 4. Final report format

1. Summary of what was deleted / moved / fixed (bullets).
2. Acceptance command outputs for WP0.1, WP0.2, WP0.4 (verbatim tails).
3. Test count before → after, with the list of deleted test files.
4. `requirements.txt` removals with the grep proof.
5. Deviations from this brief and why.
6. Anything you noticed that the lead should know for Phase 1 (do not fix it).
