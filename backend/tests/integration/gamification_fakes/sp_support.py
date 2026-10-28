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

"""Rows the Skill-Point tests start from.

Every helper opens its own session on the test database and commits, so a
test reads exactly what the close-time code persisted. Names and numbers are
unique per call; tests never share an org.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.models.bug import Bug, BugStatus, BugType
from app.models.feature_learning import FeatureLearning
from app.models.organization import Organization
from app.models.user import User
from tests.fakes.seed import Factory

CloseStep = Callable[[AsyncSession, uuid.UUID, BUDDocument], Awaitable[None]]


async def new_bud(
    factory: Factory,
    org_id: uuid.UUID,
    *,
    number: int = 7,
    complexity: int | None = 3,
    status: BUDStatus = BUDStatus.CLOSED,
    reviews: list[dict[str, Any]] | None = None,
) -> uuid.UUID:
    """A BUD in ``status`` with optional ``code_review_comments``."""
    async with factory() as db:
        bud = BUDDocument(
            org_id=org_id,
            bud_number=number,
            title=f"BUD {number}",
            status=status,
            complexity=complexity,
            code_review_comments=reviews or [],
        )
        db.add(bud)
        await db.commit()
        return bud.id


async def add_todo(
    factory: Factory,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    assignee_id: uuid.UUID,
    title: str,
    *,
    sequence: int,
) -> uuid.UUID:
    """A completed development todo assigned to ``assignee_id``."""
    async with factory() as db:
        todo = BUDTodo(
            org_id=org_id,
            bud_id=bud_id,
            sequence=sequence,
            title=title,
            description=f"{title} in full",
            phase="development",
            status=BUDTodoStatus.COMPLETED.value,
            assignee_id=assignee_id,
        )
        db.add(todo)
        await db.commit()
        return todo.id


async def add_bugs(
    factory: Factory,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    reporter_id: uuid.UUID,
    count: int,
    *,
    bug_type: BugType = BugType.TESTING,
    status: BugStatus = BugStatus.OPEN,
    first_number: int = 1,
) -> list[uuid.UUID]:
    """``count`` bugs on the BUD filed by ``reporter_id``; returns their ids."""
    async with factory() as db:
        bugs = [
            Bug(
                org_id=org_id,
                bud_id=bud_id,
                bug_number=first_number + i,
                title=f"bug {first_number + i}",
                reporter_id=reporter_id,
                bug_type=bug_type,
                status=status,
            )
            for i in range(count)
        ]
        db.add_all(bugs)
        await db.commit()
        return [b.id for b in bugs]


async def add_learning(
    factory: Factory,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    *,
    drift: dict[str, float] | None = None,
    estimated_days: float | None = None,
    cycle_time_days: float | None = None,
) -> None:
    """The post-close metrics envelope: per-phase ``drift_pct`` and estimate vs actual."""
    phase_metrics = {phase: {"drift_pct": pct} for phase, pct in (drift or {}).items()}
    async with factory() as db:
        db.add(
            FeatureLearning(
                org_id=org_id,
                bud_id=bud_id,
                estimated_days=estimated_days,
                cycle_time_days=cycle_time_days,
                metrics={"phase_metrics": phase_metrics},
            )
        )
        await db.commit()


async def add_event(
    factory: Factory,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    event_type: str,
    actor_id: uuid.UUID | None,
    detail: dict[str, Any],
) -> None:
    """One timeline event (status change, assignment, design update, override)."""
    async with factory() as db:
        db.add(
            BUDTimelineEvent(
                org_id=org_id,
                bud_id=bud_id,
                event_type=event_type,
                actor_id=actor_id,
                detail=detail,
            )
        )
        await db.commit()


async def set_github_login(factory: Factory, user_id: uuid.UUID, login: str) -> None:
    """Give a seeded member a GitHub login so review comments resolve to them."""
    async with factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.github_username = login
        await db.commit()


async def set_org_config(factory: Factory, org_id: uuid.UUID, config: dict[str, Any]) -> None:
    """Replace the org's ``config`` JSON (bug thresholds, quiz settings)."""
    async with factory() as db:
        org = await db.get(Organization, org_id)
        assert org is not None
        org.config = config
        await db.commit()


async def run_close_step(
    factory: Factory, org_id: uuid.UUID, bud_id: uuid.UUID, step: CloseStep
) -> None:
    """Load the BUD, run one close-time SP rule on it, and commit."""
    async with factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        await step(db, org_id, bud)
        await db.commit()
