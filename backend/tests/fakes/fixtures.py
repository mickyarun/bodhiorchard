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

"""Pytest fixtures for the fakes. Re-export them from a directory's conftest.

``external_guard`` is autouse wherever it is re-exported: from then on no
test in that directory can reach the network, the dev database or Redis,
or spawn a real agent CLI, without failing. ``fake_embeddings`` is autouse
too, because the real embedding model is a network download. The other
fixtures are opt-in.
The database-bound fixtures live in :mod:`tests.fakes.fixtures_db`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
import pytest_asyncio

from app.services import github_app_auth
from tests.fakes.app_state import (
    EventRecorder,
    disable_redis,
    drain_tasks_started_since,
    isolate_data_dir,
)
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.embeddings import FakeEmbedder
from tests.fakes.git_repo import DEFAULT_AUTHOR_EMAIL, LocalGitRepo, build_git_repo
from tests.fakes.github import API_HOST as GITHUB_HOST
from tests.fakes.github import FakeGitHub
from tests.fakes.guard import ExternalCallGuard
from tests.fakes.http_router import FakeHttpRouter
from tests.fakes.jira import FakeJira
from tests.fakes.slack import API_HOST as SLACK_HOST
from tests.fakes.slack import FakeSlack


@pytest_asyncio.fixture(autouse=True)
async def external_guard(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[ExternalCallGuard]:
    """Refuse real network, dev DB / Redis and agent CLIs; fail the test if tried.

    Background tasks the test started (audit writes, event-bus transports,
    slug back-fills) are awaited, then cancelled, before the patches come
    off, so they cannot reach the outside world unguarded after the test.
    """
    guard = ExternalCallGuard()
    guard.install(monkeypatch)
    disable_redis(monkeypatch)
    before = asyncio.all_tasks()
    yield guard
    await drain_tasks_started_since(before)
    guard.assert_clean()


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> FakeEmbedder:
    """Hash-seeded 384-d vectors in place of the downloaded fastembed model."""
    embedder = FakeEmbedder()
    embedder.install(monkeypatch)
    return embedder


@pytest.fixture
def http_router(
    external_guard: ExternalCallGuard, monkeypatch: pytest.MonkeyPatch
) -> FakeHttpRouter:
    """Default transport for every new httpx client; mount fakes on it."""
    router = FakeHttpRouter(external_guard)
    router.install(monkeypatch)
    return router


@pytest.fixture
def fake_github(http_router: FakeHttpRouter, monkeypatch: pytest.MonkeyPatch) -> FakeGitHub:
    """An in-memory api.github.com with one App installation."""
    github = FakeGitHub()
    http_router.mount(GITHUB_HOST, github.handle)
    monkeypatch.setattr(github_app_auth, "_token_cache", {})
    return github


@pytest.fixture
def fake_slack(http_router: FakeHttpRouter) -> FakeSlack:
    """An in-memory slack.com/api for one workspace."""
    slack = FakeSlack()
    http_router.mount(SLACK_HOST, slack.handle)
    return slack


@pytest.fixture
def fake_jira(http_router: FakeHttpRouter) -> FakeJira:
    """An in-memory Jira Cloud site on ``*.atlassian.net``."""
    jira = FakeJira()
    http_router.mount("*.atlassian.net", jira.handle)
    return jira


@pytest.fixture
def fake_claude(
    external_guard: ExternalCallGuard, monkeypatch: pytest.MonkeyPatch
) -> Iterator[FakeClaudeRunner]:
    """Scripted ``claude`` CLI; fails the test if a run had no script."""
    runner = FakeClaudeRunner()
    runner.install(monkeypatch)
    yield runner
    runner.assert_all_scripted()


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private ``settings.storage.data_dir`` (clones, scan worktrees, uploads)."""
    return isolate_data_dir(monkeypatch, tmp_path / "data")


@pytest.fixture
def git_repo_factory(tmp_path: Path) -> Callable[..., LocalGitRepo]:
    """Build more local repos: ``git_repo_factory("billing-api", author_email=...)``."""

    def build(
        name: str = "shop-api",
        files: dict[str, str] | None = None,
        author_email: str = DEFAULT_AUTHOR_EMAIL,
    ) -> LocalGitRepo:
        return build_git_repo(tmp_path / "repos", name, files, author_email)

    return build


@pytest.fixture
def git_repo(git_repo_factory: Callable[..., LocalGitRepo]) -> LocalGitRepo:
    """A clone of a small multi-module service with a bare local origin."""
    return git_repo_factory()


@pytest.fixture
def event_recorder(monkeypatch: pytest.MonkeyPatch) -> EventRecorder:
    """Records every ``event_bus.publish`` made during the test."""
    recorder = EventRecorder()
    recorder.install(monkeypatch)
    return recorder
