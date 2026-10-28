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

"""Fakes for the external-flow tests, plus inline job running.

``external_guard`` and ``fake_embeddings`` are autouse once re-exported, so
no test here can reach GitHub, Slack, Jira, the dev database or a real agent
CLI. The shared database outlives each test, so every test seeds its own org
and uses the ``gh`` / ``slack`` fixtures, which give the fakes a per-test App
id and Slack team (org lookups by either must match exactly one org).
"""

from __future__ import annotations

import uuid

import pytest

from app.services.jira_import_pipeline import handle_discovery_job, handle_import_job
from app.services.job_agents import handle_triage_job
from app.services.job_feature_qa import handle_feature_qa_job
from app.services.job_queue import JOB_FEATURE_QA, JOB_JIRA_DISCOVERY, JOB_JIRA_IMPORT, JOB_TRIAGE
from tests.fakes.fixtures import (
    data_dir,
    event_recorder,
    external_guard,
    fake_claude,
    fake_embeddings,
    fake_github,
    fake_jira,
    fake_slack,
    git_repo,
    git_repo_factory,
    http_router,
)
from tests.fakes.fixtures_db import app_sessions, mcp_claude
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import Factory
from tests.fakes.slack import FakeSlack
from tests.integration.external_flows.jobs_support import InlineJobs

__all__ = [
    "app_sessions",
    "data_dir",
    "event_recorder",
    "external_guard",
    "fake_claude",
    "fake_embeddings",
    "fake_github",
    "fake_jira",
    "fake_slack",
    "git_repo",
    "git_repo_factory",
    "gh",
    "http_router",
    "inline_jobs",
    "jira_jobs",
    "mcp_claude",
    "slack",
    "triage_jobs",
]


@pytest.fixture
def inline_jobs(monkeypatch: pytest.MonkeyPatch) -> InlineJobs:
    """Register real job handlers for this test and run them on demand."""
    return InlineJobs(monkeypatch)


@pytest.fixture
def triage_jobs(inline_jobs: InlineJobs) -> InlineJobs:
    """The Slack events route's two job types, with their real handlers."""
    inline_jobs.register(JOB_TRIAGE, handle_triage_job)
    inline_jobs.register(JOB_FEATURE_QA, handle_feature_qa_job)
    return inline_jobs


@pytest.fixture
def jira_jobs(inline_jobs: InlineJobs, app_sessions: Factory) -> InlineJobs:
    """The Jira discovery and import jobs, with their real handlers on the test DB."""
    inline_jobs.register(JOB_JIRA_DISCOVERY, handle_discovery_job)
    inline_jobs.register(JOB_JIRA_IMPORT, handle_import_job)
    return inline_jobs


@pytest.fixture
def gh(fake_github: FakeGitHub) -> FakeGitHub:
    """``fake_github`` with an App id no other org in the shared database uses."""
    fake_github.app_id = 100_000 + uuid.uuid4().int % 800_000
    return fake_github


@pytest.fixture
def slack(fake_slack: FakeSlack) -> FakeSlack:
    """``fake_slack`` with a team id no other org in the shared database uses."""
    fake_slack.team_id = f"T{uuid.uuid4().hex[:10].upper()}"
    return fake_slack
