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

"""Only a PM who may sign in, holding that role in this org, decides from Slack.

The ✅/❌ reactions on a bug report or a feature request checked the role
but not the account, so a deactivated PM, or one who has not yet replaced
a temporary password, could still file, discard, approve or decline. The
role must also be the one held in the org the reaction happened in.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.organization import Organization
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services import slack_bug_intake, slack_intake
from app.services.slack_intake import handle_pm_approval

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]
SUMMARY_TS = "9.3"
FLOWS = [("bug", True), ("bug", False), ("feature", True), ("feature", False)]


@pytest.fixture
def replies(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Thread replies the bot posted, from either intake flow."""
    posts: list[str] = []

    async def _post(token: str, channel: str, text: str, **kwargs: Any) -> dict[str, Any]:
        posts.append(text)
        return {"ok": True}

    fake = SimpleNamespace(chat_post_message=_post)
    monkeypatch.setattr(slack_bug_intake, "slack_client", fake)
    monkeypatch.setattr(slack_intake, "slack_client", fake)
    return posts


async def _org(factory: Factory, session_type: str | None = None) -> uuid.UUID:
    """An org, with a summary awaiting a PM when ``session_type`` is given."""
    async with factory() as db:
        org = Organization(name=f"Org {uuid.uuid4()}", slug=f"o-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        if session_type is not None:
            db.add(
                TriageSession(
                    org_id=org.id, slack_channel="C1", thread_ts="9.1", original_msg_ts="9.2",
                    summary_msg_ts=SUMMARY_TS, requester_slack_id="UREQ",
                    session_type=session_type, status=TriageStatus.AWAITING_PM,
                    feature_name="Export", triage_context={"title": "Export fails"},
                )
            )  # fmt: skip
        await db.commit()
        return org.id


async def _member(
    factory: Factory, roles: dict[uuid.UUID, str], *, active: bool = True, temp_pw: bool = False
) -> str:
    """A user holding ``roles[org]`` in each org; returns their Slack id."""
    slack_id = f"U{uuid.uuid4().hex[:10]}"
    async with factory() as db:
        user = User(
            email=f"{uuid.uuid4().hex[:10]}@acme.dev", name="Sam", password_hash="x",
            slack_id=slack_id, is_active=active, must_change_password=temp_pw,
        )  # fmt: skip
        db.add(user)
        await db.flush()
        for org_id, role_name in roles.items():
            role = await RoleRepository(db).get_by_name_system(role_name)
            assert role is not None
            db.add(OrgToUser(user_id=user.id, org_id=org_id, role_id=role.id))
        await db.commit()
    return slack_id


async def _react(factory: Factory, org_id: uuid.UUID, slack_id: str, approved: bool) -> str:
    """React ✅/❌ as ``slack_id``; return the session status afterwards."""
    async with factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        await handle_pm_approval(db, org, "xoxb", "C1", SUMMARY_TS, slack_id, approved)
        await db.commit()
    async with factory() as db:
        session = (
            await db.scalars(select(TriageSession).where(TriageSession.org_id == org_id))
        ).one()
        return session.status


@pytest.mark.parametrize(("flow", "approved"), FLOWS)
@pytest.mark.parametrize("account", ["deactivated", "temporary-password"])
async def test_a_pm_who_cannot_sign_in_is_refused(
    pg_session_factory: Factory, replies: list[str], flow: str, approved: bool, account: str
) -> None:
    org_id = await _org(pg_session_factory, flow)
    pm = await _member(
        pg_session_factory,
        {org_id: "pm"},
        active=account != "deactivated",
        temp_pw=account == "temporary-password",
    )

    status = await _react(pg_session_factory, org_id, pm, approved)

    assert status == TriageStatus.AWAITING_PM
    assert len(replies) == 1 and replies[0].startswith("⚠️")


@pytest.mark.parametrize(("flow", "approved"), FLOWS)
async def test_a_pm_role_held_in_another_org_does_not_count(
    pg_session_factory: Factory, replies: list[str], flow: str, approved: bool
) -> None:
    org_a = await _org(pg_session_factory, flow)
    org_b = await _org(pg_session_factory)
    reactor = await _member(pg_session_factory, {org_a: "developer", org_b: "pm"})

    status = await _react(pg_session_factory, org_a, reactor, approved)

    assert status == TriageStatus.AWAITING_PM
    assert len(replies) == 1 and replies[0].startswith("⚠️")


@pytest.mark.parametrize("flow", ["bug", "feature"])
async def test_an_active_pm_still_declines(
    pg_session_factory: Factory, replies: list[str], flow: str
) -> None:
    org_id = await _org(pg_session_factory, flow)
    pm = await _member(pg_session_factory, {org_id: "pm"})

    status = await _react(pg_session_factory, org_id, pm, approved=False)

    assert status == TriageStatus.REJECTED
    assert len(replies) == 1 and replies[0].startswith("❌")
