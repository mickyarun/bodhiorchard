# Landing site — `bodhiorchard.ai`

The public landing site is a **multi-page, pre-rendered marketing site** built
with `vite-ssg`. Each route renders to its own static HTML file (great for SEO),
and the deeper pages reuse the same methodology **section components** as the
in-app `/methodology` route — one source of truth, no copy drift. Output is
deployed to Cloudflare Pages.

## Pages

| Route | Page | Composes |
| --- | --- | --- |
| `/` | `pages/HomePage.vue` | Bolder hero (aurora + gradient), highlights, demo facade, vs-Agile teaser, CTA |
| `/methodology` | `pages/MethodologyPage.vue` | Lifecycle flow + manifesto + AI-vs-humans + FAQ |
| `/agents` | `pages/AgentsPage.vue` | The 12 agent cards |
| `/platform` | `pages/PlatformPage.vue` | Screenshots, estimation/BUD, quality, knowledge, gamification, videos |
| `/vs-agile` | `pages/VsAgilePage.vue` | The phase-by-phase comparison table |
| `/why-bodhiorchard` | `pages/WhyBodhiorchardPage.vue` | The philosophy / brand story |

## Files (under `frontend/`)

| Path | Purpose |
| --- | --- |
| `src/components/methodology/sections/*` | Shared section components (also used in-app) — edit content via `src/data/methodology.ts` |
| `src/components/landing/effects/*` | Pure-CSS animation effects (aurora, gradient text, scroll-reveal, spotlight, tilt, border beam) |
| `landing-src/index.html` | HTML shell — only static, every-page tags (charset, fonts, icon) |
| `landing-src/main.ts` | `vite-ssg` router entry → `LandingLayout` |
| `landing-src/LandingLayout.vue` | Sticky nav + footer + `<router-view>` |
| `landing-src/router.ts` / `routes-manifest.ts` | Route table + canonical path list (shared with sitemap) |
| `landing-src/vuetify.ts` | Landing-only dark Vuetify instance (SSR-safe; no `localStorage`) |
| `landing-src/pages/*` | Thin page shells: compose sections + one `useSeo()` call |
| `landing-src/components/*` | Marketing-only components (hero, footer, CTA band, teaser, FAQ, …) |
| `landing-src/composables/useSeo.ts` | Per-route `<head>` (title, description, canonical, OG, Twitter, JSON-LD) |
| `landing-src/seo/structured-data.ts` | SoftwareApplication + FAQPage JSON-LD |
| `landing-src/content/site.ts` | Marketing copy + constants |
| `landing-src/public/` | Public assets served at site root (screenshots, logos, `robots.txt`, `404.html`) |
| `vite.landing.config.ts` | Separate Vite config — own root, `dist-landing/` output, sitemap generation |
| `tsconfig.landing.json` | Type-check config that also covers `landing-src/` |

## Build, type-check & deploy

```bash
# Type-check (covers landing-src too)
npm --workspace bodhiorchard-frontend run typecheck:landing

# Build
npm --workspace bodhiorchard-frontend run build:landing
# Output: frontend/dist-landing/  (one index.html per route + sitemap.xml)

# Local preview
npm --workspace bodhiorchard-frontend run preview:landing

# Deploy to Cloudflare Pages (from repo root)
npx wrangler@latest pages deploy frontend/dist-landing \
  --project-name=bodhiorchard-landing \
  --commit-dirty=true \
  --branch=main
```

## What the build produces

- One pre-rendered `index.html` per route (`/methodology/index.html`, etc.) with
  all text in static HTML — visible to crawlers and no-JS users.
- Per-route `<head>`: distinct title, description, canonical, Open Graph, Twitter
  card; `SoftwareApplication` JSON-LD on Home, `FAQPage` JSON-LD on Methodology.
- `sitemap.xml` (generated from the route manifest), `robots.txt`, and a static
  branded `404.html`.
- Per-route JS code-splitting — a page only ships the chunks it uses.

## SEO

Per-route metadata is set by `useSeo()` (unhead, bundled by vite-ssg) inside each
page — **not** in `index.html`. To change a page's title/description, edit the
`useSeo({...})` call in that page. To add/remove a route, update
`landing-src/routes-manifest.ts` (drives nav, sitemap) **and**
`landing-src/router.ts` (maps the path to a page).

## SSR gotchas baked into this setup

- **Dark-only, no `localStorage`.** `landing-src/vuetify.ts` hard-codes
  `bodhiorchardDark`. The main app's plugin reads `localStorage` to pick a theme,
  which would crash SSR / mismatch hydration — so the landing has its own
  instance. Both share theme definitions from `src/plugins/vuetify-theme.ts`.
- `ssr.noExternal: ['vuetify']` — Vuetify imports per-component CSS (`VChip.css`
  etc.) directly, and Node's ESM loader can't resolve `.css` imports. Bundling
  Vuetify into the SSR output routes those through Vite's CSS pipeline.
- Animation effects touch `window`/pointer only inside `onMounted`, and the SSG
  renders content in its visible final state (no `opacity:0` baked into markup),
  so crawlers and no-JS users see everything.
- `landing-src/public/` is its own publicDir (separate from `frontend/public/`)
  to avoid uploading the main app's 3D model assets to Cloudflare.

## Why this is a separate Vite root

Without `root: 'landing-src'`, `vite-ssg` discovers `frontend/index.html` (the
main app entry) and bundles the whole app — including the PlayCanvas engine and
the Rapier WASM physics layer. That blows past Cloudflare Pages' per-file limit
and pulls in dependencies that don't belong on a marketing page.
