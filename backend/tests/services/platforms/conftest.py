# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Platform tests are pure functions operating on filesystem fixtures.

Override the session-scoped autouse ``setup_database`` fixture from the
top-level conftest so these tests do not require a live Postgres.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database() -> AsyncGenerator[None, None]:
    """No-op override — platform tests do not touch the database."""
    yield
