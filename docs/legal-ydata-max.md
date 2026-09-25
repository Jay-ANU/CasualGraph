# YData model selection and Max-only Legal

The existing homepage, `/agent`, `/research`, other site pages and Word tracked-revision exporter are preserved. This change is isolated to Legal model routing and membership enforcement.

## Backend configuration

Set `YDATA_API_KEY` as a Fly backend secret. The user-provided `Bearer ...` is a placeholder, not a usable credential. Do not put the key in Vercel frontend variables, source control, browser storage, API responses or logs. Existing research provider keys are not reused or sent to YData.

The destination is fixed to `https://www.ydata.space/v1`. The backend uses `GET /models` for the credential's actual model catalog and `POST /chat/completions` for generation. The frontend never calls the gateway directly. Responses from redirects are rejected.

By default, text-chat candidates in the GPT (including o-series), Claude, DeepSeek, Kimi/Moonshot and GLM families are discovered automatically. Embedding, image, speech, realtime and other non-text models are excluded. A listed ID is not a guarantee that the gateway supports that model on the chat-completions route; unavailable/unsupported models fail explicitly, without substituting another model or provider.

`LEGAL_YDATA_DEFAULT_MODEL` optionally selects an existing catalog ID. `glm-5.2` is preferred only when actually listed. `LEGAL_YDATA_MODELS` optionally supplies an administrator-reviewed JSON array of exact model IDs, e.g. `["glm-5.2"]`, when the gateway does not expose a models route or the operator wants a restricted list. Such a list is labeled administrator-configured, not live-discovered. Do not populate it with guessed models. The short-lived in-memory catalog cache is invalidated when credentials or configured inventory change.

Generation uses the supplied chat protocol with per-family output token budgeting, no universal temperature/thinking/JSON-mode flags, local strict JSON validation and no automatic generation retry. Truncation, authorization failure, rate limits, network errors and invalid JSON cannot become published review conclusions. Functional tests use synthetic model IDs/responses; no production gateway call has been proven without a real key.

## Max memberships

All private `/legal/*` routes have a server-side Max dependency, including uploads, reading contracts, policies, review/resume, decisions, model lists and exports. `/legal/version` remains public deployment metadata. `/legal/access` requires login and returns only the current user's entitlement status. The frontend waits for that endpoint before mounting the workbench; changing localStorage cannot grant backend access. Free, Pro, expired and revoked memberships are denied.

The existing admin-to-Max mapping is retained for compatibility. A new `max_memberships` table independently grants Max to ordinary registered customers without changing their `users.role`. Administrators manage grants at `/admin/memberships` using admin-only GET/PUT/DELETE `/admin/max-memberships` routes, optional expiry, compare-and-swap version checks and audit entries. This does not create a billing/payment system. Existing Pro allowlists are unchanged. `/auth/me` and existing RAG plan resolution include active Max grants.

Review workers re-read membership and matter access before external retrieval and each model generation/verification step. Revocation stops subsequent steps, not a request already in flight. No contracts are deleted when membership ends.

## Review snapshots and privacy

New jobs require an allowed `model_id`, `external_processing_provider: "ydata"`, redaction confirmation and explicit external processing consent. The UI names the YData gateway and resets consent on model changes. The selected model ID/family/provider are frozen in each review's profile, included in idempotency hashing and in exported review reports. Both initial review and semantic verification use that snapshot, never mutable global research configuration. Resume never switches models. Legacy unfinished reviews without YData-specific consent require a fresh review; completed historical results remain readable by authorized Max users.

Only confirmed redacted blocks and applicable company rules are sent to the configured gateway; gateway catalog requests contain no contract. External legal retrieval and its citation validation remain separate. The original DOCX is used only by the existing native revision exporter; accepted suggestions remain pending insertions/deletions in Word.

## Release checks

The production frontend gate requires the backend's `max_only=true`, `model_gateway=ydata` and `model_selection_version=1` in addition to its product version. This prevents a model selector from shipping against a backend without Max enforcement. Deploy the backend first, then the frontend. GitHub Actions requires the authorized `FLY_API_TOKEN`; providing a YData inference key does not provide Fly deployment authority.

Validate Free/Pro denial, a non-admin Max account, expiration/revocation, model lists, a confirmed redacted synthetic contract, source-backed review, and tracked DOCX export after deployment. Never infer these live results from mocked CI or from Vercel READY alone.

Revocation retains an expired, versioned membership record; reactivation is an edit at the current version. This prevents stale revoke requests from affecting a new grant.
