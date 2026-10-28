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

"""Rows for the agent-task cancel tests: an org, a BUD, its task and designs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_skill import AgentSkill, AgentType
from app.models.bud import BUDDesign, BUDDesignStatus, BUDDocument, BUDStatus
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.models.organization import Organization
from app.models.tracked_repository import TrackedRepository

Factory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class AgentRun:
    """One BUD with a running design task."""

    org_id: uuid.UUID
    bud_id: uuid.UUID
    task_id: uuid.UUID
    job_id: str


async def running_task(factory: Factory, *, task_type: str = "design") -> AgentRun:
    """A design-phase BUD whose agent task is RUNNING under a fresh job id."""
    job_id = str(uuid.uuid4())
    async with factory() as db:
        org = Organization(name=f"Agent {uuid.uuid4()}", slug=f"ag-{uuid.uuid4().hex[:10]}")
        db.add(org)
        await db.flush()
        skill = AgentSkill(
            org_id=org.id,
            skill_slug="designer",
            agent_type=AgentType.DESIGN,
            name="Designer",
            prompt="p",
        )
        bud = BUDDocument(org_id=org.id, bud_number=1, title="t", status=BUDStatus.DESIGN)
        db.add_all([skill, bud])
        await db.flush()
        task = BUDAgentTask(
            org_id=org.id,
            bud_id=bud.id,
            skill_id=skill.id,
            task_type=task_type,
            status=AgentTaskStatus.RUNNING,
            job_id=job_id,
        )
        db.add(task)
        await db.commit()
        return AgentRun(org_id=org.id, bud_id=bud.id, task_id=task.id, job_id=job_id)


async def add_design(
    factory: Factory, run: AgentRun, status: BUDDesignStatus, *, job_id: str | None = None
) -> uuid.UUID:
    """A per-repo design row on the run's BUD."""
    async with factory() as db:
        repo = TrackedRepository(org_id=run.org_id, path=f"/tmp/{uuid.uuid4().hex}", name="web")
        db.add(repo)
        await db.flush()
        design = BUDDesign(
            org_id=run.org_id, bud_id=run.bud_id, repo_id=repo.id, status=status, job_id=job_id
        )
        db.add(design)
        await db.commit()
        return design.id


async def task_state(factory: Factory, task_id: uuid.UUID) -> tuple[str, str | None]:
    """``(status, error_message)`` of an agent task."""
    async with factory() as db:
        task = await db.get(BUDAgentTask, task_id)
        assert task is not None
        return task.status, task.error_message


async def design_status(factory: Factory, design_id: uuid.UUID) -> BUDDesignStatus:
    """Current status of a design row."""
    async with factory() as db:
        design = await db.get(BUDDesign, design_id)
        assert design is not None
        return design.status
