# CausalGraph Design System

> Evidence infrastructure for ESG research. This design system codifies the
> visual language, content rules, and reusable UI of the CausalGraph
> product — a workspace where analysts turn long-form ESG disclosures into
> retrieval-grounded answers and inspectable knowledge graphs.

---

## Sources

This system was reverse-engineered from the CausalGraph codebase:

| Source | Path | Notes |
|---|---|---|
| Frontend | `comp8715-casualgraphai/frontend/src/` | React + TypeScript app, Tailwind-based, lucide-react icons |
| App stylesheet | `comp8715-casualgraphai/frontend/src/index.css` | Defines `--app-*` tokens, `app-panel`, `tech-button`, `app-grid` |
| Tailwind config | `comp8715-casualgraphai/frontend/tailwind.config.js` | (Note: declares unused `primary`/`secondary`/`accent` palettes — the live app uses slate, not those) |
| Marketing pages | `pages/Home.tsx`, `pages/About.tsx`, `pages/CausalInference.tsx` | Public surface |
| Product app | `pages/Agent.tsx` (2,881 lines) | The "Research Desk" — chat + uploads + graph viewer |
| Auth | `pages/Login.tsx` | Sign-in / register surface |
| Navigation | `components/Navbar.tsx` | Logo, top nav |

> The codebase has no logo asset on disk — the `Orbit` lucide icon on a
> dark slate-950 square stands in as the logotype. Documented in
> `assets/README.md`.

---

## Product context

**CausalGraph** is an ESG-focused research platform. The product positions
itself as **"evidence infrastructure for ESG research"** and the public
hero copy reads: *"Read disclosures as connected evidence, not isolated PDFs."*

The platform has two main surfaces:

1. **Marketing site** (`/`, `/causal-inference`, `/about`) — explains the
   product, positions it for ESG analysts, drives sign-up.
2. **Research Desk** (`/agent`) — the in-product workspace. Analysts upload
   sustainability reports, ask questions, get retrieval-grounded answers
   with cited passages, and explore extracted entities/relationships in a
   knowledge graph. Includes Chat, Upload, Results, and Summary tabs.

Two answer modes: **Ask** (RAG-grounded answers) and **Predict** (causal-chain
reasoning over the graph). Optional Neo4j sync exposes a cross-document graph.

Audience: ESG analysts, sustainability researchers, GRC reviewers, portfolio
researchers screening multiple disclosures.

---

## Content fundamentals

CausalGraph copy reads like an analyst tool, not a consumer SaaS. It is
declarative, evidence-anchored, and noun-heavy. There is **no playfulness**,
no exclamation, and no first-person plural except in the About page.

### Voice

- **Authoritative and neutral.** "Locate relevant passages first, then produce
  concise answers with evidence retained in context." Never hyped, never cute.
- **Process-forward.** Verbs describe analyst actions: *upload, query, review,
  explore, extract, surface, anchor, retain.* Avoid *unleash, supercharge,
  power, transform, magic.*
- **Sources before claims.** When in doubt, lead with where the evidence comes
  from: "Every answer can be reviewed against the underlying report snippets."
- **No ESG buzzword bingo.** The product doesn't promise to "score" or "rate"
  ESG performance. It surfaces what was reported. Stay close to the document.

### Tone & casing

- **Sentence case** for almost everything: nav items, button labels, section
  titles, even hero headlines. *"Open research desk"*, *"Built for disclosure
  review"*, *"Talk to us"*. Title Case is reserved for proper nouns and
  product names (CausalGraph, Research Desk, Graph Engine).
- **Eyebrows are uppercase + tracked**: `ESG INTELLIGENCE`,
  `EVIDENCE INFRASTRUCTURE FOR ESG RESEARCH`. Use sparingly — once per
  section at most. Spec: 11px, weight 600, letter-spacing 0.14em
  (or 0.22em for the logotype eyebrow).
- **Headlines have personality through punctuation, not adjectives**:
  *"Read disclosures as connected evidence, not isolated PDFs."* —
  comma-clause headlines that contrast and reframe.
- **No emoji. Anywhere.** Not in marketing, not in the app, not in
  empty-states. Iconography is lucide-react line icons only.
- **You + the product, not we.** In product UI: *"Ask anything about the
  indexed reports"*, *"You can upload a new one anytime"*. The marketing
  site uses third-person product framing ("CausalGraph gives analysts...")
  rather than "we built this for you."

### Word choices (use / avoid)

| Use | Avoid |
|---|---|
| Disclosures, reports, passages, evidence, citations | "Knowledge", "intelligence" alone, "data" |
| Extract, retrieve, anchor, surface, ground | Generate, summon, AI-power |
| Analyst, reviewer, researcher | User (only in technical/auth context) |
| Index, ingest, sync | Add, save, plug-in |
| Causal, retrieval-first, source-grounded | Smart, intelligent, AI-driven |
| Workspace, research desk, evidence review | Dashboard (rarely used), portal |

### Status & toast messages

Short, declarative, sometimes prefixed with a bracketed token in the
product (kept from terminal-style precedent in the codebase):

- `[SUCCESS] File "{name}" is ready. Click "Index this report" to upload and process it.`
- `[ERROR] File too large: 12.4MB. Maximum size is 50MB.`
- `Document deleted successfully. You can upload a new one anytime!` (rare exclamation — only on confirmations)
- `Ask anything about the indexed reports — answers come back with the supporting evidence attached.`

### Examples to copy from

**Hero** — `Home.tsx`
> Read disclosures as connected evidence, not isolated PDFs.
>
> CausalGraph gives analysts a controlled workspace for report search,
> scenario reasoning, and graph-based review of climate, governance, and
> operating-risk disclosures.

**Empty state** — `Agent.tsx`
> Good morning, {name}
> Ask anything about the indexed reports — answers come back with the
> supporting evidence attached.

**Capability card** — `Home.tsx`
> Report-grounded answers
> Locate relevant passages first, then produce concise answers with
> evidence retained in context.

---

## Visual foundations

### Color

The system is **almost entirely monochrome slate**. The codebase declares a
sky-blue / fuchsia / emerald palette in `tailwind.config.js` but **none of
those classes appear in the live UI** — every page uses `slate-950`, `slate-200`,
`slate-500`, white/72, white/86. Treat slate as the brand and resist any
temptation to introduce blue or purple.

- **Primary** (`#020617`, slate-950) — buttons, the navbar logomark square,
  active nav items, user message bubbles, headings on light backgrounds.
- **Surface** — translucent white over a slate-tinted backdrop. Two stops:
  86% opacity for default panels, 96% for elevated/strong panels.
- **Background** — `#f7f8fa`. Marketing hero sections layer two soft radial
  gradients (top-left slate at 10%, top-right slate at 8%) over the base.
- **Borders** — `slate-200` (`#e2e8f0`) is the workhorse; `slate-100`
  (`#f1f5f9`) is the soft option for secondary dividers.
- **Accents only on domain pills**: Environmental → emerald, Social → blue,
  Governance → orange, AI → violet. These are the *only* hue accents allowed,
  and they appear on small graph-domain chips. Do not use them as button
  fills or headings.
- **Confidence ramp** for graph edges and extracted relationships: slate-400
  (low) → slate-600 (mid) → slate-900 (high). Edge stroke darkens with
  confidence; never use red/green for confidence.

### Type

Two display families and one mono:

- **Manrope** — all headings, the logomark wordmark "CausalGraph", numeric
  metric displays. Tracking always `-0.03em` (slightly tighter on h3/h4).
  Weight 600 is the workhorse; 700 only on hero displays.
- **IBM Plex Sans** — body, UI, buttons, chips, eyebrows. Weight 400 for body,
  500 for nav and chips, 600 for buttons and eyebrows.
- **IBM Plex Mono** — evidence snippet quotes, code, document IDs, graph
  edge relationship types (`HAS_METRIC`, `IMPACTS`).

Scale (1.5× growth between display tiers, denser between body tiers):
60 / 40 / 32 / 22 / 18 / 15 / 13 / 11. Body line-height is 1.55, headings
clamp between 1.05–1.35.

### Spacing

4px base. Standard panel padding is 24px (`--cg-space-6`). Content max
width is **1600px** — wide on purpose because the product is laid out for
desktop analyst monitors. Navbar is 72px tall and sticky.

### Backgrounds & texture

- **Hero sections** layer a subtle **24px grid overlay** (`linear-gradient`
  cells at `rgba(15, 23, 42, 0.05)`) on top of the radial-gradient body.
  Use grids only on the marketing hero and the graph viewer canvas — they
  read as "structured data underlay" and lose their meaning if used everywhere.
- **No hand-drawn illustrations.** No noise/grain. No photography in the
  product UI; the marketing pages are illustration-free as well.
- **Imagery** (when added later, e.g. blog/case-study) should be cool-toned,
  desaturated, document-like — think a flat scan of a sustainability report,
  not a stock-photo team meeting.

### Animation

Reserved and short. Powered by `framer-motion`.

- **Entrance** — `opacity 0 → 1, y: 16 → 0` over 0.45s, default ease.
  Used on hero headlines, the workflow card sidebar, and the agent's
  empty state.
- **Card stagger** — entrance for capability/principle cards uses
  `y: 12 → 0`, 0.35s, `whileInView` so they fade in as the user scrolls.
- **Streaming response** — `Loader2` icon spinning at 1s linear; no
  shimmer skeletons.
- **No bounces, no springs, no parallax, no scroll-triggered scaling.**
  The brand is "evidence first" — anything that draws attention away from
  text undermines the positioning.

### Hover & press

- **Primary buttons** — background darkens from slate-950 → slate-800.
- **Secondary buttons** — background lifts from `rgba(255,255,255,0.68)` →
  `rgba(255,255,255,0.92)`. No border change.
- **Nav links** — inactive items hover to `bg-white/80 + text-slate-950`.
  Active items use a solid slate-950 pill with white text and a soft shadow.
- **Cards** — no scale, no lift on hover by default. Workflow-picker cards
  in CausalInference get a `border-slate-300` highlight on hover and
  `border-slate-950 + bg-white + shadow-sm` when selected.
- **Press** — buttons translate `0.5px` down on `:active`. No scale-down.

### Borders, radii, shadows

- **Borders are 1px slate-200**, full-stop. Never doubled, never accent-colored.
- **Radii** — 14px (panels, cards, message bubbles), 12px (buttons, input fields,
  chips on hero), 8px (small chips, nav items), 6px (tags, code), pill (only
  for chips and toggle indicators). User chat bubbles round all corners
  *except* `rounded-br-sm` on the bottom-right corner — a subtle "from-me"
  tail.
- **Shadow system**:
  - `xs` — `0 1px 2px rgba(15,23,42,0.04)` for hairline elevation
  - `sm` — `0 2px 6px rgba(15,23,42,0.06)` for tags, secondary panels
  - `md` — `0 8px 24px rgba(15,23,42,0.06)` for hover states
  - `lg` — `0 18px 50px rgba(15,23,42,0.08)` for default panels (the codebase's `--app-shadow`)
  - `xl` — `0 32px 80px rgba(15,23,42,0.10)` for sticky / floating elements
- **Inner shadows are unused.** Don't introduce them.

### Transparency & blur

The codebase makes heavy use of `backdrop-filter: blur(18px)` on translucent
white panels (`bg-white/72`, `bg-white/86`). This is the *single most
distinctive* visual treatment of the brand. Use it on:

- The sticky navbar (`bg-white/78` + 24px blur)
- All `cg-panel` cards
- Sidebars over the app background

Never use blur on solid-white surfaces — it has no effect and adds GPU cost.

### Layout rules

- **Sticky 72px navbar**, content scrolls under it.
- **Marketing pages** alternate three section types: hero (grid + radials),
  flat content (`max-w-[1600px]` + 4px column gap), and "tinted band"
  (`border-y border-slate-200 bg-white/72`).
- **Product app** is a fixed-height workspace (`h-[calc(100vh-72px)]`) with
  a 256–288px left sidebar and a flexible main column. Mobile collapses the
  sidebar to a horizontal tab bar.
- **Card grids** use 4 columns on desktop (`md:grid-cols-2 lg:grid-cols-4`),
  with a 16px gap.

### Confidence, evidence & graph specifics

- Graph edges render as light-slate strokes that thicken + darken with
  confidence (low → 1px, slate-400 / mid → 1.5px, slate-600 / high → 2px,
  slate-900). The viewer is implemented in `components/GraphVisualizer.tsx`.
- Domain badges (the only colorful elements) are 12px, weight 500,
  6px-radius, with a colored text + 50-tone background fill.

### Don't

- Don't introduce sky-blue or purple gradients. The codebase has them
  defined in Tailwind but never uses them; importing them now would change
  the brand.
- Don't add emoji.
- Don't use orange/red/green except on the small status banner and domain
  pill components in this kit.
- Don't draw new SVG illustrations. Use lucide-react icons.
- Don't introduce drop-shadows on text.
- Don't round things to 24px+; the brand stops at 20px.

---

## Iconography

CausalGraph uses **`lucide-react` exclusively** — line icons, 1.5px stroke,
24×24 default with the on-screen size driven by `h-* w-*` classes. The
codebase imports from `'lucide-react'` (v0.263) in every page that needs
glyphs. No emoji, no unicode glyphs, no custom SVG illustrations.

### Standard sizes

- **20px** (`h-5 w-5`) — primary navigation icon-tiles, button leading icons in dense areas
- **16px** (`h-4 w-4`) — most buttons, chips, inline accents (the most common size)
- **14px** (`h-3.5 w-3.5`) — toast/loader spinners
- **12px** (`h-3 w-3`) — meta hints (e.g. "3 report passages retrieved")

### Icon conventions

- **Containers**: when an icon is the visual anchor of a card, wrap it in
  a 40×40 (`h-10 w-10`) square with `bg-slate-100 text-slate-700` and a
  12px radius. The product navbar uses an inverted variant — slate-950
  square with white icon — exclusively for the logomark.
- **Logomark**: `Orbit` from lucide-react in a 10×10 (40px) slate-950
  rounded-xl tile, paired with the wordmark "CausalGraph" in Manrope and
  an uppercase eyebrow "ESG INTELLIGENCE" above it.
- **Domain icons** in graph context: `Network` (general), `BarChart3`
  (metrics), `ShieldCheck` (governance/risk), `FileSearch` /
  `FileText` (documents), `Database` (indexed corpus).

### Substitutions / placeholders

- The codebase has **no logo SVG file** — `Orbit` from lucide is the de
  facto mark. We've kept that as the official logomark; if a custom
  wordmark is produced later, drop it into `assets/logo.svg` and
  `assets/logo-mark.svg`. **(FLAGGED — requires a real wordmark when
  available.)**
- Webfonts (IBM Plex Sans, IBM Plex Mono, Manrope) are loaded from
  Google Fonts via `fonts/fonts.css`. **(FLAGGED — replace with hosted
  TTF/WOFF2 if offline use is required.)**

### How to use icons in your designs

```html
<!-- Reference Lucide via CDN — same icon set the codebase uses -->
<script src="https://unpkg.com/lucide@0.263.0/dist/umd/lucide.min.js"></script>
<i data-lucide="orbit" class="h-5 w-5"></i>
<script>lucide.createIcons();</script>
```

In a React/JSX prototype:

```jsx
import { Orbit, Network, FileSearch } from 'lucide-react';
<Orbit className="h-5 w-5" />
```

---

## Index

This system lives at the project root. The reader's manifest:

| File / folder | What it is |
|---|---|
| `colors_and_type.css` | All design tokens — colors, type, spacing, radii, shadows, semantic classes. Import this first. |
| `fonts/fonts.css` | Webfont loader (IBM Plex Sans / Mono + Manrope from Google Fonts). |
| `assets/` | Logos, social-icons, README documenting the (sparse) imagery situation. |
| `preview/` | Card files that populate the **Design System** tab — colors, type specimens, components, etc. |
| `ui_kits/causalgraph/` | High-fidelity UI kit for the full product — Login, Home (marketing), Research Desk, Graph Engine, Company. Click-through demo at `index.html`. |
| `SKILL.md` | Agent-skill manifest. Drop this folder into Claude Code as a skill. |

---

## Caveats

- The repo ships **no real logo file**; we use lucide's `Orbit` glyph as
  the brand mark, matching what the live app does. A real wordmark would
  improve every surface and should be commissioned.
- Webfonts are CDN-loaded; download TTFs into `fonts/` if you need offline
  rendering (only the Google Fonts CSS is in-tree right now).
- Tailwind config defines `primary/secondary/accent` palettes that are not
  used in the live UI. We've intentionally **excluded** them from this
  system — the live brand is monochrome slate. If you discover code paths
  that *do* use them, raise a flag.
- The product is bilingual-capable in places (the chat understands Chinese
  query patterns), but every visible surface in the codebase ships in
  English. No CJK type rules included here.
