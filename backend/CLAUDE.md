# CLAUDE.md - Bodhiorchard Backend Development Guidelines

## Tech Stack
- **Python 3.12+** with strict type hints
- **FastAPI** for HTTP API
- **SQLAlchemy 2.0** (async, mapped_column style) with asyncpg
- **PostgreSQL 16** with pgvector extension
- **Alembic** for database migrations (async)
- **Pydantic v2** for DTOs and settings
- **fastembed** for local ONNX-based text embeddings (BAAI/bge-small-en-v1.5, 384d)
- **structlog** for structured logging
- **Redis** for caching

## Project Structure
- `app/models/` - SQLAlchemy ORM models (UUID PKs, TimestampMixin)
- `app/schemas/` - Pydantic request/response schemas
- `app/api/v1/` - Versioned route handlers
- `app/core/` - Security (JWT, bcrypt) and FastAPI dependencies
- `app/services/` - Business logic (LLM, embeddings)
- `app/agents/` - AI agent orchestration layer
- `app/mcp/` - Model Context Protocol servers
- `tests/` - pytest-asyncio test suite

## Key Patterns
- **Async everywhere:** All database operations, HTTP calls, and LLM calls are async
- **Pydantic for DTOs:** Use Pydantic BaseModel for all request/response schemas with `from_attributes = True`
- **SQLAlchemy 2.0 style:** Use `Mapped[]`, `mapped_column()`, never old-style `Column()`
- **UUID primary keys:** All tables use UUID v4 PKs via `BaseModel` base class
- **Multi-tenant:** All domain tables have a non-nullable `org_id` FK to `organizations`
- **Dependency injection:** Use FastAPI `Depends()` for DB sessions and auth
- **Structured logging:** Use `structlog.get_logger()`, never `print()`

## Testing
- Framework: pytest + pytest-asyncio
- Use `client` fixture for HTTP tests, `db_session` for direct DB tests
- Test database configured via `TEST_DATABASE_URL` env var
- Run: `pytest`

## Code Style
- **Formatter:** ruff (black-compatible), line length 99
- **Linter:** ruff with E, F, I, N, W, UP, B, A, SIM rules
- **Type checking:** mypy strict mode with pydantic plugin
- All functions must have type hints on parameters and return values
- All modules must have docstrings
- All public functions must have docstrings

## Async SQLAlchemy Gotchas
- **MissingGreenlet:** After modifying ORM attributes (e.g., `bug.embedding = vec`), always `await db.flush()` + `await db.refresh(obj)` before accessing other attributes — lazy loading fails outside the async greenlet
- **Background tasks:** Use `asyncio.create_task()` with a module-level `set` to hold references (prevents GC). Each task must create its own `AsyncSessionLocal()` session — never share the request's session
- **Guard ordering:** In the BUD PATCH handler, status guards must run BEFORE `transition_feature_for_bud` and other side-effect-producing calls
- **Pydantic aliases:** Use snake_case field names in Python constructors (not camelCase aliases) — mypy can't resolve aliases even with `populate_by_name=True`

## Common Commands
```bash
# Run dev server
uvicorn app.main:app --reload

# Run tests
pytest

# Lint and format
ruff check . --fix
ruff format .

# Type check
mypy app/

# Generate migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```
