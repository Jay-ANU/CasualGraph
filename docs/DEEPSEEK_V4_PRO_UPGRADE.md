# DeepSeek V4 Pro + research UI migration

## Scope

The existing React/FastAPI application is upgraded in place. The research desk
keeps its document ingestion, RAG retrieval, graph view, citations, feedback,
authentication and session state. The new home page is an interactive workflow
preview, not a dashboard of invented live metrics. Its examples are labeled.

The workspace adds a research guide, a persistent desktop focus view, clearer
composer styling, and viewport heights matching the existing responsive navbar.
Focus view hides the sidebar without unmounting the Agent or losing a conversation.

## Provider routing

Both public modes still use the wire values `flash` and `deep`:

- Flash and auxiliary text generation: DeepSeek V4 Pro through its OpenAI-format
  endpoint. Thinking is disabled for bounded quick requests.
- Deep: the same model through DeepSeek's Anthropic-format `/anthropic` endpoint,
  with thinking enabled and the existing layered source/history/graph prompt.
- Extraction, intent routing, query routing, HyDE and prediction inherit the one
  `DEEPSEEK_MODEL` setting. Legacy per-task model variables are no longer read by
  `configs.settings`. No `gpt-*` or `claude-*` identifier is sent by these clients.

`rag.openai_client`, `rag.anthropic_client`, and the `claude_*` function names are
compatibility names used by the existing pipeline. The SDK name is not the model
provider: both factories use the DeepSeek key and an explicit DeepSeek endpoint.
They never default to OpenAI or Anthropic's hosts when the endpoint is missing.
Existing OpenAI and Anthropic API keys are not an implicit fallback for these
text-generation paths. Missing DeepSeek credentials retain the existing pipeline's
unavailable/extractive fallback behavior; no live model capability is implied.

A Deep stream that fails before its first token remains eligible for the existing
Flash fallback. A stream interrupted after visible text appends an explicit
incomplete-answer notice instead of silently treating the partial text as complete.
Provider error details and private prompt contents are not logged by the new Deep
answerer. The existing retrieval and outer SSE orchestration are not rewritten.

Official API contracts:
- https://api-docs.deepseek.com/guides/anthropic_api/
- https://api-docs.deepseek.com/api/create-chat-completion/

## Required backend environment change

Merge the PR, then update the backend's secret/environment configuration and
redeploy. Editing a repository template does not modify an existing Fly deployment.
Use the backend's protected secret store for the key; never put it in a frontend
`REACT_APP_*` variable, source file, commit, screenshot, or chat message.

```dotenv
DEEPSEEK_API_KEY=<set in backend secret store>
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MAX_TOKENS=2048
DEEPSEEK_TIMEOUT=90
DEEPSEEK_MAX_RETRIES=1
RAG_DEEP_MAX_TOKENS=8192
RAG_DEEP_TIMEOUT=120
```

An existing `DEEPSEEK_MODEL=deepseek-v4-flash` is an explicit setting and must be
changed to `deepseek-v4-pro`; changing a code default alone cannot override it.
The supported explicit alternative remains `deepseek-v4-flash`. Invalid model
IDs fail configuration validation instead of being silently mapped to Flash by
the provider. An explicit custom proxy must implement the appropriate format;
use `DEEPSEEK_ANTHROPIC_BASE_URL` if its Messages endpoint has a different path.

The old `RAG_ANSWER_MODE=openai` value remains valid: it selects the existing
answer-generation path, not an OpenAI billing account. `OPENAI_MAX_TOKENS` is
replaced by `DEEPSEEK_MAX_TOKENS`. Keep or increase an explicitly configured
`RAG_DEEP_MAX_TOKENS` as needed; low limits can truncate a thinking answer.

Keep existing embedding, vector-store, graph, auth, storage and CORS settings.
There is no data migration or index rebuild. Do not delete existing provider
secrets until separately checking optional desktop vision/legacy services.
DeepSeek V4 Pro in this migration is a text model; desktop screenshot/vision
summarization is not migrated or verified. The new frontend still needs the
existing `REACT_APP_ESG_API_BASE` to point at the deployed backend.

## Checks

```bash
python -m pip install pytest python-dotenv openai anthropic httpx
python -m pytest tests/test_deepseek_migration.py -q
cd frontend
npm ci --legacy-peer-deps
CI=true npm run build
```

The added GitHub Actions workflow runs these focused provider contracts and the
frontend production build without production credentials. Mock-HTTP checks test
request format and destination; they do not prove live quota, provider latency,
report retrieval quality, or a deployed end-to-end conversation.

After deployment, verify both Flash and Deep on a known report, a cross-report
question, an evidence-missing question and a follow-up. Check the network request
and citation panel, then disconnect a stream to inspect the incomplete state.
Check sign-in, upload, report selection and mobile composition before release.

Rollback: revert the PR and restore the previous backend model configuration.
No uploaded reports, embeddings, database schema or graph data are changed by
this upgrade.
