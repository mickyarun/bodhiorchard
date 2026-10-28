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

import pytest

from app.models.bug import BugSeverity
from app.models.triage_session import TriageStatus
from tests.integration.scan_features_bugs_support import Factory, new_bud, new_org, vec
from tests.integration.slack_bug_intake_support import (
    bug_session,
    decide,
    fake_slack,
    member_with_slack,
    state,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def slack(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Thread replies posted during the test."""
    return fake_slack(monkeypatch)


async def test_a_pm_approval_files_the_bug_and_links_the_closest_bud(
    pg_session_factory: Factory, slack: list[str]
) -> None:
    org = await new_org(pg_session_factory)
    bud = await new_bud(pg_session_factory, org, 3, embedding=vec(1))
    pm = await member_with_slack(pg_session_factory, org, "pm")
    sid = await bug_session(pg_session_factory, org)

    await decide(pg_session_factory, org, pm, approved=True)

    bugs, status = await state(pg_session_factory, org, sid)
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
    pm = await member_with_slack(pg_session_factory, org, "admin")
    sid = await bug_session(pg_session_factory, org, ctx={})

    await decide(pg_session_factory, org, pm, approved=True)

    bugs, _ = await state(pg_session_factory, org, sid)
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
    sid = await bug_session(pg_session_factory, org)
    if who == "developer":
        approver = await member_with_slack(pg_session_factory, org, "developer")
    elif who == "unknown":
        approver = "UNOBODY"
    else:
        approver = await member_with_slack(
            pg_session_factory, await new_org(pg_session_factory), "pm"
        )

    await decide(pg_session_factory, org, approver, approved=True)

    bugs, status = await state(pg_session_factory, org, sid)
    assert bugs == [] and status == TriageStatus.AWAITING_PM
    assert slack[-1].startswith("⚠️")
