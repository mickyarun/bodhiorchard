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

"""A Jira project imported end to end: discovery, a paginated import, review, re-import.

``JiraClient.search_issues`` pauses a second between pages, so each project
here spans two pages of the fake's page size of 2.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.bud import BUDStatus
from app.repositories.bud import BUDRepository
from tests.fakes.jira import FakeJira
from tests.fakes.seed import Factory
from tests.integration.external_flows.jira_support import (
    act,
    connected_org,
    discover,
    review_items,
    seed_backlog,
    start_import,
)
from tests.integration.external_flows.jobs_support import InlineJobs

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def test_discovery_counts_types_and_samples_across_pages(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira, jira_jobs: InlineJobs
) -> None:
    seed_backlog(fake_jira)
    org = await connected_org(client, app_sessions, fake_jira)

    found = await discover(client, org, jira_jobs, "PAY")

    assert (found["status"], found["totalIssues"]) == ("ready", 4)
    result = found["discoveryResult"]
    assert {t["issueType"]: t["count"] for t in result["byType"]} == {
        "Epic": 1,
        "Story": 2,
        "Bug": 1,
    }
    assert result["statusesFound"] == ["To Do", "In Progress", "Done"]
    assert [s["key"] for s in result["sampleIssues"]] == ["PAY-1", "PAY-2"]
    assert result["alreadyImportedCount"] == 0
    searches = [r for r in fake_jira.requests if r.url.path.endswith("/search/jql")]
    assert all('project = "PAY"' in r.url.params["jql"] for r in searches)
    assert any(r.url.params.get("nextPageToken") == "2" for r in searches)


async def test_an_import_groups_the_epic_and_queues_every_item_for_review(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira, jira_jobs: InlineJobs
) -> None:
    seed_backlog(fake_jira)
    org = await connected_org(client, app_sessions, fake_jira)
    found = await discover(client, org, jira_jobs, "PAY")

    done = await start_import(client, org, jira_jobs, found["id"], consolidationMode="epic")

    assert done["status"] == "completed"
    review = done["result"]["reviewNeeded"]
    assert [(r["jiraKey"], r["issueType"]) for r in review] == [
        ("PAY-1", "Epic"),
        ("PAY-3", "Story"),
        ("PAY-4", "Bug"),
    ]
    assert done["result"]["failed"] == []
    items = await review_items(client, org, found["id"])
    assert set(items) == {"PAY-1", "PAY-2", "PAY-3", "PAY-4"}
    assert items["PAY-2"]["note"] == "Child of PAY-1"


async def test_importing_a_review_item_creates_a_bud_with_the_mapped_fields(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira, jira_jobs: InlineJobs
) -> None:
    seed_backlog(fake_jira)
    org = await connected_org(client, app_sessions, fake_jira)
    found = await discover(client, org, jira_jobs, "PAY")
    await start_import(client, org, jira_jobs, found["id"], consolidationMode="flat")
    items = await review_items(client, org, found["id"])

    imported = await act(client, org, items["PAY-3"]["id"], "import")
    skipped = await act(client, org, items["PAY-2"]["id"], "skip")
    again = await act(client, org, items["PAY-3"]["id"], "import")

    assert (imported.json()["status"], skipped.json()["status"]) == ("imported", "skipped")
    assert again.status_code == 400
    async with app_sessions() as db:
        bud = await BUDRepository(db, org_id=org.org_id).get_by_id(
            uuid.UUID(imported.json()["budId"])
        )
    assert bud is not None
    assert (bud.title, bud.status) == ("Export statements", BUDStatus.BUD)
    assert "Monthly" in (bud.requirements_md or "") and "CSV" in (bud.requirements_md or "")
    meta = bud.metadata_ or {}
    assert (meta["jira_key"], meta["jira_priority"], meta["jira_labels"]) == (
        "PAY-3",
        "High",
        ["finance"],
    )
    remaining = await review_items(client, org, found["id"])
    assert "PAY-3" not in remaining and "PAY-2" not in remaining


async def test_a_reimport_skips_issues_already_imported(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira, jira_jobs: InlineJobs
) -> None:
    seed_backlog(fake_jira)
    org = await connected_org(client, app_sessions, fake_jira)
    first = await discover(client, org, jira_jobs, "PAY")
    await start_import(client, org, jira_jobs, first["id"], consolidationMode="flat")
    items = await review_items(client, org, first["id"])
    await act(client, org, items["PAY-3"]["id"], "import")

    second = await discover(client, org, jira_jobs, "PAY")
    redone = await start_import(client, org, jira_jobs, second["id"], consolidationMode="flat")

    assert second["discoveryResult"]["alreadyImportedCount"] == 1
    keys = [r["jiraKey"] for r in redone["result"]["reviewNeeded"]]
    assert "PAY-3" not in keys
    assert set(keys) == {"PAY-1", "PAY-2", "PAY-4"}
    assert redone["result"]["skipped"]["exactDuplicates"] == 1


async def test_a_type_mapped_to_skip_never_reaches_review(
    client: AsyncClient, app_sessions: Factory, fake_jira: FakeJira, jira_jobs: InlineJobs
) -> None:
    seed_backlog(fake_jira)
    org = await connected_org(client, app_sessions, fake_jira)
    found = await discover(client, org, jira_jobs, "PAY")

    skip_bugs = [{"jiraType": "Bug", "target": "skip"}]
    done = await start_import(
        client, org, jira_jobs, found["id"], consolidationMode="flat", typeMappings=skip_bugs
    )

    assert done["status"] == "completed"
    assert sorted(r["jiraKey"] for r in done["result"]["reviewNeeded"]) == [
        "PAY-1",
        "PAY-2",
        "PAY-3",
    ]
    assert done["result"]["skipped"]["exactDuplicates"] == 0
    assert set(await review_items(client, org, found["id"])) == {"PAY-1", "PAY-2", "PAY-3"}
