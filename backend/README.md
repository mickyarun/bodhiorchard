# Bodhigrove Backend

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
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://bodhigrove:bodhigrove@localhost:5432/bodhigrove` |
| `SECRET_KEY` | JWT signing key | `change-me-in-production` |
| `LLM_PROVIDER` | LLM provider | `ollama` |
| `EMBEDDING_PROVIDER` | Embedding provider | `ollama` |

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
