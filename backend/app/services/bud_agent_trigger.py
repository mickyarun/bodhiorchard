"""BUD agent task triggering service.

Creates agent tasks based on stage mappings and enqueues them
in the job queue. Used by both the BUD API (status transitions)
and triage approval flows (Slack + UI).
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument

logger = structlog.get_logger(__name__)


async def create_agent_task_for_stage(
    bud: BUDDocument,
    bud_status: str,
    org_id: uuid.UUID,
    db: AsyncSession,
    *,
    triggered_by: uuid.UUID | None = None,
) -> None:
    """Look up stage mapping and create an agent task if configured.

    Args:
        bud: The BUD document.
        bud_status: The BUD status that triggers the agent.
        org_id: Organization UUID.
        db: Async database session.
        triggered_by: Optional user UUID who triggered the transition.
    """
    from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
    from app.repositories.agent_skill_bud_stage import AgentSkillBudStageRepository
    from app.schemas.jobs import BUDAgentTaskPayload
    from app.services.job_queue import JOB_BUD_AGENT, create_job

    stage_repo = AgentSkillBudStageRepository(db, org_id=org_id)
    mappings = await stage_repo.get_for_status(bud_status)
    if not mappings:
        return

    # Trigger first enabled mapping (pipeline: execution_order=1)
    first = next((m for m in mappings if m.enabled), None)
    if not first:
        return

    # Skip if the output section already has content (prevents re-runs on
    # status back-and-forth). Exception: "bud" status always runs — the PM agent
    # refines user-provided requirements, not just fills empty fields.
    output_section = first.output_section
    if output_section and bud_status != "bud" and hasattr(bud, output_section):
        existing_content = getattr(bud, output_section)
        if existing_content and existing_content.strip():
            logger.info(
                "agent_skip_content_exists",
                bud_id=str(bud.id),
                status=bud_status,
                section=output_section,
            )
            return

    # Skip if an agent is already running for this BUD
    from app.repositories.bud_agent_task import BUDAgentTaskRepository

    task_repo = BUDAgentTaskRepository(db, org_id=org_id)
    if await task_repo.get_active_for_bud(bud.id):
        return

    task = BUDAgentTask(
        org_id=org_id,
        bud_id=bud.id,
        skill_id=first.skill_id,
        task_type=bud_status,
        status=AgentTaskStatus.PENDING,
        attempt=1,
        triggered_by=triggered_by,
    )
    db.add(task)
    await db.flush()  # get task.id without committing

    job = create_job(
        JOB_BUD_AGENT,
        payload=BUDAgentTaskPayload(
            org_id=str(org_id),
            bud_id=str(bud.id),
            task_id=str(task.id),
        ).model_dump(),
        user_id=str(triggered_by) if triggered_by else None,
    )
    task.job_id = job.job_id
    task.status = AgentTaskStatus.RUNNING

    # Single atomic commit — task + job_id visible to worker together.
    # Must commit before returning because the worker opens its own session.
    await db.commit()

    logger.info(
        "agent_task_created",
        bud_id=str(bud.id),
        task_id=str(task.id),
        task_type=bud_status,
        skill_id=str(first.skill_id),
    )
