# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Shared pytest fixtures for the Bodhiorchard test suite.

**No DB scaffolding lives here.** The previous autouse session-scope
``setup_database`` fixture called ``Base.metadata.drop_all()`` on
teardown — which happily wiped whatever ``TEST_DATABASE_URL`` resolved
to. With the env var unset (or pointed at the dev DB by mistake), a
single ``pytest`` invocation deleted the entire dev schema. None of
the existing tests actually used the helper fixtures (``db_session``,
``client``) — every test that needs DB state opens its own session
inline. So the fixtures were both unused and dangerous; they're gone.

If a future test genuinely needs a shared schema-bootstrapped DB:

1. Put the bootstrap in a *function-scope* fixture, not session-scope.
2. Hard-fail if the URL doesn't end with ``_test`` (or some equivalent
   sentinel) — never trust a fallback.
3. Document why the inline-session pattern in the existing tests is
   not enough; the bar for re-introducing global DB teardown is high.
"""

import asyncio

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop. Required by pytest-asyncio for
    session-scope async fixtures defined elsewhere in the suite.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
