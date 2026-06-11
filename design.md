# Design — Bodhiorchard

A locked design system for the Bodhiorchard frontend. Every page redesign reads
this file before emitting code. Do not regenerate per page — extend or amend this
file when the system needs to grow.

Built with the Hallmark skill (custom theme route, multi-page flow). The product's
metaphor is a **living garden**: BUDs are seeds, shipped work is the harvest, the
3D world is the orchard. This system honours that — a forest-deep canvas, one
disciplined leaf-green accent, a reserved harvest-gold signal — executed with
dev-tool precision, not gamified noise.

## Genre

modern-minimal (dev-ops platform) — custom palette carrying the garden warmth.

## Vibe

`cultivated dev-ops, forest-deep, harvest-gold`

## Macrostructure family

Pages share the system's colour, type, and CTA voice. They vary only in
macrostructure (within the page-type family) and component archetypes.

- **App pages** (Dashboard, BUDs, Features, Bugs, Leaderboard, Skills, Learnings,
  Members, Triage, Settings): **Workbench** — panel/rail-based, dense, functional.
  Nav is the **N3 side-rail** (the persistent left drawer). Variation knobs:
  panel count, rail content, table-vs-card density.
- **Auth / setup pages** (Login, Setup, Change Password): focused single-column,
  quietly branded, centred on a forest-gradient canvas.
- **Narrative pages** (Methodology, Profile): **Long Document** — editorial,
  generous whitespace, one accent moment per section.

## Theme — dark (primary identity)

Anchor hue **150° (forest green)**. Dark is the default theme; the light variant
keeps the hue and flips only lightness/chroma. Never switch the anchor between modes.

- `--color-paper`    oklch(17% 0.025 152)  ·  `#07130A`  deep forest canvas
- `--color-paper-2`  oklch(21% 0.026 152)  ·  `#0F1C12`  card surface (elevation +1)
- `--color-paper-3`  oklch(25% 0.026 152)  ·  `#18251B`  elevated / hover (+2)
- `--color-ink`      oklch(94% 0.012 150)  ·  `#E6EEE7`  primary text (sage-white)
- `--color-ink-2`    oklch(78% 0.014 150)  ·  `#B1BAB3`  secondary text
- `--color-muted`    oklch(62% 0.014 150)  ·  `#808982`  metadata / hints
- `--color-rule`     oklch(31% 0.018 150)  ·  `#2A332C`  dividers
- `--color-rule-2`   oklch(27% 0.016 150)  ·  `#212922`  faint dividers
- `--color-accent`   oklch(66% 0.15 150)   ·  `#3EAB5E`  leaf-green — primary signal
- `--color-accent-ink` oklch(16% 0.02 150) ·  `#071009`  text on accent fill
- `--color-focus`    oklch(72% 0.19 150)   ·  `#20C45F`  focus ring (shows instantly)
- `--color-gold`     oklch(80% 0.13 85)    ·  `#E4B750`  harvest signal — XP/rewards
- `--color-gold-ink` oklch(22% 0.03 85)    ·  `#211909`  text on gold fill

### Tuned semantic layer (status, not brand accent)

Legitimate for a real application — these are status signals, kept distinct from
the two brand accents above.

- `--color-success` oklch(74% 0.16 145) · `#61C568`  (brighter than accent — distinct)
- `--color-error`   oklch(65% 0.17 27)  · `#E45D53`
- `--color-warning` oklch(79% 0.13 68)  · `#F1AA57`
- `--color-info`    oklch(70% 0.12 235) · `#45AADE`

## Theme — light (derived)

- `--color-paper`    `#F0F8F1`  ·  `--color-paper-2` `#FBFEFB`  ·  `--color-paper-3` `#E8F1EA`
- `--color-ink`      `#141D16`  ·  `--color-ink-2` `#414B43`    ·  `--color-muted` `#69716A`
- `--color-rule`     `#CBD4CC`  ·  `--color-rule-2` `#D9E0DA`
- `--color-accent`   `#007834`  ·  `--color-accent-ink` `#F4FAF5` · `--color-focus` `#00822B`
- `--color-gold`     `#C28E24`  ·  `--color-gold-ink` `#211909`
- `--color-success`  `#1B7E2A`  ·  `--color-error` `#C53732` · `--color-warning` `#D78C29` · `--color-info` `#007BB2`

## Typography

Three families — the ceiling. Display ≠ body so the app reads branded, not
defaulted. Loaded via Google Fonts (`index.html`), `font-display: swap`.

- **Display / wordmark:** Bricolage Grotesque — variable display grotesque, weight 600–800, `font-style: normal` (roman; never italic headers). Letter-spacing −0.02em on display sizes.
- **Body / UI:** Geist — weight 400 (350 optical on dark per the dark-mode recipe), 500 for emphasis, 600 for control labels.
- **Mono / code:** JetBrains Mono — BUD docs, code graph, terminal output, tabular numerals. This is the outlier register (≤ 2 role-slots).
- **Type scale:** 1.25 major third from 16px body. Display caps at `clamp(2.25rem, 4vw + 1rem, 3.75rem)` — app headers stay grounded, not poster-sized.

## Spacing

4-point named scale (`--space-3xs` … `--space-3xl`). Values live in `tokens.css`.
Pages must use named tokens (`var(--space-md)`), never raw values.

## Motion

Minimal (modern-minimal). The page is composed, not animated in.

- Easings: `--ease-out` cubic-bezier(0.16, 1, 0.3, 1) · `--ease-in` cubic-bezier(0.7, 0, 0.84, 0) · `--ease-in-out` cubic-bezier(0.65, 0, 0.35, 1). Never the browser default `ease`; never bounce/overshoot on UI state.
- Durations: `--dur-short` 150ms · `--dur-mid` 240ms · `--dur-long` 360ms.
- Reveal pattern: none by default. Hover/active feedback only; `transform` + `opacity` only.
- Reduced-motion fallback: spatial motion collapses to ≤ 150ms opacity crossfade.

## Microinteractions stance

- Silent success over celebratory toasts (XP/harvest toasts are the one earned exception — they are the product's reward loop).
- Optimistic update + Undo over confirmation dialogs where reversible.
- Hover tooltips delay 800ms; focus tooltips 0ms.
- `:focus-visible` ring at ≥ 3:1 contrast, shown instantly (never animated).

## CTA voice

Vuetify-native, 8–10px radius (dense app, not pill-marketing).

- **Primary CTA:** `flat` accent-green fill, accent-ink text, weight 600. One per view region.
- **Secondary CTA:** `tonal` or `outlined` on rule colour, ink text.
- **Destructive:** `text`/`outlined` error colour — never a filled red block by default.
- Copy: imperative + specific ("Plant a BUD", "Ship to prod", "Run scan"), never "Submit"/"Click here".

## Per-page allowances

- Narrative pages (Methodology) MAY use Tier-A CSS art / Tier-B SVG enrichment.
- App pages MUST NOT use enrichment — function and data carry the page.
- The 3D Garden Engine views are out of scope for this token system (own pipeline; see `frontend/src/engine/ARCHITECTURE.md`). They consume brand hues but render in PlayCanvas, not the DOM.

## What pages MUST share

- The wordmark / logotype (Bricolage Grotesque, accent leaf-dot).
- The accent colour and its placement (≤ ~3% per viewport).
- Gold reserved strictly for reward/harvest moments (XP, shipped BUDs, achievements).
- The display + body + mono fonts.
- The CTA voice (button shape, radius, padding rhythm).
- Section heading rhythm: short eyebrow OFF by default; stacked tag-above-heading only when genuinely ordinal.

## What pages MAY differ on

- Macrostructure within the page-type family.
- Component archetypes (card vs table density, panel layout).
- Enrichment — narrative pages only, Tier-A/B only.

## Exports

Drop-in formats for re-using this system. Canonical source is
`frontend/src/assets/styles/tokens.css`.

### tokens.css (dark)
```css
:root {
  --color-paper:      oklch(17% 0.025 152);
  --color-paper-2:    oklch(21% 0.026 152);
  --color-paper-3:    oklch(25% 0.026 152);
  --color-ink:        oklch(94% 0.012 150);
  --color-ink-2:      oklch(78% 0.014 150);
  --color-muted:      oklch(62% 0.014 150);
  --color-rule:       oklch(31% 0.018 150);
  --color-rule-2:     oklch(27% 0.016 150);
  --color-accent:     oklch(66% 0.15 150);
  --color-accent-ink: oklch(16% 0.02 150);
  --color-focus:      oklch(72% 0.19 150);
  --color-gold:       oklch(80% 0.13 85);
  --color-gold-ink:   oklch(22% 0.03 85);

  --font-display: "Bricolage Grotesque", ui-sans-serif, system-ui, sans-serif;
  --font-body:    "Geist", ui-sans-serif, system-ui, sans-serif;
  --font-mono:    "JetBrains Mono", ui-monospace, monospace;

  --space-3xs: 0.25rem; --space-2xs: 0.5rem; --space-xs: 0.75rem;
  --space-sm:  1rem;    --space-md:  1.5rem; --space-lg: 2rem;
  --space-xl:  3rem;    --space-2xl: 4.5rem; --space-3xl: 7rem;

  --text-xs: 0.8rem;  --text-sm: 0.9rem;  --text-base: 1rem;
  --text-md: 1.25rem; --text-lg: 1.5625rem; --text-xl: 1.953rem;
  --text-2xl: 2.441rem; --text-display: clamp(2.25rem, 4vw + 1rem, 3.75rem);

  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in:  cubic-bezier(0.7, 0, 0.84, 0);
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
  --dur-short: 150ms; --dur-mid: 240ms; --dur-long: 360ms;

  --radius-card: 10px; --radius-input: 8px; --radius-pill: 999px;
}
```

### Tailwind v4 `@theme`
```css
@theme {
  --color-paper:   oklch(17% 0.025 152);
  --color-ink:     oklch(94% 0.012 150);
  --color-accent:  oklch(66% 0.15 150);
  --color-gold:    oklch(80% 0.13 85);
  --font-display:  "Bricolage Grotesque", sans-serif;
  --font-body:     "Geist", sans-serif;
  --font-mono:     "JetBrains Mono", monospace;
  --spacing-md:    1.5rem;
  --text-md:       1.25rem;
  --ease-out:      cubic-bezier(0.16, 1, 0.3, 1);
}
```

### DTCG `tokens.json`
```json
{
  "color": {
    "paper":  { "$value": "oklch(17% 0.025 152)", "$type": "color" },
    "ink":    { "$value": "oklch(94% 0.012 150)", "$type": "color" },
    "accent": { "$value": "oklch(66% 0.15 150)", "$type": "color" },
    "gold":   { "$value": "oklch(80% 0.13 85)",  "$type": "color" }
  },
  "font": {
    "display": { "$value": "Bricolage Grotesque", "$type": "fontFamily" },
    "body":    { "$value": "Geist", "$type": "fontFamily" },
    "mono":    { "$value": "JetBrains Mono", "$type": "fontFamily" }
  },
  "space": { "md": { "$value": "1.5rem", "$type": "dimension" } }
}
```

### shadcn/ui CSS variables (dark)
```css
:root {
  --background:         17% 0.025 152;
  --foreground:         94% 0.012 150;
  --primary:            66% 0.15 150;
  --primary-foreground: 16% 0.02 150;
  --muted:              31% 0.018 150;
  --muted-foreground:   62% 0.014 150;
  --border:             31% 0.018 150;
  --input:              31% 0.018 150;
  --ring:               72% 0.19 150;
  --radius:             10px;
}
```

<!-- Hallmark · system · genre: modern-minimal · theme: custom
     vibe: "cultivated dev-ops, forest-deep, harvest-gold"
     paper: oklch(17% 0.025 152) · accent: oklch(66% 0.15 150)
     display: Bricolage Grotesque · body: Geist · mono: JetBrains Mono
     axes: dark / geometric-sans / chromatic-green ~150° · designed-as-app -->
