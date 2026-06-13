# API Reference

Bodhiorchard exposes three programmable surfaces. All three run on the same host as the backend.

| Surface | Port | What it's for |
|---|---|---|
| **REST** | `:8000/api/v1` | Day-to-day CRUD: BUDs, orgs, repos, skills, triage, Slack/GitHub webhooks. FastAPI; interactive docs at [/docs](http://localhost:8000/docs) (Swagger) and [/redoc](http://localhost:8000/redoc). |
| **MCP** | `:8001/mcp` | Tools for Claude Code and other MCP clients — BUD lifecycle writes, feature registry, code graph, team context. Full list in [AI Engines & MCP Server](ai-engines.md). |
| **WebSocket** | `:8000/ws/jobs/{job_id}` | Live progress for async jobs (repo scans, BUD generation, etc.). Frontend uses `useJobSocket`; CLI consumers can use `wscat`. |

## Key REST endpoints

| Endpoint | Description |
|---|---|
| `POST /api/v1/auth/login` | JWT authentication |
| `GET /api/v1/buds` | List BUD documents |
| `POST /api/v1/buds` | Create a new BUD |
| `GET /api/v1/dashboard/tree-data` | 3D Living-Tree visualization data |
| `GET /api/v1/skills/profiles` | Developer skill profiles |
| `POST /api/v1/skills/scan` | Trigger repository scan (returns `202` + `job_id`) |
| `GET /api/v1/triage-sessions` | Triage approval queue |
| `POST /api/v1/slack/events` | Slack webhook handler |

## Example: create a BUD via `curl`

```bash
curl -X POST http://localhost:8000/api/v1/buds \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Add export-to-PDF on the dashboard",
    "stage": "bud",
    "summary": "Users want to share weekly dashboard snapshots with leadership."
  }'
```

## Async-job pattern

Long-running operations (repo scans, embedding builds, BUD generation) return `202 Accepted` with a `job_id`. Subscribe to `ws://localhost:8000/ws/jobs/{job_id}` for progress events instead of polling the REST endpoint.

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://bodhiorchard:bodhiorchard@localhost:5432/bodhiorchard` |
| `SECRET_KEY` | JWT signing key | `change-me-in-production` |
| `ENCRYPTION_KEY` | AES key for secrets at rest (used to encrypt the Claude API key, Slack tokens, GitHub private keys) | (generated) |
| `ANTHROPIC_API_KEY` | Optional process-level fallback for Claude auth. Ignored when an org-level key is configured in Settings. | (unset) |
| `EMBEDDING_PROVIDER` | Embedding provider (local ONNX via [fastembed](https://github.com/qdrant/fastembed)) | `fastembed` |
| `EMBEDDING_MODEL` | Embedding model | `BAAI/bge-small-en-v1.5` (384-d) |
| `EMBEDDING_DIMENSIONS` | Vector dimensions (must match `EMBEDDING_MODEL`) | `384` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379` |
| `SLACK_BOT_TOKEN` | Slack bot token | (optional) |
| `GITHUB_PAT` | GitHub personal access token | (optional) |
