# Connect your local AI to Glideship via MCP

Glideship exposes a Model Context Protocol (MCP) endpoint so your local AI
assistant (Claude Desktop, Cursor, Continue, etc.) can use the same org
context our internal agents see — recent BUDs, the active-features knowledge
base, and your design systems — while you draft a PRD, design or tech spec in
your own tooling.

The endpoint can also write, within narrow limits: it can create a BUD, save
content for the BUD's current phase, and add or edit plan TODOs. Everything
else (testing, code review, status changes, assignment) stays in the app.

## When to use it

New BUDs default to External-LLM mode for every phase — under Advanced
settings on create, opt **in** per phase (`PRD writer` / `Design` /
`Tech plan` / `Test plan`) to anything you'd rather have our agent
auto-fire; leave the rest off and you'll drive them yourself. The BUD
detail page will then
show a banner with a one-click link to this page.

## Endpoint

```
https://<your-glideship-host>/mcp/sse
```

* Transport: MCP `2025-03-26/streamable-http`
* Auth: `Authorization: Bearer <token>` on every request
* CORS: explicitly blocked — desktop clients only

## Available tools

Ten tools, grouped by whether they change anything.

**Read**

| Tool | Purpose |
| --- | --- |
| `get_bud_context` | List in-progress BUDs (with an optional keyword filter) so the AI doesn't propose duplicates. |
| `get_bud_by_id` | Fetch one BUD with the full body of every section, by UUID or by its BUD number. |
| `get_features` | Hybrid keyword + semantic search over your org's active features. |
| `list_design_systems` | Design-system metadata per repo. |
| `get_design_system` | Full HTML / CSS / tokens for a repo or the org default. |
| `get_prompt` | Return our agent's prompt for a BUD stage (`task_type` ∈ `pm` / `design` / `tech_plan` / `testing`). Feed it to your local AI so output matches the section-editor shape. |

**Write**

| Tool | Purpose |
| --- | --- |
| `create_bud` | Create a new BUD. The token's user becomes creator and assignee. |
| `update_bud` | Save content for the BUD's current phase: the PRD, the design, or the tech spec. Assignee only; the server picks the field from the phase, and `expected_phase` rejects the write if the BUD has moved on. |
| `create_todo` | Add a TODO to a BUD's plan for work the tech-spec plan missed. It starts pending and unassigned, and a later regenerate keeps it. |
| `update_todo` | Edit a TODO's title or description. Status and assignment stay in the app. |

All four writes need a per-user token, and every BUD write is saved as a
version you can see in the BUD history.

That's the complete list. `write_bud`, `get_team_context`, `code_*` and
every other internal tool are NOT reachable from this endpoint — the
transport keeps its own allowlist (`REMOTE_TOOLS` in `app/mcp/streamable.py`),
so adding a tool to the internal handler registry never widens this surface.

## Manage your tokens

Visit **Settings → MCP Connect** in the Glideship UI:

1. Click **New token**, give it a descriptive name
   (`claude-desktop-laptop`), set a TTL (default 90 days, max 365).
2. Copy the plaintext token **immediately** — we store only a bcrypt
   hash and won't show it again.
3. Paste it into your client's `mcp.json` (snippets below).
4. Revoke any token from the same page; revocation drops the client's
   SSE stream within ~30s.

## Client config snippets

Claude Desktop / Cursor / Continue's `mcp.json` schemas accept stdio
servers natively. For an HTTP MCP server the reliable cross-version
approach is the `mcp-remote` npm bridge (maintained by the MCP team)
— it runs as a stdio child process and translates to streamable-http
on our side. The newer `"type": "http"` form is shown second for
desktop builds that support it natively, but `mcp-remote` works
everywhere.

### Claude Desktop (recommended — `mcp-remote` bridge)

```jsonc
// ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
// %APPDATA%\Claude\claude_desktop_config.json (Windows)
{
  "mcpServers": {
    "glideship": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://<your-host>/mcp/sse",
        "--header",
        "Authorization: Bearer YOUR_TOKEN_HERE"
      ]
    }
  }
}
```

### Claude Desktop (native HTTP — newer builds only)

```jsonc
{
  "mcpServers": {
    "glideship": {
      "type": "http",
      "url": "https://<your-host>/mcp/sse",
      "headers": { "Authorization": "Bearer YOUR_TOKEN_HERE" }
    }
  }
}
```

### Cursor

```jsonc
// ~/.cursor/mcp.json
{
  "mcpServers": {
    "glideship": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://<your-host>/mcp/sse",
        "--header",
        "Authorization: Bearer YOUR_TOKEN_HERE"
      ]
    }
  }
}
```

### Continue

```jsonc
// ~/.continue/config.json under "experimental.mcpServers"
{
  "name": "glideship",
  "command": "npx",
  "args": [
    "-y",
    "mcp-remote",
    "https://<your-host>/mcp/sse",
    "--header",
    "Authorization: Bearer YOUR_TOKEN_HERE"
  ]
}
```

## Security model in one screen

| What we do | Why |
| --- | --- |
| Bearer auth via your own Glideship MCP token (bcrypt-hashed). | Reuses the credential model your Claude Code CLI already uses; no parallel auth system. |
| Fixed tool allowlist enforced at the transport layer. | Adding a tool to the internal registry cannot accidentally leak it remotely. |
| Writes are limited to the BUD's current creative phase (PRD, design, tech spec) and to TODO text, and BUD content writes are assignee-only. | An external AI can't move a BUD through the lifecycle, reassign work, or touch testing and code-review evidence. |
| Rate limit per (token, IP) **and** globally per token. | Per-IP catches single-machine spam; global catches a leaked token hit from many IPs. |
| Every call logged to `mcp_audit_log` (90-day retention). | Incident response — your admin can see which token did what. |
| Token TTL (default 90 days, max 365) + last-used tracking. | Leaked tokens auto-expire; orphans are visible in the connect panel. |
| SSE stream re-verifies the token every 30s. | Revocation takes effect mid-stream, not "next reconnect". |
| `/mcp/*` strips browser CORS headers. | Defence-in-depth so a future CORS change doesn't open us to a browser-side attack. |

## Threat model — what to worry about

* **Token leakage.** Treat tokens like passwords. Revoke any unused
  tokens from Settings → MCP Connect; an org owner can see and revoke
  every team member's tokens from the admin settings page.
* **Prompt injection via BUD content.** When the local AI reads BUD
  text via `get_bud_context` or `get_bud_by_id`, a maliciously crafted
  BUD could try to steer the LLM. The worst it can do is write through
  the four write tools: new BUDs, content for the current phase of BUDs
  you're assigned to, and TODO text. It can't change status, assignment
  or any other phase, and every BUD write lands as a version you can
  review and restore from the BUD history. Read what your AI proposes
  before you let it call a write tool.
* **Out-of-band data exfiltration.** Anything you allow your local AI
  to read via this endpoint is now subject to that AI's own data
  handling. If your client uploads context to a cloud model, that
  data leaves your org. Keep that in mind when selecting which AI to
  connect.

## Operational reference

| Limit | Default | Where |
| --- | --- | --- |
| Per-(token, IP) | 60 cost-units / min | `app/mcp/rate_limit.py` |
| Per-token global | 300 cost-units / min | same |
| `get_features` cost | 5 units | (pgvector + embedding) |
| `get_bud_context` cost | 1 unit | (single DB scan) |
| `get_bud_by_id` / `get_design_system` cost | 2 units | |
| `create_bud` / `update_bud` cost | 15 units | (version snapshot + embedding) |
| `create_todo` / `update_todo` cost | 5 units | (single-row write) |
| Audit log retention | 90 days | `app/services/mcp_audit_cleanup.py` |
| Token TTL | 90 days (max 365) | `app/api/v1/me.py` |
| SSE heartbeat | 30 s | `app/mcp/streamable.py` |

## Reporting a token leak

Revoke first, investigate after. From the connect page click the
trash icon next to the suspect token — it drops the SSE stream within
one heartbeat and any subsequent POST returns 401. Then check
`mcp_audit_log` (org-scoped query in the admin panel) for the rows
written by that token id.
