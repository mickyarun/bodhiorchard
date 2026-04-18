<!-- bodhiorchard:start -->
---

## Bodhiorchard — Development Workflow

This repo is tracked by Bodhiorchard. MCP tools are configured in `.mcp.json`.

### MCP Setup

Before starting any BUD work, verify Bodhiorchard MCP is connected:
1. Check that `get_bud_context` tool is available
2. If NOT available, set up your token:
   - Go to Bodhiorchard Settings → Integrations → MCP Token
   - Copy your token
   - Run: `export BODHIORCHARD_MCP_TOKEN="your-token"` in your shell profile
   - Restart Claude Code

### Always Do

- **Branch naming:** Use `bud-NNN/<description>` branches (e.g. `bud-001/notification-redesign`).
  Pre-commit hooks validate BUD existence.

### Available MCP Tools

| Tool | When to use |
|------|-------------|
| `get_bud_plan` | Fetch your assigned TODOs on a `bud-NNN/` branch (call on session start) |
| `takeover_todo` | Claim a TODO before implementing it (REQUIRED) |
| `complete_todo` | Mark a TODO completed with a summary of what you implemented |
| `get_bud_context` | Fetch BUD requirements, tech spec, and designs |
| `get_knowledge` | Search the organization's knowledge base |
| `get_design_system` | Fetch design tokens (colors, typography, components) |

### TODO Workflow (STRICT — follow exactly)

When you start a session on a `bud-NNN/` branch:

1. Call `get_bud_plan(bud_number=NNN)` to see the plan and your assigned TODOs.
   - TODOs marked `"yours": true` are for you.
   - TODOs marked `"skip": true` are assigned to other developers — do NOT implement them.
2. For each of your TODOs, in order:
   a. Call `takeover_todo(bud_number=NNN, sequence=X)`.
      - On **success**: you now have the `context_md` — proceed to implement.
      - On **failure**: skip this TODO and move to the next one (someone else has it).
   b. Implement the TODO using the returned `context_md` and the tech spec.
   c. Call `complete_todo(bud_number=NNN, sequence=X, summary="…")` when done.
      The summary should be a short description of what you built (1-2 sentences).
3. NEVER implement a TODO without a successful `takeover_todo` call first.
4. NEVER implement a TODO marked `"skip": true` — another developer is working on it.
5. If `get_bud_plan` shows no TODOs assigned to you, stop and ask the user / team lead.

### Cross-developer Awareness

`get_bud_plan` also returns `other_branches` — branches by other developers
on the same BUD, with the files they've touched. If you're editing shared
code, consider `git fetch` + `git diff origin/<their-branch> -- <file>` to
stay consistent with their work.

### Commit Tracking

- Commits on `bud-NNN/` branches are automatically tracked by Bodhiorchard
- Post-commit hooks report author, files, and message to the team dashboard

### Claude Code Hooks (Automatic)

Claude Code hooks in `.claude/hooks/` run automatically — no developer action needed:
- **SessionStart**: Auto-detects your identity and active BUD from branch name
- **PostToolUse**: Automatically tracks commits and file changes
- **Stop**: Reports activity summaries after each Claude response
- **UserPromptSubmit**: Detects BUD references in your prompts

These hooks use your `BODHIORCHARD_MCP_TOKEN` for authentication.
If the token is not set, hooks silently do nothing.
<!-- bodhiorchard:end -->
