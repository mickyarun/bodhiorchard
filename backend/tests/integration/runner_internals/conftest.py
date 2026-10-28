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

"""Fakes and a real job runtime for the agent runner tests on Postgres."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from app.api.v1 import settings_claude
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.fixtures import (
    event_recorder,
    external_guard,
    fake_claude,
    fake_embeddings,
    fake_github,
    git_repo,
    git_repo_factory,
    http_router,
)
from tests.fakes.fixtures_db import app_sessions, mcp_claude
from tests.fakes.seed import Factory
from tests.integration.runner_internals.runtime_support import JobRuntime
from tests.integration.runner_internals.stage_support import ESTIMATE_MARKER
from tests.services.runner_internals.log_tap import CRED_VARS, CREDENTIAL_PATH, LogTap

__all__ = [
    "app_sessions",
    "cred_tap",
    "event_recorder",
    "external_guard",
    "fake_claude",
    "fake_embeddings",
    "fake_github",
    "git_repo",
    "git_repo_factory",
    "http_router",
    "job_runtime",
    "mcp_claude",
    "stage_claude",
]

# What the estimator's follow-up agent run answers in these tests. Every
# stage that writes content re-estimates the BUD with one more agent run.
ESTIMATE_REPLY = '{"complexity": 2, "phases": {}}'


@pytest.fixture
def stage_claude(mcp_claude: FakeClaudeRunner, app_sessions: Factory) -> FakeClaudeRunner:
    """``mcp_claude`` that also answers the estimator's follow-up runs."""
    mcp_claude.when(ESTIMATE_MARKER, AgentScript.ok(ESTIMATE_REPLY))
    return mcp_claude


@pytest.fixture
def cred_tap(monkeypatch: pytest.MonkeyPatch) -> LogTap:
    """Unset the credential env vars (restored after) and tap the credential-path loggers."""
    for var in CRED_VARS:
        # setenv first so teardown restores (or removes) the var even when the
        # code under test sets it directly in ``os.environ``.
        monkeypatch.setenv(var, "placeholder")
        monkeypatch.delenv(var)
    tap = LogTap()
    tap.install(monkeypatch, *CREDENTIAL_PATH, settings_claude)
    return tap


@pytest_asyncio.fixture
async def job_runtime(
    monkeypatch: pytest.MonkeyPatch, app_sessions: Factory
) -> AsyncIterator[JobRuntime]:
    """Real workers for the agent job types, stopped at teardown."""
    runtime = JobRuntime(monkeypatch)
    await runtime.start()
    try:
        yield runtime
    finally:
        await runtime.stop()
