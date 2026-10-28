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

"""Only a PM or admin of the org may discard a Slack bug report.

The reject branch ran before the role check, so any Slack user, even one
who isn't a member, could discard a report with a ❌ reaction.
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
from app.services import slack_bug_intake
from app.services.slack_bug_intake import handle_bug_approval

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]
SUMMARY_TS = "9.3"


@pytest.fixture
def replies(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Thread replies the bot posted."""
    posts: list[str] = []

    async def _post(token: str, channel: str, text: str, **kwargs: Any) -> dict[str, Any]:
        posts.append(text)
        return {"ok": True}

    monkeypatch.setattr(slack_bug_intake, "slack_client", SimpleNamespace(chat_post_message=_post))
    return posts


async def _member(factory: Factory, org_id: uuid.UUID, role: str) -> str:
    slack_id = f"U{uuid.uuid4().hex[:10]}"
    async with factory() as db:
        user = User(
            email=f"{uuid.uuid4().hex[:10]}@acme.dev", name="Sam", password_hash="x",
            slack_id=slack_id,
        )  # fmt: skip
        db.add(user)
        await db.flush()
        found = await RoleRepository(db).get_by_name_system(role)
        assert found is not None
        db.add(OrgToUser(user_id=user.id, org_id=org_id, role_id=found.id))
        await db.commit()
    return slack_id


async def _report(factory: Factory) -> uuid.UUID:
    async with factory() as db:
        org = Organization(name=f"Org {uuid.uuid4()}", slug=f"o-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        db.add(
            TriageSession(
                org_id=org.id, slack_channel="C1", thread_ts="9.1", original_msg_ts="9.2",
                summary_msg_ts=SUMMARY_TS, requester_slack_id="UREQ", session_type="bug",
                status=TriageStatus.AWAITING_PM, triage_context={"title": "Export fails"},
            )
        )  # fmt: skip
        await db.commit()
        return org.id


async def _reject(factory: Factory, org_id: uuid.UUID, slack_id: str) -> str:
    """React ❌ as ``slack_id``; return the session status afterwards."""
    async with factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        await handle_bug_approval(db, org, "xoxb", "C1", SUMMARY_TS, slack_id, approved=False)
        await db.commit()
    async with factory() as db:
        session = (
            await db.scalars(select(TriageSession).where(TriageSession.org_id == org_id))
        ).one()
        return session.status


@pytest.mark.parametrize("who", ["non-member", "developer", "pm-of-another-org"])
async def test_someone_without_the_role_cannot_discard_a_report(
    pg_session_factory: Factory, replies: list[str], who: str
) -> None:
    org_id = await _report(pg_session_factory)
    if who == "non-member":
        reactor = "UOUTSIDER"
    elif who == "developer":
        reactor = await _member(pg_session_factory, org_id, "developer")
    else:
        other = await _report(pg_session_factory)
        reactor = await _member(pg_session_factory, other, "pm")

    status = await _reject(pg_session_factory, org_id, reactor)

    assert status == TriageStatus.AWAITING_PM
    assert len(replies) == 1 and replies[0].startswith("⚠️")


async def test_a_pm_still_discards_a_report(
    pg_session_factory: Factory, replies: list[str]
) -> None:
    org_id = await _report(pg_session_factory)
    pm = await _member(pg_session_factory, org_id, "pm")

    status = await _reject(pg_session_factory, org_id, pm)

    assert status == TriageStatus.REJECTED
    assert replies == ["❌ Bug report discarded."]
