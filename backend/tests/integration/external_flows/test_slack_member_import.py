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

"""Unlinking a Slack member, and importing workspace members as new members."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.repositories.user import UserRepository
from tests.fakes.seed import Factory, auth_headers, seed_member, seed_org
from tests.fakes.slack import FakeSlack
from tests.integration.external_flows.slack_support import (
    PHOTO,
    SLACK_SETTINGS,
    link_slack,
    member_row,
    slack_user_id,
    with_photo,
)

pytestmark = pytest.mark.integration


async def test_unlinking_clears_the_slack_id_and_unknown_ids_are_404(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org = await seed_org(app_sessions, slack=slack)
    ana, ana_slack = await seed_member(app_sessions, org.org_id, "ana"), slack_user_id()
    await link_slack(app_sessions, ana, ana_slack)
    headers = auth_headers(org.owner_id, org.org_id)

    gone = await client.post(
        f"{SLACK_SETTINGS}/unlink-member", json={"slack_id": ana_slack}, headers=headers
    )
    again = await client.post(
        f"{SLACK_SETTINGS}/unlink-member", json={"slack_id": ana_slack}, headers=headers
    )
    blank = await client.post(f"{SLACK_SETTINGS}/unlink-member", json={}, headers=headers)

    assert (gone.status_code, again.status_code, blank.status_code) == (200, 404, 400)
    assert (await member_row(app_sessions, ana)).slack_id is None
    assert slack.calls == []


async def test_import_creates_linked_members_and_skips_known_people(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org = await seed_org(app_sessions, slack=slack)
    known = await seed_member(app_sessions, org.org_id, "known")
    known_email = (await member_row(app_sessions, known)).email
    taken = slack_user_id()
    await link_slack(app_sessions, org.owner_id, taken)
    zed, zed_email = slack_user_id(), f"zed-{uuid.uuid4().hex[:6]}@acme.dev"
    slack.add_user(zed, "Zed", zed_email)
    with_photo(slack, zed)
    imports = [
        {"slack_id": zed, "slack_name": "Zed Newcomer", "slack_email": zed_email},
        {"slack_id": slack_user_id(), "slack_name": "Known", "slack_email": known_email},
        {"slack_id": taken, "slack_name": "Owner Twin", "slack_email": "twin@acme.dev"},
    ]

    resp = await client.post(
        f"{SLACK_SETTINGS}/import-members",
        json={"imports": imports},
        headers=auth_headers(org.owner_id, org.org_id),
    )

    assert resp.json() == {"imported": 1, "skipped": [known_email, "twin@acme.dev"]}
    async with app_sessions() as db:
        created = await UserRepository(db, org_id=org.org_id).get_by_email_in_org(
            org.org_id, zed_email
        )
    assert created is not None
    assert (created.name, created.slack_id, created.avatar_url) == ("Zed Newcomer", zed, PHOTO)
