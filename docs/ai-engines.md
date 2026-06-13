# AI Engines & MCP Server

Bodhiorchard is **AI-engine-agnostic**. The agent layer is engine-independent — adding a new engine is API rewiring only, no deployment changes. Today: Claude Code + the Anthropic direct API. Next: Ollama (air-gapped), OpenAI, OpenAI Codex.

## Today — Claude Code (codebase-aware agents)

Codebase-aware agent runs (BUD spec, Tech Plan, Implementation, Code Review) are executed by the [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI, which gives agents file access, shell tool-use, and direct access to Bodhiorchard's MCP server.

**Why Claude Code (and not just the raw API):**

- **Codebase awareness out of the box** — Claude Code already knows how to read files, run shell commands, and edit code; Bodhiorchard reuses that surface area instead of re-implementing it.
- **Token-efficient by default** — agent prompts use Anthropic prompt caching, structured tool-use, and incremental context loading. The cost per BUD stays low even on long sessions.
- **One runtime, two billing models** — point Bodhiorchard at an Anthropic API key (pay-per-token) **or** at a host `claude login` session backed by a Claude Pro / Max subscription (flat-rate). Same agents either way.

### Authentication modes

| Mode | When the org uses this | Where the credential lives |
|---|---|---|
| `api_key` | Full Docker deployments, or any host that doesn't have a Claude subscription | `sk-ant-…` key encrypted in Postgres (Fernet AES-128) and pushed into the backend's process env on save |
| `hybrid_host` | Hybrid deployments where the developer already runs `claude` interactively | Host's existing `claude login` session — nothing stored in the database |

The backend auto-detects which mode is available (via `/.dockerenv`) and the Settings page only surfaces the option that actually works for that deployment.

## Today — Anthropic direct API (lightweight non-codebase agents)

Triage, Bug-Linker, and Standup don't need to read files — they reason over chat messages, bug reports, and aggregated activity. For those, Bodhiorchard skips Claude Code and calls the Anthropic API directly. Lower latency, lower per-call cost, same `sk-ant-…` key (configured at **Settings → AI Configuration → Anthropic API**).

## Coming soon

| Engine | Status |
|---|---|
| **Ollama** (fully local, free, air-gapped) | Planned |
| **OpenAI** API (GPT-4o / 4 / 3.5) | Planned |
| **OpenAI Codex** | In development |

These will appear as additional presets in the AI Configuration page — API rewiring only, no deployment changes.

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
