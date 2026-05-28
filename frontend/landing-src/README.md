# Landing site — `bodhiorchard.ai`

The public landing site is **derived from the Vue methodology page**
(`frontend/src/views/setup/steps/MethodologyStep.vue`) so there is a single
source of truth between the in-app `/methodology` route and the marketing
site. The Vue page is pre-rendered to static HTML with `vite-ssg` and the
output is deployed to Cloudflare Pages.

## Files (under `frontend/`)

| Path | Purpose |
| --- | --- |
| `src/views/setup/steps/MethodologyStep.vue` | The methodology content — edit here. |
| `landing-src/index.html` | HTML shell: SEO meta, OG tags, JSON-LD, favicon |
| `landing-src/main.ts` | `vite-ssg` entry — mounts `LandingApp` |
| `landing-src/LandingApp.vue` | App-bar + GitHub CTA wrapper around `MethodologyStep` |
| `landing-src/public/` | Public assets served at site root (screenshots, logos) |
| `vite.landing.config.ts` | Separate Vite config (own `root`, own `dist-landing/` output) |

## Build & deploy

```bash
# Build
npm --workspace bodhiorchard-frontend run build:landing
# Output: frontend/dist-landing/

# Local preview
npm --workspace bodhiorchard-frontend run preview:landing
# http://localhost:4173

# Deploy to Cloudflare Pages (from repo root)
npx wrangler@latest pages deploy frontend/dist-landing \
  --project-name=bodhiorchard-landing \
  --commit-dirty=true \
  --branch=main
```

## What the build produces

- Pre-rendered `index.html` (~155 kB) with every section's text in static HTML —
  visible to crawlers and to users with JavaScript disabled.
- Hydration JS (~110 kB gzipped) for interactive features: expansion panels,
  video tabs, image lightbox, smooth scrolling.
- Vuetify's full theme CSS + MDI icon font (~250 kB gzipped total).
- All seven screenshots and both logos under `dist-landing/landing/` and
  `dist-landing/assets/`.

## Why this is a separate Vite root

Without `root: 'landing-src'`, `vite-ssg` discovers `frontend/index.html` (the
main app entry) and bundles the whole app — including the PlayCanvas engine and
the Rapier WASM physics layer. That blows the bundle past 25 MB (Cloudflare
Pages' per-file limit) and pulls in dependencies that don't belong on a
marketing page. Keeping the landing build in its own root isolates it.

## SSR gotchas baked into this setup

- `ssr.noExternal: ['vuetify']` in `vite.landing.config.ts` — Vuetify imports
  per-component CSS (`VChip.css` etc.) directly, and Node's ESM loader can't
  resolve `.css` imports. Bundling Vuetify into the SSR output routes those
  through Vite's CSS pipeline instead.
- Native `<img>` instead of `<v-img>` in `MethodologyStep.vue` — `v-img` is
  intentionally lazy and renders a loading skeleton server-side; image URLs
  never make it into the pre-rendered HTML. `<img loading="lazy">` SSR-renders
  with the `src` attribute intact while keeping the lazy behaviour.
- `landing-src/public/` is its own publicDir (separate from `frontend/public/`)
  to avoid uploading the main app's ~60 MB of 3D model assets to Cloudflare.
- `MethodologyStep.vue` references the logo at `/assets/bodhiorchard-logo-sm.png`
  (the main-app path served from `frontend/public/assets/`). The landing build
  resolves the same path via `landing-src/public/assets/bodhiorchard-logo-sm.png`.
  Three copies of the same PNG sit on disk — keep them in sync, or replace the
  duplicates with a build-time copy step.

## History

The earlier hand-coded `landing/index.html` drifted from the canonical Vue
methodology page — any improvement to one had to be duplicated to the other.
The vite-ssg pipeline replaces that static HTML with a build of the Vue page.

The old static HTML lives in git history (`git log -- landing/index.html`).
