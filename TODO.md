# FlowDev — Master TODO

> **Last updated**: 2026-03-17
> **Status**: Phase 1 in progress
> **Architecture**: See `FLOWDEV-ARCHITECTURE.md` (8400+ lines)

---

## Legend

- [x] Done
- [ ] Not started
- [~] Partially done (details in notes)

---

## Phase 0: Project Scaffolding

### Backend Structure
- [x] Project scaffolding (`pyproject.toml`, `requirements.txt`, `Dockerfile`)
- [x] FastAPI app skeleton (`app/main.py` with lifespan, CORS, structlog)
- [x] Pydantic-settings config (`app/config.py` — DB, Auth, LLM, Embedding, Redis, Integrations)
- [x] Async SQLAlchemy 2.0 engine + session (`app/database.py`)
- [x] Docker Compose (PostgreSQL pgvector, Redis, Ollama + model pull, backend)
- [x] `.env.example` with all environment variables
- [x] `README.md` with quickstart and project structure
- [x] `CLAUDE.md` with development guidelines and code standards

### Database Models (SQLAlchemy 2.0 `mapped_column`)
- [x] `Base` + `TimestampMixin` + `BaseModel` (`models/base.py`)
- [x] `Organization` model (`models/organization.py`)
- [x] `User` + `OrgMembership` models (`models/user.py`)
- [x] `PRDDocument` model with `Vector(768)` embedding (`models/prd.py`)
- [x] `Bug` model with vector embedding (`models/bug.py`)
- [x] `SkillProfile` model (`models/skill_profile.py`)
- [x] `StandupReport` model (`models/standup.py`)
- [x] `FeatureLearning` model with vector embedding (`models/feature_learning.py`)
- [x] `CodeEmbedding` model (`models/code_embedding.py`)
- [x] `AgentLog` model (`models/agent_log.py`)
- [x] `EnterpriseRule` model with vector embedding (`models/enterprise_rule.py`)
- [x] `KnowledgeItem` model with vector embedding (`models/knowledge_item.py`)
- [x] `ExecutionNode` model (`models/execution_node.py`)
- [x] `JWTToken` model (`models/jwt_token.py`)
- [x] `models/__init__.py` — all models imported for Alembic discovery

### Alembic
- [x] `alembic.ini` configuration
- [x] Async `alembic/env.py` with asyncpg
- [x] `alembic/script.py.mako` migration template
- [x] Generate initial migration (`alembic revision --autogenerate -m "initial schema"`)
- [x] Verify migration runs cleanly against fresh database
- [x] Add pgvector extension creation to migration (`CREATE EXTENSION IF NOT EXISTS vector`)
- [x] Add HNSW indexes on all vector columns in migration
- [ ] Add RLS policies in migration (all tables with `org_id`)

### API Layer (Stubs)
- [x] Health check endpoint (`/health`)
- [x] Auth routes: `POST /login`, `POST /register`, `GET /me`
- [x] Org routes: `GET /`, `POST /`, `GET /{id}`
- [x] JWT security (`core/security.py` — create/verify tokens, bcrypt)
- [x] Auth dependency (`core/deps.py` — `get_current_user`)

### Services
- [x] LLM service (`services/llm_service.py` — LiteLLM, default/premium tiers)
- [x] Embedding service (`services/embedding_service.py` — Ollama/OpenAI/sentence-transformers)

### Pydantic Schemas
- [x] Auth schemas (`LoginRequest`, `RegisterRequest`, `TokenResponse`)
- [x] User schemas (`UserRead`)
- [x] Organization schemas (`OrganizationCreate`, `OrganizationRead`)

### Frontend Structure
- [x] Vue 3 + Vuetify 3 + TypeScript project scaffold
- [x] Vuetify dark theme configuration (`flowdevDark` / `flowdevLight`)
- [x] SCSS variables + global styles (Inter font, card borders, gradient bg)
- [x] Pinia stores (setup wizard state, auth stub)
- [x] Vue Router (`/setup`, `/dashboard`)
- [x] Axios API service with auth interceptor
- [x] Type definitions (`SetupState`, `DeploymentMode`, `StepDefinition`)
- [x] FlowDevLogo component
- [x] StepIndicator component (6-step horizontal progress)
- [x] SetupLayout (gradient background, centered content)

### Setup Wizard (6 Steps)
- [x] `SetupWizard.vue` — v-window stepper with validation gating
- [x] Step 0: MethodologyStep — FlowDev methodology intro (11 agents, 9-phase lifecycle, principles)
- [x] Step 1: WelcomeStep — feature cards (AI Agents, Code-Aware, Local-First)
- [x] Step 2: OrganizationStep — name + auto-slug
- [x] Step 3: AdminAccountStep — name, email, password with strength indicator
- [x] Step 4: IntegrationsStep (Connections) — Source Code (local file picker + git providers), Messaging (Slack), AI Config (4 presets: local/cloud/hybrid/claude-ollama), Claude Code connection test
- [x] Step 5: ReviewStep — config summary + Launch button
- [x] DashboardPlaceholder view
- [x] DirectoryPicker component — server-side filesystem browser with breadcrumbs, git repo detection
- [x] `GET /setup/browse-directories` endpoint — lists directories for file picker
- [x] `GET /setup/check-claude` endpoint — tests Claude Code CLI availability

### Tests
- [x] `tests/conftest.py` with async test client + DB session fixtures
- [ ] Write tests for auth endpoints (login, register, me)
- [ ] Write tests for organization endpoints (create, list, get)

---

## Phase 1: Foundation (Week 1-2)

### Database & Migrations
- [x] Run `alembic revision --autogenerate` to generate initial migration
- [x] Add `CREATE EXTENSION` statements (uuid-ossp, vector, pg_trgm) to migration
- [x] Add HNSW indexes for: `prd_documents`, `bugs`, `enterprise_rules`, `feature_learnings`, `code_embeddings`, `knowledge_items`
- [ ] Add RLS policies for all org-scoped tables
- [ ] Add trigram index on `prd_documents.title`
- [ ] Add database views: `prd_summary`, `team_utilization`
- [ ] Create `org_registration_tokens` table (for node registration)
- [ ] Create `agent_tasks` table (for task queue tracking with `assigned_node` FK)
- [ ] Test migration: up + down + up (reversibility)

### Setup API Endpoint
- [x] `POST /api/setup/initialize` — first-time setup endpoint
  - [x] Accept org name, slug, admin credentials, integrations config, LLM config
  - [x] Create org + admin user + set org config in one transaction
  - [x] Return JWT token for the admin user
  - [x] Guard: rejects duplicate org slug (409 Conflict)
- [x] `GET /api/setup/status` — check if setup is complete
- [x] `GET /api/setup/browse-directories` — filesystem browser for source code picker
- [x] `GET /api/setup/check-claude` — test Claude Code CLI availability
- [x] Connect frontend setup wizard `submitSetup()` to this endpoint
- [x] Frontend stores JWT token from setup response in localStorage

### Permission System (RBAC)
- [x] `Permission` model with categories (BACKLOG, AGENTS, NODES, PRDs, TEAM, ORG, INTEGRATIONS, KNOWLEDGE, REPORTS)
- [x] `Role` model with system/custom scope types
- [x] `RolePermission` join table
- [x] `PermissionCategory` model for UI grouping
- [x] Permission seeder — 9 system roles with granular permission assignments
- [x] Role CRUD API: `GET/POST/PUT/DELETE /api/v1/roles`
- [x] Permission list API: `GET /api/v1/permissions`

### Public Access & Cloudflare Tunnel (Optional)
- [x] `PUBLIC_URL` setting in backend config (`app/config.py`)
- [x] `cloudflared` service in Docker Compose (opt-in via `--profile tunnel`)
- [x] `VITE_API_BASE_URL` documented in frontend `.env.example`
- [x] `docs/tunnel-setup.md` — complete Cloudflare Tunnel setup guide

### Claude Code Integration
- [x] `services/claude_runner.py` — subprocess execution, JSON output parsing, cost tracking
- [x] `GET /api/v1/claude/test` — test CLI availability and connectivity
- [x] `POST /api/v1/claude/run` — execute Claude Code task with configurable turns/budget/timeout

### MCP Server
- [x] `mcp/server.py` — FastAPI router at `/mcp/tools/*`
- [x] 7 MCP tools: `get_prd_context`, `write_prd`, `get_knowledge`, `search_bugs`, `update_task_status`, `post_slack_message`, `get_team_context`
- [x] MCP auth via bearer token (org `mcp_token_hash`)

### PRD CRUD Endpoints (Full)
- [ ] `POST /api/v1/prds` — create PRD (auto-increment `prd_number` per org)
- [ ] `GET /api/v1/prds` — list PRDs (filter by status, paginate with cursor)
- [ ] `GET /api/v1/prds/{id}` — get single PRD with full content
- [ ] `PATCH /api/v1/prds/{id}` — update PRD (status transitions, content)
- [ ] `DELETE /api/v1/prds/{id}` — soft delete or archive
- [ ] PRD Pydantic schemas: `PRDCreate`, `PRDRead`, `PRDUpdate`, `PRDList`
- [ ] Auto-embed PRD content on create/update (via embedding service)

### Knowledge API Endpoints
- [ ] `GET /api/v1/knowledge` — list knowledge items (filter by category)
- [ ] `POST /api/v1/knowledge` — create knowledge item
- [ ] `PUT /api/v1/knowledge/{id}` — update (triggers re-embedding)
- [ ] `DELETE /api/v1/knowledge/{id}` — deactivate
- [ ] `POST /api/v1/knowledge/search` — semantic search via pgvector
- [ ] Knowledge Pydantic schemas: `KnowledgeItemCreate`, `KnowledgeItemRead`, `KnowledgeItemUpdate`

### ~~Node Registration API~~ (Removed — local execution model, no remote nodes)
_FlowDev runs agents locally on the same machine. Node registration, discovery, and remote execution have been removed in favor of direct subprocess calls via `services/claude_runner.py`._

### LLM Provider Abstraction
- [ ] Test LiteLLM integration with Ollama (llama3:8b)
- [ ] Test LiteLLM integration with OpenAI (gpt-4o)
- [ ] Test LiteLLM integration with Anthropic (claude-sonnet-4-6)
- [ ] Add `model_tier` routing (default → local, premium → cloud or large local)
- [ ] Add streaming support for long-form generation

### Embedding Provider Abstraction
- [ ] Test Ollama embeddings (nomic-embed-text, 768 dims)
- [ ] Test OpenAI embeddings (text-embedding-3-small, 1536 dims)
- [ ] Test sentence-transformers fallback (all-MiniLM-L6-v2, 384 dims)
- [ ] Add batch embedding support for bulk operations
- [ ] Validate embedding dimensions match `Vector(N)` in models

### Bug CRUD Endpoints
- [ ] `POST /api/v1/bugs` — create bug (auto-link to PRD if module matches)
- [ ] `GET /api/v1/bugs` — list bugs (filter by status, severity, assignee)
- [ ] `GET /api/v1/bugs/{id}` — get single bug
- [ ] `PATCH /api/v1/bugs/{id}` — update status, reassign
- [ ] Bug schemas: `BugCreate`, `BugRead`, `BugUpdate`

### User Management Endpoints
- [ ] `GET /api/v1/users` — list org users (admin only)
- [ ] `GET /api/v1/users/{id}` — get user profile
- [ ] `PATCH /api/v1/users/{id}` — update user (role, name)
- [ ] `DELETE /api/v1/users/{id}` — deactivate user
- [ ] Add role-based access control middleware (`require_role("admin", "org_owner")`)

### Docker & DevOps
- [x] Docker Compose with Redis, Ollama, optional Cloudflare Tunnel (`--profile tunnel`)
- [ ] Verify `docker compose up` boots all services cleanly
- [ ] Add Ollama healthcheck to docker-compose (wait for model ready)
- [ ] Add backend healthcheck to docker-compose
- [ ] Add `docker-compose.dev.yml` override for hot-reload
- [ ] Create `scripts/seed.py` — seed demo data for local dev

### Testing
- [ ] Auth endpoint tests (login success, login fail, register, duplicate email)
- [ ] Org endpoint tests (create, list, get, slug uniqueness)
- [ ] PRD endpoint tests (CRUD, status transitions, auto prd_number)
- [ ] Setup endpoint test (first-time init, guard on second call)
- [ ] CI config: GitHub Actions for pytest + ruff + mypy

---

## Phase 2: Integrations (Week 3-4)

### GitHub Integration
- [ ] GitHub App setup documentation (permissions, webhook URL)
- [ ] `POST /api/webhooks/github` — webhook receiver with signature validation
- [ ] Handle `pull_request.opened` event → notify relevant PRD watchers
- [ ] Handle `pull_request.closed` (merged) event → trigger Status Agent
- [ ] Handle `pull_request.synchronize` event → update PR metadata
- [ ] GitHub API service (`services/github_service.py`) — list repos, get PR, get files
- [ ] Store GitHub App installation token per org
- [ ] OAuth flow endpoint for connecting GitHub org

### Slack Integration
- [ ] Slack App setup documentation (Event Subscriptions, Slash Commands)
- [ ] `POST /api/webhooks/slack/events` — event receiver with signature validation
- [ ] `POST /api/webhooks/slack/slash` — slash command handler
- [ ] Handle `message.channels` event → feature intake pipeline
- [ ] Handle `app_mention` event → respond with status/info
- [ ] Slash commands: `/flowdev-prd`, `/flowdev-status`, `/flowdev-triage`, `/flowdev-standup`
- [ ] Slack API service (`services/slack_service.py`) — post message, open modal, thread reply
- [ ] OAuth flow endpoint for connecting Slack workspace

### PRD Status Updates via GitHub
- [ ] Auto-update PRD status when linked PR is merged (`in-dev` → `in-qa`)
- [ ] Track PRD ↔ PR linkage (via PR title convention: `PRD-042: feature name`)
- [ ] Add `linked_prs` to PRD metadata on PR creation
- [ ] Post Slack notification when PRD status changes

### Frontend: Integration Settings Page
- [ ] GitHub connection card (OAuth connect button, connected repos list)
- [ ] Slack connection card (OAuth connect button, connected workspace info)
- [ ] Integration status indicators in dashboard

---

## Phase 3: Core Agents (Week 5-6)

### Vector DB & Embedding Pipeline
- [ ] Verify HNSW indexes are created on all vector columns
- [ ] Implement `services/vector_search.py` — cosine similarity search with org isolation
- [ ] Batch re-embed endpoint for existing data (backfill)
- [ ] Add configurable `ef_search` for HNSW query-time tuning

### Triage Agent (Agent #1)
- [ ] Agent implementation (`agents/triage_agent.py`) using Agno
- [ ] Tools: `SlackTools`, `VectorSearchTools`, `GithubTools`
- [ ] Input: Slack message (feature request thread)
- [ ] Output: Structured intake form (title, description, urgency, module, complexity estimate)
- [ ] Logic: search existing PRDs for duplicates via vector similarity
- [ ] Post intake summary to Slack thread as reply
- [ ] Test with sample Slack payloads

### PRD Agent (Agent #2)
- [ ] Agent implementation (`agents/prd_agent.py`) using Agno
- [ ] Tools: `PRDRepoTools`, `VectorSearchTools`, `GithubTools`
- [ ] Input: Approved intake form from Triage Agent
- [ ] Output: Full PRD document (markdown) with tech context
- [ ] Model tier: `premium` (needs deep reasoning)
- [ ] Execution path: Mac Mini (Claude Code) or API fallback
- [ ] Save PRD to database + generate embedding
- [ ] Post PRD link to Slack

### Agent Execution (Local)
- [x] Claude Code CLI execution via `asyncio.create_subprocess_exec` (`services/claude_runner.py`)
- [x] Configurable max_turns, max_budget, timeout per task
- [x] JSON output parsing and cost tracking
- [ ] Redis task queue for async agent execution
- [ ] Concurrency control (asyncio.Semaphore)
- [ ] Timeout handling (5 min default per task)

### Local Agent Execution
- [x] Claude Code CLI integration (`services/claude_runner.py`)
- [x] `GET /api/v1/claude/test` — test Claude Code CLI availability
- [x] `POST /api/v1/claude/run` — trigger Claude Code CLI task
- [ ] Auto-fallback to API mode when Claude Code is not available

### MCP Server for Claude Code Writeback
- [ ] `mcp/server.py` — FastAPI router at `/mcp/tools/*`
- [ ] Tool: `write_prd` — save generated PRD to database
- [ ] Tool: `update_task_status` — report task progress
- [ ] Tool: `post_slack_message` — post to Slack channel/thread
- [ ] Tool: `get_prd_context` — read existing PRDs for context
- [ ] Tool: `get_team_context` — read team capacity/active work
- [ ] Tool: `get_knowledge` — query org knowledge base
- [ ] MCP auth: verify `FLOWDEV_INTERNAL_TOKEN` bearer token

### Knowledge Sync Agent
- [ ] `agents/knowledge_sync_agent.py`
- [ ] L1→L3: Scan repo CLAUDE.md files → upsert into `knowledge_items`
- [ ] L3→L2: Push coding standards from DB → Mac Mini skills
- [ ] L3→L4: Generate embeddings for unembedded knowledge items
- [ ] Stale detection: compare L1 timestamps vs L3 `updated_at`
- [ ] Scheduled execution: hourly scan, on-change push, daily stale check

### Slack Slash Commands (Updated for Multi-Mode)
- [ ] `/flowdev-prd "description"` → route to node or API
- [ ] `/flowdev-triage "slack thread URL"` → trigger Triage Agent
- [ ] `/flowdev-status` → show current PRD statuses
- [ ] `/flowdev-standup` → trigger standup generation
- [ ] Ephemeral response with task ID for tracking

---

## Phase 4: Advanced Agents (Week 7-8)

### Status Agent (Agent #3)
- [ ] Trigger on PR merge → update PRD status
- [ ] Auto-detect PRD from PR title/branch naming convention
- [ ] Update metadata: linked PRs, status transitions log
- [ ] Post status change notification to Slack

### Standup Agent (Agent #4)
- [ ] Cron trigger: daily at configured time
- [ ] Aggregate: PRs merged, PRDs progressed, bugs opened/closed
- [ ] Generate: natural language daily summary
- [ ] Flag: blockers, overdue PRDs, capacity warnings
- [ ] Save to `standup_reports` + post to Slack

### Learning Agent (Agent #5)
- [ ] Trigger on PRD reaching `deployed` status
- [ ] Analyze: cycle time, estimate accuracy, bug count
- [ ] Generate retrospective markdown
- [ ] Save to `feature_learnings` with embedding
- [ ] Execution path: local Claude Code (needs git history access)

### Bug Linker Agent (Agent #6)
- [ ] Trigger on new bug creation
- [ ] Vector search: find related PRDs by description similarity
- [ ] Auto-link bug to most likely PRD
- [ ] Search code embeddings for related files
- [ ] Post linking results as Slack notification

### Reassignment Agent (Agent #7)
- [ ] Trigger when bug count for a module exceeds threshold
- [ ] Query skill profiles: find devs with matching module expertise
- [ ] Consider workload: don't overload busy devs
- [ ] Suggest reassignment via Slack (human approval)
- [ ] Auto-reassign if configured for automation

### Skill Agent (Agent #8)
- [ ] Trigger on PR merge → update skill profiles
- [ ] Extract: languages, modules, repos from PR diff
- [ ] Update `skill_profiles` table (touch count, skill score, last touch)
- [ ] Pattern recognition: identify skill growth trends

### Support Agent (Agent #9)
- [ ] Support ticket integration (Zendesk, Intercom, or custom webhook)
- [ ] Customer profiling: link tickets to org context
- [ ] Revenue-based prioritization (if customer data available)
- [ ] PRD reopening: trigger when bug pattern matches closed PRD
- [ ] Model tier: `premium` (customer-facing needs nuance)

### Design Agent (Agent #10)
- [ ] Trigger on PRD approved
- [ ] UI/UX scope definition and component breakdowns
- [ ] Interaction specs and accessibility planning
- [ ] Execution path: local Claude Code (codebase-aware)

### Test Plan Agent (Agent #11)
- [ ] Trigger on dev complete status
- [ ] Generate Playwright e2e tests, unit/integration tests
- [ ] Manual UAT test cases and security test plans
- [ ] Execution path: local Claude Code (codebase-aware)

### Inter-Agent Communication
- [ ] Define event bus pattern (Redis pub/sub or Agno Teams)
- [ ] Triage → PRD Agent handoff
- [ ] Status → Standup data aggregation
- [ ] Bug Linker → Reassignment trigger chain
- [ ] Support → PRD reopening lifecycle

---

## Phase 5: Frontend & Polish (Week 9-10)

### Dashboard
- [ ] Main dashboard layout (sidebar nav, header with org switcher)
- [ ] Org switcher dropdown (for multi-org users)
- [ ] Role-based navigation (hide admin items from non-admins)
- [ ] Dark/light theme toggle

### PRD Board
- [ ] Kanban-style PRD board (columns by status)
- [ ] PRD detail view (full markdown rendered)
- [ ] PRD creation form (manual)
- [ ] Status transition controls (drag or button)
- [ ] Timeline view (Gantt-like)
- [ ] Filter by assignee, module, date range
- [ ] Search (text + semantic)

### Bug Tracker
- [ ] Bug list view with severity/status filters
- [ ] Bug detail view with linked PRD
- [ ] Bug creation form
- [ ] Bulk actions (assign, close, change severity)

### Capacity Planning
- [ ] Team utilization chart (per dev, per module)
- [ ] Workload heatmap
- [ ] Skill matrix visualization
- [ ] Assignment recommendations (from Skill Agent data)

### Metrics Dashboard
- [ ] Cycle time trends (chart)
- [ ] Bug rates by module (chart)
- [ ] Agent activity log (recent agent actions)
- [ ] Estimate accuracy tracking

### Settings Pages
- [ ] Organization settings (name, slug, config)
- [ ] User management (invite, roles, deactivate)
- [ ] Integration settings (GitHub, Slack — connect/disconnect)
- [ ] LLM configuration (provider, model, API keys)
- [ ] Agent execution settings (Claude Code path, budget limits)
- [ ] Knowledge base management (CRUD for standards, guidelines, ADRs)
- [ ] Agent configuration (thresholds, schedules, enable/disable)

### Real-Time Updates
- [ ] WebSocket connection from frontend to backend
- [ ] Live PRD status updates
- [ ] Live agent activity feed
- [ ] Notification toasts for important events

### Knowledge Base UI
- [ ] Coding standards viewer/editor
- [ ] Design guidelines viewer/editor
- [ ] API standards viewer/editor
- [ ] Architecture decisions (ADR) list + viewer
- [ ] Repo contexts (auto-generated, view + refresh)
- [ ] Sync status dashboard (last sync times, stale items)

### Monitoring & Observability
- [ ] Structured logging with request ID correlation
- [ ] Agent execution logs viewer (from `agent_logs` table)
- [ ] API request metrics (latency, error rate)
- [ ] Database connection pool monitoring
- [ ] Ollama health status indicator
- [ ] Agent execution health (task count, success rate, cost)

### Performance
- [ ] API response time benchmarks
- [ ] Database query optimization (EXPLAIN ANALYZE on key queries)
- [ ] Frontend bundle size optimization
- [ ] Lazy loading for heavy views (charts, PRD board)

---

## Phase 6: VSCode Extension (Week 11-14, post-launch)

### Extension Scaffold
- [ ] TypeScript VSCode extension project setup
- [ ] Extension manifest (`package.json` — contributes, activationEvents)
- [ ] Authentication: store FlowDev JWT in VSCode SecretStorage

### Sidebar TreeView
- [ ] "My PRDs" tree (assigned PRDs, grouped by status)
- [ ] "My Bugs" tree (assigned bugs, grouped by severity)
- [ ] "Pending Reviews" tree (PRDs awaiting review)
- [ ] Auto-refresh on focus/timer

### Status Bar
- [ ] Current work context: `PRD-042: Payment Retry [in-dev]`
- [ ] Click to switch active PRD

### Command Palette
- [ ] `FlowDev: Trigger PRD Agent` — generate PRD for current repo
- [ ] `FlowDev: File Bug` — quick bug creation from editor
- [ ] `FlowDev: View Standup` — show today's standup
- [ ] `FlowDev: My Capacity` — show current workload

### Notifications
- [ ] Bug assigned notification
- [ ] PRD status change notification
- [ ] Agent completion notification

### Deep Links
- [ ] "View full PRD" → opens web app in browser
- [ ] "View bug details" → opens web app in browser

---

## Infrastructure & DevOps (Ongoing)

### CI/CD
- [ ] GitHub Actions: lint (ruff) + typecheck (mypy) + test (pytest) on PR
- [ ] GitHub Actions: build Docker image on main push
- [ ] GitHub Actions: run frontend lint + typecheck on PR
- [ ] Automated migration check in CI (ensure no pending migrations)

### Security
- [ ] Rate limiting on auth endpoints
- [ ] CORS configuration for production (restrict origins)
- [ ] Secret management (no secrets in code or config files)
- [ ] Dependency vulnerability scanning (dependabot or similar)
- [ ] Input validation on all endpoints (Pydantic enforced)
- [ ] SQL injection prevention (verified by SQLAlchemy parameterized queries)

### Documentation
- [ ] API documentation auto-generated via OpenAPI/Swagger (FastAPI built-in)
- [ ] Deployment guide (Docker, bare metal, cloud)
- [ ] Contributing guide (`CONTRIBUTING.md`)
- [ ] License file (Apache 2.0)
- [ ] Architecture decision records in knowledge base

### Monitoring (Production)
- [ ] Prometheus metrics endpoint
- [ ] Grafana dashboard templates
- [ ] Alerting rules (API errors, agent failures, node offline)
- [ ] Log aggregation (structured JSON logs → ELK or Loki)

---

## Tech Debt & Improvements (Backlog)

- [ ] Add `OrgMembership`-based multi-org user access (currently `User.org_id` is single-org)
- [ ] Add cursor-based pagination helper (reusable across all list endpoints)
- [ ] Add request ID middleware for log correlation
- [ ] Add OpenTelemetry tracing for agent execution
- [ ] Add embedding dimension migration strategy (for switching providers)
- [ ] Add soft-delete mixin for archivable records
- [ ] Add audit log table (who changed what, when)
- [ ] Extract Agno agent base class (`BaseFlowDevAgent`) for framework migration safety
- [ ] Add `enterprise_rules` CRUD endpoints
- [ ] Add `skill_profiles` CRUD + auto-update endpoints
- [ ] Add `standup_reports` read endpoints (list by date range)
- [ ] Add `feature_learnings` read endpoints (list by PRD)
- [ ] Add `code_embeddings` ingestion pipeline (scan repos, chunk files, embed)
- [ ] Frontend: Add i18n support
- [ ] Frontend: Add E2E tests (Playwright or Cypress)
- [ ] Frontend: Add Storybook for component library
- [ ] Frontend: PWA support for mobile access

---

## File Reference

| Path | What |
|------|------|
| `FLOWDEV-ARCHITECTURE.md` | Full architecture spec (8400+ lines) |
| `TODO.md` | This file |
| `backend/` | FastAPI backend |
| `backend/app/models/` | SQLAlchemy models (org, user, permission, PRD, bug, skill, etc.) |
| `backend/app/api/v1/` | API route handlers (auth, setup, roles, permissions, claude) |
| `backend/app/services/` | LLM, embedding, Claude runner, permission seeder |
| `backend/app/mcp/` | MCP server (7 tools for Claude Code writeback) |
| `backend/app/agents/` | Agent skill mappings (11 agents) |
| `backend/alembic/` | Database migrations |
| `backend/docker-compose.yml` | Local dev infrastructure (Redis, Ollama, optional Cloudflare Tunnel) |
| `docs/tunnel-setup.md` | Cloudflare Tunnel setup guide |
| `frontend/` | Vue 3 + Vuetify 3 frontend |
| `frontend/src/views/setup/` | 6-step setup wizard |
| `frontend/src/components/setup/` | DirectoryPicker, AgentCard, LifecycleFlowchart, StepIndicator |
| `frontend/src/plugins/vuetify.ts` | Theme configuration |
