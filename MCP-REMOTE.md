# Connect your local AI to Bodhiorchard via MCP

Bodhiorchard exposes a **read-only** Model Context Protocol (MCP) endpoint so
your local AI assistant (Claude Desktop, Cursor, Continue, etc.) can use the
same org context our internal agents see — recent BUDs, the active-features
knowledge base, and your design systems — while you draft a PRD, design or
tech spec in your own tooling.

When you finish, paste the result into the BUD section editor. The remote
endpoint **cannot write** to your data; uploads happen through the in-app
editor only.

## When to use it

Toggle **External-LLM mode** on a BUD (Advanced settings → "Auto-generate"
switch off) when you'd rather drive the writing yourself instead of letting
the PM / Designer / TechPlanner agents run. The BUD detail page will then
show a banner with a one-click link to this page.

## Endpoint

```
https://<your-bodhiorchard-host>/mcp/sse
```

* Transport: MCP `2025-03-26/streamable-http`
* Auth: `Authorization: Bearer <token>` on every request
* CORS: explicitly blocked — desktop clients only

## Available tools

| Tool | Purpose |
| --- | --- |
| `get_bud_context` | List recent BUDs in your org for context. |
| `get_features` | Semantic knowledge search over your org's active features. |
| `list_design_systems` | Design-system metadata per repo. |
| `get_design_system` | Full HTML / CSS / tokens for a repo or the org default. |

That's the complete list. `write_bud`, `get_team_context`, `code_*` and
every other internal tool are NOT reachable from this endpoint — adding a
new tool to the internal handler registry never widens this surface.

## Manage your tokens

Visit **Settings → MCP Connect** in the Bodhiorchard UI:

1. Click **New token**, give it a descriptive name
   (`claude-desktop-laptop`), set a TTL (default 90 days, max 365).
2. Copy the plaintext token **immediately** — we store only a bcrypt
   hash and won't show it again.
3. Paste it into your client's `mcp.json` (snippets below).
4. Revoke any token from the same page; revocation drops the client's
   SSE stream within ~30s.

## Client config snippets

### Claude Desktop

```jsonc
// ~/Library/Application Support/Claude/claude_desktop_config.json (macOS)
// %APPDATA%\Claude\claude_desktop_config.json (Windows)
{
  "mcpServers": {
    "bodhiorchard": {
      "transport": "streamable-http",
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
    "bodhiorchard": {
      "url": "https://<your-host>/mcp/sse",
      "transport": "streamable-http",
      "headers": { "Authorization": "Bearer YOUR_TOKEN_HERE" }
    }
  }
}
```

### Continue

```jsonc
// ~/.continue/config.json under "experimental.mcpServers"
{
  "name": "bodhiorchard",
  "transport": {
    "type": "streamable-http",
    "url": "https://<your-host>/mcp/sse",
    "headers": { "Authorization": "Bearer YOUR_TOKEN_HERE" }
  }
}
```

## Security model in one screen

| What we do | Why |
| --- | --- |
| Bearer auth via your own `bodhi_token` (bcrypt-hashed). | Reuses the credential model your Claude Code CLI already uses; no parallel auth system. |
| Read-only tool allowlist enforced at the transport layer. | Adding a tool to the internal registry cannot accidentally leak it remotely. |
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
  text via `get_bud_context`, a maliciously crafted BUD could try to
  steer the LLM. The remote endpoint deliberately gives that LLM no
  way to call `write_bud`, so the worst case is misleading output in
  your local client — never a write back to your org.
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
| Audit log retention | 90 days | `app/services/mcp_audit_cleanup.py` |
| Token TTL | 90 days (max 365) | `app/api/v1/me.py` |
| SSE heartbeat | 30 s | `app/mcp/streamable.py` |

## Reporting a token leak

Revoke first, investigate after. From the connect page click the
trash icon next to the suspect token — it drops the SSE stream within
one heartbeat and any subsequent POST returns 401. Then check
`mcp_audit_log` (org-scoped query in the admin panel) for the rows
written by that token id.
