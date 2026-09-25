# Phase 1 · 共享契约（所有 Phase 1 任务书的公共依据）

> 中文摘要：Phase 1 建立"文档模型"。四个并行工作包各自负责 **A 解析与条款切分**、**B 脱敏**、**C matter 与租户**、**D 多文档索引**，最后由 **E 集成**。它们通过本文定义的数据结构、文件布局、函数签名协作。已经落地的共享代码（不要改签名，只能追加字段）：`ingest/models.py`、`legal/redaction/types.py`、`services/crypto.py`、`configs/settings.py` 的 Phase 1 段、`app.py` 的可选路由自动注册、`rag/vector_store.remove_document`。

## 1. Shared code that already exists (frozen: additive changes only, and report them)

| File | What it gives you |
|---|---|
| `ingest/models.py` | `Block`, `Page`, `ParsedDocument` (canonical text = blocks in order joined by `"\n"`; `block_offsets()`), `ClauseNode`, `ClauseTree`, chunk-row schema v2 (`CHUNK_V2_FIELDS`, `make_chunk_uid`, `validate_chunk_row`) |
| `legal/redaction/types.py` | `CATEGORIES`, `PLACEHOLDER_PATTERN`, `RedactionPolicy` (`.default()` reads settings), `Occurrence`, `EntityCandidate`, `RedactionReview`, `MappingEntry`, `RedactionMapping` (`forward`, `reverse`, `legend`), `RedactionResult`, `RedactionPendingError` |
| `services/crypto.py` | Fernet at-rest encryption: `write_encrypted(_json)`, `read_encrypted(_json)`, `reset_for_tests()`; key from `REDACTION_KEY`, dev fallback `DATA_DIR/.redaction_key` |
| `configs/settings.py` | `PARSED_DIR`, `CLAUSES_DIR`, `REDACTION_DIR`, `REDACTION_KEY`, `REDACTION_REQUIRE_CONFIRMATION` (default false), `REDACTION_DEFAULT_CATEGORIES`, `VECTOR_SHARD_CACHE_SIZE`, `BM25_MERGE_MAX_CHUNKS`; `ensure_directories()` creates the new dirs |
| `app.py` | Includes `api.routers.document_content`, `api.routers.redaction`, `api.routers.matters` automatically when the module exists and exposes `router`. Do not edit `app.py`. |
| `rag/vector_store.remove_document(document_id, persist_path)` | Stable delete entry point (WP1-D re-implements it; WP1-A calls it) |
| `requirements.txt` / `requirements-dev.txt` | `pdfplumber`, `cryptography` added; `reportlab` (fixture generation) and tooling in dev. Do not edit; ask via your report if you need another package. |

## 2. Storage layout under `DATA_DIR`

```
raw/<document_id>/original.<ext>.enc      encrypted original upload                     (A writes, A serves)
parsed/<document_id>.original.json.enc    encrypted ParsedDocument before redaction     (A writes, B reads)
parsed/<document_id>.redacted.json        plain ParsedDocument with placeholders        (B writes via hook; A reads for clauses/chunks/content)
clauses/<document_id>.json                ClauseTree over the redacted canonical text   (A)
chunks/<document_id>_chunks.jsonl         chunk rows v2, redacted text                  (A)
processed/<document_id>.txt               canonical redacted text (compat)              (A)
vector_store/<document_id>/               per-document shard (metadata.json, index.faiss|index.pkl, bm25.pkl)  (D)
vector_store/catalog.json                 shard catalog                                 (D)
redaction/<document_id>.review.json.enc   encrypted RedactionReview                     (B)
redaction/<document_id>.mapping.json.enc  encrypted RedactionMapping                    (B)
documents/registry.json                   registry entries (see §3)                     (A owns the module)
```

**Plaintext rule:** any plaintext file may contain redacted text only. Anything holding original client text goes through `services/crypto.py`. Log lines and error messages must never include candidate values or block text.

## 3. Registry entry (A owns `document_registry.py`; others read via its functions)

Existing fields stay. New fields (all optional for legacy entries):

```json
{
  "schema_version": 2,
  "status": "ready",                 // uploaded | parsing | pending_redaction | finalizing | ready | failed
  "status_message": "",
  "language": "zh",                  // zh | en | mixed | unknown
  "page_count": 12,
  "clause_count": 48,
  "original_filename": "采购合同.docx",
  "source_format": "docx",
  "redaction": {"status": "confirmed", "counts_by_category": {"org": 6, "person": 2}, "confirmed_at": "..."},
  "paths": {"raw": "...", "parsed_original": "...", "parsed_redacted": "...", "clauses": "...",
            "chunks": "...", "processed_text": "...", "vector_store": "..."}
}
```

Legacy entries (no `status`) are treated as `status="ready"` with `redaction.status="skipped_legacy"`. `document_registry.update_metadata(document_id, updates)` exists; A adds `set_status(document_id, status, message="")`.

## 4. Ingestion stages and hooks (A owns `pipeline_runtime.py`, `ingestion_jobs.py`, `ingest/**`)

```
ingest_uploaded_document(...)                     # signature unchanged; new kwargs: matter_id="", policy=None
  stage_store_original(ctx)  -> raw path
  stage_parse(ctx)           -> ParsedDocument (original) saved encrypted; registry status=parsing
  redaction hook             -> ingest.hooks.REDACTION_HOOK(parsed, ctx)
                                 returns the redacted ParsedDocument to continue with,
                                 or None => registry status=pending_redaction, job ends here
  finalize_document(document_id, parsed=None) -> Dict
      segment -> chunk -> index (build_vector_store + build_bm25_index) -> registry status=ready
      (loads parsed/<id>.redacted.json when `parsed` is None; falls back to the encrypted original
       only when no redaction review exists at all, i.e. the hook is not installed)
```

`ingest/hooks.py` (A creates, B implements the function, E installs it at startup):

```python
RedactionHook = Callable[[ParsedDocument, "IngestContext"], Optional[ParsedDocument]]
REDACTION_HOOK: Optional[RedactionHook] = None
```

`legal/redaction/hooks.py` (B creates, E installs):

```python
ON_CONFIRMED: Optional[Callable[[str], Any]] = None   # receives document_id; E sets it to pipeline_runtime.finalize_document
```

`IngestContext` (A, in `ingest/context.py`): `document_id, title, filename, source_format, owner_user_id, document_group, visibility_scope, domain, source, source_type, matter_id, policy: Optional[RedactionPolicy], progress: Callable, paths: Dict[str, Path]`.

`ingestion_jobs.start_finalize_job(document_id, actor=None) -> job dict` (A) runs `finalize_document` in the worker pool; B's confirm endpoint returns whatever `ON_CONFIRMED` returns (a job dict or a result dict).

## 5. Chunk rows (v2)

Produced by `ingest/chunking.chunk_document(parsed, tree, ...)` (A). One chunk per leaf clause; oversized leaves split on sentence boundaries with overlap; tiny sibling leaves merged. Fields: all of `CHUNK_V1_FIELDS` (compat; `chunk_id` stays `chunk_{N}`, `section` = `tree.path_label(clause_id)`) plus `CHUNK_V2_FIELDS`. `validate_chunk_row` must return `[]` for every row written.

## 6. Citations (A owns `legal/citations.py`)

```python
@dataclass
class Citation:
    document_id: str; chunk_uid: Optional[str]; clause_id: Optional[str]; clause_label: str
    page: Optional[int]; quote: str; char_start: Optional[int]; char_end: Optional[int]
    block_ids: List[str]; verified: bool; verification: str   # exact | normalized | fuzzy | not_found

verify_quote(quote: str, canonical_text: str) -> Optional[Tuple[int, int, str]]
   # exact match; else whitespace/punctuation/full-width normalised match mapped back to raw offsets;
   # else fuzzy (difflib ratio >= 0.85 within a sliding window); else None
locate(chunk_row: dict, quote: str, parsed: Optional[ParsedDocument]) -> Citation
display_label(citation: Citation, document_title: str, lang: str) -> str   # 《title》第三条 · 第4页 / Title, cl. 3.2, p. 4
```

The marker grammar the model will emit is decided in Phase 2; Phase 1 only delivers verification and labelling.

## 7. Redaction (B owns `legal/redaction/**` except `types.py`, plus `api/routers/redaction.py`)

```python
legal.redaction.engine.detect(parsed, policy) -> RedactionReview          # local only, no network
legal.redaction.engine.apply(parsed, review) -> RedactionResult           # rewrites block texts, keeps ids/pages/bboxes
legal.redaction.store: save_review/load_review/save_mapping/load_mapping/review_status(document_id)
legal.redaction.gate.assert_documents_model_ready(document_ids) -> None   # raises RedactionPendingError
legal.redaction.pipeline.redaction_hook(parsed, ctx) -> Optional[ParsedDocument]
legal.redaction.pipeline.confirm(document_id, actor_user_id) -> Dict     # apply + save + ON_CONFIRMED
```

HTTP (all require document access through `services.document_access._can_access_entry`):

```
GET   /documents/{id}/redaction            review incl. values and decisions (the reviewer must see them)
PATCH /documents/{id}/redaction            {"decisions":[{"entity_id","decision"}], "add":[{"category","value","role_hint"}], "remove":["ent_.."], "policy":{...}}
POST  /documents/{id}/redaction/confirm    -> {"status":"confirmed", "summary":{...}, "finalize": <ON_CONFIRMED result>}
GET   /documents/{id}/redaction/mapping    placeholders -> values (for local re-identification in the UI/export)
GET   /documents/{id}/redaction/status     public_summary() only
```

Status gate error: HTTP 409 `{"error": "redaction_pending", "document_ids": [...]}`.

## 8. Matters and tenancy (C owns `services/matters.py`, `services/audit.py`, `services/db.py`, `api/routers/matters.py`, `api/routers/documents.py`, `services/document_access.py`, `services/rag_context.py`, `api/deps.py`)

SQLite tables in the auth database (created in `services/db.py`):

```
organizations(id TEXT PK, name, created_at, settings_json)
org_members(org_id, user_id, role CHECK(role IN ('owner','admin','member')), created_at, PK(org_id,user_id))
matters(id TEXT PK, org_id, name, client_ref, description, status CHECK(status IN ('active','archived')),
        created_by, created_at, updated_at, settings_json)
matter_members(matter_id, user_id, role CHECK(role IN ('lead','member','viewer')), added_by, created_at, PK(matter_id,user_id))
matter_documents(matter_id, document_id, added_by, added_at, PK(matter_id,document_id))
audit_events(id INTEGER PK AUTOINCREMENT, org_id, matter_id, actor_user_id, action, target_type, target_id,
             details_json, created_at)   -- details_json: ids and counts only, never document text
```

Functions: `ensure_personal_workspace(user) -> {"org_id","matter_id"}` (idempotent), `require_matter_member(matter_id, user, min_role)`, `matter_document_ids(matter_id)`, `user_matter_ids(user_id)`, `services.audit.record_event(*, actor_user_id, action, target_type, target_id, matter_id=None, org_id=None, details=None)`.

HTTP: `GET/POST /matters`, `GET/PATCH/DELETE /matters/{id}`, `GET/POST/DELETE /matters/{id}/members`, `GET/POST /matters/{id}/documents`, `DELETE /matters/{id}/documents/{document_id}`, `GET /matters/{id}/audit`. `POST /documents/upload(-async)` and `/documents/ingest-text` accept optional `matter_id`; `GET /documents?matter_id=` filters. `RagAskRequest.matter_id: Optional[str]`; `_resolve_rag_request_context` intersects the matter's documents with any explicit `document_ids` and refuses (403) when the user is not a member.

Access rule (extend, do not replace): a user may access a document if the legacy owner/global rules allow it **or** the user is a member of a matter that contains it.

## 9. Index layer (D owns `rag/vector_store.py`, `rag/bm25_index.py`, `rag/pinecone_store.py`, the store-facing parts of `rag/retriever.py`, `scripts/build_vector_index.py`, new `scripts/rebuild_index_catalog.py`)

Keep every public signature currently imported elsewhere: `build_vector_store(chunks, persist_path)`, `build_bm25_index(chunks, persist_path)`, `search(query, top_k, persist_path=None, filters=None)`, `search_bm25(query, top_k, filters=None)`, `load_vector_store(persist_path=None)`, `warm_bm25_index()`, `remove_document(document_id, persist_path)`, `_apply_local_filters`, `_build_pinecone_filter` (tested by `tests/test_phase0_security.py`). Replace the single active store with `vector_store/catalog.json` + per-document shards; `search` selects shards from `filters["document_ids"]` / owner / visibility, merges scores across shards; BM25 merges the selected shards' corpora on demand (cap `BM25_MERGE_MAX_CHUNKS`) with a cache. `preferred_document_id` keeps its "primary first, then fill" behaviour.

## 10. Acceptance conventions for every Phase 1 WP

* `python -m pytest -q tests` green (currently 100 passing).
* `ruff check --select E9,F63,F7,F82 .` clean; `python -m compileall -q $(git ls-files -co --exclude-standard '*.py')`.
* `python scripts/dump_openapi_paths.py` shows only the routes you were asked to add on top of `docs/legal-agent/wp/openapi-expected-after-wp01.txt`.
* No commits. Report with the format in your brief.
