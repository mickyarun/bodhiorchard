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

"""Bulk onboarding refused at the route: nothing is queued and nothing is cloned."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.job_queue import JOB_REPO_BULK_ONBOARD
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import Factory, auth_headers, seed_org
from tests.integration.external_flows.bulk_onboard_support import (
    BULK_ONBOARD,
    ScanKickoffs,
    onboard_item,
)
from tests.integration.external_flows.github_support import set_installation, unique_name
from tests.integration.external_flows.jobs_support import InlineJobs

pytestmark = pytest.mark.integration


async def test_repos_outside_the_installation_are_refused_before_any_job(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub, onboarding: ScanKickoffs
) -> None:
    shop = f"acme/{unique_name('shop')}"
    gh.add_repo(shop)
    org = await seed_org(app_sessions, github=gh)
    items = [onboard_item(shop), onboard_item("other/secret")]

    resp = await client.post(
        BULK_ONBOARD, json={"items": items}, headers=auth_headers(org.owner_id, org.org_id)
    )

    assert resp.status_code == 400
    assert "other/secret" in resp.json()["detail"]
    assert shop not in resp.json()["detail"]
    assert onboarding.calls == []


async def test_bulk_onboard_needs_the_app_installed(
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
    inline_jobs: InlineJobs,
    onboarding: ScanKickoffs,
) -> None:
    shop = f"acme/{unique_name('shop')}"
    gh.add_repo(shop)
    org = await seed_org(app_sessions, github=gh)
    await set_installation(app_sessions, org.org_id, None)

    resp = await client.post(
        BULK_ONBOARD,
        json={"items": [onboard_item(shop)]},
        headers=auth_headers(org.owner_id, org.org_id),
    )

    assert resp.status_code == 400
    assert inline_jobs.queued(JOB_REPO_BULK_ONBOARD) == 0
    assert gh.requests == []
