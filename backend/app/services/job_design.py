# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Design job handlers for wireframe generation and design system extraction.

Handles:
- Design agent job: generates wireframes using Claude + design system context
- Design extract job: extracts design systems from tracked repositories
"""

import re
import uuid as uuid_mod
from pathlib import Path
from typing import Any

import structlog

from app.schemas.jobs import DesignAgentJobPayload, DesignExtractJobPayload, JobState
from app.services.agent_activity_logger import log_agent_activity
from app.services.chat_persistence import persist_design
from app.services.chat_prompts import build_design_prompt
from app.services.job_chat import _parse_chat_response
from app.services.job_queue import update_job
from app.services.job_utils import (
    build_mcp_config,
    make_progress_callback,
    record_agent_timeline,
    resolve_repo_path,
)
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

    # Prefer MCP-based design system access
    design_tools = ["list_design_systems", "get_design_system"]
    mcp_config = build_mcp_config(payload.org_id, tool_names=design_tools)
    use_mcp = mcp_config is not None

    prompt, ds_temp_file = await build_design_prompt(
        bud_ref=bud_ref,
        title=payload.title,
        org_id=payload.org_id,
        current_content="",
        message=(
            f"Generate an initial wireframe for {bud_ref}: {payload.title}.\n\n"
            "## BUD Requirements\n\n"
            f"{payload.requirements_md}\n\n"
            "Create a wireframe covering the key screens and interactions "
            "described in the requirements. Focus on layout, information "
            "architecture, and user flow."
            f"{scope_note}"
        ),
        repo_id=repo_id,
        use_mcp=use_mcp,
        repo_name=repo_name,
    )

    update_job(
        job_id,
        status_message="Generating wireframe (this may take a few minutes)...",
        progress_pct=20,
    )

    from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

    # Read config from the designer skill
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

    sys_files = [str(ds_temp_file)] if ds_temp_file else []
    try:
        result = await run_claude_code(
            prompt=prompt,
            working_dir=repo_path,
            config=ClaudeRunnerConfig(
                max_turns=designer_skill.max_turns if designer_skill else 0,
                timeout_seconds=900,
                system_prompt_files=sys_files,
                mcp=mcp_config,
                model=(designer_skill.model or None) if designer_skill else None,
                effort=(designer_skill.effort or None) if designer_skill else None,
            ),
            progress_callback=make_progress_callback(job_id),
        )
    finally:
        if ds_temp_file is not None:
            ds_temp_file.unlink(missing_ok=True)

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

    update_job(job_id, status_message="Saving wireframe...", progress_pct=80)

    # Try to read wireframe from the expected file path
    wireframe_html = None
    reply = "Design wireframe generated."
    rel_path: str | None = None
    expected_path = (
        Path(repo_path) / ".bodhiorchard" / "wireframes" / bud_ref / "wireframe.html"
        if repo_path
        else None
    )

    if expected_path and expected_path.exists():
        wireframe_html = expected_path.read_text(encoding="utf-8")
        rel_path = f".bodhiorchard/wireframes/{bud_ref}/wireframe.html"
        # Try to get reply from Claude's JSON response
        response = _parse_chat_response(result.output)
        if response and response.get("reply"):
            reply = response["reply"]
    else:
        # Fallback: try parsing from output text
        response = _parse_chat_response(result.output)
        if response:
            wireframe_html = response.get("updated_content")
            reply = response.get("reply", reply)
        else:
            wireframe_html = _extract_html_from_output(result.output)

    # Persist to bud_designs table
    if wireframe_html and design_id:
        await persist_design(design_id, payload.org_id, wireframe_html, design_path=rel_path)
    elif design_id:
        await _update_design_status(design_id, payload.org_id, "failed")
        logger.warning(
            "design_no_html_extracted",
            design_id=design_id,
            output_preview=result.output[:200],
        )

    final_state = JobState.COMPLETED if wireframe_html else JobState.FAILED
    final_error = None if wireframe_html else "AI returned text instead of HTML wireframe"

    _final_event = "skill_completed" if wireframe_html else "skill_failed"
    await log_agent_activity(
        None,
        org_id=_org_uuid,
        event_type=_final_event,
        skill_slug="designer",
        message=f"Designer {'completed' if wireframe_html else 'failed'} for {bud_ref}",
        bud_id=uuid_mod.UUID(payload.bud_id),
        skill_id=_skill_uuid,
        task_id=_task_uuid,
        repo_id=_repo_uuid,
        metadata_={"design_id": design_id, "repo_id": repo_id} if wireframe_html else None,
        bud_number=payload.bud_number,
        bud_title=payload.title,
    )

    # Re-estimate with design complexity context
    if wireframe_html:
        try:
            await _estimate_after_design(payload.bud_id, payload.org_id)
        except Exception:
            logger.warning("design_estimation_failed", bud_id=payload.bud_id)

    if wireframe_html:
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
        status_message="Design wireframe ready" if wireframe_html else "No wireframe generated",
        progress_pct=100,
        error=final_error,
    )

    # Check if all design jobs for this BUD are done — complete the tracking task
    await _maybe_complete_design_task(payload.bud_id, payload.org_id)


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


def _extract_html_from_output(output: str) -> str | None:
    """Extract an HTML document from mixed AI output.

    Claude often wraps wireframes in narrative text or markdown code fences.
    This tries multiple strategies to isolate just the HTML:

    1. Markdown ```html code fence (most common with explanatory output).
    2. <!DOCTYPE html>...</html> or <html>...</html> block.
    3. HTML fragment starting with <meta>, <head>, <link>, or <style>
       (Claude sometimes omits the <html> wrapper).
    4. Entire output if it starts with a tag and contains closing tags.

    Args:
        output: Raw AI text output that may contain embedded HTML.

    Returns:
        Extracted HTML string, or None if no HTML found.
    """
    text = output.strip()

    # 1. Extract from ```html code fence
    html_fence = re.search(r"```html\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if html_fence:
        return html_fence.group(1).strip()

    # 2. Extract <!DOCTYPE html>...</html> or <html...>...</html>
    doctype_match = re.search(
        r"(<!DOCTYPE\s+html[^>]*>.*?</html>)", text, re.DOTALL | re.IGNORECASE
    )
    if doctype_match:
        return doctype_match.group(1).strip()

    html_tag_match = re.search(r"(<html[^>]*>.*?</html>)", text, re.DOTALL | re.IGNORECASE)
    if html_tag_match:
        return html_tag_match.group(1).strip()

    # 3. HTML fragment embedded in prose
    fragment_match = re.search(
        r"(<!DOCTYPE\s+html|<html|<head|<meta\s|<link\s|<style)",
        text,
        re.IGNORECASE,
    )
    if fragment_match:
        html_start = fragment_match.start()
        extracted = text[html_start:].strip()
        # Only accept if it has substantial HTML content (not just a stray tag in prose)
        if len(extracted) > 200:
            return extracted

    # 4. Entire output if it starts with a tag and contains closing markers
    if text.startswith("<") and ("</html>" in text.lower() or "</body>" in text.lower()):
        return text

    return None


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
