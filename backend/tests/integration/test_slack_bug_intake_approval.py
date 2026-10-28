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

"""Approving a Slack bug report turns the triage summary into a linked bug.

Only PMs, admins and owners of the session's own org may approve; Slack and
the embedding model are faked, the rows are real.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from app.models.bug import Bug, BugSeverity
from app.models.organization import Organization
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import User
from app.services import bug_linker, slack_bug_intake
from app.services.slack_bug_intake import handle_bug_approval
from tests.integration.scan_features_bugs_support import Factory, new_bud, new_member, new_org, vec

pytestmark = pytest.mark.integration

SUMMARY_TS = "222.333"
CONTEXT = {
    "title": "Export button 500s",
    "description": "CSV export fails for large teams",
    "severity": "high",
    "module": "reports",
}


@pytest.fixture
def slack(monkeypatch: pytest.MonkeyPatch) -> list[str]:
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


async def _member_with_slack(factory: Factory, org: uuid.UUID, role: str) -> str:
    """A member holding ``role`` and a Slack id; returns the Slack id."""
    user_id = await new_member(factory, org, role)
    slack_id = f"U{uuid.uuid4().hex[:10].upper()}"
    async with factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.slack_id = slack_id
        await db.commit()
    return slack_id


async def _session(
    factory: Factory, org: uuid.UUID, *, kind: str = "bug", ctx: dict[str, str] | None = None
) -> uuid.UUID:
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


async def _decide(factory: Factory, org: uuid.UUID, approver: str, approved: bool) -> None:
    async with factory() as db:
        org_row = await db.get(Organization, org)
        assert org_row is not None
        await handle_bug_approval(db, org_row, "xoxb", "C9", SUMMARY_TS, approver, approved)
        await db.commit()


async def _state(factory: Factory, org: uuid.UUID, sid: uuid.UUID) -> tuple[list[Bug], str]:
    async with factory() as db:
        bugs = list((await db.scalars(select(Bug).where(Bug.org_id == org))).all())
        session = await db.get(TriageSession, sid)
        assert session is not None
        return bugs, session.status


async def test_a_pm_approval_files_the_bug_and_links_the_closest_bud(
    pg_session_factory: Factory, slack: list[str]
) -> None:
    org = await new_org(pg_session_factory)
    bud = await new_bud(pg_session_factory, org, 3, embedding=vec(1))
    pm = await _member_with_slack(pg_session_factory, org, "pm")
    sid = await _session(pg_session_factory, org)

    await _decide(pg_session_factory, org, pm, approved=True)

    bugs, status = await _state(pg_session_factory, org, sid)
    assert status == TriageStatus.BUD_CREATED
    assert len(bugs) == 1
    bug = bugs[0]
    assert (bug.title, bug.description, bug.module) == (
        "Export button 500s", "CSV export fails for large teams", "reports"
    )  # fmt: skip
    assert bug.severity == BugSeverity.HIGH and bug.bud_id == bud and bug.bug_number == 1
    assert slack[-1].startswith("✅ Bug created: *Export button 500s*")
    assert "BUD-003" in slack[-1]


async def test_a_bare_summary_falls_back_to_the_original_message(
    pg_session_factory: Factory, slack: list[str]
) -> None:
    org = await new_org(pg_session_factory)
    pm = await _member_with_slack(pg_session_factory, org, "admin")
    sid = await _session(pg_session_factory, org, ctx={})

    await _decide(pg_session_factory, org, pm, approved=True)

    bugs, _ = await _state(pg_session_factory, org, sid)
    assert [(b.title, b.description, b.severity) for b in bugs] == [
        ("Export", "export is broken", BugSeverity.MEDIUM)
    ]
    assert bugs[0].bud_id is None
    assert "Linked to" not in slack[-1]


@pytest.mark.parametrize("who", ["developer", "unknown", "other-org-pm"])
async def test_only_a_pm_of_this_org_can_approve(
    pg_session_factory: Factory, slack: list[str], who: str
) -> None:
    org = await new_org(pg_session_factory)
    sid = await _session(pg_session_factory, org)
    if who == "developer":
        approver = await _member_with_slack(pg_session_factory, org, "developer")
    elif who == "unknown":
        approver = "UNOBODY"
    else:
        approver = await _member_with_slack(
            pg_session_factory, await new_org(pg_session_factory), "pm"
        )

    await _decide(pg_session_factory, org, approver, approved=True)

    bugs, status = await _state(pg_session_factory, org, sid)
    assert bugs == [] and status == TriageStatus.AWAITING_PM
    assert slack[-1].startswith("⚠️")


async def test_rejecting_discards_the_report(
    pg_session_factory: Factory, slack: list[str]
) -> None:
    org = await new_org(pg_session_factory)
    sid = await _session(pg_session_factory, org)

    await _decide(pg_session_factory, org, "UANYONE", approved=False)

    bugs, status = await _state(pg_session_factory, org, sid)
    assert bugs == [] and status == TriageStatus.REJECTED
    assert slack == ["❌ Bug report discarded."]


async def test_feature_requests_and_decided_sessions_are_left_alone(
    pg_session_factory: Factory, slack: list[str]
) -> None:
    org = await new_org(pg_session_factory)
    pm = await _member_with_slack(pg_session_factory, org, "pm")
    feature_sid = await _session(pg_session_factory, org, kind="bud")

    await _decide(pg_session_factory, org, pm, approved=True)
    _, feature_status = await _state(pg_session_factory, org, feature_sid)

    other = await new_org(pg_session_factory)
    bug_sid = await _session(pg_session_factory, other)
    other_pm = await _member_with_slack(pg_session_factory, other, "pm")
    await _decide(pg_session_factory, other, other_pm, approved=False)
    await _decide(pg_session_factory, other, other_pm, approved=True)
    bugs, bug_status = await _state(pg_session_factory, other, bug_sid)

    assert feature_status == TriageStatus.AWAITING_PM
    assert bugs == [] and bug_status == TriageStatus.REJECTED
    assert slack == ["❌ Bug report discarded."]
