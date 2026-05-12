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

"""BUD design wireframe endpoints."""

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud import BUDDesignStatus
from app.models.user import User
from app.repositories.bud import BUDDesignRepository, BUDRepository
from app.schemas.bud import BUDDesignRead, DesignGenerateRequest, DesignHtmlUpdate
from app.schemas.jobs import DesignAgentJobPayload
from app.services.job_queue import JOB_DESIGN_AGENT, create_job

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=list[BUDDesignRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_designs(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all design wireframes for a BUD with repo names."""
    design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
    return await design_repo.list_with_repo_names(bud_id)


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def generate_designs(
    bud_id: uuid.UUID,
    body: DesignGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Create bud_design rows and enqueue design jobs for each repo."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
    repo_ids: list[uuid.UUID | None] = list(body.repo_ids) if body.repo_ids else [None]

    design_rows: list[tuple[uuid.UUID | None, str]] = []
    for rid in repo_ids:
        design = await design_repo.upsert(
            bud_id=bud.id,
            repo_id=rid,
            status=BUDDesignStatus.PENDING,
        )
        design_rows.append((rid, str(design.id)))
    await db.flush()

    # Resolve skill + create agent task BEFORE enqueuing jobs
    # so task_id and skill_id are available in the job payload
    from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
    from app.repositories.agent_skill import AgentSkillRepository
    from app.repositories.bud_agent_task import BUDAgentTaskRepository

    skill_repo = AgentSkillRepository(db, org_id=current_user.org_id)
    designer_skill = await skill_repo.get_by_slug("designer")
    skill_id_str = str(designer_skill.id) if designer_skill else None

    task_repo = BUDAgentTaskRepository(db, org_id=current_user.org_id)
    active = await task_repo.get_active_for_bud(bud_id)
    task_id_str: str | None = str(active.id) if active else None

    if not active and designer_skill:
        task = BUDAgentTask(
            org_id=current_user.org_id,
            bud_id=bud_id,
            skill_id=designer_skill.id,
            task_type="design",
            status=AgentTaskStatus.RUNNING,
            attempt=1,
            triggered_by=current_user.id,
        )
        db.add(task)
        await db.flush()
        task_id_str = str(task.id)

    results = []
    for rid, design_id in design_rows:
        payload = DesignAgentJobPayload(
            org_id=str(current_user.org_id),
            bud_id=str(bud.id),
            bud_number=bud.bud_number,
            title=bud.title,
            requirements_md=bud.requirements_md or "",
            repo_id=str(rid) if rid else None,
            design_id=design_id,
            skill_id=skill_id_str,
            task_id=task_id_str,
        )
        job = create_job(
            JOB_DESIGN_AGENT,
            payload=payload.model_dump(),
            user_id=str(current_user.id),
        )

        design_obj = await design_repo.get_by_id(uuid.UUID(design_id))
        if design_obj:
            design_obj.job_id = job.job_id
            design_obj.status = BUDDesignStatus.GENERATING

        # Backfill job_id on the task (first job wins)
        if task_id_str and not active:
            active_task = await task_repo.get_by_id(uuid.UUID(task_id_str))
            if active_task and not active_task.job_id:
                active_task.job_id = job.job_id

        results.append(
            {
                "designId": design_id,
                "repoId": str(rid) if rid else None,
                "jobId": job.job_id,
            }
        )
        logger.info(
            "design_job_created",
            bud_id=str(bud.id),
            repo_id=str(rid) if rid else None,
            job_id=job.job_id,
            design_id=design_id,
        )

    await db.commit()
    return results


@router.put(
    "/{design_id}",
    response_model=BUDDesignRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def update_design_html(
    bud_id: uuid.UUID,
    design_id: uuid.UUID,
    body: DesignHtmlUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Manually edit a design wireframe's HTML or notes."""
    design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
    design = await design_repo.get_by_id(design_id)
    if design is None or design.bud_id != bud_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design not found")

    if body.design_html is not None:
        from app.services.html_sanitizer import sanitize_design_html

        design.design_html = sanitize_design_html(body.design_html)
        design.status = BUDDesignStatus.READY
    if body.notes is not None:
        design.notes = body.notes
    await db.flush()
    await db.refresh(design)

    designs = await design_repo.list_with_repo_names(bud_id)
    return next((d for d in designs if d["id"] == design_id), designs[0])


@router.post(
    "/{design_id}/regenerate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def regenerate_design(
    bud_id: uuid.UUID,
    design_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Re-trigger design generation for a single design."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
    design = await design_repo.get_by_id(design_id)
    if design is None or design.bud_id != bud_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Design not found")

    design.status = BUDDesignStatus.GENERATING
    await db.flush()

    # Resolve skill_id and active task_id for activity logging
    from app.repositories.agent_skill import AgentSkillRepository
    from app.repositories.bud_agent_task import BUDAgentTaskRepository

    skill_repo = AgentSkillRepository(db, org_id=current_user.org_id)
    designer_skill = await skill_repo.get_by_slug("designer")
    task_repo = BUDAgentTaskRepository(db, org_id=current_user.org_id)
    active_task = await task_repo.get_active_for_bud(bud_id)

    payload = DesignAgentJobPayload(
        org_id=str(current_user.org_id),
        bud_id=str(bud.id),
        bud_number=bud.bud_number,
        title=bud.title,
        requirements_md=bud.requirements_md or "",
        repo_id=str(design.repo_id) if design.repo_id else None,
        design_id=str(design.id),
        skill_id=str(designer_skill.id) if designer_skill else None,
        task_id=str(active_task.id) if active_task else None,
    )
    job = create_job(
        JOB_DESIGN_AGENT,
        payload=payload.model_dump(),
        user_id=str(current_user.id),
    )

    design.job_id = job.job_id
    await db.flush()

    return {"designId": str(design.id), "jobId": job.job_id}
