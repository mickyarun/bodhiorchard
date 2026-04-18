<div align="center">

# Bodhiorchard

### AI-Native Software Development Operations Platform

**Replace Agile ceremonies with intelligent agents. Powered by AI. Runs on your machine.**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688.svg)](https://fastapi.tiangolo.com)
[![Vue 3](https://img.shields.io/badge/Vue.js-3-4FC08D.svg)](https://vuejs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791.svg)](https://www.postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)](https://www.docker.com)

[Getting Started](#getting-started) | [Architecture](#architecture) | [AI Agents](#ai-agents) | [MCP Integration](#model-context-protocol-mcp) | [Roadmap](#roadmap) | [Commercial License](#license)

</div>

---

## What is Bodhiorchard?

Bodhiorchard is an **open-source, AI-first alternative to Agile project management tools** like Jira, Linear, and Shortcut. It runs locally on your laptop or Mac Mini with **11 specialized AI agents** that orchestrate the entire software development lifecycle — from feature intake to production deployment, learning, and continuous improvement. Choose your AI engine: [**Claude Code**](https://docs.anthropic.com/en/docs/claude-code) for codebase-aware intelligence, [**Ollama**](https://ollama.com) for fully local/free inference, or cloud APIs from **Anthropic** and **OpenAI** — mix and match per agent.

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

### BUD (Build-Up Document) — Single Source of Truth

Every feature lives in one **BUD** — spec, tech spec, test plan, acceptance criteria, and full history. Replaces scattered Jira tickets, Google Docs, and Notion pages.

```
BUD Lifecycle: bud -> design -> development -> testing -> uat -> prod -> closed
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

Powered by **GitNexus** code graph analysis:

- Scan repositories to build a knowledge graph of code relationships
- Auto-synthesize feature descriptions from code clusters
- Cross-repo feature deduplication and merging
- Semantic search across all indexed code and documentation

### Model Context Protocol (MCP) Integration

Bodhiorchard exposes **10 MCP tools** for Claude Code and other MCP-compatible AI assistants:

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

### Enterprise-Grade Security

- **Multi-tenant isolation** — all queries scoped to organization
- **RBAC** with 9 built-in roles and granular permissions
- **AES encryption at rest** for GitHub PATs, Slack tokens, and secrets
- **JWT authentication** with refresh tokens
- **Audit trail** — every agent action logged with full context

---

## AI Agents

Bodhiorchard ships with **11 specialized agents**, each triggered automatically and connected to each other:

### Intake & Planning

| Agent | Trigger | What It Does |
|---|---|---|
| **Triage Agent** | Chat / Slack event | Interviews users, checks capacity, finds duplicates, estimates complexity, suggests priority |
| **BUD Agent** | PM approval | Generates full BUD with codebase context, enterprise rules, prior art, and competitor analysis |

### Design & Development

| Agent | Trigger | What It Does |
|---|---|---|
| **Design Agent** | BUD approved | Scopes UI/UX requirements, generates component breakdowns and interaction specs |
| **Tech Plan Agent** | BUD approved | Creates file-level implementation TODOs with architecture analysis and dependency mapping |
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

### Runs on Your Machine — Not in the Cloud

Bodhiorchard is designed to run **locally on your laptop or a Mac Mini** sitting under your desk. No expensive cloud servers. No per-seat SaaS subscriptions. One machine runs the entire platform — AI agents, database, vector search, and all.

Need Slack integration or internet access? A **Cloudflare Tunnel** exposes just the webhook endpoints — your data stays on your hardware while the world can talk to it. This means:

- **Dramatically lower cost** — no cloud compute bills, no per-user pricing
- **Lower energy footprint** — a Mac Mini uses ~10W idle vs hundreds of watts for cloud VMs
- **Your data stays local** — code, BUDs, and knowledge never leave your machine
- **Offline-capable** — with Ollama, everything works without internet

### AI Configuration — 4 Presets, Your Choice

Bodhiorchard uses [**Claude Code**](https://docs.anthropic.com/en/docs/claude-code) as its core AI engine for codebase-aware agents (Tech Plan, Test Plan, BUD generation). For other agents, you choose the provider. The Settings page offers four presets:

| Preset | Codebase Agents | Other Agents | Best For |
|---|---|---|---|
| **Hybrid** (recommended) | Claude Code | Anthropic or OpenAI API | Best quality — local code intelligence + cloud reasoning |
| **Claude + Ollama** | Claude Code | Ollama (local) | Privacy-first — cloud only for code, everything else local |
| **Cloud API** | Anthropic or OpenAI | Anthropic or OpenAI | Teams already paying for API access |
| **Local (Ollama)** | Ollama | Ollama | Fully offline — zero API keys, zero cost, full privacy |

**Supported LLM providers:**

| Provider | Models | Cost |
|---|---|---|
| **Ollama** | llama3, nomic-embed-text, and any GGUF model | Free (your hardware) |
| **Anthropic** | Claude Opus, Sonnet, Haiku via Claude Code + API | Pay-per-use |
| **OpenAI** | GPT-4o, GPT-4, GPT-3.5 via fastembed | Pay-per-use |
| **OpenAI Codex** | Code-specialized models | Under development |

Start free with Ollama. Add Claude Code for codebase intelligence. Upgrade to cloud APIs when you need them.

### System Diagram

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
  │  ┌───────▼───┐  ┌────────▼──┐  ┌────────▼──┐  │           │
  │  │PostgreSQL  │  │  Redis    │  │  Ollama   │  │           │
  │  │+ pgvector  │  │  Cache    │  │(local LLM)│  │           │
  │  └───────────┘  └───────────┘  └───────────┘  │           │
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

### Tech Stack

**Backend**
- Python 3.12+ / FastAPI / SQLAlchemy 2.0 (async)
- PostgreSQL 16 with pgvector for vector search
- Redis for caching and job queues
- fastembed for multi-provider LLM access (Ollama, OpenAI, Anthropic)
- Alembic for database migrations
- structlog for structured JSON logging

**Frontend**
- Vue 3 (Composition API) / TypeScript 5.3
- Vuetify 3 (Material Design component library)
- Pinia for state management
- Three.js for 3D tree visualization
- Axios with auth interceptor

**AI & Infrastructure**
- Claude Code as the core AI engine for codebase-aware agents (via MCP)
- Ollama for local LLM inference (no API keys needed to start)
- fastembed for multi-provider LLM access (Anthropic, OpenAI, Ollama)
- Docker + Docker Compose on a local machine or Mac Mini
- Cloudflare Tunnel for exposing webhooks to Slack / GitHub / internet

---

## Getting Started

### Prerequisites

- A Mac, Linux machine, or Mac Mini (recommended for always-on deployment)
- Docker and Docker Compose
- Node.js 18+ (for frontend development)
- Python 3.12+ (for backend development)
- (Optional) Cloudflare account for tunnel — needed for Slack/GitHub webhooks

### Quick Start (Docker)

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/bodhiorchard.git
cd bodhiorchard

# Copy environment config
cp backend/.env.example backend/.env

# Start all services (PostgreSQL, Redis, Ollama, Backend)
cd backend
docker compose up -d

# Wait for Ollama to pull models (~5 min first time)
# The API will be available at http://localhost:8000
# API docs at http://localhost:8000/docs

# Start the frontend
cd ../frontend
npm install
npm run dev
# Frontend available at http://localhost:3000
```

### Local Development

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d redis ollama      # infrastructure only
alembic upgrade head                    # run migrations
uvicorn app.main:app --reload           # start dev server

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://bodhiorchard:bodhiorchard@localhost:5432/bodhiorchard` |
| `SECRET_KEY` | JWT signing key | `change-me-in-production` |
| `ENCRYPTION_KEY` | AES key for secrets at rest | (generated) |
| `LLM_PROVIDER` | LLM provider | `ollama` |
| `LLM_MODEL` | LLM model name | `llama3:8b` |
| `EMBEDDING_PROVIDER` | Embedding provider | `ollama` |
| `EMBEDDING_MODEL` | Embedding model | `nomic-embed-text` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379` |
| `SLACK_BOT_TOKEN` | Slack bot token | (optional) |
| `GITHUB_PAT` | GitHub personal access token | (optional) |

---

## Project Structure

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
│   ├── docker-compose.yml   # PostgreSQL, Redis, Ollama
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
├── BODHIORCHARD-ARCHITECTURE.md  # Comprehensive architecture spec (8400+ lines)
├── AGENTS.md                # Agent capabilities documentation
├── TODO.md                  # Roadmap and progress tracking
└── LICENSE                  # AGPL-3.0 + Commercial dual license
```

---

## API Documentation

When the backend is running, interactive API documentation is available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

| Endpoint | Description |
|---|---|
| `POST /api/v1/auth/login` | JWT authentication |
| `GET /api/v1/buds` | List BUD documents |
| `POST /api/v1/buds` | Create a new BUD |
| `GET /api/v1/dashboard/tree-data` | 3D tree visualization data |
| `GET /api/v1/skills/profiles` | Developer skill profiles |
| `POST /api/v1/skills/scan` | Trigger repository scan |
| `GET /api/v1/triage-sessions` | Triage approval queue |
| `POST /api/v1/slack/events` | Slack webhook handler |
| `POST /mcp/*` | MCP tools for AI assistants |

---

## Integrations

| Integration | Status | Description |
|---|---|---|
| **Claude Code** | Core | AI backbone — runs codebase-aware agents locally via MCP (10 tools) |
| **Ollama** | Supported | Local LLM inference — free, private, no API keys needed |
| **Anthropic API** | Supported | Cloud LLM for non-codebase agents via fastembed |
| **OpenAI API** | Supported | Alternative cloud LLM provider via fastembed |
| **Slack** | Supported | Feature intake, triage conversations, notifications (via Cloudflare Tunnel) |
| **GitHub** | Supported | PR merge detection, branch status, code scanning |
| **OpenAI Codex** | In Development | Code-specialized agent tasks |
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
- [x] 11 AI agent definitions

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

### Contributor License Agreement

By contributing to Bodhiorchard, you agree that your contributions will be licensed under the same license as the project, and you grant the project maintainer (Arun Rajkumar) a perpetual, worldwide, non-exclusive, royalty-free license to use, modify, sublicense, and distribute your contributions. This ensures the project can offer commercial licensing alongside the open-source version.

---

## License

Bodhiorchard is **dual-licensed**:

### Open Source — AGPL-3.0

The open-source version is licensed under the [GNU Affero General Public License v3.0](LICENSE). This means:

- You can use, modify, and distribute the software freely
- If you run a modified version as a network service (SaaS), you must make your source code available to users
- All derivative works must also be licensed under AGPL-3.0

### Commercial License

For organizations that want to use Bodhiorchard **without AGPL obligations** (e.g., in proprietary SaaS products, internal tools without source disclosure, or OEM embedding), a **commercial license** is available.

**Contact**: YOUR_EMAIL@example.com

The commercial license includes:
- Use in proprietary/closed-source products
- No AGPL source disclosure requirements
- Priority support and feature requests
- Custom deployment assistance

---

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

**Built by [Arun Rajkumar](https://github.com/arunrajkumar)**

If Bodhiorchard helps your team, give it a star and spread the word.

</div>
