# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Local conftest for schema-level tests.

Overrides the parent ``tests/conftest.py`` ``setup_database`` autouse
fixture with a no-op so these pure-Pydantic tests don't require a live
Postgres instance. Schema tests never touch the DB — running them should
not force a CI to spin up a database.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database() -> AsyncGenerator[None, None]:  # noqa: PT004
    """No-op override: schema tests have no DB dependency."""
    yield
