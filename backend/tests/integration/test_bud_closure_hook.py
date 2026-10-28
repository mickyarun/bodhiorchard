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

"""``on_bud_closed`` called directly, the way the auto-close path does.

Contributor XP comes from commits and PR authors, never the assignee,
and is paid once however often the hook runs. Learning metrics and the
Learning Agent belong to the CLOSED firing only. A failing metrics
compute or agent spawn must not take the rewards down with it.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.pull_request import PullRequest
from app.services.bud_closure import on_bud_closed
from tests.integration.bud_lifecycle_reads import (
    timeline,
    xp_events,
    xp_ledger,
)
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_commit,
    add_member,
    new_org,
    stub_externals,
)

pytestmark = pytest.mark.integration

NUMBER = 77


async def _seed(
    factory: Factory, status: BUDStatus, **fields: Any
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Org, assignee (also a committer), a committer and a PR author."""
    org = await new_org(factory)
    lead = await add_member(factory, org, "lead", role="developer")
    committer = await add_member(factory, org, "committer", role="developer")
    author = await add_member(factory, org, "author", role="developer")
    bud_id = await add_bud(factory, org, number=NUMBER, status=status, assignee_id=lead, **fields)
    await add_commit(factory, org, bud_id, lead)
    await add_commit(factory, org, bud_id, committer)
    async with factory() as db:
        db.add(
            PullRequest(
                org_id=org,
                bud_id=bud_id,
                github_pr_number=1,
                github_pr_id=int(uuid.uuid4().int % 10**12),
                github_repo_full_name="acme/api",
                title="Add retries",
                html_url="https://example.invalid/pr/1",
                head_branch="bud-077/retries",
                base_branch="main",
                author_github_login="author",
                author_user_id=author,
            )
        )
        await db.commit()
    return org, bud_id, lead, committer, author


async def _close(factory: Factory, org: uuid.UUID, bud_id: uuid.UUID) -> None:
    """Run the hook in its own transaction and commit, like the callers do."""
    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        await on_bud_closed(db, org, bud)
        await db.commit()


async def test_contributors_from_commits_and_prs_are_paid_once(
    pg_session_factory: Factory,
) -> None:
    """Three firings, one payout each; the assignee is never a contributor."""
    org, bud_id, lead, committer, author = await _seed(pg_session_factory, BUDStatus.CLOSED)

    with stub_externals():
        for _ in range(3):
            await _close(pg_session_factory, org, bud_id)

    assert await xp_events(pg_session_factory, org) == {
        f"bud_contrib:{NUMBER}:{committer}": 25,
        f"bud_contrib:{NUMBER}:{author}": 25,
    }
    for user in (committer, author):
        assert await xp_ledger(pg_session_factory, org, user) == (25, 25)
    assert await xp_ledger(pg_session_factory, org, lead) == (0, 0)


async def test_prod_firing_skips_metrics_and_learning_agent(
    pg_session_factory: Factory,
) -> None:
    """At prod only rewards run, even when the closed phase is opted in."""
    org, bud_id, *_ = await _seed(
        pg_session_factory, BUDStatus.PROD, auto_generate_phases={"closed": True}
    )
    metrics, spawn = AsyncMock(), AsyncMock()

    with (
        stub_externals(),
        patch("app.services.bud_closure.compute_bud_metrics", metrics),
        patch("app.services.bud_closure.create_agent_task_for_stage", spawn),
    ):
        await _close(pg_session_factory, org, bud_id)

    metrics.assert_not_awaited()
    spawn.assert_not_awaited()
    assert len(await xp_events(pg_session_factory, org)) == 2


@pytest.mark.parametrize(
    ("phases", "spawns"), [({"closed": True}, 1), ({"closed": False}, 0), (None, 0)]
)
async def test_closed_firing_computes_metrics_and_gates_the_agent(
    pg_session_factory: Factory, phases: dict[str, bool] | None, spawns: int
) -> None:
    """Metrics always run at closed; the agent only with ``closed`` opted in."""
    org, bud_id, *_ = await _seed(
        pg_session_factory, BUDStatus.CLOSED, auto_generate_phases=phases
    )
    metrics, spawn = AsyncMock(), AsyncMock()

    with (
        stub_externals(),
        patch("app.services.bud_closure.compute_bud_metrics", metrics),
        patch("app.services.bud_closure.create_agent_task_for_stage", spawn),
    ):
        await _close(pg_session_factory, org, bud_id)

    assert metrics.await_count == 1
    assert spawn.await_count == spawns


async def test_failed_metrics_roll_back_alone(pg_session_factory: Factory) -> None:
    """A metrics crash undoes its own writes; contributor XP still commits."""
    org, bud_id, *_ = await _seed(pg_session_factory, BUDStatus.CLOSED)

    async def _crash(db: AsyncSession, org_id: uuid.UUID, bud: BUDDocument) -> None:
        db.add(BUDTimelineEvent(org_id=org_id, bud_id=bud.id, event_type="metrics_partial"))
        await db.flush()
        raise RuntimeError("metrics blew up")

    with stub_externals(), patch("app.services.bud_closure.compute_bud_metrics", _crash):
        await _close(pg_session_factory, org, bud_id)

    assert await timeline(pg_session_factory, bud_id, "metrics_partial") == []
    assert len(await xp_events(pg_session_factory, org)) == 2


async def test_failed_agent_spawn_does_not_block_the_close(
    pg_session_factory: Factory,
) -> None:
    """The Learning Agent is best effort: its failure is swallowed."""
    org, bud_id, *_ = await _seed(
        pg_session_factory, BUDStatus.CLOSED, auto_generate_phases={"closed": True}
    )
    spawn = AsyncMock(side_effect=RuntimeError("agent queue down"))

    with (
        stub_externals(),
        patch("app.services.bud_closure.compute_bud_metrics", AsyncMock()),
        patch("app.services.bud_closure.create_agent_task_for_stage", spawn),
    ):
        await _close(pg_session_factory, org, bud_id)

    assert spawn.await_count == 1
    assert len(await xp_events(pg_session_factory, org)) == 2


async def test_bud_without_contributors_pays_no_xp(pg_session_factory: Factory) -> None:
    """Only the assignee committed: there is nobody to pay contributor XP."""
    org = await new_org(pg_session_factory)
    lead = await add_member(pg_session_factory, org, "lead", role="developer")
    bud_id = await add_bud(
        pg_session_factory, org, number=NUMBER, status=BUDStatus.CLOSED, assignee_id=lead
    )
    await add_commit(pg_session_factory, org, bud_id, lead)

    with stub_externals():
        await _close(pg_session_factory, org, bud_id)

    assert await xp_events(pg_session_factory, org) == {}
