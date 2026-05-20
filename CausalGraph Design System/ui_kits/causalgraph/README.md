# CausalGraph UI Kit

A faithful recreation of the CausalGraph research-desk web application — built from the production frontend at `comp8715-casualgraphai/frontend/src/`.

## What's here

- **`index.html`** — Interactive click-through demo. Sign in (any creds), browse the Home hero, open the Research Desk to chat about an indexed report, and pop into the Graph Engine.
- **`components.jsx`** — Atomic shared primitives: `Button`, `IconButton`, `EyebrowChip`, `Pill`, `Input`, `Field`, `Tag`, `DomainTag`, `Panel`.
- **`Navbar.jsx`** — Sticky 72px nav with the orbital mark, segmented page tabs, and Sign-in/Open-desk action.
- **`Login.jsx`** — Centered sign-in card. Side panel with the four-step research workflow.
- **`Home.jsx`** — Marketing hero with eyebrow chip, two CTAs, and a dotted grid background. "Active evidence set" panel on the right.
- **`ResearchDesk.jsx`** — Three-pane workspace: report library on the left, chat thread in the middle, evidence + graph subpanel on the right. The composer supports Ask / Predict / Reason-on-graph modes.
- **`GraphEngine.jsx`** — Force-directed knowledge graph view with an entity inspector and a relationship table.

All visuals are pixel-targeted at the production app (Tailwind utility classes used in the codebase have been kept verbatim where possible). Component implementations are **simple cosmetic versions** — they don't talk to any backend.

## Tech

- React 18 (UMD) + Babel standalone
- Tailwind via Play CDN (matches the codebase's Tailwind config)
- Lucide icons via CDN
- All design tokens come from `../../colors_and_type.css`
