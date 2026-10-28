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

"""A Jira import when the site refuses or throttles the search, and starting it again."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.fakes.jira import FakeJira
from tests.fakes.seed import Factory
from tests.integration.external_flows.jira_support import (
    connected_org,
    discover,
    review_items,
    seed_backlog,
    start_import,
)
from tests.integration.external_flows.jobs_support import InlineJobs

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def test_a_revoked_token_fails_the_import_with_the_reason(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira, jira_jobs: InlineJobs
) -> None:
    seed_backlog(fake_jira)
    org = await connected_org(client, app_sessions, fake_jira)
    found = await discover(client, org, jira_jobs, "PAY")
    fake_jira.fail(r"/search/jql$", 401)

    done = await start_import(client, org, jira_jobs, found["id"])

    assert done["status"] == "failed"
    assert "returned 401" in done["error"]
    assert fake_jira.faults.faults == []
    assert await review_items(client, org, found["id"]) == {}
    (job_type, job_id) = jira_jobs.ran[-1]
    assert jira_jobs.status(job_id).state.value == "failed"


async def test_a_rate_limited_page_is_retried_once_and_the_import_completes(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira, jira_jobs: InlineJobs
) -> None:
    seed_backlog(fake_jira)
    org = await connected_org(client, app_sessions, fake_jira)
    found = await discover(client, org, jira_jobs, "PAY")
    fake_jira.fail(r"/search/jql$", 429)
    before = len(fake_jira.requests)

    done = await start_import(client, org, jira_jobs, found["id"], consolidationMode="flat")

    assert done["status"] == "completed"
    assert len(done["result"]["reviewNeeded"]) == 4
    assert fake_jira.faults.faults == []
    # Two pages, plus the one retry of the throttled first page.
    searches = [r for r in fake_jira.requests[before:] if r.url.path.endswith("/search/jql")]
    assert len(searches) == 3


async def test_a_failed_import_can_be_started_again(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira, jira_jobs: InlineJobs
) -> None:
    seed_backlog(fake_jira)
    org = await connected_org(client, app_sessions, fake_jira)
    found = await discover(client, org, jira_jobs, "PAY")
    fake_jira.fail(r"/search/jql$", 403)
    failed = await start_import(client, org, jira_jobs, found["id"], consolidationMode="flat")

    retried = await start_import(client, org, jira_jobs, found["id"], consolidationMode="flat")

    assert (failed["status"], retried["status"]) == ("failed", "completed")
    assert len(retried["result"]["reviewNeeded"]) == 4
