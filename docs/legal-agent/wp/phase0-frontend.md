# Phase 0 · 前端任务书：清场 + 迁移 Vite + 统一 API client（WP0.3）

> 执行者：一个子代理。验收人：主会话。
> 背景与理由见 `docs/legal-agent/00-alignment.md`（第 1.10、7 节）。本任务书是唯一的执行依据。

## 0. Ground rules

- Work in `/home/user/CasualGraph/frontend` (repo root `/home/user/CasualGraph`, current branch). **Do not commit, do not push, do not create branches.** The lead commits after acceptance.
- Node 22 and npm are installed; `frontend/node_modules` is already populated from the current lockfile. Chromium for Playwright is preinstalled under `/opt/pw-browsers` (`PLAYWRIGHT_BROWSERS_PATH` is set). **Never run `playwright install`.** The Python venv is `/home/user/CasualGraph/.venv`; install the Playwright Python package into it with `.venv/bin/pip install playwright==1.58.0` when you get to the smoke test. If the bundled Chromium version does not match, launch with `executable_path` pointing at the chromium binary under `/opt/pw-browsers`.
- **File ownership.** You own `frontend/**`, root `vercel.json`, the root folder `CausalGraph Design System/`, and `scripts/research_ui_smoke.py`. **Do not touch** anything else (a backend agent is editing Python, README, `.env.example`, CI workflows, `.gitignore`, `docs/`).
- No new product features. Deletion, tooling migration, de-duplication, and copy neutralisation only. The big split of `Agent.tsx` into a routed workspace is **not** part of Phase 0 (Phase 4 replaces that screen with a clause-review workbench).
- When something in this brief is impossible or wrong, do the closest safe thing and report it under "Deviations".

## 1. Backend contract changes you must absorb (the backend agent is making them now)

Removed endpoints (stop calling them, delete the code that used them): `/admin/recruitment/*`, `/offers/*`, `/desktop/*`, `/kg-view`, `/kg-view/ticket`, `/public/knowledge-graph`, `/kg-api/*`, `/api/*`, `/graph/causal/*`, `/documents/rebuild-graph`, `/extract`, `/pipeline/pdf`. The `/graph/neo4j/*` admin routes still exist but the UI must no longer use them.

Changed payloads:
- `GET /documents` and `GET /documents/{id}` no longer return `graph`, `relationships`, `relationship_count`, or any `*_path` field. Keep using `id`, `title`, `domain`, `source`, `document_group`, `owner_user_id`, `visibility_scope`, `source_type`, `chunk_count`, `ingested_at`, `neo4j_sync`.
- `GET /models/status` no longer has `extraction` or `vision`. Make the types optional and the component tolerant.

Everything else (`/auth/*`, `/rag/ask/stream` SSE contract, `/chat/sessions/*`, `/documents/upload-async`, `/documents/jobs/{id}`, `/feedback`, `/admin/overview|uploads|invite-codes|rag-unlimited-users`) is unchanged.

## 2. Delete

- Pages and their tests/CSS: `pages/Recruitment.tsx`, `pages/OfferView.tsx`, `pages/offer/**`, `pages/recruitment/**`, `pages/EsgDemo.tsx`, `pages/CausalInference.tsx`, `pages/DesktopDownload.tsx`, `pages/About.tsx`.
- Components: `components/KnowledgeGraphView.tsx`, `components/GraphVisualizer.tsx`, `components/PredictionAnswer.tsx`, `components/AdminTabs.tsx` (fold whatever Admin still needs into `Admin.tsx`), `config/downloads.ts`.
- Public assets: `public/assets/desktop-pet-hero-mockup.png|webp`. Keep `public/brand/*`, `public/assets/login-bg.png`, `manifest.json`.
- Types in `types/api.ts` and `types/graph.ts` that only served the deleted screens (`PredictionAnswer`, `CausalChainStep`, graph payload types used solely by KnowledgeGraphView). Keep `RagSource`, `RagResponse`, `AgentTraceStep`, session and document types.
- Routes in `App.tsx`: keep exactly `/`, `/home`, `/login`, `/agent`, `/admin`, `*`. Remove the Navbar hide-rule for `/offer/*`.
- Navbar / sidebar / admin links to Recruitment, Graph, Desktop, Company, About.
- The root folder `CausalGraph Design System/` (stale, contradicts the live tokens).
- Inside `pages/Agent.tsx`: the Neo4j status/subgraph loading, graph inspector, graph auto-repair (`/documents/rebuild-graph`), document-detail graph/relationship sections and exports, `KnowledgeGraphView` usage, the ESG graph-domain maps (`GRAPH_DOMAIN_LABELS`, `DOMAIN_DOT_CLASS`), the "Skills" tab and skill upload (cosmetic, no backend), the four built-in skill cards, and the dead state (`quickUploadInputRef`, `uploadStatusResult`, `SAMPLE_DOCUMENTS`, `sample_esg_report` branch). Keep: chat with streaming, sessions list, Cmd+K session search, Library list + document detail (title, source, chunk count, scope toggle, delete), Upload, feedback, model status, account/plan label, the trace/process drawer and sources drawer. Also delete `pages/agent/skillFiles.ts` and its test.
- Unused dependencies: `mammoth`, `recharts`, `web-vitals`, `pdfjs-dist` (re-added in Phase 4), `@types/jest`, `react-scripts`. Move `@types/*` to devDependencies.

## 3. Migrate Create React App → Vite

- Add `vite`, `@vitejs/plugin-react`, `vitest`, `jsdom` (only if a test needs DOM; the current tests are pure functions), `typescript@^5`, `@types/node@^22`. Keep React 18, react-router-dom 6, Tailwind 3 (via the existing PostCSS config), react-markdown stack, lucide-react, @fontsource packages.
- `frontend/index.html` at the package root (move from `public/index.html`, drop `%PUBLIC_URL%`, add `<script type="module" src="/src/index.tsx">`).
- `vite.config.ts`: react plugin, `server.port` 3000, `build.outDir` `dist`, `test: { globals: true, environment: 'node' }` for vitest (switch to `jsdom` only where needed).
- `tsconfig.json`: `"target": "ES2020"`, `"module": "ESNext"`, `"moduleResolution": "bundler"`, `"jsx": "react-jsx"`, `"strict": true`, `"types": ["vite/client", "vitest/globals"]`, `"skipLibCheck": true`. Add `src/vite-env.d.ts`.
- Env vars: Vite exposes only `VITE_*`. Create `src/api/config.ts` exporting `apiBase()` that reads `import.meta.env.VITE_API_BASE` and falls back to the current localhost logic. Every one of the eight ad-hoc base-URL computations (AuthContext, Login, Agent, Admin, …) must use it. Document in the report that the Vercel project env var must be renamed `REACT_APP_ESG_API_BASE` → `VITE_API_BASE` (the lead will tell the user).
- Replace `process.env.NODE_ENV` / `process.env.REACT_APP_*` usages with `import.meta.env`.
- `package.json` scripts, exactly these names: `dev` (`vite`), `build` (`tsc --noEmit && vite build`), `preview`, `typecheck` (`tsc --noEmit`), `lint` (`eslint .`), `test` (`vitest`). CI will call `npm run typecheck`, `npm run lint`, `npm test -- --run`, `npm run build`.
- ESLint flat config `eslint.config.js` with `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`; `react-hooks/exhaustive-deps` as `warn`, everything else default. `npm run lint` must exit 0 (fix or narrowly disable with a comment, never blanket-disable a rule file-wide without saying so in the report).
- Convert the remaining Jest tests (`agentTraceUi`, `ragUi`, `accountPlan`, `modelStatus`) to vitest (mostly no change; replace any `jest.fn`/`jest.mock` with `vi.*`).
- `vercel.json` (root and `frontend/`): output directory `frontend/dist`; keep the SPA rewrite. Root `vercel.json` build command stays `npm --prefix frontend run build`.
- `scripts/research_ui_smoke.py`: serve `frontend/dist` instead of `frontend/build`; keep the `.research-model` and `.research-starters` hooks in the UI so the script still passes; update any selector that pointed at deleted UI. Run it as part of acceptance.

## 4. Shared typed API client

- `src/api/client.ts`: `apiFetch<T>(path, init?)` that prefixes `apiBase()`, injects the bearer token from the same storage key AuthContext uses, parses JSON, and throws a typed `ApiError { status, code?, message }` built from the existing `readApiErrorMessage` logic. `src/api/sse.ts` keeps `readSseEvents`. Replace direct `fetch(...)` calls in the kept pages with the client (streaming keeps a thin wrapper around `fetch` for the SSE body).
- Keep response types in `src/types/api.ts`; remove `any` where it is cheap, do not chase perfection.

## 5. Copy neutralisation (minimal)

Replace ESG-specific product copy in the kept screens with neutral contract-review wording. Keep it short and bilingual-friendly (Chinese primary where the existing copy was English marketing, e.g. 首页标题 "合同逐条审阅 agent"). Concretely: Home hero and feature blurbs, Login side panel, `WorkbenchWelcome` starter prompts passed from Agent (e.g. "总结这份合同的关键条款", "违约责任条款有哪些风险？", "对比两份合同的付款条件"), the loading phrases and ESG "low-value words" in `pages/agent/ragUi.ts`, upload category labels (`Agent.tsx` ~4268-4305: replace ESG categories with `合同 / 附件 / 其他`), `document.title` strings, and `modelDisplayName`'s DeepSeek-only mapping (make it generic). Do not redesign layouts.

## 6. Acceptance (run all; paste outputs)

```bash
cd /home/user/CasualGraph/frontend
npm ci --no-audit --no-fund
npm run typecheck
npm run lint
npm test -- --run
npm run build
grep -rn "REACT_APP_\|process.env" src && echo "(must be empty)"
grep -rnE "rebuild-graph|kg-view|/api/(filters|graph|cluster|stats|greenwashing)|/graph/causal|/desktop/|recruitment|/offers|/extract|/pipeline/pdf|/graph/neo4j" src && echo "(must be empty)"
grep -n 'path="' src/App.tsx    # exactly: /, /home, /login, /agent, /admin, *
cd /home/user/CasualGraph && .venv/bin/pip install -q playwright==1.58.0 && .venv/bin/python scripts/research_ui_smoke.py
ls "CausalGraph Design System" 2>/dev/null && echo "STILL EXISTS" || echo "design system folder removed"
```

## 7. Final report format

1. Summary (deleted / migrated / de-duplicated / copy changes).
2. Acceptance outputs (verbatim tails).
3. Line counts of `src/` before → after; `Agent.tsx` before → after.
4. Deviations and why.
5. Operational notes for the lead (Vercel env var rename, anything else the deploy needs).
6. Things you noticed for Phase 4 (do not fix).
