# Deployment Guide

Glideship splits cleanly into two planes so you can pick how much of it lives on your hardware.

## The data plane is always local

Postgres + pgvector, every BUD, the embeddings index, the scanned repos, the agent skills, and the audit log all sit on your machine. Nothing in this plane ever calls home — even when you choose cloud inference, the data the agents reason over stays on your hardware.

## Inference is your call

Three first-class modes, three reasons to pick each:

- **Local Claude Code** — point Glideship at a host `claude login` session. Pro / Max flat-rate, no per-token bills, codebase-aware.
- **Cloud Claude via API key** — paste an `sk-ant-…` into **Settings → AI Configuration → Claude Code**. Pay-per-token, recommended for evaluators and CI.
- **Anthropic direct API** — for the lightweight non-codebase agents (Triage, Bug-Linker, Standup). Lower latency and lower per-call cost than going through Claude Code.

See [AI Engines & MCP Server](ai-engines.md) for the engine-by-engine breakdown.

## One-machine self-host

A single laptop or Mac Mini runs the whole platform — frontend, backend, multiplayer, Postgres, Redis. A **Cloudflare Tunnel** optionally exposes just the Slack / GitHub webhook endpoints without putting the rest of the stack online. This makes Glideship a credible **self-hosted Jira alternative** for teams that don't want to live on per-seat SaaS.

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

Glideship ships in **two deployment modes**. The product is identical, only the process boundary between your host and the containers changes.

| Mode | What runs in Docker | What runs on your host | Claude auth |
|---|---|---|---|
| **Full Docker** | postgres, redis, **backend**, multiplayer, frontend | nothing | Anthropic API key (entered in Settings → AI Configuration) |
| **Hybrid** | postgres, redis only (infra) | backend, multiplayer, frontend via `npm run dev` | The host's existing `claude login` session (Claude Pro/Max subscription) |

**Pick Full Docker** for a one-command "evaluator" setup, a dedicated Mac-mini deployment, or any case where you'd rather pay-per-token via Anthropic's API than wire up a Claude subscription. **Pick Hybrid** if you already run `claude` interactively on your laptop and want agents to use that same flat-rate subscription, or you want hot-reload for development.

### Fastest: one command with `npx` (no clone, no build)

The quickest way to try Glideship. The [`glideship`](https://www.npmjs.com/package/glideship) npm package pulls prebuilt images from Docker Hub and runs the full Full-Docker stack — you don't clone the repo or build anything.

```bash
npx glideship init     # detect ports, generate secrets, pull images
cd glideship
npx glideship start     # start everything and open the setup wizard
```

`init` writes this install's secrets, including the key that encrypts employee records (`HR_ENCRYPTION_KEYS`), to `bodhiorchard/.env`. Back that file up with your data: records encrypted with its key can't be read without it. Installs from before the key existed get one on their next `start` or `update`.

Needs only **Docker (running)** and **Node.js 22+**. If Postgres (5432) or Redis (6379) — or an app port — is already in use, the installer detects it and asks whether to **remap to a free port** or **reuse the existing service**. When the stack is healthy it opens **http://localhost:3000/setup**; finish there (organization, admin account, AI provider, repositories). No keys are entered on the command line.

Manage the stack with these commands (run from the install directory):

| Command | What it does |
|---|---|
| `glideship init [name]` | Scaffold the install: resolve ports, generate secrets, pull images |
| `glideship start` | Start the stack and open the setup wizard |
| `glideship stop` | Stop the stack — **containers come down, your data volumes are kept** |
| `glideship status` | Show container status and the access URLs |
| `glideship logs [service]` | Follow logs (optionally for one service) |
| `glideship update [--tag X.Y.Z]` | Pull newer images and restart |
| `glideship reset` | Stop **and delete all data volumes** (destructive) |

To stop everything when you're done, run `glideship stop` (your database and cloned repos persist; `glideship start` brings it back up). It's the same stack as **Full Docker mode** below — just pulled instead of built. Use the `git clone` paths below if you want to build from source or run in **Hybrid** mode.

### Prerequisites

- **Full Docker**: Docker Desktop ≥ 4.20 (everything else is in containers)
- **Hybrid**: Docker + Node.js 24+ + Python 3.12+ + a host-installed, already-logged-in [Claude Code CLI](https://code.claude.com/docs/en/setup)
- Windows: use WSL2 for either mode
- (Optional) Cloudflare account for tunnel — needed for Slack/GitHub webhooks

### Full Docker mode (one command)

```bash
git clone https://github.com/mickyarun/glideship.git
cd glideship
docker compose up
```

Open **http://localhost:3000**. Postgres, Redis, backend, multiplayer, and frontend all start together. Migrations run automatically on backend startup. First build takes ~5 min (the backend image installs git, Node.js 24, and the `@anthropic-ai/claude-code` npm package); subsequent runs are instant.

Once the UI is up:

1. Complete first-time setup (org name, admin user, source repo path).
2. Go to **Settings → AI Configuration → Claude Code**.
3. Choose **API key (Full Docker)**, paste an `sk-ant-…` key from [console.anthropic.com](https://console.anthropic.com/settings/keys), and **Save**.
4. Click **Test connection** — it should report the CLI version and a successful round-trip.

The key is encrypted (Fernet AES-128) in Postgres and pushed into the backend's process env on save, so every subsequent agent run inherits it. No compose-level env var required.

#### Secrets in Full Docker

You don't set any. On first start the backend generates this install's own `SECRET_KEY` (signs sign-ins), `ENCRYPTION_KEY` (encrypts stored tokens such as the Claude, Slack, GitHub and Jira keys), `HR_ENCRYPTION_KEYS` (encrypts employees' bank and ID details and documents) and `COLYSEUS_BRIDGE_SECRET` (shared with the multiplayer server), and keeps them in the `secrets_data` volume so they survive rebuilds. Setting any of them in your environment overrides the generated one.

Installs from before per-install keys had their stored tokens encrypted under a shared default key. Every start re-encrypts anything still under that old key, so the first start after updating moves them all over (and signs everyone out once). A token that can't be read with any key is listed in the log; save it again in Settings. Scripts run with `docker compose exec backend python -m scripts...` use the same generated keys as the server.

Keep the `secrets_data` volume with your database: without its `encryption_key` the stored tokens can't be read, and without its `hr_encryption_keys` the employee records can't. `docker compose down -v` deletes it.

### Hybrid mode (hot reload)

```bash
git clone https://github.com/mickyarun/glideship.git
cd glideship
npm install        # frontend + multiplayer deps via workspaces
npm run setup      # Python venv, .env files, infra, migrations
npm run dev        # backend + frontend + multiplayer, one terminal
```

- **Frontend**: http://localhost:3000 (Vite, hot reload)
- **Backend**: http://localhost:8000/docs (FastAPI, `--reload`)
- **Multiplayer**: ws://localhost:2567 (Colyseus)

Only `postgres` and `redis` run in Docker (via `docker-compose.infra.yml`). The backend process inherits your shell environment — including whatever `claude login` has authenticated on your host — so agent runs use your Claude subscription automatically. In **Settings → AI Configuration → Claude Code**, leave the auth mode on **Hybrid / host login** (the default).

`npm run setup` also adds an `HR_ENCRYPTION_KEYS` line to `backend/.env` if there isn't one, so employee records can be encrypted. Keep that file: records encrypted with its key can't be read without it.

All three host processes run in a single terminal with color-coded logs. Ctrl-C stops them; `npm run stop` tears down the infra containers.

### Switching between modes

The database is the same shape either way, so you can swap modes against the same data. Stop the current mode first (`Ctrl-C` + `npm run stop` for Hybrid, `docker compose down` for Full Docker), then start the other. The stored `claude_auth_mode` on your organization determines which path agent runs take — update it in Settings when you switch.

Going from Full Docker to Hybrid, give the host backend the same `ENCRYPTION_KEY`, or the tokens Full Docker stored can't be read. Copy it into `backend/.env` (skip this if you set `ENCRYPTION_KEY` yourself):

```bash
key=$(docker compose run --rm --no-deps --entrypoint cat backend /data/secrets/encryption_key) && [ -n "$key" ] && echo "ENCRYPTION_KEY=$key" >> backend/.env
```

Do the same for employee records, or the ones stored in Full Docker can't be read. This puts Full Docker's HR key first in `backend/.env` and keeps the one setup generated after it, so records saved under either stay readable. Running it twice changes nothing:

```bash
key=$(docker compose run --rm --no-deps --entrypoint cat backend /data/secrets/hr_encryption_keys) && [ -n "$key" ] && old=$(sed -n 's/^HR_ENCRYPTION_KEYS=//p' backend/.env) && case ",$old," in *",$key,"*) ;; *) grep -v '^HR_ENCRYPTION_KEYS=' backend/.env > backend/.env.new && echo "HR_ENCRYPTION_KEYS=$key${old:+,$old}" >> backend/.env.new && mv backend/.env.new backend/.env ;; esac
```

The other way round, give Full Docker both keys, the one from `backend/.env` first, so the records stored in either mode stay readable. Set `HR_ENCRYPTION_KEYS` in the environment you start Full Docker with to `<the value in backend/.env>,<the contents of /data/secrets/hr_encryption_keys>`. A value in the environment replaces the generated key rather than adding to it. Stored tokens need nothing: tokens saved in Hybrid under the default key are re-encrypted on the next Full Docker start.

## Try the included examples

Glideship pairs with **TaskFlow** — four deliberately wired-together sample repos that exercise cross-repo feature detection, skill profiling, BUD generation, and PR-merge feature reconciliation without you needing to wire up your own codebase:

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

**2. In the Glideship UI, add the four repos under Settings → Repositories:**

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
