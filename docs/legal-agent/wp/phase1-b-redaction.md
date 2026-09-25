# Phase 1 · WP1-B 任务书：本地脱敏引擎、审阅与确认 API、送模关卡

> 执行者：一个子代理。验收人：主会话。先读 `docs/legal-agent/wp/phase1-contracts.md` §1、§2、§4、§7，再读本文。产品要求见 `docs/legal-agent/00-alignment.md` §2.2 第 3 步和 §3-G。

## 0. Ground rules

- Work in `/home/user/CasualGraph`, venv `. .venv/bin/activate`. **No commits / pushes / branches.**
- Three other agents work in the same tree. **You own:** `legal/redaction/**` except `types.py` (additive changes only, reported), `api/routers/redaction.py` (new), `tests/test_redaction_*.py`, `tests/fixtures/redaction/**`. **Do not touch** `ingest/**`, `pipeline_runtime.py`, `services/**` (use `services.crypto` and `services.document_access._can_access_entry` as they are), `api/routers/*.py` other than yours, `rag/**`, `configs/settings.py`, `app.py`, `requirements*.txt`, `docs/**`.
- **Hard rule: nothing in `legal/redaction` may call a network API** (no model, no embedding, no web). Detection uses regexes, contract-structure heuristics, dictionaries and `jieba.posseg` (already installed). Add a test that monkeypatches `socket.socket` to raise and runs `detect()` on every fixture.
- **Never log or raise with candidate values or block text.** Add a test that captures logging and stdout during `detect`/`apply`/API calls and asserts no candidate value appears.
- Coordinates: `Occurrence` offsets are block-relative in the *original* text. `apply()` must keep block ids, order, pages and bboxes untouched.

## 1. Deliverables

### 1.1 Detectors — `legal/redaction/detectors.py`

Each detector returns candidate spans `(block_id, start, end, value, category, confidence, detector_name, role_hint)`; `engine.detect` merges them. Version every detector (`DETECTOR_VERSIONS` dict).

| Category | Rules (zh + en) |
|---|---|
| `uscc` | 18 chars `[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}`; confidence 0.95, 0.99 with a valid check digit |
| `id_number` | PRC 18-digit with valid checksum (0.99) or 15-digit legacy (0.8); cue words 身份证 raise confidence |
| `phone` | CN mobile `1[3-9]\d{9}`, landline `0\d{2,3}-?\d{7,8}`, international `\+\d{1,3}[- ]?\d{6,12}`, AU `04\d{8}`; must not overlap a `uscc`/`id_number`/`bank_account` span |
| `email` | standard pattern |
| `bank_account` | 12–19 digits (spaces allowed) with a cue within 12 chars: 账号 / 账户 / 银行账户 / Account No / A/C |
| `passport` | `[EeGgDdSsPp]\d{8}`, `[A-Z]{1,2}\d{7}` with cue 护照 / Passport |
| `license_plate` | CN plates incl. new-energy |
| `org` | party headers `^(甲|乙|丙|丁|戊)方(（[^）]*）)?[:：]\s*(.+)$` (role_hint = 甲方…), `Party A[:：]`, `between (.+?) \("(.+?)"\)` / `\(hereinafter[^)]*"(.+?)"\)` (alias); suffix rule `…(有限公司|股份有限公司|有限责任公司|集团|事务所|银行|研究院|大学|医院|中心|协会)`, en `(Ltd\.?|Limited|LLC|Inc\.?|Corp\.?|Corporation|Co\.,?\s?Ltd\.?|GmbH|Pty\.?\s?Ltd\.?|LLP|PLC|S\.A\.|B\.V\.)`; 简称 `以下简称[“"]?(.+?)[”"]?[）)]` becomes an alias of the preceding org |
| `person` | signature-block cues `法定代表人[:：]`, `委托代理人[:：]`, `联系人[:：]`, `签字[:：]`, `Name:`, `By:`, `Attn:`, `Mr\.|Ms\.|Mrs\.|Dr\.` (0.9); `jieba.posseg` `nr` tokens of 2–4 chars not in a stop list (甲方, 乙方, 法定代表人, 本合同…) (0.6); en capitalised 2–3 token sequences without cues (0.4, i.e. rejected by default) |
| `address` | zh: `地址[:：]\s*(.+)` (0.9) or a run containing ≥ 3 of 省/市/区/县/路/街/号/大道/大厦/室/层 (0.6); en: `\d+\s+\w+\s(Street|St\.|Road|Rd\.|Avenue|Ave\.|Drive|Dr\.|Lane|Ln\.|Boulevard|Blvd\.)…` with optional suite/city/postcode |
| `amount` (off by default) | currency symbols/words + digits, Chinese 大写金额 `[壹贰叁肆伍陆柒捌玖拾佰仟万亿元角分整]{4,}` |
| `date` (off by default) | ISO, `YYYY年M月D日`, English month names |
| `custom` | `policy.custom_terms` literal matches (1.0) |

Rules that span all detectors: overlapping spans → longest wins, ties → higher confidence; `policy.keep_party_roles` keeps the words 甲方/乙方/Party A themselves; any accepted `org`/`person` value (and aliases) is searched in **every** block so the same entity is replaced everywhere (`consistency` pass); placeholders are numbered per category in order of first occurrence (`[ORG_1]`, `[ORG_2]`, `[PERSON_1]`…). Candidates below `policy.min_confidence` start as `rejected`, the rest as `pending` (or `accepted` under `auto_confirm`).

### 1.2 Engine — `legal/redaction/engine.py`

`detect(parsed, policy) -> RedactionReview` and `apply(parsed, review) -> RedactionResult`. `apply` rewrites each block's text from its accepted occurrences right-to-left, returns a **new** `ParsedDocument` (deep copy) with `meta.redacted=True`, `meta.redaction_stats`, and a `RedactionMapping` with `role_hint` and aliases. Round trip property: for every accepted candidate, `mapping.reverse(redacted.full_text())` restores the original canonical text.

### 1.3 Store, gate, pipeline, hooks

- `store.py`: `save_review/load_review/save_mapping/load_mapping/review_status(document_id) -> "none"|"pending"|"confirmed"|"skipped"` using `services.crypto.write_encrypted_json/read_encrypted_json` under `REDACTION_DIR` (`<id>.review.json.enc`, `<id>.mapping.json.enc`). Test that the file bytes never contain a candidate value.
- `gate.py`: `is_model_ready(document_id)` and `assert_documents_model_ready(document_ids)` → `RedactionPendingError` when a review exists with status `pending`. Documents with no review at all are ready (legacy).
- `hooks.py`: `ON_CONFIRMED: Optional[Callable[[str], Any]] = None`.
- `pipeline.py`: `redaction_hook(parsed, ctx) -> Optional[ParsedDocument]` (policy = `ctx.policy or RedactionPolicy.default()`; detect → save review; if `policy.auto_confirm`: accept everything ≥ min_confidence, confirm, apply, save mapping, write `PARSED_DIR/<ctx.document_id>.redacted.json` (plain, via `ParsedDocument.to_dict()`), return the redacted document; else return `None`). `confirm(document_id, actor_user_id) -> Dict`: load review + `PARSED_DIR/<id>.original.json.enc`, apply, save mapping and the redacted parsed file, mark confirmed, call `ON_CONFIRMED(document_id)` when set, return `{"status": "confirmed", "summary": review.public_summary(), "finalize": <callback result or None>}`. `ctx` is duck-typed: use only `ctx.document_id`, `ctx.policy`, `ctx.owner_user_id`.
- Also export `forward_map_query(document_ids, text) -> str` (apply each mapping's `forward` so user questions containing real names reach the model as placeholders) and `reverse_map_text(document_ids, text) -> str` for display. WP1-E wires them.

### 1.4 API — `api/routers/redaction.py` (expose `router`)

Routes exactly as contracts §7. Access: load the registry entry with `document_registry.get_entry(document_id, valid_only=False)` and check `services.document_access._can_access_entry(current_user, entry)`; 404 when the entry is missing, 404 `{"error": "redaction_unavailable"}` when no review exists. `PATCH` validates categories/decisions, supports `add` (creates a `custom`/given-category candidate by scanning all blocks for the literal value) and `remove`, and re-saves. `POST /confirm` returns 409 if already confirmed and 400 if nothing is accepted and the policy is not empty… no: confirming with zero accepted candidates is allowed (the reviewer may decide nothing is sensitive) and produces an identity mapping. If `services.audit.record_event` is importable, record `redaction.confirmed` with the public summary; otherwise skip silently (WP1-C may not have landed).

## 2. Fixtures and tests — `tests/fixtures/redaction/`, `tests/test_redaction_*.py`

Build small `ParsedDocument` fixtures in code (zh purchase contract preamble + signature block; en services agreement with "between X Pty Ltd ("Supplier") and Y Ltd ("Customer")", contact block with phone/email/address/bank). Tests: every category detector (positive and negative cases, checksum validation), party header + alias + consistency across blocks, overlap resolution, `keep_party_roles`, `min_confidence` defaults, `apply` invariants (ids/pages/bboxes unchanged, round trip), store encryption, gate, `redaction_hook` auto-confirm and pending paths, `confirm` + `ON_CONFIRMED`, `forward_map_query`, API flow with `TestClient(app.app)` (write the encrypted original parsed file directly, register an entry with `document_registry.register`, then GET → PATCH → confirm → mapping → status; an unrelated user gets 403/404), the no-network test and the no-leak logging test.

## 3. Acceptance (run all, paste tails)

```bash
. .venv/bin/activate
python -m pytest -q tests
ruff check --select E9,F63,F7,F82 .
python -m compileall -q $(git ls-files -co --exclude-standard '*.py')
python scripts/dump_openapi_paths.py | diff docs/legal-agent/wp/openapi-expected-after-wp01.txt -   # only the five /documents/{id}/redaction... routes may be added
grep -rn "requests\.\|httpx\.\|openai\|urllib" legal/redaction && echo "MUST BE EMPTY"
```

## 4. Report format

1. Detector table with measured precision/recall on your fixtures (counts). 2. Acceptance outputs. 3. Any additive change to `types.py` and why. 4. Deviations. 5. Notes for WP1-E (how to install the hook, what the UI needs) and Phase 4 (preview UI data needs).
