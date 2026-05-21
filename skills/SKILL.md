---
name: ui-design-skill
description: >
  MANDATORY UI design skill. Activate this skill for ANY task that involves creating, designing,
  or styling a user interface — no exceptions. This includes: web pages, landing pages, dashboards,
  React/Vue/HTML components, mobile app screens, PDF layouts, report designs, admin panels,
  forms, data visualizations, email templates, slide decks, application UIs, CLI output styling,
  and ANY other visual output a user will look at. Trigger even if the user only says "make it
  look good", "design something", "create a UI", "build a page", "style this", or mentions any
  visual deliverable. Every UI generated under this skill must be visually unique — no two designs
  should share the same template, color palette, or layout pattern. World-class output only.
---

# UI Design Skill — Master Instruction File

> **Non-negotiable directive:** Every UI you generate must look like it was designed by a senior product designer at a world-class design studio. Generic, boring, or repetitive output is a failure state.

---

## 📁 SKILL STRUCTURE

```
ui-design-skill/
├── SKILL.md                          ← You are here (read first, always)
├── design-systems.md                 ← Tokens, typography, color, spacing systems
├── ui-patterns.md                    ← Component patterns for every UI type
├── uniqueness-engine.md              ← Anti-repetition rules and variation system
└── platform-specs.md                 ← Platform-specific rules (web/mobile/PDF/app)
```

**When to load reference files:**
| Task | Load These |
|------|-----------|
| Any UI task | `design-systems.md` + `uniqueness-engine.md` (always) |
| Web / React / HTML | + `ui-patterns.md` + `platform-specs.md#web` |
| Mobile UI | + `ui-patterns.md` + `platform-specs.md#mobile` |
| PDF / Report / Print | + `platform-specs.md#print` |
| Dashboard / Data viz | + `ui-patterns.md#data` + `design-systems.md#data` |
| Email template | + `platform-specs.md#email` |

---

## ⚡ ACTIVATION PROTOCOL

When this skill activates, execute these steps **in order**:

### STEP 1 — UNDERSTAND THE BRIEF
Before designing anything, extract:
- **What is it?** (web page / dashboard / PDF / app screen / component)
- **Who uses it?** (end users / developers / executives / general public)
- **What is the purpose?** (convert / inform / manage / entertain / impress)
- **What platform?** (browser / mobile / desktop / print)
- **Any existing brand?** (colors, fonts, logos mentioned?)

If any of these are unclear, ask ONE targeted question before proceeding.

### STEP 2 — LOAD REFERENCE FILES
Load `design-systems.md` and `uniqueness-engine.md` immediately.
Load platform-specific refs based on the task type (see table above).

### STEP 3 — RUN THE UNIQUENESS ENGINE
Before picking ANY visual direction, consult `uniqueness-engine.md`.
Select an aesthetic direction that has NOT been used recently.
Commit to it fully.

### STEP 4 — DESIGN DECLARATION
Before writing code or layout, output a short design declaration:

```
## 🎨 Design Direction
- **Aesthetic:** [chosen style — e.g., "Refined Brutalist", "Soft Organic", "Dark Futurism"]
- **Palette:** [3–4 exact hex colors with roles]
- **Typography:** [headline font + body font, both specific]
- **Layout Concept:** [describe the spatial idea in 1 sentence]
- **Signature Element:** [the one thing that makes this unforgettable]
```

### STEP 5 — BUILD THE UI
Follow the platform-specific rules from `platform-specs.md`.
Apply component patterns from `ui-patterns.md`.
Use the token system from `design-systems.md`.

### STEP 6 — SELF-REVIEW
After building, review against this checklist:
```
[ ] Is this visually distinct from any "default" or template-looking design?
[ ] Does every color choice have a purpose?
[ ] Is typography hierarchy clear and interesting?
[ ] Are spacing and alignment consistent throughout?
[ ] Does it work at the target screen size / format?
[ ] Is the signature element present and impactful?
[ ] Would a design-conscious user be genuinely impressed?
```

If any box is unchecked → revise before output.

---

## 🚫 ABSOLUTE PROHIBITIONS

These are design crimes. Never commit them:

### Color Crimes
- ❌ Purple-to-blue gradient on white — the most clichéd AI design
- ❌ Default Bootstrap blue (`#007bff`) as a primary color
- ❌ Pure black (`#000000`) backgrounds — use near-blacks with a hue
- ❌ Pure white (`#ffffff`) on pure white — always add subtle tint
- ❌ More than 5 colors in a palette without intentional purpose

### Typography Crimes
- ❌ Inter as the ONLY font (overused to the point of invisibility)
- ❌ Arial, Roboto, or system-ui for display headings
- ❌ More than 3 font families in one design
- ❌ Body text smaller than 14px on web
- ❌ ALL CAPS body text (headings only)
- ❌ Line height below 1.4 for body text

### Layout Crimes
- ❌ Centered hero + 3 feature cards + footer (the #1 clichéd web layout)
- ❌ Sidebar + content + no visual hierarchy (the #1 clichéd dashboard)
- ❌ Equal margins everywhere with no breathing room variation
- ❌ No visual focal point — user's eye has nowhere to land

### Component Crimes
- ❌ Default browser styles with no customization
- ❌ Rounded-8px everything (choose a border-radius system and stick to it)
- ❌ Drop shadows on everything
- ❌ No hover/focus states on interactive elements

---

## ✅ DESIGN EXCELLENCE STANDARDS

### Color
- Build a palette with **intention**: 1 dominant, 1 accent, 1–2 neutrals, 1 semantic (error/success)
- Use color to direct attention, not just decorate
- Ensure WCAG AA contrast minimum (4.5:1 for body text)
- Reference: `design-systems.md#color-systems`

### Typography
- Choose fonts that express the personality of the product
- Establish a clear type scale (not arbitrary sizes)
- Pair a distinctive display font with a readable body font
- Reference: `design-systems.md#typography`

### Spacing & Layout
- Use a consistent spacing scale (4px, 8px, 16px, 24px, 32px, 48px, 64px...)
- Create visual rhythm through repeated spacing patterns
- Use negative space as a design element, not empty space
- Reference: `design-systems.md#spacing`

### Motion & Interaction (web only)
- Add subtle transitions that feel responsive, not flashy
- Hover states on all interactive elements
- Loading states for async operations
- Reference: `ui-patterns.md#motion`

---

## 📐 OUTPUT FORMAT BY TASK TYPE

### Web / HTML / React
Output complete, production-ready code.
Include all CSS (variables-based, scoped).
Include interaction states.
Comment code sections clearly.

For React, keep styling token-based and scoped; use the host project's styling system consistently.

### PDF / Print / Report
Output layout specification + tool-appropriate code.
Define page dimensions, margins, bleed zones.
Font-embed instructions included.
Reference: `platform-specs.md#print`

### Mobile App Screen
Output as React Native / Flutter / HTML mockup as appropriate.
Define touch target sizes (min 44×44px).
Consider thumb-reach zones.
Reference: `platform-specs.md#mobile`

### Dashboard / Data Visualization
Output with chart library code + layout.
Define data hierarchy visually.
Include empty states and loading states.
Reference: `ui-patterns.md#data`

---

## 🎯 THE GOLDEN RULE

> **If a non-designer user looked at this UI and said "wow, who designed that?" — you succeeded.**
> **If they said "looks like a template" — you failed.**

Every project deserves a design that feels custom-built for it. No exceptions.

---

*Load `design-systems.md` and `uniqueness-engine.md` now before proceeding to any design task.*
