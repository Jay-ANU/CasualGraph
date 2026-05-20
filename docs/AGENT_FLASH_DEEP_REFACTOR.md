# Agent: Flash / Deep model-tier system (replace fixed Predict format)

## Context

Today the Agent has three intent-shaped modes — **Ask**, **Predict**, **Reason on graph** — exposed as a single "Predict" pill in the input bar. `Predict` is hard-coded to a strict JSON schema (confidence enum + causal_chain + evidence_refs + counter_evidence + disclaimer; see `rag/prediction.py:26-66`), rendered by a bespoke `PredictionAnswerPanel` component. Streaming is disabled for Predict, and the output cannot deviate from the schema. This is rigid and out of step with modern AI tooling (Claude Flash/Deep, Perplexity Pro Search, Grok Deep Think) where the selector is a **model-tier** choice and the output stays free-form markdown.

The user has decided:
- **Selector becomes Flash / Deep** (model tier), not Ask / Predict (output format).
- **Flash = current OpenAI model `gpt-5.4-mini`** + single-pass vector/hybrid retrieval (today's "ask" path, no change).
- **Deep = Anthropic Claude API** + deeper retrieval (layered + graph context + decomposition).
- **Drop the Predict JSON pipeline entirely.** Both modes return plain streaming markdown; the model may use "Evidence:", "Reasoning:", "Conclusion:" headings naturally, but no special UI.
- Intended outcome: a flexible chat surface that matches industry-standard AI agents, a clear cost/quality tradeoff between two distinct providers, and a much simpler frontend (no more `PredictionAnswerPanel` JSON contract to maintain).

The pre-existing `RagReasoningMode = 'flash' | 'deep'` type (`frontend/src/types/api.ts:31`) and the `reasoning_mode` field on `RagAskRequest` (`app.py:624`) are already half-wired — the FE just never sends them, and the backend never differentiates. This refactor finishes that work and removes the legacy `predict` branch.

---

## Frontend changes

### 1. `frontend/src/pages/Agent.tsx`

| Where | Change |
|---|---|
| `Agent.tsx:691-697` | Rename state: `answerMode: 'ask' \| 'predict' \| 'graph'` → `tier: 'flash' \| 'deep'`. Init from URL param: `?tier=deep` (keep `?mode=predict` accepting Deep for backward URL compat). |
| `Agent.tsx:697` | Remove the `effectiveMode = answerMode === 'graph' ? 'predict' : answerMode` line. No legacy mapping. |
| `Agent.tsx:225-248` `getLoadingSteps` | Re-key on tier. **Flash**: 4 quick steps ("Routing query", "Searching reports", "Reading top sources", "Writing answer"). **Deep**: 8 steps ("Routing query", "Decomposing question", "Layered search across current / historical / regulatory", "Reading top sources", "Pulling graph context", "Composing structured analysis", "Citing evidence", "Finalising answer"). |
| `Agent.tsx:1549-1563` request payload | Drop `mode`. Add `reasoning_mode: tier`. Backend reads only `reasoning_mode`. |
| `Agent.tsx:1587-1602` response handling | Drop the `payload?.mode === 'predict' && isPredictionAnswer(...)` branch. Always treat `answer` as markdown string. Stop storing `messageData.prediction`. |
| `Agent.tsx:2273` `isPrediction` | Delete this derived flag entirely. |
| `Agent.tsx:2311-2315` render branch | Drop `<PredictionAnswerPanel>` branch. Always render the `ReactMarkdown` block. |
| `Agent.tsx:2445-2456` mode button | Replace single Predict toggle with a 2-segment Flash/Deep pill (matching the existing scope toggle pattern at `Agent.tsx:2416-2434`). Flash = ⚡ Zap icon. Deep = 🧠 BrainCircuit (already imported in Home.tsx; add to imports). Active = `border-ink bg-ink text-white`; inactive = `border-hairline bg-canvas text-ink-steel hover:border-ink`. |
| `Agent.tsx:6` imports | Drop `Zap` (Predict) if no longer used elsewhere; add `BrainCircuit` from `lucide-react`. |
| `Agent.tsx` `import PredictionAnswerPanel` line | Remove import. |

### 2. `frontend/src/types/api.ts`

- `RagReasoningMode` (line 31) — promote to the primary selector field. Already correctly typed.
- `RagResponse` — keep `reasoning_mode?: RagReasoningMode` (line 75). Now always populated by backend.
- Remove `prediction?: PredictionAnswer` from any response types where it appears (do **not** delete the `PredictionAnswer` type itself yet — keep it as dead code for one release for backward-compat with any cached responses).
- `RagStreamEvent` — unchanged (text/token/done events stay tier-agnostic, just like today's ask streaming).

### 3. `frontend/src/components/PredictionAnswer.tsx`

- **Do not delete.** Becomes dead code. Add a one-line deprecation comment at top: `// Deprecated: legacy Predict JSON renderer. Will be removed in a follow-up cleanup PR.`
- No import from Agent.tsx after refactor.

### 4. Files **not** touched (per prior user note)

- `frontend/src/pages/CausalInference.tsx`, `EsgDemo.tsx`
- `frontend/src/components/KnowledgeGraphView.tsx`, `GraphVisualizer.tsx`

---

## Backend changes

### 5. `app.py` — request / response contract

- **`RagAskRequest`** (`app.py:616-627`):
  - `mode` field — keep for one release, accept silently, ignore.
  - `reasoning_mode: Optional[Literal['flash', 'deep']] = 'flash'` — becomes the primary field.
- **Streaming endpoint** `/rag/ask/stream` (`app.py:1337`):
  - Lift the `NotImplementedError` for non-ask modes (`app.py:723`).
  - Both Flash and Deep stream markdown via the same SSE plumbing. Deep's SSE events are bridged from Anthropic's stream by the adapter in `rag/claude_answering.py`, so the wire-shape is identical to Flash from the FE's POV.
- **Non-streaming** `/rag/ask` (`app.py:1261`):
  - Response payload: `{ answer: <markdown string>, sources, graph_sources, timings_ms, reasoning_mode, routing }`.
  - Drop the `prediction` JSON key. Drop `_build_predict_payload`.

### 6. `rag/rag_pipeline.py`

- **`_resolve_answer_mode`** (`rag/rag_pipeline.py:55-71`):
  - Rewrite as `_resolve_tier(reasoning_mode)` returning `'flash' | 'deep'`. Default `'flash'`.
  - Remove all heuristic regex (`_PREDICT_STRONG_PATTERN`, `_PREDICT_DEEP_PATTERN`) that auto-promote queries to predict.
- **`answer_question`** (~line 494):
  - Flash branch: existing `_run_routed_retrieval` (vector_only / hybrid) + `generate_openai_rag_answer()` with `RAG_FLASH_MODEL`. No change to retrieval depth.
  - Deep branch: force strategy to `layered` + always include graph_context. Optionally invoke `decompose_query` for compound questions. Then call new `rag.claude_answering.generate_claude_deep_rag_answer()` with `RAG_DEEP_MODEL`.
  - If Deep is selected but `anthropic_configured()` is false, fall back to Flash automatically and emit a meta event so the FE can show a tiny notice.
  - Drop the `if resolved_mode == "predict": generate_prediction(...)` branch entirely. No more `prediction` field returned.
- Return dict always contains `reasoning_mode: tier`.

### 7. **New file**: `rag/claude_answering.py` — Deep generator (Anthropic)

Implements `generate_claude_deep_rag_answer(query, layered_context, graph_context, history_block, model=RAG_DEEP_MODEL, ...)`:

- Uses the official `anthropic` Python SDK (`from anthropic import Anthropic`) with streaming (`client.messages.stream(...)`).
- **Provider-agnostic SSE adapter**: normalises Anthropic's stream events (`content_block_delta`, `message_stop`) into the same `{type: 'token' | 'meta' | 'done', ...}` shape the frontend already consumes via `readSseEvents`. The FE does not need to know which provider generated the tokens.
- **System prompt** (Claude-tuned, encourages but does not enforce structure): _"You are an ESG research analyst. When the question is analytical or speculative, organise your answer with 'Evidence', 'Reasoning', 'Conclusion' markdown headings. Cite sources inline with `[chunk_N]`, `[prior_N]`, or `[G_N]` markers. Be explicit about uncertainty. Never invent figures."_
- Higher `max_tokens` (e.g. 2000 vs Flash's 600).
- Accepts `layered_context` dict (primary + priors + regulatory) and graph triples — flattens them into the prompt context (Claude prefers structured XML-like tags for context blocks; use `<sources>...</sources>`, `<graph>...</graph>`).
- **Error / fallback**: if `ANTHROPIC_API_KEY` is missing or the call errors out, emit one SSE `meta` event `{ fallback_to_flash: true, reason: "..." }`, then delegate to `generate_openai_rag_answer` so the user still gets an answer.

### 7a. **New file**: `rag/anthropic_client.py` — thin client factory

Mirrors the existing `rag/openai_client.py` pattern. Provides `get_anthropic_client()` that lazy-instantiates the SDK with `ANTHROPIC_API_KEY` and respects `ANTHROPIC_BASE_URL` if set (for proxies). Returns `None` if unconfigured so callers can fallback.

### 7b. `requirements.txt`

Add `anthropic>=0.40.0` (or current pinned version). No other changes.

### 8. `configs/settings.py`

- Add `RAG_FLASH_MODEL = os.getenv("RAG_FLASH_MODEL", "gpt-5.4-mini")` (current OpenAI tier — env-overridable).
- Add `ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")`.
- Add `ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")`.
- Add `RAG_DEEP_MODEL = os.getenv("RAG_DEEP_MODEL", "claude-opus-4-7")` (latest Claude 4.x Opus per system knowledge; env-overridable so user can pin Sonnet for cost).
- Add `RAG_DEEP_MAX_TOKENS = int(os.getenv("RAG_DEEP_MAX_TOKENS", "2000"))`.
- Add `anthropic_configured()` helper mirroring `openai_configured()`.
- Keep `RAG_PREDICTION_*` constants for now (referenced by dead `rag/prediction.py`), but stop reading them anywhere.
- Update `.env.example` with the four new vars (`ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `RAG_FLASH_MODEL`, `RAG_DEEP_MODEL`).

### 9. `rag/prediction.py`

- **Do not delete.** Add a top-of-file deprecation note: `# Deprecated: replaced by rag/openai_answering.generate_openai_deep_rag_answer. Will be removed once no callers remain.`
- The file becomes unreachable once `rag/rag_pipeline.py` drops the predict branch.

---

## Files modified (summary)

| Path | Type | Lines touched (approx) |
|---|---|---|
| `frontend/src/pages/Agent.tsx` | Refactor | ~70 (state, payload, render branch, mode toggle, loading copy) |
| `frontend/src/types/api.ts` | Trim | ~10 |
| `frontend/src/components/PredictionAnswer.tsx` | Deprecate comment | 1 |
| `app.py` | API contract | ~30 (RagAskRequest, response builders, streaming guard) |
| `rag/rag_pipeline.py` | Branch rewrite | ~80 (tier resolution, ask/deep dispatch, Flash fallback) |
| `rag/claude_answering.py` | **New** | ~180 (Claude streaming + SSE adapter + Flash fallback) |
| `rag/anthropic_client.py` | **New** | ~30 (lazy SDK client) |
| `configs/settings.py` | New env vars + helper | ~12 |
| `requirements.txt` | New dep | 1 (`anthropic>=0.40.0`) |
| `rag/prediction.py` | Deprecate comment | 1 |
| `.env.example` | Doc | ~6 |

Touch order (recommended):
1. Backend deps + settings (`requirements.txt`, `configs/settings.py`, `.env.example`).
2. Backend Anthropic client + Deep generator (`rag/anthropic_client.py`, `rag/claude_answering.py`).
3. Backend pipeline + API contract (`rag/rag_pipeline.py`, `app.py`).
4. Frontend types (`api.ts`).
5. Frontend Agent.tsx — state, payload, render branch.
6. Frontend Agent.tsx — UI (Flash/Deep toggle, loading copy).
7. Deprecation comments on dead files (`rag/prediction.py`, `PredictionAnswer.tsx`).

---

## Verification

1. **Install deps**: `pip install -r requirements.txt` picks up `anthropic`.
2. **Compile**:
   - `cd frontend && npx tsc --noEmit` — zero errors.
   - `python -c "import app; import rag.rag_pipeline; import rag.claude_answering; import rag.anthropic_client"` — no import errors.
3. **Smoke tests** (no API keys required):
   - Deep without `ANTHROPIC_API_KEY` → falls back to Flash, emits meta event with `fallback_to_flash: true`.
   - Flash with `OPENAI_API_KEY` unset → existing graceful-degradation path still works.
4. **Unit tests**: `python -m pytest tests/ -x` should still pass. Existing `test_predict_*` tests may need to be moved to `_test_predict_deprecated.py` or deleted; add new tests for `generate_claude_deep_rag_answer` (mock the Anthropic client to assert SSE event shape).
5. **Manual E2E** (with both API keys configured):
   - Start backend (`uvicorn app:app --reload`) + frontend (`npm start`).
   - Send a Flash query ("What was NVIDIA's Scope 1 in 2023?") — expect fast streaming markdown from gpt-5.4-mini, vector_only retrieval, ~1-2s.
   - Send a Deep query ("How might Apple's 2030 carbon-neutral target affect their supplier audit posture?") — expect slower streaming markdown from Claude with Evidence/Reasoning/Conclusion sections, layered retrieval + graph context, ~4-10s.
   - Toggle Flash/Deep mid-session — next message uses new tier. Previous message bubbles remain unchanged.
   - Refresh page with `?tier=deep` URL — Deep is pre-selected.
6. **Regression check**: visit `/admin`, `/home`, `/about`, `/login` — unchanged.
7. **Network panel inspection**:
   - Flash request body: `{ ..., reasoning_mode: "flash" }`, response stream uses SSE with `event: token`, no `prediction` key in final payload.
   - Deep request body: `{ ..., reasoning_mode: "deep" }`, same SSE shape (provider-agnostic from the FE's POV), larger payload.
