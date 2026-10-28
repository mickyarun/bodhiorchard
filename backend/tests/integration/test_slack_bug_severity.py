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

"""A Slack bug report is filed whatever casing the triage agent used for severity.

The severity went straight from the agent's JSON into the enum column, so
``"High"`` (or anything off the list) failed the insert: no bug, the session
stuck waiting, and no reply in the thread.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bug import Bug, BugSeverity
from app.models.organization import Organization
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services import bug_linker, slack_bug_intake
from app.services.slack_bug_intake import handle_bug_approval

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


@pytest.fixture(autouse=True)
def linked(monkeypatch: pytest.MonkeyPatch) -> list[uuid.UUID]:
    """No Slack, and the linker replaced where the approval looks it up.

    Returns the ids of the bugs handed to the linker so a test can prove
    the replacement was the one actually called.
    """
    seen: list[uuid.UUID] = []

    async def _post(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    async def _record_link(db: Any, org_id: uuid.UUID, bug: Bug) -> None:
        seen.append(bug.id)

    monkeypatch.setattr(slack_bug_intake, "slack_client", SimpleNamespace(chat_post_message=_post))
    monkeypatch.setattr(bug_linker, "embed_and_link_bug", _record_link)
    return seen


async def _org_with_pm_and_report(factory: Factory, severity: object) -> tuple[uuid.UUID, str]:
    slack_id = f"U{uuid.uuid4().hex[:10]}"
    async with factory() as db:
        org = Organization(name=f"Org {uuid.uuid4()}", slug=f"o-{uuid.uuid4().hex[:10]}")
        pm = User(
            email=f"{uuid.uuid4().hex[:10]}@acme.dev", name="Pat", password_hash="x",
            slack_id=slack_id,
        )  # fmt: skip
        db.add_all([org, pm])
        await db.flush()
        role = await RoleRepository(db).get_by_name_system("pm")
        assert role is not None
        db.add(OrgToUser(user_id=pm.id, org_id=org.id, role_id=role.id))
        db.add(
            TriageSession(
                org_id=org.id, slack_channel="C1", thread_ts="1.1", original_msg_ts="1.2",
                summary_msg_ts="1.3", requester_slack_id="UREQ", session_type="bug",
                status=TriageStatus.AWAITING_PM,
                triage_context={"title": "Export fails", "severity": severity},
            )
        )  # fmt: skip
        await db.commit()
        return org.id, slack_id


@pytest.mark.parametrize(
    ("reported", "stored"),
    [
        ("High", BugSeverity.HIGH),
        ("  CRITICAL ", BugSeverity.CRITICAL),
        ("low", BugSeverity.LOW),
        ("P1", BugSeverity.MEDIUM),
        (None, BugSeverity.MEDIUM),
        (3, BugSeverity.MEDIUM),
    ],
)
async def test_the_bug_is_filed_with_a_known_severity(
    pg_session_factory: Factory, linked: list[uuid.UUID], reported: object, stored: BugSeverity
) -> None:
    org_id, pm = await _org_with_pm_and_report(pg_session_factory, reported)

    async with pg_session_factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        await handle_bug_approval(db, org, "xoxb", "C1", "1.3", pm, approved=True)
        await db.commit()

    async with pg_session_factory() as db:
        bugs = (await db.scalars(select(Bug).where(Bug.org_id == org_id))).all()
        session = (
            await db.scalars(select(TriageSession).where(TriageSession.org_id == org_id))
        ).one()
    assert [(b.title, b.severity) for b in bugs] == [("Export fails", stored)]
    assert linked == [bugs[0].id]
    assert session.status == TriageStatus.BUD_CREATED
