---
name: graitech-design
description: Use this skill to generate well-branded interfaces and assets for graitech, either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and Instagram-post templates for prototyping.
user-invocable: true
---

Read the `README.md` file within this skill, and explore the other available files.

The brand is dark, modern, and neon-accented — black canvas, concrete texture, a single neon-green (`#39FF14`) accent, and bold display type (Bungee + Anton SC) paired with Space Mono for everything else.

Key files to load:
- `README.md` — foundations, voice, iconography, layout rules.
- `colors_and_type.css` — all design tokens (CSS custom properties) and semantic base styles. Always include this file via `<link rel="stylesheet">` at the top of any HTML artifact you produce.
- `assets/graitech-logo.png` — primary logo (PNG, transparent).
- `assets/concrete-texture.svg` — full-bleed background texture (1080×1350).
- `assets/concrete-tile.svg` — small tileable swatch.
- `templates/instagram-post.css` + `templates/slide-0*.html` — canonical Instagram-post layouts (1080×1350 portrait). Use these as the starting point for any social asset.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc.), copy assets out of this skill into your working directory and create static HTML files for the user to view. If working on production code, copy the assets and lift the rules in `README.md` to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask a few clarifying questions (surface, audience, dimensions, length), then act as an expert designer who outputs HTML artifacts or production code, depending on the need.

**Non-negotiables when designing for graitech:**
- Black background. Concrete texture. Crosshatch grid overlay with a soft radial mask.
- Headlines in neon green (`#39FF14`) with a soft glow. Body in pure white. No coloured body text.
- All caps for display type and labels. Sentence case for body.
- No emoji. No gradients-as-decoration. No bluish-purple anything.
- For IG portrait surfaces: logo top-right (130×130, 56px from edges), `@graitech` bottom-left, page number bottom-center. Content safe-area: `top: 220 / sides: 80 / bottom: 160`. Chrome never collides with content.
