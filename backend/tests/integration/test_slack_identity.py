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

"""Slack links say who clicks Approve, so changing them is guarded."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.models.organization import Organization
from app.models.user import User
from app.repositories.leave_digest_post import LeaveDigestPostRepository
from app.repositories.user import UserRepository
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration
LINK = "/api/v1/settings/slack/link-members"


async def _link(
    client: AsyncClient, org: uuid.UUID, actor: uuid.UUID, user: uuid.UUID, sid: str
) -> int:
    body = {"links": [{"slack_id": sid, "user_id": str(user)}]}
    return (await client.post(LINK, json=body, headers=as_user(actor, org))).status_code


async def test_an_admin_cannot_take_over_hr_slack_link(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (admin, hr, dev, owner), _ = await setup_org(
        pg_session_factory, "Admin", "Hr", "Dev", "Own"
    )
    await give_role(pg_session_factory, org, admin, "admin")
    await give_role(pg_session_factory, org, hr, "hr")
    await give_role(pg_session_factory, org, dev, "developer")
    await give_role(pg_session_factory, org, owner, "org_owner")
    assert await _link(client, org, admin, hr, "UADMIN") == 403
    assert await _link(client, org, admin, dev, "UDEV") == 200
    assert await _link(client, org, owner, hr, "UHR") == 200


async def test_one_slack_account_links_to_one_member(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (owner, a, b), _ = await setup_org(pg_session_factory, "Own", "A", "B")
    await give_role(pg_session_factory, org, owner, "org_owner")
    assert await _link(client, org, owner, a, "USAME") == 200
    assert await _link(client, org, owner, b, "USAME") == 409


async def test_ambiguous_slack_ids_match_nobody(pg_session_factory: Factory) -> None:
    org, (a, b), _ = await setup_org(pg_session_factory, "A", "B")
    async with pg_session_factory() as db:
        for user_id in (a, b):
            user = await db.get(User, user_id)
            assert user is not None
            user.slack_id = "UDUP"  # old data from before the uniqueness check
        await db.commit()
        assert await UserRepository(db).get_by_slack_id_with_role(org, "UDUP") is None


async def test_a_workspace_belongs_to_one_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    first, (owner1,), _ = await setup_org(pg_session_factory, "Own1")
    second, (owner2,), _ = await setup_org(pg_session_factory, "Own2")
    await give_role(pg_session_factory, first, owner1, "org_owner")
    await give_role(pg_session_factory, second, owner2, "org_owner")
    team = f"T{uuid.uuid4().hex[:8]}"
    async with pg_session_factory() as db:
        org = await db.get(Organization, first)
        assert org is not None
        org.slack_team_id = team
        await db.commit()
    body = {"slack": {"teamId": team}}
    url = "/api/v1/settings/connections"
    response = await client.patch(url, json=body, headers=as_user(owner2, second))
    assert response.status_code == 409, response.text


async def test_an_abandoned_daily_claim_is_retried(pg_session_factory: Factory) -> None:
    org, _, _ = await setup_org(pg_session_factory, "A")
    day = date(2026, 10, 19)
    async with pg_session_factory() as db:
        posts = LeaveDigestPostRepository(db, org_id=org)
        assert await posts.claim(day) is True
        await db.commit()
        assert await posts.claim(day) is False  # fresh claim still in progress
        await db.execute(
            text(
                "update leave_digest_posts set updated_at = now() - interval '10 minutes' "
                "where org_id = :org"
            ),
            {"org": org},
        )
        assert await posts.claim(day) is True
