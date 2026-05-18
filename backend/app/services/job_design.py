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

"""Design job handlers for wireframe generation and design system extraction.

Handles:
- Design agent job: generates wireframes using Claude + design system context
- Design extract job: extracts design systems from tracked repositories
"""

import uuid as uuid_mod
from pathlib import Path
from typing import Any

import structlog

from app.database import AsyncSessionLocal
from app.models.bud import BUDDesignStatus
from app.repositories.bud import BUDDesignRepository
from app.schemas.jobs import DesignAgentJobPayload, DesignExtractJobPayload, JobState
from app.services.agent_activity_logger import log_agent_activity
from app.services.chat_prompts import build_design_prompt
from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code
from app.services.job_queue import update_job
from app.services.job_utils import (
    build_mcp_config,
    make_progress_callback,
    record_agent_timeline,
    resolve_repo_path,
)
from app.services.json_parser import parse_chat_response
from app.services.section_session import mint_session_id, record_originating_session
from app.services.skill_loader import load_skill

logger = structlog.get_logger(__name__)


async def handle_design_agent_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Generate a design wireframe for a BUD using a repo-specific design system."""
    payload = DesignAgentJobPayload(**raw_payload)
    bud_ref = f"BUD-{payload.bud_number:03d}"
    repo_id = payload.repo_id
    design_id = payload.design_id

    update_job(job_id, status_message="Loading design system...", progress_pct=10)

    # Resolve repo path so Claude runs in the repo dir and reads its CLAUDE.md
    repo_path = await resolve_repo_path(repo_id, payload.org_id)

    # Scope the design to this repo only (prevents cross-repo contamination)
    repo_name = Path(repo_path).name if repo_path else None
    scope_note = ""
    if repo_name:
        scope_note = (
            f"\n\n## Scope\n\n"
            f"You are generating a wireframe ONLY for the **{repo_name}** repository. "
            f"Do NOT include screens or features from other repositories. "
            f"Focus exclusively on this repo's functionality and UI patterns.\n"
        )

    # Design tools: read existing wireframe, write iterated result, browse system.
    design_tools = [
        "list_design_systems",
        "get_design_system",
        "get_bud_designs",
        "write_bud_design",
    ]
    mcp_config = build_mcp_config(payload.org_id, tool_names=design_tools)

    prompt = await build_design_prompt(
        bud_ref=bud_ref,
        title=payload.title,
        org_id=payload.org_id,
        message=(
            f"Generate an initial wireframe for {bud_ref}: {payload.title}.\n\n"
            "## BUD Requirements\n\n"
            f"{payload.requirements_md}\n\n"
            "Create a wireframe covering the key screens and interactions "
            "described in the requirements. Focus on layout, information "
            "architecture, and user flow."
            f"{scope_note}"
        ),
        bud_id=payload.bud_id,
        repo_id=repo_id,
        repo_name=repo_name,
    )

    update_job(
        job_id,
        status_message="Generating wireframe (this may take a few minutes)...",
        progress_pct=20,
    )

    # Resolve the designer skill via per-BUD override > org default > seed.
    # The BUD's Advanced-Settings pick must follow the design through to
    # the worker, not just the API/task row — otherwise the worker would
    # load the seeded designer config (model, max_turns, prompt) even
    # when the task itself was created with a custom designer skill_id.
    from app.models.bud import BUDStatus
    from app.services.skill_loader import resolve_skill_for_org

    try:
        async with AsyncSessionLocal() as _skill_db:
            designer_skill = await resolve_skill_for_org(
                "design",
                uuid_mod.UUID(payload.org_id),
                _skill_db,
                bud_id=uuid_mod.UUID(payload.bud_id),
                bud_status=BUDStatus.DESIGN,
                fallback_slug="designer",
            )
    except (ValueError, LookupError):
        try:
            designer_skill = load_skill("designer")
        except FileNotFoundError:
            designer_skill = None

    _skill_uuid = uuid_mod.UUID(payload.skill_id) if payload.skill_id else None
    _task_uuid = uuid_mod.UUID(payload.task_id) if payload.task_id else None
    _repo_uuid = uuid_mod.UUID(repo_id) if repo_id else None
    _org_uuid = uuid_mod.UUID(payload.org_id)

    await log_agent_activity(
        None,
        org_id=_org_uuid,
        event_type="skill_invoked",
        skill_slug="designer",
        message=f"Designer skill invoked for {bud_ref}",
        bud_id=uuid_mod.UUID(payload.bud_id),
        skill_id=_skill_uuid,
        task_id=_task_uuid,
        repo_id=_repo_uuid,
        bud_number=payload.bud_number,
        bud_title=payload.title,
    )

    # Mint a CLI session id so subsequent design-tab chats on this exact
    # (bud, design) row can ``--resume`` and keep the prompt cache warm.
    originating_session_id = mint_session_id()

    result = await run_claude_code(
        prompt=prompt,
        working_dir=repo_path,
        config=ClaudeRunnerConfig(
            max_turns=designer_skill.max_turns if designer_skill else 0,
            timeout_seconds=900,
            mcp=mcp_config,
            model=(designer_skill.model or None) if designer_skill else None,
            effort=(designer_skill.effort or None) if designer_skill else None,
            cli_session_id=str(originating_session_id),
            is_resume=False,
        ),
        progress_callback=make_progress_callback(
            job_id,
            generating_message=("Generating wireframe HTML — this may take a minute or two..."),
        ),
    )

    if not result.success:
        await log_agent_activity(
            None,
            org_id=_org_uuid,
            event_type="skill_failed",
            skill_slug="designer",
            message=result.error or "AI unavailable",
            bud_id=uuid_mod.UUID(payload.bud_id),
            skill_id=_skill_uuid,
            task_id=_task_uuid,
            repo_id=_repo_uuid,
            bud_number=payload.bud_number,
            bud_title=payload.title,
        )
        if design_id:
            await _update_design_status(design_id, payload.org_id, "failed")
        await _maybe_complete_design_task(payload.bud_id, payload.org_id)
        update_job(
            job_id,
            state=JobState.FAILED,
            error=result.error or "AI unavailable",
            error_code=result.error_code,
        )
        return

    update_job(job_id, status_message="Verifying wireframe...", progress_pct=80)

    # The agent persists its HTML via the ``write_bud_design`` MCP tool —
    # we only check the DB to confirm the row was set to READY. The reply
    # text is best-effort: parse the JSON response if present, otherwise
    # fall back to a generic message (a contaminated stdout no longer
    # blocks persistence).
    wireframe_saved = await _design_was_saved(design_id, payload.org_id) if design_id else False

    reply = "Design wireframe generated."
    response = parse_chat_response(result.output)
    if response and response.reply:
        reply = response.reply

    if not wireframe_saved and design_id:
        await _update_design_status(design_id, payload.org_id, "failed")
        logger.warning(
            "design_no_mcp_write",
            design_id=design_id,
            output_preview=result.output[:200],
        )

    final_state = JobState.COMPLETED if wireframe_saved else JobState.FAILED
    final_error = None if wireframe_saved else "Agent did not call write_bud_design MCP"

    # Roll up the parent ``bud_agent_tasks`` row state BEFORE emitting
    # the ``skill_completed`` event. The frontend listener reacts to
    # that event by calling ``fetchBUD`` — if the task row hasn't
    # been flipped to COMPLETED/FAILED yet, the response carries a
    # stale ``active_agent_task.status='running'`` and ``agentLocked``
    # stays true (edit button greyed) until the next page load.
    # Wrapped in try/except so a DB failure here doesn't skip the
    # session/timeline/job-state writes below.
    try:
        await _maybe_complete_design_task(payload.bud_id, payload.org_id)
    except Exception:
        logger.warning(
            "design_task_rollup_failed",
            bud_id=payload.bud_id,
            design_id=design_id,
        )

    _final_event = "skill_completed" if wireframe_saved else "skill_failed"
    await log_agent_activity(
        None,
        org_id=_org_uuid,
        event_type=_final_event,
        skill_slug="designer",
        message=f"Designer {'completed' if wireframe_saved else 'failed'} for {bud_ref}",
        bud_id=uuid_mod.UUID(payload.bud_id),
        skill_id=_skill_uuid,
        task_id=_task_uuid,
        repo_id=_repo_uuid,
        metadata_={"design_id": design_id, "repo_id": repo_id} if wireframe_saved else None,
        bud_number=payload.bud_number,
        bud_title=payload.title,
    )

    # Persist the originating-agent CLI session id (per-design row) so
    # design-tab chats on this wireframe can ``--resume`` against it.
    if wireframe_saved and design_id:
        await record_originating_session(
            org_id=_org_uuid,
            bud_id=uuid_mod.UUID(payload.bud_id),
            section="design",
            session_id=originating_session_id,
            design_id=uuid_mod.UUID(design_id),
        )

    # Re-estimate with design complexity context
    if wireframe_saved:
        try:
            await _estimate_after_design(payload.bud_id, payload.org_id)
        except Exception:
            logger.warning("design_estimation_failed", bud_id=payload.bud_id)

    if wireframe_saved:
        event_type = "design_generated"
        detail = {"design_id": design_id, "repo_id": repo_id}
    else:
        event_type = "ai_agent_failed"
        detail = {"agent": "designer", "section": "design", "job_id": job_id}
    await record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        event_type,
        skill_name="designer",
        section="design",
        job_id=job_id,
        extra_detail=detail,
    )

    update_job(
        job_id,
        state=final_state,
        result={
            "reply": reply,
            "design_id": design_id,
        },
        status_message="Design wireframe ready" if wireframe_saved else "No wireframe generated",
        progress_pct=100,
        error=final_error,
    )


async def _maybe_complete_design_task(bud_id: str, org_id: str) -> None:
    """Mark design BUDAgentTask as complete/failed when no designs are still generating."""
    from app.database import AsyncSessionLocal
    from app.models.bud import BUDDesignStatus
    from app.models.bud_agent_task import AgentTaskStatus
    from app.repositories.bud import BUDDesignRepository
    from app.repositories.bud_agent_task import BUDAgentTaskRepository

    async with AsyncSessionLocal() as db:
        design_repo = BUDDesignRepository(db, org_id=uuid_mod.UUID(org_id))
        still_generating = await design_repo.count_by_status(
            uuid_mod.UUID(bud_id),
            BUDDesignStatus.GENERATING,
        )
        if still_generating > 0:
            return

        task_repo = BUDAgentTaskRepository(db, org_id=uuid_mod.UUID(org_id))
        task = await task_repo.get_active_for_bud(uuid_mod.UUID(bud_id))
        if task and task.task_type == "design":
            ready_count = await design_repo.count_by_status(
                uuid_mod.UUID(bud_id),
                BUDDesignStatus.READY,
            )
            if ready_count > 0:
                task.status = AgentTaskStatus.COMPLETED
            else:
                task.status = AgentTaskStatus.FAILED
                task.error_message = "Design generation failed"
            await db.commit()


async def handle_design_extract_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Extract a design system from a tracked repository via LLM."""
    from datetime import UTC, datetime

    payload = DesignExtractJobPayload(**raw_payload)

    update_job(job_id, status_message="Discovering design files...", progress_pct=10)

    repo_path = Path(payload.repo_path)
    if not repo_path.exists():
        update_job(
            job_id,
            state=JobState.FAILED,
            error=f"Repository path not found: {payload.repo_path}",
        )
        return

    update_job(
        job_id,
        status_message="Analyzing with AI (this may take a few minutes)...",
        progress_pct=20,
    )

    from app.services.design_system_extractor import extract_design_system
    from app.services.platforms import get_platform

    try:
        platform = get_platform(payload.platform)
    except KeyError:
        update_job(
            job_id,
            state=JobState.FAILED,
            error=f"Unknown platform slug in payload: {payload.platform!r}",
        )
        return

    extraction = await extract_design_system(repo_path, platform)

    if extraction.error:
        update_job(
            job_id,
            status_message=f"LLM failed ({extraction.error}), used regex fallback...",
            progress_pct=70,
        )

    update_job(job_id, status_message="Saving to database...", progress_pct=80)

    from app.database import AsyncSessionLocal
    from app.repositories.design_system import DesignSystemRefRepository

    async with AsyncSessionLocal() as db:
        try:
            ds_repo = DesignSystemRefRepository(db, org_id=uuid_mod.UUID(payload.org_id))

            if payload.is_default:
                existing_default = await ds_repo.get_default()
                if (
                    existing_default is not None
                    and str(existing_default.repo_id) != payload.repo_id
                ):
                    existing_default.is_default = False

            ds = await ds_repo.upsert(
                repo_id=uuid_mod.UUID(payload.repo_id),
                content=extraction.content,
                source_hash=extraction.source_hash,
                extracted_at=datetime.now(UTC),
                is_default=payload.is_default,
            )
            await db.commit()

            logger.info(
                "design_system_extracted",
                ds_id=str(ds.id),
                repo_path=payload.repo_path,
            )
        except Exception:
            await db.rollback()
            raise

    status_msg = "Design system extracted"
    if extraction.method == "regex_fallback":
        status_msg = "Extracted (regex fallback — re-extract when AI is available)"

    update_job(
        job_id,
        state=JobState.COMPLETED,
        result={
            "status": "extracted",
            "method": extraction.method,
            "error": extraction.error,
        },
        status_message=status_msg,
        progress_pct=100,
    )


# ── Design helpers ────────────────────────────────────────────────


async def _design_was_saved(design_id: str, org_id: str) -> bool:
    """Check whether the agent's ``write_bud_design`` MCP call landed.

    Returns True iff the row is in READY state with non-empty HTML —
    i.e. the agent finished its iteration cleanly. Used in place of
    stdout-JSON parsing, which is fragile when learning-mode prefixes
    or other prose leak into the subprocess output.
    """
    async with AsyncSessionLocal() as db:
        repo = BUDDesignRepository(db, org_id=uuid_mod.UUID(org_id))
        design = await repo.get_by_id(uuid_mod.UUID(design_id))
        if design is None:
            return False
        return design.status == BUDDesignStatus.READY and bool(design.design_html)


async def _update_design_status(
    design_id: str,
    org_id: str,
    status_str: str,
) -> None:
    """Update the status of a bud_designs row (e.g., on failure)."""
    from app.database import AsyncSessionLocal
    from app.models.bud import BUDDesignStatus
    from app.repositories.bud import BUDDesignRepository

    async with AsyncSessionLocal() as db:
        repo = BUDDesignRepository(db, org_id=uuid_mod.UUID(org_id))
        design = await repo.get_by_id(uuid_mod.UUID(design_id))
        if design is not None:
            design.status = BUDDesignStatus(status_str)
            await db.commit()


async def _estimate_after_design(bud_id: str, org_id: str) -> None:
    """Re-estimate delivery dates after a design wireframe is generated."""
    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDRepository
    from app.services.bud_estimation import estimate_bud_dates

    async with AsyncSessionLocal() as db:
        bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(org_id))
        bud = await bud_repo.get_by_id(uuid_mod.UUID(bud_id))
        if bud:
            await estimate_bud_dates(db, uuid_mod.UUID(org_id), bud, trigger="design_completed")
            await db.commit()
