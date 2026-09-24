# Phase 1 · WP1-A 任务书：页级解析、条款切分、条款级 chunk、引用校验、原件保留

> 执行者：一个子代理。验收人：主会话。先读 `docs/legal-agent/wp/phase1-contracts.md`（契约）再读本文。产品背景在 `docs/legal-agent/00-alignment.md` §2、§3-B′。

## 0. Ground rules

- Work in `/home/user/CasualGraph`, venv `. .venv/bin/activate`. **No commits / pushes / branches.**
- Three other agents work in the same tree at the same time. **You own:** `ingest/**` (except `ingest/models.py`: additive changes only, reported), `legal/clause_segmenter.py`, `legal/citations.py`, `document_processing/**` (may delete), `pipeline_runtime.py`, `ingestion_jobs.py`, `document_registry.py`, `api/routers/document_content.py` (new), `tests/test_parsers.py`, `tests/test_clause_segmenter.py`, `tests/test_chunking.py`, `tests/test_citations.py`, `tests/test_ingest_stages.py`, `tests/fixtures/contracts/**`, `scripts/make_contract_fixtures.py`, and the one assertion in `tests/test_phase0_security.py` that lists registry path keys (line ~191). **Do not touch** `legal/redaction/**`, `services/**`, `api/routers/{documents,matters,redaction,rag}.py`, `rag/**`, `configs/settings.py`, `app.py`, `requirements*.txt`, `docs/**`.
- No network calls in parsing, segmentation or tests. No OCR in this WP (raise a clear error instead).
- Keep the existing upload flow working end to end: with no redaction hook installed, `ingest_uploaded_document` must still produce a `ready` document that the current chat UI can query.

## 1. Deliverables

### 1.1 Parsers — `ingest/parsers/`

`parse_upload(*, document_id, filename=None, file_bytes=None, file_path=None, content=None) -> ParsedDocument`

- Format detection by extension and magic bytes (`%PDF`, zip/`word/document.xml`). `.doc` → `UnsupportedFormatError("legacy .doc, convert to .docx")`. `.rtf` → same error (the old regex stripping was lossy). `.txt/.md` → `text.py`.
- **PDF (`pdf.py`, pdfplumber):** per page, `extract_words()` → lines (group by `top`, tolerance ≈ 3pt) → blocks (new block on vertical gap > 1.3× median line height, on indentation change combined with a numbering label, or on a heading-like line). Block `bbox` = union of its words. `kind="heading"` when the line is short and either larger/bolder than the body or starts with a numbering label. Tables via `page.extract_tables()` become `kind="table"` blocks (rows joined with `"\n"`, cells with `" | "`), and words inside a table's bbox are not emitted again as paragraphs. Detect running headers/footers: normalised line text that repeats in the same vertical band on ≥ 60 % of pages (min 3 pages) is dropped, as are bare page-number lines (`第 3 页 共 10 页`, `Page 3 of 10`, `- 3 -`). Record what was dropped in `meta.warnings` (counts only). If the whole file averages < 20 extractable characters per page, raise `NeedsOcrError`.
- **DOCX (`docx.py`, python-docx):** walk `document.element.body` in order so paragraphs and tables interleave correctly. Paragraph → block with `meta.style`; tables → `kind="table"` blocks. Numbering label: literal label in the text first (`第三条`, `3.2`, `(a)`); otherwise resolve `w:numPr` (numId + ilvl) through the numbering part: keep counters per (numId, ilvl), render `w:lvlText` (`%1.%2`) with `w:numFmt` (`decimal`, `lowerLetter`, `upperLetter`, `lowerRoman`, `upperRoman`, `chineseCounting` → 一二三…, `chineseLegalSimplified`), reset deeper counters when a shallower level advances. Store the result in `meta.numbering_label`, `meta.is_numbered=True`. Headers, footers, footnotes and tracked changes are ignored; add `meta.warnings` entries when footnotes or `w:del/w:ins` exist. `page_no=None`, `pages=[]`.
- **Text (`text.py`):** paragraphs split on blank lines; Markdown `#` headings → `kind="heading"`.
- Language: CJK character ratio > 0.3 → `zh`; < 0.05 → `en`; else `mixed`.
- Cleaning (`ingest/cleaning.py`): normalise whitespace inside a block, unify line endings, strip control characters. **Never delete repeated lines** (headers/footers are handled structurally above). Retire `document_processing/text_cleaner.py`; delete `document_processing/` entirely if nothing else imports it (grep first; `tests/` may).

### 1.2 Clause segmenter — `legal/clause_segmenter.py`

`segment(parsed: ParsedDocument) -> ClauseTree`

- Label families, anchored at block start (after optional whitespace/brackets):
  - zh: `第[一二三四五六七八九十百零〇\d]+[条章节部分编]`, `[一二三四五六七八九十]+、`, `（[一二三四五六七八九十]+）` / `\([一二三四五六七八九十]+\)`, `\d+(?:\.\d+)*[\.、．]?\s`, `（\d+）` / `\(\d+\)`, `[①-⑳]`
  - en: `Article\s+\d+`, `Section\s+\d+(?:\.\d+)*`, `Clause\s+\d+(?:\.\d+)*`, `\d+(?:\.\d+)*\.?\s`, `\([a-z]\)`, `\([ivx]+\)`, `[A-Z]\.\s`
  - Precedence (shallow → deep): 第X章/部分 > 第X条 = Article/Section N > 一、 > 1. > 1.1 > （一） > (1)/(a) > ① / (i). A dotted label's depth is its number of components. DOCX `meta.numbering_label` and `Heading N` styles win over text patterns.
- Structural kinds: `title` (the first heading-like block before any label), `preamble` (blocks between the title and the first numbered node; party lines such as `甲方：…`, `Party A: …`, `between … and …` are recorded in `meta.party_lines=[{"role": "甲方", "block_id": ...}]` so the redactor can use them), `recital` (`鉴于` / `WHEREAS`), `definitions` (first article whose title contains 定义 / Definitions / Interpretation), `annex` (`附件` / `附录` / `Annex` / `Schedule` / `Exhibit` and everything after), `signature` (`签字` / `盖章` / `法定代表人` / `IN WITNESS WHEREOF` / `Signed by` and everything after until an annex).
- Unnumbered blocks attach to the preceding node. `normalized_number` is a dotted path of arabic numerals / letters (`第三条` → `3`, `（一）` under `第三条` → `3.1`, `(a)` → `3.1.a`). `char_start/char_end` come from `parsed.block_offsets()` and cover descendants; `page_start/page_end` from the blocks. `confidence` drops to 0.7 when a sequence skips or repeats a number.
- The tree must be valid: every non-root node's `parent_id` exists, children are in document order, roots are in document order, ranges of siblings do not overlap.

### 1.3 Clause-based chunking — `ingest/chunking.py`

`chunk_document(parsed, tree, *, max_chars=CHUNK_SIZE, overlap=CHUNK_OVERLAP) -> List[dict]`

One chunk per leaf clause; leaves longer than `max_chars` are split on sentence boundaries (`。！？；` `.!?;`) with `overlap` characters carried over; consecutive tiny leaves (< 200 chars) with the same parent are merged up to `max_chars`; `title/preamble/recital/signature/annex` nodes become their own chunks. Every row carries the v1 fields (compat: `chunk_id="chunk_{N}"`, `section=tree.path_label(clause_id)`, `category` = clause kind) and all v2 fields (`chunk_uid`, `page_start/page_end`, `block_ids`, `clause_id`, `clause_label`, `clause_number`, `language`, `schema_version=2`). `validate_chunk_row` must return `[]` for every row.

### 1.4 Citations — `legal/citations.py`

Implement §6 of the contracts: `Citation`, `verify_quote` (exact → normalised → fuzzy, with offsets mapped back to the raw canonical text), `locate(chunk_row, quote, parsed)`, `display_label(citation, document_title, lang)`.

### 1.5 Ingestion stages, original retention, registry, jobs

- Restructure `pipeline_runtime.ingest_uploaded_document` into the stages in contracts §4 with `ingest/context.py::IngestContext` and `ingest/hooks.py::REDACTION_HOOK`. New keyword arguments `matter_id: str = ""` and `policy=None` are accepted and stored on the context (the matter link itself is WP1-C's).
- `stage_store_original`: write the upload to `RAW_DIR/<document_id>/original.<ext>.enc` through `services.crypto.write_encrypted`; text-only ingests store the UTF-8 bytes as `original.txt.enc`.
- `stage_parse`: `parse_upload` → `PARSED_DIR/<id>.original.json.enc` (encrypted) via `services.crypto.write_encrypted_json`; registry status `parsing`.
- Hook: if `REDACTION_HOOK` is `None` continue with the original parsed document; if it returns `None`, set status `pending_redaction`, write nothing plaintext, return `{"document": {..., "status": "pending_redaction"}, ...}`; otherwise continue with the returned (redacted) document.
- `finalize_document(document_id, parsed=None) -> Dict`: load `PARSED_DIR/<id>.redacted.json` (or the passed document; or the encrypted original only when no review file `REDACTION_DIR/<id>.review.json.enc` exists), then segment → chunk → `processed/<id>.txt` (canonical text) → `chunks/<id>_chunks.jsonl` → `clauses/<id>.json` → `build_vector_store` + `build_bm25_index` (unchanged calls) → registry `status=ready` with `language`, `page_count`, `clause_count`, `source_format`, `original_filename`, `schema_version=2`, and the full `paths` set from contracts §2. Idempotent: re-running replaces the derived files.
- `ingestion_jobs.start_finalize_job(document_id, actor=None)` runs `finalize_document` in the existing worker pool and reports progress like uploads do.
- `delete_uploaded_document`: also remove `raw/`, `parsed/`, `clauses/` artefacts and call `rag.vector_store.remove_document(document_id, vector_store_path)` instead of the local repair helper (delete `_repair_active_vector_store_after_delete`).
- `document_registry`: new fields per contracts §3, `set_status()`, and `get_entry()` must return legacy entries unchanged.
- Update the `tests/test_phase0_security.py` assertion that lists `paths` keys to the new set (`raw`, `parsed_original`, `parsed_redacted` (may be absent when no redaction ran), `clauses`, `chunks`, `processed_text`, `vector_store`).

### 1.6 Content router — `api/routers/document_content.py` (expose `router`)

Access check: `services.document_access._can_access_entry(current_user, entry)` (WP1-C extends it; just call it). Legacy documents without parsed files return 404 `{"error": "content_unavailable"}`.

```
GET /documents/{id}/status     {"status", "status_message", "language", "page_count", "clause_count", "redaction": <registry.redaction or null>}
GET /documents/{id}/clauses    ClauseTree.to_dict() + {"labels": {clause_id: path_label}}
GET /documents/{id}/content    {"document_id", "language", "source_format", "pages": [...], "blocks": [{block_id, order, kind, page_no, bbox, text}]}   # from parsed/<id>.redacted.json, else the encrypted original ONLY if no review exists
GET /documents/{id}/file       original bytes (decrypted) with the right media type and Content-Disposition
```

### 1.7 Fixtures — `tests/fixtures/contracts/` + `scripts/make_contract_fixtures.py`

Generate and **commit the files** (keep the folder under 300 KB): (1) `zh_purchase.docx` — 采购合同, `第一条…第十二条`, sub-clauses `1.1/1.2`, `（一）（二）`, a party header `甲方：… 乙方：…`, a table, a signature block; (2) `zh_nda.pdf` — via reportlab with `UnicodeCIDFont('STSong-Light')`, 3+ pages, running header, page numbers, `第X条` structure; (3) `en_services.pdf` — reportlab, `Article 1 … Article 8`, `1.1`, `(a)`, `(i)`, `WHEREAS` recitals, `IN WITNESS WHEREOF`, `Schedule 1`; (4) `en_lease.docx` — Word auto-numbering (`w:numPr`) with three levels and no literal labels in the text; (5) `mixed_notes.txt` — Markdown-ish headings. Also a `scanned_like.pdf` with no text layer (a blank page) for the `NeedsOcrError` test. Each fixture has a golden expectation file (`*.expected.json`) with: top-level count, the first five labels, one nested path, page count, language.

## 2. Tests (write them first where practical)

- Parsers: page count, block count sanity, bbox present for PDF blocks, table blocks, header/footer removal, `NeedsOcrError`, `.doc` rejection, DOCX numbering resolution, language detection, JSON round trip.
- Segmenter: golden expectations for all five fixtures; tree validity; a hand-built `ParsedDocument` covering every label family and the structural kinds.
- Chunking: one chunk per leaf, oversized split with overlap, tiny merge, v2 validation, `section` equals the path label.
- Citations: exact / normalised (full-width punctuation, collapsed whitespace) / fuzzy / not found; offsets map back to the raw text; `display_label` in zh and en.
- Stages: end-to-end `ingest_uploaded_document` on the DOCX fixture into `tmp_path` (monkeypatch the data dirs and `services.crypto.reset_for_tests()`): status `ready`, original file encrypted (bytes do not contain the party name), `finalize_document` idempotent, `pending_redaction` when a stub hook returns `None`, `start_finalize_job` completes.

## 3. Acceptance (run all, paste tails)

```bash
. .venv/bin/activate
python -m pytest -q tests
ruff check --select E9,F63,F7,F82 .
python -m compileall -q $(git ls-files -co --exclude-standard '*.py')
python scripts/dump_openapi_paths.py | diff docs/legal-agent/wp/openapi-expected-after-wp01.txt -   # only the four /documents/{id}/... routes may appear as additions
du -sh tests/fixtures/contracts
python - <<'PY'
from pathlib import Path
from ingest.parsers import parse_upload
from legal.clause_segmenter import segment
from ingest.chunking import chunk_document
from ingest.models import validate_chunk_row
for f in sorted(Path("tests/fixtures/contracts").glob("*.docx")) + sorted(Path("tests/fixtures/contracts").glob("*.pdf")):
    if f.name.startswith("scanned"): continue
    parsed = parse_upload(document_id=f.stem, filename=f.name, file_bytes=f.read_bytes())
    tree = segment(parsed); rows = chunk_document(parsed, tree)
    bad = [p for r in rows for p in validate_chunk_row(r)]
    print(f.name, parsed.language, "pages", len(parsed.pages), "blocks", len(parsed.blocks), "roots", len(tree.roots), "nodes", len(tree.nodes), "chunks", len(rows), "invalid", len(bad))
PY
```

## 4. Report format

1. What was built (one paragraph per deliverable) and what was deleted.
2. Acceptance outputs.
3. Segmentation quality notes per fixture (what it got right, what it missed, why).
4. Any additive change to `ingest/models.py` and why.
5. Deviations. 6. Notes for WP1-E integration and for Phase 2 (do not fix).
