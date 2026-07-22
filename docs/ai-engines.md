# AI Engines & MCP Server

Bodhiorchard is **AI-engine-agnostic**. An organisation picks its provider in **Settings → AI Config** (or during setup), and every agent run routes through it. Today: Claude Code, GitHub Copilot, OpenAI Codex, and Ollama.

The first three drive a CLI. Ollama does not — it talks HTTP to an Ollama server, on your own machine or a shared one, for deployments where those CLIs cannot be installed. That difference is not cosmetic: **a provider without a CLI has no file access**, so it cannot run every feature. See [Ollama](#today--ollama-fully-local-no-cli) below before choosing it.

## Today — Claude Code (codebase-aware agents)

Codebase-aware agent runs (BUD spec, Tech Plan, Implementation, Code Review) are executed by the [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI, which gives agents file access, shell tool-use, and direct access to Bodhiorchard's MCP server.

**Why Claude Code (and not just the raw API):**

- **Codebase awareness out of the box** — Claude Code already knows how to read files, run shell commands, and edit code; Bodhiorchard reuses that surface area instead of re-implementing it.
- **Token-efficient by default** — agent prompts use Anthropic prompt caching, structured tool-use, and incremental context loading. The cost per BUD stays low even on long sessions.
- **One runtime, two billing models** — point Bodhiorchard at an Anthropic API key (pay-per-token) **or** at a host `claude login` session backed by a Claude Pro / Max subscription (flat-rate). Same agents either way.

### Authentication modes

Each provider declares the modes it supports, so the Settings page can only offer one the chosen provider accepts.

| Mode | When the org uses this | Where the credential lives |
|---|---|---|
| `api_key` | Full Docker deployments, or any host without a Claude subscription. Also used by Copilot (a GitHub token) and Codex (an OpenAI key) | Encrypted in Postgres (Fernet AES-128) and pushed into the backend's process env on save |
| `subscription` | A Claude Pro / Max plan, via an OAuth token from `claude setup-token` | Encrypted in Postgres, same as `api_key` |
| `host` | Hybrid deployments where the developer already runs `claude` interactively. For Ollama it means *no authentication* — nothing is sent | The host's existing login session — nothing stored in the database |

The backend auto-detects the deployment (via `/.dockerenv`) and the Settings page only surfaces options that work there — except where a provider has nothing else to offer, since a provider needing no credential still has to be selectable in Docker.

## Today — Anthropic direct API (lightweight non-codebase agents)

Triage, Bug-Linker, and Standup don't need to read files — they reason over chat messages, bug reports, and aggregated activity. For those, Bodhiorchard skips Claude Code and calls the Anthropic API directly. Lower latency, lower per-call cost, same `sk-ant-…` key (configured at **Settings → AI Configuration → Anthropic API**).

## Today — Ollama (no CLI)

For machines where an agent CLI cannot be installed, or where code must not leave the network. Bodhiorchard speaks Ollama's HTTP API directly and executes MCP tools in-process, so there is no CLI and no subprocess.

**Setup:** install [Ollama](https://ollama.com), then `ollama pull qwen3`. Choose *Ollama* in **Settings → AI Config**, set the server address if it isn't on this machine, and pick a model.

### Local or hosted

The server address accepts any `http`/`https` URL, so one shared or hosted Ollama can serve the whole organisation instead of every machine running its own model.

- **Path prefix** — if the endpoint serves Ollama under a prefix (`https://gw.example.com/ollama`), include it. Bodhiorchard appends Ollama's own paths (`/api/chat`, `/api/tags`) to whatever you save.
- **Authentication** — a local server needs none; pick *No authentication*. For a hosted endpoint behind a gateway, pick *Bearer token* and paste the credential. It is stored encrypted and sent as `Authorization: Bearer …`.
- **It must speak Ollama's own API.** An OpenAI-compatible endpoint (`/v1/chat/completions`) is a different protocol and will not work — a 404 on `/api/chat` is the symptom.
- Link-local addresses (the `169.254.0.0/16` cloud-metadata range) are refused.

Before deploying to a restricted machine, run the readiness check on it — it verifies the two things this integration depends on, and reports the latency you should expect:

```bash
python3 backend/scripts/check_ollama_ready.py
```

**Only models advertising the `tools` capability can run agents.** One without it answers in prose instead of calling a tool, so the model list only offers models that qualify — `ollama pull qwen3` if none appear.

### What Ollama cannot do

Ollama has MCP tools but **no access to your repository files**, so these features stay unavailable and fail with a clear error rather than a plausible-looking empty result:

- BUD stage agents (spec, tech plan, test plan)
- Design generation
- Repository scanning and feature synthesis
- Design-system extraction

Everything that reasons over text rather than files works: Slack triage and PRD drafting, feature Q&A, estimation, SP attribution, smart assignment, and quiz generation.

### Speed

Self-hosted inference is far slower than a frontier hosted API, and slower still without a GPU. Latency tracks how much the model *writes*: a tool call emits a handful of tokens and stays fast, while a long prose answer dominates. **Reasoning** ("thinking") roughly doubles response time — it is off by default and switchable in Settings.

### Docker

In Full Docker, `localhost` is the container, not your machine. Point the server address at `http://host.docker.internal:11434` to reach an Ollama running on the host; the backend service already declares the `extra_hosts` entry that makes this resolve on Linux. A hosted endpoint needs none of this — the container reaches it like any other URL.

## Coming soon

| Engine | Status |
|---|---|
| **OpenAI** API (GPT-4o / 4 / 3.5) | Planned |

New providers are one entry in the backend capability table (`app/services/ai_runner/capabilities.py`) plus an adapter — the table declares what a provider can do, and the UI and the run seam both read it, so a provider is never offered a setting or a feature it cannot handle.

## MCP server — the tools Bodhiorchard exposes to Claude Code

Bodhiorchard runs an MCP server on `:8001` (HTTP) with a `stdio` bridge for desktop clients. The tools split into six groups. Every call is JWT-scoped to the calling user's organisation, audited, and rate-limited.

### BUD lifecycle (write path)

How agents and the UI create and advance BUDs:

| Tool | Purpose | Typical caller |
|---|---|---|
| `create_bud` | Create a new BUD from a chat request, intake interview, or external trigger. Returns the BUD id + slug used by every later call. | Triage Agent (Slack/Teams intake), UI "New BUD" button, external MCP clients drafting their own spec |
| `update_bud` | Patch any field on an existing BUD — status transitions, assignee changes, priority bumps, spec edits. | BUD Agent (spec generation), Status Agent (PR-merge → status), human reviewers |
| `write_bud` | Replace a full BUD markdown section (spec / tech spec / test plan / acceptance criteria). | BUD Agent, Tech Plan Agent, Test Plan Agent — each owns a section |
| `get_bud_by_id` | Fetch a single BUD by id with all sections + full history. | Anywhere a deep-link lands an agent on a specific BUD |
| `get_bud_context` | Retrieve nearby / related BUDs for codebase-aware drafting (vector search + same-repo siblings). | BUD Agent during draft, agents avoiding duplicate work |
| `write_bud_design` | Save Design Agent output — wireframes, design notes, Figma links. | Design Agent, Designer reviewing/editing |
| `get_bud_designs` | List the design artefacts already attached to a BUD. | Design Agent (avoid re-generating), Tech Plan Agent (read design intent) |
| `get_bud_plan` | Fetch the implementation plan + file-level TODOs for a BUD. | Implementation runs, Smart Assignment Agent, developers via `claude` |
| `takeover_todo` / `complete_todo` | Claim a specific TODO item and mark it done. Enables a developer (or AI) to atomically pick up granular work. | Implementation Agent, IDE-side coding assistants pairing with Bodhiorchard |

### Feature registry (post-deploy)

What shipped, deduplicated, knowledge-base searchable:

| Tool | Purpose |
|---|---|
| `get_features` | List shipped features across the org with filters (repo, area, owner, recency). |
| `get_pending_features` | Next batch of code-cluster candidates waiting for synthesis into Features. |
| `write_synthesis_feature` | Save a feature description synthesised from a code-cluster. |
| `write_feature_registry` | Promote a BUD to a permanent Feature on deploy. |
| `check_feature_exists` | Dedup check before creating — vector + name lookup. |
| `search_bugs` | Find related bugs for a feature (powers the bug-linker threshold path). |

### Team & design system context

What agents need to know about people and projects:

| Tool | Purpose |
|---|---|
| `get_team_context` | Per-org team snapshot: people, skill profiles, capacity, current assignments. Used by Triage, Smart Assignment, Standup. |
| `list_design_systems` / `get_design_system` | Project design-system metadata (Vuetify theme, tokens, component patterns) that Design Agent consumes when drafting wireframes. |
| `post_slack_message` | Send a thread reply or DM from an agent run. Used by Triage during intake interviews and by Status / Standup for stakeholder updates. |
| `get_prompt` | Fetch a versioned agent prompt template from the org's prompt registry. Lets agents stay in sync when prompts are tuned. |

### Code graph (`code_*` tool group)

Impact / blast-radius queries powered by the in-tree code-graph indexer (`backend/app/services/code_indexer/`):

| Tool | Purpose |
|---|---|
| `code_impact` | Upstream / downstream BFS from a symbol — *what breaks if I change this?* |
| `code_query` | Substring search across symbol labels + file paths. |
| `code_context` | 360° on a single symbol: attributes, callers, callees, file. |
| `code_community` | List nodes/files in one auto-detected cluster. |
| `code_god_nodes` | Top-N highest-degree hubs — refactoring candidates. |
| `code_stats` | Graph stats + language extension distribution. |

### Hooks & activity

`dev_activity` ingests Claude Code hook events for the Standup Agent's daily aggregation, and `agent_activity` records when an agent run starts/ends for the audit trail.

> **Note for teams whose developers don't run Claude Code.** `dev_activity` is fed by hooks installed in each developer's *own* editor — it is independent of the provider the org runs its agents on. Where those hooks aren't installed, the endpoint simply receives nothing: XP, streaks, standups, and contributor resolution have no input and render empty. Nothing breaks, but those features stay blank until activity arrives from somewhere.

> The full MCP server is in `backend/app/mcp/`. Each handler lives in `handlers_*.py`; the JSON-schema for every tool is defined alongside it. Auth, rate-limiting, and the audit pipeline are in `backend/app/mcp/{auth,audit,streamable}.py`.

## Registering Bodhiorchard's MCP server in your own Claude Code

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

## Bring your own AI — external-LLM mode

Prefer to draft your PRD / design / tech spec with **your own** local AI? Toggle "Auto-generate" off when creating a BUD, then connect Claude Desktop / Cursor / Continue to the read-only remote MCP endpoint and paste the finished spec back into the section editors. Tokens are scoped, expiring, individually revocable, rate-limited, and audited. See **[MCP-REMOTE.md](../MCP-REMOTE.md)** for the full setup, client config snippets, and threat model.
