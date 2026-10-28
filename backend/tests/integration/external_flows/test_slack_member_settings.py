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

"""Matching, linking and importing Slack workspace members against the fake workspace."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

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


async def test_sync_matches_by_email_and_name_and_skips_bots_and_deleted_users(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org = await seed_org(app_sessions, slack=slack)
    by_email = await seed_member(app_sessions, org.org_id, "ana")
    by_name = await seed_member(app_sessions, org.org_id, "Carol Danvers")
    linked = await seed_member(app_sessions, org.org_id, "dev")
    await link_slack(app_sessions, linked, "ULINKED01")
    ana_email = (await member_row(app_sessions, by_email)).email
    slack.add_user("UANA00001", "Ana Lopez", ana_email.upper())
    slack.add_user("UCAROL001", "Carol D", None)
    slack.add_user("ULINKED01", "Dev One", "dev@elsewhere.dev")
    slack.add_user("UNEW00001", "Zed Newcomer", "zed@acme.dev")
    slack.add_user("UGONE0001", "Gone Person", "gone@acme.dev", deleted=True)
    slack.add_user("UBOT00001", "Deploy Bot", None, is_bot=True)
    slack.add_user("USLACKBOT", "Slackbot", None)

    resp = await client.post(
        f"{SLACK_SETTINGS}/sync-members", headers=auth_headers(org.owner_id, org.org_id)
    )

    assert resp.status_code == 200
    rows = [(m["slack_id"], m["matched_user_id"], m["already_linked"]) for m in resp.json()]
    assert rows == [
        ("UANA00001", str(by_email), False),
        ("UCAROL001", str(by_name), False),
        ("UNEW00001", None, False),
        ("ULINKED01", str(linked), True),
    ]
    assert [c.token for c in slack.calls_to("users.list")] == ["xoxb-fake-bot-token"]


async def test_sync_with_a_missing_scope_returns_an_empty_preview(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org = await seed_org(app_sessions, slack=slack)
    slack.add_user("UANA00001", "Ana Lopez", "ana@acme.dev")
    slack.fail("users.list", "missing_scope")

    resp = await client.post(
        f"{SLACK_SETTINGS}/sync-members", headers=auth_headers(org.owner_id, org.org_id)
    )

    # Slack's refusal is logged, not surfaced: the admin sees nobody to match.
    assert (resp.status_code, resp.json()) == (200, [])
    assert [c.method for c in slack.calls] == ["users.list"]
    assert slack.faults.faults == []


async def test_sync_needs_a_bot_token(client: AsyncClient, app_sessions: Factory) -> None:
    org = await seed_org(app_sessions)

    resp = await client.post(
        f"{SLACK_SETTINGS}/sync-members", headers=auth_headers(org.owner_id, org.org_id)
    )

    assert (resp.status_code, resp.json()["detail"]) == (400, "Slack bot token not configured.")


async def test_linking_sets_slack_ids_and_adopts_the_slack_photo(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org = await seed_org(app_sessions, slack=slack)
    other_org = await seed_org(app_sessions)
    ana = await seed_member(app_sessions, org.org_id, "ana")
    ben = await seed_member(app_sessions, org.org_id, "ben")
    outsider = await seed_member(app_sessions, other_org.org_id, "outsider")
    ana_slack, ben_slack = slack_user_id(), slack_user_id()
    slack.add_user(ana_slack, "Ana", None)
    slack.add_user(ben_slack, "Ben", None)
    with_photo(slack, ana_slack)
    links = [
        {"slack_id": ana_slack, "user_id": str(ana)},
        {"slack_id": ben_slack, "user_id": str(ben)},
        {"slack_id": slack_user_id(), "user_id": str(outsider)},
        {"slack_id": slack_user_id(), "user_id": "not-a-uuid"},
    ]

    resp = await client.post(
        f"{SLACK_SETTINGS}/link-members",
        json={"links": links},
        headers=auth_headers(org.owner_id, org.org_id),
    )

    assert resp.json() == {"linked": 2, "avatars": 1}
    linked = await member_row(app_sessions, ana)
    assert (linked.slack_id, linked.avatar_url) == (ana_slack, PHOTO)
    assert (await member_row(app_sessions, ben)).avatar_url is None
    assert (await member_row(app_sessions, outsider)).slack_id is None


async def test_a_rate_limited_photo_lookup_still_saves_the_links(
    client: AsyncClient, app_sessions: Factory, slack: FakeSlack
) -> None:
    org = await seed_org(app_sessions, slack=slack)
    ana, ana_slack = await seed_member(app_sessions, org.org_id, "ana"), slack_user_id()
    slack.add_user(ana_slack, "Ana", None)
    with_photo(slack, ana_slack)
    slack.rate_limit("users.list")

    resp = await client.post(
        f"{SLACK_SETTINGS}/link-members",
        json={"links": [{"slack_id": ana_slack, "user_id": str(ana)}]},
        headers=auth_headers(org.owner_id, org.org_id),
    )

    assert resp.json() == {"linked": 1, "avatars": 0}
    assert len(slack.calls_to("users.list")) == 1
    assert slack.faults.faults == []
    member = await member_row(app_sessions, ana)
    assert (member.slack_id, member.avatar_url) == (ana_slack, None)
