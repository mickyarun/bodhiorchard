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

"""Two approval reactions on the same Slack bug report land at once.

Each reaction is handled in its own transaction. Both used to read the
session as still waiting, so the slower one either filed a second bug or
failed on the bug-number unique key.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bug import Bug
from app.models.organization import Organization
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import OrgToUser, User
from app.repositories.role import RoleRepository
from app.services import bug_linker, slack_bug_intake, slack_intake
from app.services.slack_intake import handle_pm_approval

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]
SUMMARY_TS = "7.3"


@pytest.fixture(autouse=True)
def _fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    """No Slack and no linker; the session and bug rows are real."""

    async def _post(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"ok": True}

    async def _no_link(*args: Any) -> None:
        return None

    slack = SimpleNamespace(chat_post_message=_post)
    monkeypatch.setattr(slack_intake, "slack_client", slack)
    monkeypatch.setattr(slack_bug_intake, "slack_client", slack)
    monkeypatch.setattr(bug_linker, "embed_and_link_bug", _no_link)


async def _bug_report_awaiting_approval(factory: Factory) -> tuple[uuid.UUID, str]:
    """An org, a PM with a Slack id, and a bug session awaiting approval."""
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
                org_id=org.id, slack_channel="C1", thread_ts="7.1", original_msg_ts="7.2",
                summary_msg_ts=SUMMARY_TS, requester_slack_id="UREQ", session_type="bug",
                status=TriageStatus.AWAITING_PM,
                triage_context={"title": "Export fails", "severity": "high"},
            )
        )  # fmt: skip
        await db.commit()
        return org.id, slack_id


async def _react(factory: Factory, org_id: uuid.UUID, pm: str) -> str:
    """Handle one ✅ in its own transaction; returns "ok" or the error type."""
    try:
        async with factory() as db:
            org = await db.get(Organization, org_id)
            assert org is not None
            await handle_pm_approval(db, org, "xoxb", "C1", SUMMARY_TS, pm, approved=True)
            await db.commit()
        return "ok"
    except Exception as exc:  # the race surfaced as a database error before the fix
        return type(exc).__name__


async def test_a_double_approval_files_exactly_one_bug(pg_session_factory: Factory) -> None:
    org_id, pm = await _bug_report_awaiting_approval(pg_session_factory)

    outcomes = await asyncio.gather(
        _react(pg_session_factory, org_id, pm), _react(pg_session_factory, org_id, pm)
    )

    async with pg_session_factory() as db:
        bugs = await db.scalar(select(func.count()).select_from(Bug).where(Bug.org_id == org_id))
        session = (
            await db.scalars(select(TriageSession).where(TriageSession.org_id == org_id))
        ).one()
    assert outcomes == ["ok", "ok"]
    assert bugs == 1
    assert session.status == TriageStatus.BUD_CREATED
