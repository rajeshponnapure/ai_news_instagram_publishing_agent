# graitech — Design System

A dark, modern, neon-accented brand system. Built around a single, vivid neon-green accent (`#39FF14`) on a deep black canvas, with concrete-grey texture work and bold display type. The vibe is **techy, urban, premium** — half engineering blog, half streetwear drop.

> _"Build at the edge."_ — operating tagline

---

## Provided context

This system was built from a small starting kit:

- **Logo** — `uploads/GR logo without bng.png` (320×320 PNG with transparency; glitchy GR mark, laurel branches, circle outline, lime-green on transparent)
- **Brand notes** — Instagram-post template brief (1080×1350 portrait, 4:5). Black background + concrete-grey texture. Neon-green headings (`#39FF14`) over white (`#FFFFFF`) body. Fixed chrome: logo top-right, `@graitech` bottom-left, page number bottom-center. Clear safe-areas so chrome never collides with content.
- **Fonts** — installed locally in `fonts/`:
  - `FontdinerSwanky-Regular.ttf`
  - `AntonSC-Regular.ttf`
  - `SpaceMono-Regular.ttf`, `SpaceMono-Italic.ttf`, `SpaceMono-Bold.ttf`, `SpaceMono-BoldItalic.ttf`

> ⚠️ **One font still substituted.** Three of the four brand families ship locally via `@font-face` in `colors_and_type.css` and need no network. **Bungee** is still pulled from Google Fonts (`https://fonts.googleapis.com/css2?family=Bungee`) — drop `Bungee-Regular.ttf` into `fonts/` and replace the trailing `@import` in `colors_and_type.css` with a fourth `@font-face` block to ship fully self-contained.

There is no codebase, no Figma file, no existing marketing site, and no product UI for this brand at the time of writing. This system is therefore **opinionated greenfield**: it interprets the brief into a consistent visual language. Treat it as a starting point — every token is easy to swap.

---

## Index

| File | What's in it |
| --- | --- |
| `README.md` | This file. Foundations, voice, iconography, layout rules. |
| `SKILL.md` | Agent-Skills frontmatter for Claude Code / agent reuse. |
| `colors_and_type.css` | All design tokens (CSS custom properties) + semantic base styles + `.gt-bg-concrete` utility. |
| `assets/graitech-logo.png` | Primary logo, neon-on-transparent. |
| `assets/concrete-texture.svg` | Full-bleed concrete/cement texture for backgrounds (1080×1350). |
| `assets/concrete-tile.svg` | 200×200 tileable concrete swatch (for small surfaces). |
| `templates/instagram-post.html` | All five sample IG slides on one canvas. |
| `templates/instagram-post.css` | Slide layout + element styles shared by all `slide-0*.html` files. |
| `templates/slide-01-title.html` … `slide-05-cta.html` | One IG slide per file (1080×1350). |
| `preview/*.html` | Small token/component cards that populate the Design System tab. |

No `ui_kits/` directory exists — this brand has **no product UI** to recreate. If a web app, dashboard, or marketing site materialises later, scaffold each one as its own folder under `ui_kits/<product>/`.

---

## 1. Visual Foundations

### Color

- **One** brand accent: `#39FF14` neon green. Used at full intensity for headlines, dividers, status dots, focus rings, and the brand glow. `--gt-neon-soft` (`#5AFF3A`) is the hover state; `--gt-neon-deep` (`#1FCC00`) is the pressed state. Reserve a `rgba(57,255,20,0.45)` halo for glows.
- **Black-first surfaces.** The canvas is true `#000000`. Elevated surfaces step up in ~5-point increments: Ink → Graphite → Iron → Cement → Cement 2. Anything brighter than Cement 2 is intentional and probably wrong.
- **Foreground is monochrome** — pure white for body, with chalk / ash / smoke as descending steps. No coloured body text. Ever.
- **Semantic colours exist but are quiet.** Warn (`#FFB800`), Danger (`#FF3355`), Info (`#18C0FF`) are used for states only — never for decoration.

### Type

Four families do four distinct jobs. Don't mix the jobs.

| Family | Role | Used for |
| --- | --- | --- |
| **Bungee** (`--gt-font-block`) | Chunky urban headlines | Hero numbers, IG title slides, big single-line statements. Always uppercase. |
| **Anton SC** (`--gt-font-display`) | Tall condensed all-caps | Stacked multi-line headlines, section titles. Always uppercase, slight positive tracking. |
| **Space Mono** (`--gt-font-mono`) | The whole rest of the system | Body, labels, eyebrows, code, metadata. The brand's voice in text form. |
| **Fontdiner Swanky** (`--gt-font-kitsch`) | Wildcard accent | One use per piece, maximum. Easter-egg labels, after-hours moments. Never body. |

Default body line-height is `1.55`. Headlines run tight: `0.88–0.95`. Eyebrows use heavy mono tracking (`0.32em`) and always sit in neon green.

### Backgrounds

- **Default canvas** is `--gt-bg-concrete`: solid black + two layers of micro-speckle + soft cement blotches + a subtle vignette. Always full-bleed.
- A **thin crosshatch grid** (90px on slides, scaled smaller elsewhere) sits on top, masked with a soft radial so the centre is clean and the corners pick up the grid. This is the techy fingerprint of the brand.
- **No gradients** as decoration. No bluish-purple anything. No marketing-gradient mesh blobs.
- **Imagery**, when used, should be high-contrast, slightly desaturated, with a black multiply or duotone (black + neon) to keep it on-brand. No warm/sun-drenched photography.

### Layout & spacing

- 8-point spacing scale: `4, 8, 12, 16, 24, 32, 48, 64, 96, 128` — exposed as `--gt-s-1`…`--gt-s-10`.
- IG safe-areas (the rule that protects fixed chrome): **top 220px** reserved for the logo (130px square + 56px margin + 34px gap). **Bottom 160px** reserved for `@graitech` handle and page number. Side gutters **80px**. Content lives strictly inside these bounds.
- Logo position: `top: 56px; right: 56px;` — fixed, every slide, no exceptions.
- Handle position: `bottom: 56px; left: 56px;`. Page number: bottom-center, vertically aligned with handle.

### Radii & elevation

- Radii are restrained: most surfaces are sharp (`0`) or `4px`. Pills (`999px`) are reserved for stamps/tags. No oversized rounded cards.
- Two elevation languages:
  - **Soft drop** (`--gt-shadow-soft`) for elevated surfaces on neutral backgrounds — the usual UI shadow.
  - **Neon glow** (`--gt-shadow-glow` and `--gt-shadow-glow-soft`) for anything that should feel "live" — focus rings, active states, hero logos, key headlines.
- Focus rings use `--gt-ring-focus` (a black halo then a neon ring). Always visible. Never removed.

### Borders, transparency, blur

- Borders are 1px or 1.5px, in `--gt-iron` or `--gt-cement-2`. They function as hairlines, not as decoration.
- Transparency and blur are used **sparingly** — usually on grid overlays masked with radial gradients, or for the neon glow halo (`rgba` not `opacity` on element). No frosted-glass cards.
- Corner ticks (1.5px L-brackets in the four corners of a content frame) are an optional techy accent — see `preview/components-accents.html`.

### Motion & state

- Durations: `--gt-dur-fast: 120ms`, `--gt-dur-base: 200ms`, `--gt-dur-slow: 360ms`. Default ease is `cubic-bezier(0.2, 0.7, 0.1, 1)` — a confident out-curve, no bounce.
- **Hover**: brighten (`--gt-neon-soft`), add or intensify the neon glow. Never just opacity.
- **Press**: deepen colour (`--gt-neon-deep`) and slightly tighten the glow. No `scale(0.98)` shrink unless the element is iconographic.
- **Loading**: a single neon dot that pulses (opacity 0.4 → 1 → 0.4 at `--gt-dur-slow`). Never a spinner.
- Animation is **rare**. The brand reads as solid and built; things don't slide around for fun.

### Cards

- Surfaces use `--gt-ink` or `--gt-graphite` over the concrete canvas.
- Border `1px solid var(--gt-iron)`, radius `var(--gt-r-md)` (8px), shadow `var(--gt-shadow-soft)`.
- If a card is "the hero of the screen," promote it to `--gt-shadow-glow-soft` and a neon border. Use this once per screen.

---

## 2. Content Fundamentals

### Voice

graitech writes like **a senior engineer talking to peers** — direct, slightly dry, more "shipped on Tuesday" than "industry-leading platform." Confidence without hype.

- **You / we**, not "users" or "customers." First-person plural for the company, second-person singular for the reader.
- **No exclamation points.** Periods do the work.
- **Short, declarative sentences.** Five to fifteen words is the strike zone.
- **Concrete over abstract.** "Three deploys before lunch" not "Improved deployment velocity."
- **No emoji**, full stop. They break the aesthetic.
- **No corporate hedging** — no "could," "might," "potentially." Say it or don't.

### Casing

- **Display type is uppercase.** Always. The condensed/blocky families are designed for it.
- **Eyebrows are uppercase**, monospace, wide-tracked.
- **Body type is sentence case.** Never all-caps body.
- **Stamps and labels are uppercase**, mono, wide-tracked.
- **Numbers in stamps and pagination are zero-padded** (`01 / 05`, `Dispatch / 026`).

### Examples (lifted from the IG templates)

- **Eyebrow:** `FIELD NOTES — MAY 2026`
- **Hero headline:** `BUILDING AT THE EDGE.`
- **Body:** `Five engineering principles we use every day at graitech — distilled into things you can actually steal.`
- **Quote attribution:** `— K. MENSAH · PRINCIPAL ENGINEER`
- **CTA:** `SWIPE →`, `SAVE THIS. STEAL THIS. SHARE IT.`
- **Stamp:** `DISPATCH / 026`, `END / DISPATCH 026`

### Punctuation rules

- Em dash (`—`) is the brand's favourite punctuation. Use it for asides and shifts.
- Use `·` (middle dot) as a separator in metadata rows, not `|` or `/` unless paginating.
- Slashes (`/`) are for ratios and paths: `01 / 05`, `graitech.io`, `DISPATCH / 026`.

---

## 3. Iconography

graitech has **no proprietary icon set**. Iconography is intentionally minimal — the brand leans on type and bold accent geometry instead of a vocabulary of pictograms.

### Approach

- **Icons are a last resort**, not a default. If a label can carry the meaning, use a label.
- When icons are needed, draw from **[Lucide](https://lucide.dev)** — clean 1.5–2px stroke weight, square caps, neutral geometry. It matches the brand's "engineered, not decorated" feel.
  - CDN: `https://unpkg.com/lucide@latest`
  - Use stroke `currentColor`. Tint to `--gt-neon` for active/accent, `--gt-chalk` for default, `--gt-smoke` for muted.
- **Heroicons (outline)** is an acceptable secondary if you need a glyph Lucide doesn't have.

> 🏷️ **Substitution flag.** Lucide is a substitution, not part of the original brand brief. Swap it for a proprietary set if/when one is commissioned.

### Iconographic accents (built into this system)

These are not icons — they're **geometric primitives** the brand uses repeatedly. Keep them consistent across surfaces:

- **Neon dot** — `8px × 8px` round, neon green, with a `0 0 12px var(--gt-neon)` glow. Used before the `@graitech` handle, inside stamps, and as a status indicator.
- **Accent rule** — `96px × 3px` neon bar with a soft glow. Always sits between an eyebrow and a headline.
- **Corner ticks** — 1.5px L-brackets at the four corners of a content frame, in `--gt-cement-2`. Optional "techy" detail.
- **Swipe arrow** — a thin neon line with a chevron, used for "SWIPE →" CTAs.
- **Pagination bars** — a 1px hairline either side of the page-number string in the IG chrome.

### Logo

- The GR mark lives in `assets/graitech-logo.png` (320×320 PNG, transparent background, neon-on-black mark with laurel branches and an outer circle).
- On dark backgrounds: drop-shadow with `rgba(57,255,20,0.25–0.5)` for the glow halo.
- On light backgrounds: `filter: invert(1)` produces a high-contrast inverse. (A dedicated SVG version would be better and is **TODO**.)
- **Minimum size**: 48px square in product UI, 130px square on IG portrait slides.
- **Clear space**: at least half the logo's height of empty space on every side. Nothing — text, image, or other glyph — may enter that zone.

### Emoji & unicode glyphs

- **No emoji** anywhere in brand surfaces.
- Acceptable unicode glyphs: `—` (em dash), `·` (middle dot), `→` (rightwards arrow, only where the swipe arrow isn't available), `×` (multiplication sign, for stats like `3.4×`), `°` (degree, only in data).

---

## 4. Layout rules (Instagram-specific)

The IG portrait template (1080×1350, 4:5) is the canonical surface for this brand right now. Rules:

1. **Logo is fixed.** Top-right, `56px` from each edge, `130px × 130px`. Never moves. Never resized.
2. **Handle is fixed.** Bottom-left, `56px` from each edge. `@graitech` in 22px bold mono with the neon dot preceding it.
3. **Page indicator is fixed.** Bottom-center, vertically aligned to the handle. Format: `— 01 / 05 —` with 28px hairline bars either side.
4. **Content safe-area:** `top: 220px; left: 80px; right: 80px; bottom: 160px;`. No content escapes this rectangle. The fixed chrome lives _outside_ it and is guaranteed to never collide.
5. **Every slide carries the eyebrow → rule → headline → body rhythm**, even if abbreviated. The rule (neon bar) is the brand's connective tissue across slides.
6. **One headline per slide.** Don't stack a Bungee block and an Anton tall headline in the same composition.
7. **Concrete texture + crosshatch grid run on every slide**, full-bleed, behind everything. They're brand glue.

---

## Caveats and known gaps

- **Fonts:** loaded from Google Fonts (substitution flagged above).
- **No SVG logo:** we only have the PNG. A vector version would let us recolour, scale crisply, and provide variant marks.
- **No icons in `assets/`:** brand uses Lucide via CDN as a substitution.
- **No UI kit:** brand has no product surfaces yet.
- **One canonical surface:** IG portrait only. Stories (9:16), reels covers, web hero modules, slide decks etc. are all derivable from the same tokens but are not yet built.

