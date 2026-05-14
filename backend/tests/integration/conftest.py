# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Opt-in Postgres fixtures for integration tests.

Lives in ``tests/integration/conftest.py`` so the fixtures only load
when pytest is collecting tests under ``tests/integration/`` — keeps
the default ``pytest`` run (which deselects the ``integration`` marker
via ``addopts`` in ``pyproject.toml``) free of any Docker / migration
side effects. The previous repo-wide ``conftest.py`` once held a
session-scoped autouse fixture that called ``Base.metadata.drop_all()``
on teardown and wiped the developer's dev DB; that is the footgun the
``conftest.py`` docstring warns about, and the reason these fixtures
live under ``integration/`` not ``tests/``.

Each session spins up an ephemeral ``pgvector/pgvector:pg16`` container
via ``testcontainers`` and runs the full Alembic migration chain
against it. The container is torn down at session end; the developer's
local Postgres is never touched.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from alembic import command


@pytest.fixture(scope="session")
def pg_container() -> Iterator[PostgresContainer]:
    """Start an ephemeral pgvector-enabled Postgres container once per session.

    ``pgvector/pgvector:pg16`` is the same image the production migration
    chain assumes (``CREATE EXTENSION vector`` lives in the initial
    schema migration). Using a stock ``postgres:16`` image would cause
    ``alembic upgrade head`` to fail on the very first migration.
    """
    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        username="test",
        password="test",
        dbname="bodhiorchard_test",
    )
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def pg_async_url(pg_container: PostgresContainer) -> str:
    """asyncpg-flavoured connection URL pointing at the test container."""
    # testcontainers returns a psycopg2-style URL; convert to asyncpg.
    sync_url: str = pg_container.get_connection_url()
    # Format: postgresql+psycopg2://test:test@host:port/bodhiorchard_test
    return sync_url.replace("postgresql+psycopg2", "postgresql+asyncpg")


@pytest.fixture(scope="session")
def _apply_migrations(pg_container: PostgresContainer, pg_async_url: str) -> str:
    """Run ``alembic upgrade head`` against the ephemeral container.

    Runs once per session. Returns the asyncpg URL so downstream fixtures
    can depend on this fixture by name to enforce migration order.
    """
    backend_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_root / "alembic"))
    # Alembic's env.py reads DATABASE_URL from os.environ. Stash the
    # current value (if any) and restore afterwards so we don't leak
    # the container URL into the rest of the session.
    prior = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = pg_async_url
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        if prior is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prior
    return pg_async_url


@pytest_asyncio.fixture
async def pg_session_factory(
    _apply_migrations: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Yield an ``AsyncSession`` factory bound to the migrated test DB.

    Each test gets its own engine + factory so transactions can't bleed
    across tests through a shared pool. The engine is disposed at test
    end. The DB itself is shared across tests in a session — write
    tests on disjoint keys (e.g. a fresh ``bud_id`` per test) to avoid
    cross-test contamination.
    """
    engine = create_async_engine(_apply_migrations, future=True)
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
