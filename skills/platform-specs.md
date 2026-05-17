# Platform Specifications
> Loaded by: SKILL.md — load only the section relevant to your task
> Purpose: Platform-specific constraints, rules, and output formats

---

## 🌐 WEB (HTML / CSS / React / Vue) {#web}

### Technical Rules
- Use **CSS custom properties** (variables) for ALL design tokens — never hardcode values
- Mobile-first CSS — start with mobile styles, add breakpoints for larger screens
- Always include `box-sizing: border-box` globally
- Always include `scroll-behavior: smooth` on `:root`
- Use `rem` for font sizes, `em` for component-scoped spacing, `px` for borders
- Prefer CSS Grid for 2D layouts, Flexbox for 1D layouts
- Never use `!important` unless overriding a third-party library

### Performance Rules
- Lazy-load images below the fold (`loading="lazy"`)
- Inline critical CSS (above-the-fold styles)
- Use `will-change: transform` only on actively animated elements
- Prefer `transform` and `opacity` for animations (GPU-accelerated)
- Load Google Fonts with `display=swap`

### Accessibility Rules (non-negotiable)
- All interactive elements must be keyboard-focusable
- All images must have descriptive `alt` text
- Color contrast minimum: 4.5:1 for body text, 3:1 for large text
- Use semantic HTML: `<nav>`, `<main>`, `<section>`, `<article>`, `<header>`, `<footer>`
- Focus states must be VISIBLE — never `outline: none` without a custom focus style
- Form inputs must have associated `<label>` elements

### HTML Boilerplate Pattern
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>[Page Title]</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=[Font]:wght@[weights]&display=swap" rel="stylesheet">
  <style>
    /* 1. CSS Reset */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    /* 2. Design Tokens */
    :root { /* All variables here */ }

    /* 3. Base Styles */
    body {
      font-family: var(--font-body);
      font-size: var(--text-base);
      color: var(--color-text-primary);
      background: var(--color-surface);
      line-height: var(--leading-normal);
      -webkit-font-smoothing: antialiased;
    }

    /* 4. Layout */
    /* 5. Components */
    /* 6. Utilities */
    /* 7. Responsive Overrides */
  </style>
</head>
<body>
  <!-- Content -->
</body>
</html>
```

### React Component Pattern
```jsx
// Always use CSS-in-JS via inline styles with tokens OR Tailwind utilities
// Structure: styled component → logic → return JSX

export default function ComponentName({ prop1, prop2 }) {
  // State & logic
  const [state, setState] = useState(null);

  // Event handlers
  const handleAction = () => {};

  // Render
  return (
    <div className="component-root">
      {/* JSX here */}
    </div>
  );
}
```

---

## 📱 MOBILE APP SCREENS {#mobile}

### Dimension Standards
```
iPhone 15 Pro:   393 × 852 pt
iPhone SE:       375 × 667 pt
Android Common:  360 × 800 dp
iPad:            820 × 1180 pt (landscape: 1180 × 820)

Safe zones:
  Status bar:     ~50pt top
  Home indicator: ~34pt bottom
  Side margins:   16–24pt
```

### Touch Target Rules
- Minimum touch target: **44 × 44pt** (iOS) / **48 × 48dp** (Android)
- Spacing between targets: minimum 8pt
- Primary actions: 48–56pt tall (always thumb-friendly)

### Thumb Reach Zones
```
SAFE (easy reach):   Bottom 40% of screen
STRETCH (reachable): Middle 40% of screen
HARD (difficult):    Top 20% of screen

→ Place primary actions in SAFE zone
→ Navigation at the bottom (not top) for thumb-first design
→ Destructive actions (delete) in HARD zone (requires deliberate reach)
```

### Mobile Navigation Patterns
**Tab Bar** (bottom, iOS / Android):
- 3–5 tabs maximum
- Icon + label (both together, not icon alone)
- Active tab: colored icon, heavier label

**Gesture Navigation**:
- Swipe from left edge to go back
- Pull to refresh on list views
- Long press for context menus (not right-click)

### Mobile Typography Minimums
```
Body text:    minimum 16pt (never smaller)
Caption:      minimum 12pt
Button label: minimum 14pt, weight 600+
```

### React Native / Flutter Output Format
When building mobile UI code:
```
1. Define dimensions using device-independent units (pt/dp, not px)
2. Use percentage-based widths, not fixed pixel widths
3. Use SafeAreaView to avoid notch/status bar collisions
4. Always define touch feedback (opacity change or ripple)
5. Include scroll behavior for content that may overflow
```

---

## 🖨️ PDF / PRINT / REPORT DESIGN {#print}

### Page Dimensions
```
A4:       210 × 297mm  (portrait)  /  297 × 210mm  (landscape)
Letter:   8.5 × 11in   (portrait)  /  11 × 8.5in   (landscape)
A3:       297 × 420mm
A5:       148 × 210mm
```

### Margin System (print)
```
Standard report:    25mm all sides
Presentation PDF:   15mm all sides
Book/editorial:     Outside 15mm / Inside 25mm / Top 20mm / Bottom 25mm
```

### Print-Specific Rules
- Use **CMYK or Pantone** values for physical print; RGB/HEX for screen PDFs
- Minimum font size for print: **8pt**
- Body text for long-form: **9–11pt** (smaller than screen)
- Line height for print: **1.3–1.5** (screen: 1.5–1.625)
- Never use `px` for print — use `pt` or `mm`
- Images for print: minimum **300 DPI**
- Avoid hairline borders (< 0.25pt) — they may not print

### PDF Layout Grid System
```
Single column:    Text width = page width − margins
Two column:       Each col = (page − margins − gutter) / 2
Three column:     Each col = (page − margins − (2 × gutter)) / 3
Gutter width:     5mm minimum, 8–10mm standard
```

### Report Structure Template
```
Cover Page:
  - Company logo (top left or centered)
  - Report title (large, brand color)
  - Subtitle / date / author (small, secondary)
  - Optional: Full-bleed image or color background

Table of Contents:
  - Section names (left) + page numbers (right)
  - Leader dots connecting name to number

Executive Summary:
  - Key findings as KPI callouts
  - 2–3 paragraph summary

Content Sections:
  - Section header (large, branded)
  - Body text in 1–2 columns
  - Charts and figures with captions
  - Data tables with alternating row colors

Back Cover / Appendix:
  - Contact information
  - Legal / disclaimer text (smallest size)
```

### PDF Generation Tools (by platform)
```
Python:      reportlab, weasyprint, pdfkit (html→pdf)
JavaScript:  puppeteer (html→pdf), jsPDF, PDFKit
React:       @react-pdf/renderer
CSS:         @page rules + print media query
```

### Print Color Rules
```css
/* For screen PDFs (most common) */
:root {
  --color-primary: #1A3A5C;   /* Deep, prints well */
  --color-accent:  #E8953A;   /* Warm, visible in print */
  --color-text:    #1A1A1A;   /* Near-black (not pure) */
  --color-subtle:  #F5F5F5;   /* Light gray for alternating rows */
}

/* Avoid for print: */
/* - Neon colors (bleed in print) */
/* - Very light tints < 10% (invisible in print) */
/* - Multiple gradients (inconsistent across printers) */
```

---

## 📧 EMAIL TEMPLATES {#email}

### Email Constraints (the hardest platform)
- **No CSS Grid** — use HTML tables for layout
- **No Flexbox** — not supported in Outlook
- **No web fonts** — fall back to system fonts (`Arial, sans-serif` / `Georgia, serif`)
- **No external stylesheets** — all CSS must be **inline**
- **Max width: 600px** — standard for email clients
- **No JavaScript** — email clients strip it
- **No `position: absolute/fixed`**
- **Images must have `alt` text** — many clients block images by default

### Email Structure Template
```html
<!-- Wrapper table -->
<table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#F4F4F4">
  <tr>
    <td align="center" style="padding: 24px 0;">

      <!-- Email container -->
      <table width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="#FFFFFF"
             style="border-radius: 8px; overflow: hidden;">

        <!-- Header -->
        <tr>
          <td bgcolor="#1A3A5C" style="padding: 32px 40px; text-align: center;">
            <img src="logo.png" alt="Company" width="150" style="display: block; margin: 0 auto;">
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding: 40px; font-family: Arial, sans-serif;">
            <h1 style="font-size: 28px; color: #1A1A1A; margin: 0 0 16px;">Heading</h1>
            <p style="font-size: 16px; line-height: 1.6; color: #444444; margin: 0 0 24px;">Body text</p>

            <!-- CTA Button (table-based for Outlook) -->
            <table cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td bgcolor="#1A3A5C" style="border-radius: 6px;">
                  <a href="#" style="display: block; padding: 14px 28px; color: #ffffff;
                     font-family: Arial, sans-serif; font-size: 16px; font-weight: bold;
                     text-decoration: none;">Call to Action</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td bgcolor="#F4F4F4" style="padding: 24px 40px; text-align: center;
               font-family: Arial, sans-serif; font-size: 12px; color: #888888;">
            <p>Unsubscribe | Privacy Policy | Company Address</p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
```

### Email Typography (inline only)
```
Headline:  font-size: 28–36px; font-weight: bold; color: [brand]
Subhead:   font-size: 20–24px; font-weight: bold;
Body:      font-size: 16px; line-height: 1.6; color: #444444
Caption:   font-size: 13px; color: #888888
```

---

## 🖥️ DESKTOP APPLICATION UI {#desktop}

### Window Layout Standards
```
Title bar:       28–36px tall (system-controlled on most platforms)
Toolbar:         40–48px tall
Sidebar:         200–280px wide
Status bar:      24–28px tall
Content padding: 16–24px from edges
```

### Desktop-Specific Interactions
- **Right-click context menus** — support them everywhere contextually relevant
- **Keyboard shortcuts** — all primary actions must have them; display in tooltips
- **Drag and drop** — support where it reduces friction (file uploads, sorting lists)
- **Resize handles** — panels should be resizable where content depth varies
- **Multi-selection** — Shift+click, Ctrl+click for lists and grids

### Electron / Tauri App Conventions
```
Menu bar:   Use native OS menu bar (File, Edit, View, Help minimum)
Titlebar:   Platform-native, or custom with traffic light buttons on Mac
Scrollbars: Platform-native (prefer native over custom scrollbar CSS)
Dialogs:    Use native dialogs for file open/save — not custom HTML modals
```

---

*Return to SKILL.md Step 5 — Build the UI using the appropriate platform spec.*
