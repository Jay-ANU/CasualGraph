---
name: causalgraph-design
description: Use this skill to generate well-branded interfaces and assets for CausalGraph — an evidence-grounded ESG research workspace — either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## Quick map

- **`README.md`** — start here. Sources, content fundamentals, visual foundations, iconography, manifest, caveats.
- **`colors_and_type.css`** — all tokens (colors, type, spacing, radii, shadows, semantic classes). Import this first in any HTML output.
- **`fonts/`** — Manrope (display) + IBM Plex Sans/Mono loader.
- **`assets/`** — logos (lockup, mark, dark) and asset README.
- **`preview/`** — registered design-system cards (colors, type, spacing, components, brand).
- **`ui_kits/causalgraph/`** — interactive UI-kit demo of the product (Login → Home → Research Desk → Graph Engine). Reusable JSX components + `index.html` entry.
