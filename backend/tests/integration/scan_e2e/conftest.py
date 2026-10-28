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

"""End-to-end scans: real git, real indexer, real Postgres, scripted agent."""

import uuid
from collections.abc import Callable

import pytest

from tests.fakes.fixtures import (
    data_dir,
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
from tests.fakes.git_repo import LocalGitRepo

__all__ = [
    "app_sessions",
    "data_dir",
    "event_recorder",
    "external_guard",
    "fake_claude",
    "fake_embeddings",
    "fake_github",
    "git_repo",
    "git_repo_factory",
    "http_router",
    "mcp_claude",
    "shop_repo",
]


@pytest.fixture
def shop_repo(git_repo_factory: Callable[..., LocalGitRepo]) -> LocalGitRepo:
    """The sample service, committed by an author no other test's org has seen."""
    return git_repo_factory("shop-api", author_email=f"dev-{uuid.uuid4().hex[:10]}@example.test")
