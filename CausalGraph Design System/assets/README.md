# Assets

CausalGraph ships **no logo SVG** in its codebase. The live app renders its
logomark by composing the `Orbit` icon from lucide-react inside a
40×40 slate-950 rounded-xl tile, paired with the wordmark "CausalGraph"
and the eyebrow "ESG INTELLIGENCE" — see `components/Navbar.tsx`.

We've reproduced that exact composition as `logo.svg` and `logo-mark.svg`
so designs in this kit can reference a single asset. If a real wordmark
is commissioned later, replace those two files in place — every consumer
will pick up the change.

| File | What it is |
|---|---|
| `logo.svg` | Full logomark — square + wordmark + eyebrow |
| `logo-mark.svg` | The square-only mark (40×40), suitable for favicons / app tiles |
| `logo-mark-dark.svg` | Square-only mark inverted for dark backgrounds |

The product also has no photography or hand-drawn illustrations on disk —
the marketing UI is illustration-free by design. If imagery becomes
needed for blog/case-study work, it should be cool-toned, desaturated,
document-like, and added under `assets/imagery/` with a sub-README.
