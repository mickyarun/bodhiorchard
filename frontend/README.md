# Bodhiorchard Frontend

Vue 3 + Vuetify 3 + Pinia SPA. Hosts the in-app UI and the public landing site (same source, two builds).

## Tech stack

- **Framework**: Vue 3 (`<script setup>`, Composition API) + TypeScript
- **UI**: Vuetify 3 (forest-green + warm-gold dark theme, see `src/plugins/vuetify.ts`)
- **State**: Pinia
- **Routing**: Vue Router 4
- **3D engine**: PlayCanvas (Living Tree dashboard + the multiplayer virtual world)
- **Physics**: Rapier3D (WASM)
- **Multiplayer**: Colyseus 0.17 client (connects to the multiplayer workspace at `:2567`)
- **Build**: Vite 5
- **Tests**: Vitest

## Two build targets, one source tree

| Target | Entry | Command | Output |
| --- | --- | --- | --- |
| Main app (`localhost:3000`) | `index.html` → `src/main.ts` | `npm run dev` / `npm run build` | `frontend/dist/` |
| Public landing (`bodhiorchard.ai`) | `landing-src/index.html` → `landing-src/main.ts` → wraps `MethodologyStep.vue` | `npm run build:landing` (uses `vite.landing.config.ts` + `vite-ssg`) | `frontend/dist-landing/` |

The landing build pre-renders to true static HTML via `vite-ssg` so the page is SEO-friendly and visible without JavaScript. See [`landing-src/README.md`](landing-src/README.md) for the build internals.

## Common commands

```bash
# Dev (from repo root, recommended — also starts backend + multiplayer + infra)
npm run dev

# Frontend only
npm --workspace bodhiorchard-frontend run dev
# http://localhost:3000

# Type-check + build the main app
npm --workspace bodhiorchard-frontend run build

# Type-check only (use this as the gate — npm run lint is broken, see below)
cd frontend && npx vue-tsc --noEmit

# Build the public landing
npm --workspace bodhiorchard-frontend run build:landing

# Preview the built landing locally
npm --workspace bodhiorchard-frontend run preview:landing

# Unit tests (Vitest)
npm --workspace bodhiorchard-frontend test
```

## Project layout

```
frontend/
├── index.html                 # Main app entry
├── landing-src/               # Landing build (see landing-src/README.md)
├── public/                    # Main-app static assets (~60 MB — 3D models, etc.)
├── src/
│   ├── App.vue                # Root component
│   ├── main.ts                # Main-app entry
│   ├── router/                # Vue Router
│   ├── stores/                # Pinia stores
│   ├── views/                 # Top-level routes
│   ├── components/            # Reusable components (common/, setup/, buds/, …)
│   ├── engine/                # 3D Garden Engine (PlayCanvas)
│   ├── multiplayer/           # Colyseus integration
│   ├── data/                  # Static data (agents, phases, …)
│   ├── plugins/vuetify.ts     # Theme + defaults — single source of truth
│   ├── services/              # API client (axios + JWT interceptor)
│   └── assets/styles/         # SCSS theme overrides
├── vite.config.ts             # Main-app build
└── vite.landing.config.ts     # Landing build
```

## Conventions (enforced by review)

- **Type-check is the real gate**: `npm run lint` is intentionally broken — there's no ESLint config. Use `npx vue-tsc --noEmit` instead. There's a pre-existing unused-import error in `SceneManager.ts` that you can ignore.
- **No big files**: keep components under ~200 lines. Composables and child components are encouraged.
- **`v-tabs-window-item` `value` must match `v-tab` `value` exactly** — mismatches silently render blank content.
- **AppCallout + AppPillToggle** (from `components/common/`) — never `v-alert` or `v-btn-toggle` directly. The visual contract is muted tint + 3 px left accent for callouts; primary-fill pill track + surface-active for toggles.
- **Garden Engine**: read [`src/engine/ARCHITECTURE.md`](src/engine/ARCHITECTURE.md) before touching anything under `src/engine/`. Specifically:
  - **Never** set `useLighting = false` on any material — the engine uses proper IBL + ACES tone mapping; bypassing the pipeline corrupts colour.
  - Only `GardenEngine` (from `engine/index.ts`) is imported by Vue; the engine's `types.ts` has zero app-layer imports.
  - Use `MaterialFactory.getColor()` for cached, properly-lit materials — no ad-hoc `StandardMaterial`.
  - Subsystems that occupy ground space must return `{ x, z, radius }` exclusion zones so grass and rocks avoid them.

## KayKit character animations (two-state-graph gotcha)

KayKit and Kenney characters use **different parameter types** in their animation state graphs:

```ts
if (this._isKayKit) {
  anim.setBoolean('sitting', true)   // BOOLEAN for KayKit
} else {
  anim.setInteger('sitting', 1)      // INTEGER for Kenney
}
```

Animation tracks must be referenced by **exact name** (e.g. `Sit_Chair_Idle`, not `'Sit'`) — `findAnimTrack()` does substring matching and returns the first hit, so the more specific name has to come first. `KayKitCharacterFactory.ANIM_TRACK_MAP` is the authoritative mapping for NPC characters.

## Shared world layout

World zone positions, scaling, and paths live in [`shared/world/zones.ts`](../shared/world/zones.ts) and are imported by **both** the frontend engine **and** the multiplayer server. Edit one without the other and the simulations desync.

## Frontend-only landing build deep-dive

If you're changing the public landing page, edit `src/views/setup/steps/MethodologyStep.vue` — it's the single source of truth for both the in-app `/methodology` route and `bodhiorchard.ai`. See [`landing-src/README.md`](landing-src/README.md) for the SSR gotchas, the Vite root isolation rationale, and the deploy command.

## Environment

| Variable | Purpose | Default |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Backend API base | proxied to `http://localhost:8000` |
| `VITE_MULTIPLAYER_URL` | Colyseus server | proxied to `ws://localhost:2567` |

Vite proxies `/api` → `:8000` and `/colyseus` → `:2567` in dev so HTTPS pages (ngrok, Tailscale Serve) don't hit a mixed-content block.
