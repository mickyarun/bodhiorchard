# Bodhiorchard Technical Architecture Document

**Version**: 2.1
**Last Updated**: 2026-03-17
**Platform**: Open-source AI-native development operations platform
**License**: Apache 2.0

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Tech Stack Details](#2-tech-stack-details)
3. [API Specification](#3-api-specification)
4. [Agent Architecture](#4-agent-architecture)
5. [Webhook & Event Flows](#5-webhook--event-flows)
6. [Database Schema](#6-database-schema)
7. [Vector DB Strategy](#7-vector-db-strategy)
8. [PRD Repository Structure](#8-prd-repository-structure)
9. [GitHub Actions](#9-github-actions)
10. [Slack Bot Design](#10-slack-bot-design)
11. [Configuration](#11-configuration)
12. [Security & Auth](#12-security--auth)
13. [Monitoring & Observability](#13-monitoring--observability)
14. [UI Architecture](#14-ui-architecture)
15. [Support Integration](#15-support-integration)
16. [VSCode Extension Spec](#16-vscode-extension-spec)
17. [Deployment Modes](#17-deployment-modes)
18. [Repository Scan Pipeline](#18-repository-scan-pipeline)

---

## 1. System Overview

### High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Bodhiorchard Platform                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────┐  ┌──────────────────────┐                │
│  │   Slack Users &      │  │   GitHub Repos &     │                │
│  │   Feature Requests   │  │   Pull Requests      │                │
│  └──────────┬───────────┘  └──────────┬───────────┘                │
│             │                         │                            │
│             │ Slack Events API        │ GitHub Webhooks           │
│             │                         │                            │
│  ┌──────────▼─────────────────────────▼──────────┐                │
│  │        Webhook Router & Event Dispatcher       │                │
│  │  (/webhooks/slack, /webhooks/github)           │                │
│  └──────────┬──────────────────────────┬──────────┘                │
│             │                          │                           │
│  ┌──────────▼────────────────┐  ┌──────▼──────────────────┐        │
│  │  FastAPI REST API         │  │  Agent Orchestration    │        │
│  │  (async-first)            │  │  (Agno Framework)       │        │
│  │                           │  │                         │        │
│  │ • Auth & Orgs             │  │  ┌─────────────────┐   │        │
│  │ • PRD CRUD                │  │  │ Triage Agent    │   │        │
│  │ • Bug Management          │  │  ├─────────────────┤   │        │
│  │ • Capacity Planning       │  │  │ PRD Agent       │   │        │
│  │ • Metrics & Dashboard     │  │  ├─────────────────┤   │        │
│  │ • Skill Profiles          │  │  │ Status Agent    │   │        │
│  │ • Agent Triggers (manual) │  │  ├─────────────────┤   │        │
│  └──────────┬────────────────┘  │  │ Standup Agent   │   │        │
│             │                   │  ├─────────────────┤   │        │
│             │                   │  │ Learning Agent  │   │        │
│             │                   │  ├─────────────────┤   │        │
│  ┌──────────▼───────────────────┼─►│ Bug Linker      │   │        │
│  │  Shared Services            │  │ Agent           │   │        │
│  │                             │  ├─────────────────┤   │        │
│  │ • Embedding Service         │  │ Reassignment    │   │        │
│  │ • Vector Search             │  │ Agent           │   │        │
│  │ • PRD Repo Tools            │  ├─────────────────┤   │        │
│  │ • GitHub Tools              │  │ Skill Agent     │   │        │
│  │ • Slack Tools               │  └─────────────────┘   │        │
│  │ • Capacity Service          └──────────┬──────────────┘        │
│  └──────────┬───────────────────────────┬─────┘                   │
│             │                           │                         │
│  ┌──────────▼───────────────────────────▼──────────────────┐      │
│  │           PostgreSQL 16 + pgvector                       │      │
│  │                                                          │      │
│  │  • organizations, users, org_memberships               │      │
│  │  • prd_documents (with vector embeddings)              │      │
│  │  • enterprise_rules (with vector embeddings)           │      │
│  │  • bugs (with vector embeddings)                       │      │
│  │  • skill_profiles                                      │      │
│  │  • standup_reports                                     │      │
│  │  • feature_learnings (with vector embeddings)          │      │
│  │  • agent_logs                                          │      │
│  │  • code_embeddings (with vector embeddings)            │      │
│  │  • HNSW indexes on all vector columns                  │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │       Vue 3 Frontend (Composition API)                   │      │
│  │                                                          │      │
│  │  • Dashboard (org switcher, real-time updates)          │      │
│  │  • PRD Board (status management, timeline view)         │      │
│  │  • Skill Profiles (expertise tracking)                  │      │
│  │  • Capacity Planning (dev workload)                     │      │
│  │  • Metrics (cycle time, throughput, bug rates)          │      │
│  │  • Org Settings (config management)                     │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │       External Integrations                             │      │
│  │                                                          │      │
│  │  • GitHub App (org-level installation)                  │      │
│  │  • Slack OAuth (workspace installation)                 │      │
│  │  • LLM Provider (Ollama local / OpenAI / Anthropic)     │      │
│  │  • LiteLLM (provider abstraction layer)                │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Overview

| Component | Technology | Purpose | Async? |
|-----------|-----------|---------|--------|
| **API Server** | FastAPI 0.104+ | REST endpoints, webhook routing | Yes (uvicorn) |
| **Agent Framework** | Agno 1.0+ | Multi-agent orchestration, Teams, Workflows | Yes (async tools) |
| **Database** | PostgreSQL 16 | Persistent storage, row-level security, transactions | Via asyncpg |
| **Vector DB** | pgvector ext. | Semantic search, embeddings storage | Native SQL |
| **Embeddings** | Configurable (Ollama/OpenAI/sentence-transformers) | Vectorization of content | Via async HTTP |
| **LLM Abstraction** | LiteLLM | Multi-provider LLM routing | Via async HTTP |
| **Frontend** | Vue 3 | Web UI, dashboard, real-time updates | WebSocket (future) |
| **Message Queue** | None (Agno handles async) | Agent task scheduling | Agno's native queue |
| **Cache Layer** | Redis (optional) | Session tokens, rate limiting | Optional for scale |

### Multi-Org Isolation Model

Every table includes `org_id` as a foreign key to `organizations`. The multi-org isolation strategy:

1. **Data Isolation**: Every row in every table is scoped to an organization via `org_id`.
2. **Row-Level Security (RLS)**: PostgreSQL RLS policies enforce org boundaries at the database level.
3. **API Authentication**: JWT tokens include `org_id`; all API endpoints validate the requesting user belongs to the specified org.
4. **Vector DB Namespacing**: Vector searches filter by `org_id` in metadata to prevent cross-org leakage.
5. **Slack/GitHub per Org**: Each org connects to its own Slack workspace and GitHub organization.
6. **Configuration Isolation**: `organizations.config_json` stores per-org settings (thresholds, notification preferences, etc.).

**Example RLS Policy**:
```sql
ALTER TABLE prd_documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation_prd ON prd_documents
  USING (org_id = current_setting('app.org_id')::uuid)
  WITH CHECK (org_id = current_setting('app.org_id')::uuid);
```

## 2. Tech Stack Details

### 2.1 Python 3.11+ with FastAPI (Async-First)

**Why FastAPI:**
- Native async/await support for handling webhooks and agent execution concurrently
- Automatic API documentation (OpenAPI/Swagger)
- Pydantic integration for request/response validation
- Excellent performance for I/O-bound operations (API calls, DB queries, embeddings)

**Core Dependencies:**
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
sqlalchemy==2.0.23
asyncpg==0.29.0
python-jose[cryptography]==3.3.0
python-multipart==0.0.6
litellm==1.40.0               # LLM provider abstraction (Ollama, OpenAI, Anthropic)
claude-agent-sdk==0.1.0        # Claude Agent SDK for codebase-aware agents (PRD, Learning)
httpx==0.27.0                  # Async HTTP client for Ollama API
```

**Async Request Handling Example:**
```python
from fastapi import FastAPI, BackgroundTasks
from contextlib import asynccontextmanager

app = FastAPI()

@app.post("/webhooks/github")
async def github_webhook(payload: GitHubPayload, background_tasks: BackgroundTasks):
    # Immediate response to GitHub
    await validate_github_signature(payload)

    # Offload agent execution to background
    background_tasks.add_task(status_agent.run, payload)
    return {"status": "webhook received"}

@app.post("/api/prd")
async def create_prd(request: CreatePRDRequest, current_org: OrgContext):
    prd = await prd_service.create(request, current_org)
    background_tasks.add_task(prd_agent.run, prd)
    return prd
```

### 2.2 Agno Agent Framework

**Why Agno:**
- Purpose-built for multi-agent orchestration (our 8 agents)
- Team-based coordination (agents can call each other)
- Workflow support for sequential processes
- Persistent agent state via PostgreSQL
- Built on FastAPI (not a wrapper)
- 100+ integrations (Slack, GitHub, PostgreSQL)
- Model-agnostic (Claude, GPT, open models)

**Agno Concepts:**

1. **Agent**: Single autonomous entity with tools, a model, and memory.
   ```python
   from agno.agent import Agent
   from agno.tools.github import GithubTools

   triage_agent = Agent(
       name="Triage Agent",
       model="claude-opus-4",
       tools=[
           SlackTools(),
           VectorSearchTools(),
           GitHubTools(),
       ],
       memory=PostgresAgentMemory(table="agent_memory"),
       description="Handles feature intake from Slack",
   )
   ```

2. **Team**: Coordinated group of agents that can delegate to each other.
   ```python
   from agno.team import Team

   dev_ops_team = Team(
       agents=[
           triage_agent,
           prd_agent,
           status_agent,
           standup_agent,
           learning_agent,
           bug_linker_agent,
           reassignment_agent,
           skill_agent,
       ],
       memory=PostgresAgentMemory(table="team_memory"),
   )
   ```

3. **Workflow**: Sequential multi-step execution (optional; can use Teams for orchestration).
   ```python
   from agno.workflow import Workflow

   prd_creation_workflow = Workflow(
       name="Create PRD",
       steps=[
           WorkflowStep(agent=triage_agent, task="Analyze intake form"),
           WorkflowStep(agent=prd_agent, task="Generate PRD draft"),
           WorkflowStep(agent=status_agent, task="Create repo structure"),
       ],
   )
   ```

**Tool Definition (Agno Pattern):**
```python
from agno.tools import Tool

class VectorSearchTools:
    def search_prd_embeddings(
        self,
        query: str,
        org_id: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Search PRDs by semantic similarity."""
        results = vector_search_service.search(
            query=query,
            org_id=org_id,
            table="prd_documents",
            top_k=top_k,
        )
        return results

    def search_code_embeddings(
        self,
        query: str,
        org_id: str,
        repo: str = None,
    ) -> list[dict]:
        """Search code by semantic similarity."""
        # Implementation
        pass

vector_search_tools = Tool(VectorSearchTools())
```

### 2.3 Vue 3 Frontend with Composition API

**Technology Stack:**
```json
{
  "dependencies": {
    "vue": "^3.3.8",
    "vue-router": "^4.2.5",
    "pinia": "^2.1.6",
    "axios": "^1.6.5",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.3.3"
  }
}
```

**Key Features:**
- **Composition API** for reactive state management and reusable logic
- **Pinia** for global state (org context, auth, cache)
- **Real-time Updates**: WebSocket integration for live standup/metric updates
- **Responsive Design**: Mobile-first, Tailwind CSS

**Core Stores (Pinia):**
```typescript
// stores/orgStore.ts
import { defineStore } from 'pinia'

export const useOrgStore = defineStore('org', () => {
  const currentOrg = ref<Organization | null>(null)
  const allOrgs = ref<Organization[]>([])

  const switchOrg = async (orgId: string) => {
    currentOrg.value = await api.get(`/api/orgs/${orgId}`)
  }

  const fetchOrgs = async () => {
    allOrgs.value = await api.get('/api/orgs')
  }

  return { currentOrg, allOrgs, switchOrg, fetchOrgs }
})

// stores/authStore.ts
export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<User | null>(null)

  const login = async (email: string, password: string) => {
    const response = await api.post('/api/auth/login', { email, password })
    token.value = response.token
    user.value = response.user
    localStorage.setItem('token', token.value)
  }

  return { token, user, login, logout }
})
```

### 2.4 PostgreSQL 16 + pgvector

**Why PostgreSQL:**
- Single source of truth for all data (no separate vector DB)
- ACID transactions (PRD metadata + embeddings in one transaction)
- Row-level security (org isolation)
- pgvector extension for semantic search
- HNSW index for fast approximate nearest neighbor search
- Excellent JSON/JSONB support for flexible schemas
- Native async support via asyncpg

**pgvector Configuration:**
```sql
-- Install extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create a vector column (1536 dims for OpenAI text-embedding-3-small)
ALTER TABLE prd_documents ADD COLUMN embedding vector(1536);

-- Create HNSW index for fast search
CREATE INDEX prd_embedding_idx ON prd_documents
USING hnsw (embedding vector_cosine_ops)
WITH (m = 30, ef_construction = 200);

-- Query example (cosine similarity)
SELECT id, title, 1 - (embedding <=> query_vector) as similarity
FROM prd_documents
WHERE org_id = $1
ORDER BY embedding <=> query_vector
LIMIT 5;
```

### 2.5 GitHub Apps for Integration

**Installation Flow:**
1. Org admin visits Bodhiorchard dashboard
2. Clicks "Connect GitHub Organization"
3. Redirected to GitHub OAuth approval
4. User grants Bodhiorchard app access to:
   - Code repos (read access)
   - PR/merge events (webhooks)
   - Workflow runs (check status)
5. Bodhiorchard stores GitHub App installation token in `organizations.github_app_token`

**Webhook Events:**
```python
# /api/webhooks/github
# Receives: pull_request.opened, pull_request.closed, pull_request.synchronize
# Payload signature validation via X-Hub-Signature-256 header

@app.post("/api/webhooks/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    org = await validate_github_signature(request)
    payload = await request.json()

    if payload['action'] == 'opened':
        background_tasks.add_task(triage_agent.process_pr_opened, payload, org)
    elif payload['action'] == 'closed' and payload['pull_request']['merged']:
        background_tasks.add_task(status_agent.process_pr_merged, payload, org)

    return {"status": "received"}
```

**Permissions Required:**
```yaml
Repository Permissions:
  - contents: read (to search code)
  - pull_requests: read (to track PRs)
  - workflows: read (to check CI status)

Organization Permissions:
  - members: read (to list team)
  - administration: read (to detect config changes)
```

### 2.6 Slack Bot (Events API + Slash Commands)

**Slack App Configuration:**
```yaml
app_id: your-app-id
signing_secret: your-signing-secret

Event Subscriptions:
  - message.channels (feature requests)
  - app_mention (questions/updates)

Slash Commands:
  - /bodhiorchard-request (submit feature request)
  - /bodhiorchard-status (check PRD status)
  - /bodhiorchard-assign (manually assign dev)
  - /bodhiorchard-capacity (view team capacity)
```

**Request Signing Validation:**
```python
from slack_sdk.signature import SignatureVerifier

verifier = SignatureVerifier(signing_secret=SLACK_SIGNING_SECRET)

@app.post("/api/webhooks/slack")
async def slack_webhook(request: Request):
    body = await request.body()
    headers = request.headers

    if not verifier.is_valid_request(body, headers):
        return {"error": "invalid signature"}, 401

    payload = json.loads(body)

    if payload['type'] == 'url_verification':
        return {"challenge": payload['challenge']}

    if payload['type'] == 'event_callback':
        background_tasks.add_task(route_slack_event, payload)

    return {"ok": True}
```
## 3. API Specification

All endpoints require JWT bearer token: `Authorization: Bearer <token>`

### 3.1 Auth & Orgs

#### POST /api/auth/login
**Public endpoint** (no auth required)

Request:
```json
{
  "email": "user@example.com",
  "password": "secure_password"
}
```

Response (200):
```json
{
  "token": "eyJhbGc...",
  "user": {
    "id": "uuid",
    "name": "John Doe",
    "email": "user@example.com",
    "role": "admin"
  },
  "orgs": [
    {
      "id": "org-uuid",
      "name": "Acme Corp",
      "slug": "acme"
    }
  ]
}
```

---

#### POST /api/auth/signup
**Public endpoint** (no auth required)

Request:
```json
{
  "email": "user@example.com",
  "password": "secure_password",
  "name": "John Doe",
  "org_name": "My Company",
  "org_slug": "my-company"
}
```

Response (201):
```json
{
  "token": "eyJhbGc...",
  "user": { ... },
  "org": {
    "id": "org-uuid",
    "name": "My Company",
    "slug": "my-company"
  }
}
```

---

#### GET /api/orgs
**Auth**: Any authenticated user

Response (200):
```json
{
  "orgs": [
    {
      "id": "org-uuid",
      "name": "Acme Corp",
      "slug": "acme",
      "role": "admin",
      "config": {
        "bug_threshold_multiplier": 2.5,
        "standup_time": "08:30",
        "github_org": "acme-github",
        "slack_workspace": "acme.slack.com"
      }
    }
  ]
}
```

---

#### GET /api/orgs/:id
**Auth**: User must belong to org

Response (200):
```json
{
  "id": "org-uuid",
  "name": "Acme Corp",
  "slug": "acme",
  "members": [
    {
      "id": "user-uuid",
      "name": "John Doe",
      "email": "john@acme.com",
      "role": "admin",
      "slack_id": "U12345"
    }
  ],
  "config": { ... }
}
```

---

#### PUT /api/orgs/:id/config
**Auth**: Admin only

Request:
```json
{
  "bug_threshold_multiplier": 3.0,
  "standup_time": "09:00",
  "standup_enabled": true,
  "notification_channels": ["#dev-updates"],
  "github_org": "acme-github",
  "slack_workspace_url": "acme.slack.com"
}
```

Response (200):
```json
{
  "id": "org-uuid",
  "config": { ... },
  "updated_at": "2026-03-05T10:30:00Z"
}
```

---

#### POST /api/orgs/:id/github/connect
**Auth**: Admin only

Request:
```json
{
  "installation_id": "12345",
  "access_token": "ghu_..."
}
```

Response (200):
```json
{
  "status": "connected",
  "github_org": "acme-github"
}
```

---

#### POST /api/orgs/:id/slack/connect
**Auth**: Admin only

Request:
```json
{
  "bot_token": "xoxb-...",
  "signing_secret": "..."
}
```

Response (200):
```json
{
  "status": "connected",
  "workspace": "acme.slack.com"
}
```

---

### 3.2 PRD Management

#### POST /api/prd
**Auth**: PM or Admin

Request:
```json
{
  "title": "Stripe Billing Integration",
  "description": "Integrate Stripe for recurring subscriptions",
  "business_impact": "Critical - enables recurring revenue",
  "estimated_complexity": 8,
  "estimated_days": 10,
  "assignees": ["user-uuid-1", "user-uuid-2"]
}
```

Response (201):
```json
{
  "id": "prd-uuid",
  "prd_number": 2026001,
  "title": "Stripe Billing Integration",
  "status": "draft",
  "content_md": "# Stripe Billing Integration\n\n...",
  "metadata": {
    "assignees": [...],
    "complexity_score": 8,
    "estimated_days": 10,
    "created_at": "2026-03-05T10:00:00Z"
  },
  "repo_path": "active/PRD-2026-001"
}
```

---

#### GET /api/prd
**Auth**: Authenticated user

Query Params:
- `status`: draft | design | tech-spec | in-dev | in-qa | in-uat | deployed
- `assignee`: user-uuid
- `search`: free text search (uses vector DB)
- `page`: pagination

Response (200):
```json
{
  "prds": [
    {
      "id": "prd-uuid",
      "prd_number": 2026001,
      "title": "Stripe Billing Integration",
      "status": "in-dev",
      "assignees": [...],
      "created_at": "2026-03-05T10:00:00Z",
      "updated_at": "2026-03-05T14:30:00Z"
    }
  ],
  "total": 42,
  "page": 1,
  "limit": 20
}
```

---

#### GET /api/prd/:id
**Auth**: Authenticated user

Response (200):
```json
{
  "id": "prd-uuid",
  "prd_number": 2026001,
  "title": "Stripe Billing Integration",
  "status": "in-dev",
  "content_md": "# Stripe Billing Integration\n\n## Overview\n...",
  "tech_spec_md": "# Technical Specification\n\n...",
  "test_plan_md": "# Test Plan\n\n...",
  "metadata": {
    "assignees": ["user-uuid-1"],
    "complexity_score": 8,
    "estimated_days": 10,
    "linked_prs": ["PR-123", "PR-124"],
    "created_at": "2026-03-05T10:00:00Z",
    "status_transitions": [
      { "from": "draft", "to": "design", "at": "2026-03-05T11:00:00Z" }
    ]
  },
  "bugs": [
    {
      "id": "bug-uuid",
      "title": "Payment fails on retry",
      "severity": "high",
      "status": "open"
    }
  ]
}
```

---

#### PUT /api/prd/:id
**Auth**: Author or Admin

Request:
```json
{
  "title": "Stripe Billing Integration v2",
  "content_md": "...",
  "tech_spec_md": "...",
  "test_plan_md": "...",
  "assignees": ["user-uuid-1", "user-uuid-2"]
}
```

Response (200):
```json
{
  "id": "prd-uuid",
  "updated_at": "2026-03-05T15:00:00Z"
}
```

---

#### PUT /api/prd/:id/status
**Auth**: PM or Admin

Request:
```json
{
  "status": "in-qa",
  "reason": "Implementation complete, ready for QA testing"
}
```

Response (200):
```json
{
  "id": "prd-uuid",
  "status": "in-qa",
  "status_changed_at": "2026-03-05T16:00:00Z"
}
```

Allowed Transitions:
- `draft` → `design`
- `design` → `tech-spec`
- `tech-spec` → `in-dev`
- `in-dev` → `in-qa`
- `in-qa` → `in-uat`
- `in-uat` → `deployed`
- Any status → `draft` (reopen)

---

#### DELETE /api/prd/:id
**Auth**: Author or Admin

Response (204 No Content)

---

#### GET /api/prd/search
**Auth**: Authenticated user

Query Params:
- `q`: search query (semantic + metadata)
- `type`: prd | bug | rule
- `org_id`: (required)

Response (200):
```json
{
  "results": [
    {
      "type": "prd",
      "id": "prd-uuid",
      "title": "Stripe Billing Integration",
      "status": "in-dev",
      "similarity": 0.94
    },
    {
      "type": "bug",
      "id": "bug-uuid",
      "title": "Payment fails on retry",
      "prd_id": "prd-uuid",
      "similarity": 0.87
    }
  ]
}
```

---

### 3.3 Bug Management

#### POST /api/bug
**Auth**: QA, Dev, or Admin

Request:
```json
{
  "title": "Payment fails on retry with 3D Secure",
  "description": "When a payment fails due to 3D Secure...",
  "severity": "high",
  "module": "payments",
  "reporter_id": "user-uuid"
}
```

Response (201):
```json
{
  "id": "bug-uuid",
  "title": "Payment fails on retry with 3D Secure",
  "status": "open",
  "severity": "high",
  "linked_prd_id": "prd-uuid",
  "linked_prd_title": "Stripe Billing Integration",
  "created_at": "2026-03-05T14:30:00Z"
}
```

---

#### GET /api/bug
**Auth**: Authenticated user

Query Params:
- `status`: open | in-progress | resolved | closed
- `prd_id`: filter by PRD
- `severity`: low | medium | high | critical
- `page`: pagination

Response (200):
```json
{
  "bugs": [
    {
      "id": "bug-uuid",
      "title": "Payment fails on retry",
      "severity": "high",
      "status": "open",
      "prd_id": "prd-uuid",
      "created_at": "2026-03-05T14:30:00Z"
    }
  ],
  "total": 12,
  "page": 1
}
```

---

#### PUT /api/bug/:id/status
**Auth**: QA, Dev, or Admin

Request:
```json
{
  "status": "in-progress",
  "assignee_id": "user-uuid"
}
```

Response (200):
```json
{
  "id": "bug-uuid",
  "status": "in-progress",
  "assignee_id": "user-uuid",
  "updated_at": "2026-03-05T15:00:00Z"
}
```

---

#### GET /api/prd/:id/bugs/threshold
**Auth**: Authenticated user

Response (200):
```json
{
  "prd_id": "prd-uuid",
  "total_bugs": 8,
  "critical_bugs": 2,
  "threshold_exceeded": true,
  "threshold_multiplier": 2.5,
  "complexity_score": 8,
  "expected_max_bugs": 20,
  "action_triggered": {
    "agent": "reassignment",
    "triggered_at": "2026-03-05T15:30:00Z",
    "reassignments": [
      { "user_id": "user-uuid", "old_prd": "prd-uuid", "reason": "Bug threshold exceeded" }
    ]
  }
}
```

---

### 3.4 Skill Profiles

#### GET /api/users/:id/skill-profile
**Auth**: Authenticated user in org

Response (200):
```json
{
  "user_id": "user-uuid",
  "name": "Priya Chen",
  "expertise": [
    {
      "module": "payments",
      "repos": ["api", "billing-service"],
      "languages": ["python", "typescript"],
      "skill_score": 0.95,
      "last_touch": "2026-02-28T10:00:00Z",
      "touch_count": 47
    },
    {
      "module": "auth",
      "repos": ["api"],
      "languages": ["python"],
      "skill_score": 0.75,
      "last_touch": "2026-02-15T14:30:00Z",
      "touch_count": 12
    }
  ],
  "bus_factor_alerts": [],
  "recommended_for": [
    {
      "prd_id": "prd-uuid",
      "title": "Stripe Billing Integration",
      "reason": "Highest expertise in payments module",
      "confidence": 0.94
    }
  ]
}
```

---

#### GET /api/orgs/:id/skill-profiles
**Auth**: Authenticated user in org

Response (200):
```json
{
  "profiles": [
    {
      "user_id": "user-uuid-1",
      "name": "Priya Chen",
      "expertise": [...],
      "bus_factor_alerts": []
    },
    {
      "user_id": "user-uuid-2",
      "name": "James Rodriguez",
      "expertise": [...],
      "bus_factor_alerts": [
        {
          "module": "auth-provider",
          "only_touched_by": ["James Rodriguez"],
          "risk_level": "critical"
        }
      ]
    }
  ]
}
```

---

#### POST /api/prd/:id/recommend-assignment
**Auth**: PM or Admin

Request: (empty body)

Response (200):
```json
{
  "recommendations": [
    {
      "user_id": "user-uuid-1",
      "name": "Priya Chen",
      "reason": "Highest expertise in payments module",
      "confidence": 0.94,
      "current_capacity": "80% utilized",
      "can_fit": true
    },
    {
      "user_id": "user-uuid-2",
      "name": "James Rodriguez",
      "reason": "Experience with Stripe API",
      "confidence": 0.72,
      "current_capacity": "40% utilized",
      "can_fit": true
    }
  ]
}
```

---

### 3.5 Standups

#### GET /api/standups/today
**Auth**: Authenticated user in org

Response (200):
```json
{
  "date": "2026-03-05",
  "generated_at": "2026-03-05T08:30:00Z",
  "standups": [
    {
      "user_id": "user-uuid-1",
      "name": "Priya Chen",
      "activity": {
        "commits": [
          { "repo": "api", "message": "Add stripe webhook handler", "files_changed": 3 }
        ],
        "prs_open": 1,
        "prs_under_review": 0,
        "prs_merged_since_last_standup": 1,
        "bugs_filed": 0,
        "prd_status_changes": 0
      },
      "flags": [
        {
          "type": "design_change",
          "prd_id": "prd-uuid",
          "description": "PRD scope expanded to include refund handling"
        }
      ]
    }
  ],
  "summary": "2 commits, 1 merged PR, no blockers detected",
  "posted_to_slack": true
}
```

---

#### POST /api/standups/generate
**Auth**: Admin only

Request:
```json
{
  "date": "2026-03-05"
}
```

Response (200):
```json
{
  "date": "2026-03-05",
  "standups": [...],
  "posted_to_slack": true
}
```

---

### 3.6 Capacity Planning

#### GET /api/orgs/:id/capacity
**Auth**: Authenticated user in org

Response (200):
```json
{
  "org_id": "org-uuid",
  "total_devs": 5,
  "workload": [
    {
      "user_id": "user-uuid-1",
      "name": "Priya Chen",
      "assigned_prds": [
        {
          "prd_id": "prd-uuid-1",
          "title": "Stripe Billing",
          "status": "in-dev",
          "complexity": 8,
          "estimated_days_remaining": 3
        },
        {
          "prd_id": "prd-uuid-2",
          "title": "Fraud Detection",
          "status": "in-qa",
          "complexity": 6,
          "estimated_days_remaining": 2
        }
      ],
      "utilization": "90%",
      "capacity_available": "2 days"
    }
  ],
  "team_utilization": "75%",
  "can_take_new_work": true,
  "recommendation": "Team has capacity for 1 more high-complexity feature this sprint"
}
```

---

### 3.7 Metrics & Dashboard

#### GET /api/orgs/:id/metrics
**Auth**: Authenticated user in org

Query Params:
- `period`: week | month | quarter
- `end_date`: YYYY-MM-DD (defaults to today)

Response (200):
```json
{
  "period": "month",
  "end_date": "2026-03-05",
  "cycle_time": {
    "mean_days": 8.5,
    "median_days": 7,
    "p95_days": 15,
    "trend": "improving"
  },
  "throughput": {
    "prd_deployed": 12,
    "trend": "stable"
  },
  "quality": {
    "mean_bugs_per_prd": 2.3,
    "critical_bugs": 1,
    "trend": "stable"
  },
  "team_health": {
    "bus_factor_alerts": 2,
    "high_utilization_devs": 1,
    "blockers": 0
  },
  "top_deployments": [
    {
      "prd_id": "prd-uuid",
      "title": "Stripe Billing Integration",
      "cycle_time_days": 6,
      "bugs_during_qa": 2,
      "status": "deployed"
    }
  ]
}
```

---

### 3.8 Agent Triggers (Manual)

#### POST /api/agents/triage/trigger
**Auth**: Admin only

Request:
```json
{
  "slack_message": "We need to add export to CSV feature",
  "channel_id": "C1234567",
  "user_id": "U1234567"
}
```

Response (202 Accepted):
```json
{
  "job_id": "job-uuid",
  "status": "processing",
  "agent": "triage",
  "estimated_completion": "2026-03-05T10:05:00Z"
}
```

---

#### GET /api/agents/:job_id/result
**Auth**: Authenticated user

Response (200):
```json
{
  "job_id": "job-uuid",
  "agent": "triage",
  "status": "completed",
  "input": { ... },
  "output": {
    "recommendation": {
      "action": "create_prd",
      "impact_score": 7,
      "complexity_estimate": 5,
      "estimated_days": 4,
      "trade_off_analysis": "Recommend deferring UI improvements to fit in exports feature"
    },
    "intake_summary": { ... }
  },
  "completed_at": "2026-03-05T10:04:30Z",
  "tokens_used": 2500
}
```

---

#### POST /api/agents/standup/trigger
**Auth**: Admin only

Request:
```json
{
  "date": "2026-03-05"
}
```

Response (202 Accepted):
```json
{
  "job_id": "job-uuid",
  "status": "processing",
  "agent": "standup",
  "estimated_completion": "2026-03-05T08:35:00Z"
}
```

---

### 3.9 Enterprise Rules

#### GET /api/enterprise-rules
**Auth**: Authenticated user in org

Query Params:
- `category`: business_logic | technical_standard
- `search`: free text

Response (200):
```json
{
  "rules": [
    {
      "id": "rule-uuid",
      "category": "business_logic",
      "title": "Subscription cancellation must include 30-day notice",
      "content_md": "...",
      "last_updated": "2026-02-28T14:00:00Z",
      "updated_by": "user-uuid"
    }
  ]
}
```

---

#### POST /api/enterprise-rules
**Auth**: Admin or PM

Request:
```json
{
  "category": "business_logic",
  "title": "Subscription cancellation must include 30-day notice",
  "content_md": "..."
}
```

Response (201):
```json
{
  "id": "rule-uuid",
  "category": "business_logic",
  "title": "Subscription cancellation must include 30-day notice",
  "created_at": "2026-03-05T10:00:00Z"
}
```

---
## 4. Agent Architecture (Detailed)

### Agent Interaction Diagram

```
                        ┌─────────────────────┐
                        │  GitHub Webhook     │
                        │  (PR merged)        │
                        └──────────┬──────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │    Status Agent             │
                    │ (webhook trigger)           │
                    └──────────────┬──────────────┘
                                   │
                  ┌────────────────┼────────────────┐
                  │                │                │
         ┌────────▼──────┐  ┌──────▼───────┐  ┌───▼──────────┐
         │ Learning Agent │  │ Vector Re-   │  │ Slack        │
         │ (if deployed)  │  │ index Trigger│  │ Notification │
         └────────────────┘  └──────────────┘  └──────────────┘


    ┌─────────────────────────┐
    │  Slack Feature Request  │
    │  (Events API)           │
    └────────────┬────────────┘
                 │
     ┌───────────▼────────────┐
     │    Triage Agent        │
     │ (Slack event trigger)  │
     └───────────┬────────────┘
                 │
      ┌──────────┼──────────┐
      │          │          │
      ▼          ▼          ▼
  [Exists?]  [Interview] [Estimate]
   Search    Questions   Code
    VectorDB   Slack     Search
               API       Github
                         API
      │          │          │
      └──────────┼──────────┘
                 │
     ┌───────────▼────────────┐
     │  PM Recommendation     │
     │  Posted to Slack       │
     └────────────────────────┘


  ┌──────────────────┐
  │  New Bug Filed   │
  │  (API or Slack)  │
  └────────┬─────────┘
           │
  ┌────────▼──────────────┐
  │  Bug Linker Agent     │
  │  (event trigger)      │
  └────────┬──────────────┘
           │
      [Link to PRD]
    [Check threshold]
           │
           ├─────────────────────┐
           │                     │
           ▼                     ▼
    [Threshold OK]    [Threshold Exceeded]
                            │
                   ┌────────▼─────────┐
                   │  Reassignment    │
                   │  Agent           │
                   │ (programmatic    │
                   │  trigger)        │
                   └────────┬─────────┘
                            │
                    [Reassign devs]
                    [Update plans]
                    [Slack notify]


┌──────────────────┐
│  Daily Cron      │
│  (08:30 AM)      │
└────────┬─────────┘
         │
  ┌──────▼──────────────┐
  │  Standup Agent      │
  │  (cron trigger)     │
  └──────┬──────────────┘
         │
    [Aggregate activity]
    [Detect flags]
    [Generate summary]
         │
         ▼
  [Post to Slack]


┌──────────────────────┐
│  PM Initiates PRD    │
│  (Dashboard/CLI)     │
└────────┬─────────────┘
         │
  ┌──────▼──────────────┐
  │  PRD Agent          │
  │  (manual trigger)   │
  └──────┬──────────────┘
         │
    [Research codebase]
    [Generate tech spec]
    [Generate test plan]
    [Create repo structure]
         │
         ▼
  [PRD folder in git repo]


┌─────────────────────────┐
│  PRD Status → deployed  │
│  (Status Agent)         │
└────────┬────────────────┘
         │
  ┌──────▼──────────────┐
  │  Learning Agent     │
  │  (event trigger)    │
  └──────┬──────────────┘
         │
   [Calculate metrics]
   [Analyze patterns]
   [Generate retrospective]
         │
         ▼
  [Embed in vector DB]


 ┌─────────────────┐
 │  Daily Rebuild  │
 │  (02:00 AM UTC) │
 └────────┬────────┘
          │
 ┌────────▼─────────┐
 │  Skill Agent     │
 │  (cron trigger)  │
 └────────┬─────────┘
          │
  [Git analysis]
  [PRD history]
  [Bug fixes]
          │
          ▼
  [Update skill profiles]
  [Calculate expertise]
```

---

### Agent 1: Triage Agent

**Agent Class Structure:**

```python
from agno.agent import Agent

class TriageAgent(Agent):
    def __init__(self, model: str = "claude-opus-4"):
        super().__init__(
            name="Triage Agent",
            model=model,
            description="Analyzes new feature requests from Slack and generates PM recommendations",
            tools=[
                SlackTools(),
                VectorSearchTools(),
                GitHubTools(),
                PRDRepoTools(),
            ],
            memory=PostgresAgentMemory(
                table="agent_memory_triage",
                db_url=DB_URL,
            ),
            # Agent executes with timeout
            execution_timeout=600,
        )

    async def process_slack_message(
        self,
        message_text: str,
        channel_id: str,
        user_id: str,
        org_id: str,
    ) -> TriageResult:
        """Main entry point for Slack-triggered triage."""

        # Step 1: Search for similar existing PRDs
        existing_match = await self.search_existing_prds(message_text, org_id)

        if existing_match and existing_match.similarity > 0.85:
            # Found a match
            return TriageResult(
                action="existing_prd",
                matched_prd=existing_match,
                slack_response=f"This looks like {existing_match.title}, "
                               f"currently {existing_match.status}. "
                               f"Estimated completion: {existing_match.est_completion}",
            )

        # Step 2: Run structured intake interview in Slack thread
        intake_data = await self.run_intake_interview(message_text, channel_id, user_id, org_id)

        # Step 3: Estimate complexity
        complexity_estimate = await self.estimate_complexity(intake_data, org_id)

        # Step 4: Generate PM recommendation
        recommendation = await self.generate_pm_recommendation(
            intake_data,
            complexity_estimate,
            org_id,
        )

        # Step 5: Post recommendation to Slack
        await slack_tools.post_message(
            channel=channel_id,
            text=f"Feature Recommendation for: {intake_data['feature_name']}",
            blocks=self.format_recommendation_blocks(recommendation),
            thread_ts=message_text.thread_ts,
        )

        return TriageResult(
            action="new_prd",
            recommendation=recommendation,
            intake_data=intake_data,
        )

triage_agent = TriageAgent()
```

**Tools Used:**

```python
class TriageAgent(Agent):
    # Tool 1: Vector search across PRDs and enterprise rules
    async def search_existing_prds(
        self,
        query: str,
        org_id: str,
    ) -> Optional[PRDMatch]:
        """Search vector DB for semantically similar PRDs."""
        results = await vector_search_tools.search_prd_embeddings(
            query=query,
            org_id=org_id,
            top_k=3,
        )
        if results and results[0]['similarity'] > 0.80:
            return PRDMatch(
                prd_id=results[0]['id'],
                title=results[0]['title'],
                status=results[0]['metadata']['status'],
                similarity=results[0]['similarity'],
                est_completion=results[0]['metadata'].get('est_deploy_date'),
            )
        return None

    # Tool 2: Slack intake interview
    async def run_intake_interview(
        self,
        initial_message: str,
        channel_id: str,
        user_id: str,
        org_id: str,
    ) -> IntakeData:
        """Run structured Slack interview to gather feature details."""
        interview_questions = [
            "What is the business impact? (revenue, customer satisfaction, technical debt)",
            "Which customer(s) are requesting this?",
            "What is the timeline urgency? (ASAP, this month, this quarter, nice-to-have)",
            "Are there any dependencies or blockers?",
        ]

        responses = {}
        for i, question in enumerate(interview_questions):
            # Post question in thread
            await slack_tools.post_message(
                channel=channel_id,
                text=question,
                thread_ts=initial_message.thread_ts,
            )

            # Wait for response (timeout 5 min, user cancels with "skip")
            response = await self.wait_for_slack_response(
                channel_id,
                user_id,
                timeout=300,
            )
            responses[f"q{i+1}"] = response

        return IntakeData(
            feature_name=initial_message.text,
            business_impact=responses.get('q1'),
            customer_context=responses.get('q2'),
            urgency=responses.get('q3'),
            blockers=responses.get('q4'),
        )

    # Tool 3: Estimate complexity via code search
    async def estimate_complexity(
        self,
        intake_data: IntakeData,
        org_id: str,
    ) -> ComplexityEstimate:
        """Search codebase to estimate implementation complexity."""
        # Search for related code
        code_results = await vector_search_tools.search_code_embeddings(
            query=intake_data.feature_name,
            org_id=org_id,
            top_k=5,
        )

        # Analyze affected modules
        affected_modules = set()
        for result in code_results:
            affected_modules.add(result['metadata']['module'])

        # Estimate based on LLM + code analysis
        estimate_prompt = f"""
        Feature: {intake_data.feature_name}
        Affected modules: {', '.join(affected_modules)}
        Related code snippets: {[r['content'] for r in code_results]}

        Estimate implementation complexity (1-10) and days needed.
        Return JSON:
        {{
          "complexity_score": <1-10>,
          "estimated_days": <int>,
          "rationale": "<explanation>"
        }}
        """

        response = await self.model.agenerate(estimate_prompt)
        estimate = json.loads(response)

        return ComplexityEstimate(
            score=estimate['complexity_score'],
            days=estimate['estimated_days'],
            affected_modules=list(affected_modules),
        )

    # Tool 4: Generate PM recommendation
    async def generate_pm_recommendation(
        self,
        intake_data: IntakeData,
        complexity: ComplexityEstimate,
        org_id: str,
    ) -> PMRecommendation:
        """Generate recommendation with trade-off analysis."""

        # Get current capacity
        capacity = await capacity_service.get_team_capacity(org_id)

        # Get PRDs in dev/qa to analyze deprioritization options
        active_prds = await prd_service.get_prds_by_status(
            org_id,
            status=['in-dev', 'in-qa'],
        )

        prompt = f"""
        New Feature Request:
        - {intake_data.feature_name}
        - Business Impact: {intake_data.business_impact}
        - Urgency: {intake_data.urgency}
        - Estimated complexity: {complexity.score}/10
        - Estimated timeline: {complexity.days} days

        Team Capacity:
        - Total developer capacity: {capacity.available_days} days
        - Current utilization: {capacity.utilization}%
        - Currently in-flight: {len(active_prds)} features

        Generate a PM recommendation JSON:
        {{
          "recommendation": "build|defer|negotiate",
          "impact_score": <1-10>,
          "reasoning": "<explanation>",
          "deprioritization_options": [
            {{
              "prd_id": "<id>",
              "title": "<title>",
              "reason": "<why this could be deferred>"
            }}
          ]
        }}
        """

        response = await self.model.agenerate(prompt)
        rec_data = json.loads(response)

        return PMRecommendation(
            action=rec_data['recommendation'],
            impact_score=rec_data['impact_score'],
            reasoning=rec_data['reasoning'],
            deprioritization_options=rec_data['deprioritization_options'],
            requested_by=intake_data.requested_by,
        )
```

**Trigger Mechanism:**

```python
# Slack Events API → webhook router → triage agent
@app.post("/api/webhooks/slack")
async def slack_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await validate_slack_request(request)

    if payload['type'] == 'event_callback':
        event = payload['event']

        # Trigger on message in #feature-requests channel
        if event['type'] == 'message' and event.get('channel') == 'C_FEATURE_REQUESTS':
            org = await org_service.get_org_by_slack_channel(event['channel'])

            background_tasks.add_task(
                triage_agent.process_slack_message,
                message_text=event['text'],
                channel_id=event['channel'],
                user_id=event['user'],
                org_id=org.id,
            )

    return {"ok": True}
```

**Input/Output Schema:**

```python
from pydantic import BaseModel

class TriageInput(BaseModel):
    message_text: str
    channel_id: str
    user_id: str
    org_id: uuid.UUID

class IntakeData(BaseModel):
    feature_name: str
    business_impact: str
    customer_context: str
    urgency: str  # ASAP | This Month | Q | Nice-to-Have
    blockers: str | None

class ComplexityEstimate(BaseModel):
    score: int  # 1-10
    days: int
    affected_modules: list[str]

class PMRecommendation(BaseModel):
    action: str  # build | defer | negotiate
    impact_score: int  # 1-10
    reasoning: str
    deprioritization_options: list[dict]
    requested_by: str

class TriageOutput(BaseModel):
    action: str  # existing_prd | new_prd
    matched_prd: Optional[PRDMatch]
    recommendation: Optional[PMRecommendation]
    intake_data: Optional[IntakeData]
```

**Interaction with Other Agents:**

- **Calls PRD Agent** (after PM approval) to auto-generate PRD
- **Reads from Skill Agent** (on-demand) to get assignment recommendations
- **Queries Status Agent** indirectly via vector DB for existing PRD status

---

### Agent 2: PRD Agent

**Agent Class Structure:**

```python
class PRDAgent(Agent):
    def __init__(self, model: str = "claude-opus-4"):
        super().__init__(
            name="PRD Agent",
            model=model,
            description="Co-authors PRDs with PMs, generates tech specs and test plans",
            tools=[
                VectorSearchTools(),
                GitHubTools(),
                PRDRepoTools(),
                TemplateEngine(),
            ],
            memory=PostgresAgentMemory(table="agent_memory_prd"),
        )

    async def create_prd(
        self,
        title: str,
        description: str,
        business_impact: str,
        estimated_complexity: int,
        estimated_days: int,
        assignees: list[str],
        org_id: uuid.UUID,
    ) -> PRDDocument:
        """Create PRD with auto-generated sections."""

        # Step 1: Search for relevant enterprise rules and prior art
        enterprise_rules = await vector_search_tools.search_enterprise_rules(
            query=title,
            org_id=org_id,
        )

        code_context = await vector_search_tools.search_code_embeddings(
            query=f"{title} {description}",
            org_id=org_id,
            top_k=10,
        )

        # Step 2: Generate PRD content
        prd_content = await self.generate_prd_content(
            title=title,
            description=description,
            business_impact=business_impact,
            enterprise_rules=enterprise_rules,
            code_context=code_context,
        )

        # Step 3: Generate tech spec
        tech_spec = await self.generate_tech_spec(
            prd_content=prd_content,
            code_context=code_context,
        )

        # Step 4: Generate test plan
        test_plan = await self.generate_test_plan(
            prd_content=prd_content,
            tech_spec=tech_spec,
        )

        # Step 5: Create PRD folder in repo
        prd_folder = await prd_repo_tools.create_prd_folder(
            org_id=org_id,
            prd_number=await prd_service.get_next_prd_number(org_id),
            title=title,
            prd_md=prd_content,
            tech_spec_md=tech_spec,
            test_plan_md=test_plan,
            metadata={
                'assignees': assignees,
                'complexity_score': estimated_complexity,
                'estimated_days': estimated_days,
                'created_at': datetime.utcnow().isoformat(),
            },
        )

        # Step 6: Store in DB and trigger embedding
        prd = await prd_service.create_prd(
            org_id=org_id,
            title=title,
            content_md=prd_content,
            tech_spec_md=tech_spec,
            test_plan_md=test_plan,
            metadata={
                'repo_path': prd_folder,
                'assignees': assignees,
                'complexity_score': estimated_complexity,
                'estimated_days': estimated_days,
            },
        )

        # Step 7: Trigger embedding service
        background_tasks.add_task(
            embedding_service.embed_and_index,
            prd_id=prd.id,
            org_id=org_id,
            content=prd_content,
        )

        return prd

prd_agent = PRDAgent()
```

**Tools:**

```python
class PRDAgent(Agent):
    async def generate_prd_content(
        self,
        title: str,
        description: str,
        business_impact: str,
        enterprise_rules: list[dict],
        code_context: list[dict],
    ) -> str:
        """LLM-generated PRD content based on context."""

        prompt = f"""
        You are a product manager writing a detailed PRD.

        Title: {title}
        Description: {description}
        Business Impact: {business_impact}

        Relevant Enterprise Rules:
        {json.dumps(enterprise_rules, indent=2)}

        Related Code:
        {json.dumps(code_context[:3], indent=2)}

        Generate a comprehensive PRD in Markdown with:
        - Overview
        - Goals & Success Metrics
        - User Stories
        - Requirements & Constraints
        - Acceptance Criteria
        - Out of Scope
        - Dependencies
        - Risks
        """

        content = await self.model.agenerate(prompt)
        return content

    async def generate_tech_spec(
        self,
        prd_content: str,
        code_context: list[dict],
    ) -> str:
        """Generate technical specification."""

        prompt = f"""
        Based on this PRD and code context, generate a detailed Technical Specification.

        PRD:
        {prd_content}

        Related Code Modules:
        {json.dumps(code_context[:5], indent=2)}

        Generate Tech Spec with:
        - Architecture Overview
        - Data Models
        - API Endpoints
        - Database Changes
        - Integration Points
        - Performance Considerations
        - Security Implications
        """

        tech_spec = await self.model.agenerate(prompt)
        return tech_spec

    async def generate_test_plan(
        self,
        prd_content: str,
        tech_spec: str,
    ) -> str:
        """Generate test plan."""

        prompt = f"""
        Based on this PRD and tech spec, generate a comprehensive Test Plan.

        PRD:
        {prd_content}

        Tech Spec:
        {tech_spec}

        Generate Test Plan with:
        - Unit Test Coverage
        - Integration Test Scenarios
        - End-to-End Test Cases
        - Performance Test Cases
        - Security Test Cases
        - UAT Scenarios
        - Regression Tests
        """

        test_plan = await self.model.agenerate(prompt)
        return test_plan
```

**Trigger & Input/Output Schema:**

```python
class PRDAgentInput(BaseModel):
    title: str
    description: str
    business_impact: str
    estimated_complexity: int
    estimated_days: int
    assignees: list[uuid.UUID]
    org_id: uuid.UUID

class PRDAgentOutput(BaseModel):
    prd_id: uuid.UUID
    prd_number: int
    title: str
    repo_path: str
    created_at: datetime
    status: str = "draft"
```

---

### Agent 3: Status Agent

**Responsibilities:**

```python
class StatusAgent(Agent):
    """Monitors PR merges and updates PRD statuses."""

    async def process_pr_merged(
        self,
        pr_payload: GitHubPullRequestPayload,
        org_id: uuid.UUID,
    ):
        """Handle PR merge event."""

        # Step 1: Extract PRD reference from branch or description
        prd_ref = self.extract_prd_reference(
            pr_payload.head.ref,  # branch name
            pr_payload.body,      # PR description
        )

        if not prd_ref:
            logger.info(f"PR {pr_payload.number} has no PRD reference, skipping")
            return

        prd = await prd_service.get_prd_by_number(org_id, prd_ref)

        # Step 2: Determine new status based on branch
        new_status = self.determine_new_status(
            base_branch=pr_payload.base.ref,
            current_status=prd.status,
        )

        # Step 3: Update PRD metadata
        await prd_service.update_prd_status(
            prd_id=prd.id,
            new_status=new_status,
            linked_pr=pr_payload.html_url,
        )

        # Step 4: If deployed, move PRD folder from active/ to deployed/
        if new_status == "deployed":
            await prd_repo_tools.move_prd_folder(
                org_id=org_id,
                prd_id=prd.id,
                from_path=f"active/PRD-{prd.prd_number}",
                to_path=f"deployed/PRD-{prd.prd_number}",
            )

            # Trigger Learning Agent
            background_tasks.add_task(
                learning_agent.analyze_deployment,
                prd_id=prd.id,
                org_id=org_id,
            )

        # Step 5: Check for enterprise rule changes
        await self.detect_rule_changes(pr_payload, org_id)

        # Step 6: Trigger vector re-indexing
        background_tasks.add_task(
            embedding_service.reindex_prd,
            prd_id=prd.id,
            org_id=org_id,
        )

    def extract_prd_reference(
        self,
        branch_name: str,
        pr_description: str,
    ) -> Optional[int]:
        """Extract PRD number from branch or PR description."""
        import re

        # Try branch name: feature/PRD-2026-042 or PRD-042
        pattern = r'PRD-(\d+)'
        match = re.search(pattern, branch_name)
        if match:
            return int(match.group(1))

        # Try PR description
        match = re.search(pattern, pr_description)
        if match:
            return int(match.group(1))

        return None

    def determine_new_status(
        self,
        base_branch: str,
        current_status: str,
    ) -> str:
        """Determine new PRD status based on merge branch."""

        if base_branch == "main":
            return "deployed"
        elif base_branch.startswith("release/") or base_branch.startswith("hotfix/"):
            return "in-uat"
        elif base_branch == "dev":
            return "in-dev"

        # Default: no change
        return current_status

    async def detect_rule_changes(
        self,
        pr_payload: GitHubPullRequestPayload,
        org_id: uuid.UUID,
    ):
        """Detect if PR affects enterprise rules."""

        # Get diff of PR
        diff = await github_tools.get_pr_diff(
            repo=pr_payload.repository,
            pr_number=pr_payload.number,
        )

        # Search for changes to enterprise-rules/*
        if "enterprise-rules/" in diff:
            # Flag for manual review OR auto-generate update PR
            affected_files = self.extract_affected_files(diff, "enterprise-rules/")

            logger.info(f"PR {pr_payload.number} affects enterprise rules: {affected_files}")

            # Could trigger automatic rule update or flag for review
            await slack_tools.post_message(
                channel="#dev-updates",
                text=f"PR {pr_payload.html_url} affects enterprise rules. Review required.",
            )

status_agent = StatusAgent()
```

---

### Agent 4: Standup Agent

**Responsibilities:**

```python
class StandupAgent(Agent):
    """Generates daily standup summaries."""

    async def generate_daily_standup(
        self,
        org_id: uuid.UUID,
        date: str = None,
    ) -> StandupReport:
        """Generate standup for entire team."""

        if not date:
            date = datetime.utcnow().date().isoformat()

        # Step 1: Get all team members
        team = await user_service.get_team_members(org_id)

        # Step 2: For each dev, aggregate activity
        standup_items = []
        for user in team:
            activity = await self.aggregate_dev_activity(
                user=user,
                org_id=org_id,
                date=date,
            )

            flags = await self.detect_flags(activity, org_id)

            standup_items.append(
                StandupItem(
                    user=user,
                    activity=activity,
                    flags=flags,
                )
            )

        # Step 3: Generate summary and post to Slack
        summary = await self.generate_summary(standup_items, org_id)

        slack_blocks = self.format_standup_blocks(standup_items, summary)

        slack_ts = await slack_tools.post_message(
            channel="#standup",
            text="Daily Standup",
            blocks=slack_blocks,
        )

        # Step 4: Store in DB
        report = await standup_service.create_report(
            org_id=org_id,
            date=date,
            content={
                'items': standup_items,
                'summary': summary,
                'slack_ts': slack_ts,
            },
        )

        return report

    async def aggregate_dev_activity(
        self,
        user: User,
        org_id: uuid.UUID,
        date: str,
    ) -> DevActivity:
        """Aggregate all activity for a developer."""

        # Get last standup timestamp (or 24h ago)
        last_standup = await standup_service.get_last_standup(org_id)
        since = (datetime.fromisoformat(last_standup or date) - timedelta(hours=1)).isoformat()

        # Get commits
        commits = await github_tools.get_commits(
            org=org.github_org,
            author=user.github_username,
            since=since,
        )

        # Get PR activity
        pr_activity = await github_tools.get_pr_activity(
            org=org.github_org,
            user=user.github_username,
            since=since,
        )

        # Get PRD status changes
        prd_changes = await prd_service.get_status_changes(
            org_id=org_id,
            user_id=user.id,
            since=since,
        )

        # Get bugs filed/resolved
        bugs = await bug_service.get_bugs(
            org_id=org_id,
            assignee_id=user.id,
            since=since,
        )

        # Get Slack discussion summary
        slack_summary = await slack_tools.get_thread_summary(
            channels=org.notification_channels,
            user_id=user.slack_id,
            since=since,
        )

        return DevActivity(
            user=user,
            commits=commits,
            pr_activity=pr_activity,
            prd_changes=prd_changes,
            bugs=bugs,
            slack_discussion=slack_summary,
        )

    async def detect_flags(
        self,
        activity: DevActivity,
        org_id: uuid.UUID,
    ) -> list[Flag]:
        """Detect risks and issues."""

        flags = []

        # Flag 1: No activity
        if not any([activity.commits, activity.pr_activity, activity.prd_changes]):
            flags.append(Flag(type="no_activity", severity="info"))

        # Flag 2: Lagging on PRD
        for prd_change in activity.prd_changes:
            if prd_change.status in ['in-dev', 'in-qa']:
                prd = await prd_service.get_prd(prd_change.prd_id)
                days_elapsed = (datetime.utcnow() - prd.created_at).days
                if days_elapsed > prd.metadata['estimated_days'] * 1.2:
                    flags.append(Flag(
                        type="prd_lagging",
                        severity="warning",
                        prd_id=prd.id,
                        days_over=days_elapsed - prd.metadata['estimated_days'],
                    ))

        # Flag 3: Design changes affecting in-flight work
        if activity.prd_changes:
            for change in activity.prd_changes:
                if change.change_type == "scope_expanded":
                    flags.append(Flag(
                        type="scope_change",
                        severity="warning",
                        prd_id=change.prd_id,
                        description=change.description,
                    ))

        # Flag 4: High bug count
        critical_bugs = [b for b in activity.bugs if b.severity == "critical"]
        if len(critical_bugs) > 0:
            flags.append(Flag(
                type="critical_bugs",
                severity="critical",
                count=len(critical_bugs),
            ))

        return flags

standup_agent = StandupAgent()
```

---

### Agent 5: Learning Agent

```python
class LearningAgent(Agent):
    """Analyzes completed features and generates learnings."""

    async def analyze_deployment(
        self,
        prd_id: uuid.UUID,
        org_id: uuid.UUID,
    ) -> FeatureLearning:
        """Analyze PRD and generate retrospective."""

        prd = await prd_service.get_prd(prd_id)

        # Step 1: Calculate cycle time
        cycle_time = self.calculate_cycle_time(prd)

        # Step 2: Get bug data
        bugs = await bug_service.get_bugs_for_prd(prd_id)

        # Step 3: Compare actual vs estimated
        estimates_vs_actual = {
            'estimated_days': prd.metadata['estimated_days'],
            'actual_days': cycle_time,
            'estimated_complexity': prd.metadata['complexity_score'],
            'actual_complexity': self.infer_actual_complexity(prd),
            'estimate_accuracy': (prd.metadata['estimated_days'] / max(cycle_time, 0.1)),
        }

        # Step 4: Analyze patterns
        similar_features = await self.find_similar_features(prd, org_id)
        patterns = self.analyze_patterns(prd, similar_features)

        # Step 5: Generate retrospective
        retrospective = await self.generate_retrospective(
            prd=prd,
            cycle_time=cycle_time,
            bugs=bugs,
            estimates=estimates_vs_actual,
            patterns=patterns,
        )

        # Step 6: Embed in vector DB
        learning = await learning_service.create_learning(
            org_id=org_id,
            prd_id=prd_id,
            cycle_time_days=cycle_time,
            bug_count=len(bugs),
            retrospective_md=retrospective,
        )

        background_tasks.add_task(
            embedding_service.embed_and_index,
            learning_id=learning.id,
            org_id=org_id,
            content=retrospective,
        )

        return learning

    def calculate_cycle_time(self, prd: PRDDocument) -> int:
        """Calculate days from creation to deployment."""
        created = prd.metadata['created_at']
        deployed = prd.metadata.get('deployed_at', datetime.utcnow())
        return (deployed - created).days

    async def generate_retrospective(
        self,
        prd: PRDDocument,
        cycle_time: int,
        bugs: list[Bug],
        estimates: dict,
        patterns: dict,
    ) -> str:
        """LLM-generated retrospective."""

        prompt = f"""
        Analyze this completed feature and generate a retrospective.

        Feature: {prd.title}
        Description: {prd.content_md[:500]}

        Metrics:
        - Cycle time: {cycle_time} days (estimated: {estimates['estimated_days']})
        - Bugs found: {len(bugs)} (severity: {json.dumps({b.severity for b in bugs})})
        - Complexity: {estimates['estimated_complexity']}/10 (actual: {estimates['actual_complexity']})

        Patterns Observed:
        {json.dumps(patterns, indent=2)}

        Generate a retrospective with:
        - What went well
        - What took longer than expected
        - Key blockers
        - Recommendations for future similar features
        - Estimate accuracy analysis
        """

        retrospective = await self.model.agenerate(prompt)
        return retrospective

learning_agent = LearningAgent()
```

---

### Agent 6: Bug Linker Agent

```python
class BugLinkerAgent(Agent):
    """Links bugs to PRDs and triggers reassignment if threshold exceeded."""

    async def process_new_bug(
        self,
        bug_title: str,
        bug_description: str,
        module: str,
        org_id: uuid.UUID,
    ) -> Bug:
        """Link bug to PRD and check threshold."""

        # Step 1: Search for related PRD
        related_prd = await self.find_related_prd(
            bug_title,
            bug_description,
            module,
            org_id,
        )

        # Step 2: Create bug
        bug = await bug_service.create_bug(
            org_id=org_id,
            title=bug_title,
            description=bug_description,
            linked_prd_id=related_prd.id if related_prd else None,
        )

        if not related_prd:
            return bug

        # Step 3: Check threshold
        threshold_exceeded = await self.check_threshold(related_prd, org_id)

        if threshold_exceeded:
            # Step 4: Trigger Reassignment Agent
            background_tasks.add_task(
                reassignment_agent.handle_threshold_exceeded,
                prd_id=related_prd.id,
                org_id=org_id,
            )

        # Step 5: Embed bug in vector DB
        background_tasks.add_task(
            embedding_service.embed_and_index,
            bug_id=bug.id,
            org_id=org_id,
            content=f"{bug.title}\n{bug.description}",
        )

        return bug

    async def find_related_prd(
        self,
        bug_title: str,
        bug_description: str,
        module: str,
        org_id: uuid.UUID,
    ) -> Optional[PRDDocument]:
        """Find PRD related to bug using vector search."""

        # Search in active PRDs
        results = await vector_search_tools.search_prd_embeddings(
            query=f"{bug_title} {bug_description}",
            org_id=org_id,
            filters={"status": ["in-dev", "in-qa", "in-uat"]},
            top_k=3,
        )

        # Filter by module match if possible
        for result in results:
            if result.get('metadata', {}).get('module') == module or result['similarity'] > 0.8:
                return await prd_service.get_prd(result['id'])

        return None

    async def check_threshold(
        self,
        prd: PRDDocument,
        org_id: uuid.UUID,
    ) -> bool:
        """Check if bug count exceeds threshold."""

        org_config = await org_service.get_org_config(org_id)
        threshold_multiplier = org_config.get('bug_threshold_multiplier', 2.0)

        complexity = prd.metadata['complexity_score']
        bug_count = await bug_service.count_bugs_for_prd(prd.id)

        threshold = complexity * threshold_multiplier

        return bug_count > threshold

bug_linker_agent = BugLinkerAgent()
```

---

### Agent 7: Reassignment Agent

```python
class ReassignmentAgent(Agent):
    """Reassigns devs and QA when bug threshold exceeded."""

    async def handle_threshold_exceeded(
        self,
        prd_id: uuid.UUID,
        org_id: uuid.UUID,
    ):
        """Reassign devs and QA."""

        prd = await prd_service.get_prd(prd_id)

        # Step 1: Reassign original dev to review
        original_devs = prd.metadata.get('assignees', [])
        for dev_id in original_devs:
            await prd_service.add_prd_assignee(
                prd_id=prd_id,
                user_id=dev_id,
                role="review",
            )

        # Step 2: Create sub-plans for review
        await prd_service.create_sub_plan(
            prd_id=prd_id,
            title="Code review and bug fixes",
            description="Review implementation and fix reported bugs",
        )

        # Step 3: Find and reassign available QA
        available_qa = await self.find_available_qa(org_id)
        if available_qa:
            # Get next waiting item (UAT PRD)
            next_prd = await self.find_next_waiting_prd(org_id)
            if next_prd:
                await prd_service.add_prd_assignee(
                    prd_id=next_prd.id,
                    user_id=available_qa.id,
                    role="qa",
                )

        # Step 4: Notify via Slack
        await slack_tools.post_message(
            channel="#dev-updates",
            text=f"Bug threshold exceeded for {prd.title}. {original_devs} reassigned for review.",
        )

reassignment_agent = ReassignmentAgent()
```

---

### Agent 8: Skill Agent

```python
class SkillAgent(Agent):
    """Tracks and analyzes developer skills."""

    async def rebuild_skill_profiles(self, org_id: uuid.UUID):
        """Rebuild skill profiles for all team members (daily cron)."""

        team = await user_service.get_team_members(org_id)

        for user in team:
            # Step 1: Get git history
            git_history = await github_tools.get_user_git_history(
                user=user.github_username,
                org=org.github_org,
                limit=1000,
            )

            # Step 2: Get PRD history
            prd_history = await prd_service.get_user_prd_history(
                user_id=user.id,
                org_id=org_id,
            )

            # Step 3: Get bug fix history
            bug_fixes = await bug_service.get_user_bug_fixes(
                user_id=user.id,
                org_id=org_id,
            )

            # Step 4: Analyze skills from git data
            skills = await self.analyze_skills(
                git_history=git_history,
                prd_history=prd_history,
                bug_fixes=bug_fixes,
            )

            # Step 5: Update skill profiles
            await skill_service.update_profile(
                user_id=user.id,
                org_id=org_id,
                skills=skills,
            )

            # Step 6: Detect bus factor alerts
            alerts = await self.detect_bus_factor_alerts(
                user=user,
                org_id=org_id,
                skills=skills,
            )

    async def recommend_assignment(
        self,
        prd: PRDDocument,
        org_id: uuid.UUID,
    ) -> list[UserRecommendation]:
        """Recommend developers for PRD assignment."""

        # Step 1: Analyze PRD requirements
        prd_skills = await self.extract_prd_skills(prd)

        # Step 2: Get all team members with skill profiles
        profiles = await skill_service.get_all_profiles(org_id)

        # Step 3: Score each member
        recommendations = []
        for user, profile in profiles:
            score = self.score_user_for_prd(
                user_skills=profile.expertise,
                prd_skills=prd_skills,
                user_capacity=await capacity_service.get_user_capacity(user.id, org_id),
            )

            recommendations.append(UserRecommendation(
                user=user,
                reason=score['reason'],
                confidence=score['confidence'],
                can_fit=score['can_fit'],
            ))

        # Sort by score
        recommendations.sort(key=lambda x: x['confidence'], reverse=True)

        return recommendations

skill_agent = SkillAgent()
```
## 5. Webhook & Event Flows

### 5.1 GitHub PR Merge → Status Update Flow

```
GitHub Event: pull_request (action: closed, merged: true)
     │
     ├─ Webhook sent to: POST /api/webhooks/github
     │
     ├─ Signature validation: X-Hub-Signature-256
     │
     ├─ Extract PR metadata:
     │  ├─ Branch name (e.g., "feature/PRD-2026-042")
     │  ├─ PR title & description
     │  ├─ Base branch (main, release/*, dev, hotfix/*)
     │  ├─ Files changed
     │  └─ Commits
     │
     ├─ Find PRD reference:
     │  ├─ Regex: "PRD-\d+" in branch or description
     │  └─ Get PRD metadata from DB
     │
     ├─ Determine new status:
     │  ├─ If merged to main → "deployed"
     │  ├─ If merged to release/* or hotfix/* → "in-uat"
     │  └─ If merged to dev → "in-dev"
     │
     ├─ Update PRD metadata.yaml:
     │  ├─ status: new status
     │  ├─ linked_prs: append PR URL
     │  ├─ status_transitions: append { from, to, at }
     │  └─ Commit change to PRD repo
     │
     ├─ If status → "deployed":
     │  ├─ Move PRD folder: active/PRD-X → deployed/PRD-X
     │  ├─ Trigger Learning Agent (analyze deployment)
     │  └─ Update dashboard metrics
     │
     ├─ Detect enterprise rule changes:
     │  ├─ Check if diff contains "enterprise-rules/*"
     │  ├─ If yes, flag or auto-generate update PR
     │  └─ Post notification to Slack (#dev-updates)
     │
     ├─ Trigger vector re-indexing:
     │  ├─ Fetch updated PRD content
     │  ├─ Generate embeddings
     │  ├─ Update pgvector table
     │  └─ Log embedding operation
     │
     └─ Notify Slack:
        ├─ Channel: #prd-updates
        └─ Message: "PRD-2026-042: Stripe Billing Integration → deployed"
```

**Implementation:**

```python
@app.post("/api/webhooks/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    # Validate signature
    signature = request.headers.get("X-Hub-Signature-256")
    body = await request.body()

    if not verify_github_signature(signature, body, GITHUB_WEBHOOK_SECRET):
        return {"error": "invalid signature"}, 401

    payload = json.loads(body)

    # Only process PR merged events
    if payload['action'] != 'closed' or not payload['pull_request']['merged']:
        return {"ok": True}

    org = await org_service.get_org_by_github_repo(payload['repository']['full_name'])

    # Offload to background task
    background_tasks.add_task(
        status_agent.process_pr_merged,
        pr_payload=payload['pull_request'],
        org_id=org.id,
    )

    return {"ok": True}
```

---

### 5.2 Slack Feature Request → Triage Flow

```
User sends message in #feature-requests channel:
"We need to add bulk export to CSV"
     │
     ├─ Slack Events API → POST /api/webhooks/slack
     │
     ├─ Validate signature: X-Slack-Signature
     │
     ├─ Route to Triage Agent:
     │  ├─ Channel: #feature-requests
     │  ├─ User: sender
     │  └─ Message: text content
     │
     ├─ Search existing PRDs:
     │  ├─ Vector search: "bulk export to CSV"
     │  ├─ Check similarity score
     │  └─ If > 0.85, return existing PRD info to Slack thread
     │
     ├─ If new feature, run intake interview:
     │  ├─ Post Q1: "What is the business impact?" (thread)
     │  ├─ Wait for response (timeout 5 min)
     │  ├─ Post Q2: "Which customer requested this?" (thread)
     │  ├─ Wait for response
     │  ├─ Post Q3: "What is the timeline urgency?" (thread)
     │  ├─ Wait for response
     │  └─ Post Q4: "Any dependencies or blockers?" (thread)
     │
     ├─ Estimate complexity:
     │  ├─ Search code: "export", "CSV", "bulk operations"
     │  ├─ Get LLM estimate based on code context
     │  └─ Result: complexity (1-10), days (est.)
     │
     ├─ Generate PM Recommendation:
     │  ├─ Get team capacity data
     │  ├─ Get current in-flight PRDs
     │  ├─ LLM generates recommendation:
     │  │  ├─ Action: build | defer | negotiate
     │  │  ├─ Impact score
     │  │  └─ Deprioritization options (if needed)
     │  └─ Confidence score
     │
     ├─ Post recommendation to Slack:
     │  ├─ Thread message with PM recommendation
     │  ├─ Add reaction buttons for PM approval
     │  └─ Include impact/complexity/timeline
     │
     ├─ Wait for PM approval (in Slack):
     │  ├─ If approved, trigger PRD Agent
     │  │  ├─ Pass intake data + recommendation
     │  │  └─ Create PRD draft
     │  └─ If deferred, add to backlog
     │
     └─ Embed intake data & recommendation:
        ├─ Vector embed the feature request
        ├─ Store in pgvector table
        └─ Update org's knowledge base
```

**Implementation:**

```python
@app.post("/api/webhooks/slack")
async def slack_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.text()
    headers = request.headers

    # Validate signature
    if not slack_client.verify_request_signature(body, headers):
        return {"error": "invalid signature"}, 401

    payload = json.loads(body)

    # Handle URL verification challenge
    if payload['type'] == 'url_verification':
        return {"challenge": payload['challenge']}

    # Route event
    if payload['type'] == 'event_callback':
        event = payload['event']

        if event['type'] == 'message' and event.get('channel') == FEATURE_REQUESTS_CHANNEL:
            org = await org_service.get_org_by_slack_workspace(payload['team_id'])

            background_tasks.add_task(
                triage_agent.process_slack_message,
                message_text=event['text'],
                channel_id=event['channel'],
                user_id=event['user'],
                org_id=org.id,
            )

    return {"ok": True}
```

---

### 5.3 Bug Threshold → Reassignment Flow

```
QA files 8th bug against PRD-2026-042:
"Payment fails when customer retries with different card"
     │
     ├─ Bug created via API: POST /api/bug
     │
     ├─ Bug Linker Agent triggered:
     │  ├─ Search for related PRD:
     │  │  ├─ Vector search: "payment fails retry card"
     │  │  ├─ Module matching: "payments"
     │  │  └─ Result: PRD-2026-042 (Stripe Billing)
     │  │
     │  ├─ Link bug to PRD:
     │  │  ├─ bugs[PRD-2026-042] = 8
     │  │  └─ Update PRD metadata
     │  │
     │  └─ Check threshold:
     │     ├─ org_config.bug_threshold_multiplier = 2.5
     │     ├─ prd.complexity_score = 8
     │     ├─ threshold = 8 * 2.5 = 20
     │     ├─ actual bugs = 8
     │     └─ No threshold exceeded yet (8 < 20)
     │
     └─ If threshold exceeded (12th bug filed):
        │
        ├─ Reassignment Agent triggered:
        │  │
        │  ├─ Get original assignees from metadata:
        │  │  └─ assignees: [Priya Chen, James Rodriguez]
        │  │
        │  ├─ Reassign to review phase:
        │  │  ├─ Update PRD status: "in-qa" (no change)
        │  │  ├─ Add review sub-task:
        │  │  │  ├─ Title: "Code review and bug fixes"
        │  │  │  ├─ Description: "Review implementation against test plan"
        │  │  │  ├─ Assignees: [Priya, James]
        │  │  │  └─ Est. days: 2
        │  │  └─ Mark PRD as "needs review"
        │  │
        │  ├─ Find available QA:
        │  │  ├─ Query skill_profiles for QA role
        │  │  ├─ Get current workload per QA
        │  │  └─ Recommend least utilized
        │  │
        │  ├─ Get next waiting PRD:
        │  │  ├─ Status: "in-uat" or "in-qa" without QA
        │  │  └─ Least recently reviewed
        │  │
        │  ├─ Reassign QA:
        │  │  ├─ Current QA moves to "pending verification"
        │  │  └─ Available QA assigned to next PRD
        │  │
        │  ├─ Update PRD metadata:
        │  │  ├─ reassignment_event:
        │  │  │  ├─ triggered_by: "bug_threshold"
        │  │  │  ├─ triggered_at: ISO timestamp
        │  │  │  ├─ bug_count: 12
        │  │  │  ├─ threshold: 20
        │  │  │  └─ action: "code_review"
        │  │  └─ Commit to PRD repo
        │  │
        │  └─ Notify Slack:
        │     ├─ Channel: #dev-updates
        │     ├─ Thread: Original PRD announcement
        │     └─ Message:
        │        "🚨 Bug threshold exceeded for PRD-2026-042!
        │         Bugs: 12 / Threshold: 20
        │         Reassigning Priya & James for code review.
        │         Moving Sarah to PRD-2026-045 UAT verification."
        │
        └─ Update vector DB embeddings
```

---

### 5.4 Daily Standup Generation Flow

```
Cron trigger: 08:30 AM (configurable per org)
     │
     ├─ Standup Agent starts
     │
     ├─ Get team members:
     │  └─ Query: SELECT * FROM users WHERE org_id = $1 AND role IN ('dev', 'qa', 'pm')
     │
     ├─ For each team member, aggregate activity:
     │  │
     │  ├─ Get commits since last standup:
     │  │  ├─ Query GitHub API for commits by this user
     │  │  ├─ Limit to last 24h
     │  │  └─ Extract: files, lines changed, commit messages
     │  │
     │  ├─ Get PR activity:
     │  │  ├─ PRs opened, reviewed, merged, commented
     │  │  ├─ Filter: since last standup
     │  │  └─ Extract: URLs, review comments, merge status
     │  │
     │  ├─ Get PRD status changes:
     │  │  ├─ Query: SELECT * FROM prd_status_history
     │  │  ├─ Filter: updated_by = user, created_at > last_standup
     │  │  └─ Extract: PRD title, old status, new status
     │  │
     │  ├─ Get bugs filed/resolved:
     │  │  ├─ Query: SELECT * FROM bugs
     │  │  ├─ Filter: assignee = user, status changed or created > last_standup
     │  │  └─ Extract: severity, module, linked PRD
     │  │
     │  ├─ Get Slack discussion:
     │  │  ├─ Query Slack API for messages by this user
     │  │  ├─ Filter: channels in org notification list, since last standup
     │  │  └─ Summarize: who asked questions, what was answered
     │  │
     │  └─ Detect flags:
     │     ├─ No activity: 0 commits, 0 PR activity
     │     ├─ PRD lagging: days_in_status > estimated_days * 1.2
     │     ├─ Scope change: PRD complexity increased significantly
     │     ├─ Design changes: PRD content changed while in-dev
     │     └─ Blockers: bugs marked "blocked", slack discussion escalated
     │
     ├─ Generate standup summary:
     │  ├─ LLM prompt:
     │  │  "Summarize this team's activity since last standup
     │  │   Commits: [...]
     │  │   PRs: [...]
     │  │   PRD updates: [...]
     │  │   Bugs: [...]
     │  │   Flags: [...]
     │  │
     │  │   Generate a standup summary highlighting:
     │  │   - Key accomplishments
     │  │   - Current blockers
     │  │   - Recommendations"
     │  │
     │  └─ Result: team-level summary + per-dev summaries
     │
     ├─ Format Slack message:
     │  ├─ Header: "📊 Daily Standup - March 5, 2026"
     │  ├─ Per-dev sections with activity
     │  ├─ Team summary with key flags
     │  ├─ Recommendations for team leads
     │  └─ Interactive buttons: [Discuss], [Mark resolved]
     │
     ├─ Post to Slack:
     │  ├─ Channel: #standup (configurable)
     │  ├─ Timestamp: saved as standup_ts
     │  └─ Start thread if flags detected
     │
     ├─ Store standup report:
     │  ├─ Table: standup_reports
     │  ├─ Columns:
     │  │  ├─ date
     │  │  ├─ org_id
     │  │  ├─ content_json (full activity data)
     │  │  ├─ summary_text
     │  │  ├─ flags (JSON array)
     │  │  ├─ posted_to_slack_ts
     │  │  └─ created_at
     │  │
     │  └─ Commit
     │
     └─ Log execution:
        ├─ agent_logs entry
        ├─ Tokens used
        ├─ Execution time
        └─ Any errors
```

---

### 5.5 Enterprise Rules Auto-Update Flow

```
GitHub PR merged (any branch):
     │
     ├─ Status Agent processes PR merge
     │
     ├─ Check if diff affects enterprise rules:
     │  ├─ Get PR diff from GitHub API
     │  ├─ Search for "enterprise-rules/" in file paths
     │  └─ Extract affected files
     │
     ├─ If enterprise rules changed:
     │  ├─ Option A: Flag for manual review
     │  │  ├─ Post to Slack (#dev-updates)
     │  │  └─ Message: "PR affected business rules - review required"
     │  │
     │  └─ Option B: Auto-generate update (configurable)
     │     ├─ Analyze PR diff to detect rule changes
     │     ├─ LLM generates updated enterprise rules docs
     │     ├─ Auto-create PR to enterprise-rules/ folder:
     │     │  ├─ Branch: auto/update-rules-{pr_number}
     │     │  ├─ Commit message: "Auto-update: Enterprise rules based on PR #{number}"
     │     │  ├─ Files: Updated rule docs
     │     │  └─ PR description: Links to original PR + change summary
     │     │
     │     └─ Tag team for review:
     │        ├─ Notify in Slack
     │        └─ Assign PM/Tech Lead for approval
     │
     ├─ If business logic rules updated:
     │  ├─ Trigger vector re-indexing
     │  ├─ Update pgvector embeddings
     │  └─ Make searchable for future Triage queries
     │
     └─ Log enterprise rule change
        ├─ Record PR that triggered change
        ├─ Track before/after diff
        └─ Store in audit log
```
## 6. Database Schema

### 6.1 PostgreSQL Setup

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Enum types
CREATE TYPE user_role AS ENUM ('admin', 'pm', 'dev', 'qa', 'viewer');
CREATE TYPE prd_status AS ENUM ('draft', 'design', 'tech-spec', 'in-dev', 'in-qa', 'in-uat', 'deployed');
CREATE TYPE bug_status AS ENUM ('open', 'in-progress', 'resolved', 'closed', 'blocked');
CREATE TYPE bug_severity AS ENUM ('low', 'medium', 'high', 'critical');

-- ============================================================================
-- Organizations (Multi-Org Root)
-- ============================================================================
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    config JSONB DEFAULT '{}'::jsonb,
    github_app_token VARCHAR(255),
    slack_bot_token VARCHAR(255),
    slack_signing_secret VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_organizations_slug ON organizations(slug);

-- ============================================================================
-- Users
-- ============================================================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(255),
    password_hash VARCHAR(255),
    role user_role DEFAULT 'dev',
    slack_id VARCHAR(100),
    github_username VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(org_id, email)
);

CREATE INDEX idx_users_org_id ON users(org_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_slack_id ON users(slack_id);
CREATE INDEX idx_users_github_username ON users(github_username);

-- Row-Level Security for users
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_org_isolation ON users
    USING (org_id = current_setting('app.org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.org_id')::uuid);

-- ============================================================================
-- Org Memberships (for multi-org support)
-- ============================================================================
CREATE TABLE org_memberships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role user_role DEFAULT 'dev',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, org_id)
);

CREATE INDEX idx_org_memberships_user_id ON org_memberships(user_id);
CREATE INDEX idx_org_memberships_org_id ON org_memberships(org_id);

-- ============================================================================
-- PRD Documents (with vector embeddings)
-- ============================================================================
CREATE TABLE prd_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    prd_number INT NOT NULL,
    title VARCHAR(500) NOT NULL,
    status prd_status DEFAULT 'draft',

    -- Content
    content_md TEXT,
    tech_spec_md TEXT,
    test_plan_md TEXT,

    -- Vector embeddings (dimensions configurable via EMBEDDING_DIMENSIONS env var)
    -- Default: 768 (Ollama nomic-embed-text), 1536 (OpenAI), 384 (MiniLM)
    embedding vector(768),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,
    -- metadata schema:
    -- {
    --   "assignees": ["user-uuid-1", "user-uuid-2"],
    --   "complexity_score": 8,
    --   "estimated_days": 10,
    --   "repo_path": "active/PRD-2026-042",
    --   "linked_prs": ["PR-123", "PR-124"],
    --   "created_at": "2026-03-05T10:00:00Z",
    --   "deployed_at": "2026-03-12T14:30:00Z",
    --   "status_transitions": [
    --     { "from": "draft", "to": "design", "at": "2026-03-05T11:00:00Z" }
    --   ]
    -- }

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(org_id, prd_number)
);

-- HNSW index for vector search
CREATE INDEX prd_embedding_hnsw ON prd_documents
USING hnsw (embedding vector_cosine_ops)
WITH (m = 30, ef_construction = 200);

CREATE INDEX idx_prd_org_id ON prd_documents(org_id);
CREATE INDEX idx_prd_status ON prd_documents(org_id, status);
CREATE INDEX idx_prd_title_trgm ON prd_documents USING gin(title gin_trgm_ops);

-- RLS
ALTER TABLE prd_documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY prd_org_isolation ON prd_documents
    USING (org_id = current_setting('app.org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.org_id')::uuid);

-- ============================================================================
-- Enterprise Rules (with vector embeddings)
-- ============================================================================
CREATE TABLE enterprise_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL, -- 'business_logic' | 'technical_standard'
    title VARCHAR(500) NOT NULL,
    content_md TEXT NOT NULL,

    embedding vector(768),  -- Configurable: set via EMBEDDING_DIMENSIONS

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX enterprise_rules_embedding_hnsw ON enterprise_rules
USING hnsw (embedding vector_cosine_ops)
WITH (m = 30, ef_construction = 200);

CREATE INDEX idx_enterprise_rules_org_id ON enterprise_rules(org_id);
CREATE INDEX idx_enterprise_rules_category ON enterprise_rules(org_id, category);

-- RLS
ALTER TABLE enterprise_rules ENABLE ROW LEVEL SECURITY;
CREATE POLICY enterprise_rules_org_isolation ON enterprise_rules
    USING (org_id = current_setting('app.org_id')::uuid);

-- ============================================================================
-- Bugs (with vector embeddings)
-- ============================================================================
CREATE TABLE bugs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    prd_id UUID REFERENCES prd_documents(id) ON DELETE SET NULL,

    title VARCHAR(500) NOT NULL,
    description TEXT,
    severity bug_severity DEFAULT 'medium',
    status bug_status DEFAULT 'open',

    module VARCHAR(100), -- e.g., "payments", "auth"

    reporter_id UUID NOT NULL REFERENCES users(id),
    assignee_id UUID REFERENCES users(id),

    linked_pr VARCHAR(255), -- GitHub PR URL

    embedding vector(768),  -- Configurable: set via EMBEDDING_DIMENSIONS

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX bugs_embedding_hnsw ON bugs
USING hnsw (embedding vector_cosine_ops)
WITH (m = 30, ef_construction = 200);

CREATE INDEX idx_bugs_org_id ON bugs(org_id);
CREATE INDEX idx_bugs_prd_id ON bugs(prd_id);
CREATE INDEX idx_bugs_status ON bugs(org_id, status);
CREATE INDEX idx_bugs_severity ON bugs(org_id, severity);

-- RLS
ALTER TABLE bugs ENABLE ROW LEVEL SECURITY;
CREATE POLICY bugs_org_isolation ON bugs
    USING (org_id = current_setting('app.org_id')::uuid);

-- ============================================================================
-- Skill Profiles
-- ============================================================================
CREATE TABLE skill_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    module VARCHAR(100), -- e.g., "payments", "auth", "frontend"
    repo VARCHAR(100),   -- e.g., "api", "web"
    languages VARCHAR(50)[], -- e.g., ARRAY['python', 'typescript']

    skill_score NUMERIC(3, 2), -- 0.00 - 1.00
    touch_count INT DEFAULT 0, -- number of commits/PRs
    last_touch TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, org_id, module)
);

CREATE INDEX idx_skill_profiles_user_org ON skill_profiles(user_id, org_id);
CREATE INDEX idx_skill_profiles_module ON skill_profiles(org_id, module, skill_score DESC);

-- RLS
ALTER TABLE skill_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY skill_profiles_org_isolation ON skill_profiles
    USING (org_id = current_setting('app.org_id')::uuid);

-- ============================================================================
-- Standup Reports
-- ============================================================================
CREATE TABLE standup_reports (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    date DATE NOT NULL,
    content JSONB, -- Full standup data
    summary TEXT,  -- Summary text
    flags JSONB,   -- Array of flags

    posted_to_slack_ts VARCHAR(100),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(org_id, date)
);

CREATE INDEX idx_standup_reports_org_date ON standup_reports(org_id, date DESC);

-- RLS
ALTER TABLE standup_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY standup_reports_org_isolation ON standup_reports
    USING (org_id = current_setting('app.org_id')::uuid);

-- ============================================================================
-- Feature Learnings (with vector embeddings)
-- ============================================================================
CREATE TABLE feature_learnings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    prd_id UUID NOT NULL REFERENCES prd_documents(id) ON DELETE CASCADE,

    cycle_time_days INT,
    estimated_days INT,
    bug_count INT DEFAULT 0,

    retrospective_md TEXT,

    embedding vector(768),  -- Configurable: set via EMBEDDING_DIMENSIONS

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX feature_learnings_embedding_hnsw ON feature_learnings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 30, ef_construction = 200);

CREATE INDEX idx_feature_learnings_org_id ON feature_learnings(org_id);
CREATE INDEX idx_feature_learnings_prd_id ON feature_learnings(prd_id);

-- RLS
ALTER TABLE feature_learnings ENABLE ROW LEVEL SECURITY;
CREATE POLICY feature_learnings_org_isolation ON feature_learnings
    USING (org_id = current_setting('app.org_id')::uuid);

-- ============================================================================
-- Code Embeddings
-- ============================================================================
CREATE TABLE code_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    repo VARCHAR(100),
    file_path VARCHAR(500),
    function_name VARCHAR(255),
    content_summary TEXT,

    embedding vector(768),  -- Configurable: set via EMBEDDING_DIMENSIONS

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX code_embeddings_hnsw ON code_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 30, ef_construction = 200);

CREATE INDEX idx_code_embeddings_org_repo ON code_embeddings(org_id, repo);
CREATE INDEX idx_code_embeddings_file_path ON code_embeddings(org_id, file_path);

-- RLS
ALTER TABLE code_embeddings ENABLE ROW LEVEL SECURITY;
CREATE POLICY code_embeddings_org_isolation ON code_embeddings
    USING (org_id = current_setting('app.org_id')::uuid);

-- ============================================================================
-- Agent Logs (for monitoring and observability)
-- ============================================================================
CREATE TABLE agent_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    agent_name VARCHAR(100), -- triage, prd, status, standup, learning, bug_linker, reassignment, skill
    trigger_type VARCHAR(50), -- webhook, cron, manual, event
    trigger_source VARCHAR(255), -- slack, github, api, scheduler

    input_summary TEXT,
    output_summary TEXT,

    tokens_used INT,
    execution_time_ms INT,

    status VARCHAR(50), -- success, error, timeout
    error_message TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_agent_logs_org_id ON agent_logs(org_id);
CREATE INDEX idx_agent_logs_agent_name ON agent_logs(org_id, agent_name);
CREATE INDEX idx_agent_logs_created_at ON agent_logs(org_id, created_at DESC);

-- RLS
ALTER TABLE agent_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY agent_logs_org_isolation ON agent_logs
    USING (org_id = current_setting('app.org_id')::uuid);

-- ============================================================================
-- JWT Session Tokens (optional, if not using stateless JWT)
-- ============================================================================
CREATE TABLE jwt_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMP
);

CREATE INDEX idx_jwt_tokens_user_id ON jwt_tokens(user_id);
CREATE INDEX idx_jwt_tokens_expires_at ON jwt_tokens(expires_at);

-- ============================================================================
-- Views for common queries
-- ============================================================================

-- View: PRD summary with stats
CREATE VIEW prd_summary AS
SELECT
    p.id,
    p.org_id,
    p.prd_number,
    p.title,
    p.status,
    p.metadata->>'complexity_score'::int AS complexity_score,
    COUNT(DISTINCT b.id) AS bug_count,
    MAX(b.created_at) AS last_bug_date,
    p.created_at,
    p.updated_at
FROM prd_documents p
LEFT JOIN bugs b ON p.id = b.prd_id
GROUP BY p.id, p.org_id, p.prd_number, p.title, p.status, p.created_at, p.updated_at;

-- View: Team utilization
CREATE VIEW team_utilization AS
SELECT
    p.org_id,
    u.id AS user_id,
    u.name,
    COUNT(DISTINCT p.id) AS assigned_prds,
    SUM((p.metadata->>'estimated_days')::int) AS estimated_days_remaining,
    ROUND(100.0 * SUM((p.metadata->>'estimated_days')::int) /
        NULLIF(SUM((p.metadata->>'estimated_days')::int) OVER (PARTITION BY p.org_id), 0), 2) AS utilization_pct
FROM prd_documents p
CROSS JOIN LATERAL jsonb_array_elements_text(p.metadata->'assignees') AS assignee_id
JOIN users u ON u.id = assignee_id::uuid
WHERE p.status IN ('in-dev', 'in-qa', 'in-uat')
GROUP BY p.org_id, u.id, u.name;
```
## 7. Vector DB Strategy

### 7.1 Content Embedding Strategy

**What Gets Embedded & When:**

| Content Type | Trigger | Chunking Strategy | Embedding Dims | Re-index Frequency |
|---|---|---|---|---|
| **PRD Documents** | Create/Update | Per-section (overview, goals, requirements, acceptance criteria) | Configurable (default: 768) | On update |
| **Enterprise Rules** | Create/Update | Whole doc (rules are concise) | Configurable (default: 768) | On update |
| **Bug Reports** | Created | Title + description + linked code | Configurable (default: 768) | On creation |
| **Code (Functions)** | PR merge to dev/main | Per-function (sig + docstring) | Configurable (default: 768) | On PR merge |
| **Feature Learnings** | PRD deployed | Whole retrospective | Configurable (default: 768) | On creation |
| **Slack Decisions** | Manually flagged | Message thread summary | Configurable (default: 768) | Manual |

### 7.2 Chunking Strategy

**PRDs (per-section):**
```python
class PRDChunker:
    def chunk_prd(self, prd_content: str) -> list[Chunk]:
        """Split PRD by headers and create overlapping chunks."""
        sections = self._extract_sections(prd_content)
        chunks = []

        for section in sections:
            # Each section is a chunk
            chunks.append(Chunk(
                id=f"prd-section-{section['id']}",
                content=f"{section['title']}\n{section['content']}",
                metadata={
                    'type': 'prd_section',
                    'section_title': section['title'],
                    'section_order': section['order'],
                },
            ))

        # Add overlapping context chunks (prev + curr + next section)
        for i in range(1, len(sections) - 1):
            context_content = "\n\n".join([
                f"### {sections[i-1]['title']}\n{sections[i-1]['content'][:200]}",
                f"### {sections[i]['title']}\n{sections[i]['content']}",
                f"### {sections[i+1]['title']}\n{sections[i+1]['content'][:200]}",
            ])
            chunks.append(Chunk(
                id=f"prd-context-{sections[i]['id']}",
                content=context_content,
                metadata={
                    'type': 'prd_context',
                    'main_section': sections[i]['title'],
                },
            ))

        return chunks
```

**Code (per-function):**
```python
class CodeChunker:
    def chunk_repo(self, repo_path: str, org_id: str) -> list[Chunk]:
        """Extract functions and create chunks from code."""
        chunks = []

        for file_path in self._walk_files(repo_path):
            if not self._is_code_file(file_path):
                continue

            functions = self._extract_functions(file_path)

            for func in functions:
                chunks.append(Chunk(
                    id=f"code-{func['hash']}",
                    content=f"{func['signature']}\n\n{func['docstring']}\n{func['body'][:500]}",
                    metadata={
                        'type': 'code_function',
                        'repo': repo_path.split('/')[-1],
                        'file_path': file_path,
                        'function_name': func['name'],
                        'language': self._detect_language(file_path),
                    },
                ))

        return chunks
```

### 7.3 Embedding Model Configuration

**Default Model**: Ollama `nomic-embed-text` (local-first)

| Model | Provider | Dimensions | Cost | When to use |
|-------|----------|-----------|------|-------------|
| `nomic-embed-text` | Ollama | 768 | Free (local) | **Default** — local deployment |
| `mxbai-embed-large` | Ollama | 1024 | Free (local) | Local deployment (higher quality) |
| `text-embedding-3-small` | OpenAI | 1536 | ~$0.02/1M tokens | Cloud deployment |
| `all-MiniLM-L6-v2` | sentence-transformers | 384 | Free (local) | Zero-infrastructure fallback |

**Configuration:**
```python
# config.py
EMBEDDING_CONFIG = {
    'provider': os.getenv('EMBEDDING_PROVIDER', 'ollama'),  # "openai", "ollama", "sentence-transformers"
    'model': os.getenv('EMBEDDING_MODEL', 'nomic-embed-text'),
    'dimensions': int(os.getenv('EMBEDDING_DIMENSIONS', '768')),  # MUST match model output
    'batch_size': 100,
    'max_retries': 3,
    'base_url': os.getenv('LLM_BASE_URL', 'http://localhost:11434'),
}
```

### 7.4 HNSW Index Configuration

**Index Parameters:**

```sql
-- PRD embeddings: high precision
CREATE INDEX prd_embedding_hnsw ON prd_documents
USING hnsw (embedding vector_cosine_ops)
WITH (m = 30, ef_construction = 200);

-- Code embeddings: moderate precision
CREATE INDEX code_embedding_hnsw ON code_embeddings
USING hnsw (embedding vector_cosine_ops)
WITH (m = 25, ef_construction = 150);

-- Bug embeddings: high recall
CREATE INDEX bug_embedding_hnsw ON bugs
USING hnsw (embedding vector_cosine_ops)
WITH (m = 30, ef_construction = 200);
```

**Tuning Guidelines:**
- **m**: 16-30 (higher = better quality, slower indexing)
- **ef_construction**: 200-400 (higher = better quality, slower indexing)
- **ef_search**: 100-500 at runtime (higher = better recall, slower queries)

### 7.5 Namespace Isolation Per Org

```python
class SecureVectorSearch:
    async def search(
        self,
        query: str,
        org_id: str,  # MANDATORY
        table: str,
        top_k: int = 5,
    ):
        """Vector search with org isolation."""

        query_embedding = await embedding_service.embed(query)

        # ALWAYS include org_id in WHERE clause
        sql = f"""
        SELECT * FROM {table}
        WHERE org_id = %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """

        results = await db.fetch(sql, org_id, query_embedding, top_k)
        return results
```

---

## 8. PRD Repository Structure

### 8.1 Complete Folder Structure

```
prd-repo/
├── active/
│   ├── PRD-2026-001/
│   │   ├── prd.md
│   │   ├── tech-spec.md
│   │   ├── test-plan.md
│   │   ├── metadata.yaml
│   │   └── bugs/
│   │       ├── bug-001.md
│   │       └── bug-002.md
│   └── ...
│
├── deployed/
│   ├── PRD-2025-100/
│   │   ├── prd.md
│   │   ├── tech-spec.md
│   │   ├── test-plan.md
│   │   ├── metadata.yaml
│   │   └── retrospective.md
│   └── ...
│
├── enterprise-rules/
│   ├── business-logic/
│   │   ├── subscription-cancellation.md
│   │   ├── pricing-rules.md
│   │   └── payment-processing.md
│   └── technical-standards/
│       ├── api-design.md
│       ├── database-schema.md
│       └── security-requirements.md
│
├── templates/
│   ├── prd-template.md
│   ├── tech-spec-template.md
│   └── test-plan-template.md
│
└── README.md
```

### 8.2 Metadata.yaml Schema

```yaml
prd_number: 2026042
title: "Stripe Billing Integration"
status: "in-dev"

assignees:
  - name: "Priya Chen"
    id: "user-uuid-1"
    role: "lead-dev"
  - name: "James Rodriguez"
    id: "user-uuid-2"
    role: "dev"

created_at: "2026-02-28T10:00:00Z"
started_at: "2026-03-01T09:00:00Z"
deployed_at: null

estimated_complexity: 8
estimated_days: 10
estimated_completion: "2026-03-12"

linked_prs:
  - number: 123
    url: "https://github.com/acme/api/pull/123"
    status: "merged"

linked_bugs:
  - id: "bug-uuid-1"
    title: "Payment fails on retry"
    severity: "high"
    status: "resolved"

business_impact: "Enables recurring subscriptions - critical for ARR growth"
revenue_impact: "Expected $2M ARR increase"

dependencies:
  - prd_id: 2026040
    prd_title: "Payment Processing Foundation"
    status: "deployed"

status_transitions:
  - from: "draft"
    to: "design"
    at: "2026-02-28T14:00:00Z"

bug_count: 2
bug_threshold: 20  # complexity (8) * multiplier (2.5)
```

### 8.3 Branch Naming Conventions

```
Code Repos:
  feature/PRD-2026-042           # Feature branch for PRD
  bugfix/PRD-2026-042-issue-123  # Bug fix for specific PRD
  hotfix/urgent-payment-bug      # Hotfix (no PRD reference needed)

PRD Repo:
  prd/2026-042-stripe-billing    # Feature branch for PRD creation/updates
  main                            # Main branch, all PRDs live here
```

---

## 9. GitHub Actions

### 9.1 status-update.yml (Reusable Workflow)

```yaml
# .github/workflows/status-update.yml

name: Bodhiorchard Status Update
on:
  pull_request:
    types: [closed]

jobs:
  update_prd_status:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest

    steps:
      - name: Extract PRD Reference
        id: extract_prd
        run: |
          PRD=$(echo "${{ github.head_ref }}" | grep -oP 'PRD-\d+' || echo "")
          if [ -z "$PRD" ]; then
            PRD=$(echo "${{ github.event.pull_request.body }}" | grep -oP 'PRD-\d+' || echo "")
          fi
          echo "prd_ref=$PRD" >> $GITHUB_OUTPUT

      - name: Call Bodhiorchard API
        if: steps.extract_prd.outputs.prd_ref != ''
        run: |
          curl -X POST https://bodhiorchard.your-domain.com/api/webhooks/github \
            -H "Content-Type: application/json" \
            -H "X-GitHub-Event: pull_request" \
            -d '{
              "action": "closed",
              "pull_request": {
                "number": ${{ github.event.pull_request.number }},
                "merged": true,
                "head": {"ref": "${{ github.head_ref }}"},
                "base": {"ref": "${{ github.base_ref }}"}
              }
            }'
```

### 9.2 enterprise-rules-check.yml

```yaml
# .github/workflows/enterprise-rules-check.yml

name: Enterprise Rules Check
on:
  pull_request:
    paths:
      - 'src/billing/**'
      - 'src/payment/**'

jobs:
  check_rules:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Check if PR affects enterprise rules
        id: check_rules
        run: |
          AFFECTED=$(git diff origin/main --name-only | grep -E '^src/(billing|payment)' || echo "")
          [ ! -z "$AFFECTED" ] && echo "needs_rule_update=true" >> $GITHUB_OUTPUT

      - name: Trigger Bodhiorchard Rule Update
        if: steps.check_rules.outputs.needs_rule_update == 'true'
        run: |
          curl -X POST https://bodhiorchard.your-domain.com/api/agents/status/trigger \
            -H "Authorization: Bearer ${{ secrets.BODHIORCHARD_API_KEY }}" \
            -d '{"pr_number": ${{ github.event.pull_request.number }}}'

      - name: Post PR Comment
        if: steps.check_rules.outputs.needs_rule_update == 'true'
        uses: actions/github-script@v6
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '⚠️ This PR affects business logic. Please update enterprise rules.'
            })
```

---

## 10. Slack Bot Design

### 10.1 Event Subscriptions & Commands

```yaml
app_display_name: Bodhiorchard

scopes:
  - chat:write
  - app_mentions:read
  - channels:read
  - users:read
  - reactions:read

events:
  - message.channels
  - app_mention
  - reaction_added

slash_commands:
  - /bodhiorchard-request     # Submit feature request
  - /bodhiorchard-status      # Check PRD status
  - /bodhiorchard-assign      # Assign dev
  - /bodhiorchard-capacity    # View team capacity
  - /bodhiorchard-prd         # Generate PRD via Claude Agent SDK
  - /bodhiorchard-standup     # Trigger standup generation
  - /bodhiorchard-triage      # Trigger triage on a Slack thread
```

### 10.2 Slash Commands Implementation

```python
@app.post("/api/webhooks/slack/slash")
async def slack_slash_command(request: Request):
    payload = parse_slack_request(request)
    command = payload['command']
    text = payload['text']
    user_id = payload['user_id']
    channel_id = payload['channel_id']

    if command == '/bodhiorchard-request':
        background_tasks.add_task(
            triage_agent.process_slack_message,
            message_text=text,
            channel_id=channel_id,
            user_id=user_id,
        )
        return {"response_type": "in_channel", "text": f"📋 Processing: {text}"}

    elif command == '/bodhiorchard-status':
        prd_num = extract_prd_number(text)
        prd = await prd_service.get_prd_by_number(prd_num)
        blocks = format_prd_status_blocks(prd)
        return {"response_type": "in_channel", "blocks": blocks}

    elif command == '/bodhiorchard-capacity':
        capacity = await capacity_service.get_team_capacity()
        blocks = format_capacity_blocks(capacity)
        return {"response_type": "in_channel", "blocks": blocks}

    return {"text": "Unknown command"}
```

### 10.3 Channel Conventions

```
#feature-requests              → Feature intake (monitored by Triage Agent)
#prd-updates                  → PRD status changes
#standup                      → Daily standups (8:30 AM)
#dev-updates                  → General dev team updates
#metrics                      → Weekly metrics dashboard
#enterprise-rules-changes     → Business rules updates
```

---

## 11. Configuration

### 11.1 org-config.yaml Schema

```yaml
organization:
  id: "org-uuid-12345"
  name: "Acme Corp"
  slug: "acme"

github:
  org_name: "acme-github"
  installation_id: "12345678"
  token_encrypted: true

slack:
  workspace_url: "acme.slack.com"
  team_id: "T12345678"
  bot_token_encrypted: true

feature_intake:
  channel_id: "C_FEATURE_REQUESTS"
  channel_name: "#feature-requests"

notifications:
  prd_updates: "#prd-updates"
  dev_updates: "#dev-updates"
  standups: "#standup"

standup:
  enabled: true
  timezone: "America/Los_Angeles"
  time: "08:30"
  day_of_week: [1, 2, 3, 4, 5]  # Mon-Fri

bug_management:
  threshold_multiplier: 2.5
  auto_reassign: true
  notify_on_threshold: true

capacity:
  dev_count: 5
  estimated_sprint_days: 50
  high_utilization_threshold: 0.85

embeddings:
  provider: "ollama"                    # or "openai", "sentence-transformers"
  model: "nomic-embed-text"             # or "text-embedding-3-small" for OpenAI
  dimensions: 768                        # MUST match model output

features:
  auto_prd_generation: true
  enterprise_rules_auto_update: true
  skill_based_assignment: true
  standup_generation: true
```

### 11.2 Environment Variables

```bash
# API Configuration
API_PORT=8000
ENV=production

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/bodhiorchard
DATABASE_POOL_SIZE=20

# Authentication
JWT_SECRET_KEY=your-secret-key
JWT_EXPIRATION_HOURS=24

# GitHub
GITHUB_WEBHOOK_SECRET=your-webhook-secret
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA...

# Slack
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_BOT_TOKEN=xoxb-your-token

# LLM Configuration (local-first default)
LLM_PROVIDER=ollama                     # or "openai", "anthropic"
LLM_MODEL=llama3:8b                     # default tier model
LLM_BASE_URL=http://localhost:11434
LLM_PREMIUM_PROVIDER=ollama             # or "openai" for hybrid
LLM_PREMIUM_MODEL=llama3:70b            # or "gpt-4o"

# Embedding Configuration
EMBEDDING_PROVIDER=ollama               # or "openai", "sentence-transformers"
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768                # MUST match model output

# OpenAI (only needed if using OpenAI as LLM/embedding provider)
OPENAI_API_KEY=sk-...

# Anthropic (only needed if using Claude Agent SDK for PRD/Learning agents)
ANTHROPIC_API_KEY=sk-ant-...

# Agno Framework
AGNO_MODEL_PROVIDER=ollama
AGNO_MODEL=llama3:8b

# Public URL (set when using Cloudflare Tunnel or any reverse proxy)
PUBLIC_URL=https://api.bodhiorchard.yourdomain.com

# Cloudflare Tunnel (only needed with docker compose --profile tunnel)
CLOUDFLARE_TUNNEL_TOKEN=your-tunnel-token

# Logging
LOG_LEVEL=INFO
```

### 11.3 Docker Compose for Local Development (Local-First)

```yaml
# docker-compose.yml

version: '3.9'

services:
  ollama:
    image: ollama/ollama:latest
    container_name: bodhiorchard-ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:11434/api/tags || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]  # Optional — enables GPU acceleration

  ollama-init:
    image: ollama/ollama:latest
    container_name: bodhiorchard-ollama-init
    depends_on:
      ollama:
        condition: service_healthy
    environment:
      OLLAMA_HOST: http://ollama:11434
    entrypoint: >
      sh -c "ollama pull llama3:8b && ollama pull nomic-embed-text"
    restart: "no"

  postgres:
    image: pgvector/pgvector:pg16-latest
    container_name: bodhiorchard-postgres
    environment:
      POSTGRES_USER: bodhiorchard
      POSTGRES_PASSWORD: bodhiorchard_password
      POSTGRES_DB: bodhiorchard
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bodhiorchard"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: bodhiorchard-redis
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
    container_name: bodhiorchard-backend
    environment:
      DATABASE_URL: postgresql://bodhiorchard:bodhiorchard_password@postgres:5432/bodhiorchard
      REDIS_URL: redis://redis:6379/0
      ENV: development
      LLM_PROVIDER: ollama
      LLM_MODEL: llama3:8b
      LLM_BASE_URL: http://ollama:11434
      LLM_PREMIUM_PROVIDER: ollama
      LLM_PREMIUM_MODEL: llama3:8b
      EMBEDDING_PROVIDER: ollama
      EMBEDDING_MODEL: nomic-embed-text
      EMBEDDING_DIMENSIONS: 768
      LOG_LEVEL: DEBUG
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      ollama-init:
        condition: service_completed_successfully
    volumes:
      - ./backend:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build:
      context: ./frontend
    container_name: bodhiorchard-frontend
    environment:
      VITE_API_URL: http://localhost:8000/api
    ports:
      - "3000:3000"
    volumes:
      - ./frontend/src:/app/src
    depends_on:
      - backend
    command: npm run dev

volumes:
  postgres_data:
  ollama_data:
```

---

## 12. Security & Auth

### 12.1 JWT-Based Authentication

```python
# auth.py

from datetime import datetime, timedelta
from jose import jwt

def create_access_token(user_id: str, org_id: str, role: str) -> str:
    """Create JWT token."""
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

async def verify_token(credentials: HTTPAuthCredentials) -> TokenData:
    """Verify JWT token."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )
        return TokenData(
            user_id=payload.get("sub"),
            org_id=payload.get("org_id"),
            role=payload.get("role"),
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### 12.2 Webhook Signature Validation

```python
import hmac
import hashlib

def verify_github_signature(signature: str, body: bytes, secret: str) -> bool:
    """Verify GitHub webhook signature."""
    expected = "sha256=" + hmac.new(
        secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)

def verify_slack_signature(signature: str, timestamp: str, body: str, secret: str) -> bool:
    """Verify Slack webhook signature."""
    if abs(int(time.time()) - int(timestamp)) > 300:
        return False
    message = f"v0:{timestamp}:{body}"
    expected = "v0=" + hmac.new(
        secret.encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)
```

### 12.3 Role-Based Access Control (9 Roles, 9 Permission Categories)

Bodhiorchard uses a **granular RBAC model** with 9 system roles, 9 permission categories, and support for custom org-level roles.

**Role Hierarchy:**

```
org_owner (full control)
  └── admin (manage members, config)
        └── pm (product manager)
        └── tech_lead
        └── developer
        └── designer
        └── qa
        └── support
        └── viewer (read-only stakeholders)
```

**9 Permission Categories (implemented in `permission_seeder.py`):**

| Category | Permissions |
|---|---|
| BACKLOG | view, create, edit, delete, approve |
| AGENTS | view, configure, trigger |
| NODES | view, scan, approve, install |
| PRDs | view, create, edit |
| TEAM | view, invite, remove, assign_roles |
| ORGANIZATION | view_settings, edit_settings |
| INTEGRATIONS | view, configure |
| KNOWLEDGE | view, contribute, manage |
| REPORTS | view, export |

**Permission Matrix (abbreviated — see Section 14 for complete route access matrix):**

```
Permission                    owner  admin  pm    tech_lead  dev  designer  qa   support  viewer
─────────────────────────────────────────────────────────────────────────────────────────────────
org.manage                      Y      Y     -      -        -      -       -      -       -
prd.create                      Y      Y     Y      Y        -      -       -      -       -
prd.edit                        Y      Y     Y      Y        Y*     Y*      -      -       -
prd.reopen                      Y      Y     Y      Y        -      -       -      Y       -
bug.create                      Y      Y     Y      Y        Y      Y       Y      Y       -
ticket.manage                   Y      Y     Y      -        -      -       -      Y       -
customer.view_revenue           Y      Y     Y      Y        -      -       -      Y       -
agent.trigger_manual            Y      Y     Y      Y        -      -       -      -       -

*  dev/designer can edit PRDs they're assigned to
```

**Permission API Endpoints (implemented):**

- `GET /api/v1/permissions` — list all permission categories with nested permissions
- `GET /api/v1/roles` — list all roles (system + custom)
- `GET /api/v1/roles/{role_id}` — get single role with assigned permissions
- `POST /api/v1/roles` — create custom org-level role
- `PUT /api/v1/roles/{role_id}` — update role permissions
- `DELETE /api/v1/roles/{role_id}` — delete custom role (system roles protected)

**Permission Middleware:**

```python
# Permission definitions with role mappings
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "org_owner": {"*"},  # wildcard = all permissions
    "org_admin": {
        "org.manage", "org.config", "org.members.invite", "org.members.remove",
        "org.members.roles", "prd.*", "bug.*", "ticket.*", "customer.*",
        "enterprise_rules.*", "standup.*", "metrics.*", "agent.*",
    },
    "pm": {
        "org.members.invite", "prd.*", "tech_spec.*", "test_plan.*",
        "bug.*", "ticket.*", "customer.*", "enterprise_rules.*",
        "standup.*", "metrics.*", "agent.*",
    },
    "developer": {
        "prd.edit.assigned", "prd.status.transition.limited", "prd.view",
        "tech_spec.*", "test_plan.*", "bug.create", "bug.edit", "bug.close",
        "bug.view", "ticket.view", "customer.view", "enterprise_rules.view",
        "standup.view", "metrics.view",
    },
    "support": {
        "prd.reopen", "prd.view", "bug.create", "bug.edit", "bug.view",
        "ticket.*", "customer.*", "enterprise_rules.view",
        "standup.view", "metrics.view",
    },
    "viewer": {
        "prd.view", "bug.view", "ticket.view", "customer.view",
        "enterprise_rules.view", "standup.view", "metrics.view",
    },
}


def has_permission(permission: str) -> Callable:
    """FastAPI dependency that checks if current user has the required permission."""

    async def check_permission(
        current_user: User = Depends(get_current_user),
        org_context: OrgContext = Depends(get_org_context),
    ):
        membership = await get_membership(current_user.id, org_context.org_id)
        if not membership or not membership.is_active:
            raise HTTPException(status_code=403, detail="Not a member of this organization")

        role_perms = ROLE_PERMISSIONS.get(membership.role, set())
        if "*" in role_perms:
            return current_user

        if permission in role_perms:
            return current_user

        namespace = permission.rsplit(".", 1)[0]
        if f"{namespace}.*" in role_perms:
            return current_user

        raise HTTPException(
            status_code=403,
            detail=f"Role '{membership.role}' does not have '{permission}' permission"
        )

    return check_permission


# Usage in route
@app.post("/api/prd")
async def create_prd(
    request: CreatePRDRequest,
    user: User = Depends(has_permission("prd.create")),
    org: OrgContext = Depends(get_org_context),
):
    return await prd_service.create(request, org, user)
```

---

## 13. Monitoring & Observability

### 13.1 Agent Execution Logging

```python
class AgentLogger:
    async def log_execution(
        self,
        agent_name: str,
        trigger_type: str,
        input_data: dict,
        output_data: dict,
        tokens_used: int,
        execution_time_ms: int,
        org_id: str,
        status: str = "success",
        error_message: str = None,
    ):
        """Log agent execution to DB."""
        await db.execute(
            """
            INSERT INTO agent_logs (org_id, agent_name, trigger_type,
                                    input_summary, output_summary, tokens_used,
                                    execution_time_ms, status, error_message)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            org_id, agent_name, trigger_type,
            json.dumps(input_data)[:500],
            json.dumps(output_data)[:500],
            tokens_used,
            execution_time_ms,
            status,
            error_message,
        )
```

### 13.2 Token Usage Tracking

```python
class TokenTracker:
    async def track_token_usage(
        self,
        org_id: str,
        agent_name: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
    ):
        """Track token usage per org per agent."""
        total = prompt_tokens + completion_tokens
        await db.execute(
            """
            INSERT INTO token_usage (org_id, agent_name, model,
                                     prompt_tokens, completion_tokens, total_tokens)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            org_id, agent_name, model_name,
            prompt_tokens, completion_tokens, total,
        )
```

### 13.3 Performance Metrics

```python
class MetricsCollector:
    async def collect_org_metrics(self, org_id: str, period_days: int = 30):
        """Collect key performance metrics."""

        # Cycle time
        cycle_times = await db.fetch(
            """
            SELECT
                EXTRACT(DAY FROM (metadata->>'deployed_at'::timestamp -
                                  metadata->>'created_at'::timestamp)) AS cycle_days
            FROM prd_documents
            WHERE org_id = $1 AND status = 'deployed'
            AND (metadata->>'deployed_at'::timestamp) >= NOW() - $2 * INTERVAL '1 day'
            """,
            org_id, period_days,
        )

        cycle_list = [row['cycle_days'] for row in cycle_times if row['cycle_days']]
        return {
            'cycle_time': {
                'mean': statistics.mean(cycle_list) if cycle_list else 0,
                'median': statistics.median(cycle_list) if cycle_list else 0,
            },
            'throughput': len(cycle_times),
        }
```

### 13.4 Health Check Endpoints

```python
@app.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "healthy"}

@app.get("/health/ready")
async def readiness_check():
    """Readiness check (all dependencies available)."""
    checks = {}

    try:
        await db.fetchval("SELECT 1")
        checks['database'] = "ok"
    except Exception as e:
        checks['database'] = f"error: {str(e)}"

    try:
        await embedding_service.embed("test")
        checks['embeddings'] = "ok"
    except Exception as e:
        checks['embeddings'] = f"error: {str(e)}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "ready": all_ok,
        "checks": checks,
    }
```

---

*(Implementation roadmap is at the end of Section 17.)*

---

## 14. UI Architecture

### 14.1 Per-User Personalized UI

#### Design Philosophy

Every user sees a **personalized home view** tuned to their role. The AI analyzes their assignments, pending work, blockers, and team activity to surface the **minimum set of things they need to act on today**.

No dashboards full of noise — just what matters to you, right now.

#### Home View per Role

#### Developer Home

```
┌─────────────────────────────────────────────────────────────────┐
│  Bodhiorchard                                    Arun • Atoa • ⚙    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Good morning, Arun                          Thu, Mar 5 2026    │
│                                                                 │
│  ┌─── TODAY'S FOCUS ───────────────────────────────────────┐    │
│  │                                                         │    │
│  │  🔴 PRD-042 Payment Retry Logic                        │    │
│  │     2 review comments pending on PR #847                │    │
│  │     ⚠ Design changed yesterday — check with Mike        │    │
│  │     [View PR] [View PRD]                                │    │
│  │                                                         │    │
│  │  🟡 PRD-048 User Onboarding V2                         │    │
│  │     Tech spec approved — ready to start implementation  │    │
│  │     Estimated: 3 days • Complexity: Medium              │    │
│  │     [Start Implementation]                              │    │
│  │                                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─── ATTENTION NEEDED ────────────────────────────────────┐    │
│  │                                                         │    │
│  │  ⚡ Bug #291 — Critical customer bug (Acme Corp, $120k) │    │
│  │     Assigned to you • PRD-039 reopened                  │    │
│  │     Priority: 8.5/10 • Filed 2h ago                     │    │
│  │     [View Bug] [View Ticket]                            │    │
│  │                                                         │    │
│  │  💬 PR #843 needs your review (Priya's PR)              │    │
│  │     PRD-045 Search Optimization                         │    │
│  │     [Review PR]                                         │    │
│  │                                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─── YOUR VELOCITY ──────────────────────────────────────┐    │
│  │  This week: 8 commits • 3 PRs merged • 1 PRD completed │    │
│  │  Avg cycle time: 4.2 days (team avg: 5.1)              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─── STANDUP PREVIEW ────────────────────────────────────┐    │
│  │  AI suggests discussing:                                │    │
│  │  • PRD-042 design change impact on your implementation  │    │
│  │  • PRD-039 reopened — customer escalation context       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### PM Home

```
┌─────────────────────────────────────────────────────────────────┐
│  Bodhiorchard                                   Sarah • Atoa • ⚙    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Good morning, Sarah                         Thu, Mar 5 2026    │
│                                                                 │
│  ┌─── DECISIONS NEEDED ───────────────────────────────────┐    │
│  │                                                         │    │
│  │  📥 3 feature requests pending your review              │    │
│  │                                                         │    │
│  │  1. "Bulk invoice export" — Sales request               │    │
│  │     AI Score: Revenue impact HIGH, Complexity LOW       │    │
│  │     Recommendation: Take it, fits in current capacity   │    │
│  │     [Approve] [Defer] [Discuss]                         │    │
│  │                                                         │    │
│  │  2. "SSO for enterprise" — Customer request (Acme)      │    │
│  │     AI Score: Revenue impact HIGH, Complexity HIGH      │    │
│  │     Recommendation: Schedule for next month             │    │
│  │     Would deprioritize: PRD-050, PRD-051                │    │
│  │     [Approve] [Defer] [Discuss]                         │    │
│  │                                                         │    │
│  │  3. "Dark mode" — Internal request                      │    │
│  │     AI Score: Revenue impact LOW, Complexity MEDIUM     │    │
│  │     Recommendation: Backlog                             │    │
│  │     [Approve] [Defer] [Backlog]                         │    │
│  │                                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─── CUSTOMER PRIORITY QUEUE ────────────────────────────┐    │
│  │                                                         │    │
│  │  🔴 2 high-priority customer bugs need attention        │    │
│  │                                                         │    │
│  │  Acme Corp ($120k) — Payment retry failing • Score: 8.5 │    │
│  │  BigTech Inc ($85k) — Export timeout • Score: 7.2       │    │
│  │                                                         │    │
│  │  [View Full Queue]                                      │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─── ENRICHMENT NEEDED ──────────────────────────────────┐    │
│  │  📋 1 new customer needs profile enrichment             │    │
│  │  NewStartup Inc — first ticket filed, no revenue data   │    │
│  │  [Enrich Profile]                                       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─── PIPELINE STATUS ────────────────────────────────────┐    │
│  │  Active PRDs: 8   In Dev: 4   In QA: 2   In UAT: 1    │    │
│  │  Reopened: 1      Deployed this week: 2                 │    │
│  │  Team utilization: 78%                                  │    │
│  │  [View Board]                                           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### QA Home

```
┌─────────────────────────────────────────────────────────────────┐
│  Bodhiorchard                                   James • Atoa • ⚙    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Good morning, James                         Thu, Mar 5 2026    │
│                                                                 │
│  ┌─── READY FOR QA ──────────────────────────────────────┐     │
│  │                                                         │    │
│  │  PRD-045 Search Optimization                            │    │
│  │    Moved to in-qa 3h ago • Dev: Priya                   │    │
│  │    Test plan: 12 automation + 5 manual cases            │    │
│  │    [Start QA] [View Test Plan]                          │    │
│  │                                                         │    │
│  │  PRD-041 Notification Preferences                       │    │
│  │    Moved to in-qa yesterday • Dev: Arun                 │    │
│  │    Test plan: 8 automation + 3 manual cases             │    │
│  │    [Start QA] [View Test Plan]                          │    │
│  │                                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─── YOUR ACTIVE QA ────────────────────────────────────┐     │
│  │                                                         │    │
│  │  PRD-043 User Dashboard                                 │    │
│  │    Automation: 14/18 passing (3 flaky, 1 failing)       │    │
│  │    Manual: 4/7 verified                                 │    │
│  │    Bugs filed: 2 (1 medium, 1 low)                      │    │
│  │    [Continue QA] [View Results]                          │    │
│  │                                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─── UAT / PROD VERIFICATION ───────────────────────────┐     │
│  │                                                         │    │
│  │  PRD-039 Payment Processing (REOPENED)                  │    │
│  │    Waiting for dev fix → will return to you for QA      │    │
│  │                                                         │    │
│  │  PRD-038 Report Builder                                 │    │
│  │    In UAT • Manual spot-check needed                    │    │
│  │    [Run UAT Checklist]                                  │    │
│  │                                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─── YOUR SKILLS UPDATE ────────────────────────────────┐     │
│  │  Top coverage: Payments (92%), Search (78%), Auth (85%) │    │
│  │  Suggested: Build automation for Notifications module   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### Support Home

```
┌─────────────────────────────────────────────────────────────────┐
│  Bodhiorchard                                    Alex • Atoa • ⚙    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─── OPEN TICKETS ──────────────────────────────────────┐     │
│  │                                                         │    │
│  │  🔴 3 critical/high • 🟡 5 medium • 🟢 2 low           │    │
│  │                                                         │    │
│  │  Acme Corp — "Payments failing on retry" • Score: 8.5   │    │
│  │    Status: Linked to PRD-039 (reopened, dev assigned)   │    │
│  │    [View] [Update Customer]                             │    │
│  │                                                         │    │
│  │  BigTech — "Export hangs after 10k rows" • Score: 7.2   │    │
│  │    Status: New bug filed, waiting PM triage             │    │
│  │    [View] [Escalate]                                    │    │
│  │                                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─── RESOLUTION UPDATES (send to customer) ──────────────┐    │
│  │                                                         │    │
│  │  PRD-037 API Rate Limiting — deployed today             │    │
│  │    3 customer tickets can be closed                      │    │
│  │    [Draft Response] [Close Tickets]                     │    │
│  │                                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### AI-Powered Daily Focus Generation

The **Home Agent** (a lightweight sub-agent, not a full standalone agent) runs at login or on demand:

```python
class HomeViewGenerator:
    """Generates personalized home view content per user per role."""

    async def generate(self, user: User, org_id: uuid.UUID) -> HomeView:
        membership = await get_membership(user.id, org_id)

        # Common data
        assigned_prds = await prd_service.get_assigned(user.id, org_id)
        assigned_bugs = await bug_service.get_assigned(user.id, org_id)
        standup_preview = await standup_service.get_preview(user.id, org_id)

        # Role-specific sections
        match membership.role:
            case "developer" | "designer":
                return await self._dev_home(user, org_id, assigned_prds, assigned_bugs, standup_preview)
            case "pm":
                return await self._pm_home(user, org_id, assigned_prds)
            case "qa":
                return await self._qa_home(user, org_id, assigned_prds, assigned_bugs)
            case "tech_lead":
                return await self._lead_home(user, org_id, assigned_prds)
            case "support":
                return await self._support_home(user, org_id)
            case "viewer" | "org_admin" | "org_owner":
                return await self._overview_home(user, org_id)

    async def _dev_home(self, user, org_id, prds, bugs, standup) -> HomeView:
        # Prioritize: critical bugs > PRD changes > pending reviews > active work
        focus_items = []

        # Critical bugs first
        critical_bugs = [b for b in bugs if b.priority_score >= 7.0]
        for bug in critical_bugs:
            focus_items.append(FocusItem(
                priority="critical",
                title=f"Bug #{bug.id}: {bug.title}",
                subtitle=self._bug_subtitle(bug),
                actions=["view_bug", "view_ticket"],
            ))

        # PRDs with changes affecting this user
        for prd in prds:
            changes = await prd_service.get_recent_changes(prd.id, since=user.last_login)
            if changes.has_design_change or changes.has_scope_change:
                focus_items.append(FocusItem(
                    priority="warning",
                    title=f"PRD-{prd.prd_number}: {prd.title}",
                    subtitle=f"{'Design' if changes.has_design_change else 'Scope'} changed — review impact",
                    actions=["view_prd", "view_diff"],
                ))

        # Pending PR reviews
        pending_reviews = await github_tools.get_pending_reviews(user.github_username, org_id)
        for pr in pending_reviews:
            focus_items.append(FocusItem(
                priority="info",
                title=f"PR #{pr.number} needs your review",
                subtitle=f"{pr.author} • {pr.title}",
                actions=["review_pr"],
            ))

        # Active work (current PRDs)
        for prd in prds:
            if prd.status in ("in-dev", "tech-spec"):
                focus_items.append(FocusItem(
                    priority="normal",
                    title=f"PRD-{prd.prd_number}: {prd.title}",
                    subtitle=self._prd_progress_subtitle(prd, user),
                    actions=["view_prd", "view_pr"],
                ))

        # Velocity stats
        velocity = await metrics_service.get_user_velocity(user.id, org_id, days=7)

        return HomeView(
            greeting=self._greeting(user),
            focus_items=focus_items[:6],  # Max 6 items — keep it focused
            velocity=velocity,
            standup_preview=standup,
        )
```

#### API Endpoint for Home View

```python
@router.get("/api/home")
async def get_home_view(
    user: User = Depends(get_current_user),
    org: OrgContext = Depends(get_org_context),
) -> HomeViewResponse:
    """Get personalized home view for current user."""
    generator = HomeViewGenerator()
    home = await generator.generate(user, org.org_id)
    return HomeViewResponse(
        user=UserSummary.from_user(user),
        role=org.membership.role,
        focus_items=home.focus_items,
        velocity=home.velocity,
        standup_preview=home.standup_preview,
        sections=home.sections,
    )
```

---

### 14.2 Frontend Architecture (Vue 3)

#### Project Structure

```
frontend/
├── src/
│   ├── main.ts
│   ├── App.vue
│   │
│   ├── router/
│   │   ├── index.ts                  # Route definitions
│   │   └── guards.ts                 # Auth + permission route guards
│   │
│   ├── stores/                       # Pinia stores
│   │   ├── auth.ts                   # User session, JWT, org context
│   │   ├── org.ts                    # Current org, org switching
│   │   ├── prds.ts                   # PRD data
│   │   ├── bugs.ts                   # Bug tracking
│   │   ├── tickets.ts               # Support tickets
│   │   ├── home.ts                  # Home view data
│   │   └── notifications.ts         # Real-time notifications
│   │
│   ├── composables/                  # Shared logic
│   │   ├── usePermission.ts          # Permission checking
│   │   ├── useWebSocket.ts           # Real-time updates
│   │   ├── useTheme.ts              # Dark/light mode
│   │   └── usePagination.ts         # Pagination logic
│   │
│   ├── views/
│   │   ├── auth/
│   │   │   ├── Login.vue
│   │   │   └── OrgSelect.vue        # Multi-org selector
│   │   ├── home/
│   │   │   ├── Home.vue             # Role-based home router
│   │   │   ├── DevHome.vue
│   │   │   ├── PMHome.vue
│   │   │   ├── QAHome.vue
│   │   │   ├── SupportHome.vue
│   │   │   └── LeadHome.vue
│   │   ├── prds/
│   │   │   ├── PRDBoard.vue          # Kanban-style board
│   │   │   ├── PRDDetail.vue
│   │   │   └── PRDCreate.vue
│   │   ├── bugs/
│   │   │   ├── BugList.vue
│   │   │   └── BugDetail.vue
│   │   ├── support/
│   │   │   ├── TicketQueue.vue
│   │   │   ├── TicketDetail.vue
│   │   │   └── CustomerList.vue
│   │   ├── metrics/
│   │   │   ├── Dashboard.vue
│   │   │   ├── CycleTime.vue
│   │   │   └── SkillProfiles.vue
│   │   ├── capacity/
│   │   │   └── Capacity.vue
│   │   └── settings/
│   │       ├── OrgSettings.vue
│   │       ├── Members.vue
│   │       └── Integrations.vue
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── AppShell.vue          # Main layout wrapper
│   │   │   ├── Sidebar.vue           # Role-aware sidebar
│   │   │   ├── TopBar.vue
│   │   │   └── OrgSwitcher.vue
│   │   ├── common/
│   │   │   ├── StatusBadge.vue
│   │   │   ├── PriorityBadge.vue
│   │   │   ├── UserAvatar.vue
│   │   │   ├── FocusCard.vue         # Reusable home focus item
│   │   │   ├── EmptyState.vue
│   │   │   └── PermissionGate.vue    # v-if wrapper for permissions
│   │   └── domain/
│   │       ├── PRDCard.vue
│   │       ├── BugRow.vue
│   │       ├── TicketRow.vue
│   │       └── SkillChart.vue
│   │
│   ├── api/                          # API client layer
│   │   ├── client.ts                 # Axios instance with auth interceptor
│   │   ├── auth.ts
│   │   ├── prds.ts
│   │   ├── bugs.ts
│   │   ├── tickets.ts
│   │   ├── customers.ts
│   │   ├── home.ts
│   │   └── metrics.ts
│   │
│   └── types/                        # TypeScript types
│       ├── models.ts
│       ├── api.ts
│       └── permissions.ts
│
├── public/
├── tailwind.config.ts
├── vite.config.ts
├── tsconfig.json
└── package.json
```

#### Route Definitions with Permission Guards

```typescript
// router/index.ts
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  // Public
  { path: '/login', name: 'login', component: () => import('@/views/auth/Login.vue'), meta: { public: true } },
  { path: '/org-select', name: 'org-select', component: () => import('@/views/auth/OrgSelect.vue'), meta: { requiresAuth: true } },

  // App (requires auth + org)
  {
    path: '/',
    component: () => import('@/components/layout/AppShell.vue'),
    meta: { requiresAuth: true, requiresOrg: true },
    children: [
      // Home (role-aware)
      { path: '', name: 'home', component: () => import('@/views/home/Home.vue') },

      // PRDs
      { path: 'prds', name: 'prd-board', component: () => import('@/views/prds/PRDBoard.vue'), meta: { permission: 'prd.view' } },
      { path: 'prds/new', name: 'prd-create', component: () => import('@/views/prds/PRDCreate.vue'), meta: { permission: 'prd.create' } },
      { path: 'prds/:id', name: 'prd-detail', component: () => import('@/views/prds/PRDDetail.vue'), meta: { permission: 'prd.view' } },

      // Bugs
      { path: 'bugs', name: 'bug-list', component: () => import('@/views/bugs/BugList.vue'), meta: { permission: 'bug.view' } },
      { path: 'bugs/:id', name: 'bug-detail', component: () => import('@/views/bugs/BugDetail.vue'), meta: { permission: 'bug.view' } },

      // Support (support, pm, admin, owner)
      { path: 'support/tickets', name: 'ticket-queue', component: () => import('@/views/support/TicketQueue.vue'), meta: { permission: 'ticket.view' } },
      { path: 'support/tickets/:id', name: 'ticket-detail', component: () => import('@/views/support/TicketDetail.vue'), meta: { permission: 'ticket.view' } },
      { path: 'support/customers', name: 'customer-list', component: () => import('@/views/support/CustomerList.vue'), meta: { permission: 'customer.view' } },
      { path: 'support/priority-queue', name: 'priority-queue', component: () => import('@/views/support/PriorityQueue.vue'), meta: { permission: 'ticket.view' } },

      // Metrics (all roles can view)
      { path: 'metrics', name: 'metrics', component: () => import('@/views/metrics/Dashboard.vue'), meta: { permission: 'metrics.view' } },
      { path: 'metrics/skills', name: 'skill-profiles', component: () => import('@/views/metrics/SkillProfiles.vue'), meta: { permission: 'metrics.view' } },
      { path: 'metrics/cycle-time', name: 'cycle-time', component: () => import('@/views/metrics/CycleTime.vue'), meta: { permission: 'metrics.view' } },

      // Capacity (pm, tech_lead, admin, owner)
      { path: 'capacity', name: 'capacity', component: () => import('@/views/capacity/Capacity.vue'), meta: { permission: 'metrics.view' } },

      // Settings (admin, owner)
      { path: 'settings', name: 'settings', component: () => import('@/views/settings/OrgSettings.vue'), meta: { permission: 'org.config' } },
      { path: 'settings/members', name: 'members', component: () => import('@/views/settings/Members.vue'), meta: { permission: 'org.members.invite' } },
      { path: 'settings/integrations', name: 'integrations', component: () => import('@/views/settings/Integrations.vue'), meta: { permission: 'org.config' } },
    ],
  },

  // Catch-all
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

// Global navigation guard
router.beforeEach(async (to, from) => {
  const auth = useAuthStore()

  // Public routes
  if (to.meta.public) return true

  // Auth check
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // Org check
  if (to.meta.requiresOrg && !auth.currentOrg) {
    return { name: 'org-select' }
  }

  // Permission check
  if (to.meta.permission) {
    const hasAccess = auth.hasPermission(to.meta.permission as string)
    if (!hasAccess) {
      return { name: 'home' }  // Redirect to home if no permission
    }
  }

  return true
})

export default router
```

#### Permission Composable

```typescript
// composables/usePermission.ts
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { ROLE_PERMISSIONS } from '@/types/permissions'

export function usePermission() {
  const auth = useAuthStore()

  const role = computed(() => auth.currentMembership?.role)

  function can(permission: string): boolean {
    if (!role.value) return false

    const perms = ROLE_PERMISSIONS[role.value]
    if (!perms) return false

    // Wildcard check
    if (perms.has('*')) return true

    // Direct match
    if (perms.has(permission)) return true

    // Namespace wildcard
    const namespace = permission.split('.').slice(0, -1).join('.')
    if (perms.has(`${namespace}.*`)) return true

    // Check user-specific overrides (loaded from API)
    const override = auth.permissionOverrides[permission]
    if (override !== undefined) return override

    return false
  }

  function canAny(...permissions: string[]): boolean {
    return permissions.some(p => can(p))
  }

  function canAll(...permissions: string[]): boolean {
    return permissions.every(p => can(p))
  }

  return { can, canAny, canAll, role }
}
```

#### PermissionGate Component

```vue
<!-- components/common/PermissionGate.vue -->
<template>
  <slot v-if="allowed" />
  <slot name="fallback" v-else />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePermission } from '@/composables/usePermission'

const props = defineProps<{
  permission?: string
  anyOf?: string[]
  allOf?: string[]
}>()

const { can, canAny, canAll } = usePermission()

const allowed = computed(() => {
  if (props.permission) return can(props.permission)
  if (props.anyOf) return canAny(...props.anyOf)
  if (props.allOf) return canAll(...props.allOf)
  return true
})
</script>

<!-- Usage -->
<!--
  <PermissionGate permission="prd.create">
    <button @click="createPRD">New PRD</button>
  </PermissionGate>

  <PermissionGate :anyOf="['prd.edit', 'prd.edit.assigned']">
    <PRDEditForm :prd="prd" />
    <template #fallback>
      <PRDReadOnlyView :prd="prd" />
    </template>
  </PermissionGate>
-->
```

#### Role-Aware Sidebar

```typescript
// Sidebar navigation items filtered by permission
const sidebarItems = computed(() => {
  const { can } = usePermission()

  const items = [
    { label: 'Home', icon: 'Home', to: '/', show: true },
    { label: 'PRD Board', icon: 'Layout', to: '/prds', show: can('prd.view') },
    { label: 'Bugs', icon: 'Bug', to: '/bugs', show: can('bug.view') },
    {
      label: 'Support',
      icon: 'Headphones',
      show: can('ticket.view'),
      children: [
        { label: 'Tickets', to: '/support/tickets', show: can('ticket.view') },
        { label: 'Priority Queue', to: '/support/priority-queue', show: can('ticket.view') },
        { label: 'Customers', to: '/support/customers', show: can('customer.view') },
      ],
    },
    { label: 'Capacity', icon: 'BarChart', to: '/capacity', show: can('metrics.view') },
    {
      label: 'Metrics',
      icon: 'TrendingUp',
      show: can('metrics.view'),
      children: [
        { label: 'Dashboard', to: '/metrics', show: true },
        { label: 'Cycle Time', to: '/metrics/cycle-time', show: true },
        { label: 'Skill Profiles', to: '/metrics/skills', show: true },
      ],
    },
    {
      label: 'Settings',
      icon: 'Settings',
      show: can('org.config'),
      children: [
        { label: 'General', to: '/settings', show: can('org.config') },
        { label: 'Members', to: '/settings/members', show: can('org.members.invite') },
        { label: 'Integrations', to: '/settings/integrations', show: can('org.config') },
      ],
    },
  ]

  return items.filter(i => i.show)
})
```

---

### 14.3 UI Design System

#### Tech Stack

```json
{
  "vue": "^3.4",
  "typescript": "^5.3",
  "tailwindcss": "^3.4",
  "@headlessui/vue": "^1.7",
  "lucide-vue-next": "^0.300",
  "apexcharts": "^3.44",
  "vue3-apexcharts": "^1.5",
  "vueuse": "^10.7",
  "@tanstack/vue-table": "^8.10"
}
```

#### Design Tokens

```css
/* tailwind.config.ts extended theme */
:root {
  /* Brand */
  --color-primary-50: #eff6ff;
  --color-primary-500: #3b82f6;
  --color-primary-600: #2563eb;
  --color-primary-700: #1d4ed8;

  /* Semantic */
  --color-success: #10b981;
  --color-warning: #f59e0b;
  --color-danger: #ef4444;
  --color-info: #6366f1;

  /* Surface (light) */
  --surface-primary: #ffffff;
  --surface-secondary: #f8fafc;
  --surface-elevated: #ffffff;
  --surface-border: #e2e8f0;

  /* Text */
  --text-primary: #0f172a;
  --text-secondary: #475569;
  --text-muted: #94a3b8;

  /* Spacing scale */
  --space-xs: 0.25rem;
  --space-sm: 0.5rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
  --space-xl: 2rem;

  /* Radius */
  --radius-sm: 0.375rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;

  /* Shadow */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1);
  --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1);
}

/* Dark mode */
[data-theme="dark"] {
  --surface-primary: #0f172a;
  --surface-secondary: #1e293b;
  --surface-elevated: #1e293b;
  --surface-border: #334155;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
}
```

#### Component Library Pattern

All components follow a consistent pattern:

```vue
<!-- components/common/FocusCard.vue -->
<template>
  <div
    :class="[
      'rounded-lg border p-4 transition-all hover:shadow-md',
      priorityClasses[priority]
    ]"
  >
    <div class="flex items-start justify-between">
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 mb-1">
          <span :class="['w-2 h-2 rounded-full', dotClasses[priority]]" />
          <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
            {{ title }}
          </h3>
        </div>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {{ subtitle }}
        </p>
      </div>
      <div class="flex gap-2 ml-4 flex-shrink-0">
        <button
          v-for="action in actions"
          :key="action.key"
          class="text-xs font-medium text-blue-600 hover:text-blue-800 dark:text-blue-400"
          @click="$emit('action', action.key)"
        >
          {{ action.label }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  subtitle: string
  priority: 'critical' | 'warning' | 'info' | 'normal'
  actions: { key: string; label: string }[]
}>()

defineEmits<{
  action: [key: string]
}>()

const priorityClasses = {
  critical: 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950',
  warning: 'border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950',
  info: 'border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950',
  normal: 'border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800',
}

const dotClasses = {
  critical: 'bg-red-500',
  warning: 'bg-amber-500',
  info: 'bg-blue-500',
  normal: 'bg-gray-400',
}
</script>
```

### 14.4 Modularization & Design Patterns

#### Backend Architecture (Layered)

```
┌─────────────────────────────────────────────┐
│              Routes (API Layer)              │
│  Thin — validation, auth, call service      │
├─────────────────────────────────────────────┤
│              Services (Business Logic)       │
│  Orchestration, business rules, validation  │
├─────────────────────────────────────────────┤
│              Repositories (Data Access)      │
│  SQL queries, ORM, data mapping             │
├─────────────────────────────────────────────┤
│              Models (Domain)                 │
│  Pydantic schemas, SQLAlchemy models        │
├─────────────────────────────────────────────┤
│              Infrastructure                  │
│  DB connections, external APIs, cache       │
└─────────────────────────────────────────────┘
```

#### Module Structure

```python
# Each domain is a self-contained module
# backend/app/modules/prds/
#   ├── __init__.py
#   ├── router.py      # FastAPI route definitions
#   ├── service.py     # Business logic
#   ├── repository.py  # Database queries
#   ├── schemas.py     # Pydantic request/response models
#   ├── models.py      # SQLAlchemy ORM models
#   └── exceptions.py  # Domain-specific exceptions

# router.py — thin, delegates to service
from fastapi import APIRouter, Depends
from .schemas import CreatePRDRequest, PRDResponse
from .service import PRDService

router = APIRouter(prefix="/api/prds", tags=["PRDs"])

@router.post("", response_model=PRDResponse, status_code=201)
async def create_prd(
    request: CreatePRDRequest,
    user: User = Depends(has_permission("prd.create")),
    org: OrgContext = Depends(get_org_context),
    service: PRDService = Depends(get_prd_service),
):
    return await service.create(request, org.org_id, user)


# service.py — business logic, orchestration
class PRDService:
    def __init__(self, repo: PRDRepository, embedding_svc: EmbeddingService):
        self.repo = repo
        self.embedding_svc = embedding_svc

    async def create(self, request: CreatePRDRequest, org_id: uuid.UUID, user: User) -> PRD:
        # Generate PRD number
        next_number = await self.repo.get_next_prd_number(org_id)

        # Create PRD
        prd = PRDCreate(
            org_id=org_id,
            prd_number=f"PRD-{datetime.now().year}-{next_number:03d}",
            title=request.title,
            status="draft",
            content_md=request.description,
            metadata={"created_by": str(user.id), "complexity_score": request.complexity_score},
        )
        saved = await self.repo.create(prd)

        # Generate embedding
        embedding = await self.embedding_svc.embed(f"{saved.title}\n{saved.content_md}")
        await self.repo.update_embedding(saved.id, embedding)

        return saved


# repository.py — pure data access
class PRDRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, prd: PRDCreate) -> PRD:
        db_prd = PRDModel(**prd.dict())
        self.session.add(db_prd)
        await self.session.flush()
        return PRD.from_orm(db_prd)

    async def get_next_prd_number(self, org_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.max(PRDModel.prd_number_seq), 0) + 1)
            .where(PRDModel.org_id == org_id)
        )
        return result.scalar()

    async def vector_search(
        self, embedding: list[float], org_id: uuid.UUID, top_k: int = 5
    ) -> list[PRD]:
        result = await self.session.execute(
            select(PRDModel)
            .where(PRDModel.org_id == org_id)
            .order_by(PRDModel.embedding.cosine_distance(embedding))
            .limit(top_k)
        )
        return [PRD.from_orm(r) for r in result.scalars()]
```

#### Dependency Injection

```python
# Dependency injection using FastAPI's Depends
from functools import lru_cache

# Database session
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        # Set org context for RLS
        yield session

# Service factory
async def get_prd_service(
    session: AsyncSession = Depends(get_db_session),
) -> PRDService:
    repo = PRDRepository(session)
    embedding_svc = EmbeddingService(settings.OPENAI_API_KEY)
    return PRDService(repo, embedding_svc)

# Org context middleware
async def get_org_context(
    request: Request,
    user: User = Depends(get_current_user),
) -> OrgContext:
    org_id = request.headers.get("X-Org-Id")
    if not org_id:
        raise HTTPException(400, "X-Org-Id header required")

    membership = await get_membership(user.id, uuid.UUID(org_id))
    if not membership or not membership.is_active:
        raise HTTPException(403, "Not a member of this organization")

    # Set RLS context for this request
    await request.state.db.execute(text(f"SET LOCAL app.org_id = '{org_id}'"))

    return OrgContext(org_id=uuid.UUID(org_id), membership=membership)
```

#### Error Handling Pattern

```python
# Domain exceptions
class BodhiorchardError(Exception):
    """Base exception for all Bodhiorchard errors."""
    def __init__(self, message: str, code: str, status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code

class PRDNotFoundError(BodhiorchardError):
    def __init__(self, prd_id: str):
        super().__init__(f"PRD {prd_id} not found", "PRD_NOT_FOUND", 404)

class PermissionDeniedError(BodhiorchardError):
    def __init__(self, permission: str):
        super().__init__(f"Permission denied: {permission}", "PERMISSION_DENIED", 403)

class PRDTransitionError(BodhiorchardError):
    def __init__(self, current: str, target: str):
        super().__init__(
            f"Cannot transition from '{current}' to '{target}'",
            "INVALID_TRANSITION", 422
        )

# Global exception handler
@app.exception_handler(BodhiorchardError)
async def bodhiorchard_error_handler(request: Request, exc: BodhiorchardError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            },
            "request_id": request.state.request_id,
        },
    )
```

#### Event Bus Pattern (Inter-Module Communication)

```python
from typing import Callable, Any
from collections import defaultdict

class EventBus:
    """
    In-process event bus for decoupled inter-module communication.
    Agents and services publish events; other modules subscribe.
    """
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable):
        self._handlers[event_type].append(handler)

    async def publish(self, event_type: str, data: Any):
        for handler in self._handlers[event_type]:
            try:
                await handler(data)
            except Exception as e:
                logger.error(f"Event handler error for {event_type}: {e}")

# Global event bus
event_bus = EventBus()

# Events
class Events:
    PRD_CREATED = "prd.created"
    PRD_STATUS_CHANGED = "prd.status_changed"
    PRD_REOPENED = "prd.reopened"
    BUG_CREATED = "bug.created"
    BUG_THRESHOLD_EXCEEDED = "bug.threshold_exceeded"
    TICKET_CREATED = "ticket.created"
    PR_MERGED = "pr.merged"
    CUSTOMER_CREATED = "customer.created"

# Publishing (in service)
class PRDService:
    async def update_status(self, prd_id, new_status, org_id):
        prd = await self.repo.update_status(prd_id, new_status)
        await event_bus.publish(Events.PRD_STATUS_CHANGED, {
            "prd_id": prd_id, "old_status": prd.status, "new_status": new_status, "org_id": org_id,
        })
        return prd

# Subscribing (in agent or another service)
async def on_prd_deployed(data):
    """Trigger Learning Agent when a PRD is deployed."""
    if data["new_status"] == "deployed":
        await learning_agent.run(prd_id=data["prd_id"], org_id=data["org_id"])

event_bus.subscribe(Events.PRD_STATUS_CHANGED, on_prd_deployed)

async def on_bug_threshold(data):
    """Trigger Reassignment Agent when bug threshold exceeded."""
    await reassignment_agent.run(prd_id=data["prd_id"], org_id=data["org_id"])

event_bus.subscribe(Events.BUG_THRESHOLD_EXCEEDED, on_bug_threshold)
```

---

## 15. Support Integration

This addendum covers features F13–F15 which extend the core Bodhiorchard platform with customer-facing support ticket integration, customer revenue-based profiling, and a PRD reopening lifecycle.

---

### 15.1 New Features (F13-F15)

### F13. Support Ticket Integration (Customer Bugs → Dev Lifecycle)
- Support tickets (from Freshdesk, Zendesk, Intercom, or Slack) feed into the Bodhiorchard lifecycle as **customer bugs**
- **Support Agent** (new Agent #9) triages incoming tickets:
  - Semantic search: is this a known bug? Is there already a PRD for this feature?
  - If known bug → link ticket to existing bug → notify customer with status/ETA
  - If new bug → create a bug linked to the relevant PRD (or flag for manual linking)
  - If it traces to an old PR → the bug gets linked to that PR and the originating PRD
- Customer bugs can **reopen a deployed PRD** — the PRD status reverts from `deployed` to `in-dev` or `in-qa` and the full tracking lifecycle restarts
- Support tickets carry a **customer priority score** derived from customer profiling (F14)

### F14. Customer Profiling & Revenue-Based Prioritization
- When the **first ticket** is raised by a customer (or their company), the system asks for / looks up:
  - **Average revenue** (ARR/MRR) from this customer
  - **Contract tier** (enterprise, pro, starter)
  - **Strategic importance** (partnership, reference customer, churning risk)
- This creates a **customer profile** that is used for all future tickets from this customer
- Every incoming support ticket is auto-scored:
  - `priority_score = revenue_weight * severity_weight * strategic_weight`
  - Higher-revenue customers with critical bugs surface at the top of the roadmap
- PM sees a **prioritized support bug queue** where customer bugs are ranked by this composite score alongside the internal roadmap
- The Triage Agent (F1) incorporates customer priority when recommending what to work on next

### F15. PRD Reopening Lifecycle
- A deployed PRD can be **reopened** when:
  - A customer bug traces back to it (via Support Agent)
  - A regression is discovered (via internal QA Bug Linker)
  - A feature request modifies an existing deployed feature
- Reopening flow:
  1. Bug/ticket filed → links to deployed PRD
  2. Support Agent or Bug Linker Agent determines severity warrants reopening
  3. PRD status transitions: `deployed` → `reopened`
  4. PRD folder moves from `deployed/` back to `active/`
  5. Original implementation plan gets a new section: "Reopened — Round N"
  6. A new linked PR branch is created referencing the PRD
  7. Dev assignment uses Skill Agent to recommend the best person (ideally original author)
  8. Full lifecycle restarts: `reopened` → `in-dev` → `in-qa` → `in-uat` → `deployed`
- PRD metadata tracks reopening history:
  ```yaml
  reopened_history:
    - round: 2
      reason: "customer_bug"
      ticket_id: "TICKET-2026-891"
      customer: "acme_corp"
      reopened_at: "2026-03-05T10:30:00Z"
      linked_pr: 912
  ```
- Metrics track: how often PRDs get reopened, by which customers, and which modules are most fragile

---

### 15.2 Agent #9: Support Agent

**Trigger**: Incoming support ticket (via webhook from Freshdesk/Zendesk/Intercom, or Slack message in #support channel)

**Responsibilities**:
- Parse incoming support ticket (title, description, customer info, severity)
- Look up or create **customer profile** (ask for revenue/tier if first ticket)
- Calculate **customer priority score**
- Semantic search: match ticket to existing bugs, PRDs, or code areas
- If match found:
  - Link ticket to existing bug → notify customer with status/ETA
  - If the bug is critical and the PRD is deployed → trigger PRD reopening
- If no match:
  - Create new bug, auto-link to most likely PRD via vector search
  - If no PRD match → flag for PM to triage
- Track all tickets per customer for pattern detection ("this customer has reported 5 bugs in payments this month")

**Tools**: Support platform API (Freshdesk/Zendesk/Intercom), Slack API, Vector DB search, PRD repo read/write, Bug service, Customer profile DB

**Interaction with Other Agents**:
- Calls **Bug Linker Agent** to link bugs to PRDs
- Calls **Reassignment Agent** if a reopened PRD needs dev reassignment
- Calls **Skill Agent** to recommend who should fix the reopened PRD
- Feeds data to **Triage Agent** for roadmap prioritization (customer priority scores)
- Feeds data to **Standup Agent** (customer bug urgency flags in standup)

### Agent Class Structure

```python
from agno.agent import Agent
import uuid
from datetime import datetime

class SupportAgent(Agent):
    name = "Support Agent"
    description = "Triages customer support tickets, manages customer profiles, and triggers PRD reopening"

    tools = [
        SupportPlatformTools(),   # Freshdesk/Zendesk/Intercom API
        SlackTools(),
        VectorSearchTools(),
        PRDRepoTools(),
        BugServiceTools(),
        CustomerProfileTools(),
    ]

    async def run(self, ticket: SupportTicket, org_id: uuid.UUID) -> SupportResult:
        # Step 1: Look up or create customer profile
        customer = await self.get_or_create_customer_profile(
            org_id=org_id,
            customer_email=ticket.reporter_email,
            customer_company=ticket.company,
        )

        # Step 2: Calculate priority score
        priority_score = self.calculate_priority_score(
            customer=customer,
            severity=ticket.severity,
        )

        # Step 3: Semantic search for matching bugs/PRDs
        matches = await vector_search_tools.search_all(
            query=f"{ticket.title} {ticket.description}",
            org_id=org_id,
            tables=["bugs", "prd_documents", "code_embeddings"],
            top_k=5,
        )

        # Step 4: Determine action
        if matches.has_existing_bug():
            # Link ticket to existing bug
            await bug_service.link_ticket(
                bug_id=matches.best_bug.id,
                ticket_id=ticket.id,
                customer_id=customer.id,
            )
            await self.notify_customer_status(ticket, matches.best_bug)

            # Check if severity warrants reopening a deployed PRD
            if self.should_reopen_prd(matches.best_bug, priority_score):
                await self.trigger_prd_reopen(
                    prd_id=matches.best_bug.prd_id,
                    reason="customer_bug",
                    ticket_id=ticket.id,
                    customer=customer,
                )

            return SupportResult(action="linked_to_existing", bug=matches.best_bug)

        elif matches.has_matching_prd():
            # Create new bug linked to PRD
            bug = await bug_service.create(
                org_id=org_id,
                prd_id=matches.best_prd.id,
                title=ticket.title,
                description=ticket.description,
                severity=ticket.severity,
                source="customer_ticket",
                ticket_id=ticket.id,
                customer_id=customer.id,
                priority_score=priority_score,
            )

            # Check if this deployed PRD needs reopening
            if matches.best_prd.status == "deployed" and priority_score >= org.config.reopen_threshold:
                await self.trigger_prd_reopen(
                    prd_id=matches.best_prd.id,
                    reason="customer_bug",
                    ticket_id=ticket.id,
                    customer=customer,
                )

            return SupportResult(action="new_bug_linked", bug=bug)

        else:
            # No match — create unlinked bug, flag for PM
            bug = await bug_service.create(
                org_id=org_id,
                title=ticket.title,
                description=ticket.description,
                severity=ticket.severity,
                source="customer_ticket",
                ticket_id=ticket.id,
                customer_id=customer.id,
                priority_score=priority_score,
                needs_triage=True,
            )
            await slack_tools.post_message(
                channel=org.pm_channel,
                text=f"🎫 New customer bug needs triage: {ticket.title}\n"
                     f"Customer: {customer.company} (${customer.arr:,.0f} ARR)\n"
                     f"Priority Score: {priority_score:.1f}/10",
            )
            return SupportResult(action="needs_triage", bug=bug)

    async def get_or_create_customer_profile(
        self, org_id: uuid.UUID, customer_email: str, customer_company: str
    ) -> CustomerProfile:
        """Look up customer or create profile, asking for revenue if new."""
        profile = await customer_service.get_by_email(org_id, customer_email)

        if profile:
            return profile

        # New customer — create profile
        # Try to auto-detect company info from domain
        domain = customer_email.split("@")[1]
        company_info = await customer_service.lookup_company(domain)

        # Create profile with available info (PM can enrich later)
        profile = await customer_service.create(
            org_id=org_id,
            email=customer_email,
            company=customer_company or company_info.name,
            domain=domain,
            tier="unknown",  # PM will set this
            arr=company_info.estimated_arr if company_info else 0,
            needs_enrichment=True,
        )

        # Notify PM to enrich customer profile
        await slack_tools.post_message(
            channel=org.pm_channel,
            text=f"📋 New customer profile created for {customer_company or domain}.\n"
                 f"Please enrich: revenue, tier, strategic importance.\n"
                 f"Dashboard: {org.dashboard_url}/customers/{profile.id}",
        )

        return profile

    def calculate_priority_score(
        self, customer: CustomerProfile, severity: str
    ) -> float:
        """
        Calculate composite priority score (0-10).
        Higher = more urgent.
        """
        # Revenue weight (0-4): based on ARR percentile within org
        if customer.arr >= 100000:
            revenue_weight = 4.0
        elif customer.arr >= 50000:
            revenue_weight = 3.0
        elif customer.arr >= 10000:
            revenue_weight = 2.0
        elif customer.arr > 0:
            revenue_weight = 1.0
        else:
            revenue_weight = 0.5  # unknown revenue gets baseline

        # Severity weight (0-3)
        severity_map = {
            "critical": 3.0,    # system down, data loss
            "high": 2.5,        # major feature broken
            "medium": 1.5,      # feature degraded
            "low": 0.5,         # cosmetic, minor
        }
        severity_weight = severity_map.get(severity, 1.0)

        # Strategic weight (0-3): from customer profile
        strategic_map = {
            "enterprise": 3.0,
            "strategic_partner": 2.5,
            "churn_risk": 2.0,
            "pro": 1.5,
            "starter": 1.0,
            "unknown": 0.5,
        }
        strategic_weight = strategic_map.get(customer.tier, 0.5)

        # Composite score (0-10)
        score = (revenue_weight + severity_weight + strategic_weight)
        return min(10.0, score)

    async def trigger_prd_reopen(
        self,
        prd_id: uuid.UUID,
        reason: str,
        ticket_id: str,
        customer: CustomerProfile,
    ):
        """Reopen a deployed PRD for additional work."""
        prd = await prd_service.get(prd_id)

        # Determine reopening round
        reopen_count = len(prd.metadata.get("reopened_history", []))
        round_number = reopen_count + 2  # Round 1 was original, so this is Round 2+

        # Update PRD status
        await prd_service.update_status(
            prd_id=prd_id,
            new_status="reopened",
        )

        # Move PRD folder back to active
        await prd_repo_tools.move_prd(
            prd_number=prd.prd_number,
            from_dir="deployed",
            to_dir="active",
        )

        # Add reopening history
        await prd_service.add_reopen_history(
            prd_id=prd_id,
            round=round_number,
            reason=reason,
            ticket_id=ticket_id,
            customer=customer.company,
        )

        # Add sub-plan to implementation plan
        await prd_repo_tools.append_to_tech_spec(
            prd_number=prd.prd_number,
            content=f"\n\n## Reopened — Round {round_number}\n\n"
                    f"**Reason**: {reason}\n"
                    f"**Ticket**: {ticket_id}\n"
                    f"**Customer**: {customer.company}\n"
                    f"**Date**: {datetime.utcnow().isoformat()}\n\n"
                    f"### Investigation Plan\n\n"
                    f"- [ ] Root cause analysis\n"
                    f"- [ ] Fix implementation\n"
                    f"- [ ] Regression test\n"
                    f"- [ ] Customer verification\n",
        )

        # Use Skill Agent to recommend assignment
        recommendation = await skill_agent.recommend_assignment(
            prd_id=prd_id,
            org_id=prd.org_id,
            prefer_original_author=True,
        )

        # Notify team
        await slack_tools.post_message(
            channel=org.dev_channel,
            text=f"🔄 PRD {prd.prd_number} reopened (Round {round_number})\n"
                 f"Reason: Customer bug from {customer.company} (${customer.arr:,.0f} ARR)\n"
                 f"Recommended assignee: {recommendation.top_pick.name}\n"
                 f"Priority: {ticket.priority_score:.1f}/10",
        )
```

---

### 15.3 Updated PRD Status Lifecycle

The status lifecycle now includes `reopened`:

```
draft → design → tech-spec → in-dev → in-qa → in-uat → deployed
                                                            │
                                                            ▼
                                                        reopened
                                                            │
                                                            ▼
                                                    in-dev → in-qa → in-uat → deployed
                                                                                  │
                                                                              (can reopen again)
```

**Status enum update:**
```sql
CREATE TYPE prd_status AS ENUM (
    'draft',
    'design',
    'tech-spec',
    'in-dev',
    'in-qa',
    'in-uat',
    'deployed',
    'reopened'    -- NEW
);
```

---

### 15.4 New Database Tables

### customer_profiles

```sql
CREATE TABLE customer_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Identity
    company VARCHAR(255) NOT NULL,
    domain VARCHAR(255),
    primary_contact_email VARCHAR(255),
    primary_contact_name VARCHAR(255),

    -- Revenue & Tier (for priority scoring)
    arr NUMERIC(12, 2) DEFAULT 0,            -- Annual Recurring Revenue
    mrr NUMERIC(12, 2) DEFAULT 0,            -- Monthly Recurring Revenue
    tier VARCHAR(50) DEFAULT 'unknown',       -- enterprise, pro, starter, unknown
    strategic_importance VARCHAR(50) DEFAULT 'standard',  -- strategic_partner, churn_risk, reference, standard

    -- Metadata
    contract_start_date DATE,
    contract_end_date DATE,
    total_tickets_filed INT DEFAULT 0,
    avg_ticket_severity NUMERIC(3, 2) DEFAULT 0,
    needs_enrichment BOOLEAN DEFAULT TRUE,    -- PM needs to fill in revenue/tier

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT unique_customer_per_org UNIQUE (org_id, domain)
);

CREATE INDEX idx_customer_profiles_org ON customer_profiles(org_id);
CREATE INDEX idx_customer_profiles_domain ON customer_profiles(org_id, domain);
CREATE INDEX idx_customer_profiles_arr ON customer_profiles(org_id, arr DESC);
```

### support_tickets

```sql
CREATE TABLE support_tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Ticket info
    external_ticket_id VARCHAR(255),          -- ID from Freshdesk/Zendesk/Intercom
    source VARCHAR(50) NOT NULL,              -- freshdesk, zendesk, intercom, slack
    title VARCHAR(500) NOT NULL,
    description TEXT,
    severity VARCHAR(20) NOT NULL DEFAULT 'medium',  -- critical, high, medium, low
    status VARCHAR(30) NOT NULL DEFAULT 'open',      -- open, linked, resolved, closed

    -- Customer link
    customer_id UUID REFERENCES customer_profiles(id),
    reporter_email VARCHAR(255),
    reporter_name VARCHAR(255),

    -- Internal linking
    bug_id UUID REFERENCES bugs(id),           -- linked internal bug
    prd_id UUID REFERENCES prd_documents(id),  -- linked PRD (if PRD was reopened)
    linked_pr VARCHAR(255),                     -- old PR this traces back to

    -- Priority
    priority_score NUMERIC(4, 2) DEFAULT 0,    -- calculated composite score (0-10)

    -- Resolution
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,

    -- Embedding for semantic search
    embedding vector(768),  -- Configurable: set via EMBEDDING_DIMENSIONS

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_support_tickets_org ON support_tickets(org_id);
CREATE INDEX idx_support_tickets_customer ON support_tickets(customer_id);
CREATE INDEX idx_support_tickets_bug ON support_tickets(bug_id);
CREATE INDEX idx_support_tickets_prd ON support_tickets(prd_id);
CREATE INDEX idx_support_tickets_priority ON support_tickets(org_id, priority_score DESC);
CREATE INDEX idx_support_tickets_status ON support_tickets(org_id, status);
CREATE INDEX idx_support_tickets_embedding ON support_tickets
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200);

-- Enable RLS
ALTER TABLE support_tickets ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation_support_tickets ON support_tickets
    USING (org_id = current_setting('app.org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.org_id')::uuid);

ALTER TABLE customer_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation_customer_profiles ON customer_profiles
    USING (org_id = current_setting('app.org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.org_id')::uuid);
```

### PRD reopening history (added to prd_documents)

```sql
-- Add reopened tracking columns to prd_documents
ALTER TABLE prd_documents
    ADD COLUMN reopen_count INT DEFAULT 0,
    ADD COLUMN last_reopened_at TIMESTAMPTZ,
    ADD COLUMN reopened_history JSONB DEFAULT '[]'::jsonb;

-- Index for finding frequently reopened PRDs
CREATE INDEX idx_prd_reopen_count ON prd_documents(org_id, reopen_count DESC)
    WHERE reopen_count > 0;
```

### Bugs table extension (add customer/ticket fields)

```sql
-- Extend bugs table with customer ticket linkage
ALTER TABLE bugs
    ADD COLUMN source VARCHAR(30) DEFAULT 'internal',  -- internal, customer_ticket
    ADD COLUMN ticket_id UUID REFERENCES support_tickets(id),
    ADD COLUMN customer_id UUID REFERENCES customer_profiles(id),
    ADD COLUMN priority_score NUMERIC(4, 2) DEFAULT 0;

CREATE INDEX idx_bugs_ticket ON bugs(ticket_id);
CREATE INDEX idx_bugs_customer ON bugs(customer_id);
CREATE INDEX idx_bugs_priority ON bugs(org_id, priority_score DESC);
```

---

### 15.5 New API Endpoints

### Support Tickets

```
POST   /api/support/tickets              Create ticket (manual or webhook)
GET    /api/support/tickets              List tickets (filterable by status, customer, priority)
GET    /api/support/tickets/:id          Get ticket details with linked bug/PRD
PUT    /api/support/tickets/:id          Update ticket (status, resolution)
POST   /api/support/tickets/:id/link     Link ticket to existing bug or PRD

POST   /webhooks/freshdesk               Freshdesk webhook handler
POST   /webhooks/zendesk                 Zendesk webhook handler
POST   /webhooks/intercom                Intercom webhook handler
```

### Customer Profiles

```
POST   /api/customers                    Create customer profile
GET    /api/customers                    List customers (sortable by ARR, ticket count)
GET    /api/customers/:id                Get customer with ticket history
PUT    /api/customers/:id                Update customer (enrich revenue, tier, etc.)
GET    /api/customers/:id/tickets        Get all tickets for a customer
GET    /api/customers/priority-queue     Ranked bug queue by customer priority score
```

### PRD Reopening

```
POST   /api/prds/:id/reopen             Reopen a deployed PRD
GET    /api/prds/reopened                List all currently reopened PRDs
GET    /api/prds/:id/reopen-history      Get full reopening history for a PRD
```

### Request/Response Schemas

```python
# Support Ticket
class CreateSupportTicketRequest(BaseModel):
    title: str
    description: str
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    source: Literal["freshdesk", "zendesk", "intercom", "slack", "manual"]
    external_ticket_id: str | None = None
    reporter_email: str
    reporter_name: str | None = None
    company: str | None = None

class SupportTicketResponse(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    severity: str
    priority_score: float
    customer: CustomerProfileSummary | None
    linked_bug: BugSummary | None
    linked_prd: PRDSummary | None
    created_at: datetime

# Customer Profile
class CreateCustomerProfileRequest(BaseModel):
    company: str
    domain: str | None = None
    primary_contact_email: str
    primary_contact_name: str | None = None
    arr: float = 0
    mrr: float = 0
    tier: Literal["enterprise", "pro", "starter", "unknown"] = "unknown"
    strategic_importance: Literal["strategic_partner", "churn_risk", "reference", "standard"] = "standard"

class CustomerProfileResponse(BaseModel):
    id: uuid.UUID
    company: str
    domain: str | None
    arr: float
    tier: str
    strategic_importance: str
    total_tickets_filed: int
    avg_ticket_severity: float
    needs_enrichment: bool

# Customer Priority Queue
class PriorityQueueItem(BaseModel):
    ticket: SupportTicketResponse
    customer: CustomerProfileResponse
    priority_score: float
    linked_prd_status: str | None
    estimated_fix_date: str | None

# PRD Reopen
class ReopenPRDRequest(BaseModel):
    reason: Literal["customer_bug", "regression", "feature_modification"]
    ticket_id: uuid.UUID | None = None
    bug_id: uuid.UUID | None = None
    notes: str | None = None
```

---

### 15.6 Webhook Flows

### Support Ticket → Triage → PRD Reopen Flow

```
1.  Freshdesk/Zendesk sends webhook to POST /webhooks/freshdesk
2.  Webhook router validates signature
3.  Parse ticket payload (title, description, customer email, severity)
4.  Trigger Support Agent
5.  Support Agent: look up customer profile by email/domain
6.  If customer not found:
    a. Create new customer profile (needs_enrichment=true)
    b. Post to PM Slack channel: "New customer, please enrich profile"
7.  Calculate priority_score from customer ARR + severity + tier
8.  Vector search: match ticket to bugs, PRDs, code
9.  If matching existing bug found:
    a. Link ticket to bug
    b. Notify customer: "This is a known issue, status: {status}"
    c. If bug severity × customer priority >= reopen_threshold AND PRD is deployed:
       i.   PRD status → "reopened"
       ii.  Move PRD folder: deployed/ → active/
       iii. Append "Reopened — Round N" to tech spec
       iv.  Skill Agent recommends assignee (prefer original author)
       v.   Notify dev channel with assignment recommendation
       vi.  Reassignment Agent moves current QA to next waiting item
10. If matching PRD found but no existing bug:
    a. Create new bug linked to PRD
    b. Same reopen logic as 9c if severity warrants it
11. If no match:
    a. Create unlinked bug (needs_triage=true)
    b. Post to PM channel with priority score for manual triage
12. Update support_tickets table with all linkages
13. Update customer_profiles.total_tickets_filed
14. Re-embed ticket in vector DB
```

---

### 15.7 Updated Agent Interaction Diagram

```
                                   ┌──────────────────┐
                                   │  Support Platform │
                                   │  (Freshdesk/etc)  │
                                   └────────┬─────────┘
                                            │ webhook
                                            ▼
┌──────────┐   feature req    ┌─────────────────────────┐   known bug?
│  Slack   │ ────────────────▶│    Support Agent (#9)    │──────────────┐
│  Users   │                  │  - customer profiling    │              │
└──────────┘                  │  - priority scoring      │              │
     │                        │  - ticket→bug matching   │              │
     │                        └─────┬──────┬──────┬──────┘              │
     │                              │      │      │                    │
     │                     new bug  │      │      │ reopen PRD         │
     │                              │      │      │                    │
     │                              ▼      │      ▼                    ▼
     │                    ┌──────────────┐  │  ┌──────────────┐  ┌──────────┐
     │   feature req      │  Bug Linker  │  │  │ Reassignment │  │  Link to │
     │                    │  Agent (#6)  │  │  │  Agent (#7)  │  │  existing │
     │                    └──────┬───────┘  │  └──────────────┘  │  bug     │
     │                           │          │                    └──────────┘
     ▼                           │          │
┌──────────────┐                 │          ▼
│ Triage Agent │                 │  ┌──────────────┐
│    (#1)      │◄────────────────┤  │ Skill Agent  │
│ (now also    │  priority data  │  │    (#8)      │
│  considers   │                 │  │ (recommends  │
│  customer    │                 │  │  assignee)   │
│  priority)   │                 │  └──────────────┘
└──────┬───────┘                 │
       │                         │
       ▼                         ▼
┌──────────────┐         ┌──────────────┐
│  PRD Agent   │         │ Standup Agent│
│    (#2)      │         │    (#4)      │
│              │         │ (shows cust  │
└──────────────┘         │  bug flags)  │
                         └──────────────┘
```

---

### 15.8 Configuration Updates

Add to `org-config.yaml`:

```yaml
# Support ticket integration
support:
  enabled: true
  platform: "freshdesk"  # freshdesk, zendesk, intercom, slack
  webhook_secret: "${SUPPORT_WEBHOOK_SECRET}"

  # Priority scoring weights (adjust per org)
  priority_weights:
    revenue:
      tier_1: 4.0    # ARR >= 100k
      tier_2: 3.0    # ARR >= 50k
      tier_3: 2.0    # ARR >= 10k
      tier_4: 1.0    # ARR > 0
      unknown: 0.5   # no revenue data
    severity:
      critical: 3.0
      high: 2.5
      medium: 1.5
      low: 0.5
    strategic:
      enterprise: 3.0
      strategic_partner: 2.5
      churn_risk: 2.0
      pro: 1.5
      starter: 1.0
      unknown: 0.5

  # PRD reopen threshold (priority_score >= this triggers reopen discussion)
  reopen_threshold: 6.0

  # Auto-reopen or require PM approval
  auto_reopen: false  # if true, reopens automatically; if false, flags PM

  # Customer profile enrichment
  customer_enrichment:
    auto_lookup_domain: true    # try to auto-detect company info from email domain
    require_arr_for_priority: false  # if true, unknown-ARR tickets get lowest priority

  # Notification channels
  notification_channels:
    new_customer: "#pm-alerts"
    high_priority_bug: "#dev-urgent"
    prd_reopened: "#dev-channel"
```

---

### 15.9 Vector DB Updates

Add support tickets and customer profiles to the embedding strategy:

| Content Type | Trigger | Chunking Strategy | Purpose |
|---|---|---|---|
| **Support Tickets** | On creation | Title + description | Match new tickets to existing bugs/PRDs |
| **Customer Profiles** | On update | Company + ticket history summary | Pattern detection across customer issues |

---

### 15.10 Dashboard Updates

### New Views

**Customer Priority Queue** (`/dashboard/support-queue`)
- Ranked list of open customer bugs by priority score
- Columns: ticket title, customer, ARR, severity, priority score, linked PRD, status, age
- Filterable by: severity, tier, date range
- Click through to ticket detail with full customer history

**Customer Profiles** (`/dashboard/customers`)
- All customers with ticket counts, ARR, tier
- Click through to see ticket history, bug patterns
- "Needs enrichment" badge for new customers missing revenue data

**PRD Reopening Metrics** (`/dashboard/metrics/reopens`)
- How often PRDs get reopened
- Which modules are most fragile (most reopens)
- Average time-to-fix on reopened PRDs
- Reopens by customer (are certain customers finding more bugs?)

**Standup Enhancements**
- Customer bug urgency flags in daily standup
- "Customer X (enterprise, $200k ARR) has critical bug on PRD-042" shows in standup summary

---

### 15.11 Updated Feature List Summary

| # | Feature | Agent(s) |
|---|---------|----------|
| F1 | Slack Feature Intake & AI Triage | Triage Agent (#1) |
| F2 | PRD-as-Code Repository | PRD Agent (#2) |
| F3 | Enterprise Rules (Living Knowledge Base) | Status Agent (#3) |
| F4 | Auto-Status Updates on PR Merge | Status Agent (#3) |
| F5 | AI-Generated Daily Standups | Standup Agent (#4) |
| F6 | Feature Release Learnings | Learning Agent (#5) |
| F7 | Bug ↔ PRD Linking | Bug Linker Agent (#6) |
| F8 | Bug Threshold Auto-Reassignment | Reassignment Agent (#7) |
| F9 | Skill Tracking & Smart Assignment | Skill Agent (#8) |
| F10 | Multi-Org Support | All agents |
| F11 | Capacity Planning & Dev Workload | Skill Agent (#8) + Dashboard |
| F12 | Vector DB Knowledge Layer | All agents |
| **F13** | **Support Ticket Integration** | **Support Agent (#9)** |
| **F14** | **Customer Profiling & Revenue Prioritization** | **Support Agent (#9)** |
| **F15** | **PRD Reopening Lifecycle** | **Support Agent (#9) + Reassignment (#7) + Skill (#8)** |

**Total: 15 features, 9 agents**

---

## 16. VSCode Extension Spec (Phase 6)

### 16.1 Overview

A **companion extension** for developers only — NOT a replacement for the Vue 3 web UI. The web app serves all 9 roles (org_owner, admin, pm, tech_lead, developer, designer, qa, support, viewer). The VSCode extension targets only developers and tech leads who spend most of their time in the IDE.

### 16.2 Architecture

```
VSCode Extension (TypeScript)
├── sidebar TreeView: My PRDs, My Bugs, Pending Reviews
├── Status Bar: current work context ("PRD-042: Payment Retry [in-dev]")
├── Command Palette: trigger agents, file bugs, view standup
├── Notifications: bug assigned, PRD status change
└── Deep links: "View full PRD" opens web app in browser
```

The extension connects to the **same FastAPI REST API** as the web app. Zero backend changes needed.

### 16.3 Features

| Feature | Implementation | API Endpoint |
|---------|---------------|-------------|
| **My PRDs** | TreeView sidebar panel | `GET /api/prds?assignee={userId}` |
| **My Bugs** | TreeView sidebar panel | `GET /api/bugs?assignee_id={userId}` |
| **Pending Reviews** | TreeView sidebar panel | GitHub API + PRD cross-ref |
| **Current Context** | Status bar item | `GET /api/prds/{id}` |
| **Trigger Agent** | Command palette | `POST /api/agents/{name}/trigger` |
| **File Bug** | Command palette + quick input | `POST /api/bugs` |
| **View Standup** | Webview panel | `GET /api/standups/today` |
| **PRD Status Change** | Notification | WebSocket subscription |
| **Deep Link to Web** | Open in browser | `https://app.bodhiorchard.io/prds/{id}` |

### 16.4 Status Bar Context

```typescript
// Displays current work context in VSCode status bar
// Example: "PRD-042: Payment Retry [in-dev]"

const statusBarItem = vscode.window.createStatusBarItem(
  vscode.StatusBarAlignment.Left, 100
);

async function updateStatusBar() {
  const prds = await api.get('/api/prds?assignee=me&status=in-dev');
  if (prds.length > 0) {
    const prd = prds[0];
    statusBarItem.text = `$(file-code) PRD-${prd.prd_number}: ${prd.title} [${prd.status}]`;
    statusBarItem.tooltip = `Complexity: ${prd.metadata.complexity_score}/10\nEstimated: ${prd.metadata.estimated_days} days`;
    statusBarItem.command = 'bodhiorchard.openPRD';
  }
  statusBarItem.show();
}
```

### 16.5 Command Palette Commands

```
Bodhiorchard: Show My PRDs
Bodhiorchard: Show My Bugs
Bodhiorchard: File a Bug (opens quick input)
Bodhiorchard: Trigger Triage Agent
Bodhiorchard: View Today's Standup
Bodhiorchard: Open PRD Board (opens web app)
Bodhiorchard: Search PRDs (semantic search)
Bodhiorchard: View Capacity
```

### 16.6 Authentication

The extension uses the same JWT tokens as the web app. On first launch:
1. User clicks "Sign in to Bodhiorchard"
2. Extension opens browser to `https://app.bodhiorchard.io/vscode-auth`
3. User logs in, app generates a device token
4. Token is passed back to VSCode via URI handler (`vscode://bodhiorchard/auth?token=...`)
5. Extension stores token in VSCode SecretStorage

### 16.7 Timeline

**Phase 6 (Week 11-14, post-launch)**. Prerequisites:
- Web app and API must be stable (Phases 1-5 complete)
- WebSocket endpoint for real-time notifications
- No backend changes required — uses existing REST API

---

## 17. Deployment Modes

### 17.1 LLM Provider Abstraction

Bodhiorchard uses **LiteLLM** as the LLM abstraction layer, enabling seamless switching between local and cloud providers.

```python
# backend/app/services/llm_service.py
import litellm

class LLMService:
    """Unified LLM interface supporting local (Ollama) and cloud providers."""

    def __init__(self, config: LLMConfig):
        self.default_model = config.model_string    # "ollama/llama3:8b"
        self.premium_model = config.premium_model    # "ollama/llama3:70b" or "gpt-4o"

    async def generate(self, prompt: str, model_tier: str = "default", **kwargs) -> str:
        model = self.premium_model if model_tier == "premium" else self.default_model
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return response.choices[0].message.content
```

### 17.2 Embedding Provider Abstraction

Vector dimensions are **configurable** — not hardcoded to 1536. The embedding service supports multiple providers:

```python
# backend/app/services/embedding_service.py
class EmbeddingService:
    """Multi-provider embedding service."""

    def __init__(self, config: EmbeddingConfig):
        self.provider = config.provider  # "openai", "ollama", "sentence-transformers"
        self.model = config.model
        self.dimensions = config.dimensions  # Used in DB migration

    async def embed(self, text: str) -> list[float]:
        if self.provider == "openai":
            response = await openai_client.embeddings.create(
                model=self.model, input=text
            )
            return response.data[0].embedding
        elif self.provider == "ollama":
            response = await httpx.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            return response.json()["embedding"]
        elif self.provider == "sentence-transformers":
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(self.model)
            return model.encode(text).tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]
```

**Supported Embedding Models:**

| Model | Provider | Dimensions | When to use |
|-------|----------|-----------|-------------|
| `text-embedding-3-small` | OpenAI (API) | 1536 | Cloud deployment |
| `nomic-embed-text` | Ollama | 768 | Local deployment (recommended) |
| `mxbai-embed-large` | Ollama | 1024 | Local deployment (higher quality) |
| `all-MiniLM-L6-v2` | sentence-transformers | 384 | Zero-infrastructure fallback |

### 17.3 Agent Model Tiers

Each agent is assigned a model tier based on task complexity:

| Agent | Model Tier | Rationale | Local Model Viability |
|-------|-----------|-----------|----------------------|
| Triage Agent | `premium` | Nuanced business reasoning | Needs 70B+ locally |
| PRD Agent | `premium` | Long-form document generation | Needs 70B+ locally |
| Support Agent | `premium` | Customer-facing triage needs nuance | Needs 70B+ locally |
| Status Agent | `default` | Simple logic, regex-heavy | Any local model works |
| Standup Agent | `default` | Summarization | 8B+ works well |
| Learning Agent | `default` | Structured output from metrics | 8B+ works well |
| Bug Linker Agent | `default` | Vector search does heavy lifting | Any local model |
| Reassignment Agent | `default` | Mostly DB queries | Any local model |
| Skill Agent | `default` | Pattern recognition | 8B+ works well |

### 17.4 Codebase-Aware Agent Execution (Local Claude Code / API)

Agents that generate PRDs, technical plans, and retrospectives need deep codebase awareness — they must read source files, grep patterns, understand git history, and apply org-level design guidelines. Direct API calls lack this context. Claude Code CLI running on the same machine as Bodhiorchard with the source code accessible locally solves this.

> **Note**: Bodhiorchard runs directly on the machine where the source code lives. There is no separate Mac Mini, remote node, or network discovery — agents execute locally via Claude Code CLI or cloud API calls.

#### 17.4.1 Two Execution Modes (Configurable at Setup)

| Mode | Execution | Codebase Access | Quality | Cost | Complexity |
|------|-----------|----------------|---------|------|------------|
| **A: Local Claude Code** | `claude -p "..."` via subprocess on the Bodhiorchard host | Full filesystem (Read/Glob/Grep/Bash) + Skills + CLAUDE.md | Highest | API key billing | Low |
| **B: Direct API** | `litellm` from Bodhiorchard backend | Limited (prompt-only, no filesystem) | Good | API key billing | Lowest |

Mode A is recommended. Mode B is the fallback when Claude Code is not installed.

#### 17.4.2 Architecture Diagram

```
SLACK / GITHUB
  /bodhiorchard-prd "payment retry"
  /bodhiorchard-triage "thread URL"
               | webhook (via Cloudflare Tunnel or localhost)
               v
  Bodhiorchard Host Machine (Backend + Agents + Source Code)

  ┌─────────────────────────────────────────┐
  │  FastAPI Backend                         │
  │  1. Receive webhook / API request        │
  │  2. Ack immediately                      │
  │  3. Trigger agent via subprocess         │
  │  4. MCP server for Claude Code writeback │
  └──────────────┬──────────────────────────┘
                 │ subprocess (asyncio)
                 v
  ┌─────────────────────────────────────────┐
  │  Claude Code CLI                         │
  │  --output-format json                    │
  │  --max-turns 20                          │
  │  --max-budget-usd 2.00                   │
  └──────────────┬──────────────────────────┘
                 │ filesystem access
                 v
  ┌─────────────────────────────────────────┐
  │  Local Source Code                       │
  │  ~/projects/                             │
  │    service-auth/                         │
  │    service-payments/                     │
  │    frontend-app/                         │
  │                                          │
  │  MCP Writeback --> Bodhiorchard API (localhost)│
  │    - write_prd(title, content, metadata) │
  │    - update_task_status(task_id, status)  │
  │    - post_slack_message(channel, text)    │
  │    - get_prd_context() / get_team_context()│
  └─────────────────────────────────────────┘
```

#### 17.4.3 Local Infrastructure

**Directory layout:**

```
~/
  projects/                       # Source code (configured in setup wizard)
    service-auth/
      CLAUDE.md                   # Per-repo context for Claude Code
    service-payments/
      CLAUDE.md
    frontend-app/
      CLAUDE.md
    bodhiorchard/                      # Bodhiorchard itself
      CLAUDE.md
  .claude/
    CLAUDE.md                     # Org-level context (loaded in ALL sessions)
    settings.json                 # Claude Code settings
    .mcp.json                     # MCP server config (Bodhiorchard writeback)
```

**Networking: Cloudflare Tunnel (optional)**

Public access is provided via Cloudflare Tunnel (see Section 17.5). For local-only deployments, no networking setup is needed — Bodhiorchard runs on `localhost:8000` (API) and `localhost:3000` (UI).

**Process management (launchd on macOS):**

```xml
<!-- ~/Library/LaunchAgents/com.bodhiorchard.runner.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.bodhiorchard.runner</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/Users/bodhiorchard/bodhiorchard-runner/runner.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/bodhiorchard/bodhiorchard-runner/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/bodhiorchard/bodhiorchard-runner/logs/stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>ANTHROPIC_API_KEY</key>
        <string>from-keychain</string>
        <key>BODHIORCHARD_API_URL</key>
        <string>http://localhost:8000</string>
    </dict>
</dict>
</plist>
```

#### 17.4.4 Task Runner Daemon

The daemon runs on the Mac Mini, polls a Redis queue for tasks, and runs the configured CLI tool. On startup, it **self-registers** with the Bodhiorchard backend and waits for admin approval before accepting tasks. It also sends **heartbeats** every 30 seconds.

```python
# bodhiorchard-runner/runner.py
import asyncio, json, platform, psutil, httpx
from pathlib import Path
from enum import Enum

class ExecutionMode(Enum):
    CLAUDE_CODE = "claude_code"       # Mode A
    CODEX = "codex"                   # Mode B
    API = "api"                       # Mode C (runs on backend, not here)

class TaskRunner:
    def __init__(self, config: dict):
        self.redis = redis_from_url(config["redis_url"])
        self.mode = ExecutionMode(config["execution_mode"])
        self.repos_dir = Path(config["repos_dir"])
        self.max_concurrent = config.get("max_concurrent", 3)
        self.max_budget = config.get("max_budget_usd", 2.00)
        self.max_turns = config.get("max_turns", 20)
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        self.mcp_config = config.get("mcp_config", "~/.claude/.mcp.json")
        # Node registration (see 17.4.10)
        self.backend_url = config["bodhiorchard_api_url"]
        self.org_token = config.get("org_token")
        self.node_id = config.get("node_id")          # Populated after registration
        self.node_token = config.get("node_token")      # Populated after registration
        self.active_tasks = 0
        self.active_tasks_count = 0

    async def run(self):
        """Startup sequence: register → wait for approval → poll tasks."""
        # Step 1: Register with backend (17.4.10 L1: Self-Registration)
        await self._register_with_backend()

        # Step 2: Start heartbeat loop (every 30s)
        asyncio.create_task(self._heartbeat_loop())

        # Step 5: Main task loop — poll node-specific Redis queue
        queue_key = f"bodhiorchard:tasks:{self.node_id}"
        while True:
            task_json = await self.redis.brpop(queue_key, timeout=5)
            if task_json:
                _, payload = task_json
                task = json.loads(payload)
                asyncio.create_task(self._execute_with_semaphore(task))

    async def _register_with_backend(self):
        """Self-register with the Bodhiorchard backend. See 17.4.10."""
        if self.node_id and self.node_token:
            # Already registered (re-registration with existing creds)
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.backend_url}/api/nodes/register",
                    json={
                        "hostname": platform.node(),
                        "lan_ip": self._get_local_ip(),
                        "tailscale_ip": self._get_tailscale_ip(),
                        "execution_mode": self.mode.value,
                        "cli_version": self._get_cli_version(),
                        "os_info": f"{platform.system()} {platform.release()}",
                        "capabilities": {
                            "ram_gb": round(psutil.virtual_memory().total / (1024**3)),
                            "cpu_cores": psutil.cpu_count(),
                            "gpu": self._has_gpu(),
                        },
                        "repos": self._list_repos(),
                        "org_token": self.org_token,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                self.node_id = data["node_id"]
                self.node_token = data["node_token"]
                self._save_credentials(data)
                print(f"Registered as {self.node_id} (status: {data['status']})")

    async def _wait_for_approval(self):
        """Poll backend until admin approves this node."""
        print("Waiting for admin approval...")
        while True:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.backend_url}/api/nodes/me",
                    headers={"Authorization": f"Bearer {self.node_token}"},
                )
                status = resp.json()["status"]
                if status == "active":
                    print("Node approved! Starting task runner.")
                    return
                elif status == "rejected":
                    print("Node rejected by admin. Exiting.")
                    raise SystemExit(1)
            await asyncio.sleep(10)

    async def _heartbeat_loop(self):
        """Send heartbeat to backend every 30 seconds."""
        while True:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{self.backend_url}/api/nodes/heartbeat",
                        headers={"Authorization": f"Bearer {self.node_token}"},
                        json={
                            "cpu_percent": psutil.cpu_percent(),
                            "ram_percent": psutil.virtual_memory().percent,
                            "active_tasks": self.active_tasks,
                        },
                    )
            except Exception:
                pass  # Heartbeat failure is non-fatal; backend detects via timeout
            await asyncio.sleep(30)

    async def _execute_task(self, task: dict):
        task_type = task["type"]       # "prd", "tech_plan", "retrospective"
        prompt = task["prompt"]
        repo = task.get("repo")        # Optional: specific repo context
        task_id = task["task_id"]

        cwd = self.repos_dir / repo if repo else self.repos_dir

        try:
            if self.mode == ExecutionMode.CLAUDE_CODE:
                result = await self._run_claude_code(prompt, cwd)
            elif self.mode == ExecutionMode.CODEX:
                result = await self._run_codex(prompt, cwd)
            else:
                raise ValueError("API mode tasks should not reach the runner")

            await self._post_result(task_id, "completed", result)
        except Exception as e:
            await self._post_result(task_id, "failed", str(e))

    async def _run_claude_code(self, prompt: str, cwd: Path) -> str:
        """Run via Claude Code CLI using asyncio.create_subprocess_exec."""
        cmd = [
            "claude", "-p", prompt,
            "--dangerously-skip-permissions",
            "--output-format", "json",
            "--max-turns", str(self.max_turns),
            "--max-budget-usd", str(self.max_budget),
            "--mcp-config", str(self.mcp_config),
            "--no-session-persistence",
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"Claude Code failed: {stderr.decode()}")
        output = json.loads(stdout.decode())
        return output.get("result", stdout.decode())

    async def _run_codex(self, prompt: str, cwd: Path) -> str:
        """Run via Codex CLI (or other configurable CLI tool)."""
        cmd = ["codex", "-p", prompt, "--output-format", "json"]
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        if proc.returncode != 0:
            raise RuntimeError(f"Codex failed: {stderr.decode()}")
        return json.loads(stdout.decode()).get("result", stdout.decode())
```

#### 17.4.5 MCP Server for Claude Code Writeback

Claude Code on the Mac Mini connects to a Bodhiorchard MCP server to write PRDs, update statuses, and post to Slack while generating content.

**MCP config on Mac Mini (`~/.claude/.mcp.json`):**

```json
{
  "mcpServers": {
    "bodhiorchard": {
      "type": "http",
      "url": "http://bodhiorchard-backend.tailnet:8000/mcp",
      "headers": {
        "Authorization": "Bearer ${BODHIORCHARD_INTERNAL_TOKEN}"
      }
    }
  }
}
```

**MCP server endpoint (FastAPI side):**

```python
# backend/app/mcp/server.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/mcp")

# Tool: write_prd
class WritePRDInput(BaseModel):
    title: str
    content: str           # Markdown PRD content
    status: str = "draft"
    repo: str | None
    tags: list[str] = []

@router.post("/tools/write_prd")
async def write_prd(input: WritePRDInput, db=Depends(get_db)):
    """Claude Code calls this MCP tool to save a generated PRD."""
    prd = await db.execute(
        insert(prds).values(
            title=input.title, content=input.content,
            status=input.status, source_repo=input.repo,
            tags=input.tags, created_by="ai-agent",
        ).returning(prds.c.id)
    )
    return {"prd_id": prd.scalar(), "status": "created"}

# Tool: update_task_status
class UpdateStatusInput(BaseModel):
    task_id: str
    status: str            # "in_progress", "completed", "failed"
    result: str | None
    metadata: dict = {}

@router.post("/tools/update_task_status")
async def update_task_status(input: UpdateStatusInput, db=Depends(get_db)):
    """Claude Code reports progress via this MCP tool."""
    await db.execute(
        update(agent_tasks)
        .where(agent_tasks.c.id == input.task_id)
        .values(status=input.status, result=input.result)
    )
    return {"status": "updated"}

# Tool: post_slack_message
class SlackMessageInput(BaseModel):
    channel: str
    text: str
    thread_ts: str | None

@router.post("/tools/post_slack_message")
async def post_slack_message(input: SlackMessageInput, slack=Depends(get_slack)):
    """Claude Code posts results to Slack via this MCP tool."""
    resp = await slack.chat_postMessage(
        channel=input.channel, text=input.text, thread_ts=input.thread_ts,
    )
    return {"ts": resp["ts"], "channel": resp["channel"]}

# Tool: get_prd_context (read existing PRDs for context)
class PRDContextInput(BaseModel):
    prd_id: str | None
    search_query: str | None

@router.post("/tools/get_prd_context")
async def get_prd_context(input: PRDContextInput, db=Depends(get_db)):
    """Claude Code reads existing PRDs before generating new ones."""
    if input.prd_id:
        prd = await db.execute(select(prds).where(prds.c.id == input.prd_id))
        return {"prd": dict(prd.first())}
    elif input.search_query:
        results = await semantic_search(input.search_query, table="prds", limit=5)
        return {"related_prds": results}

# Tool: get_team_context
@router.post("/tools/get_team_context")
async def get_team_context(db=Depends(get_db)):
    """Claude Code reads team capacity and active work."""
    team = await db.execute(select(users).where(users.c.role.in_(["developer", "tech_lead"])))
    active_prds = await db.execute(select(prds).where(prds.c.status == "in-dev"))
    return {
        "team_members": [dict(m) for m in team.fetchall()],
        "active_prds": [dict(p) for p in active_prds.fetchall()],
    }
```

#### 17.4.6 Org-Level Skills (Design Guidelines and Templates)

Skills are stored on the Mac Mini at `~/.claude/skills/` and are automatically available in every Claude Code session.

**Design Guidelines Skill:**

````markdown
<!-- ~/.claude/skills/design-guidelines/SKILL.md -->
---
name: design-guidelines
description: Org design system guidelines, component patterns, UI/UX standards
user-invocable: false
---

# Design Guidelines

## Brand
- Primary: #2563EB (blue-600), Secondary: #7C3AED (violet-600)
- Font: Inter for UI, JetBrains Mono for code
- Border radius: 8px (cards), 6px (inputs), 4px (buttons)

## Component Patterns
- Use headless UI components (Radix/Headless UI style)
- All interactive elements must have focus-visible styles
- Loading states: skeleton screens, not spinners
- Error states: inline messages, not modals

## API Design
- REST with JSON:API conventions
- Snake_case for all field names
- ISO 8601 for all timestamps
- Cursor-based pagination (not offset)

## When writing PRDs
- Reference these guidelines in "Design Requirements" section
- Specify responsive breakpoints: mobile (<768px), tablet (768-1024px), desktop (>1024px)
````

**PRD Template Skill:**

````markdown
<!-- ~/.claude/skills/prd-template/SKILL.md -->
---
name: prd-template
description: Standard PRD template for Bodhiorchard feature requests
user-invocable: true
argument-hint: "[feature description]"
allowed-tools: Read, Glob, Grep, Bash
---

Generate a PRD using this template. Read relevant repos for technical context.
Use the Bodhiorchard MCP tools to save the PRD when complete.

# PRD: [Feature Title]
## 1. Overview
## 2. User Stories
## 3. Technical Approach (read code first!)
## 4. Design Requirements (use /design-guidelines)
## 5. Success Metrics
## 6. Dependencies and Risks
## 7. Timeline Estimate
````

**Tech Plan Template Skill:**

````markdown
<!-- ~/.claude/skills/tech-plan-template/SKILL.md -->
---
name: tech-plan-template
description: Technical implementation plan template, used after PRD approval
user-invocable: true
argument-hint: "[PRD ID or feature name]"
allowed-tools: Read, Glob, Grep, Bash
---

Generate a technical plan. Fetch the PRD via get_prd_context MCP tool.
Read affected repos for context.

# Technical Plan: [Feature]
## 1. Architecture Changes
## 2. Database Migrations
## 3. API Changes
## 4. Implementation Steps
## 5. Testing Strategy
## 6. Rollout Plan
````

#### 17.4.7 Per-Repo CLAUDE.md Files (Microservice Knowledge)

Each cloned repo gets a `CLAUDE.md` giving Claude Code deep context:

````markdown
<!-- ~/repos/service-payments/CLAUDE.md -->
# service-payments

## Tech Stack
Python 3.12, FastAPI, SQLAlchemy 2.0, PostgreSQL 16, Redis 7, Stripe SDK v8

## Architecture
- app/api/ -- FastAPI route handlers
- app/models/ -- SQLAlchemy ORM models
- app/services/ -- Business logic layer
- app/tasks/ -- Celery async tasks (webhook processing)
- app/stripe/ -- Stripe API wrapper

## Key Patterns
- All monetary amounts stored as integers (cents)
- Webhook idempotency via idempotency_key column
- Subscription state machine: trial -> active -> past_due -> canceled

## Testing
- pytest with --cov=app
- Stripe test mode with fixtures in tests/fixtures/stripe_events/

## Common Issues
- Stripe webhook ordering: always fetch latest state, don't trust event data
- Currency: never use float, always integer cents
````

#### 17.4.8 Initial Setup Flow (CLI Wizard)

The setup flow configures the execution mode, registers repos, installs skills, and configures connectivity during first installation.

```python
# bodhiorchard-runner/setup.py
"""Bodhiorchard AI Execution Node Setup Wizard"""
import questionary, yaml
from pathlib import Path

def run_setup():
    print("Bodhiorchard AI Execution Node Setup")
    print("=" * 40)

    # Step 1: Choose execution mode
    mode = questionary.select(
        "Select AI execution mode:",
        choices=[
            {"name": "Claude Code on Mac Mini (best quality)", "value": "claude_code"},
            {"name": "Codex CLI on Mac Mini (OpenAI alternative)", "value": "codex"},
            {"name": "Direct API only (no dedicated machine)", "value": "api"},
        ]
    ).ask()

    config = {"execution_mode": mode}

    if mode in ("claude_code", "codex"):
        # Step 2: Org registration token (see 17.4.10)
        # Admin generates this in Bodhiorchard UI → Settings → Execution Nodes → "Generate Token"
        print("\nStep 2: Organization Registration")
        org_token = questionary.password(
            "Enter your org registration token (from Bodhiorchard admin panel):"
        ).ask()
        config["org_token"] = org_token

        # Validate token and discover backend URL automatically
        backend_url = _discover_backend(org_token)
        if not backend_url:
            backend_url = questionary.text(
                "Bodhiorchard backend URL:", default="http://bodhiorchard-backend.tailnet:8000"
            ).ask()
        config["bodhiorchard_api_url"] = backend_url
        print(f"  ✓ Backend: {backend_url}")

        # Step 3: Register this machine with backend (17.4.10 L1)
        print("\nStep 3: Registering this machine...")
        reg_result = _register_node(config)
        config["node_id"] = reg_result["node_id"]
        config["node_token"] = reg_result["node_token"]
        print(f"  Hostname: {platform.node()}")
        print(f"  LAN IP: {_get_local_ip()}")
        tailscale_ip = _get_tailscale_ip()
        if tailscale_ip:
            print(f"  Tailscale IP: {tailscale_ip}")
        print(f"\n  ✓ Registered! Status: {reg_result['status']}")

        if reg_result["status"] == "pending":
            print("  ⏳ Waiting for admin approval...")
            print("  (Ask your admin to approve in Bodhiorchard → Settings → Execution Nodes)")
            _wait_for_approval(config)
            print("  ✓ Approved! Node is now active.")

        # Step 4: Verify CLI tool is installed
        _verify_cli(mode, config)

        # Step 5: Configure repos directory
        repos_dir = questionary.path("Repos directory:", default="~/repos").ask()
        config["repos_dir"] = repos_dir
        Path(repos_dir).mkdir(parents=True, exist_ok=True)

        # Step 6: Register and clone code repos
        print("\nRegister code repositories for AI context:")
        config["repos"] = _register_repos(repos_dir)

        # Step 7: Configure Tailscale SSH (if not already on Tailscale)
        if not tailscale_ip:
            _setup_tailscale(config)

        # Step 8: Redis connection
        config["redis_url"] = questionary.text(
            "Redis URL:", default=f"redis://{_extract_host(backend_url)}:6379"
        ).ask()

        # Step 9: Install org-level skills
        print("\nInstalling org-level skills...")
        _install_default_skills(Path.home() / ".claude" / "skills")

        # Step 10: Configure MCP server writeback
        _setup_mcp_config(config["bodhiorchard_api_url"], config["node_token"])

        # Step 11: Generate org-level CLAUDE.md
        org_name = questionary.text("Organization name:").ask()
        _generate_org_claude_md(Path.home() / ".claude" / "CLAUDE.md", org_name, config["repos"])

        # Step 12: Concurrency and budget limits
        config["max_concurrent"] = int(questionary.text("Max concurrent tasks:", default="3").ask())
        config["max_budget_usd"] = float(questionary.text("Max budget per task (USD):", default="2.00").ask())
        config["max_turns"] = int(questionary.text("Max turns per task:", default="20").ask())

        # Step 13: Update node registration with final config (repos, capabilities)
        _update_node_registration(config)

    elif mode == "api":
        # API-only mode (no Mac Mini needed)
        config["anthropic_api_key"] = questionary.password("Anthropic API key:").ask()
        config["api_model"] = questionary.select(
            "Default model:",
            choices=["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"]
        ).ask()

    # Save config
    with open("config.yaml", "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    print("\nSetup complete. Run 'python runner.py' to start.")


def _register_repos(repos_dir: str) -> list:
    """Interactive loop to register and clone repos."""
    repos = []
    while True:
        url = questionary.text("Git repo URL (blank to finish):").ask()
        if not url:
            break
        name = url.rstrip("/").split("/")[-1].replace(".git", "")
        branch = questionary.text(f"Default branch for {name}:", default="main").ask()
        repos.append({"url": url, "name": name, "branch": branch})

        repo_path = Path(repos_dir) / name
        if not repo_path.exists():
            print(f"Cloning {url}...")
            _safe_git_clone(url, branch, str(repo_path))

        # Generate per-repo CLAUDE.md if missing
        if not (repo_path / "CLAUDE.md").exists():
            if questionary.confirm(f"Create CLAUDE.md for {name}?").ask():
                _generate_repo_claude_md(repo_path, name)
    return repos
```

#### 17.4.9 Repo Sync (Cron Job)

Keep repos up-to-date on the Mac Mini automatically.

```bash
#!/bin/bash
# ~/bodhiorchard-runner/sync-repos.sh
# Cron: */15 * * * * ~/bodhiorchard-runner/sync-repos.sh
REPOS_DIR="$HOME/repos"
for repo in "$REPOS_DIR"/*/; do
    if [ -d "$repo/.git" ]; then
        cd "$repo" && git fetch --all && git pull --ff-only 2>/dev/null
    fi
done
```

#### 17.4.10 Node Discovery & Registration Protocol

The architecture assumes the Bodhiorchard backend and Mac Mini(s) need to find each other, authenticate, and maintain a persistent connection. This section defines how that works across three discovery layers.

**Problem**: The backend needs to know which execution nodes exist, whether they're healthy, and how to route tasks to them — without requiring manual IP entry.

##### Discovery Mechanisms (Three Layers)

| Layer | Mechanism | Scope | Setup | Best For |
|-------|-----------|-------|-------|----------|
| **L1: Self-Registration** | Runner calls `POST /api/nodes/register` on startup | Any network (LAN, Tailscale, internet) | Runner needs backend URL | Primary — always works |
| **L2: mDNS/Bonjour** | Runner advertises `_bodhiorchard-runner._tcp.local` | Same LAN only | Zero-config | Local dev, small teams |
| **L3: Tailscale Tags** | Backend queries Tailscale API for `tag:bodhiorchard-runner` devices | Tailscale mesh | Tag nodes in Tailscale ACLs | Cross-network, multi-site |

All three layers feed into the same `execution_nodes` table. Discovered nodes always start in `pending` status — an admin must approve before the node receives tasks.

##### Database: `execution_nodes` Table

```python
# backend/app/models/execution_node.py
class ExecutionNode(Base):
    __tablename__ = "execution_nodes"

    id = Column(UUID, primary_key=True, default=uuid4)
    org_id = Column(UUID, ForeignKey("organizations.id"), nullable=False)
    hostname = Column(String, nullable=False)           # e.g. "mac-mini-01"
    display_name = Column(String)                       # Admin-friendly name
    lan_ip = Column(String)                             # 192.168.x.x (LAN)
    tailscale_ip = Column(String)                       # 100.x.x.x (Tailscale mesh)
    advertised_url = Column(String)                     # How runner says to reach it
    health_port = Column(Integer, default=8100)         # Runner health endpoint port
    execution_mode = Column(String, nullable=False)     # "claude_code", "codex"
    status = Column(String, default="pending")          # pending, active, paused, offline, rejected
    discovery_method = Column(String)                   # "self_register", "mdns", "tailscale_tag"

    # Capabilities & resources
    capabilities = Column(JSONB, default={})            # {"gpu": true, "ram_gb": 64, "cpu_cores": 10}
    cli_version = Column(String)                        # "claude 1.0.12" or "codex 0.5.0"
    os_info = Column(String)                            # "macOS 15.3 (Darwin 25.3.0)"
    max_concurrent = Column(Integer, default=3)
    repos = Column(JSONB, default=[])                   # [{"name": "service-auth", "branch": "main"}]

    # Authentication
    node_token_hash = Column(String, nullable=False)    # bcrypt hash of node's bearer token
    approved_by = Column(UUID, ForeignKey("users.id"))  # Admin who approved
    approved_at = Column(DateTime)

    # Health tracking
    last_heartbeat = Column(DateTime)
    active_task_count = Column(Integer, default=0)
    cpu_percent = Column(Float)
    ram_percent = Column(Float)
    total_tasks_completed = Column(Integer, default=0)
    total_tasks_failed = Column(Integer, default=0)

    # Timestamps
    registered_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, onupdate=utcnow)

    # RLS: nodes belong to an org
    __table_args__ = (
        Index("ix_execution_nodes_org_status", "org_id", "status"),
    )
```

##### L1: Self-Registration Flow (Primary)

This is the **always-on** discovery method. The runner daemon registers itself with the backend on every startup.

```
Mac Mini (runner daemon startup)              Bodhiorchard Backend
        |                                            |
  1.    |--- POST /api/nodes/register -------------->|
        |    {                                       |
        |      hostname: "mac-mini-01",              |
        |      lan_ip: "192.168.1.50",               |
        |      tailscale_ip: "100.64.0.1",           |  2. Validate token format
        |      execution_mode: "claude_code",        |     Store in execution_nodes
        |      cli_version: "claude 1.0.12",         |     status = "pending"
        |      os_info: "macOS 15.3",                |     Generate node_token
        |      capabilities: {                       |
        |        gpu: false, ram_gb: 32,             |
        |        cpu_cores: 10                       |
        |      },                                    |
        |      repos: ["service-auth", ...],         |
        |      org_token: "ot_abc123..."             |  3. Verify org_token is valid
        |    }                                       |
        |                                            |
        |<--- 201 Created ---------------------------|
        |    {                                       |
        |      node_id: "uuid-...",                  |
        |      node_token: "nt_xyz789...",           |  4. Runner stores node_token
        |      status: "pending",                    |     in macOS Keychain
        |      message: "Awaiting admin approval"    |
        |    }                                       |
        |                                            |
        |                                            |  5. Admin sees notification in UI:
        |                                            |     "New node: mac-mini-01 (192.168.1.50)"
        |                                            |     [Approve] [Reject]
        |                                            |
        |                                            |  6. Admin clicks [Approve]
        |                                            |     UPDATE execution_nodes
        |                                            |     SET status='active', approved_by=admin_id
        |                                            |
  7.    |--- GET /api/nodes/me ---------------------->|
        |    Authorization: Bearer nt_xyz789...      |
        |<--- { status: "active" } ------------------|
        |                                            |
  8.    |=== NOW POLLING REDIS FOR TASKS ============|
        |                                            |
  9.    |--- POST /api/nodes/heartbeat ------------->|  (every 30s)
        |    {                                       |
        |      cpu_percent: 34.2,                    |
        |      ram_percent: 58.1,                    |
        |      active_tasks: 1,                      |
        |      queue_depth: 0                        |
        |    }                                       |
        |<--- 200 OK -------------------------------|
```

**Backend API endpoints for node management:**

```python
# backend/app/api/nodes.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/nodes", tags=["execution-nodes"])

class NodeRegistration(BaseModel):
    hostname: str
    lan_ip: str | None
    tailscale_ip: str | None
    execution_mode: str              # "claude_code" or "codex"
    cli_version: str
    os_info: str
    capabilities: dict = {}
    repos: list[dict] = []           # [{"name": "service-auth", "branch": "main"}]
    org_token: str                   # One-time org registration token

class NodeRegistrationResponse(BaseModel):
    node_id: str
    node_token: str                  # Bearer token for future requests
    status: str                      # "pending"
    message: str

@router.post("/register", response_model=NodeRegistrationResponse)
async def register_node(input: NodeRegistration, db=Depends(get_db)):
    """Runner calls this on startup to register with the backend."""
    # 1. Verify org_token is valid and unused (or reusable)
    org = await verify_org_registration_token(input.org_token, db)
    if not org:
        raise HTTPException(403, "Invalid or expired organization token")

    # 2. Check if this hostname is already registered (re-registration)
    existing = await db.execute(
        select(execution_nodes)
        .where(execution_nodes.c.org_id == org.id)
        .where(execution_nodes.c.hostname == input.hostname)
    )
    existing_node = existing.first()

    # 3. Generate node token
    node_token = secrets.token_urlsafe(32)
    node_token_prefixed = f"nt_{node_token}"
    hashed = bcrypt.hash(node_token_prefixed)

    if existing_node:
        # Re-registration: update IP, capabilities, keep approval status
        await db.execute(
            update(execution_nodes)
            .where(execution_nodes.c.id == existing_node.id)
            .values(
                lan_ip=input.lan_ip, tailscale_ip=input.tailscale_ip,
                cli_version=input.cli_version, os_info=input.os_info,
                capabilities=input.capabilities, repos=input.repos,
                node_token_hash=hashed, last_heartbeat=utcnow(),
            )
        )
        return NodeRegistrationResponse(
            node_id=str(existing_node.id),
            node_token=node_token_prefixed,
            status=existing_node.status,
            message="Re-registered. Previous approval status preserved."
        )
    else:
        # New registration
        node_id = uuid4()
        await db.execute(
            insert(execution_nodes).values(
                id=node_id, org_id=org.id, hostname=input.hostname,
                lan_ip=input.lan_ip, tailscale_ip=input.tailscale_ip,
                execution_mode=input.execution_mode,
                cli_version=input.cli_version, os_info=input.os_info,
                capabilities=input.capabilities, repos=input.repos,
                node_token_hash=hashed, status="pending",
                discovery_method="self_register",
            )
        )
        # Notify admins (Slack + in-app)
        await notify_admins_new_node(org.id, input.hostname, input.lan_ip)
        return NodeRegistrationResponse(
            node_id=str(node_id),
            node_token=node_token_prefixed,
            status="pending",
            message="Awaiting admin approval. Node will not receive tasks until approved."
        )

@router.get("/me")
async def get_my_status(node=Depends(authenticate_node)):
    """Runner polls this to check if it's been approved."""
    return {"node_id": str(node.id), "status": node.status}

class HeartbeatInput(BaseModel):
    cpu_percent: float
    ram_percent: float
    active_tasks: int
    queue_depth: int = 0
    errors_since_last: int = 0

@router.post("/heartbeat")
async def heartbeat(input: HeartbeatInput, node=Depends(authenticate_node), db=Depends(get_db)):
    """Runner sends this every 30s to prove it's alive."""
    await db.execute(
        update(execution_nodes)
        .where(execution_nodes.c.id == node.id)
        .values(
            last_heartbeat=utcnow(),
            cpu_percent=input.cpu_percent,
            ram_percent=input.ram_percent,
            active_task_count=input.active_tasks,
        )
    )
    return {"status": "ok"}

# Admin endpoints
@router.get("/")
async def list_nodes(user=Depends(require_role("admin", "org_owner")), db=Depends(get_db)):
    """List all execution nodes for this org."""
    nodes = await db.execute(
        select(execution_nodes).where(execution_nodes.c.org_id == user.org_id)
    )
    return [dict(n) for n in nodes.fetchall()]

@router.patch("/{node_id}/approve")
async def approve_node(node_id: UUID, user=Depends(require_role("admin", "org_owner")), db=Depends(get_db)):
    """Admin approves a pending node."""
    await db.execute(
        update(execution_nodes)
        .where(execution_nodes.c.id == node_id)
        .values(status="active", approved_by=user.id, approved_at=utcnow())
    )
    return {"status": "active", "message": "Node approved and will begin receiving tasks."}

@router.patch("/{node_id}/reject")
async def reject_node(node_id: UUID, user=Depends(require_role("admin", "org_owner")), db=Depends(get_db)):
    """Admin rejects a pending node."""
    await db.execute(
        update(execution_nodes)
        .where(execution_nodes.c.id == node_id)
        .values(status="rejected")
    )
    return {"status": "rejected"}

@router.patch("/{node_id}/pause")
async def pause_node(node_id: UUID, user=Depends(require_role("admin", "org_owner")), db=Depends(get_db)):
    """Admin pauses an active node (stops receiving tasks, finishes current ones)."""
    await db.execute(
        update(execution_nodes)
        .where(execution_nodes.c.id == node_id)
        .values(status="paused")
    )
    return {"status": "paused"}
```

##### L2: mDNS/Bonjour Auto-Discovery (Same LAN)

For teams where the Bodhiorchard backend and Mac Mini are on the same local network, zero-config discovery via Bonjour eliminates all manual setup.

**On the Mac Mini** (runner daemon advertises itself):

```python
# bodhiorchard-runner/discovery.py
import socket
from zeroconf import ServiceInfo, Zeroconf

class BonjourAdvertiser:
    """Advertises this runner on the local network via mDNS/Bonjour."""

    SERVICE_TYPE = "_bodhiorchard-runner._tcp.local."

    def __init__(self, hostname: str, port: int, org_id: str, mode: str):
        self.zeroconf = Zeroconf()
        local_ip = self._get_local_ip()
        self.info = ServiceInfo(
            self.SERVICE_TYPE,
            f"{hostname}.{self.SERVICE_TYPE}",
            addresses=[socket.inet_aton(local_ip)],
            port=port,
            properties={
                "version": "0.1.0",
                "mode": mode,            # "claude_code" or "codex"
                "org_id": org_id,
                "hostname": hostname,
            },
        )

    def start(self):
        """Start advertising. Call on daemon startup."""
        self.zeroconf.register_service(self.info)

    def stop(self):
        """Stop advertising. Call on daemon shutdown."""
        self.zeroconf.unregister_service(self.info)
        self.zeroconf.close()

    def _get_local_ip(self) -> str:
        """Get this machine's LAN IP address."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))  # Doesn't actually send data
            return s.getsockname()[0]
        finally:
            s.close()
```

**On the Bodhiorchard backend** (discovers Mac Minis on the LAN):

```python
# backend/app/services/node_discovery.py
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

class LanNodeDiscovery(ServiceListener):
    """Listens for Bodhiorchard runner nodes on the local network via mDNS."""

    SERVICE_TYPE = "_bodhiorchard-runner._tcp.local."

    def __init__(self, db_session_factory, org_id: str):
        self.db_factory = db_session_factory
        self.org_id = org_id
        self.zeroconf = Zeroconf()
        self.browser = None

    def start(self):
        """Start listening for mDNS advertisements."""
        self.browser = ServiceBrowser(self.zeroconf, self.SERVICE_TYPE, self)

    def stop(self):
        self.zeroconf.close()

    def add_service(self, zc: Zeroconf, type_: str, name: str):
        """Called when a new runner is discovered on the network."""
        info = zc.get_service_info(type_, name)
        if not info:
            return
        props = {k.decode(): v.decode() for k, v in info.properties.items()}
        ip = socket.inet_ntoa(info.addresses[0])
        hostname = props.get("hostname", name.split(".")[0])

        # Auto-register as pending (admin must still approve)
        asyncio.create_task(self._register_discovered_node(
            hostname=hostname,
            lan_ip=ip,
            port=info.port,
            mode=props.get("mode", "claude_code"),
            org_id=props.get("org_id", self.org_id),
        ))

    def remove_service(self, zc: Zeroconf, type_: str, name: str):
        """Called when a runner disappears from the network."""
        # Mark node as offline (don't delete — it may come back)
        hostname = name.split(".")[0]
        asyncio.create_task(self._mark_node_offline(hostname))

    def update_service(self, zc: Zeroconf, type_: str, name: str):
        """Called when a runner's mDNS properties change."""
        self.add_service(zc, type_, name)  # Re-register with updated info

    async def _register_discovered_node(self, **kwargs):
        async with self.db_factory() as db:
            existing = await db.execute(
                select(execution_nodes)
                .where(execution_nodes.c.hostname == kwargs["hostname"])
                .where(execution_nodes.c.org_id == kwargs["org_id"])
            )
            if not existing.first():
                await db.execute(
                    insert(execution_nodes).values(
                        id=uuid4(), status="pending",
                        discovery_method="mdns",
                        **kwargs,
                    )
                )
                await notify_admins_new_node(kwargs["org_id"], kwargs["hostname"], kwargs["lan_ip"])
```

##### L3: Tailscale Tag Discovery (Cross-Network)

For multi-site deployments where Mac Minis are on different networks but share a Tailscale mesh.

**Tailscale ACL configuration** (on admin.tailscale.com):

```json
{
  "tagOwners": {
    "tag:bodhiorchard-runner": ["autogroup:admin"]
  },
  "acls": [
    {
      "action": "accept",
      "src": ["tag:bodhiorchard-backend"],
      "dst": ["tag:bodhiorchard-runner:*"]
    }
  ]
}
```

**Tag the Mac Mini:**

```bash
# On Mac Mini
sudo tailscale up --ssh --advertise-tags=tag:bodhiorchard-runner
```

**Backend periodically queries Tailscale API for tagged devices:**

```python
# backend/app/services/tailscale_discovery.py
import httpx

class TailscaleNodeDiscovery:
    """Discovers Bodhiorchard runner nodes via Tailscale device API."""

    def __init__(self, api_key: str, tailnet: str, db_session_factory):
        self.api_key = api_key          # Tailscale API key
        self.tailnet = tailnet          # e.g. "myorg.tailnet.ts.net"
        self.db_factory = db_session_factory
        self.base_url = f"https://api.tailscale.com/api/v2/tailnet/{tailnet}"

    async def discover(self):
        """Poll Tailscale API for devices tagged 'bodhiorchard-runner'."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/devices",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            devices = resp.json()["devices"]

        for device in devices:
            tags = device.get("tags", [])
            if "tag:bodhiorchard-runner" not in tags:
                continue

            hostname = device["hostname"]
            tailscale_ip = device["addresses"][0]  # First Tailscale IP
            is_online = device["online"]

            async with self.db_factory() as db:
                existing = await db.execute(
                    select(execution_nodes)
                    .where(execution_nodes.c.hostname == hostname)
                )
                if not existing.first():
                    # New node discovered via Tailscale tag
                    await db.execute(
                        insert(execution_nodes).values(
                            id=uuid4(), hostname=hostname,
                            tailscale_ip=tailscale_ip,
                            status="pending",
                            discovery_method="tailscale_tag",
                            org_id=await self._resolve_org(device),
                        )
                    )
                    await notify_admins_new_node(None, hostname, tailscale_ip)
                else:
                    # Update online status
                    new_status = "active" if is_online else "offline"
                    await db.execute(
                        update(execution_nodes)
                        .where(execution_nodes.c.hostname == hostname)
                        .values(tailscale_ip=tailscale_ip)
                    )
```

**Discovery schedule:**

| Method | Trigger | Latency |
|--------|---------|---------|
| Self-registration (L1) | Runner startup | Instant |
| mDNS/Bonjour (L2) | Continuous listener | 1-5 seconds |
| Tailscale tags (L3) | Cron every 5 min | Up to 5 minutes |

##### Heartbeat & Health Monitoring

The runner daemon sends heartbeats to the backend every 30 seconds. The backend uses these to track node health and detect failures.

```python
# backend/app/services/node_health.py
class NodeHealthMonitor:
    """Background task that monitors execution node health."""

    HEARTBEAT_INTERVAL = 30          # Expected heartbeat every 30s
    OFFLINE_THRESHOLD = 3            # Mark offline after 3 missed heartbeats (90s)
    DEGRADED_THRESHOLD = 2           # Mark degraded after 2 missed heartbeats (60s)

    async def check_health(self):
        """Run periodically (every 30s) to detect unhealthy nodes."""
        now = utcnow()
        active_nodes = await self.db.execute(
            select(execution_nodes)
            .where(execution_nodes.c.status.in_(["active", "degraded"]))
        )
        for node in active_nodes:
            if not node.last_heartbeat:
                continue
            seconds_since = (now - node.last_heartbeat).total_seconds()

            if seconds_since > self.HEARTBEAT_INTERVAL * self.OFFLINE_THRESHOLD:
                await self._transition(node, "offline")
                await self._notify_admins(node, "offline",
                    f"Node {node.hostname} is offline (no heartbeat for {int(seconds_since)}s)")
                # Requeue any tasks assigned to this node
                await self._requeue_orphaned_tasks(node.id)

            elif seconds_since > self.HEARTBEAT_INTERVAL * self.DEGRADED_THRESHOLD:
                await self._transition(node, "degraded")

    async def _requeue_orphaned_tasks(self, node_id: UUID):
        """Move in-progress tasks from a dead node back to the Redis queue."""
        orphaned = await self.db.execute(
            select(agent_tasks)
            .where(agent_tasks.c.assigned_node == node_id)
            .where(agent_tasks.c.status == "in_progress")
        )
        for task in orphaned:
            await self.redis.lpush("bodhiorchard:tasks", json.dumps({
                "task_id": str(task.id),
                "type": task.type,
                "prompt": task.prompt,
                "repo": task.repo,
                "retry_count": task.retry_count + 1,
            }))

    async def on_heartbeat_received(self, node_id: UUID):
        """Called when a heartbeat arrives. Restore degraded nodes to active."""
        node = await self.get_node(node_id)
        if node.status == "degraded":
            await self._transition(node, "active")
```

**Node status state machine:**

```
                  ┌──────────┐
                  │ rejected │
                  └──────────┘
                       ▲ admin rejects
                       │
  ┌─────────┐    ┌─────────┐    ┌────────┐    ┌─────────┐
  │ (start) │───>│ pending │───>│ active │───>│ paused  │
  └─────────┘    └─────────┘    └────────┘    └─────────┘
   register       admin approves  ▲  │  ▲       │ admin
                                  │  │  │       │ resumes
                                  │  │  └───────┘
                      heartbeat   │  │ 2 missed
                      resumes     │  ▼ heartbeats
                                ┌──────────┐
                                │ degraded │
                                └──────────┘
                                     │ 3 missed
                                     ▼ heartbeats
                                ┌─────────┐
                                │ offline │──> requeue tasks
                                └─────────┘    notify admins
                                     │
                                     │ heartbeat resumes
                                     ▼
                                ┌────────┐
                                │ active │
                                └────────┘
```

##### Multi-Node Task Routing

When an org has multiple Mac Minis, the backend must decide which node gets each task.

```python
# backend/app/services/node_router.py
class NodeRouter:
    """Routes tasks to the best available execution node."""

    async def select_node(self, org_id: UUID, task: dict) -> ExecutionNode | None:
        """Select the best node for a task. Returns None to fallback to API mode."""
        active_nodes = await self.db.execute(
            select(execution_nodes)
            .where(execution_nodes.c.org_id == org_id)
            .where(execution_nodes.c.status == "active")
            .order_by(execution_nodes.c.active_task_count.asc())
        )
        candidates = list(active_nodes.fetchall())

        if not candidates:
            return None  # No active nodes — caller should fallback to Mode C

        # Filter: prefer nodes that have the required repo cloned
        target_repo = task.get("repo")
        if target_repo:
            with_repo = [n for n in candidates if target_repo in [r["name"] for r in (n.repos or [])]]
            if with_repo:
                candidates = with_repo

        # Filter: skip nodes at max capacity
        available = [n for n in candidates if n.active_task_count < n.max_concurrent]
        if not available:
            return None  # All nodes busy — fallback to API mode or queue

        # Strategy: least-loaded node (fewest active tasks)
        return min(available, key=lambda n: n.active_task_count)

    async def route_task(self, org_id: UUID, task: dict) -> str:
        """Route a task to a node or fallback to API mode."""
        node = await self.select_node(org_id, task)

        if node:
            # Push to node-specific Redis queue
            queue_key = f"bodhiorchard:tasks:{node.id}"
            await self.redis.lpush(queue_key, json.dumps(task))
            await self.db.execute(
                update(agent_tasks)
                .where(agent_tasks.c.id == task["task_id"])
                .values(assigned_node=node.id, status="queued")
            )
            return f"Routed to {node.hostname}"
        else:
            # Fallback: run via direct API on the backend
            await self.fallback_to_api(task)
            return "No active nodes — using API fallback"
```

**Routing strategy options** (configurable per org):

| Strategy | Behavior | Best For |
|----------|----------|----------|
| **least-loaded** (default) | Pick node with fewest active tasks | General use |
| **repo-affinity** | Prefer node that has the target repo | Multi-repo orgs |
| **round-robin** | Distribute evenly regardless of load | Equal-spec nodes |
| **dedicated** | Pin specific agents to specific nodes | Isolation / security |

##### Admin UI: Node Management

```
Execution Nodes (Admin view)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

● mac-mini-01 [ACTIVE]                          Discovered: self-register
  IP: 100.64.0.1 (Tailscale) / 192.168.1.50 (LAN)
  Mode: Claude Code v1.0.12 | macOS 15.3
  Tasks: 2/3 | CPU: 34% | RAM: 58%
  Repos: service-auth, service-payments, frontend-app
  Uptime: 14d 3h | Completed: 847 tasks | Failed: 12
  Last heartbeat: 12s ago
  [Pause] [Remove] [View Logs]

● mac-mini-02 [ACTIVE]                          Discovered: mdns
  IP: 100.64.0.2 (Tailscale) / 192.168.1.51 (LAN)
  Mode: Claude Code v1.0.12 | macOS 15.3
  Tasks: 0/3 | CPU: 8% | RAM: 42%
  Repos: service-auth, service-payments
  Uptime: 7d 12h | Completed: 423 tasks | Failed: 5
  Last heartbeat: 5s ago
  [Pause] [Remove] [View Logs]

◌ mac-mini-03 [PENDING]                         Discovered: mdns
  IP: 192.168.1.52 (LAN only — no Tailscale)
  Mode: Codex v0.5.0 | macOS 15.3
  Registered: 2 minutes ago
  [Approve] [Reject]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Routing strategy: least-loaded ▼
Auto-fallback to API: enabled ✓
Discovery: mDNS active ● | Tailscale polling: every 5m ●
```

##### Org Registration Token

To prevent unauthorized nodes from registering, the admin generates a one-time (or reusable) **org registration token** in the Bodhiorchard UI. This token is entered during the Mac Mini setup wizard.

```python
# backend/app/api/org_tokens.py
@router.post("/api/org/registration-token")
async def create_registration_token(
    user=Depends(require_role("admin", "org_owner")),
    db=Depends(get_db),
):
    """Generate a token that Mac Minis use to register with this org."""
    token = f"ot_{secrets.token_urlsafe(32)}"
    await db.execute(
        insert(org_registration_tokens).values(
            id=uuid4(), org_id=user.org_id,
            token_hash=bcrypt.hash(token),
            created_by=user.id,
            expires_at=utcnow() + timedelta(hours=24),
            max_uses=5,  # Allow up to 5 nodes to register with this token
            uses=0,
        )
    )
    return {"token": token, "expires_in": "24 hours", "max_uses": 5}
```

**Setup wizard uses this token:**

```
Bodhiorchard AI Execution Node Setup
========================================
Step 1: Organization Registration
  Enter your org registration token (from Bodhiorchard admin panel):
  > ot_a1b2c3d4e5f6...

  ✓ Token valid. Organization: "Acme Corp"
  ✓ Backend: https://bodhiorchard.acme.corp

Step 2: Registering this machine...
  Hostname: mac-mini-01
  LAN IP: 192.168.1.50
  Tailscale IP: 100.64.0.1

  ✓ Registered! Status: PENDING
  ⏳ Waiting for admin approval...
  (Ask your admin to approve this node in Bodhiorchard → Settings → Execution Nodes)

  ✓ Approved! Node is now active.

Step 3: Choose execution mode...
```

### 17.5 Slack Integration for Agent Triggers (Multi-Mode)

Slack commands dispatch to Redis queue (Modes A/B) or direct API (Mode C).

```python
# backend/app/api/slack_commands.py
@app.post("/api/webhooks/slack/slash")
async def handle_slash_command(request: Request, bg: BackgroundTasks):
    payload = await request.form()
    command, text = payload["command"], payload["text"]
    user_id, channel_id = payload["user_id"], payload["channel_id"]

    if command == "/bodhiorchard-prd":
        task_id = str(uuid4())
        mode = get_org_config().execution_mode

        if mode in ("claude_code", "codex"):
            # Route to best available node (see 17.4.10 Multi-Node Routing)
            task = {
                "task_id": task_id,
                "type": "prd",
                "prompt": (
                    f"Generate a PRD for: {text}. "
                    f"Use /prd-template skill. "
                    f"Read relevant repos for technical context. "
                    f"Use the bodhiorchard MCP tools to save the PRD."
                ),
                "repo": None,
                "requested_by": user_id,
                "channel": channel_id,
            }
            router = NodeRouter(redis=redis, db=db)
            route_result = await router.route_task(org_id, task)
        else:
            # Mode C: Direct API call on the backend
            bg.add_task(generate_prd_via_api, text, task_id, channel_id)

        return {"response_type": "ephemeral", "text": f"Generating PRD... (task: {task_id})"}
```

#### 17.5.1 Agent Execution Path Matrix

| Agent | Execution Path | Why |
|-------|---------------|-----|
| PRD Agent | **Mac Mini (Claude Code/Codex)** | Needs full codebase, design guidelines, PRD template skills |
| Learning Agent | **Mac Mini (Claude Code/Codex)** | Needs git history, code diffs, retrospective analysis |
| Triage Agent | **Mac Mini or API** | Benefits from codebase context but can work with API alone |
| All other agents | **Direct API (LiteLLM)** | Status, Standup, Bug Linker, Reassignment, Skill: no codebase access needed |

#### 17.5.2 Cost Comparison

| Approach | Cost ~20 PRD tasks/day | Quality | Setup |
|----------|----------------------|---------|-------|
| Mac Mini + Claude Code (API key) | ~$40-80/mo API + electricity | Highest | Medium |
| Mac Mini + Codex (API key) | ~$30-60/mo API + electricity | High | Medium |
| Direct API (claude-agent-sdk) | ~$40-80/mo API | Good | Low |
| Optimized mix (Mac Mini for PRD + API for rest) | ~$50-100/mo | Best balance | Medium |

**Note on billing**: The Mac Mini approach uses the `claude` CLI with an **API key** (`ANTHROPIC_API_KEY`) for automated usage, not a personal subscription. Anthropic's Consumer ToS prohibits using Pro/Max subscription tokens in automated services.

#### 17.5.3 Security Considerations

| Concern | Mitigation |
|---------|-----------|
| `--dangerously-skip-permissions` | Mac Mini is dedicated, isolated. No user data besides code repos. |
| API key on Mac Mini | Stored in macOS Keychain, injected via launchd env vars. Never in config files. |
| Tailscale network | Private mesh, not exposed to internet. ACLs restrict node access. |
| MCP token | Short-lived, scoped to internal API. Rotated via setup wizard. |
| Repo access | Read-only clones. Writes go through MCP to Bodhiorchard API only. |
| Budget control | `--max-budget-usd` prevents runaway API costs per task. |

### 17.6 Deployment Modes Matrix

| Mode | LLM | Embeddings | Min Hardware | Quality |
|------|-----|-----------|-------------|---------|
| **Quick Start** | `ollama/llama3:8b` | `ollama/nomic-embed-text` | 16GB RAM, no GPU | Functional |
| **Local Production** | `ollama/llama3:70b` | `ollama/mxbai-embed-large` | 64GB RAM + GPU | Good |
| **Hybrid** | Local default + cloud premium | OpenAI embeddings | 16GB + API key | Best |
| **Full Cloud** | `gpt-4o` / `claude-opus-4` | OpenAI embeddings | Minimal | Highest |
| **Enterprise** | vLLM + Llama 3 70B | Self-hosted BGE | GPU cluster | Production-grade |

### 17.7 Cost Comparison

| Approach | Cost for ~20 tasks/day | Notes |
|----------|----------------------|-------|
| Claude Sonnet 4.6 API | ~$30-60/mo | Best price/performance for most agents |
| Claude Haiku 4.5 API | ~$10-20/mo | Great for simple agents (Status, Bug Linker) |
| Claude Opus 4.6 API | ~$150-300/mo | Only for premium tasks (PRD, Triage) |
| **Optimized mix** | **~$40-80/mo** | Haiku for 6 simple agents + Sonnet for 3 complex agents |
| **Local (Ollama)** | **$0/mo** | Zero marginal cost after hardware |

**Cost optimizations:**
- **Prompt caching**: 90% input cost savings on repeated system prompts
- **Batch API**: 50% off for non-urgent tasks (e.g., nightly standup prep)
- **Model tiering**: Haiku for Status/BugLinker/Reassignment, Sonnet for Triage/PRD/Support

### 17.5 Public Access via Cloudflare Tunnel (Optional)

Bodhiorchard works fully on localhost. For orgs needing Slack webhooks (require public HTTPS) or remote access, **Cloudflare Tunnel** provides a free, zero-VPS solution.

| Requirement | Cloudflare Tunnel |
|---|---|
| Free? | Yes, no bandwidth limits |
| Custom domain? | Yes, any domain you own |
| Auto HTTPS? | Yes, valid certs, zero config |
| Needs a VPS? | No |
| Open source client? | Yes (Apache 2.0) |

**Docker Compose integration (opt-in via profile):**

```yaml
cloudflared:
  image: cloudflare/cloudflared:latest
  command: tunnel run
  environment:
    - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}
  restart: unless-stopped
  profiles:
    - tunnel
  depends_on:
    - backend
```

- Default `docker compose up` does **not** start the tunnel
- To enable: `docker compose --profile tunnel up`
- Configuration: `PUBLIC_URL` env var on backend, `VITE_API_BASE_URL` on frontend
- See `docs/tunnel-setup.md` for full setup guide

---

## 18. Knowledge Management System

### Why this matters

AI agents hallucinate when they lack context. Bodhiorchard solves this with a
four-layer knowledge architecture that keeps all organizational knowledge
current, structured, and accessible to every agent.

### 18.1 Knowledge Architecture (Four Layers)

| Layer | Location | What lives here | Who updates it | Sync frequency |
|-------|----------|----------------|----------------|----------------|
| **L1: Git Repos** | `~/repos/<service>/` on Mac Mini | Source code, per-repo CLAUDE.md, .editorconfig, linter configs | Developers (commits) | Every 15 min (git pull cron) |
| **L2: Mac Mini Filesystem** | `~/.claude/` | Org CLAUDE.md, skills (design guidelines, templates, API standards) | Setup wizard + admins | On change (manual or sync agent) |
| **L3: PostgreSQL (Central)** | `knowledge_items` table + pgvector | PRD knowledge, architecture decisions, coding standards, design tokens | Knowledge Sync Agent + admins via UI | Real-time (on write) |
| **L4: Vector Embeddings** | pgvector HNSW indexes | Semantic search across all knowledge | Embedding service (auto) | On L3 write |

### 18.2 Knowledge Categories

#### A. PRD Knowledge
- Every PRD stored in `prd_documents` table with full content, metadata, status
- Related PRDs linked via vector similarity (pgvector)
- PRD history tracked: status changes, reopen events, retrospectives
- Accessible to AI via MCP tool `get_prd_context(prd_id | search_query)`

#### B. Code Knowledge (Per-Repo)
- Per-repo `CLAUDE.md` files describe: tech stack, architecture, key patterns, testing, gotchas
- Auto-generated during setup, manually enriched by developers
- Stored on Mac Mini filesystem (Layer L1) — Claude Code loads them automatically
- Synced to PostgreSQL `knowledge_items` table for API-mode agents

```python
# Database table for centralized code knowledge
class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"
    id = Column(UUID, primary_key=True, default=uuid4)
    org_id = Column(UUID, ForeignKey("organizations.id"), nullable=False)
    category = Column(String, nullable=False)  # "coding_standard", "design_guideline",
                                                # "architecture_decision", "api_standard",
                                                # "repo_context", "prd_context", "lint_rule"
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)       # Markdown content
    source = Column(String)                      # "manual", "auto_scan", "prd", "git"
    source_ref = Column(String)                  # repo name, PRD ID, file path
    tags = Column(ARRAY(String), default=[])
    embedding = Column(Vector(768))              # Configurable dimensions
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, onupdate=utcnow)
    created_by = Column(UUID, ForeignKey("users.id"))
```

#### C. Org-Wide Coding Standards
- **Where stored**: PostgreSQL `knowledge_items` (category="coding_standard") + Mac Mini skills
- **What includes**:
  - Language-specific style guides (Python: black+ruff, TypeScript: eslint+prettier, Go: gofmt)
  - Approved linters and their configs
  - Naming conventions (snake_case for Python, camelCase for TS, etc.)
  - Error handling patterns
  - Logging standards
  - Git commit message format

```yaml
# Example: knowledge_items row for Python coding standard
category: coding_standard
title: "Python Coding Standards"
content: |
  ## Formatting
  - Formatter: black (line-length=100)
  - Linter: ruff (select=ALL, ignore=D100,D104)
  - Type checker: pyright (strict mode)

  ## Naming
  - snake_case for functions, variables, modules
  - PascalCase for classes
  - UPPER_SNAKE for constants

  ## Patterns
  - Use pydantic BaseModel for all DTOs
  - Use SQLAlchemy 2.0 style (select() not query())
  - Async everywhere (no sync DB calls)

  ## Error Handling
  - Custom exception hierarchy: BodhiorchardError > DomainError > ...
  - Never catch bare Exception
  - Always log with structlog

  ## Testing
  - pytest with pytest-asyncio
  - Factory Boy for fixtures
  - 80% coverage minimum
tags: ["python", "backend", "lint", "formatting"]
source: manual
```

#### D. Design Language / Design System
- **Where stored**: PostgreSQL `knowledge_items` (category="design_guideline") + Mac Mini skill `design-guidelines`
- **What includes**:
  - Brand colors, typography, spacing
  - Component patterns (buttons, forms, cards, modals)
  - Responsive breakpoints
  - Accessibility requirements
  - Animation/transition standards
  - Dark mode tokens

#### E. Architecture Decisions (ADRs)
- **Where stored**: PostgreSQL `knowledge_items` (category="architecture_decision")
- **What includes**:
  - Decision title, context, options considered, chosen option, consequences
  - Linked to affected repos and PRDs
  - Prevents AI from suggesting already-rejected approaches

#### F. API Standards
- **Where stored**: PostgreSQL `knowledge_items` (category="api_standard") + Mac Mini skill `api-standards`
- **What includes**:
  - REST conventions (JSON:API, snake_case, cursor pagination)
  - Auth patterns (JWT RS256, Bearer token)
  - Rate limiting policy
  - Versioning strategy
  - Error response format

### 18.3 Knowledge Sync Agent

A background agent that keeps all four layers in sync.

```python
# backend/app/agents/knowledge_sync_agent.py
class KnowledgeSyncAgent:
    """Runs periodically to keep knowledge layers synchronized."""

    async def sync_repo_knowledge(self):
        """L1 -> L3: Scan repos, extract/update code knowledge in PostgreSQL."""
        for repo in await self.get_registered_repos():
            claude_md_path = repo.local_path / "CLAUDE.md"
            if claude_md_path.exists():
                content = claude_md_path.read_text()
                await self.upsert_knowledge_item(
                    category="repo_context",
                    title=f"Repo: {repo.name}",
                    content=content,
                    source="auto_scan",
                    source_ref=repo.name,
                )

    async def sync_standards_to_mac_mini(self):
        """L3 -> L2: Push coding standards from DB to Mac Mini skills."""
        standards = await self.db.execute(
            select(knowledge_items)
            .where(knowledge_items.c.category.in_([
                "coding_standard", "design_guideline", "api_standard"
            ]))
            .where(knowledge_items.c.is_active == True)
        )
        # Write to Mac Mini skills via SSH/Tailscale
        for item in standards:
            await self.write_skill_file(item.category, item.title, item.content)

    async def embed_knowledge(self):
        """L3 -> L4: Generate embeddings for all knowledge items."""
        unembedded = await self.db.execute(
            select(knowledge_items)
            .where(knowledge_items.c.embedding == None)
        )
        for item in unembedded:
            embedding = await self.embedding_service.embed(
                f"{item.title}\n{item.content}"
            )
            await self.db.execute(
                update(knowledge_items)
                .where(knowledge_items.c.id == item.id)
                .values(embedding=embedding)
            )

    async def detect_stale_knowledge(self):
        """Flag knowledge items that may be outdated."""
        # Compare repo CLAUDE.md last-modified vs knowledge_items.updated_at
        # Alert admins if drift detected
        ...
```

**Sync schedule:**

| Sync | Frequency | Direction |
|------|-----------|-----------|
| Repo git pull | Every 15 min | Remote git -> Mac Mini (L1) |
| CLAUDE.md scan | Every 1 hour | Mac Mini (L1) -> PostgreSQL (L3) |
| Standards push | On change | PostgreSQL (L3) -> Mac Mini skills (L2) |
| Embedding generation | On write | PostgreSQL (L3) -> pgvector (L4) |
| Stale detection | Daily | Compare L1 vs L3 timestamps |

### 18.4 Knowledge API Endpoints

```python
# backend/app/api/knowledge.py

@router.get("/api/knowledge")
async def list_knowledge(category: str = None, search: str = None):
    """List/search knowledge items. Used by UI and agents."""

@router.post("/api/knowledge")
async def create_knowledge(input: KnowledgeItemCreate):
    """Create a knowledge item (coding standard, design guideline, etc.)."""

@router.put("/api/knowledge/{id}")
async def update_knowledge(id: UUID, input: KnowledgeItemUpdate):
    """Update a knowledge item. Triggers re-embedding and Mac Mini sync."""

@router.post("/api/knowledge/search")
async def semantic_search(query: str, categories: list[str] = None, limit: int = 10):
    """Semantic search across all knowledge using pgvector."""

# MCP tool for Claude Code
@router.post("/mcp/tools/get_knowledge")
async def mcp_get_knowledge(query: str, categories: list[str] = None):
    """Claude Code calls this to query org knowledge before generating PRDs."""
```

### 18.5 Knowledge Management UI (Vue 3)

```
Knowledge Base (Admin/PM/Tech Lead view)
├── Coding Standards
│   ├── Python Standards [edit] [active/inactive]
│   ├── TypeScript Standards [edit]
│   └── Go Standards [edit]
├── Design Guidelines
│   ├── Brand & Colors [edit]
│   ├── Component Patterns [edit]
│   └── Accessibility [edit]
├── API Standards
│   ├── REST Conventions [edit]
│   ├── Auth Patterns [edit]
│   └── Error Format [edit]
├── Architecture Decisions
│   ├── ADR-001: Use Agno framework [view]
│   ├── ADR-002: PostgreSQL over MongoDB [view]
│   └── ADR-003: Vue 3 over React [view]
├── Repo Contexts (auto-generated)
│   ├── service-auth [view] [refresh]
│   ├── service-payments [view] [refresh]
│   └── frontend-app [view] [refresh]
└── Sync Status
    ├── Last repo sync: 5 min ago
    ├── Last embedding update: 12 min ago
    └── Stale items: 0
```

### 18.6 How Agents Use Knowledge

| Agent | Knowledge Access | Method |
|-------|-----------------|--------|
| PRD Agent (Claude Code) | Reads CLAUDE.md (L1) + skills (L2) + MCP get_knowledge (L3) | Full context: code + standards + design guidelines |
| Learning Agent (Claude Code) | Reads git history (L1) + CLAUDE.md (L1) + MCP get_prd_context (L3) | Retrospective analysis with full code context |
| Triage Agent (API) | Calls semantic search API (L4) | Finds related PRDs and architecture decisions |
| Support Agent (API) | Calls semantic search API (L4) | Finds related bugs, customer context |
| All agents | Knowledge items embedded in system prompt | Org standards injected via LLM system prompt prefix |

### 18.7 Initial Setup: Knowledge Seeding

Part of the setup wizard (Section 17.4.8):

1. **Register repos** -> auto-generate per-repo CLAUDE.md files
2. **Scan repos** -> detect tech stack, linters, frameworks -> seed `knowledge_items`
3. **Import standards** -> load from bundled templates or paste existing docs
4. **Design system import** -> paste design tokens or link to Figma
5. **Embedding generation** -> embed all seeded knowledge for semantic search

```
Setup Wizard Step: Knowledge Seeding
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[x] Repos registered and cloned (3 repos)
[x] Per-repo CLAUDE.md generated
[ ] Import coding standards?
    > Paste your Python style guide (or skip to use defaults): ___
    > Paste your TypeScript style guide (or skip): ___
[ ] Import design guidelines?
    > Paste your design tokens/guidelines (or skip): ___
[ ] Import API standards?
    > Paste your API conventions (or skip): ___
[ ] Generate embeddings for all knowledge?
    > [Start embedding] (takes ~30 seconds)
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- Database schema with **configurable vector dimensions**
- **`knowledge_items` table** with pgvector embeddings
- **`execution_nodes` table** for node registration and health tracking
- FastAPI skeleton + authentication (JWT)
- **LLM provider abstraction** (LiteLLM integration)
- **Embedding provider abstraction** (Ollama/OpenAI/sentence-transformers)
- Basic CRUD endpoints for PRDs
- **Knowledge API endpoints** (CRUD + semantic search)
- **Node registration API** (`/api/nodes/register`, `/heartbeat`, `/approve`)
- Docker Compose with **Ollama included by default**

### Phase 2: Integrations (Week 3-4)
- GitHub webhook handler + Status Agent
- Slack webhook handler + basic bot
- PRD status updates via GitHub

### Phase 3: Core Agents (Week 5-6)
- Vector DB setup (pgvector, configurable HNSW indexes)
- Embedding service (multi-provider)
- Triage Agent + PRD Agent (with model tier support)
- **Local agent execution** (Claude Code CLI subprocess OR direct API — configurable at setup)
- **MCP server** for Claude Code writeback (write_prd, update_status, post_slack)
- **Setup wizard** (org token, node registration + approval, repo cloning, knowledge seeding)
- **Knowledge Sync Agent** (L1↔L3 sync, stale detection)
- **Slack slash commands** for agent triggers (`/bodhiorchard-prd`, `/bodhiorchard-triage`)

### Phase 4: Advanced Agents (Week 7-8)
- Learning, Skill, Standup, Bug Linker, Reassignment agents
- Design Agent, Tech Plan Agent, Test Plan Agent (codebase-aware)
- Support Agent with customer profiling
- Inter-agent communication patterns

### Phase 5: Frontend & Polish (Week 9-10)
- Vue 3 dashboard (all 9 roles served)
- Real-time updates (WebSocket)
- Monitoring & observability
- Performance optimization

### Phase 6: VSCode Extension (Week 11-14, post-launch)
- Developer-only companion extension
- Sidebar TreeView, Status Bar, Command Palette
- Deep links back to web app
- Same FastAPI REST API, no backend changes

---

## Feature Summary

Total: 17 features, 11 agents

| # | Feature | Agent |
|---|---------|-------|
| F1 | Slack Feature Intake & AI Triage | Triage Agent #1 |
| F2 | PRD-as-Code Repository | PRD Agent #2 |
| F3 | Enterprise Rules Living Knowledge Base | Status Agent #3 |
| F4 | Auto-Status Updates on PR Merge | Status Agent #3 |
| F5 | AI-Generated Daily Standups | Standup Agent #4 |
| F6 | Feature Release Learnings | Learning Agent #5 |
| F7 | Bug-to-PRD Linking | Bug Linker Agent #6 |
| F8 | Bug Threshold Auto-Reassignment | Reassignment Agent #7 |
| F9 | Skill Tracking & Smart Assignment | Skill Agent #8 |
| F10 | Multi-Org Support | All agents |
| F11 | Capacity Planning & Dev Workload | Skill Agent #8 + Dashboard |
| F12 | Vector DB Knowledge Layer | All agents |
| F13 | Support Ticket Integration | Support Agent #9 |
| F14 | Customer Profiling & Revenue Prioritization | Support Agent #9 |
| F15 | PRD Reopening Lifecycle | Support Agent #9 + Reassignment #7 + Skill #8 |
| F16 | UI/UX Design Scope & Component Breakdown | Design Agent #10 |
| F17 | Automated Test Plan Generation | Test Plan Agent #11 |

---

## 18. Repository Scan Pipeline

### 18.1 Overview

A **full repository scan** is the operation behind `POST /api/v1/skills/scan`. It is a **sequential, non-resumable waterfall of 11 phases** that analyzes every active `TrackedRepository` in an org, synthesizes features via a Claude subprocess backed by MCP, and persists results into `knowledge_items` + `skill_profiles`. End-to-end latency is typically 5–30 minutes depending on repo count and cluster volume.

The pipeline has two stripes:

```
Per-repo (run once per repo, sequential within a repo)
    A   Scan Mode Detection       (incremental vs full)
    B   GitNexus Indexing         (code clusters extracted)
    B1  Repo Setup                (worktrees, hooks, CLAUDE.md, setup PR)
    D   Stale Cleanup             (incremental only)
    E   Git Skill Analysis        (directory-level skill profiles)
    E1b Design System Extraction  (async job if UI platform detected)

Global (run once after all repos finish their per-repo stripe)
    B2  Feature Synthesis         (Claude subprocess + MCP, parallel per repo)
    E2  Skill Remap               (conditional: re-run E using feature modules)
    B3  Cross-Repo Merge          (workspace mode, ≥2 features)
    F   Embedding Backfill        (embed items missing embeddings)
    G   Persist                   (write head_sha, counts, org config — last step)
```

Scan state is tracked in **Redis** (progress) plus the **`tracked_repositories` table** (final, commit-only). There is **no per-phase checkpoint anywhere**, which is why any mid-scan failure forces the entire pipeline to restart from Phase A on the next run.

### 18.2 Entry Point & Trigger

| Aspect | Detail |
|--------|--------|
| Trigger | `POST /api/v1/skills/scan` — `backend/app/api/v1/skills.py:37-124`, function `trigger_scan()` |
| Body | `{ "fullRescan": bool }` |
| Response | `{ "scanId": "<uuid>", "status": "started" }` (fire-and-forget via `BackgroundTasks`) |
| Preconditions | Embedding service healthy; every active repo has `main_branch` + `develop_branch`; all repo paths exist on disk with `.git` |
| Status poll | `GET /api/v1/skills/scan/{scan_id}/status` — `skills.py:127-154` (resolves via `resolve_scan_progress()`) |
| Cancel | `POST /api/v1/skills/scan/{scan_id}/cancel` — `skills.py:157+` |
| Background dispatch | `run_scan_pipeline()` in `backend/app/services/scan_pipeline.py:356-841` |
| Auth | Requires `org:edit_settings` permission |

### 18.3 The 11 Phases

| # | Phase | Scope | Source | What happens | Persisted to | Resumable on rerun? |
|---|-------|-------|--------|--------------|--------------|---------------------|
| A | Scan Mode Detection | per-repo | `scan_pipeline.py:478-508` | Compare `head_sha` with current HEAD. If <30% of files changed → `incremental`; else `full`. Forces `full` if no scan-sourced features exist. | in-memory flag only | ❌ |
| B | GitNexus Indexing | per-repo | `scan_pipeline.py:510-542` | Run `gitnexus analyze`; collect code clusters + repo_overview. | GitNexus index (on-disk, outside app DB) | ⚠️ index survives but orchestrator ignores it |
| B1 | Repo Setup | per-repo | `scan_pipeline.py:544-560` | Install worktrees, hooks, `.gitignore`, CLAUDE.md; commit + push + open setup PR if branch pushed. | Git remote (setup PR) | ⚠️ |
| D | Stale Cleanup (incremental only) | per-repo | `scan_pipeline.py:620-632` | Delete `knowledge_items` whose `code_locations` reference deleted files. | `knowledge_items`, `knowledge_to_repo` | ✅ DB-backed |
| E | Git Skill Analysis | per-repo | `scan_pipeline.py:634-658` → `git_analyzer.py:analyze_repo_skills()` | Walk git log → compute per-author-per-module touch counts, language stats, recency score → upsert `SkillProfile`. Optional auto-create `User` rows (gated by `scan.auto_create_members`). | `skill_profiles` | ✅ DB-backed |
| E1b | Design System Extraction | per-repo | `scan_pipeline.py:660-681` | Detect UI platform (Flutter, iOS, Tauri…), hash source files, enqueue async design-extraction job if hash changed. | `job_queue` (async) | ✅ async, independent |
| B2 | Feature Synthesis | **global, parallel per repo** | `scan_phases.py:314-470`, dispatched from `scan_pipeline.py:696-707` | For each repo, start one Claude subprocess. Prompt = `build_synthesis_prompt()` for clustered repos or `build_direct_scan_prompt()` if no clusters. Claude calls MCP `get_pending_features` → `write_feature_registry` in a loop. | `knowledge_items` (category=`feature_registry`) | ⚠️ PARTIAL — features already written survive, un-synthesized clusters are lost with the process |
| E2 | Skill Remap | global (gated) | `scan_pipeline.py:726-738` | Only runs if **new feature count ≥ 70% of previous feature count**. Wipes existing profiles and re-runs skill analysis using feature names (not directory paths) as the `module` dimension. | `skill_profiles` (destructive replace) | ⚠️ destructive |
| B3 | Cross-Repo Merge | global (workspace mode only, ≥2 features) | `scan_phases.py:670-800` | Second Claude subprocess with `merge_features` MCP. Embed any items missing embeddings. `dedup_merged_features()` handles concurrent-MCP-retry fallout. Auto-link orphaned features. | `knowledge_items` (`is_active` flips), `knowledge_to_repo` | ⚠️ |
| F | Embedding Backfill | global | called from inside B3 path | Embed any `knowledge_item` still missing a vector. | `knowledge_items.embedding` | ✅ DB-backed |
| G | Persist | global, **last** | `scan_pipeline.py:748-841` | Update `tracked_repositories.head_sha`, `knowledge_count`, `feature_count`. Write `org.config.knowledge.repo_shas` + `last_scan`. | `tracked_repositories`, `organizations.config` | ✅ final commit |

### 18.4 The Single Backing "Scan State" Table

The only row-level persisted answer to *"where did the last scan get to?"* lives in **`tracked_repositories`** (`backend/app/models/tracked_repository.py:33-81`).

Scan-relevant columns:

| Column | Role |
|--------|------|
| `head_sha` | SHA of the last **successfully completed** scan. **Written only in Phase G.** |
| `last_scanned_at` | Timestamp, also written only in Phase G. |
| `knowledge_count`, `feature_count` | Denormalized counters, written in Phase G. |
| `status` | `ACTIVE` / `IGNORED` / `REMOVED` — lifecycle, not scan state. |
| `main_branch`, `develop_branch`, `uat_branch` | Branch mapping (Phase 0 gate). |
| `github_repo_full_name` | Auto-populated during B1. |

**There is no column, and no separate table, that records per-phase completion.** A scan that dies anywhere between Phase A and Phase G leaves `head_sha` untouched, which is precisely why the orchestrator has no choice but to re-run every phase from A on the next attempt.

Actual scan results live in two supporting stores — **`knowledge_items`** (+ `knowledge_to_repo` junction, for `code_locations`) and **`skill_profiles`** — which **do** survive partial failures. The orchestrator simply has no signal of the form "Phase E already finished for repo X", so it redoes those phases anyway. That wasted work is the core pain point motivating future splitting.

### 18.5 Progress & Error Tracking (Redis)

| Aspect | Detail |
|--------|--------|
| Module | `backend/app/services/scan_progress.py` |
| Store | Redis hash `scan:{scan_id}` (TTL 2h); in-memory fallback when Redis down |
| Active-scan pointer | `scan_active:{org_id}` → current `scan_id` |
| Monotonicity | `progress_pct` is `max(existing, new)` and clamped to `[0, 100]` |
| Stale detection | No update for 2h → auto-fail (matches Redis TTL) |
| Event bus | Every update publishes to topic `scan:{scan_id}` → frontend `useScanSocket` |

Tracked fields (see `schemas/skills.py:62-86`): `status`, `scan_mode`, `progress_pct`, `features_indexed`, `features_skipped`, `profiles_found`, `stale_cleaned`, `unmatched_authors`, `synthesis_warning`, `setup_pr_message`, `repo_warnings[]`, `error`.

**Granularity ceiling.** `repo_warnings` is per-repo-per-phase:

```json
{"repo": "bodhiorchard", "phase": "synthesis", "summary": "...", "hint": "..."}
```

Everything that happens *inside* Phase B2 — individual cluster failures, individual MCP call errors, Claude turn exhaustion — collapses into a single `synthesis_warning` string plus the `features_skipped` counter. There is no per-cluster, per-MCP-call, or per-turn record. This is the reason the user-visible failure log `claude_run_failed, returncode: 1` carries essentially no actionable signal.

### 18.6 Claude Subprocess & MCP Tools

**Runner.** `backend/app/services/claude_runner.py:88-320`.

Command shape (`claude_runner.py:375-432`):

```
claude -p <prompt> \
    --output-format stream-json \
    --dangerously-skip-permissions \
    --settings '{"outputStyle":"default"}' \
    --verbose \
    --max-turns <N> \
    --mcp-config <tmpfile>
```

Notes:
- `--settings '{"outputStyle":"default"}'` is **mandatory** — without it, learning/explanatory output styles leak `★ Insight` blocks into skill output and corrupt the stream-JSON parser.
- Output is consumed line-by-line looking for `{"type":"result", ...}` as the terminal event. `is_error: true` on any event surfaces as `claude_run_failed` in the log.
- Default `--max-turns` is 40; default `timeout_seconds` is 300 for B2 and longer for B3 (both override-able via `org.config.scan.max_turns` / `.timeout_seconds`).
- Stderr is drained concurrently in a separate task to prevent the OS pipe buffer from filling and deadlocking the subprocess.

**MCP handlers invoked from inside the subprocess:**

| Tool | Handler | Behavior |
|------|---------|----------|
| `get_pending_features` | `handlers_knowledge.py:145` | Returns next ≤10 queued clusters from in-memory queue in `mcp/synthesis_queue.py`. Queue keyed by `org_id` or `org_id:repo_name` (parallel-per-repo). |
| `write_feature_registry` | `handlers_knowledge.py:164` | Upserts `KnowledgeItem` (category=`feature_registry`, source=`scan`) + links via `KnowledgeRepoLink`. **If `repo_name` cannot be resolved to a `TrackedRepository`, insertion continues with `repo_id=None`** — the feature is persisted but orphaned. This is the "fails to fetch skill properly lib" symptom: the DB write succeeds but the repo-link side is silently dropped, and downstream readers (merge, UI) treat the feature as unlinked. |
| `merge_features` | `handlers_knowledge.py` (referenced in B3) | Deactivates duplicate titles and consolidates `code_locations` across repos. |

### 18.7 Soft-Delete Rollback Pattern

`scan_pipeline.py:~421-431` soft-deletes (`is_active = false`) every existing scan-sourced `KnowledgeItem` for the org **at the start of Phase B2**, tracking their IDs in `soft_deleted_ids`. Phase B2 then re-creates / reactivates each feature as MCP `write_feature_registry` calls land.

The implication: **if the scan dies before Phase G**, the org is left with its entire scan-sourced feature set soft-deleted. This is why an aborted scan can make features *temporarily vanish* from the UI even though no data was actually destroyed — they will reappear the next time a scan succeeds. There is currently no catch-block that reactivates `soft_deleted_ids` on failure.

### 18.8 Frontend Wiring

| Aspect | Detail |
|--------|--------|
| Trigger UI | `frontend/src/components/SetupChecklist.vue:~138-166` — "Scan Repository" button |
| Composable | `frontend/src/composables/useScanSocket.ts:39-65` — wraps `useRealtimeTracker` with `topicPrefix: "scan"` |
| Transport | WebSocket on `scan:{scan_id}` topic, with 2000 ms HTTP polling alongside (`pollAlongsideWs: true`) to catch missed events |
| Terminal signals | `status === "completed"` or `"failed"` — stops the poller |
| Client-side timeout | **None** (by design — scans can legitimately exceed an hour) |
| Status labels | `STATUS_LABELS` map in the composable (e.g. `"synthesizing_features"` → "Synthesizing features") |
| Warning rendering | `SetupChecklist.vue:~74-95` — lists each `repoWarning` with phase + summary + hint |

### 18.9 Known Failure Modes (observed)

Concrete symptoms driving this documentation pass:

- **`error_max_turns` from the synthesis subprocess** — e.g. `num_turns: 41, max_turns: 40`. The orchestrator records only a generic `synthesis_warning`; there is no record of how far through the cluster queue Claude got, so every un-synthesized cluster is lost with the process.
- **MCP `write_feature_registry` with unresolvable `repo_name`** — feature persisted without `repo_id`, orphaned from its repo. Downstream merge and UI display logic then treats it as unlinked ("fails to fetch skill properly lib").
- **B3 merge concurrency** — under concurrent MCP retries, `merge_features` calls can collide; `dedup_merged_features()` cleans most of it up but mis-merges are still possible.
- **Phase B1 setup-PR push failure** — captured as `setup_pr_message` and surfaced to the UI but **does not abort the scan**. A repo can complete a scan without its CLAUDE.md / hooks being present on the remote.
- **Soft-delete visibility gap** — any mid-scan failure between Phase B2 start and Phase G success leaves scan-sourced features soft-deleted until the next successful scan.

### 18.10 Why It Is Not Resumable Today

Three concrete blockers, any one of which alone would force a full restart:

1. **No per-phase checkpoint column.** The only durable "where did we get to" signal is `tracked_repositories.head_sha`, and that is written last (Phase G). Earlier phases produce real DB state in `knowledge_items` and `skill_profiles`, but there is no index telling the orchestrator which `(repo_id, phase)` pairs already succeeded.
2. **In-memory synthesis queue.** `mcp/synthesis_queue.py` holds the per-repo cluster list in a Python module-level dict (`_synthesis_queue`). If the backend process dies, the queue dies with it — there is no recovery path that knows which clusters still need synthesis.
3. **Single `scan_id`, overwriting progress record.** The Redis `scan:{scan_id}` hash is overwritten on each update, not appended to. By the time Phase B2 is running, the progress record no longer contains Phase A/B/E success signals — so even a hypothetical "resume from last known good phase" check has nothing to read.

Addressing any of these without addressing the other two still leaves the pipeline effectively all-or-nothing. The follow-up design work (not in scope for this section) needs to pick a minimum-viable checkpoint granularity — most likely `(repo_id, phase)` — and durably persist both the completion signal and the synthesis-queue position.

### 18.11 Key File Map

| Layer | File | Key symbol(s) |
|-------|------|---------------|
| API trigger | `backend/app/api/v1/skills.py:37-154` | `trigger_scan`, `get_scan_status` |
| Orchestrator | `backend/app/services/scan_pipeline.py:356-841` | `run_scan_pipeline`, `build_synthesis_prompt`, `build_direct_scan_prompt` |
| Phase implementations | `backend/app/services/scan_phases.py:314-800` | `phase_b2_synthesis`, `phase_b3_merge` |
| Claude runner | `backend/app/services/claude_runner.py:88-432` | `run_claude_code`, `_run_with_streaming` |
| Progress tracking | `backend/app/services/scan_progress.py` | `create_scan_progress`, `update_scan_progress`, `resolve_scan_progress` |
| MCP knowledge handlers | `backend/app/mcp/handlers_knowledge.py:145+` | `handle_get_pending_features`, `handle_write_feature_registry` |
| MCP synthesis queue | `backend/app/mcp/synthesis_queue.py` | `set_synthesis_queue`, `get_queue_remaining`, `remove_from_queue` |
| Skill extraction | `backend/app/services/git_analyzer.py` | `analyze_repo_skills` |
| Results model | `backend/app/models/knowledge_item.py:42-80` | `KnowledgeItem`, `KnowledgeRepoLink` |
| Skill model | `backend/app/models/skill_profile.py:24-54` | `SkillProfile` |
| Scan-state model | `backend/app/models/tracked_repository.py:33-81` | `TrackedRepository` |
| Progress schema | `backend/app/schemas/skills.py:11-86` | `ScanRequest`, `ScanResponse`, `ScanStatus`, `RepoScanWarning` |
| Frontend composable | `frontend/src/composables/useScanSocket.ts:39-65` | `useScanSocket` |
| Frontend trigger | `frontend/src/components/SetupChecklist.vue` | Scan checklist item |

### 18.12 How Skills Are Computed

Developer "skills" aren't inferred from anywhere fancy — they're a direct function of the git log. Two passes run during a scan:

**Pass 1 — `SKILL_EXTRACTION` (per-repo, directory-based).** Source: `backend/app/services/git_analyzer.py:115-219`. Steps:

1. Enumerate commits via `git log --format=%H|%ae|%an|%aI --no-merges --since=6.months.ago` (window is `DEFAULT_SINCE` at `git_analyzer.py:22`). Merge commits excluded so reviewers don't inherit author credit.
2. For each commit, pull the changed file list (`git show --name-only`).
3. Map every file to a **module**. Default: the top-level directory (`backend/…` → `backend`). Paths under `_SKIP_SKILL_PATHS` (`.claude`, `.githooks`, `.bodhiorchard`, `.gitnexus`, `.github`, `.vscode`, `.idea`) are dropped as tooling, not code.
4. Accumulate per `(email, module)` a `ModuleStats`: `touch_count`, `languages` (derived from extension via `LANG_MAP`), `last_touch`.
5. Compute `skill_score = min(1.0, touch_count / 50.0) * recency_weight`. The `/ 50.0` saturates at 50 touches so an outlier 500-touch author doesn't pin the curve; `recency_weight` exponentially decays from `last_touch` to "now".
6. Upsert into `skill_profiles` keyed on `(user_id, org_id, module)`. Authors whose email doesn't resolve to a `User` surface as `unmatched_authors` in the `ScanStatus` payload; the scan is never blocked by them.

**Pass 2 — `SKILL_REMAP` (global, feature-based).** Source: `backend/app/services/scan_phases.py::phase_e2_skill_remap` and the `upsert_skill_profiles` helper at `scan_helpers.py:55-108`. Runs only when synthesis produced enough features — gated by `new_count >= 0.7 * old_count` (constant `_E2_SPARSE_THRESHOLD`). When it fires:

1. Build a `feature_map` from `knowledge_to_repo.code_locations`: one entry per feature with its path prefixes (longest-prefix-wins).
2. Re-run `analyze_repo_skills` per repo with that map — files matching a feature prefix land under the feature name instead of the directory.
3. In a single DB **SAVEPOINT** (`async with db.begin_nested()`): DELETE all scan-sourced rows, then INSERT the feature-keyed profiles. A crash between delete and insert rolls the savepoint back, leaving the old rows intact — the "empty skills table until next scan" window is closed.

When the 70% gate doesn't fire (sparse feature map), E2 does a partial upsert without wiping — a tiny feature set never nukes established directory profiles.

### 18.13 Resumability

Shipped in P1–P13 of the "Scan Repo Waterfall — Resumable Pipeline Design" plan at `.claude/plans/scan-repo-for-big-elegant-waterfall.md`. This subsection summarises what landed.

**Two new tables + typed enum.** `backend/app/models/scan_phase.py` defines the `ScanPhase`, `PhaseScope`, `CheckpointStatus`, `MergeOutcome`, and `ScanErrorCode` StrEnums (legacy A..G codes preserved in comments for grep). The 11 phases:

| Enum value | Was | Scope |
|------------|-----|-------|
| `mode_detection` | A | per-repo |
| `gitnexus_index` | B | per-repo |
| `repo_setup` | B1 | per-repo |
| `stale_cleanup` | D | per-repo (incremental only) |
| `skill_extraction` | E | per-repo |
| `design_system_extract` | E1b | per-repo |
| `feature_synthesis` | B2 | per-repo (runs under the global stripe, parallel per repo) |
| `skill_remap` | E2 | global |
| `feature_merge` | B3 | global |
| `embedding_backfill` | F | global |
| `persist_results` | G | global |

`SHA_REUSABLE_PHASES = {GITNEXUS_INDEX, SKILL_EXTRACTION, DESIGN_SYSTEM_EXTRACT}` — these three phases copy their payload from an earlier DONE row when the repo HEAD SHA matches, so a full-rescan of an unchanged repo costs nothing beyond the lookup.

**`scan_phase_checkpoints`** (migration `zn_scan_phase_checkpoints.py`). One row per `(scan_id, repo_id, phase, attempt)`. Stores lifecycle (`pending` / `running` / `done` / `failed` / `skipped`), `sha_at_run`, `error_code`, `error_message`, JSONB `payload`, and `parent_scan_id` for resume lineage. Indexed on `(scan_id, phase)`, `(org_id, phase, sha_at_run)` for cross-scan reuse lookups, and `(org_id, status)` for admin listings.

**`synthesized_features`** (migration `zo_synthesized_features.py`). Immutable, append-only record written by the MCP `write_feature_registry` handler during `FEATURE_SYNTHESIS`. `repo_id` is NOT NULL — unresolvable `repo_name` now hard-fails in the MCP handler instead of silently creating an orphan. `merge_outcome` is an enum (`canonical` / `merged_into` / `unvisited`) with a self-FK `merged_into_id` pointing at the surviving canonical row. Superseded rows get `superseded_at` set but are never hard-deleted — the partial index `ix_synth_feat_latest WHERE superseded_at IS NULL` keeps "current view" queries fast.

**Checkpoint wrapper.** `backend/app/services/scan_checkpoints.py::run_checkpointed_phase` handles all three axes of skip logic in one place:

1. Within-scan skip — if the current scan already has a DONE / SKIPPED checkpoint for this phase, return its payload.
2. Cross-scan SHA reuse — for phases in `SHA_REUSABLE_PHASES` with a matching `sha_at_run` row in any prior scan, copy the payload and stamp a new DONE row with `started_at == finished_at` (the "cached" signal the frontend renders).
3. Run + classify — otherwise execute the phase body, classify any exception via `classify_scan_error`, stamp the checkpoint accordingly, and re-raise.

The typed `ScanPhaseError` hierarchy (`MaxTurnsError`, `ClaudeSubprocessError`, `MCPError`, `PhaseTimeoutError`, `OrphanFeaturesError`, `MergeIncompleteError`) lets the scan body raise a specific failure mode and have the UI render an actionable hint without string-matching.

**Per-repo stripe.** `backend/app/services/scan_repo_loop.py::process_one_repo` replaces the inline per-repo loop body that used to live in `run_scan_pipeline`. Each of the six per-repo phases runs through a local `_ckpt(phase, phase_fn)` wrapper that forwards to `run_checkpointed_phase` with the captured SHA. Sibling modules `scan_design_system.py` and `scan_synthesis_queue.py` hold two helpers (`maybe_extract_design_system`, `build_pending_synthesis`) extracted to keep the loop module under 400 lines.

**B2 self-heal + audit.** `phase_b2_synthesis` now queries `synthesized_features.cluster_names_for_repo` before launching the Claude subprocess and rewrites the in-memory queue to the pending subset — resume always picks up exactly where the previous attempt left off, without any durable queue. After the subprocess exits successfully, `KnowledgeItemScanRepository.find_items_missing_repo_link` runs as a belt-and-braces audit; auto-repair inserts missing links, and anything unfixable surfaces as `OrphanFeaturesError` → `error_code='orphan_feature'` on the checkpoint.

**B3 post-merge audit.** `phase_b3_merge` ends with `SynthesizedFeatureRepository.mark_unvisited_for_scan(scan_id)`. Any synth row still NULL has not been mentioned by the merge subprocess — it's flagged `unvisited` and the phase raises `MergeIncompleteError`. The retry endpoint can then re-run merge with only the unvisited subset as input.

**Durable checkpoint sessions.** Every checkpoint write — RUNNING insert, DONE finalize, FAILED finalize, SHA-reuse copy-forward — runs inside a dedicated `_checkpoint_tx(org_id)` async context (`scan_checkpoints.py`) that opens its own `AsyncSessionLocal()`, commits on clean exit, rolls back and re-raises on exception. The pipeline's outer `db` session is *never* used for checkpoint I/O. This decouples the WAL of phase transitions from the phase body's transaction: when a phase raises and the pipeline session rolls back its work, the FAILED checkpoint is already committed independently and stays durable. Repository writers (`start`, `finalize_by_id`, `insert_reused`) return primitive types (`uuid.UUID` / `None`) rather than ORM rows, so callers can't accidentally hold a detached instance after the helper closes its session. `run_checkpointed_phase` carries the checkpoint id between the start and the finalize as a UUID — the FAILED `UPDATE` then targets a primary key in a fresh session, no identity-map dependency. Cancellation (`asyncio.CancelledError`) is the one exception path that intentionally leaves the row in RUNNING — `reconcile_orphan_scans` flips it to FAILED on next boot.

**Soft-delete scope.** `run_scan_pipeline` now computes `changed_repos` upfront by comparing each active repo's `git rev-parse HEAD` against `tracked_repositories.head_sha`. Only those repos' feature rows are soft-deleted at scan start (via `KnowledgeItemScanRepository.soft_delete_by_repo_ids`). Unchanged repos keep their rows live for the whole scan — the "features temporarily vanish during a full rescan of a mostly-unchanged workspace" UX gap is closed.

**HTTP surface.** Under `/api/v1/skills`:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/scan` | Unchanged. Fresh scan. |
| `POST` | `/scan/{scan_id}/resume` | Mint a child scan that inherits parent's DONE / SKIPPED checkpoints; re-run the rest. |
| `POST` | `/scan/{scan_id}/phases/{phase}/retry?repo_id=…` | Same as resume, but the child scan omits the specified phase (optionally one repo) so it runs fresh. |
| `GET`  | `/scan/{scan_id}/checkpoints` | Full checkpoint list powering the frontend timeline. |
| `POST` | `/scan/recover/feature/{synth_feature_id}` | Bad-merge recovery — re-insert a feature from its immutable pre-merge synth row into `knowledge_items` + `knowledge_to_repo`. |
| `GET`  | `/scan/{scan_id}/status` | Now enriched with `phases[]` and `parentScanId` via `enrich_status_with_phases`. |

All require `org:edit_settings`, matching `trigger_scan`.

**WebSocket delivery.** Stays on the existing `scan:{scan_id}` topic — no sub-topic, no wildcard subscription (`event_bus` doesn't support them). `_publish` in `scan_progress.py` routes through `publish_scan_status` which hashes the payload and silently drops no-op republishes. Non-UUID `scan_id` sentinels used in older tests fall through to the raw publish path unchanged.

**Frontend wiring.** `frontend/src/composables/useScanSocket.ts` `ScanStatusData` grew `phases: PhaseStatus[]` and `parentScanId`. A new `frontend/src/stores/scan.ts` Pinia store centralises scan state and exposes `resume()` / `retryPhase()` actions. `frontend/src/components/scan/ScanPhaseTimeline.vue` renders the per-phase timeline with per-row retry buttons. `SetupChecklist.vue` swaps in the timeline when `phases.length > 0` and falls back to the legacy progress bar when it's empty (pre-migration scans).

---

**This document is implementation-ready and provides all technical details needed for a senior engineer to build Bodhiorchard from scratch.**
