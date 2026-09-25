# Legal release handoff

The repository's Vercel project builds from the repository root, not `frontend/`. Root `vercel.json` is authoritative for this project. It runs four release-gate tests, verifies `/legal/version` in production only, and then builds Vite. The production gate intentionally stops a new frontend from replacing the working site before the required backend is deployed; previews remain available. A READY preview is not a successful production release.

## Authorized release order

1. An administrator supplies an app-scoped Fly deploy token as GitHub Actions secret `FLY_API_TOKEN` in this repository or its `production` environment. Do not put token values in the repository, issue comments, CI output, or chat.
2. Run the existing **Deploy Fly backend** workflow against `main`. It verifies model configuration and the contract API; preserves any existing REDACTION_KEY and stages a new Fernet key only if one is absent.
3. After the Fly workflow succeeds and `/legal/version` returns product `contract-review`, version `1.0.0`, redeploy the corresponding `main` commit in Vercel. The release gate then permits the production build.
4. Perform an authenticated synthetic-contract smoke test with real external model calls, and obtain professional review of labelled examples before relying on substantive legal output.

## Verified before release-gate-only change

CI run 36092934098 at commit 7c03948adc941d7816ddddf27a8dda4ff4b47490: backend and frontend jobs succeeded, including all existing and new tests and both browser smoke workflows. Backend: 197 tests; frontend: 32 unit tests. New local release gate tests: 4 passed. The browser workflow uses synthetic contracts and mocked API responses; it does not establish that production model inference succeeds.

A separate real public-query retrieval diagnostic fetched official Civil Code pages from the Supreme People's Court and SAMR. This verifies that a query can retrieve official HTML, not the completeness, current legal status, applicability, or correctness of review conclusions.

The last checked pre-refactor Fly deployment stopped for missing FLY_API_TOKEN. The preview API proxy was checked: it correctly forwards to Fly and receives JSON 404 for `/legal/version` while the old backend is still running. No secrets were extracted, printed, or bypassed.
