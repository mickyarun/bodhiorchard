# TaskFlow QA — Test Automation Project

## Purpose

Playwright + Cucumber test suite for the TaskFlow web application (`examples/taskflow-web`).

## Tech Stack

- **Playwright** for browser automation
- **Cucumber** (Gherkin BDD) for feature files and step definitions
- **TypeScript** for all code
- **Page Object Model** for maintainable selectors

## Project Structure

```
src/
  features/     Gherkin .feature files organized by domain
  steps/        Step definitions (TypeScript) matching feature files
  pages/        Page Object Model classes (one per page/screen)
  fixtures/     Playwright fixtures for auth, setup, etc.
  helpers/      Shared utilities (API client, test data generators)
tests/          Pure Playwright spec tests (non-Cucumber)
  smoke/        Quick health checks
  e2e/          Full end-to-end flows
```

## Conventions

1. **Page Objects**: One class per page, encapsulates all selectors and actions. Import via `@pages/PageName`.
2. **Feature files**: Use descriptive scenario names. One feature per file, grouped by domain.
3. **Step definitions**: Keep steps reusable. Use `Given/When/Then` consistently.
4. **Test data**: Use `helpers/test-data.ts` factories. Never hardcode test data in steps.
5. **API setup/teardown**: Use `helpers/api-client.ts` for pre/post-test data via REST.

## Running Tests

```bash
npm install
npx playwright install

# Run all Playwright tests
npm test

# Run smoke tests only
npm run test:smoke

# Run Cucumber BDD tests
npm run test:cucumber

# Open HTML report
npm run report
```

## Environment

- `BASE_URL`: Frontend URL (default: `http://localhost:9002`)
- `API_URL`: Backend API URL (default: `http://localhost:9001`)

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
