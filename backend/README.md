# Bodhiorchard Backend

AI-powered software development platform backend built with FastAPI, SQLAlchemy 2.0, and PostgreSQL with pgvector.

## Tech Stack

- **Framework:** FastAPI 0.104+
- **ORM:** SQLAlchemy 2.0 (async) with asyncpg
- **Database:** PostgreSQL 16 with pgvector extension
- **Auth:** JWT (python-jose) + bcrypt (passlib)
- **LLM:** litellm (multi-provider: Ollama, OpenAI, Anthropic)
- **Embeddings:** pgvector for semantic search
- **Cache:** Redis
- **Migrations:** Alembic (async)
- **Logging:** structlog

## Prerequisites

- Python 3.12+
- Docker and Docker Compose
- (Optional) Ollama for local LLM inference

## Quick Start

```bash
# Start all services (Postgres, Redis, Ollama, Backend)
docker compose up -d

# The API will be available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

## Local Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env

# Start infrastructure services only
docker compose up -d postgres redis ollama

# Run database migrations
alembic upgrade head

# Start the development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Project Structure

```
backend/
├── alembic/              # Database migration scripts
├── app/
│   ├── api/              # Route handlers
│   │   └── v1/           # Versioned API endpoints
│   ├── agents/           # AI agent orchestration
│   ├── core/             # Security, dependencies
│   ├── mcp/              # Model Context Protocol integration
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   └── services/         # Business logic (LLM, embeddings)
└── tests/                # Test suite
```

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://bodhiorchard:bodhiorchard@localhost:5432/bodhiorchard` |
| `SECRET_KEY` | JWT signing key | `change-me-in-production` |
| `LLM_PROVIDER` | LLM provider | `ollama` |
| `EMBEDDING_PROVIDER` | Embedding provider | `ollama` |

## File Storage (QA evidence uploads)

QA testers attach screenshots / logs / PDFs to manual test cases. Those files
flow through `app.services.file_storage.FileStorage`, which has two backends
selected by env vars at startup:

| Variable | Default | Effect |
|---|---|---|
| `FILE_STORAGE_S3` | `false` | When `true`, every upload / download / delete goes to S3. When `false` (default), uses the local-disk backend. |
| `FILE_STORAGE_S3_BUCKET` | _empty_ | S3 bucket name. **Required** when `FILE_STORAGE_S3=true` — startup fails fast if missing. |
| `AWS_REGION` | `us-east-1` | S3 region. |
| `FILE_STORAGE_LOCAL_DIR` | `data/uploads` | Local backend root (relative paths resolve against the backend's cwd). |

AWS credentials are resolved through the standard boto3 chain, in order:

1. `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` (and optional
   `AWS_SESSION_TOKEN` for temporary STS creds) in the env.
2. `~/.aws/credentials` (default profile, or one named by `AWS_PROFILE`).
3. EC2 / ECS / EKS instance or task role.

Set the env vars only when neither a credentials file nor a role is
available — typical for CI runners and single-host dev boxes. In
production prefer instance / task-role IAM so the deploy doesn't carry
static keys.

### Picking a backend

- **Hybrid host mode**: local disk is fine — `FILE_STORAGE_LOCAL_DIR` points
  at a host-owned path that survives backend restarts.
- **Single-host Docker**: local disk works **only because** the default
  `docker-compose.yml` mounts a named volume on `/app/data/uploads`
  (`evidence_data`). Without that mount, every container rebuild silently
  wipes every upload — a recurring footgun pre-merge. The backend logs a
  `file_storage_local_dir_may_be_ephemeral` warning at startup when the
  resolved path looks like an unmounted container path.
- **Multi-host / production**: set `FILE_STORAGE_S3=true` with a bucket.
  The local fallback doesn't scale across replicas, and a host loss is
  evidence loss.

### Validation

`FileStorage.validate_config()` runs once during the lifespan startup
hook in `app/main.py`. It raises `FileStorageError` (logged at `error`,
non-fatal — evidence upload outages shouldn't take the whole API down)
if S3 is enabled but no bucket is set, and warns if the local backend
points at an apparently-ephemeral container path.

### Upgrading an existing Docker deployment

The `evidence_data` named volume is **new** in this revision. On first
`docker-compose up` after pulling, the empty volume mounts over the
existing `/app/data/uploads` directory and any files in that directory
inside the old container become invisible. If your deploy had evidence
files there:

```bash
# Before the upgrade — copy data out of the old container.
docker cp <old-backend-container>:/app/data/uploads ./evidence-backup

# After the upgrade — copy data into the new named volume.
docker cp ./evidence-backup/. <new-backend-container>:/app/data/uploads
```

Or simply set `FILE_STORAGE_S3=true` with a bucket before the upgrade
and re-upload nothing.

## Database Migrations

```bash
# Generate a new migration after model changes
alembic revision --autogenerate -m "description of changes"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## API Documentation

When the server is running, interactive API documentation is available at:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
