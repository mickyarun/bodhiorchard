<div align="center">

# Bodhiorchard&trade;

### AI-Native Software Development Operations Platform

**Replace Agile ceremonies with intelligent agents. Powered by AI. Runs on your machine.**

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)](https://fastapi.tiangolo.com)
[![Vue 3](https://img.shields.io/badge/Vue.js-3-4FC08D.svg)](https://vuejs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791.svg)](https://www.postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)](https://www.docker.com)

[Getting Started](#getting-started) | [How It Runs](#how-it-runs) | [AI Engines](#ai-engines) | [AI Agents](#ai-agents) | [API](#api) | [Roadmap](#roadmap) | [License](#license)

</div>

---

<div align="center">

> 📺 **[Watch the 90-second demo](https://placeholder-demo-video-url)** &nbsp;<!-- TODO: replace with the real Loom / YouTube URL -->

![Bodhiorchard Living Tree Dashboard](docs/images/dashboard.png) <!-- TODO: drop a real hero screenshot at docs/images/dashboard.png -->

</div>

---

## What is Bodhiorchard?

Bodhiorchard is an **open-source, AI-first alternative to Agile project management tools** like Jira, Linear, and Shortcut. It runs locally on your laptop or Mac Mini with **12 specialized AI agents** that orchestrate the entire software development lifecycle — from feature intake to production deployment, learning, and continuous improvement. It's powered today by [**Claude Code**](https://docs.anthropic.com/en/docs/claude-code) for codebase-aware intelligence and the **Anthropic direct API** for lighter, non-codebase agent calls; [**Ollama**](https://ollama.com) (fully local/free), the **OpenAI** direct API, and **OpenAI Codex** are on the near-term roadmap.

### The Problem

Traditional Agile tools create busywork: manual ticket creation, estimation poker, status updates, retrospective meetings, and scattered documentation across Jira, Confluence, Notion, and Slack. Developers spend more time managing work than doing work.

### The Solution

Bodhiorchard replaces human busywork with AI automation while keeping humans in control of decisions that matter:

| What Changes | Agile / Jira | Bodhiorchard |
|---|---|---|
| **Feature Intake** | Manual ticket creation, sprint planning | Slack message triggers AI triage with duplicate detection and priority scoring |
| **Estimation** | Story points, planning poker | AI predicts cycle time from historical data (85% confidence) |
| **Specification** | PM writes PRD manually | BUD Agent generates spec with codebase context, enterprise rules, prior art |
| **Design** | Designer hands off static specs | Design Agent scopes components, captures Figma reviews via MCP |
| **Development** | Dev picks up ticket, starts from scratch | AI implements from tech plan, dev does code review |
| **Testing** | QA writes test cases manually | Auto-generated test plans (unit, integration, e2e, perf, security, UAT) |
| **Deployment** | Manual status updates | Webhook-driven status tracking, auto-notifications |
| **Learning** | Post-mortems after incidents | Continuous learning after every deployment — patterns, retrospectives, skill growth |

---

## Key Features

### BUD (Business Understanding Document) — Single Source of Truth

Every feature lives in one **BUD** — spec, tech spec, test plan, acceptance criteria, and full history. Replaces scattered Jira tickets, Google Docs, and Notion pages.

```
BUD Lifecycle: bud -> design -> tech_arch -> development -> testing -> uat -> prod -> closed
                                                                                |
                                                                      discarded (any time)
```

- Markdown-based with separate sections for spec, tech spec, and test plan
- Vector-indexed for semantic search by all agents
- Full history: stage transitions, assignees, reopens, linked bugs
- Auto-numbered per organization (BUD-001, BUD-002, ...)

### Living Tree Dashboard

A **3D interactive visualization** of your organization rendered as a living tree:

- **Trunk** = Organization
- **Limbs** = Repositories
- **Branches** = Code communities (auto-detected)
- **Leaves** = Recent files (color = "freshness" from git activity)

Hover for developer details, click for drill-down, watch the tree grow as your codebase evolves.

### Developer Skill Profiling

Automatic skill tracking from git history — no manual profile updates:

- Per-developer, per-module expertise scores (0-1.0)
- Bus factor alerts (modules touched by only one person)
- Intelligent task routing based on expertise match + capacity
- Daily profile rebuilds from git commits, BUD assignments, and bug fixes

### Slack-Native Feature Intake

Submit features directly from Slack. The Triage Agent conducts a structured interview:

1. User posts in `#feature-requests`
2. AI asks clarifying questions in a thread
3. Checks for duplicates via vector search
4. Estimates complexity from codebase analysis
5. Suggests priority with capacity check
6. PM approves in the Bodhiorchard UI
7. BUD Agent generates the full specification

### Multi-Repo Code Intelligence

Powered by an in-tree code-graph indexer (`backend/app/services/code_indexer/`)
built on the MIT-licensed [graphify](https://github.com/safishamsi/graphify)
library — tree-sitter parsing → NetworkX graph → Leiden community detection:

- Scan repositories to build a per-repo knowledge graph of code relationships
- Auto-synthesize feature descriptions from code clusters
- Cross-repo feature deduplication and merging
- Semantic search across all indexed code and documentation
- Impact / blast-radius queries via the `code_*` MCP tool group

### Claude Code-Native (MCP)

Bodhiorchard exposes **10 MCP tools** to [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and other MCP-compatible clients — see [AI Engines](#ai-engines) below for the full tool list, dual-auth modes, and registration instructions.

### Enterprise-Grade Security

- **Multi-tenant isolation** — all queries scoped to organization
- **RBAC** with 9 built-in roles and granular permissions
- **AES encryption at rest** for GitHub PATs, Slack tokens, and secrets
- **JWT authentication** with refresh tokens
- **Audit trail** — every agent action logged with full context

---

## How It Runs

Bodhiorchard splits cleanly into two planes so you can pick how much of it lives on your hardware.

### The data plane is always local

Postgres + pgvector, every BUD, the embeddings index, the scanned repos, the agent skills, and the audit log all sit on your machine. Nothing in this plane ever calls home — even when you choose cloud inference, the data the agents reason over stays on your hardware.

### Inference is your call

Three first-class modes, three reasons to pick each:

- **Local Claude Code** — point Bodhiorchard at a host `claude login` session. Pro / Max flat-rate, no per-token bills, codebase-aware.
- **Cloud Claude via API key** — paste an `sk-ant-…` into **Settings → AI Configuration → Claude Code**. Pay-per-token, recommended for evaluators and CI.
- **Anthropic direct API** — for the lightweight non-codebase agents (Triage, Bug-Linker, Standup). Lower latency and lower per-call cost than going through Claude Code.

See [AI Engines](#ai-engines) for the engine-by-engine breakdown.

### One-machine self-host

A single laptop or Mac Mini runs the whole platform — frontend, backend, multiplayer, Postgres, Redis. A **Cloudflare Tunnel** optionally exposes just the Slack / GitHub webhook endpoints without putting the rest of the stack online. This makes Bodhiorchard a credible **self-hosted Jira alternative** for teams that don't want to live on per-seat SaaS.

### What you get

- **Lower cost than per-seat SaaS** — no platform-compute bills; pay only for whichever inference engine you wire up (or flat-rate if you're on a Claude subscription).
- **Lower energy footprint** — a Mac Mini idles around 10W vs hundreds of watts for cloud VMs.
- **Data residency by default** — code, BUDs, embeddings, and knowledge stay on your hardware even when inference is in the cloud.

### System diagram

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
  │          │                │              │     │ (10 tools)│
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

---

## AI Engines

Bodhiorchard is **AI-engine-agnostic**. The agent layer is engine-independent — adding a new engine is API rewiring only, no deployment changes. Today: Claude Code + the Anthropic direct API. Next: Ollama (air-gapped), OpenAI, OpenAI Codex.

### Today — Claude Code (codebase-aware agents)

Codebase-aware agent runs (BUD spec, Tech Plan, Implementation, Code Review) are executed by the Claude Code CLI, which gives agents file access, shell tool-use, and direct access to Bodhiorchard's MCP server.

**Why Claude Code (and not just the raw API):**

- **Codebase awareness out of the box** — Claude Code already knows how to read files, run shell commands, and edit code; Bodhiorchard reuses that surface area instead of re-implementing it.
- **Token-efficient by default** — agent prompts use Anthropic prompt caching, structured tool-use, and incremental context loading. The cost per BUD stays low even on long sessions.
- **One runtime, two billing models** — point Bodhiorchard at an Anthropic API key (pay-per-token) **or** at a host `claude login` session backed by a Claude Pro / Max subscription (flat-rate). Same agents either way.

**Authentication modes:**

| Mode | When the org uses this | Where the credential lives |
|---|---|---|
| `api_key` | Full Docker deployments, or any host that doesn't have a Claude subscription | `sk-ant-…` key encrypted in Postgres (Fernet AES-128) and pushed into the backend's process env on save |
| `hybrid_host` | Hybrid deployments where the developer already runs `claude` interactively | Host's existing `claude login` session — nothing stored in the database |

The backend auto-detects which mode is available (via `/.dockerenv`) and the Settings page only surfaces the option that actually works for that deployment.

### Today — Anthropic direct API (lightweight non-codebase agents)

Triage, Bug-Linker, and Standup don't need to read files — they reason over chat messages, bug reports, and aggregated activity. For those, Bodhiorchard skips Claude Code and calls the Anthropic API directly. Lower latency, lower per-call cost, same `sk-ant-…` key (configured at **Settings → AI Configuration → Anthropic API**).

### Coming soon

| Engine | Status |
|---|---|
| **Ollama** (fully local, free, air-gapped) | Planned |
| **OpenAI** API (GPT-4o / 4 / 3.5) | Planned |
| **OpenAI Codex** | In development |

These will appear as additional presets in the AI Configuration page — API rewiring only, no deployment changes.

### MCP server — the 10 tools Bodhiorchard exposes to Claude Code

Bodhiorchard runs an MCP server on `:8001` that exposes 10 tools to Claude Code. They split into two groups:

**BUD / repo intelligence**

| Tool | Purpose |
|---|---|
| `get_bud_context` | Retrieve existing BUDs for context |
| `write_bud` | Create or update a BUD document |
| `get_knowledge` | Search feature registry and knowledge base |
| `write_feature_registry` | Save synthesized features |
| `check_feature_exists` | Deduplicate before creating |
| `search_bugs` | Find related bugs |
| `update_task_status` | Report progress back to Bodhiorchard |
| `post_slack_message` | Send messages to Slack |
| `get_team_context` | Get team capacity and skills |
| `get_pending_features` | Get next batch for synthesis |

**Code graph (`code_*` tool group)** — an in-tree code-graph indexer also exposes `code_impact`, `code_query`, `code_context`, `code_community`, `code_god_nodes`, and `code_stats` for impact / blast-radius analysis before refactors.

### Registering Bodhiorchard's MCP server in your own Claude Code

Add an entry to `~/.claude.json` (or use `claude mcp add`):

```json
{
  "mcpServers": {
    "bodhiorchard": {
      "type": "http",
      "url": "http://localhost:8001/mcp"
    }
  }
}
```

Restart Claude Code and the `bodhiorchard__*` tools will appear in tool-use. Pair this with the [Claude Code skills](https://docs.anthropic.com/en/docs/claude-code/skills) that ship in `backend/app/agents/skills/` to drive Bodhiorchard's agents from a regular `claude` session on your laptop.

---

## AI Agents

Bodhiorchard ships with **12 specialized agents**, each triggered automatically and connected to each other:

### Intake & Planning

| Agent | Trigger | What It Does |
|---|---|---|
| **Triage Agent** | Chat / Slack event | Interviews users, checks capacity, finds duplicates, estimates complexity, suggests priority |
| **BUD Agent** | PM approval | Generates full BUD with codebase context, enterprise rules, prior art, and competitor analysis |

### Design & Development

| Agent | Trigger | What It Does |
|---|---|---|
| **Design Agent** | BUD approved | Scopes UI/UX requirements, generates component breakdowns and interaction specs |
| **Tech Plan Agent** | BUD enters Tech Arch | Creates file-level implementation TODOs with architecture analysis and dependency mapping |
| **Smart Assignment Agent** | Tech plan approved | Suggests best-fit developer from per-module skill profiles (0–1.0) and real-time capacity; manager reviews if present, otherwise auto-assigns |
| **Status Agent** | GitHub webhook | Detects PR merges, infers status from branches, moves BUD folders, notifies stakeholders |
| **Standup Agent** | Daily cron (08:30) | Aggregates git/PR/bug/chat activity into daily summaries with risk flag detection |

### Testing & Quality

| Agent | Trigger | What It Does |
|---|---|---|
| **Test Plan Agent** | Dev complete | Auto-generates Playwright e2e, unit/integration tests, manual UAT cases, and security tests |
| **Bug Linker Agent** | New bug filed | Links bugs to BUDs via vector search, monitors thresholds, triggers reassignment |
| **Reassignment Agent** | Bug threshold exceeded | Reassigns devs to bug review, rotates QA, rebalances workloads |

### Post-Deploy & Continuous

| Agent | Trigger | What It Does |
|---|---|---|
| **Learning Agent** | BUD deployed | Cycle time analysis, estimate vs actual comparison, pattern matching, retrospective generation |
| **Skill Agent** | Daily cron (02:00) | Rebuilds skill profiles from git/BUD/bug history, scores 0-1.0, detects bus factor risks |

Every agent logs actions to an audit trail, uses the organization's configured LLM provider, and can be monitored in the UI.

---

## Architecture

### Tech Stack

**Backend**
- Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async)
- PostgreSQL 16 with pgvector for vector search
- Redis for caching and job queues
- fastembed for local embeddings (BAAI/bge-small-en-v1.5 by default)
- Alembic for database migrations
- structlog for structured JSON logging

**Frontend**
- Vue 3 (Composition API) / TypeScript 5.3
- Vuetify 3 (Material Design component library)
- Pinia for state management
- Three.js for 3D tree visualization
- Axios with auth interceptor

**AI & Infrastructure**
- Claude Code as the sole AI engine today (authenticated via API key in Full Docker, or host `claude login` in Hybrid)
- Docker + Docker Compose on a local machine or Mac Mini
- Cloudflare Tunnel for exposing webhooks to Slack / GitHub / internet
- Anthropic direct API live for non-codebase agents; Ollama / OpenAI / Codex integrations planned (see [AI Engines → Coming soon](#ai-engines))

### Project Structure

```
bodhiorchard/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # REST API endpoints
│   │   ├── agents/          # AI agent orchestration & skill definitions
│   │   ├── core/            # Auth, security, dependencies
│   │   ├── mcp/             # Model Context Protocol server
│   │   ├── models/          # SQLAlchemy ORM models
│   │   ├── repositories/    # Data access layer (org-scoped)
│   │   ├── schemas/         # Pydantic request/response DTOs
│   │   └── services/        # Business logic (LLM, scanning, synthesis)
│   ├── alembic/             # Database migrations
│   ├── entrypoint.sh        # Runs migrations then uvicorn
│   └── Dockerfile           # Multi-stage production build
│
├── frontend/
│   ├── src/
│   │   ├── views/           # Page components
│   │   ├── components/      # Reusable UI (tree visualization, cards)
│   │   ├── stores/          # Pinia state management
│   │   ├── types/           # TypeScript interfaces
│   │   └── data/            # Shared data (agent definitions)
│   └── package.json
│
├── multiplayer/             # Colyseus multiplayer server (TypeScript)
├── scripts/                 # setup.sh, wait-for-postgres.sh
├── docker-compose.yml       # Full stack: postgres + redis + backend + fe + mp
├── docker-compose.infra.yml # Contributor infra only: postgres + redis
├── package.json             # npm workspaces + dev scripts (root)
├── BODHIORCHARD-ARCHITECTURE.md  # Comprehensive architecture spec (8400+ lines)
├── AGENTS.md                # Agent capabilities documentation
├── TODO.md                  # Roadmap and progress tracking
└── LICENSE                  # Apache-2.0
```

---

## Getting Started

Bodhiorchard ships in **two deployment modes**. Pick the one that matches how you want to run it — the product is identical, only the process boundary between your host and the containers changes.

| Mode | What runs in Docker | What runs on your host | Claude auth |
|---|---|---|---|
| **Full Docker** | postgres, redis, **backend**, multiplayer, frontend | nothing | Anthropic API key (entered in Settings → AI Configuration) |
| **Hybrid** | postgres, redis only (infra) | backend, multiplayer, frontend via `npm run dev` | The host's existing `claude login` session (Claude Pro/Max subscription) |

**Pick Full Docker** for a one-command "evaluator" setup, a dedicated Mac-mini deployment, or any case where you'd rather pay-per-token via Anthropic's API than wire up a Claude subscription. **Pick Hybrid** if you already run `claude` interactively on your laptop and want agents to use that same flat-rate subscription, or you want hot-reload for development.

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

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://bodhiorchard:bodhiorchard@localhost:5432/bodhiorchard` |
| `SECRET_KEY` | JWT signing key | `change-me-in-production` |
| `ENCRYPTION_KEY` | AES key for secrets at rest (used to encrypt the Claude API key, Slack tokens, GitHub private keys) | (generated) |
| `ANTHROPIC_API_KEY` | Optional process-level fallback for Claude auth. Ignored when an org-level key is configured in Settings. | (unset) |
| `LLM_PROVIDER` | LLM provider (for non-codebase agents) | `ollama` |
| `LLM_MODEL` | LLM model name | `llama3:8b` |
| `EMBEDDING_PROVIDER` | Embedding provider | `ollama` |
| `EMBEDDING_MODEL` | Embedding model | `nomic-embed-text` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379` |
| `SLACK_BOT_TOKEN` | Slack bot token | (optional) |
| `GITHUB_PAT` | GitHub personal access token | (optional) |

---

## API

Bodhiorchard exposes three programmable surfaces. All three run on the same host as the backend.

| Surface | Port | What it's for |
|---|---|---|
| **REST** | `:8000/api/v1` | Day-to-day CRUD: BUDs, orgs, repos, skills, triage, Slack/GitHub webhooks. FastAPI; interactive docs at [/docs](http://localhost:8000/docs) (Swagger) and [/redoc](http://localhost:8000/redoc). |
| **MCP** | `:8001/mcp` | 10 tools for Claude Code and other MCP clients — see [AI Engines](#ai-engines) above. |
| **WebSocket** | `:8000/ws/jobs/{job_id}` | Live progress for async jobs (repo scans, BUD generation, etc.). Frontend uses `useJobSocket`; CLI consumers can use `wscat`. |

### Key REST endpoints

| Endpoint | Description |
|---|---|
| `POST /api/v1/auth/login` | JWT authentication |
| `GET /api/v1/buds` | List BUD documents |
| `POST /api/v1/buds` | Create a new BUD |
| `GET /api/v1/dashboard/tree-data` | 3D Living-Tree visualization data |
| `GET /api/v1/skills/profiles` | Developer skill profiles |
| `POST /api/v1/skills/scan` | Trigger repository scan (returns `202` + `job_id`) |
| `GET /api/v1/triage-sessions` | Triage approval queue |
| `POST /api/v1/slack/events` | Slack webhook handler |

### Example: create a BUD via `curl`

```bash
curl -X POST http://localhost:8000/api/v1/buds \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Add export-to-PDF on the dashboard",
    "stage": "bud",
    "summary": "Users want to share weekly dashboard snapshots with leadership."
  }'
```

### Async-job pattern

Long-running operations (repo scans, embedding builds, BUD generation) return `202 Accepted` with a `job_id`. Subscribe to `ws://localhost:8000/ws/jobs/{job_id}` for progress events instead of polling the REST endpoint.

---

## Screenshots

<!--
  Drop real PNGs at the paths below and they'll render here automatically.
  Suggested width: 1600px. Suggested filenames are deliberate — the landing page reuses them.
-->

| Living Tree dashboard | BUD board | Slack triage |
|---|---|---|
| ![Living Tree dashboard](docs/images/screenshot-tree.png) | ![BUD board](docs/images/screenshot-bud-board.png) | ![Slack triage](docs/images/screenshot-slack-triage.png) |

> Screenshots are placeholders for now — the broken-image icons disappear once `docs/images/screenshot-*.png` files land.

---

## Integrations

| Integration | Status | Description |
|---|---|---|
| **Claude Code** | Core | AI backbone — runs codebase-aware agents via MCP (10 tools). API key in Full Docker, host `claude login` in Hybrid. |
| **Slack** | Supported | Feature intake, triage conversations, notifications (via Cloudflare Tunnel) |
| **GitHub** | Supported | PR merge detection, branch status, deploy-key cloning of private repos |
| **Ollama** | Coming soon | Local LLM inference — free, private, no API keys needed |
| **Anthropic API** | Supported | Direct Claude API for non-codebase agents (bypasses Claude Code MCP) |
| **OpenAI API** | Coming soon | Alternative cloud LLM provider |
| **OpenAI Codex** | In development | Code-specialized agent tasks |
| **Figma** | Planned | Design review capture via MCP |
| **Linear** | Planned | Bidirectional sync |

---

## Roadmap

### Phase 1 (Current)
- [x] Core platform (auth, multi-tenant, RBAC)
- [x] BUD lifecycle management
- [x] Feature registry with vector search
- [x] Repository scanning and code intelligence
- [x] Developer skill profiling
- [x] 3D tree dashboard visualization
- [x] Slack-native triage intake
- [x] MCP server with 10 tools
- [x] 12 AI agent definitions

### Phase 2 (Next)
- [ ] Agent execution engine (autonomous agent runs)
- [ ] Real-time Slack bot conversations
- [ ] GitHub webhook processing pipeline
- [ ] Automated test generation from BUDs
- [ ] CI/CD integration

### Phase 3 (Future)
- [ ] Multi-org marketplace
- [ ] Custom agent builder
- [ ] Analytics and reporting dashboards
- [ ] Mobile companion app
- [ ] Plugin ecosystem

---

## Contributing

We welcome contributions! Please read our contributing guidelines before submitting a pull request.

### Development Setup

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run linting: `ruff check . --fix && ruff format .` (backend) / `npm run lint` (frontend)
5. Run type checking: `mypy app/` (backend) / `npx vue-tsc --noEmit` (frontend)
6. Commit your changes
7. Push to your branch and open a Pull Request

### Contributor sign-off (DCO)

By contributing to this project, you agree to license your contribution under the Apache License, Version 2.0, and you certify your right to do so under the [Developer Certificate of Origin](https://developercertificate.org/). All commits must be signed off with `git commit -s` — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

Bodhiorchard&trade; is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text and [NOTICE](NOTICE) for attribution and independence declarations.

Commercial licenses with additional support and proprietary integrations may be made available separately — contact the maintainer.

## Why "Bodhiorchard"?

<div align="center">
<em>"The purpose of technology is not to keep humans chained to screens, but to set them free."</em>
</div>

<br>

**Bodhi** (Sanskrit/Pali: "awakening, enlightenment") is the state of understanding that the Buddha attained under the Bodhi tree. **Orchard** is a cultivated grove &mdash; trees tended with intention so they can bear fruit.

The name carries a deeper belief about what AI should do for us.

The software industry has a paradox: we build tools to make life better, but the process of building them consumes our lives. Developers work late nights. PMs spend weekends writing specs. Teams sit through hours of ceremonies — standups, sprint planning, retrospectives, estimation poker — rituals that were meant to help but became the work itself.

Bodhiorchard exists because **AI should give humans their time back**.

Not to write more code. Not to ship faster. But to reclaim the hours lost to busywork — so a developer can leave at 5pm and take their kid to the park. So a PM can spend their morning thinking deeply about what users need instead of copy-pasting Jira tickets. So a team lead can mentor junior engineers instead of chasing status updates across five tools.

The 3D tree dashboard isn't just a visualization — it's the philosophy made visible. Your organization is a living orchard. Each repository is a tree. Each feature is a branch. The AI agents are the orchardists: they water, they prune, they tend the soil. They do the repetitive labor so the trees can grow naturally and bear fruit, and the humans who planted them can step back, breathe, and enjoy the harvest they've built.

The Bodhi tree is where awakening happened — not through more effort, but through stillness and clarity. Bodhiorchard is an invitation to build software the same way: let the machines handle the noise, so humans can focus on what actually matters.

Build well. Then go outside.

---

<div align="center">

**Built by [Arun Rajkumar](https://github.com/mickyarun)**

If Bodhiorchard helps your team, give it a star and spread the word.

<sub>&copy; 2025-2026 Arun Rajkumar. Bodhiorchard&trade; is a trademark of Arun Rajkumar.</sub>

<sub>Independent open-source project — not affiliated with any employer or client.</sub>

</div>
