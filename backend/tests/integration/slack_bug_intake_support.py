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

"""Sessions, members and Slack fakes for the Slack bug intake tests."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from app.models.bug import Bug
from app.models.organization import Organization
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import User
from app.services import bug_linker, slack_bug_intake
from app.services.slack_bug_intake import handle_bug_approval
from tests.integration.scan_features_bugs_support import Factory, new_member, vec

SUMMARY_TS = "222.333"
CONTEXT = {
    "title": "Export button 500s",
    "description": "CSV export fails for large teams",
    "severity": "high",
    "module": "reports",
}


def fake_slack(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record thread replies and give every bug the vector ``vec(1)``."""
    posts: list[str] = []

    async def _post(token: str, channel: str, text: str, **kw: Any) -> dict[str, Any]:
        posts.append(text)
        return {"ok": True}

    async def _embed(text: str) -> list[float]:
        return vec(1)

    monkeypatch.setattr(slack_bug_intake, "slack_client", SimpleNamespace(chat_post_message=_post))
    monkeypatch.setattr(bug_linker, "embedding_service", SimpleNamespace(embed=_embed))
    return posts


async def member_with_slack(factory: Factory, org: uuid.UUID, role: str) -> str:
    """A member holding ``role`` and a Slack id; returns the Slack id."""
    user_id = await new_member(factory, org, role)
    slack_id = f"U{uuid.uuid4().hex[:10].upper()}"
    async with factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.slack_id = slack_id
        await db.commit()
    return slack_id


async def bug_session(
    factory: Factory, org: uuid.UUID, *, kind: str = "bug", ctx: dict[str, str] | None = None
) -> uuid.UUID:
    """A triage session awaiting approval whose summary was posted at ``SUMMARY_TS``."""
    async with factory() as db:
        session = TriageSession(
            org_id=org,
            slack_channel="C9",
            thread_ts=f"{uuid.uuid4().int % 10**9}.1",
            original_msg_ts=f"{uuid.uuid4().int % 10**9}.2",
            summary_msg_ts=SUMMARY_TS,
            requester_slack_id="UREQ",
            original_text="export is broken",
            status=TriageStatus.AWAITING_PM,
            session_type=kind,
            feature_name="Export",
            triage_context=CONTEXT if ctx is None else ctx,
        )
        db.add(session)
        await db.commit()
        return session.id


async def decide(factory: Factory, org: uuid.UUID, approver: str, approved: bool) -> None:
    """``approver`` reacts to the summary with approve (True) or reject (False)."""
    async with factory() as db:
        org_row = await db.get(Organization, org)
        assert org_row is not None
        await handle_bug_approval(db, org_row, "xoxb", "C9", SUMMARY_TS, approver, approved)
        await db.commit()


async def state(factory: Factory, org: uuid.UUID, sid: uuid.UUID) -> tuple[list[Bug], str]:
    """The org's bugs and the session's status as stored."""
    async with factory() as db:
        bugs = list((await db.scalars(select(Bug).where(Bug.org_id == org))).all())
        session = await db.get(TriageSession, sid)
        assert session is not None
        return bugs, session.status
