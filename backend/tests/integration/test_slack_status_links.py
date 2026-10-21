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

"""Slack status links on real Postgres: who's still a member, and one org per account."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import delete, update

from app.core.encryption import encrypt_secret
from app.models.user import OrgToUser, User
from app.repositories.slack_status_link import SlackStatusLinkRepository
from app.services.leave.slack_status import oauth
from app.services.leave.slack_status.settings import StatusClient
from app.services.slack_user_api import UserGrant
from tests.integration.leave_support import Factory, setup_org

pytestmark = pytest.mark.integration

CLIENT = StatusClient(enabled=True, client_id="1.2", client_secret="s")


async def _link(factory: Factory, org: uuid.UUID, user: uuid.UUID, slack: str, token: str) -> None:
    async with factory() as db:
        await SlackStatusLinkRepository(db, org_id=org).save(
            user, "T1", slack, encrypt_secret(token)
        )
        await db.commit()


async def test_people_who_left_are_departed_not_current(pg_session_factory: Factory) -> None:
    org, (ann, bob, cat), _ = await setup_org(pg_session_factory, "ann", "bob", "cat")
    for user, slack in ((ann, "UA"), (bob, "UB"), (cat, "UC")):
        await _link(pg_session_factory, org, user, slack, f"xoxp-{slack}")
    async with pg_session_factory() as db:
        # Bob is removed from the org; Cat's account is deactivated.
        await db.execute(
            delete(OrgToUser).where(OrgToUser.org_id == org, OrgToUser.user_id == bob)
        )
        await db.execute(update(User).where(User.id == cat).values(is_active=False))
        await db.commit()
    async with pg_session_factory() as db:
        links = SlackStatusLinkRepository(db, org_id=org)
        assert [link.user_id for link in await links.all_links()] == [ann]
        assert {link.user_id for link in await links.departed_links()} == {bob, cat}


@pytest.mark.parametrize("same_app", [False, True])
async def test_connecting_in_a_second_org_takes_the_account_over(
    pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch, same_app: bool
) -> None:
    org_a, (ravi,), _ = await setup_org(pg_session_factory, "ravi")
    org_b, _, _ = await setup_org(pg_session_factory)
    # The test DB is shared: a fresh Slack id keeps other tests' links out.
    slack_id = f"U{uuid.uuid4().hex[:8].upper()}"
    async with pg_session_factory() as db:
        db.add(OrgToUser(user_id=ravi, org_id=org_b))
        await db.execute(update(User).where(User.id == ravi).values(slack_id=slack_id))
        await db.commit()
    await _link(pg_session_factory, org_a, ravi, slack_id, "xoxp-old")
    new_token = "xoxp-old" if same_app else "xoxp-new"

    async def exchange(*_args: Any) -> UserGrant:
        # A different workspace of the same enterprise: still the same account.
        return UserGrant(slack_user_id=slack_id, token=new_token, team_id="T2")

    monkeypatch.setattr(oauth, "exchange_code", exchange)
    async with pg_session_factory() as db:
        connected = await oauth.complete(db, CLIENT, org_b, ravi, "code")
        await db.commit()

    assert connected.moved is True
    async with pg_session_factory() as db:
        assert await SlackStatusLinkRepository(db, org_id=org_a).for_user(ravi) is None
        assert await SlackStatusLinkRepository(db, org_id=org_b).for_user(ravi) is not None
    # Handed back only after the commit, and never the token we're keeping
    # (two orgs on one Slack app get the same one).
    assert connected.stale_tokens == ([] if same_app else ["xoxp-old"])
