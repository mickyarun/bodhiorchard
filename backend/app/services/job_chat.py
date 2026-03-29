"""Chat job handler for async BUD section editing via Claude.

Handles the BUD chat workflow: builds prompts, runs Claude,
parses responses, and persists content updates to the database.
"""

import asyncio
import uuid as uuid_mod
from pathlib import Path
from typing import Any

import structlog

from app.agents.skill_mapping import SECTION_SKILL_MAP
from app.schemas.bud import SECTION_LABELS
from app.schemas.jobs import ChatJobPayload, JobState
from app.services.agent_activity_logger import log_agent_activity
from app.services.chat_persistence import persist_chat_message, persist_chat_update, persist_design
from app.services.chat_prompts import build_chat_prompt, build_design_prompt, fetch_chat_history
from app.services.job_queue import update_job
from app.services.job_utils import (
    build_mcp_config,
    make_progress_callback,
    record_agent_timeline,
    resolve_repo_path,
    save_image_temp,
    section_locks,
)
from app.services.skill_loader import load_skill

logger = structlog.get_logger(__name__)


async def handle_chat_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Process a BUD chat request via Claude Code CLI.

    Builds the prompt, runs Claude, parses the response, and
    persists any content updates to the database.

    Uses a per-section lock to serialize concurrent chats on the same
    BUD section, preventing conflicting content overwrites when multiple
    users edit simultaneously.
    """
    payload = ChatJobPayload(**raw_payload)

    # Serialize chat jobs per BUD + section to prevent conflicting edits
    lock_key = f"{payload.bud_id}:{payload.section}"
    if payload.design_id:
        lock_key += f":{payload.design_id}"
    lock = section_locks.setdefault(lock_key, asyncio.Lock())

    async with lock:
        await _run_chat_job(job_id, payload)


async def _run_chat_job(job_id: str, payload: ChatJobPayload) -> None:
    """Inner chat handler, called under the per-section lock."""
    update_job(job_id, status_message="Preparing prompt...", progress_pct=10)

    section_label = SECTION_LABELS[payload.section]

    bud_ref = f"BUD-{payload.bud_number:03d}"

    # Fetch recent chat history for LLM context
    history = await fetch_chat_history(
        bud_id=payload.bud_id,
        org_id=payload.org_id,
        section=payload.section,
        design_id=payload.design_id,
        session_id=payload.session_id,
    )

    ds_temp_file: Path | None = None
    repo_path: str | None = None
    mcp_config = None

    if payload.section == "design":
        # Prefer MCP-based design system access (Claude queries on-demand)
        design_tools = ["list_design_systems", "get_design_system"]
        mcp_config = build_mcp_config(payload.org_id, tool_names=design_tools)
        use_mcp = mcp_config is not None

        prompt, ds_temp_file = await build_design_prompt(
            bud_ref,
            payload.title,
            payload.org_id,
            payload.current_content,
            payload.message,
            repo_id=payload.repo_id,
            history=history,
            use_mcp=use_mcp,
        )
        repo_path = await resolve_repo_path(payload.repo_id, payload.org_id)
    else:
        prompt = build_chat_prompt(
            bud_ref,
            payload.title,
            section_label,
            payload.current_content,
            payload.message,
            history=history,
        )

    # Save pasted images to temp files for Claude to read
    image_paths: list[Path] = []
    if payload.images:
        for i, data_url in enumerate(payload.images):
            p = save_image_temp(data_url, i)
            if p:
                image_paths.append(p)

    if image_paths:
        prompt += "\n\n## Attached Images\n\n"
        prompt += "The user pasted the following images. Read each file to view them:\n"
        for p in image_paths:
            prompt += f"- {p}\n"

    update_job(job_id, status_message="Waiting for AI response...", progress_pct=20)

    skill_name = SECTION_SKILL_MAP.get(payload.section, "product-manager")
    _chat_org_id = payload.org_id

    await log_agent_activity(
        None, org_id=uuid_mod.UUID(_chat_org_id), event_type="skill_invoked",
        skill_slug=skill_name,
        message=f"Chat '{skill_name}' invoked for {payload.section}",
        bud_id=uuid_mod.UUID(payload.bud_id),
    )

    from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

    # Read config from the skill definition
    skill_name = SECTION_SKILL_MAP.get(payload.section, "product-manager")
    try:
        skill = load_skill(skill_name)
    except FileNotFoundError:
        skill = None

    # Design section needs a longer timeout (matches design agent job)
    chat_timeout = 900 if payload.section == "design" else 300

    sys_files = [str(ds_temp_file)] if ds_temp_file else []
    try:
        result = await run_claude_code(
            prompt=prompt,
            working_dir=repo_path,
            config=ClaudeRunnerConfig(
                max_turns=skill.max_turns if skill else 0,
                timeout_seconds=chat_timeout,
                system_prompt_files=sys_files,
                mcp=mcp_config,
                model=(skill.model or None) if skill else None,
                effort=(skill.effort or None) if skill else None,
            ),
            progress_callback=make_progress_callback(job_id),
        )
    finally:
        if ds_temp_file is not None:
            ds_temp_file.unlink(missing_ok=True)
        for p in image_paths:
            p.unlink(missing_ok=True)

    if not result.success:
        await log_agent_activity(
            None, org_id=uuid_mod.UUID(_chat_org_id), event_type="skill_failed",
            skill_slug=skill_name,
            message=result.error or "AI unavailable",
            bud_id=uuid_mod.UUID(payload.bud_id),
        )
        update_job(job_id, state=JobState.FAILED, error=result.error or "AI unavailable")
        await record_agent_timeline(
            payload.org_id,
            payload.bud_id,
            "ai_agent_failed",
            skill_name=SECTION_SKILL_MAP.get(payload.section, "product-manager"),
            section=payload.section,
            job_id=job_id,
        )
        return

    update_job(job_id, status_message="Processing response...", progress_pct=80)

    response = _parse_chat_response(result.output)
    if response is None:
        reply_text = result.output[:3000]
        await persist_chat_message(
            payload.bud_id,
            payload.org_id,
            payload.section,
            "ai",
            reply_text,
            payload.design_id,
            session_id=payload.session_id,
        )
        await log_agent_activity(
            None, org_id=uuid_mod.UUID(_chat_org_id), event_type="skill_completed",
            skill_slug=skill_name,
            message=f"Chat '{skill_name}' completed for {payload.section}",
            bud_id=uuid_mod.UUID(payload.bud_id),
        )
        update_job(
            job_id,
            state=JobState.COMPLETED,
            result={"reply": reply_text, "updated_content": None},
            progress_pct=100,
            status_message="Complete",
        )
        return

    # Persist content update to DB if present
    updated = response.get("updated_content")
    if updated is not None:
        if payload.section == "design" and payload.design_id:
            await persist_design(payload.design_id, payload.org_id, updated)
        elif payload.section != "design":
            await persist_chat_update(payload.bud_id, payload.org_id, payload.section, updated)

    reply_text = response.get("reply", "Done.")
    await persist_chat_message(
        payload.bud_id,
        payload.org_id,
        payload.section,
        "ai",
        reply_text,
        payload.design_id,
        session_id=payload.session_id,
    )

    await log_agent_activity(
        None, org_id=uuid_mod.UUID(_chat_org_id), event_type="skill_completed",
        skill_slug=skill_name,
        message=f"Chat '{skill_name}' completed for {payload.section}",
        bud_id=uuid_mod.UUID(payload.bud_id),
    )

    update_job(
        job_id,
        state=JobState.COMPLETED,
        result={"reply": reply_text, "updated_content": updated},
        status_message="Complete",
        progress_pct=100,
    )

    await record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        "ai_agent_completed",
        skill_name=skill_name,
        section=payload.section,
        job_id=job_id,
    )




def _parse_chat_response(output: str) -> dict[str, Any] | None:
    """Parse and validate AI chat response against expected schema.

    Uses Pydantic validation to ensure response only contains
    ``reply`` and ``updated_content`` — rejects unexpected fields.
    """
    from app.services.json_parser import parse_chat_response

    validated = parse_chat_response(output)
    return validated.model_dump() if validated else None
