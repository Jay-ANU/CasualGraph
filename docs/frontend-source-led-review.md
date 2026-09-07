# Source-led frontend refinement

## Approved direction

Refine the existing product rather than replace it with decorative AI-template
motifs. Keep the CausalGraph brand, report upload, session history, graph entry,
Fast/Deep behavior and existing backend contracts.

Design references (public pages, not a claim to have tested private workspaces):
- Linear: https://linear.app/now/behind-the-latest-design-refresh
- NotebookLM: https://blog.google/innovation-and-ai/models-and-research/google-labs/notebooklm-new-features-december-2024/
- Elicit: https://elicit.com/
- AlphaSense: https://help.alpha-sense.com/hc/en-us/articles/52886436185363-Reviewing-Documents-in-AlphaSense

The implemented choices are narrower navigation, quieter sidebar, readable
answer typography, distinct source metadata, and a product demonstration that
uses the same React answer and passage components as the real conversation.
These are adaptations, not copies of another product's artwork or brand.

## Changes

- Remove the decorative animated globe, outline wordmark and generic feature
  cards from the previous preview. Keep a charcoal homepage with a direct
  question input and a working citation demonstration.
- The homepage uses explicitly fictional excerpts. They do not enter the
  user's library, contact an API, or masquerade as live model output.
- The research desk retains its existing controls and data flow. Reduce the
  empty-state headline and use text-based suggested questions; remove the
  redundant Open Research Desk CTA while already in the desk.
- Shared ResearchAnswer renders known source markers as numbered buttons.
  Unknown and ambiguous duplicate source IDs remain visible text. Markdown
  links, code and math are not rewritten by the citation plugin.
- SourcePassages shows complete retrieved excerpts rather than three-line
  truncations. Page numbers appear only when explicitly supplied by the API;
  chunk identifiers are never treated as page numbers.
- Click a citation to select and reveal its passage. Escape closes the drawer
  and returns keyboard focus to the invoking citation; the mobile drawer keeps
  keyboard navigation within its controls. Stable React renderer identity
  avoids unmounting citation buttons during a drawer state update.

## Scope

Application changes are frontend-only. No new npm dependencies, model/provider
changes, production secrets, database schema changes or index rebuilding.
The two Python scripts are browser-test tooling, not server code.
This PR is a preview, not authorization to merge or deploy production.

## Reproducible verification

```bash
cd frontend
npm ci
CI=true npm test -- --watchAll=false --runInBand
CI=true npm run build
cd ..
python -m pip install playwright==1.58.0
python -m playwright install chromium
python scripts/research_ui_smoke.py
```

`research_ui_smoke.py` runs the existing 32 empty-state and streaming checks and
then `research_visual_review.py`, which adds 22 populated-answer, exact-citation,
keyboard-focus and responsive checks. Tests use mocked API responses and no
production account or provider key. They are not live inference or ingestion
acceptance tests.

The visual review captures desktop homepage, populated answer and expanded
source states at 1440 x 1000, plus mobile views. The original answer and source
screenshots use exactly the same test report, text and viewport:

```bash
python scripts/research_visual_review.py --baseline \
  --build /path/to/previous/frontend/build --out ui-artifacts/before
python scripts/research_visual_review.py --out ui-artifacts/refined
```

Reference revision: a3b7a21e636e581d9d714b03badc790237c6e56f (previous PR #3 preview).
Verified implementation revision: d1136c12a45bc3e2b6aa4bbf13582fb67b7308f3.
The new design passed the production build, unit tests and all 54 browser checks
in https://github.com/Jay-ANU/CasualGraph/actions/runs/34119449288 .
The run's `ui-refinement-review` artifact contains before/refined screenshots and
machine-readable check results. A separate 10-check baseline capture is not
counted in the new version's 54 checks.

There are no screenshots of real private documents in these test artifacts.
