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

"""Rows a stage-agent test starts from, and the reads its assertions use.

An org is seeded with the real skill templates and stage mappings (the
same seeders the app runs for a new org), so a stage trigger resolves the
real skill: its prompt, its MCP tool list and its turn limit.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.models.agent_activity import AgentActivityLog
from app.models.bud import BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.bud_agent_task import BUDAgentTask
from app.repositories.agent_activity import AgentActivityLogRepository
from app.repositories.bud import BUDRepository
from app.repositories.bud_timeline import BUDTimelineRepository
from app.repositories.organization import OrganizationRepository
from app.services.bud_agent_trigger import create_agent_task_for_stage
from app.services.bud_stage_seeder import seed_stage_mappings_for_org
from app.services.skill_loader import seed_skills_for_org
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import Factory, SeededOrg, seed_org

ESTIMATE_MARKER = "Reply with ONLY a JSON object of the form"


@dataclass(frozen=True)
class StageRun:
    """The agent task a stage trigger created and the job it enqueued."""

    task_id: uuid.UUID
    job_id: str


async def seed_agent_org(factory: Factory, *, github: FakeGitHub | None = None) -> SeededOrg:
    """An org with the default skills and BUD stage mappings."""
    org = await seed_org(factory, github=github)
    async with factory() as db:
        await seed_skills_for_org(org.org_id, db)
        await db.flush()
        await seed_stage_mappings_for_org(org.org_id, db)
        await db.commit()
    return org


async def set_org_config(factory: Factory, org_id: uuid.UUID, config: dict[str, Any]) -> None:
    """Replace the org's ``config`` JSON."""
    async with factory() as db:
        org = await OrganizationRepository(db).get_by_id(org_id)
        assert org is not None
        org.config = config
        await db.commit()


async def add_bud(
    factory: Factory,
    org_id: uuid.UUID,
    *,
    status: BUDStatus = BUDStatus.BUD,
    title: str = "Refund orders",
    requirements_md: str | None = "Shoppers can refund an order.",
    **columns: Any,
) -> BUDDocument:
    """A BUD with the org's next number; extra ``columns`` set as given."""
    async with factory() as db:
        repo = BUDRepository(db, org_id=org_id)
        bud = BUDDocument(
            org_id=org_id,
            bud_number=await repo.next_bud_number(),
            title=title,
            status=status,
            requirements_md=requirements_md,
            **columns,
        )
        db.add(bud)
        await db.commit()
        return bud


async def trigger_stage(
    factory: Factory,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    stage: str,
    *,
    triggered_by: uuid.UUID | None = None,
) -> StageRun:
    """Create and enqueue the stage's agent task through the real trigger."""
    async with factory() as db:
        bud = await BUDRepository(db, org_id=org_id).get_by_id(bud_id)
        assert bud is not None
        task = await create_agent_task_for_stage(
            bud, stage, org_id, db, triggered_by=triggered_by, force=True
        )
        assert task is not None and task.job_id is not None, f"no {stage} stage mapping"
        return StageRun(task_id=task.id, job_id=task.job_id)


async def load_bud(factory: Factory, org_id: uuid.UUID, bud_id: uuid.UUID) -> BUDDocument:
    """A fresh read of the BUD row."""
    async with factory() as db:
        bud = await BUDRepository(db, org_id=org_id).get_by_id(bud_id)
        assert bud is not None
        return bud


async def load_task(factory: Factory, task_id: uuid.UUID) -> BUDAgentTask:
    """A fresh read of the agent task row."""
    async with factory() as db:
        task = await db.get(BUDAgentTask, task_id)
        assert task is not None
        return task


async def timeline(
    factory: Factory, org_id: uuid.UUID, bud_id: uuid.UUID
) -> list[BUDTimelineEvent]:
    """The BUD's timeline events, oldest first."""
    async with factory() as db:
        return await BUDTimelineRepository(db, org_id=org_id).list_for_bud(bud_id)


async def activity(
    factory: Factory, org_id: uuid.UUID, bud_id: uuid.UUID
) -> list[AgentActivityLog]:
    """The BUD's agent activity rows, oldest first."""
    async with factory() as db:
        rows = await AgentActivityLogRepository(db, org_id=org_id).list_for_bud(bud_id)
    return sorted(rows, key=lambda row: row.created_at)


def activity_types(rows: list[AgentActivityLog]) -> list[str]:
    """Event types of activity rows, in order."""
    return [row.event_type for row in rows]
