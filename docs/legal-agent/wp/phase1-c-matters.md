# Phase 1 · WP1-C 任务书：Matter（案件）工作区、成员权限、审计日志、迁移

> 执行者：一个子代理。验收人：主会话。先读 `docs/legal-agent/wp/phase1-contracts.md` §1、§3、§8，再读本文。产品背景 `docs/legal-agent/00-alignment.md` §3-C。

## 0. Ground rules

- Work in `/home/user/CasualGraph`, venv `. .venv/bin/activate`. **No commits / pushes / branches.**
- Three other agents work in the same tree. **You own:** `services/matters.py` (new), `services/audit.py` (new), `services/db.py`, `services/document_access.py`, `services/rag_context.py`, `api/deps.py`, `api/routers/matters.py` (new), `api/routers/documents.py`, `api/routers/rag.py` (only to pass `matter_id` through if needed), `scripts/migrate_phase1_matters.py` (new), `tests/test_matters_*.py`, `tests/test_audit.py`. **Do not touch** `ingest/**`, `pipeline_runtime.py`, `ingestion_jobs.py`, `document_registry.py`, `legal/**`, `rag/**`, `configs/settings.py`, `app.py`, `requirements*.txt`, `docs/**`.
- `pipeline_runtime.ingest_uploaded_document` and `ingestion_jobs.start_ingestion_job` are being changed by WP1-A to accept `matter_id: str = ""`. Pass `matter_id=` **only if the parameter exists** (`inspect.signature`), so your code works before and after A lands; link the document to the matter yourself after ingestion succeeds (sync path: on the result; async path: `ingestion_jobs` exposes job dicts — poll is the frontend's job, so link at job start using the job's reserved `document_id` if available, otherwise link in a small completion callback if `start_ingestion_job` accepts one; if neither is possible, link when the job result is first read in `GET /documents/jobs/{job_id}` and record that in your report).
- SQLite only, via the existing `aiosqlite` connection helpers in `services/db.py`; schema created in the auth DB init; everything idempotent (`CREATE TABLE IF NOT EXISTS`).

## 1. Deliverables

### 1.1 Schema — `services/db.py`

Tables exactly as contracts §8 plus indexes on `matter_members(user_id)`, `matter_documents(document_id)`, `audit_events(matter_id, created_at)`. Ids are `uuid4` strings.

### 1.2 Services — `services/matters.py`, `services/audit.py`

- `ensure_personal_workspace(user) -> {"org_id", "matter_id"}`: one personal organization per user (`name = "<username or email> 的工作区"`), one default matter `未分类` in it; idempotent; the user is `owner` of the org and `lead` of the matter.
- `create_matter(user, *, name, client_ref="", description="", org_id=None)`; `list_matters(user)`; `get_matter(matter_id)`; `update_matter`; `archive_matter` (`status=archived`; DELETE archives, never hard-deletes); members `add_member/remove_member/list_members` (only `lead` or org admin/owner may change members); `attach_document(matter_id, document_id, user)` / `detach_document`; `matter_document_ids(matter_id)`; `user_matter_ids(user_id)`; `require_matter_member(matter_id, user, min_role="viewer")` raising `HTTPException(403)`; admins (`role == "admin"`) are **not** implicitly members — they see matter metadata through admin routes only, not contents.
- `services/audit.py`: `record_event(*, actor_user_id, action, target_type, target_id, matter_id=None, org_id=None, details=None)` (sync, safe to call from sync code; details must be JSON with ids/counts only — reject keys named `text`, `content`, `quote`, `value`), `list_events(matter_id, limit=100, before=None)`. Actions used now: `matter.created/updated/archived`, `matter.member_added/removed`, `document.attached/detached/uploaded/deleted`, `rag.asked` (WP1-E wires this one).

### 1.3 Access rules — `services/document_access.py`

Extend `_can_access_entry` and `_can_retrieve_entry`: legacy owner/global rules **or** membership in a matter that contains the document. Add `accessible_document_ids_for_matter(user, matter_id)`.

### 1.4 API — `api/routers/matters.py` (expose `router`), `api/routers/documents.py`

Routes exactly as contracts §8. Responses carry `{id, name, client_ref, description, status, org_id, role (of the caller), document_count, member_count, created_at, updated_at}`. `GET /matters/{id}/documents` returns registry summaries (use `services.document_access` helpers; no server paths) plus `status`/`redaction` fields when present in the entry. Upload endpoints and `ingest-text` accept optional `matter_id` (form field / JSON field): validate membership (`member` or above) before ingesting; link after success; audit `document.uploaded`. `GET /documents?matter_id=` filters to that matter (membership required). `DELETE /documents/{id}` also detaches from all matters and audits.

### 1.5 RAG scoping — `services/rag_context.py`

`RagAskRequest.matter_id: Optional[str] = None`. In `_resolve_rag_request_context` and `_resolve_general_rag_request_context`: when `matter_id` is given, require membership (403 `{"error": "matter_forbidden"}`), compute the matter's document ids, intersect with explicit `document_ids` (empty intersection → 403 as well), and use the result as the scope. The owner filter behaviour from Phase 0 stays for non-admins. Record `matter_id` in the returned context (`context["matter_id"]`) so WP1-E can audit it.

### 1.6 Migration — `scripts/migrate_phase1_matters.py`

For every user: `ensure_personal_workspace`; for every registry entry with an `owner_user_id`, attach it to that user's default matter unless it is already in a matter. Idempotent; prints counts; `--dry-run` flag. Also callable as `services.matters.migrate_existing_documents()` so WP1-E can run it at startup once.

## 2. Tests

`TestClient(app.app)` with `tmp_path` databases (see how `tests/test_phase0_security.py` monkeypatches paths). Cover: workspace provisioning idempotency; CRUD; membership enforcement (non-member 403 on read, member-but-not-lead 403 on member changes); attach/detach; `GET /documents?matter_id=` filtering; upload with `matter_id` links the document (mock `ingest_uploaded_document`); RAG scoping unit tests on the resolver (member with matter → document ids restricted; non-member → 403; intersection rule); audit events written with safe details and `record_event` rejecting text-like keys; migration idempotent (run twice, same counts); access rule extension (member can access a document owned by someone else through the matter).

## 3. Acceptance (run all, paste tails)

```bash
. .venv/bin/activate
python -m pytest -q tests
ruff check --select E9,F63,F7,F82 .
python -m compileall -q $(git ls-files -co --exclude-standard '*.py')
python scripts/dump_openapi_paths.py | diff docs/legal-agent/wp/openapi-expected-after-wp01.txt -   # only the /matters... routes may be added
python scripts/migrate_phase1_matters.py --dry-run
```

## 4. Report format

1. Schema and API summary. 2. Acceptance outputs. 3. How the async upload gets linked to the matter (see ground rules). 4. Deviations. 5. Notes for WP1-E (what to wire: audit of asks, migration at startup) and Phase 4 (UI needs).
