# Legal model providers and Max-only access

The existing homepage, `/agent`, `/research`, other site pages and Word tracked-revision exporter are preserved. This change is isolated to Legal model routing and membership enforcement.

## Backend configuration

Claude uses Anthropic's official API with the server-side `ANTHROPIC_API_KEY`. GPT, DeepSeek, Kimi and GLM use their existing `YDATA_GPT_API_KEY`, `YDATA_DEEPSEEK_API_KEY`, `YDATA_KIMI_API_KEY` and `YDATA_GLM_API_KEY` credentials. `YDATA_API_KEY` remains the legacy credential for those four families; a dedicated family key wins. `YDATA_CLAUDE_API_KEY` is retired and is never used to send a contract. Configure these keys as Fly backend secrets, never frontend variables.

Destinations are fixed to `https://api.anthropic.com/v1` and `https://www.ydata.space/v1`. Legal Claude ignores the legacy RAG `ANTHROPIC_BASE_URL` override. The backend discovers official models through Anthropic `GET /models` with bounded pagination, discovers each configured YData family through its own `GET /models`, and combines the results. Every model row has `provider: "anthropic"` or `"ydata"`; a mixed catalog has top-level `provider: "mixed"`. The frontend never receives or chooses credentials. A failing provider does not hide healthy models from another provider; affected families and sanitized `provider_errors` are returned. If no provider produces a usable catalog, the request fails explicitly.

At generation time the selected ID and saved provider must match the current route and available catalog. Selection reads only the chosen provider's independently cached inventory, so Claude does not wait for YData discovery and YData does not wait for Anthropic. Claude uses native `POST /messages` with `x-api-key` and `anthropic-version: 2023-06-01`; the other families use YData `POST /chat/completions`. YData keys cannot be shared across two dedicated family slots. No provider failure triggers credential fallback or automatic model substitution.

Text-chat candidates in GPT (including o-series), Claude, DeepSeek, Kimi/Moonshot and GLM are discovered automatically. Embedding, image, speech, realtime and other non-text models are excluded. Retired official Claude models and all Claude entries returned by YData are excluded. Discovery does not itself test generation permissions or account balance.

`LEGAL_YDATA_DEFAULT_MODEL` retains its existing name and may select any ID in the merged catalog, including an official Claude ID. `glm-5.2` is preferred only when listed. `LEGAL_YDATA_MODELS` and `LEGAL_ANTHROPIC_MODELS` can provide administrator-reviewed JSON arrays of exact IDs for their respective providers. Claude entries remaining in the old YData array are ignored; move approved official IDs to `LEGAL_ANTHROPIC_MODELS` or leave it empty for discovery. Never populate either array with guessed models. Credential, inventory and default-model changes invalidate the short-lived catalog cache.

Anthropic defaults to streaming with `LEGAL_ANTHROPIC_STREAM=1`; `LEGAL_ANTHROPIC_MAX_TOKENS` defaults to 8192 and is capped to the official model's reported output limit when available. System instructions use the native top-level `system` field. No OpenAI JSON-mode, temperature or thinking flags are forwarded. Only complete text output with `end_turn` is parsed as JSON; streaming also requires closed content blocks and `message_stop`. Truncation, errors and incomplete responses do not become review conclusions. The adapter makes one generation request per attempt; bounded retries are accounted for by the existing review worker, including the two-call maximum for each ultra-fast attempt.

The protocol follows the official [Messages API](https://platform.claude.com/docs/en/api/messages/create), [model catalog](https://platform.claude.com/docs/en/api/models/list) and [streaming documentation](https://platform.claude.com/docs/en/build-with-claude/streaming). Functional tests use synthetic IDs, responses and contracts; real generation needs a valid official key and account access.

## Max memberships

All private `/legal/*` routes have a server-side Max dependency, including uploads, reading contracts, policies, review/resume, decisions, model lists and exports. `/legal/version` remains public deployment metadata. `/legal/access` requires login and returns only the current user's entitlement status. The frontend waits for that endpoint before mounting the workbench; changing localStorage cannot grant backend access. Free, Pro, expired and revoked memberships are denied.

The existing admin-to-Max mapping is retained for compatibility. A new `max_memberships` table independently grants Max to ordinary registered customers without changing their `users.role`. Administrators manage grants at `/admin/memberships` using admin-only GET/PUT/DELETE `/admin/max-memberships` routes, optional expiry, compare-and-swap version checks and audit entries. This does not create a billing/payment system. Existing Pro allowlists are unchanged. `/auth/me` and existing RAG plan resolution include active Max grants.

Review workers re-read membership and matter access before external retrieval and each model generation/verification step. Revocation stops subsequent steps, not a request already in flight. No contracts are deleted when membership ends.

## Review snapshots and privacy

New jobs require an allowed `model_id`, the matching `external_processing_provider` (`"anthropic"` or `"ydata"`), redaction confirmation and explicit external-processing consent. The UI names the actual recipient and resets consent when either model ID or provider changes. A stale or mismatched recipient is rejected before creating the job. The selected ID/family/provider are frozen in the review profile and included in idempotency hashing and exported reports. Workers, resume, follow-up questions and optional draft checks use that snapshot. Official Claude question/check requests also name `external_processing_provider: "anthropic"` explicitly.

Old Claude/YData reviews cannot silently migrate to Anthropic: new external calls require a new review with official-provider consent. Their existing results and local exports remain available. Export never invokes a model or requires a provider's approval; the [user-controlled export flow](legal-agent/direct-draft-export.md) remains unchanged.

Only confirmed redacted blocks and applicable review materials are sent to the selected provider; catalog discovery contains no contract. External legal retrieval remains separate. The original DOCX is used by the local native revision exporter; selected revisions remain actual insertions/deletions in Word.

## Release checks

The production frontend gate requires `max_only=true`, `model_gateway=mixed`, `model_selection_version=2`, `draft_release_version=2` and the existing API capabilities. Deploy the backend first, then the frontend. GitHub Actions needs an app-scoped `FLY_API_TOKEN` in repository or production-environment Actions secrets. Claude inference independently needs `ANTHROPIC_API_KEY` in Fly backend secrets. The deployment check accepts official-Claude-only Legal configuration; an old YData Claude key alone no longer qualifies. Missing Claude configuration is reported without disabling healthy providers.

Validate Free/Pro denial, a non-admin Max account, expiration/revocation, model lists, a confirmed redacted synthetic contract, source-backed review, and tracked DOCX export after deployment. Never infer these live results from mocked CI or from Vercel READY alone.

Revocation retains an expired, versioned membership record; reactivation is an edit at the current version. This prevents stale revoke requests from affecting a new grant.
