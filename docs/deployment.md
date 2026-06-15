# Deployment Guide

Bodhiorchard splits cleanly into two planes so you can pick how much of it lives on your hardware.

## The data plane is always local

Postgres + pgvector, every BUD, the embeddings index, the scanned repos, the agent skills, and the audit log all sit on your machine. Nothing in this plane ever calls home — even when you choose cloud inference, the data the agents reason over stays on your hardware.

## Inference is your call

Three first-class modes, three reasons to pick each:

- **Local Claude Code** — point Bodhiorchard at a host `claude login` session. Pro / Max flat-rate, no per-token bills, codebase-aware.
- **Cloud Claude via API key** — paste an `sk-ant-…` into **Settings → AI Configuration → Claude Code**. Pay-per-token, recommended for evaluators and CI.
- **Anthropic direct API** — for the lightweight non-codebase agents (Triage, Bug-Linker, Standup). Lower latency and lower per-call cost than going through Claude Code.

See [AI Engines & MCP Server](ai-engines.md) for the engine-by-engine breakdown.

## One-machine self-host

A single laptop or Mac Mini runs the whole platform — frontend, backend, multiplayer, Postgres, Redis. A **Cloudflare Tunnel** optionally exposes just the Slack / GitHub webhook endpoints without putting the rest of the stack online. This makes Bodhiorchard a credible **self-hosted Jira alternative** for teams that don't want to live on per-seat SaaS.

What you get:

- **Lower cost than per-seat SaaS** — no platform-compute bills; pay only for whichever inference engine you wire up (or flat-rate if you're on a Claude subscription).
- **Lower energy footprint** — a Mac Mini idles around 10W vs hundreds of watts for cloud VMs.
- **Data residency by default** — code, BUDs, embeddings, and knowledge stay on your hardware even when inference is in the cloud.

## System diagram

```
  Your Machine (Laptop / Mac Mini)
  ┌────────────────────────────────────────────────────────────┐
  │                                                            │
  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
  │  │  Vue 3 SPA   │  │  FastAPI     │  │  Claude Code    │  │
  │  │  (Frontend)   │──│  (Backend)   │──│  (AI Engine)    │  │
  │  └──────────────┘  └──┬───┬───┬───┘  └────────┬────────┘  │
  │                       │   │   │                │           │
  │          ┌────────────┘   │   └──────────┐     │ MCP       │
  │          │                │              │     │ (MCP tools)│
  │  ┌───────▼────┐  ┌────────▼──┐  ┌────────▼──────┐ │         │
  │  │ PostgreSQL │  │  Redis    │  │ Ollama / OpenAI│ │         │
  │  │ + pgvector │  │  Cache    │  │ (coming soon)  │ │         │
  │  └────────────┘  └───────────┘  └────────────────┘ │         │
  │                                                            │
  └──────────────────────┬─────────────────────────────────────┘
                         │ Cloudflare Tunnel (optional)
                         │
             ┌───────────▼───────────┐
             │  Internet             │
             │  ├─ Slack webhooks    │
             │  ├─ GitHub webhooks   │
             │  └─ Cloud LLM APIs   │
             └───────────────────────┘
```

## Choosing a deployment mode

Bodhiorchard ships in **two deployment modes**. The product is identical, only the process boundary between your host and the containers changes.

| Mode | What runs in Docker | What runs on your host | Claude auth |
|---|---|---|---|
| **Full Docker** | postgres, redis, **backend**, multiplayer, frontend | nothing | Anthropic API key (entered in Settings → AI Configuration) |
| **Hybrid** | postgres, redis only (infra) | backend, multiplayer, frontend via `npm run dev` | The host's existing `claude login` session (Claude Pro/Max subscription) |

**Pick Full Docker** for a one-command "evaluator" setup, a dedicated Mac-mini deployment, or any case where you'd rather pay-per-token via Anthropic's API than wire up a Claude subscription. **Pick Hybrid** if you already run `claude` interactively on your laptop and want agents to use that same flat-rate subscription, or you want hot-reload for development.

### Fastest: one command with `npx` (no clone, no build)

The quickest way to try Bodhiorchard. The [`bodhiorchard`](https://www.npmjs.com/package/bodhiorchard) npm package pulls prebuilt images from Docker Hub and runs the full Full-Docker stack — you don't clone the repo or build anything.

```bash
npx bodhiorchard init     # detect ports, generate secrets, pull images
cd bodhiorchard
npx bodhiorchard start     # start everything and open the setup wizard
```

Needs only **Docker (running)** and **Node.js 18+**. If Postgres (5432) or Redis (6379) — or an app port — is already in use, the installer detects it and asks whether to **remap to a free port** or **reuse the existing service**. When the stack is healthy it opens **http://localhost:3000/setup**; finish there (organization, admin account, AI provider, repositories). No keys are entered on the command line.

Manage the stack with these commands (run from the install directory):

| Command | What it does |
|---|---|
| `bodhiorchard init [name]` | Scaffold the install: resolve ports, generate secrets, pull images |
| `bodhiorchard start` | Start the stack and open the setup wizard |
| `bodhiorchard stop` | Stop the stack — **containers come down, your data volumes are kept** |
| `bodhiorchard status` | Show container status and the access URLs |
| `bodhiorchard logs [service]` | Follow logs (optionally for one service) |
| `bodhiorchard update [--tag X.Y.Z]` | Pull newer images and restart |
| `bodhiorchard reset` | Stop **and delete all data volumes** (destructive) |

To stop everything when you're done, run `bodhiorchard stop` (your database and cloned repos persist; `bodhiorchard start` brings it back up). It's the same stack as **Full Docker mode** below — just pulled instead of built. Use the `git clone` paths below if you want to build from source or run in **Hybrid** mode.

### Prerequisites

- **Full Docker**: Docker Desktop ≥ 4.20 (everything else is in containers)
- **Hybrid**: Docker + Node.js 18+ + Python 3.12+ + a host-installed, already-logged-in [Claude Code CLI](https://code.claude.com/docs/en/setup)
- Windows: use WSL2 for either mode
- (Optional) Cloudflare account for tunnel — needed for Slack/GitHub webhooks

### Full Docker mode (one command)

```bash
git clone https://github.com/mickyarun/bodhiorchard.git
cd bodhiorchard
docker compose up
```

Open **http://localhost:3000**. Postgres, Redis, backend, multiplayer, and frontend all start together. Migrations run automatically on backend startup. First build takes ~5 min (the backend image installs git, Node.js 20, and the `@anthropic-ai/claude-code` npm package); subsequent runs are instant.

Once the UI is up:

1. Complete first-time setup (org name, admin user, source repo path).
2. Go to **Settings → AI Configuration → Claude Code**.
3. Choose **API key (Full Docker)**, paste an `sk-ant-…` key from [console.anthropic.com](https://console.anthropic.com/settings/keys), and **Save**.
4. Click **Test connection** — it should report the CLI version and a successful round-trip.

The key is encrypted (Fernet AES-128) in Postgres and pushed into the backend's process env on save, so every subsequent agent run inherits it. No compose-level env var required.

### Hybrid mode (hot reload)

```bash
git clone https://github.com/mickyarun/bodhiorchard.git
cd bodhiorchard
npm install        # frontend + multiplayer deps via workspaces
npm run setup      # Python venv, .env files, infra, migrations
npm run dev        # backend + frontend + multiplayer, one terminal
```

- **Frontend**: http://localhost:3000 (Vite, hot reload)
- **Backend**: http://localhost:8000/docs (FastAPI, `--reload`)
- **Multiplayer**: ws://localhost:2567 (Colyseus)

Only `postgres` and `redis` run in Docker (via `docker-compose.infra.yml`). The backend process inherits your shell environment — including whatever `claude login` has authenticated on your host — so agent runs use your Claude subscription automatically. In **Settings → AI Configuration → Claude Code**, leave the auth mode on **Hybrid / host login** (the default).

All three host processes run in a single terminal with color-coded logs. Ctrl-C stops them; `npm run stop` tears down the infra containers.

### Switching between modes

The database is the same shape either way, so you can swap modes against the same data. Stop the current mode first (`Ctrl-C` + `npm run stop` for Hybrid, `docker compose down` for Full Docker), then start the other. The stored `claude_auth_mode` on your organization determines which path agent runs take — update it in Settings when you switch.

## Try the included examples

Bodhiorchard pairs with **TaskFlow** — four deliberately wired-together sample repos that exercise cross-repo feature detection, skill profiling, BUD generation, and PR-merge feature reconciliation without you needing to wire up your own codebase:

- `taskflow-api` — FastAPI backend (auth, tasks, notifications, billing)
- `taskflow-web` — Vue + Vuetify frontend that calls into the API
- `taskflow-worker` — async job worker (reminders, invoice generation)
- `taskflow-qa` — Playwright BDD test suite

The four repos share four features (Auth, Tasks, Notifications, Billing) implemented across them by four fictional developers, so the very first scan produces cross-repo features rather than four disconnected copies.

The example repos are tracked **independently** at [`github.com/mickyarun/taskflow-*`](https://github.com/mickyarun?tab=repositories&q=taskflow) — they are NOT bundled into this repo. (The PR-merge testing flow merges PRs into them constantly, which would otherwise pollute the parent repo's `git status`.) The bootstrap script clones them on first run.

**1. Bootstrap** (one-time, ~1 min — clones the four repos from GitHub and rebuilds their synthetic per-author commit history):

```bash
cd examples
bash setup-git-history.sh
```

The script uses `gh repo clone` when available, falling back to `git clone` over SSH. To clone from a fork instead, export `BODHIORCHARD_EXAMPLES_OWNER=<your-username>` before running.

**2. In the Bodhiorchard UI, add the four repos under Settings → Repositories:**

```
/absolute/path/to/examples/taskflow-api
/absolute/path/to/examples/taskflow-web
/absolute/path/to/examples/taskflow-worker
/absolute/path/to/examples/taskflow-qa
```

Map each to its `main` branch.

**3. Click "Full Rescan"** in the Repositories settings. The scan finishes in ~1–2 minutes on a Mac Mini and you should see:

- **~4–6 cross-repo features** in the Feature Registry (Authentication, Tasks, Notifications, Billing, Reminders) — each one linked to the repos that actually implement it, not four separate copies per repo.
- **Skill profiles for 4 developers** under Settings → Developers, with per-module scores derived from the synthetic git history.
- **A populated Living Tree dashboard** — one limb per repo, branches per feature, leaves coloured by git freshness.
- **A pre-written `BUD-001-tech-spec.md`** alongside the example repos you can paste into a new BUD via the UI to watch a realistic spec drive Tech Plan → Implementation.

The TaskFlow repos are intentionally small (Vue 3 frontend, FastAPI + worker backends; ~6 commits per author) so the whole loop completes fast enough to demo. Read [`examples/README.md`](../examples/README.md) for the full feature map, SQL verification queries, and author-to-skill mapping.

You can also use the example repos to exercise the **PR-merge feature-reconcile flow**: open a PR on (e.g.) `mickyarun/taskflow-web`, merge it, and watch the backend's `webhook_logs` row transition from `pending` to `running` to `done` as the Redis-stream consumer processes the merge. The affected feature's `last_seen_sha` advances to the merge SHA and any new fetch calls materialise as BACKEND junctions in `feature_to_repo`.
