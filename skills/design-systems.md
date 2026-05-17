# Design Systems Reference
> Loaded by: SKILL.md for all UI tasks
> Purpose: Token systems, typography scales, color palettes, spacing rules

---

## 🎨 COLOR SYSTEMS

### How to Build a Palette from Scratch

Never pick colors randomly. Follow this palette construction method:

```
1. Choose a DOMINANT hue (the brand color — what the design "feels like")
2. Derive TINTS (+white) and SHADES (+black) of the dominant — 5-step scale
3. Choose an ACCENT hue — 120–180° away on the color wheel from dominant
4. Define NEUTRALS — either warm, cool, or chromatic (not pure gray)
5. Define SEMANTIC colors — success (green), error (red), warning (amber), info (blue)
```

### 10 Battle-Tested Palette Archetypes (use as starting inspiration, not copy-paste)

| Archetype | Dominant | Accent | Neutral | Vibe |
|-----------|----------|--------|---------|------|
| **Midnight Studio** | `#0F0F1A` deep navy | `#E8FF47` electric lime | `#1E1E2E` warm dark | Dark, technical, creative |
| **Clay & Stone** | `#C4805A` terracotta | `#2D4A3E` forest | `#F5EDE3` warm cream | Organic, artisan, warm |
| **Arctic Glass** | `#E8F4FD` ice blue | `#FF6B35` sunset orange | `#F8FAFC` near-white | Clean, airy, modern |
| **Gold Standard** | `#1A1A2E` deep ink | `#D4A853` warm gold | `#F0EBE1` aged paper | Luxury, editorial, refined |
| **Neon Brutalist** | `#FFFFFF` white | `#FF0080` hot pink | `#111111` near-black | Bold, raw, energetic |
| **Sage & Smoke** | `#6B7B6E` sage green | `#E8D5B7` warm wheat | `#2C2C2C` charcoal | Natural, balanced, calm |
| **Dusk Gradient** | `#2D1B69` deep purple | `#FF6E6C` coral | `#1A0A3E` darkest | Mystical, digital, immersive |
| **Paper & Ink** | `#FAF7F0` warm paper | `#1C1C1E` deep ink | `#8C7355` medium tan | Editorial, typographic |
| **Ocean System** | `#003459` deep ocean | `#00A8CC` bright teal | `#F0F4F8` mist | Corporate, trustworthy, depth |
| **Rust & Chrome** | `#2A2A2A` gunmetal | `#D4541A` rust orange | `#F5F0EB` warm light | Industrial, bold, utilitarian |

### CSS Variable System (always use this structure)

```css
:root {
  /* Brand */
  --color-primary-50:  [lightest tint];
  --color-primary-100: [light tint];
  --color-primary-500: [base — main usage];
  --color-primary-700: [dark shade];
  --color-primary-900: [darkest shade];

  /* Accent */
  --color-accent:      [accent base];
  --color-accent-hover:[accent darkened 10%];

  /* Neutrals */
  --color-surface:     [page/card background];
  --color-surface-raised: [elevated element bg];
  --color-border:      [subtle borders];
  --color-text-primary:   [main body text];
  --color-text-secondary: [captions, labels];
  --color-text-muted:     [disabled, placeholder];

  /* Semantic */
  --color-success: #22C55E;
  --color-error:   #EF4444;
  --color-warning: #F59E0B;
  --color-info:    #3B82F6;
}
```

---

## 🔤 TYPOGRAPHY

### Font Pairing Philosophy

A great pairing has CONTRAST. Pair fonts that are different in:
- Weight contrast (thin display + bold body OR heavy display + light body)
- Form contrast (serif display + sans body OR geometric + humanist)
- Era contrast (vintage + modern OR classic + digital)

### Curated Font Pairings by Aesthetic

```
EDITORIAL / MAGAZINE
  Display: Playfair Display, Cormorant Garamond, DM Serif Display
  Body:    Source Sans 3, Lato, Libre Franklin

TECHNICAL / DEVELOPER
  Display: Space Grotesk (sparingly), JetBrains Mono, Syne
  Body:    IBM Plex Sans, Fira Sans, Nunito Sans

LUXURY / HIGH-END
  Display: Bodoni Moda, Abril Fatface, Cormorant Italic
  Body:    Jost, Raleway, Questrial

FRIENDLY / CONSUMER
  Display: Nunito, Poppins, Baloo 2
  Body:    Open Sans, Mulish, DM Sans

BRUTALIST / RAW
  Display: Anton, Barlow Condensed, Oswald Bold
  Body:    IBM Plex Mono, Space Mono, Courier Prime

ORGANIC / ARTISAN
  Display: Fraunces, Vollkorn, Libre Baskerville
  Body:    Karla, Cabin, Merriweather Sans

FUTURISTIC / TECH
  Display: Orbitron, Exo 2, Rajdhani
  Body:    Oxanium, Saira, Titillium Web

MINIMAL / ZEN
  Display: Tenor Sans, Josefin Sans, Poiret One
  Body:    Lora, Spectral, Crimson Pro
```

### Type Scale System (use one scale per project)

**Major Third Scale (1.250 ratio)**
```
--text-xs:   0.64rem   (10px)
--text-sm:   0.80rem   (13px)
--text-base: 1.00rem   (16px)
--text-lg:   1.25rem   (20px)
--text-xl:   1.563rem  (25px)
--text-2xl:  1.953rem  (31px)
--text-3xl:  2.441rem  (39px)
--text-4xl:  3.052rem  (49px)
--text-5xl:  3.815rem  (61px)
```

**Perfect Fourth Scale (1.333 ratio) — more dramatic**
```
--text-xs:   0.563rem  (9px)
--text-sm:   0.75rem   (12px)
--text-base: 1.00rem   (16px)
--text-lg:   1.333rem  (21px)
--text-xl:   1.777rem  (28px)
--text-2xl:  2.369rem  (38px)
--text-3xl:  3.157rem  (51px)
--text-4xl:  4.209rem  (67px)
```

**Golden Ratio Scale (1.618) — for editorial/luxury**
```
--text-base: 1.00rem   (16px)
--text-lg:   1.618rem  (26px)
--text-xl:   2.618rem  (42px)
--text-2xl:  4.236rem  (68px)
--text-3xl:  6.854rem  (110px)
```

### Line Height System
```css
--leading-tight:   1.25   /* Headings */
--leading-snug:    1.375  /* Sub-headings */
--leading-normal:  1.5    /* Body default */
--leading-relaxed: 1.625  /* Long-form reading */
--leading-loose:   2.0    /* Spacious / editorial */
```

### Letter Spacing System
```css
--tracking-tighter: -0.05em  /* Large display, bold */
--tracking-tight:   -0.025em /* Headings */
--tracking-normal:  0em      /* Body */
--tracking-wide:    0.025em  /* UI labels, buttons */
--tracking-wider:   0.05em   /* Captions, overlines */
--tracking-widest:  0.1em    /* ALL-CAPS labels */
```

---

## 📐 SPACING SYSTEM

### The 8px Base Grid (recommended for most projects)

```css
--space-0:   0px
--space-1:   4px    /* Micro — icon gaps, tight padding */
--space-2:   8px    /* XSmall — compact padding */
--space-3:   12px   /* Small — tag padding */
--space-4:   16px   /* Base — standard padding */
--space-5:   20px   /* Medium-low */
--space-6:   24px   /* Medium — section padding */
--space-8:   32px   /* Large — card padding */
--space-10:  40px   /* XLarge */
--space-12:  48px   /* 2XLarge — section gaps */
--space-16:  64px   /* 3XLarge — major sections */
--space-20:  80px   /* 4XLarge — hero padding */
--space-24:  96px   /* 5XLarge */
--space-32:  128px  /* Full sections */
```

### Layout Width Constraints
```css
--width-xs:   480px   /* Narrow modals, cards */
--width-sm:   640px   /* Narrow content */
--width-md:   768px   /* Standard content */
--width-lg:   1024px  /* Standard layout */
--width-xl:   1280px  /* Wide layout */
--width-2xl:  1536px  /* Full-width */
--width-prose: 65ch   /* Optimal reading width */
```

---

## 🔲 BORDER RADIUS SYSTEMS

Pick ONE system per project. Never mix.

```css
/* SHARP — brutalist, technical */
--radius-sm: 0px;
--radius-md: 2px;
--radius-lg: 4px;

/* SUBTLE — modern, professional */
--radius-sm: 4px;
--radius-md: 8px;
--radius-lg: 12px;

/* ROUNDED — friendly, consumer */
--radius-sm: 8px;
--radius-md: 12px;
--radius-lg: 16px;
--radius-xl: 24px;

/* PILL — playful, bold */
--radius-sm:  20px;
--radius-md:  9999px;  /* Full pill */
--radius-lg:  9999px;

/* ORGANIC — mixed/irregular — advanced */
/* Use clip-path or SVG-based borders for truly organic shapes */
```

---

## 💫 SHADOW SYSTEMS

```css
/* Elevation-based shadows (pick one set per project) */

/* FLAT — no shadows, use borders instead */
--shadow-sm: none;
--shadow-md: none;
--shadow-border: 0 0 0 1px rgba(0,0,0,0.1);

/* SOFT — gentle elevation */
--shadow-sm:  0 1px 2px rgba(0,0,0,0.05);
--shadow-md:  0 4px 12px rgba(0,0,0,0.08);
--shadow-lg:  0 8px 24px rgba(0,0,0,0.12);
--shadow-xl:  0 16px 48px rgba(0,0,0,0.16);

/* DRAMATIC — strong depth */
--shadow-sm:  0 2px 4px rgba(0,0,0,0.15);
--shadow-md:  0 8px 20px rgba(0,0,0,0.2);
--shadow-lg:  0 20px 40px rgba(0,0,0,0.3);
--shadow-xl:  0 40px 80px rgba(0,0,0,0.4);

/* COLORED — tinted to brand */
/* Replace rgba(0,0,0) with brand color */
--shadow-brand: 0 8px 24px rgba(VAR_PRIMARY_H, VAR_PRIMARY_S, VAR_PRIMARY_L, 0.3);

/* INSET — pressed/sunken state */
--shadow-inset: inset 0 2px 4px rgba(0,0,0,0.1);
```

---

## 📊 DATA VISUALIZATION COLOR SYSTEM

For dashboards and charts, use a **categorical palette** that is:
- Distinguishable by colorblind users
- Consistent in perceived brightness (no one color "pops" more than others)
- Works on both light and dark backgrounds

```css
/* 8-color accessible categorical palette */
--chart-1: #3B82F6;  /* Blue */
--chart-2: #10B981;  /* Emerald */
--chart-3: #F59E0B;  /* Amber */
--chart-4: #EF4444;  /* Red */
--chart-5: #8B5CF6;  /* Violet */
--chart-6: #06B6D4;  /* Cyan */
--chart-7: #F97316;  /* Orange */
--chart-8: #84CC16;  /* Lime */

/* Sequential palette for single-metric heatmaps */
/* Light → Dark in your brand color */
```

---

*Return to SKILL.md after reading. Load `uniqueness-engine.md` next.*
