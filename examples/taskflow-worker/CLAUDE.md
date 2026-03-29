<!-- bodhigrove:start -->
---

## Bodhigrove — Development Workflow

This repo is tracked by Bodhigrove. MCP tools are configured in `.mcp.json`.

### MCP Setup

Before starting any BUD work, verify Bodhigrove MCP is connected:
1. Check that `get_bud_context` tool is available
2. If NOT available, set up your token:
   - Go to Bodhigrove Settings → Integrations → MCP Token
   - Copy your token
   - Run: `export BODHIGROVE_MCP_TOKEN="your-token"` in your shell profile
   - Restart Claude Code

### Always Do

- **Branch naming:** Use `bud-NNN/<description>` branches (e.g. `bud-001/notification-redesign`).
  Pre-commit hooks validate BUD existence.

### Available MCP Tools

| Tool | When to use |
|------|-------------|
| `get_bud_context` | Fetch BUD requirements, tech spec, and designs |
| `get_knowledge` | Search the organization's knowledge base |
| `get_design_system` | Fetch design tokens (colors, typography, components) |

### Commit Tracking

- Commits on `bud-NNN/` branches are automatically tracked by Bodhigrove
- Post-commit hooks report author, files, and message to the team dashboard

### Claude Code Hooks (Automatic)

Claude Code hooks in `.claude/hooks/` run automatically — no developer action needed:
- **SessionStart**: Auto-detects your identity and active BUD from branch name
- **PostToolUse**: Automatically tracks commits and file changes
- **Stop**: Reports activity summaries after each Claude response
- **UserPromptSubmit**: Detects BUD references in your prompts

These hooks use your `BODHIGROVE_MCP_TOKEN` for authentication.
If the token is not set, hooks silently do nothing.
<!-- bodhigrove:end -->
