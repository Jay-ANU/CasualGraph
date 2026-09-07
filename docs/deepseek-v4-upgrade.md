# Research Desk / DeepSeek V4 Pro migration

## What changes

The React homepage and research empty state are refreshed; existing authenticated sessions,
document upload, library, citation drawers, graph views and streaming contracts are preserved.
The status strip reads `/models/status`. It reports configuration, **not** a successful API
connection, account credit, or verified model availability. No key is returned to the browser.

The default is `LLM_PROVIDER=deepseek`. Both normal answers and Deep research use
`deepseek-v4-pro`. Deep uses `thinking.type=enabled`, effort `high`; ordinary answers,
JSON extraction and low-token classifiers explicitly set `thinking.type=disabled`.
Prediction, query rewrite/decomposition, graph labels, memory extraction and Word editing
use the selected compatible transport. DeepSeek failures never select Claude automatically.
Embedding/reranking and existing vector/graph stores are unchanged: **do not rebuild indexes**.

## Server configuration

```dotenv
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=replace_only_on_the_server
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_EXTRACTION_MODEL=deepseek-v4-pro
RAG_DEEP_MODEL=deepseek-v4-pro
RAG_ANSWER_MODE=deepseek
CHAT_MAX_TOKENS=2048
RAG_DEEP_MAX_TOKENS=16384
RAG_DEEP_REASONING_EFFORT=high
RAG_DEEP_TIMEOUT=120
```

Merge the desired revision, install `requirements.txt` and restart the backend. Keep the
existing embedding, Pinecone, Neo4j, Redis and auth settings. Never set `REACT_APP_*` to a
model API key. The frontend only needs `REACT_APP_ESG_API_BASE` pointing to the backend.
For Fly, store the new key with `flyctl secrets set DEEPSEEK_API_KEY=...` and deploy the
reviewed revision using the existing `fly.toml`. If model names were previously stored as
Fly secrets, update them as well: secrets override the non-secret settings in `fly.toml`.
This change does not provision a key or deploy to production automatically.

Old GPT/Claude overrides for chat helper models are ignored under the DeepSeek provider.
An explicit DeepSeek model override is respected: replace old `deepseek-v4-flash` values
where Pro is desired. Replace old 2,000-token Deep caps as shown above; reasoning and
answer share this budget. Existing OpenAI/Anthropic keys are not sent to DeepSeek.

## Screenshot support

V4 Pro is text-only. Screenshot summary now returns a clear `503 vision_unavailable` before
consuming application quota unless a separate image-capable service is configured with
`VISION_API_KEY`, `VISION_BASE_URL`, and `VISION_MODEL`. A vision model/key is never guessed
or silently borrowed from another provider. Text/PDF/Word extraction is unaffected.

## Verification

```bash
python -m compileall -q app.py configs rag ai_service
python -m pytest -q tests
cd frontend
npm ci
npm test -- --watchAll=false --runInBand
npm run build
```

The tests use mocks and do not spend provider credit. Before release, with real server
credentials, check `/models/status`, then ask a cited question in Fast and Deep using a
known indexed report. Verify the citations, `backend` label, evidence drawer and upload.
Try an invalid key and a temporary provider error: the UI must not claim a connected
model, and the backend must not spend Claude credit. Interrupted output must remain
explicitly incomplete rather than be spliced together with an unrelated fallback.
The configuration endpoint by itself is **not** sufficient for this live acceptance check.

## Rollback

To restore the former OpenAI/Fast + Claude/Deep setup, explicitly set `LLM_PROVIDER=openai`,
`RAG_ANSWER_MODE=openai`, `OPENAI_MODEL`, `OPENAI_API_KEY`, `RAG_DEEP_MODEL` to a valid Claude
model, and `ANTHROPIC_API_KEY`. Restoring old code is also possible through Git. No persisted
document/chat/vector schema migration is made by this upgrade.

## API references (checked 2026-09-07)

- https://api-docs.deepseek.com/ — model IDs and compatible API base URL.
- https://api-docs.deepseek.com/guides/thinking_mode/ — thinking flags, effort and separate reasoning content.
- https://api-docs.deepseek.com/quick_start/pricing/ — model capabilities.
