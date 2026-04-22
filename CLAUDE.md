# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **bodhiorchard** (21045 symbols, 40685 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/bodhiorchard/context` | Codebase overview, check index freshness |
| `gitnexus://repo/bodhiorchard/clusters` | All functional areas |
| `gitnexus://repo/bodhiorchard/processes` | All execution flows |
| `gitnexus://repo/bodhiorchard/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

---

## Common Commands

All development is orchestrated from the repo root via npm workspaces. Backend Python lives in `backend/.venv` (created by `npm run setup`); activate `conda activate python3129` for ad-hoc Python tooling.

### Root (dev loop)
| Command | What it does |
|---------|-------------|
| `npm run setup` | One-time: creates `backend/.venv`, installs Python deps, copies `.env` files, starts infra, runs Alembic migrations |
| `npm run dev` | Starts postgres+redis, waits for Postgres, then runs backend/frontend/multiplayer concurrently with colour-coded logs |
| `npm run dev:infra` / `npm run stop` | Start/stop the infra-only containers (postgres, redis) |
| `npm run dev:backend` / `dev:frontend` / `dev:multiplayer` | Run a single process if `npm run dev` is too noisy |
| `docker compose up` | **Full Docker** mode — whole stack incl. backend in containers (see README for Hybrid vs Full Docker trade-off) |
| `npx gitnexus analyze` | Refresh the GitNexus index after commits (a PostToolUse hook handles this automatically after `git commit`/`git merge`) |

### Backend (`backend/`)
- **Lint**: `.venv/bin/ruff check . --fix && .venv/bin/ruff format .` (line-length 99, rules `E,F,I,N,W,UP,B,A,SIM`)
- **Type check**: `.venv/bin/mypy app/` (strict mode, pydantic plugin enabled)
- **Tests**: `.venv/bin/pytest` — `asyncio_mode = "auto"`, testpaths = `tests/`
- **Single test**: `.venv/bin/pytest tests/path/to/test_x.py::test_name -xvs`
- **New migration**: `.venv/bin/alembic revision --autogenerate -m "message"` then `alembic upgrade head` (also auto-runs on backend startup via `entrypoint.sh`)

### Frontend (`frontend/`)
- **Type check (the real gate)**: `npx vue-tsc --noEmit` — `npm run lint` fails because no ESLint config exists; ignore the pre-existing unused-import error in `SceneManager.ts`
- **Build**: `npm run build` (runs `vue-tsc --noEmit` then Vite)
- **Tests**: `npm test` (Vitest, one-shot) / `npm run test:watch`

### Multiplayer (`multiplayer/`)
- **Dev**: `npm --workspace bodhiorchard-multiplayer run start:dev` (Colyseus 0.17, port 2567)

---

## Architecture Overview

Bodhiorchard is a **local-first, multi-tenant AI dev-ops platform** with three cooperating processes plus managed infra. Keep these boundaries in mind — they determine where new code belongs.

### Three-process topology
- **`backend/` (FastAPI, Python 3.12, async SQLAlchemy 2.0)** — REST API, agent orchestration, MCP server, repository scanning. Every request is JWT-auth'd and **org-scoped**; repositories enforce tenant isolation at the data layer.
- **`frontend/` (Vue 3 + Vuetify 3 + Pinia + TypeScript)** — SPA at `:3000`. Uses PlayCanvas for the 3D "Living Tree" / Garden Engine visualization. Axios interceptor attaches JWT.
- **`multiplayer/` (Colyseus 0.17, TypeScript)** — authoritative room server at `:2567` for shared 3D-world state (OrgRoom, RaceRoom). Simulation logic is *server-side*; clients interpolate.
- **Infra** — PostgreSQL 16 + pgvector (vector search for BUDs/bugs/features), Redis (cache + job queue).

### Backend layering (strict, top-down)
```
api/v1/          HTTP handlers — thin; validate via schemas, delegate to services
agents/          Agent definitions & orchestrators (11 agents: Triage, BUD, TechPlan, ...)
mcp/             MCP server exposing 10 tools to Claude Code
services/        Business logic — LLM calls, scanning, synthesis, bud_closure, bug_linker
repositories/    Data access — all queries filter by organization_id
models/          SQLAlchemy ORM
schemas/         Pydantic DTOs
core/            Auth, permissions, encryption (Fernet AES-128 for secrets at rest)
```
Cross-cutting patterns: **async jobs** (register handler → return `202` → track via `useJobSocket`); **dual Claude auth modes** per org (`api_key` vs `hybrid_host`, stored in `claude_auth_mode`).

**Event-bus fanout**: `event_bus.publish(topic, payload)` reaches (a) in-process asyncio Queue subscribers (dashboard `/ws`) and (b) every external transport registered via `register_transport()` in `main.py` lifespan. The multiplayer server subscribes via `services/colyseus_forwarder.py`. Add new external sinks (Slack, metrics, SSE) by writing an `async (topic, payload) -> None` callback and registering it in lifespan — no publisher-side changes.

### BUD lifecycle (the core domain object)
```
bud → design → development → testing → uat → prod → closed   (discarded at any stage)
```
- Markdown doc with spec / tech spec / test plan sections, numbered per org (`BUD-001`, …).
- Embeddings generated at creation time; bug-linker uses pgvector cosine distance, threshold 0.40.
- `on_bud_closed()` in `services/bud_closure.py` is the single entry point for contributor-XP + repo-scan side effects — called from both manual PATCH and auto-close.
- Release detection has two paths: fast (`bud_id` on PR) and SHA-walk (release PRs without `bud_id`).

### Shared code
`shared/world/zones.ts` holds world-zone positions imported by **both** the frontend engine and the multiplayer server — keep them in sync or the simulations desync.

### Deployment modes (critical context)
| Mode | Backend runs in | Claude auth | Use when |
|------|----------------|-------------|---------|
| Full Docker | Container | Org-level API key in Settings → AI Config | Evaluators, Mac-mini deploys |
| Hybrid | Host venv (hot reload) | Inherits host's `claude login` session | Dev loop, Claude Pro subscription |

The stored `claude_auth_mode` on the org decides which path agent runs take.

### Key references in-repo
- `BODHIORCHARD-ARCHITECTURE.md` — full 8400-line architecture spec
- `AGENTS.md` — per-agent capabilities and triggers
- `frontend/src/engine/ARCHITECTURE.md` — **must-read before touching the Garden Engine** (rules encoded in the Garden Engine section below)

---

## Frontend Quality Gate
- **No ESLint config exists** — `npm run lint` fails. Use `vue-tsc --noEmit` as the type-check gate
- **Pre-existing TS error** in `SceneManager.ts` (unused import) — ignore in type-check output
- `v-tabs-window-item` `value` must exactly match `v-tab` `value` — mismatches cause silent blank content
- Tab values like `'uat'`, `'prod'`, `'closed'` are NOT in `BUD_SECTIONS` — they're in `NON_SECTION_BUD_TABS` and `STATUS_TAB_MAP`

## BUD Lifecycle Completeness
- BUDs get embeddings at creation time (for bug linker vector search)
- `on_bud_closed()` in `bud_closure.py` handles: contributor XP + repo scan (called from both manual PATCH and auto-close)
- Release detection: fast path (bud_id on PR) vs SHA-walk path (release PRs without bud_id)
- Bug auto-linking: `bug_linker.py` uses pgvector cosine distance with 0.40 threshold

---

## KayKit Character Animations

**Two different state graph types** — KayKit vs Kenney characters use DIFFERENT parameter types:
- **KayKit** (via KayKitCharacterFactory): Uses `LOCOMOTION_STATE_GRAPH` from AnimUtils.ts with **BOOLEAN** `sitting` and **INTEGER** `speed`, `working`
- **Kenney** (legacy blocky): Uses custom state graphs with **INTEGER** params for all

**When setting anim params, ALWAYS check `_isKayKit`:**
```typescript
if (this._isKayKit) {
  anim.setBoolean('sitting', true)   // BOOLEAN for KayKit
} else {
  anim.setInteger('sitting', 1)      // INTEGER for Kenney
}
```

**Available KayKit animations** (from `characters/kaykit/animations/*.glb`):
- `simulation.glb`: `Sit_Chair_Idle`, `Sit_Chair_Down`, `Sit_Floor_Idle`, `Lie_Down`, `Lie_Idle`, `Lie_StandUp`, `Cheering`, `Waving`
- `general.glb`: `Idle_A`, `Idle_B`, `Interact`, `Use_Item`, `PickUp`, `Death_A`
- `movement_basic.glb`: `Walking_A`, `Running_A`, `Jump_Full_Short`
- `tools.glb`: `Work_A`, `Working_A`, `Chop`, `Hammer`, `Fishing_Idle`

**Use exact track names** with `findAnimTrack()` — not fuzzy keywords.

---

## Garden Engine (3D Visualization)

**Before making ANY changes to `frontend/src/engine/`**, you MUST:

1. **Read `frontend/src/engine/ARCHITECTURE.md`** — this is the single source of truth for the engine's structure, conventions, data flow, and design decisions.
2. **Follow the PBR lighting rule** — NEVER use `useLighting = false` on any material. The engine uses proper IBL + ACES tone mapping + sRGB gamma. If something looks dark, adjust exposure/material properties — don't bypass the pipeline.
3. **Respect the boundary** — only `GardenEngine` (from `engine/index.ts`) is imported by Vue. `types.ts` has zero app-layer imports.
4. **Use MaterialFactory** — don't create ad-hoc `StandardMaterial` instances. Use `MaterialFactory.getColor()` for cached, properly-lit materials.
5. **Return exclusion zones** — any subsystem that occupies ground space must return `{ x, z, radius }` zones so grass/rocks avoid it.
6. **Old engine backup** — the previous engine lives in `frontend/src/engine_bkup/` for reference. It is excluded from TypeScript compilation via `tsconfig.json`.

### KayKit Animation Track Gotcha
- `simulation.glb` has multiple tracks with `Sit` prefix: `Sit_Chair_Down` (0.8s transition) and `Sit_Chair_Idle` (3.6s loop). **Always use the exact track name** `Sit_Chair_Idle` — fuzzy keyword `'Sit'` matches `Sit_Chair_Down` first, which is a one-shot transition that looks like idle.
- `findAnimTrack()` in `AnimUtils.ts` does substring matching and returns the first hit. When assigning via keywords, put the most specific name first: `['Sit_Chair_Idle', 'Sit']`.
- `KayKitCharacterFactory.ANIM_TRACK_MAP` is the authoritative mapping for NPC characters. `TakeoverAnimGraph.assignCoreAnimations` must match these exact track names.
- The same pattern applies to any future animations with shared prefixes (e.g. `Walk_Forward` vs `Walk_Backward`).

### Takeover Seat Interaction
- E-key fires `wasPressed` which can trigger twice rapidly — a 300ms cooldown (`seatToggleCooldown`) in `GardenEngine.onUpdate` prevents sit/stand toggle loops.
- `TakeoverController.getAnimState()` must return `"sit"` when `_sitting` is true, otherwise the periodic broadcast sends `"idle"` to the server and other clients see the character standing on the chair.
- `TakeoverController.sitAt()` must clear `jumpProgress` and `anim.setBoolean('jumping', false)` to cleanly transition from any prior state.

### Engine Phases

| Phase | Status | What it adds |
|-------|--------|-------------|
| 1 — Skeleton | DONE | Application boot, PBR lighting, camera, input, materials |
| 2 — World | PENDING | Environment, trees, buildings, pool, water, arcs |
| 3 — Player | PENDING | GLTF characters, WASD movement, swimming, labels |
| 4 — NPC AI | PENDING | Behavior trees, time-based schedules, activity routing |
| 5 — Interaction | PENDING | Click/hover picking, tooltips, camera focus |
| 6 — Effects | PENDING | Particles, splash, ZZZ, steam, vehicles |
