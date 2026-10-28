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

"""The open-bug gate on testing and the code-review SP award.

``check_bug_threshold`` sends a testing BUD back to development once its
open bugs reach the org threshold (resolved / closed / rejected bugs do
not count) and does nothing outside testing. ``award_code_review_sp``
pays valid, non-self reviewers in reviewing roles exactly once.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.bud import BUDDocument, BUDStatus
from app.models.bug import Bug, BugStatus, BugType
from app.models.developer_xp import RewardEvent, RewardType
from app.services.bug_testing_gate import check_bug_threshold
from app.services.code_review_sp import award_code_review_sp
from tests.integration.bud_lifecycle_reads import load_bud, timeline
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_member,
    new_org,
    stub_externals,
)

pytestmark = pytest.mark.integration


async def _bugs(factory: Factory, org: uuid.UUID, bud_id: uuid.UUID, *statuses: BugStatus) -> None:
    """Bugs on the BUD, one per status, filed by a fresh QA reporter."""
    reporter = await add_member(factory, org, "reporter", role="qa")
    async with factory() as db:
        for i, status in enumerate(statuses, start=1):
            db.add(
                Bug(
                    org_id=org,
                    bud_id=bud_id,
                    bug_number=i,
                    title=f"bug {i}",
                    reporter_id=reporter,
                    bug_type=BugType.TESTING,
                    status=status,
                )
            )
        await db.commit()


async def _gate(factory: Factory, org: uuid.UUID, bud_id: uuid.UUID) -> bool:
    """Run the gate in its own committed transaction; return whether it rejected."""
    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        with stub_externals():
            rejected = await check_bug_threshold(db, org, bud)
        await db.commit()
        return rejected


async def test_reaching_the_threshold_rejects_back_to_development(
    pg_session_factory: Factory,
) -> None:
    """Two open bugs at threshold 2: back to development, QA freed, events logged."""
    org = await new_org(pg_session_factory, config={"qa": {"bugRejectThreshold": 2}})
    tester = await add_member(pg_session_factory, org, "tester", role="qa")
    dev = await add_member(pg_session_factory, org, "dev", role="developer")
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.TESTING, assignee_id=tester)
    await _bugs(pg_session_factory, org, bud_id, BugStatus.OPEN, BugStatus.BLOCKED)

    assert await _gate(pg_session_factory, org, bud_id) is True

    bud = await load_bud(pg_session_factory, bud_id)
    assert (bud.status, bud.assignee_id) == (BUDStatus.DEVELOPMENT, dev)
    [rejected] = await timeline(pg_session_factory, bud_id, "testing_rejected")
    assert (rejected["bug_count"], rejected["threshold"]) == (2, 2)
    assert rejected["previous_assignee_id"] == str(tester)
    changes = await timeline(pg_session_factory, bud_id, "status_change")
    assert [(c["from"], c["to"], c["auto"]) for c in changes] == [("testing", "development", True)]


async def test_settled_bugs_do_not_count_towards_the_threshold(
    pg_session_factory: Factory,
) -> None:
    """One open bug plus resolved / closed / rejected ones stays under 2."""
    org = await new_org(pg_session_factory, config={"qa": {"bugRejectThreshold": 2}})
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.TESTING)
    await _bugs(
        pg_session_factory,
        org,
        bud_id,
        BugStatus.OPEN,
        BugStatus.RESOLVED,
        BugStatus.CLOSED,
        BugStatus.REJECTED,
    )

    assert await _gate(pg_session_factory, org, bud_id) is False
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.TESTING
    assert await timeline(pg_session_factory, bud_id, "testing_rejected") == []


@pytest.mark.parametrize("status", [BUDStatus.DEVELOPMENT, BUDStatus.UAT, BUDStatus.CLOSED])
async def test_gate_only_acts_on_testing(pg_session_factory: Factory, status: BUDStatus) -> None:
    """Outside testing (closed in particular) the gate never moves the BUD."""
    org = await new_org(pg_session_factory, config={"qa": {"bugRejectThreshold": 1}})
    bud_id = await add_bud(pg_session_factory, org, status=status)
    await _bugs(pg_session_factory, org, bud_id, BugStatus.OPEN, BugStatus.OPEN)

    assert await _gate(pg_session_factory, org, bud_id) is False
    assert (await load_bud(pg_session_factory, bud_id)).status is status


async def _review_sp(factory: Factory, org: uuid.UUID) -> dict[str, float]:
    """``source_ref -> amount`` of every review SP event in the org."""
    async with factory() as db:
        rows = await db.scalars(
            select(RewardEvent).where(
                RewardEvent.org_id == org,
                RewardEvent.type == RewardType.SP,
                RewardEvent.source == "sp_review",
            )
        )
        return {r.source_ref: float(r.amount) for r in rows if r.source_ref}


async def test_review_sp_pays_valid_non_self_reviewers_once(
    pg_session_factory: Factory,
) -> None:
    """Valid dev reviewer paid; rubber stamp, self-review, PM and blank comments are not."""
    org = await new_org(pg_session_factory)
    good = await add_member(pg_session_factory, org, "good", role="developer", github="good")
    stamp = await add_member(pg_session_factory, org, "stamp", role="developer", github="stamp")
    author = await add_member(pg_session_factory, org, "author", role="developer", github="me")
    await add_member(pg_session_factory, org, "pmrev", role="pm", github="pmrev")
    comments = [
        {"author": "good", "body": "Handle the timeout path."},
        {"author": "good", "body": "And add a test."},
        {"author": "stamp", "body": "LGTM"},
        {"author": "me", "body": "Self note."},
        {"author": "pmrev", "body": "Copy looks fine."},
        {"author": "ghost", "body": "Unknown login."},
        {"author": "blank", "body": "   "},
    ]
    bud_id = await add_bud(
        pg_session_factory, org, number=12, status=BUDStatus.CLOSED, code_review_comments=comments
    )

    async def _award() -> int:
        """One award pass, committed; returns how many reviewers were credited."""
        async with pg_session_factory() as db:
            bud = await db.get(BUDDocument, bud_id)
            assert bud is not None
            count = await award_code_review_sp(
                db, org, bud, {"stamp": False}, exclude_user_ids={author}
            )
            await db.commit()
            return count

    assert await _award() == 1
    assert await _award() == 0
    ledger = await _review_sp(pg_session_factory, org)
    assert list(ledger) == [f"sp_review:12:{good}"]
    assert ledger[f"sp_review:12:{good}"] > 0
    assert str(stamp) not in "".join(ledger)
