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

"""Rejecting a Slack bug report, and the sessions the approval handler ignores.

Slack and the embedding model are faked, the rows are real.
"""

from __future__ import annotations

import pytest

from app.models.triage_session import TriageStatus
from tests.integration.scan_features_bugs_support import Factory, new_org
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


async def test_a_pm_rejecting_discards_the_report(
    pg_session_factory: Factory, slack: list[str]
) -> None:
    org = await new_org(pg_session_factory)
    pm = await member_with_slack(pg_session_factory, org, "pm")
    sid = await bug_session(pg_session_factory, org)

    await decide(pg_session_factory, org, pm, approved=False)

    bugs, status = await state(pg_session_factory, org, sid)
    assert bugs == [] and status == TriageStatus.REJECTED
    assert slack == ["❌ Bug report discarded."]


async def test_feature_requests_and_decided_sessions_are_left_alone(
    pg_session_factory: Factory, slack: list[str]
) -> None:
    org = await new_org(pg_session_factory)
    pm = await member_with_slack(pg_session_factory, org, "pm")
    feature_sid = await bug_session(pg_session_factory, org, kind="bud")

    await decide(pg_session_factory, org, pm, approved=True)
    _, feature_status = await state(pg_session_factory, org, feature_sid)

    other = await new_org(pg_session_factory)
    bug_sid = await bug_session(pg_session_factory, other)
    other_pm = await member_with_slack(pg_session_factory, other, "pm")
    await decide(pg_session_factory, other, other_pm, approved=False)
    await decide(pg_session_factory, other, other_pm, approved=True)
    bugs, bug_status = await state(pg_session_factory, other, bug_sid)

    assert feature_status == TriageStatus.AWAITING_PM
    assert bugs == [] and bug_status == TriageStatus.REJECTED
    assert slack == ["❌ Bug report discarded."]
