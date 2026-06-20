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

"""End-to-end SP simulation: drive a BUD to close, assert the SP ledger.

Reproduces the BUD-029 scenario the rewrite fixes — multiple developers
ship work, one of them only does trivial work, a tech-lead reviews, QA
files a couple of bugs — then closes the BUD and asserts every developer
SP rule paid the right person the right amount, that the trivial-only
contributor earns nothing, and that re-closing is idempotent.

Runs against a real Postgres (``-m integration``). The substance/review
judge is stubbed to a deterministic verdict so the maths is assertable
without invoking an LLM.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.bud import BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.models.bug import Bug, BugStatus, BugType
from app.models.developer_xp import RewardEvent, RewardType
from app.models.feature_learning import FeatureLearning
from app.models.organization import Organization
from app.models.role import Role, RoleScopeType
from app.models.user import OrgToUser, User
from app.services.bud_closure import on_bud_closed
from app.services.sp_attribution import SPAttribution

pytestmark = pytest.mark.integration


async def _add_user(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    handle: str,
    role_name: str | None,
) -> uuid.UUID:
    """Create a user + org membership (optionally role-scoped); return user_id."""
    user = User(
        email=f"{handle}-{uuid.uuid4().hex[:6]}@example.com",
        name=handle,
        password_hash="x",
        github_username=handle,
    )
    db.add(user)
    await db.flush()
    role_id: uuid.UUID | None = None
    if role_name is not None:
        # One SYSTEM role per (name, org) — uq_roles_name_org forbids dupes, so
        # multiple users sharing a role (e.g. two developers) reuse the row.
        existing = (
            await db.execute(select(Role).where(Role.name == role_name, Role.org_id == org_id))
        ).scalar_one_or_none()
        if existing is not None:
            role_id = existing.id
        else:
            role = Role(name=role_name, org_id=org_id, scope_type=RoleScopeType.SYSTEM)
            db.add(role)
            await db.flush()
            role_id = role.id
    db.add(OrgToUser(user_id=user.id, org_id=org_id, role_id=role_id))
    await db.flush()
    return user.id


async def _completed_todo(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    *,
    sequence: int,
    assignee_id: uuid.UUID,
    title: str,
) -> uuid.UUID:
    """Add a completed development todo; return its id."""
    todo = BUDTodo(
        org_id=org_id,
        bud_id=bud_id,
        sequence=sequence,
        title=title,
        phase="development",
        status=BUDTodoStatus.COMPLETED.value,
        assignee_id=assignee_id,
    )
    db.add(todo)
    await db.flush()
    return todo.id


async def _sp_ledger(
    factory: async_sessionmaker[AsyncSession], org_id: uuid.UUID
) -> dict[str, float]:
    """Map ``source_ref → amount`` for every SP reward event in the org."""
    async with factory() as db:
        rows = (
            (
                await db.execute(
                    select(RewardEvent).where(
                        RewardEvent.org_id == org_id,
                        RewardEvent.type == RewardType.SP,
                    )
                )
            )
            .scalars()
            .all()
        )
    return {r.source_ref: float(r.amount) for r in rows if r.source_ref}


@pytest.mark.asyncio
async def test_developer_sp_split_and_rules_on_close(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory = pg_session_factory

    async with factory() as db:
        org = Organization(name=f"SP Sim {uuid.uuid4()}", slug=f"sp-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        org_id = org.id

        dev1 = await _add_user(db, org_id, handle="dev1", role_name="developer")
        dev2 = await _add_user(db, org_id, handle="dev2", role_name="developer")
        dev3 = await _add_user(db, org_id, handle="dev3trivial", role_name="developer")
        lead = await _add_user(db, org_id, handle="techlead", role_name="tech_lead")

        bud = BUDDocument(
            org_id=org_id,
            bud_number=29,
            title="Multi-URL Webhook Endpoints",
            status=BUDStatus.PROD,
            complexity=3,
            code_review_comments=[
                {"author": "techlead", "body": "Consider a retry cap here.", "is_summary": False},
            ],
        )
        db.add(bud)
        await db.flush()
        bud_id = bud.id

        todo_a = await _completed_todo(
            db, org_id, bud_id, sequence=1, assignee_id=dev1, title="Build webhook fan-out"
        )
        todo_b = await _completed_todo(
            db, org_id, bud_id, sequence=2, assignee_id=dev2, title="Add delivery retry queue"
        )
        todo_c = await _completed_todo(
            db, org_id, bud_id, sequence=3, assignee_id=dev3, title="Swap settings icon"
        )

        # On-time development + bugs under the complexity-3 threshold (4).
        db.add(
            FeatureLearning(
                org_id=org_id,
                bud_id=bud_id,
                metrics={"phase_metrics": {"development": {"drift_pct": -12.0}}},
            )
        )
        for i in range(2):
            db.add(
                Bug(
                    org_id=org_id,
                    bud_id=bud_id,
                    bug_number=i + 1,
                    title=f"minor bug {i}",
                    reporter_id=dev1,
                    bug_type=BugType.TESTING,
                    status=BugStatus.OPEN,
                )
            )
        await db.commit()

    # Deterministic judge verdict: dev3's icon swap is trivial (0.0); the
    # tech-lead's review is valid.
    verdict = SPAttribution(
        todo_weights={str(todo_a): 1.0, str(todo_b): 1.0, str(todo_c): 0.0},
        review_validity={"techlead": True},
    )

    async def _run_close() -> None:
        async with factory() as db:
            bud = await db.get(BUDDocument, bud_id)
            assert bud is not None
            with patch(
                "app.services.sp_developer.judge_sp_attribution",
                new=AsyncMock(return_value=verdict),
            ):
                await on_bud_closed(db, org_id, bud)
            await db.commit()

    await _run_close()
    ledger = await _sp_ledger(factory, org_id)

    # Shipped pool (1.0) splits evenly across the two substantive devs.
    assert ledger.get(f"sp_bud_shipped:29:{dev1}") == 0.5
    assert ledger.get(f"sp_bud_shipped:29:{dev2}") == 0.5
    # Trivial-only contributor earns nothing, anywhere.
    assert not any(str(dev3) in ref for ref in ledger)
    # Valid reviewer (tech-lead) earns review SP.
    assert ledger.get(f"sp_review:29:{lead}") == 0.25
    # Quality bonus to the two real devs (bugs ≤ threshold AND on-time).
    assert ledger.get(f"sp_quality:29:{dev1}") == 0.5
    assert ledger.get(f"sp_quality:29:{dev2}") == 0.5

    # Idempotency: re-closing awards nothing new (source_ref dedup).
    before = len(ledger)
    await _run_close()
    after = await _sp_ledger(factory, org_id)
    assert len(after) == before
    assert after == ledger


@pytest.mark.asyncio
async def test_over_threshold_bugs_penalize_developers(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory = pg_session_factory

    async with factory() as db:
        org = Organization(name=f"SP Sim {uuid.uuid4()}", slug=f"sp-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        org_id = org.id
        dev1 = await _add_user(db, org_id, handle="solo", role_name="developer")

        bud = BUDDocument(
            org_id=org_id,
            bud_number=30,
            title="Flaky endpoint",
            status=BUDStatus.PROD,
            complexity=1,  # threshold 1
        )
        db.add(bud)
        await db.flush()
        bud_id = bud.id
        await _completed_todo(
            db, org_id, bud_id, sequence=1, assignee_id=dev1, title="Implement endpoint"
        )
        # 3 testing bugs >> complexity-1 threshold of 1.
        for i in range(3):
            db.add(
                Bug(
                    org_id=org_id,
                    bud_id=bud_id,
                    bug_number=i + 1,
                    title=f"bug {i}",
                    reporter_id=dev1,
                    bug_type=BugType.TESTING,
                    status=BugStatus.OPEN,
                )
            )
        await db.commit()

    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        # Single recipient → judge self-skips; no patch needed.
        await on_bud_closed(db, org_id, bud)
        await db.commit()

    ledger = await _sp_ledger(factory, org_id)
    # Solo dev still gets the full shipped pool...
    assert ledger.get(f"sp_bud_shipped:30:{dev1}") == 1.0
    # ...but is penalised for over-threshold bugs and earns no quality bonus.
    assert ledger.get(f"sp_bug_threshold:30:{dev1}") == -0.25
    assert f"sp_quality:30:{dev1}" not in ledger


@pytest.mark.asyncio
async def test_qa_close_time_rules(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory = pg_session_factory

    async with factory() as db:
        org = Organization(name=f"SP Sim {uuid.uuid4()}", slug=f"sp-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        org_id = org.id
        qa = await _add_user(db, org_id, handle="qa1", role_name="qa")

        bud = BUDDocument(
            org_id=org_id,
            bud_number=31,
            title="QA-heavy BUD",
            status=BUDStatus.CLOSED,  # QA close rules settle on the CLOSED pass
            complexity=1,  # threshold 1
        )
        db.add(bud)
        await db.flush()
        bud_id = bud.id
        # QA assigned to the testing phase → clean-exit credit resolves to them.
        db.add(
            BUDTimelineEvent(
                org_id=org_id,
                bud_id=bud_id,
                event_type="assigned",
                actor_id=qa,
                detail={"phase": "testing", "assignee_id": str(qa), "role": "qa"},
            )
        )
        for i in range(3):  # 3 testing bugs > complexity-1 threshold of 1
            db.add(
                Bug(
                    org_id=org_id,
                    bud_id=bud_id,
                    bug_number=i + 1,
                    title=f"qa bug {i}",
                    reporter_id=qa,
                    bug_type=BugType.TESTING,
                    status=BugStatus.OPEN,
                )
            )
        await db.commit()

    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        await on_bud_closed(db, org_id, bud)
        await db.commit()

    ledger = await _sp_ledger(factory, org_id)
    # Found more than the complexity bug budget → over-threshold credit.
    assert ledger.get(f"sp_qa_threshold:31:{qa}") == 0.25
    # Left testing without skipping/overriding any case → full clean-exit credit.
    assert ledger.get(f"sp_qa_tests:31:{qa}") == 0.5


@pytest.mark.asyncio
async def test_pm_close_time_rules(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory = pg_session_factory

    async with factory() as db:
        org = Organization(name=f"SP Sim {uuid.uuid4()}", slug=f"sp-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        org_id = org.id
        pm = await _add_user(db, org_id, handle="pm1", role_name="pm")

        bud = BUDDocument(
            org_id=org_id,
            bud_number=32,
            title="PM BUD",
            status=BUDStatus.CLOSED,
            complexity=2,
        )
        db.add(bud)
        await db.flush()
        bud_id = bud.id
        # PM is the actor who first moved the BUD requirement → design.
        db.add(
            BUDTimelineEvent(
                org_id=org_id,
                bud_id=bud_id,
                event_type="status_change",
                actor_id=pm,
                detail={"from": "bud", "to": "design"},
            )
        )
        # On-estimate cycle (full requirement credit) + tech-arch on time.
        db.add(
            FeatureLearning(
                org_id=org_id,
                bud_id=bud_id,
                estimated_days=10.0,
                cycle_time_days=10.0,
                metrics={"phase_metrics": {"tech_arch": {"drift_pct": -5.0}}},
            )
        )
        await db.commit()

    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        await on_bud_closed(db, org_id, bud)
        await db.commit()

    ledger = await _sp_ledger(factory, org_id)
    assert ledger.get(f"sp_pm_requirement:32:{pm}") == 1.0
    assert ledger.get(f"sp_pm_techspec:32:{pm}") == 0.25


@pytest.mark.asyncio
async def test_designer_and_tech_arch_close_time_rules(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    factory = pg_session_factory

    async with factory() as db:
        org = Organization(name=f"SP Sim {uuid.uuid4()}", slug=f"sp-{uuid.uuid4().hex[:8]}")
        db.add(org)
        await db.flush()
        org_id = org.id
        des = await _add_user(db, org_id, handle="des1", role_name="designer")
        tl = await _add_user(db, org_id, handle="tl1", role_name="tech_lead")

        bud = BUDDocument(
            org_id=org_id,
            bud_number=33,
            title="Design + tech-arch BUD",
            status=BUDStatus.CLOSED,
            complexity=4,  # high → designer on-time pays 0.5
        )
        db.add(bud)
        await db.flush()
        bud_id = bud.id
        db.add(
            BUDTimelineEvent(
                org_id=org_id,
                bud_id=bud_id,
                event_type="design_updated",
                actor_id=des,
                detail={"source": "figma_url"},
            )
        )
        db.add(
            BUDTimelineEvent(
                org_id=org_id,
                bud_id=bud_id,
                event_type="status_change",
                actor_id=tl,
                detail={"from": "tech_arch", "to": "development"},
            )
        )
        db.add(
            FeatureLearning(
                org_id=org_id,
                bud_id=bud_id,
                metrics={
                    "phase_metrics": {
                        "design": {"drift_pct": -3.0},
                        "tech_arch": {"drift_pct": -8.0},
                    }
                },
            )
        )
        await db.commit()

    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        await on_bud_closed(db, org_id, bud)
        await db.commit()

    ledger = await _sp_ledger(factory, org_id)
    assert ledger.get(f"sp_designer:33:{des}") == 0.25
    assert ledger.get(f"sp_designer_ontime:33:{des}") == 0.5  # high complexity
    assert ledger.get(f"sp_tl_techarch:33:{tl}") == 0.25
