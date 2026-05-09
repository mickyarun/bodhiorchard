# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Unified BUD agent task handler.

Single handler for all BUD-level agent tasks (PRD, tech arch, code review).
Dispatches to per-type prompt builders and result handlers via an extensible
registry. Adding a new agent type = add a builder + handler entry.
"""

import asyncio
import uuid as uuid_mod
from typing import Any, Protocol

import structlog
from sqlalchemy import select

from app.models.bud import BUDDocument
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.models.tracked_repository import TrackedRepository
from app.schemas.jobs import BUDAgentTaskPayload, JobState
from app.services.agent_activity_logger import log_agent_activity
from app.services.agent_prompts import (
    build_code_review_prompt,
    build_prd_prompt,
    build_tech_arch_prompt,
    build_testing_prompt,
)
from app.services.agent_result_handlers import (
    handle_code_review_result,
    handle_prd_result,
    handle_tech_arch_result,
    handle_testing_result,
)
from app.services.job_queue import update_job
from app.services.job_utils import make_progress_callback, record_agent_timeline
from app.services.skill_loader import Skill

logger = structlog.get_logger(__name__)


# ── Protocol for per-type prompt builders ─────────────────────────


class PromptBuilder(Protocol):
    """Protocol for building an agent prompt from BUD state."""

    async def __call__(
        self, bud: BUDDocument, skill: Skill, org_id: uuid_mod.UUID, db: Any
    ) -> tuple[str, str | None]:
        """Build the prompt and optional working directory.

        Args:
            bud: The BUD document.
            skill: The loaded skill config.
            org_id: Organization UUID.
            db: Async database session.

        Returns:
            Tuple of (prompt_string, optional_working_dir).
        """
        ...


class ResultHandler(Protocol):
    """Protocol for handling agent output after Claude completes."""

    async def __call__(
        self,
        bud_id: uuid_mod.UUID,
        org_id: uuid_mod.UUID,
        output: str,
        task: BUDAgentTask,
        db: Any,
    ) -> dict | None:
        """Process agent output and persist results.

        Args:
            bud_id: The BUD UUID.
            org_id: The org UUID.
            output: Raw Claude output text.
            task: The agent task row.
            db: Async database session.

        Returns:
            Optional result_summary dict for the task row.
        """
        ...


# ── Registry ──────────────────────────────────────────────────────

PROMPT_BUILDERS: dict[str, PromptBuilder] = {
    "bud": build_prd_prompt,
    "tech_arch": build_tech_arch_prompt,
    "code_review": build_code_review_prompt,
    "testing": build_testing_prompt,
}

RESULT_HANDLERS: dict[str, ResultHandler] = {
    "bud": handle_prd_result,
    "tech_arch": handle_tech_arch_result,
    "code_review": handle_code_review_result,
    "testing": handle_testing_result,
}


async def _fail_designs_for_bud(
    db: Any,
    bud_id: uuid_mod.UUID,
) -> None:
    """Mark all 'generating' design rows for a BUD as 'failed'."""
    from sqlalchemy import update as sql_update

    from app.models.bud import BUDDesign

    await db.execute(
        sql_update(BUDDesign)
        .where(BUDDesign.bud_id == bud_id, BUDDesign.status == "generating")
        .values(status="failed")
    )


# ── Unified handler ───────────────────────────────────────────────


async def handle_bud_agent_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Unified handler for all BUD-level agent tasks.


    Loads the task from DB, dispatches to the appropriate prompt builder,
    runs Claude, then dispatches to the result handler.
    """
    payload = BUDAgentTaskPayload(**raw_payload)
    task_id = uuid_mod.UUID(payload.task_id)
    org_id = uuid_mod.UUID(payload.org_id)
    bud_id = uuid_mod.UUID(payload.bud_id)

    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDRepository

    update_job(job_id, status_message="Loading task...", progress_pct=5)

    # Pre-set so the ``except`` branches below can always log / write
    # activity rows even if we fail before resolving the real skill/task
    # type (e.g. task row not yet visible, DB down).
    _skill_slug: str = "bud_agent"
    _task_type: str = "unknown"

    async with AsyncSessionLocal() as db:
        try:
            task = await db.get(BUDAgentTask, task_id)
            if not task:
                logger.error(
                    "bud_agent_task_not_found",
                    task_id=str(task_id),
                    job_id=job_id,
                    org_id=str(org_id),
                )
                update_job(job_id, state=JobState.FAILED, error="Agent task not found")
                return

            # Defense-in-depth: verify task belongs to the expected org
            if task.org_id != org_id:
                update_job(job_id, state=JobState.FAILED, error="Org mismatch")
                return

            bud_repo = BUDRepository(db, org_id=org_id)
            bud = await bud_repo.get_by_id(bud_id)
            if not bud:
                task.status = AgentTaskStatus.FAILED
                task.error_message = "BUD not found"
                await db.commit()
                update_job(job_id, state=JobState.FAILED, error="BUD not found")
                return

            # Get skill from joined relationship
            skill_row = task.skill
            if not skill_row:
                task.status = AgentTaskStatus.FAILED
                task.error_message = "Skill not found"
                await db.commit()
                update_job(job_id, state=JobState.FAILED, error="Skill not found")
                return

            # Capture scalar values for use after session closes
            _skill_slug = skill_row.skill_slug
            _task_type = task.task_type
            _bud_number = bud.bud_number if bud else None
            _bud_title = bud.title if bud else None

            logger.info(
                "bud_agent_phase",
                phase="task_loaded",
                task_id=str(task_id),
                task_type=_task_type,
                bud_id=str(bud_id),
                skill_slug=_skill_slug,
            )

            skill = Skill(
                name=skill_row.name,
                slug=skill_row.skill_slug,
                description=skill_row.description,
                tools=skill_row.tools,
                mcp_tools=skill_row.mcp_tools,
                prompt=skill_row.prompt,
                max_turns=skill_row.max_turns or 0,
                model=skill_row.model or "",
                effort=skill_row.effort or "",
            )

            # Dispatch to prompt builder
            builder = PROMPT_BUILDERS.get(task.task_type)
            if not builder:
                task.status = AgentTaskStatus.FAILED
                task.error_message = f"No prompt builder for task type: {task.task_type}"
                # Mark any associated design rows as failed so the UI stops spinning
                if task.task_type == "design":
                    await _fail_designs_for_bud(db, bud_id)
                await db.commit()
                update_job(job_id, state=JobState.FAILED, error=task.error_message)
                return

            update_job(job_id, status_message="Building prompt...", progress_pct=10)
            prompt, working_dir = await builder(bud, skill, org_id, db)

            logger.info(
                "bud_agent_phase",
                phase="prompt_built",
                task_id=str(task_id),
                prompt_length=len(prompt),
                working_dir=working_dir,
            )

            # Run Claude
            update_job(job_id, status_message="Running agent...", progress_pct=20)

            from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code
            from app.services.job_utils import build_mcp_config

            mcp = build_mcp_config(
                org_id=str(org_id),
                tool_names=skill.mcp_tools if skill.mcp_tools else None,
            )

            config = ClaudeRunnerConfig(
                max_turns=max(skill.max_turns, 0),
                timeout_seconds=600,
                mcp=mcp,
                model=skill.model or None,
                effort=skill.effort or None,
            )

            # Code review needs JSON output
            if task.task_type == "code_review":
                config.output_format = "json"

            # Resolve repo_id from working_dir for activity tracking
            _repo_id = None
            if working_dir:
                repo_row = await db.execute(
                    select(TrackedRepository.id).where(
                        TrackedRepository.path == working_dir,
                        TrackedRepository.org_id == org_id,
                    )
                )
                _repo_id = repo_row.scalar_one_or_none()

            # Log skill_invoked in a SEPARATE session so it commits immediately
            # (the main db session commits only after run_claude_code completes,
            #  which can take 30-120 seconds — the row must be visible NOW)
            await log_agent_activity(
                None,
                org_id=org_id,
                event_type="skill_invoked",
                skill_slug=_skill_slug,
                message=f"Skill '{_skill_slug}' invoked for {_task_type}",
                bud_id=bud_id,
                skill_id=task.skill_id,
                task_id=task_id,
                repo_id=_repo_id,
                bud_number=bud.bud_number if bud else None,
                bud_title=bud.title if bud else None,
            )

            # Mark task as RUNNING — commit immediately so it's visible
            task.status = AgentTaskStatus.RUNNING
            await db.commit()

            logger.info(
                "bud_agent_phase",
                phase="claude_invoked",
                task_id=str(task_id),
                task_type=_task_type,
                bud_id=str(bud_id),
                skill_slug=_skill_slug,
            )

            result = await run_claude_code(
                prompt=prompt,
                working_dir=working_dir,
                config=config,
                progress_callback=make_progress_callback(job_id),
            )

            logger.info(
                "bud_agent_phase",
                phase="claude_completed",
                task_id=str(task_id),
                success=result.success,
                output_length=len(result.output or ""),
                cost_usd=result.cost_usd,
                turns_used=result.turns_used,
            )

            if not result.success:
                error_msg = result.error or "Agent execution failed"
                await log_agent_activity(
                    db,
                    org_id=org_id,
                    event_type="skill_failed",
                    skill_slug=_skill_slug,
                    message=error_msg,
                    bud_id=bud_id,
                    skill_id=task.skill_id,
                    task_id=task_id,
                    repo_id=_repo_id,
                    bud_number=bud.bud_number if bud else None,
                    bud_title=bud.title if bud else None,
                )
                task.status = AgentTaskStatus.FAILED
                task.error_message = error_msg[:500]
                await db.commit()
                update_job(
                    job_id,
                    state=JobState.FAILED,
                    error=error_msg,
                    error_code=result.error_code,
                )
                return

            # Dispatch to result handler
            update_job(job_id, status_message="Saving results...", progress_pct=90)

            # Refresh the ``bud`` ORM instance before dispatching. The agent
            # may have written to the BUD via MCP tools (``write_bud``) and
            # those writes committed in *separate* HTTP-request sessions.
            # ``AsyncSessionLocal`` uses ``expire_on_commit=False``, so our
            # cached instance is stale — and because SQLAlchemy's identity
            # map keys on primary key, any ``get_by_id`` a result handler
            # does on this same session returns the same stale instance
            # rather than re-reading from the DB. One refresh here inoculates
            # every current and future result handler + downstream service
            # (estimator prompt, todo sync, notifications).
            # Note: ``refresh`` reloads scalar columns only. If a future agent
            # writes to a relationship via MCP and a downstream step reads
            # it, pass ``attribute_names=["designs", ...]`` for that field.
            await db.refresh(bud)

            handler = RESULT_HANDLERS.get(task.task_type)
            result_summary = None
            if handler:
                result_summary = await handler(bud_id, org_id, result.output or "", task, db)

            await log_agent_activity(
                db,
                org_id=org_id,
                event_type="skill_completed",
                skill_slug=_skill_slug,
                message=f"Skill '{_skill_slug}' completed for {_task_type}",
                bud_id=bud_id,
                skill_id=task.skill_id,
                task_id=task_id,
                repo_id=_repo_id,
                metadata_=result_summary,
                bud_number=bud.bud_number if bud else None,
                bud_title=bud.title if bud else None,
            )

            # Mark task completed
            task.status = AgentTaskStatus.COMPLETED
            task.result_summary = result_summary
            task.error_message = None
            await db.commit()

            logger.info(
                "bud_agent_phase",
                phase="result_saved",
                task_id=str(task_id),
                task_type=_task_type,
            )

        except asyncio.CancelledError:
            # The API/worker signalled cancel via ``cancel_job``. Claude's
            # subprocess (if still running) was killed when the await was
            # interrupted — see the CancelledError branch in
            # ``claude_runner.run_claude_code``. We own the task row's
            # terminal state: flip it to FAILED with the user-supplied
            # reason and leave WS publication + JobState.CANCELLED to the
            # worker's own CancelledError handler.
            await db.rollback()
            # ``cancel_job`` stashes the cancel reason on the job's
            # ``status_message`` before it cancels the asyncio.Task, so
            # we can recover it via the public accessor without reaching
            # into job_queue internals.
            from app.services.job_queue import get_job  # noqa: PLC0415

            job = get_job(job_id)
            reason = (job.status_message if job else None) or "Cancelled by user"
            async with AsyncSessionLocal() as err_db:
                err_task = await err_db.get(BUDAgentTask, task_id)
                if err_task and err_task.status in (
                    AgentTaskStatus.PENDING,
                    AgentTaskStatus.RUNNING,
                ):
                    err_task.status = AgentTaskStatus.FAILED
                    err_task.error_message = reason[:500]
                await err_db.commit()
            await log_agent_activity(
                None,
                org_id=org_id,
                event_type="skill_failed",
                skill_slug=_skill_slug,
                message=reason,
                bud_id=bud_id,
                task_id=task_id,
            )
            logger.info("bud_agent_job_cancelled", task_id=str(task_id), reason=reason)
            raise  # Let the worker's CancelledError branch emit the WS terminal event

        except Exception as exc:
            await db.rollback()
            # Mark task failed in a fresh session (main session was rolled back)
            async with AsyncSessionLocal() as err_db:
                err_task = await err_db.get(BUDAgentTask, task_id)
                if err_task:
                    err_task.status = AgentTaskStatus.FAILED
                    err_task.error_message = str(exc)[:500]
                await err_db.commit()
            await log_agent_activity(
                None,
                org_id=org_id,
                event_type="skill_failed",
                skill_slug=_skill_slug,
                message=str(exc)[:2000],
                bud_id=bud_id,
                task_id=task_id,
            )
            update_job(job_id, state=JobState.FAILED, error=str(exc)[:200])
            logger.exception("bud_agent_job_failed", task_id=str(task_id))
            return

    # Record timeline event (using captured scalars — safe after session close)
    await record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        "ai_agent_completed",
        skill_name=_skill_slug,
        section=_task_type,
        job_id=job_id,
    )

    update_job(
        job_id,
        state=JobState.COMPLETED,
        status_message="Done",
        progress_pct=100,
    )

    # Re-publish skill_completed as a resilience measure.
    # The first publish (inside log_agent_activity) can be lost if the WS
    # connection briefly dropped during the long-running Claude task.
    # By this point update_job already published to job:{id}, proving the
    # WS is alive — so this second attempt is very likely to be delivered.
    # character.complete() on the frontend is idempotent, so duplicates are safe.
    from app.services.event_bus import publish as _eb_publish

    logger.info(
        "agent_activity_republish",
        topic=f"agent_activity:{org_id}",
        task_id=str(task_id),
    )
    _eb_publish(
        f"agent_activity:{org_id}",
        {
            "event_type": "skill_completed",
            "status": "completed",
            "message": f"Skill '{_skill_slug}' completed for {_task_type}",
            "skill_slug": _skill_slug,
            "actor_name": _skill_slug,
            "task_id": str(task_id),
            "repo_name": None,
            "bud_number": _bud_number,
            "bud_title": _bud_title,
            "impacted_repo_names": [],
            "created_at": "",
        },
    )
