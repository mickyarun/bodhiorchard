# Design — Glideship

A locked design system for the Glideship frontend. Every page redesign reads
this file before emitting code. Do not regenerate per page — extend or amend this
file when the system needs to grow.

The product redefines how software gets built: agents run the flow from idea to
spec to code to production while people keep the decisions. The system reads as
a calm, trustworthy work tool for engineering and non-engineering teams alike —
slate neutrals, one blue for action, indigo as the brand accent, gold reserved
for XP.

## Genre

modern-minimal (work platform) — neutral surfaces, colour only where it means
something.

## Vibe

`calm, precise, effortless — work glides from idea to shipped`

## Macrostructure family

Pages share the system's colour, type, and CTA voice. They vary only in
macrostructure (within the page-type family) and component archetypes.

- **App pages** (Dashboard, Board, Features, Bugs, Leaderboard, Skills, Learnings,
  Members, Triage, Settings, People, Leave): **Workbench** — panel/rail-based,
  dense, functional. Nav is the **side rail** (the persistent left drawer),
  grouped Work · Insights · People, with Members and Settings at the foot.
- **Auth / setup pages** (Login, Setup, Change Password): focused single-column,
  quietly branded.
- **Narrative pages** (Methodology, Profile): **Long Document** — editorial,
  generous whitespace, one accent moment per section.

## Quality bar

Every component looks professional and modern and is easy to use:

- One primary button per view region marks the next step; everything else is
  secondary or text.
- Colour means something: status, priority and selection are the only coloured
  elements. Surfaces stay neutral.
- Every input has a visible label; icon-only buttons have an accessible name.
- Quiet density: 14px body, 4-point spacing, 36–40px controls.

## Theme — dark (default)

- `--color-paper`      `#0B1120`  app canvas
- `--color-paper-2`    `#111827`  card surface (elevation +1)
- `--color-paper-3`    `#1A2233`  elevated / hover (+2)
- `--color-ink`        `#E5E9F0`  primary text
- `--color-ink-2`      `#CBD2DC`  secondary text
- `--color-muted`      `#94A3B8`  metadata / hints (6.9:1 on paper-2)
- `--color-rule`       `#222C3D`  dividers, card edges
- `--color-rule-2`     `#1E2738`  faint dividers
- `--color-accent`     `#60A5FA`  action blue — a light fill with dark ink so
  labels (7.4:1) and blue text on cards (7.0:1) both pass AA
- `--color-accent-ink` `#0B1120`  text on accent fill
- `--color-focus`      `#93C5FD`  focus ring (shows instantly)
- `--color-brand`      `#818CF8`  indigo — brand accent, never an action colour
- `--color-gold`       oklch(80% 0.13 85) · `#E4B750`  XP / rewards only
- `--color-gold-ink`   oklch(22% 0.03 85) · `#211909`  text on gold fill

### Status layer (never the action colour)

- `--color-success` `#4ADE80` · `--color-error` `#F87171`
- `--color-warning` `#FBBF24` · `--color-info` `#38BDF8`

## Theme — light

- `--color-paper` `#F7F8FA` · `--color-paper-2` `#FFFFFF` · `--color-paper-3` `#F1F3F6`
- `--color-ink` `#0F172A` · `--color-ink-2` `#334155` · `--color-muted` `#5B6474` (6.0:1 on white)
- `--color-rule` `#E3E6EB` · `--color-rule-2` `#EEF1F5`
- `--color-accent` `#2563EB` (5.2:1 on white) · `--color-accent-ink` `#FFFFFF` · `--color-focus` `#2563EB`
- `--color-brand` `#3730A3`
- `--color-gold` `#C28E24` · `--color-gold-ink` `#211909`
- `--color-success` `#15803D` · `--color-error` `#DC2626` · `--color-warning` `#B45309` · `--color-info` `#0369A1`

## Brand mark

The two-plane sail: a blue sail over an indigo bow. Light surfaces use
`#2563EB` / `#3730A3`; dark surfaces use `#60A5FA` / `#6366F1` so the bow stays
visible. Assets live in `frontend/public/assets/brand/`; the product name and
mark paths are read from `frontend/src/constants/brand.ts`, rendered by
`BrandLogo.vue`.

## Typography

Loaded via Google Fonts (`index.html`), `font-display: swap`.

- **Display + body / UI:** Geist — headings 600 with −0.02em tracking; body 400
  (350 optical on dark), 500 for emphasis and labels.
- **Wordmark:** Plus Jakarta Sans 700 — the product name only (`.bo-wordmark`).
- **Mono / code:** JetBrains Mono — BUD ids, code, terminal output, tabular numerals.
- **Type scale:** 1.25 major third from 16px body. Display caps at
  `clamp(2.25rem, 4vw + 1rem, 3.75rem)` — app headers stay grounded.

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

- Silent success over celebratory toasts (XP toasts are the one earned exception — they are the product's reward loop).
- Optimistic update + Undo over confirmation dialogs where reversible.
- Hover tooltips delay 800ms; focus tooltips 0ms.
- `:focus-visible` ring at ≥ 3:1 contrast, shown instantly (never animated).

## CTA voice

Vuetify-native, 8–10px radius (dense app, not pill-marketing).

- **Primary CTA:** `flat` accent-blue fill, accent-ink text, weight 500. One per view region.
- **Secondary CTA:** `outlined` on rule colour, ink text.
- **Destructive:** `text`/`outlined` error colour — never a filled red block by default.
- Copy: imperative + specific ("New BUD", "Approve", "Connect GitHub"), never "Submit"/"Click here".

## Per-page allowances

- Narrative pages (Methodology) MAY use Tier-A CSS art / Tier-B SVG enrichment.
- App pages MUST NOT use enrichment — function and data carry the page.
- The 3D Garden Engine views are out of scope for this token system (own pipeline; see `frontend/src/engine/ARCHITECTURE.md`). They render in PlayCanvas, not the DOM, and keep their own natural palette.

## What pages MUST share

- The mark and wordmark (`BrandLogo`).
- The accent colour and its placement (≤ ~3% per viewport).
- Gold reserved strictly for reward moments (XP, shipped BUDs, achievements).
- The body + wordmark + mono fonts.
- The CTA voice (button shape, radius, padding rhythm).
- Section heading rhythm: short eyebrow OFF by default; stacked tag-above-heading only when genuinely ordinal.

## What pages MAY differ on

- Macrostructure within the page-type family.
- Component archetypes (card vs table density, panel layout).
- Enrichment — narrative pages only, Tier-A/B only.

## Exports

Canonical source is `frontend/src/assets/styles/tokens.css`; the Vuetify
theme in `frontend/src/plugins/vuetify-theme.ts` mirrors its hex values.

### tokens.css (dark)
```css
:root {
  --color-paper:      #0B1120;
  --color-paper-2:    #111827;
  --color-paper-3:    #1A2233;
  --color-ink:        #E5E9F0;
  --color-ink-2:      #CBD2DC;
  --color-muted:      #94A3B8;
  --color-rule:       #222C3D;
  --color-rule-2:     #1E2738;
  --color-accent:     #60A5FA;
  --color-accent-ink: #0B1120;
  --color-focus:      #93C5FD;
  --color-brand:      #818CF8;
  --color-gold:       oklch(80% 0.13 85);
  --color-gold-ink:   oklch(22% 0.03 85);

  --font-display: "Geist", ui-sans-serif, system-ui, sans-serif;
  --font-body:    "Geist", ui-sans-serif, system-ui, sans-serif;
  --font-brand:   "Plus Jakarta Sans", ui-sans-serif, system-ui, sans-serif;
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

<!-- system · genre: modern-minimal · theme: custom
     vibe: "calm, precise, effortless"
     paper: #0B1120 · accent: #60A5FA (dark) / #2563EB (light) · brand: indigo
     display + body: Geist · wordmark: Plus Jakarta Sans · mono: JetBrains Mono -->
