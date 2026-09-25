# Phase 1 · WP1-D 任务书：多文档索引层（替换"最后一份文档"的 active store）

> 执行者：一个子代理。验收人：主会话。先读 `docs/legal-agent/wp/phase1-contracts.md` §1、§9，再读本文。问题背景 `docs/legal-agent/00-alignment.md` §1.12（P10）。

## 0. Ground rules

- Work in `/home/user/CasualGraph`, venv `. .venv/bin/activate`. **No commits / pushes / branches.**
- Three other agents work in the same tree. **You own:** `rag/vector_store.py`, `rag/bm25_index.py`, `rag/pinecone_store.py`, `rag/retriever.py` (only the parts that talk to the stores; keep the fusion/layer logic), `scripts/build_vector_index.py`, `scripts/rebuild_index_catalog.py` (new), `tests/test_vector_index_*.py`. **Do not touch** `pipeline_runtime.py` (WP1-A calls your stable functions), `ingest/**`, `legal/**`, `services/**`, `api/**`, `configs/settings.py`, `app.py`, `requirements*.txt`, `docs/**`.
- **Every public signature listed in contracts §9 keeps working**, including `_apply_local_filters` and `_build_pinecone_filter` (imported by `tests/test_phase0_security.py`) and `load_vector_store` (imported by `rag/bm25_index.py`, which you own, and possibly others: grep before changing). `ACTIVE_VECTOR_STORE_FILE` stays defined in settings; your code may stop using it (leave a one-time migration that reads it).
- Tests use the deterministic hash-fallback embeddings (`rag/embeddings.py`: no model available in CI) — do not add a model download.

## 1. Design

- **Catalog:** `VECTOR_DIR/catalog.json` `{ "version": 1, "shards": { "<document_id>": { "location", "provider", "owner_user_id", "visibility_scope", "document_group", "domain", "chunk_count", "dim", "updated_at" } } }`, written atomically (tmp + `os.replace`) under a process lock. `build_vector_store(chunks, persist_path)` writes the shard (as today: `metadata.json` + `index.faiss` or `index.pkl`) **and** upserts its catalog entry; `remove_document` deletes the shard and the entry; `rebuild_catalog()` scans `VECTOR_DIR/*/metadata.json` (also used by `scripts/rebuild_index_catalog.py` and lazily when the catalog is missing but shards exist — the one-time migration).
- **Shard selection:** from `filters`: `document_ids` → those shards; otherwise all shards, then apply the owner/visibility rule at the *shard* level using the catalog (`owner_user_id` matches, or `visibility_scope == "global"`, or legacy group rules — mirror `_apply_local_filters` exactly so the two agree; keep applying `_apply_local_filters` per row afterwards as the source of truth). `domain`, `document_group`, `source_type` filters apply per row as today.
- **Vector search:** LRU cache of loaded shards (`VECTOR_SHARD_CACHE_SIZE`), invalidated by `updated_at`; search each selected shard for `top_k`, merge by score (inner product on normalised vectors, as now), then the existing `preferred_document_id` behaviour: primary document first, fill the remainder from the others (see the current `_search_local` logic and keep its observable behaviour, including `exclude_document_ids`).
- **BM25:** per-shard `bm25.pkl` stays (tokens + metadata). `search_bm25(query, top_k, filters)` selects shards the same way, then builds a merged `BM25Okapi` over the selected shards' token lists when their total chunk count ≤ `BM25_MERGE_MAX_CHUNKS` (cached by the sorted shard-id + `updated_at` key); above the cap, search per shard and min-max normalise scores before merging. `warm_bm25_index()` warms the catalog and the most recent shard only.
- **Pinecone:** unchanged namespace for now; drop the "active document / mix corpus" logic; `_build_pinecone_filter` semantics unchanged. `delete_vectors_by_document_id` and `pinecone_available` stay.
- **Deletion:** `remove_document(document_id, persist_path)` (already stubbed at the bottom of `rag/vector_store.py`): remove the shard directory, the catalog entry, cached shard, and — for the transition only — repair or remove the legacy active-store file. Replace the stub body.
- Remove the "American Airlines" special case in `rag/retriever.py` (lines ~370-373) — it is a demo hack, not behaviour to preserve. Keep the keyword-scan fallback (`retriever.py` ~313-361) but make it iterate all accessible chunk files, not only the active one, or delete it if the catalog makes it redundant (say which in the report).

## 2. Tests — `tests/test_vector_index_*.py`

Using `tmp_path` for `VECTOR_DIR` (monkeypatch settings and module constants), build three documents with distinct vocabularies via `build_vector_store` + `build_bm25_index`:

- vector `search` with no `document_ids` and the owner filter returns hits from all three documents (not only the last one); with `document_ids=[b]` only b; with `preferred_document_id=a` a's rows come first; a private document of another owner never appears for a non-admin filter; a `visibility_scope=global` document appears for everyone.
- `search_bm25` likewise across shards; merged mode vs per-shard mode (force by monkeypatching `BM25_MERGE_MAX_CHUNKS`) both return the expected document for a distinctive term.
- `remove_document` deletes the shard and catalog entry and the remaining documents stay searchable; catalog rebuild from a directory without `catalog.json`; legacy `active_store_path.txt` present → still works and is cleaned up.
- The two `tests/test_phase0_security.py` filter tests keep passing unchanged.
- A regression test that reproduces the old bug: ingest two shards, search a term that only exists in the first, assert it is found.

## 3. Acceptance (run all, paste tails)

```bash
. .venv/bin/activate
python -m pytest -q tests
ruff check --select E9,F63,F7,F82 .
python -m compileall -q $(git ls-files -co --exclude-standard '*.py')
python scripts/dump_openapi_paths.py | diff docs/legal-agent/wp/openapi-expected-after-wp01.txt - && echo ROUTES_UNCHANGED
grep -n "American Airlines" -r rag && echo "MUST BE EMPTY"
```

## 4. Report format

1. Catalog and shard design as built. 2. Acceptance outputs. 3. Behaviour differences the retriever or Phase 2 should know about (score scales, preferred-document semantics). 4. Deviations. 5. Notes for WP1-E (migration command for existing deployments) and Phase 2.
