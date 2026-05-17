# UI Patterns Reference
> Loaded by: SKILL.md for web, mobile, dashboard, and component tasks
> Purpose: Component patterns, interaction design, and layout blueprints

---

## 🧩 COMPONENT DESIGN PRINCIPLES

Every component must have ALL of these states defined:

```
Default → Hover → Active/Pressed → Focus → Disabled → Loading (if async) → Error (if input)
```

Never ship a component without its full state set.

---

## 📦 CORE COMPONENTS

### Buttons

**Hierarchy:** Every design needs a clear button hierarchy.

```css
/* PRIMARY — the main action, one per screen section */
.btn-primary {
  background: var(--color-primary-500);
  color: var(--color-on-primary);
  padding: var(--space-3) var(--space-6);
  border-radius: var(--radius-md);
  font-weight: 600;
  letter-spacing: var(--tracking-wide);
  transition: all 200ms ease;
}
.btn-primary:hover { background: var(--color-primary-700); transform: translateY(-1px); }
.btn-primary:active { transform: translateY(0); }

/* SECONDARY — supporting action */
.btn-secondary {
  background: transparent;
  border: 1.5px solid var(--color-primary-500);
  color: var(--color-primary-500);
}

/* GHOST — tertiary or destructive */
.btn-ghost {
  background: transparent;
  color: var(--color-text-secondary);
  border: none;
}
.btn-ghost:hover { background: var(--color-surface-raised); }
```

**Button size variants:**
```css
.btn-sm:  padding: 6px 12px;  font-size: var(--text-sm);
.btn-md:  padding: 10px 20px; font-size: var(--text-base);  /* Default */
.btn-lg:  padding: 14px 28px; font-size: var(--text-lg);
.btn-xl:  padding: 18px 36px; font-size: var(--text-xl);
```

---

### Cards

**Pattern A — Flat Card** (for content-heavy layouts)
```css
.card {
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
}
```

**Pattern B — Elevated Card** (for interactive items)
```css
.card-elevated {
  background: var(--color-surface-raised);
  box-shadow: var(--shadow-md);
  border-radius: var(--radius-lg);
  transition: box-shadow 200ms ease, transform 200ms ease;
}
.card-elevated:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}
```

**Pattern C — Outlined Card** (for selection/option states)
```css
.card-outlined {
  border: 2px solid var(--color-border);
  border-radius: var(--radius-lg);
}
.card-outlined[aria-selected="true"] {
  border-color: var(--color-primary-500);
  background: var(--color-primary-50);
}
```

---

### Forms & Inputs

```css
.input {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface);
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  color: var(--color-text-primary);
  transition: border-color 150ms ease, box-shadow 150ms ease;
}

.input:hover  { border-color: var(--color-text-secondary); }
.input:focus  {
  outline: none;
  border-color: var(--color-primary-500);
  box-shadow: 0 0 0 3px rgba(primary, 0.15);
}
.input.error  { border-color: var(--color-error); }
.input:disabled { opacity: 0.5; cursor: not-allowed; }
```

**Form layout rule:** Always use label above field, never placeholder-only.
```html
<div class="field">
  <label class="label">Email address</label>
  <input class="input" type="email" placeholder="you@example.com" />
  <span class="hint">We'll never share your email.</span>
</div>
```

---

### Navigation Patterns

**Pattern A — Top Nav Bar** (web apps, marketing)
```
[Logo]    [Nav Links]    [CTA Button]
```
- Fixed or sticky on scroll
- Mobile: collapses to hamburger with slide drawer
- Active link: use border-bottom OR background pill, not just color change

**Pattern B — Side Nav** (dashboards, admin panels)
```
[Logo]
[Nav Item - Icon + Label]
[Nav Item - Active state]
[...]
[User Profile at bottom]
```
- 240px wide (expanded), 64px (collapsed icon-only)
- Active item: background pill with primary color tint

**Pattern C — Tab Nav** (content sections, settings)
```
[Tab 1] [Tab 2 - Active] [Tab 3]
         _______________
```
- Underline style for inline tabs
- Pill style for floating tabs
- Never use tabs for navigation between pages — use links

---

### Data Tables

```html
<table class="data-table">
  <thead>
    <tr>
      <th class="th-sortable">Column <span class="sort-icon">↕</span></th>
    </tr>
  </thead>
  <tbody>
    <tr class="tr-hover">
      <td>Cell value</td>
    </tr>
  </tbody>
</table>
```

```css
.data-table { border-collapse: collapse; width: 100%; }
.data-table th {
  text-align: left;
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: var(--tracking-widest);
  text-transform: uppercase;
  color: var(--color-text-secondary);
  border-bottom: 2px solid var(--color-border);
}
.data-table td {
  padding: var(--space-4);
  border-bottom: 1px solid var(--color-border);
  font-size: var(--text-sm);
}
.tr-hover:hover { background: var(--color-surface-raised); }
```

---

### Status & Badge Components

```css
/* Status badge — for state indication */
.badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px var(--space-2);
  border-radius: 9999px;
  font-size: var(--text-xs);
  font-weight: 600;
}

.badge-success { background: #DCFCE7; color: #166534; }
.badge-error   { background: #FEE2E2; color: #991B1B; }
.badge-warning { background: #FEF9C3; color: #854D0E; }
.badge-info    { background: #DBEAFE; color: #1E40AF; }
.badge-neutral { background: var(--color-surface-raised); color: var(--color-text-secondary); }
```

---

## 📊 DATA VISUALIZATION PATTERNS

### Dashboard Layout Archetypes

**Pattern A — Command Center** (monitoring, ops)
```
┌──────────────────────────────────────┐
│  KPI  │  KPI  │  KPI  │  KPI        │
├───────────────────┬──────────────────┤
│                   │                  │
│   Main Chart      │   Secondary      │
│   (70% width)     │   Chart (30%)    │
│                   │                  │
├───────────────────┴──────────────────┤
│              Data Table              │
└──────────────────────────────────────┘
```

**Pattern B — Analytics Overview** (business metrics)
```
┌──────────────────────────────────────┐
│     Hero Metric — Big Number         │
├─────────────────────┬────────────────┤
│  Time Series Chart  │  Donut Chart   │
├──────────┬──────────┴────────────────┤
│  Top 5   │      Recent Activity      │
│  Table   │      Feed/List            │
└──────────┴───────────────────────────┘
```

**Pattern C — Compact Cards** (SaaS product overview)
```
┌────┐ ┌────┐ ┌────┐ ┌────┐
│KPI │ │KPI │ │KPI │ │KPI │
└────┘ └────┘ └────┘ └────┘
┌──────────────────────────┐
│      Full Width Chart    │
└──────────────────────────┘
┌────────────┐ ┌───────────┐
│  Table     │ │  List     │
└────────────┘ └───────────┘
```

### KPI Card Anatomy
```
┌─────────────────────┐
│ Icon    Trend ↑2.4% │
│                     │
│ 24,891              │  ← Big number, prominent
│ Total Users         │  ← Label, secondary color
│ ▁▂▃▄▅▆▇ sparkline  │  ← Optional mini chart
└─────────────────────┘
```

---

## 🎬 MOTION PATTERNS

### Transition Timing Functions
```css
--ease-default:  cubic-bezier(0.4, 0, 0.2, 1);    /* Material standard */
--ease-in:       cubic-bezier(0.4, 0, 1, 1);        /* Exit transitions */
--ease-out:      cubic-bezier(0, 0, 0.2, 1);        /* Enter transitions */
--ease-spring:   cubic-bezier(0.34, 1.56, 0.64, 1); /* Springy/bouncy */
--ease-smooth:   cubic-bezier(0.25, 0.46, 0.45, 0.94); /* Smooth, elegant */
```

### Duration Guidelines
```css
--duration-instant:  50ms   /* Feedback, checkbox toggle */
--duration-fast:    100ms   /* Hover states, tooltips */
--duration-normal:  200ms   /* Most transitions */
--duration-slow:    300ms   /* Modals, panels entering */
--duration-slower:  500ms   /* Page transitions, hero animations */
```

### Entrance Animations
```css
/* Fade up — universal, subtle */
@keyframes fade-up {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* Scale in — for modals, dropdowns */
@keyframes scale-in {
  from { opacity: 0; transform: scale(0.95); }
  to   { opacity: 1; transform: scale(1); }
}

/* Slide in right — for drawers, side panels */
@keyframes slide-in-right {
  from { transform: translateX(100%); }
  to   { transform: translateX(0); }
}

/* Stagger children — apply with CSS custom property */
.stagger-children > * {
  animation: fade-up var(--duration-slow) var(--ease-out) both;
  animation-delay: calc(var(--index, 0) * 80ms);
}
```

---

## 📱 RESPONSIVE BREAKPOINT SYSTEM

```css
/* Mobile-first breakpoints */
--bp-sm:   640px   /* Large phones, small tablets */
--bp-md:   768px   /* Tablets */
--bp-lg:   1024px  /* Small laptops */
--bp-xl:   1280px  /* Desktops */
--bp-2xl:  1536px  /* Large screens */

/* Usage */
@media (min-width: 768px) { /* md and up */ }
@media (min-width: 1024px) { /* lg and up */ }
```

### Grid System
```css
.grid-layout {
  display: grid;
  grid-template-columns: repeat(var(--cols, 12), 1fr);
  gap: var(--space-4);
}

/* Column spans */
.col-full    { grid-column: 1 / -1; }         /* 12/12 */
.col-half    { grid-column: span 6; }          /* 6/12 */
.col-third   { grid-column: span 4; }          /* 4/12 */
.col-quarter { grid-column: span 3; }          /* 3/12 */
.col-two-thirds { grid-column: span 8; }       /* 8/12 */
.col-sidebar { grid-column: span 4; }
.col-main    { grid-column: span 8; }
```

---

## 🎯 EMPTY STATES

Every interface must handle empty states gracefully.

```
┌─────────────────────────┐
│                         │
│       [Illustration]    │
│                         │
│   Nothing here yet      │  ← Primary message
│   Start by creating     │  ← Supporting text
│   your first item.      │
│                         │
│      [CTA Button]       │
│                         │
└─────────────────────────┘
```

Rules for empty states:
- Use a simple illustration (SVG, not stock photo)
- Primary message: empathetic, not robotic ("Nothing here yet" not "No records found")
- Always provide a clear next action (button or link)
- Use the brand color for the illustration

---

## ⚠️ LOADING STATES

**Skeleton loaders** (for content that loads in)
```css
.skeleton {
  background: linear-gradient(
    90deg,
    var(--color-surface-raised) 25%,
    var(--color-border) 50%,
    var(--color-surface-raised) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: var(--radius-sm);
}

@keyframes shimmer {
  from { background-position: 200% 0; }
  to   { background-position: -200% 0; }
}
```

**Spinner** (for actions)
```css
.spinner {
  width: 20px; height: 20px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary-500);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
```

---

*Return to SKILL.md after reading. Proceed to Step 5 — Build the UI.*
