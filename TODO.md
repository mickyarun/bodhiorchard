# FlowDev — Master TODO

> **Last updated**: 2026-03-20
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
- [x] `Team` + `TeamMember` models (`models/team.py`)
- [x] `models/__init__.py` — all models imported for Alembic discovery

### Repository Layer
- [x] `BaseRepository[T]` with generic async CRUD + org scoping (`repositories/base.py`)
- [x] `BugRepository` (`repositories/bug.py`)
- [x] `KnowledgeItemRepository` with 30+ methods, pgvector search, dedup (`repositories/knowledge_item.py`)
- [x] `OrganizationRepository` (`repositories/organization.py`)
- [x] `PermissionRepository` (`repositories/permission.py`)
- [x] `PRDRepository` (`repositories/prd.py`)
- [x] `RoleRepository` (`repositories/role.py`)
- [x] `SkillProfileRepository` (`repositories/skill_profile.py`)
- [x] `TeamRepository` (`repositories/team.py`)
- [x] `UserRepository` (`repositories/user.py`)

### Alembic
- [x] `alembic.ini` configuration
- [x] Async `alembic/env.py` with asyncpg
- [x] `alembic/script.py.mako` migration template
- [x] Generate initial migration (`alembic revision --autogenerate -m "initial schema"`)
- [x] Verify migration runs cleanly against fresh database
- [x] Add pgvector extension creation to migration (`CREATE EXTENSION IF NOT EXISTS vector`)
- [x] Add HNSW indexes on all vector columns in migration
- [x] Add composite indexes migration (10 indexes across 6 tables)
- [x] Add teams + team_members migration
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
- [x] Add composite indexes for query optimization (knowledge_items, bugs, prd_documents, organizations, role_permissions, skill_profiles)
- [ ] Add RLS policies for all org-scoped tables
- [ ] Add trigram index on `prd_documents.title`
- [ ] Add database views: `prd_summary`, `team_utilization`
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
- [x] `team:manage` permission added to TEAM category
- [x] Role CRUD API: `GET/POST/PUT/DELETE /api/v1/roles`
- [x] Permission list API: `GET /api/v1/permissions`

### PRD CRUD
- [x] `POST /api/v1/prds` — create PRD (auto-increment `prd_number` per org)
- [x] `GET /api/v1/prds` — list PRDs (filter by status)
- [x] `GET /api/v1/prds/{id}` — get single PRD with full content
- [x] `PATCH /api/v1/prds/{id}` — update PRD (status transitions, content)
- [x] `DELETE /api/v1/prds/{id}` — delete PRD
- [x] PRD Pydantic schemas: `PRDCreate`, `PRDRead`, `PRDUpdate`, `PRDList`
- [x] Frontend Kanban board with drag support

### Knowledge / Skills API
- [x] `GET /api/v1/skills/knowledge` — list knowledge items (filter by category, paginate)
- [x] `GET /api/v1/skills/knowledge/{id}` — single knowledge item detail
- [x] `POST /api/v1/skills/knowledge/search` — semantic search via pgvector
- [x] `GET /api/v1/skills/profiles` — list skill profiles (grouped by user)
- [x] `GET /api/v1/skills/index-stats` — scan status and counts
- [x] `POST /api/v1/skills/scan` — trigger background repository scan
- [x] `GET /api/v1/skills/scan/{id}/status` — poll scan progress

### Settings API
- [x] `GET /api/v1/settings/connections` — org connection settings
- [x] `PATCH /api/v1/settings/connections` — update settings (credential masking)
- [x] `POST /api/v1/settings/mcp-token` — generate MCP token
- [x] `GET /api/v1/settings/mcp-token/status` — check token presence
- [x] `GET /api/v1/settings/repos` — list tracked repos with per-repo stats
- [x] `POST /api/v1/settings/repos` — add a repo path
- [x] `DELETE /api/v1/settings/repos` — remove a repo

### Teams API
- [x] `Team` + `TeamMember` models with cascade delete
- [x] `TeamRepository` with org-scoped CRUD + member management
- [x] `GET /api/v1/teams` — list teams with members
- [x] `POST /api/v1/teams` — create team
- [x] `GET /api/v1/teams/{id}` — get team with members
- [x] `PATCH /api/v1/teams/{id}` — update team
- [x] `DELETE /api/v1/teams/{id}` — delete team
- [x] `POST /api/v1/teams/{id}/members` — add member
- [x] `DELETE /api/v1/teams/{id}/members/{user_id}` — remove member
- [x] `PATCH /api/v1/users/{user_id}/role` — assign RBAC role

### Frontend Views
- [x] PRD Board — Kanban view with status columns, create dialog
- [x] PRD Detail — inline editing, status selector, tabs (Requirements, Tech Spec, Test Plan)
- [x] Features/Knowledge — category tabs, debounced semantic search, expandable cards
- [x] Teams — team cards, create/delete teams, add/remove members, role display
- [x] Settings — connections, scan controls, MCP integration, tracked repositories
- [x] Setup Wizard — 6-step onboarding flow

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

### Knowledge Sync Agent
- [ ] `agents/knowledge_sync_agent.py`
- [ ] L1→L3: Scan repo CLAUDE.md files → upsert into `knowledge_items`
- [ ] L3→L2: Push coding standards from DB → Mac Mini skills
- [ ] L3→L4: Generate embeddings for unembedded knowledge items
- [ ] Stale detection: compare L1 timestamps vs L3 `updated_at`
- [ ] Scheduled execution: hourly scan, on-change push, daily stale check

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

### Bug Linker Agent (Agent #6)
- [ ] Trigger on new bug creation
- [ ] Vector search: find related PRDs by description similarity
- [ ] Auto-link bug to most likely PRD
- [ ] Search code embeddings for related files

### Reassignment Agent (Agent #7)
- [ ] Trigger when bug count for a module exceeds threshold
- [ ] Query skill profiles: find devs with matching module expertise
- [ ] Consider workload: don't overload busy devs
- [ ] Suggest reassignment via Slack (human approval)

### Skill Agent (Agent #8)
- [ ] Trigger on PR merge → update skill profiles
- [ ] Extract: languages, modules, repos from PR diff
- [ ] Update `skill_profiles` table (touch count, skill score, last touch)

### Support Agent (Agent #9), Design Agent (Agent #10), Test Plan Agent (Agent #11)
- [ ] See architecture doc for full specs

### Inter-Agent Communication
- [ ] Define event bus pattern (Redis pub/sub or Agno Teams)
- [ ] Triage → PRD Agent handoff
- [ ] Status → Standup data aggregation
- [ ] Bug Linker → Reassignment trigger chain

---

## Phase 5: Frontend & Polish (Week 9-10)

### Dashboard
- [ ] Main dashboard layout with role-based navigation
- [ ] Org switcher dropdown (for multi-org users)
- [ ] Dark/light theme toggle

### Bug Tracker
- [ ] Bug list view with severity/status filters
- [ ] Bug detail view with linked PRD
- [ ] Bug creation form
- [ ] Bulk actions (assign, close, change severity)

### Capacity Planning
- [ ] Team utilization chart (per dev, per module)
- [ ] Workload heatmap
- [ ] Skill matrix visualization

### Metrics Dashboard
- [ ] Cycle time trends (chart)
- [ ] Bug rates by module (chart)
- [ ] Agent activity log

### Real-Time Updates
- [ ] WebSocket connection from frontend to backend
- [ ] Live PRD status updates
- [ ] Live agent activity feed
- [ ] Notification toasts

### User Management UI
- [ ] `GET /api/v1/users` — list org users
- [ ] `PATCH /api/v1/users/{id}` — update user (role, name)
- [ ] User management page with role assignment

---

## Phase 6: VSCode Extension (Week 11-14, post-launch)

- [ ] TypeScript VSCode extension project setup
- [ ] Sidebar TreeView: My PRDs, My Bugs, Pending Reviews
- [ ] Status bar: current work context
- [ ] Command palette: trigger PRD agent, file bug, view standup
- [ ] Notifications for assignments and status changes

---

## Infrastructure & DevOps (Ongoing)

### CI/CD
- [ ] GitHub Actions: lint (ruff) + typecheck (mypy) + test (pytest) on PR
- [ ] GitHub Actions: build Docker image on main push
- [ ] GitHub Actions: run frontend lint + typecheck on PR

### Security
- [ ] Rate limiting on auth endpoints
- [ ] CORS configuration for production
- [ ] Dependency vulnerability scanning

### Documentation
- [ ] API documentation auto-generated via OpenAPI/Swagger
- [ ] Deployment guide
- [ ] Contributing guide (`CONTRIBUTING.md`)

---

## Garden Engine Rewrite (3D Visualization)

> **Architecture:** See `frontend/src/engine/ARCHITECTURE.md`
> **Assets:** Kenney Nature Kit + Furniture Kit + Blocky Characters (all GLB)
> **Runtime:** PlayCanvas v2.17.2 (PBR pipeline, IBL, ACES tone mapping)

### Phase 1: Skeleton Project (Foundation)
- [x] Rename old engine → `engine_bkup/`, create new directory structure
- [x] `core/Application.ts` — PlayCanvas bootstrap with proper PBR lighting (IBL, tone mapping, gamma)
- [x] `core/EventBus.ts` — Type-safe generic pub/sub
- [x] `core/Clock.ts` — Delta time, elapsed, frame tracking
- [x] `input/InputManager.ts` — Keyboard, mouse, touch input
- [x] `camera/CameraController.ts` — Orbit camera with follow mode + safety fallbacks
- [x] `rendering/MaterialFactory.ts` — PBR material cache with LRU eviction (256 max)
- [x] `index.ts` — GardenEngine public API (only Vue import)
- [x] `utils/MathUtils.ts` + `utils/EntityUtils.ts` — Math + cleanup helpers
- [x] `types.ts` — Extended data contracts with EngineEvents
- [x] `ARCHITECTURE.md` — Comprehensive architecture reference
- [x] Copy shaders from old engine
- [x] Replace old Quaternius characters (100MB) with Kenney Blocky Characters (2MB, 18 models × 27 anims)
- [x] Replace old garden assets with Kenney Nature Kit (50 GLBs)
- [x] Add Kenney Furniture Kit (43 GLBs) for buildings

### Phase 2: World Building
- [ ] `environment/SkySystem.ts` — Preetham atmospheric sky shader
- [ ] `environment/GroundSystem.ts` — Textured terrain with grass/dirt blend
- [ ] `environment/GrassSystem.ts` — Instanced grass + GLB flowers
- [ ] `environment/RockSystem.ts` — GLB rocks scattered with exclusion zones
- [ ] `environment/CloudSystem.ts` — Cloud billboard planes
- [ ] `world/WorldLayout.ts` — Zone placement + exclusion zones
- [ ] `world/TreeBuilder.ts` — GLB tree loading from Nature Kit
- [ ] `world/TreeDecorator.ts` — Fruits, flowers, bugs on trees
- [ ] `world/TreeSystem.ts` — Orchestrator for all trees
- [ ] `world/RelationshipArcs.ts` — Bezier arcs between trees
- [ ] `buildings/BuildingFactory.ts` — Shared primitives helper
- [ ] `buildings/HouseBuilder.ts` — Single house from Furniture Kit
- [ ] `buildings/HousingVillage.ts` — Grid of houses
- [ ] `buildings/CoffeeBarBuilder.ts` — Coffee bar + seats
- [ ] `buildings/CafeteriaBuilder.ts` — Lunch building + seats
- [ ] `buildings/StandupPavilion.ts` — Meeting area
- [ ] `buildings/PoolResortBuilder.ts` — Pool + chairs + floats
- [ ] `effects/WaterSurface.ts` — Shader-based pool water
- [ ] `effects/StringLightEffect.ts` — Decorative lights
- [ ] `core/SceneManager.ts` — Orchestrates full scene build from data

### Phase 3: Player Character
- [ ] `assets/AssetLoader.ts` — GLTF/GLB load + cache + dedup
- [ ] `assets/CharacterCatalog.ts` — Model lists, hash-based assignment
- [ ] `characters/CharacterFactory.ts` — Load, clone, proper PBR materials
- [ ] `characters/AnimationController.ts` — State machine (idle/walk/sprint/swim/sit)
- [ ] `characters/CharacterEntity.ts` — Mesh + animator + name label
- [ ] `characters/PlayerController.ts` — WASD movement + swimming
- [ ] `rendering/LabelRenderer.ts` — Billboard name labels
- [ ] `characters/PropAttachment.ts` — Watering can, fertilizer, agent gear

### Phase 4: NPC AI & Time-Based Behaviors
- [ ] `ai/BehaviorTree.ts` + `ai/BehaviorNodes.ts` — Generic BT evaluator
- [ ] `ai/behaviors/*.ts` — Idle, wander, walk-to, sit, swim, sleep, care-tree, coffee, eat, home
- [ ] `time/TimeScheduler.ts` — Day/hour → activity mapping
- [ ] `time/ActivityRules.ts` — Presence + time → behavior
- [ ] `ai/NPCDirector.ts` — Assigns behaviors based on time + presence

### Phase 5: Interaction & Tooltips
- [ ] `interaction/PickerSystem.ts` — Ray-sphere picking
- [ ] `interaction/TooltipManager.ts` — Tooltip content generation
- [ ] `interaction/FocusSystem.ts` — Camera focus on click

### Phase 6: Effects & Polish
- [ ] `effects/ParticleEmitter.ts` — Generic particle system
- [ ] `effects/SplashEffect.ts` — Pool splashes
- [ ] `effects/ZzzEffect.ts` — Sleep particles
- [ ] `effects/SteamEffect.ts` — Coffee/cooking steam
- [ ] `vehicles/VehicleBuilder.ts` — Procedural meshes
- [ ] `vehicles/VehicleSystem.ts` — Arrival animations
- [ ] Performance pass: instancing, LOD, material sharing

---

## Tech Debt & Improvements (Backlog)

- [ ] Add cursor-based pagination helper (reusable across all list endpoints)
- [ ] Add request ID middleware for log correlation
- [ ] Add OpenTelemetry tracing for agent execution
- [ ] Add embedding dimension migration strategy (for switching providers)
- [ ] Add soft-delete mixin for archivable records
- [ ] Add audit log table (who changed what, when)
- [ ] Frontend: Add E2E tests (Playwright)
- [ ] Frontend: PWA support for mobile access

---

## File Reference

| Path | What |
|------|------|
| `FLOWDEV-ARCHITECTURE.md` | Full architecture spec (8400+ lines) |
| `TODO.md` | This file |
| `backend/` | FastAPI backend |
| `backend/app/models/` | SQLAlchemy models (org, user, permission, PRD, bug, skill, team, etc.) |
| `backend/app/repositories/` | Data access layer (10 repositories with BaseRepository[T]) |
| `backend/app/api/v1/` | API route handlers (auth, setup, roles, permissions, skills, settings, teams, claude) |
| `backend/app/services/` | LLM, embedding, Claude runner, scan pipeline, permission seeder |
| `backend/app/mcp/` | MCP server (7 tools for Claude Code writeback) |
| `backend/app/agents/` | Agent skill mappings (11 agents) |
| `backend/alembic/` | Database migrations (9 revisions) |
| `backend/docker-compose.yml` | Local dev infrastructure |
| `frontend/` | Vue 3 + Vuetify 3 frontend |
| `frontend/src/views/` | Views: PRDBoard, PRDDetail, FeaturesView, TeamsView, Settings, Setup |
| `frontend/src/stores/` | Pinia stores: auth, prd, knowledge, teams, settings, setup |
| `frontend/src/types/` | TypeScript type definitions |
