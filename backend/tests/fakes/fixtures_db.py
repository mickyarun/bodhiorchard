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

"""Fakes wired to the integration test database.

These depend on ``pg_session_factory`` and ``client`` from
``tests/integration/conftest.py``, so re-export them only from conftests
under ``tests/integration/``.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.fakes.app_state import bind_app_sessions
from tests.fakes.claude_runner import FakeClaudeRunner


@pytest.fixture
def app_sessions(
    pg_session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> async_sessionmaker[AsyncSession]:
    """Background ``AsyncSessionLocal()`` users write to the test database."""
    bind_app_sessions(monkeypatch, pg_session_factory)
    return pg_session_factory


@pytest.fixture
def mcp_claude(
    fake_claude: FakeClaudeRunner,
    client: AsyncClient,
    app_sessions: async_sessionmaker[AsyncSession],
) -> FakeClaudeRunner:
    """``fake_claude`` whose tool calls hit the real MCP route on the test DB."""
    fake_claude.mcp_client = client
    return fake_claude
