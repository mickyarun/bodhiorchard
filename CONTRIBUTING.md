# Contributing to Bodhiorchard

Thank you for your interest in contributing to Bodhiorchard! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Code Standards](#code-standards)
- [Submitting Changes](#submitting-changes)
- [Issue Guidelines](#issue-guidelines)
- [Pull Request Process](#pull-request-process)
- [Contributor License Agreement](#contributor-license-agreement)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior by opening an issue.

---

## How Can I Contribute?

### Reporting Bugs

Found a bug? Please [open an issue](../../issues/new?template=bug_report.yml) with:

- A clear, descriptive title
- Steps to reproduce the behavior
- Expected vs actual behavior
- Screenshots if applicable
- Your environment details (OS, browser, Python/Node versions)

### Suggesting Features

Have an idea? [Open a feature request](../../issues/new?template=feature_request.yml) with:

- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered
- How it fits into Bodhiorchard's philosophy (AI doing busywork, humans doing decisions)

### Contributing Code

1. Look for issues labeled [`good first issue`](../../labels/good%20first%20issue) or [`help wanted`](../../labels/help%20wanted)
2. Comment on the issue to let others know you're working on it
3. Fork, code, test, and submit a PR

### Improving Documentation

Documentation improvements are always welcome — README, code comments, API docs, or this guide itself.

---

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 16+ with pgvector extension
- Redis
- Docker and Docker Compose (recommended)

### Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate       # Windows

# Install dependencies
pip install -e ".[dev]"

# Start infrastructure (PostgreSQL, Redis, Ollama)
docker compose up -d

# Run database migrations
alembic upgrade head

# Start the dev server
uvicorn app.main:app --reload
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
# Available at http://localhost:3000
```

### Running Tests

```bash
# Backend
cd backend
pytest                          # all tests
pytest tests/test_auth.py       # specific file
pytest -x                       # stop on first failure

# Frontend
cd frontend
npm run lint                    # lint check
npx vue-tsc --noEmit            # type check
```

---

## Code Standards

### Backend (Python)

| Rule | Details |
|---|---|
| **Formatter** | `ruff format .` (black-compatible, 99 char line length) |
| **Linter** | `ruff check . --fix` (rules: E, F, I, N, W, UP, B, A, SIM) |
| **Type checker** | `mypy app/` (strict mode with pydantic plugin) |
| **Type hints** | Required on all function parameters and return values |
| **Docstrings** | Required on all modules and public functions |
| **ORM style** | SQLAlchemy 2.0 — `Mapped[]`, `mapped_column()`, never `Column()` |
| **Async** | All DB operations, HTTP calls, and LLM calls must be async |
| **Logging** | `structlog.get_logger()`, never `print()` |
| **Multi-tenant** | All domain tables must have `org_id` FK to `organizations` |

```bash
# Run all checks before committing
ruff check . --fix && ruff format . && mypy app/ && pytest
```

### Frontend (TypeScript / Vue)

| Rule | Details |
|---|---|
| **Framework** | Vue 3 Composition API with `<script setup lang="ts">` |
| **Component library** | Vuetify 3 |
| **State management** | Pinia stores |
| **Linter** | `eslint . --ext .vue,.ts` |
| **Type checker** | `vue-tsc --noEmit` |
| **Naming** | PascalCase for components, camelCase for variables/functions |
| **Styles** | Scoped `<style scoped>` per component; shared styles in `assets/styles/main.scss` |

```bash
# Run all checks before committing
npm run lint && npx vue-tsc --noEmit
```

### Commit Messages

Use clear, descriptive commit messages:

```
<type>: <short summary>

<optional body explaining why, not what>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`

Examples:
```
feat: add bug threshold alerts to reassignment agent
fix: prevent duplicate triage sessions for same Slack thread
docs: add MCP tool usage examples to README
refactor: extract shared agent data to @/data/agents.ts
```

### Database Migrations

When modifying models:

```bash
cd backend

# Generate migration
alembic revision --autogenerate -m "add_column_to_buds"

# Review the generated migration file in alembic/versions/
# Then apply
alembic upgrade head
```

- Always review auto-generated migrations before committing
- Test both `upgrade` and `downgrade` paths
- Never modify a migration that has been merged to `main`

---

## Submitting Changes

### Branch Naming

```
feature/short-description     # new features
fix/short-description         # bug fixes
docs/short-description        # documentation
refactor/short-description    # code refactoring
```

### Workflow

1. **Fork** the repository
2. **Create a branch** from `main`
   ```bash
   git checkout -b feature/my-feature
   ```
3. **Make your changes** — keep commits focused and atomic
4. **Run all checks**
   ```bash
   # Backend
   cd backend && ruff check . --fix && ruff format . && mypy app/ && pytest

   # Frontend
   cd frontend && npm run lint && npx vue-tsc --noEmit
   ```
5. **Push** to your fork
   ```bash
   git push origin feature/my-feature
   ```
6. **Open a Pull Request** against `main`

---

## Issue Guidelines

### Before Opening an Issue

1. **Search existing issues** — your problem may already be reported
2. **Check the docs** — the answer might be in the README or API docs
3. **Try the latest version** — the bug may already be fixed on `main`

### Writing a Good Issue

**Do:**
- Use a clear, specific title
- Include steps to reproduce (for bugs)
- Provide environment details
- Attach screenshots or logs when relevant
- Label appropriately (`bug`, `feature`, `documentation`, `question`)

**Don't:**
- Open vague issues like "it doesn't work"
- Combine multiple unrelated problems in one issue
- Open issues for general questions — use Discussions instead

### Issue Labels

| Label | Description |
|---|---|
| `bug` | Something isn't working |
| `feature` | New feature request |
| `enhancement` | Improvement to existing feature |
| `documentation` | Documentation improvements |
| `good first issue` | Good for newcomers |
| `help wanted` | Extra attention needed |
| `priority: high` | Needs immediate attention |
| `priority: low` | Nice to have |
| `agent: triage` | Related to Triage Agent |
| `agent: bud` | Related to BUD Agent |
| `agent: learning` | Related to Learning Agent |
| `backend` | Backend (Python/FastAPI) |
| `frontend` | Frontend (Vue/TypeScript) |
| `mcp` | Model Context Protocol |
| `security` | Security-related |
| `wontfix` | Will not be addressed |

---

## Pull Request Process

### PR Checklist

Before requesting a review, ensure:

- [ ] Code follows the [code standards](#code-standards) above
- [ ] All linting passes (`ruff check`, `eslint`)
- [ ] All type checks pass (`mypy`, `vue-tsc`)
- [ ] All existing tests pass
- [ ] New tests added for new functionality
- [ ] Database migrations included (if models changed)
- [ ] No secrets, API keys, or `.env` files committed
- [ ] PR description explains **what** and **why**

### PR Description Template

Your PR description should include:

```markdown
## Summary
Brief description of what this PR does and why.

## Changes
- Bullet points of specific changes

## Testing
How you tested these changes.

## Screenshots
If applicable (especially for frontend changes).
```

### Review Process

1. **Automated checks** — linting, type checking, and tests run on every PR
2. **Maintainer review** — a project maintainer will review your code
3. **Feedback** — address review comments with new commits (don't force-push during review)
4. **Merge** — maintainer squash-merges once approved

### What Makes a Good PR

- **Small and focused** — one feature or fix per PR
- **Well-tested** — include tests for new behavior
- **Well-documented** — explain non-obvious decisions in comments or PR description
- **No unrelated changes** — don't sneak in formatting fixes or refactors

---

## Architecture Notes for Contributors

### Key Concepts

- **BUD (Build-Up Document)** — the central work item (replaces tickets/stories)
- **Agents** — AI modules that automate lifecycle phases (defined in `backend/app/agents/`)
- **MCP** — Model Context Protocol for AI tool integration (`backend/app/mcp/`)
- **Multi-tenant** — every query is scoped to an `org_id`; never bypass this

### Where Things Live

| Area | Backend | Frontend |
|---|---|---|
| API endpoints | `app/api/v1/` | — |
| Business logic | `app/services/` | — |
| Data models | `app/models/` | `src/types/` |
| DTOs | `app/schemas/` | — |
| Agent definitions | `app/agents/skills/` | — |
| State management | — | `src/stores/` |
| Pages | — | `src/views/` |
| Shared components | — | `src/components/` |
| Shared data | — | `src/data/` |

### Adding a New Agent

1. Create the skill definition in `backend/app/agents/skills/your-agent.md`
2. Register in `backend/app/agents/skill_mapping.py`
3. Add frontend agent data in `frontend/src/data/agents.ts`
4. Add any new MCP tools in `backend/app/mcp/server.py`

### Adding a New API Endpoint

1. Create or update the schema in `backend/app/schemas/`
2. Create or update the model in `backend/app/models/`
3. Create or update the repository in `backend/app/repositories/`
4. Add the route in `backend/app/api/v1/`
5. Register the router in `backend/app/api/router.py`
6. Generate a migration if models changed

---

## Contributor License Agreement

By submitting a pull request to Bodhiorchard, you agree to the following:

1. Your contributions are your original work (or you have the right to submit them)
2. Your contributions are licensed under the [AGPL-3.0 license](LICENSE)
3. You grant the project maintainer (**Arun Rajkumar**) a perpetual, worldwide, non-exclusive, royalty-free, irrevocable license to use, modify, sublicense, and distribute your contributions under any license — including commercial licenses

This CLA allows the project to offer dual licensing (open source + commercial) while keeping contributions open source by default. You retain copyright of your work.

---

## Questions?

- **General questions** — use [GitHub Discussions](../../discussions)
- **Bug reports** — use [Issues](../../issues)
- **Security vulnerabilities** — email privately (do not open a public issue)

Thank you for helping make Bodhiorchard better!
