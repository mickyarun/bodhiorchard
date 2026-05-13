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
from app.database import AsyncSessionLocal
from app.schemas.bud import SECTION_LABELS
from app.schemas.jobs import ChatJobPayload, JobState
from app.services.agent_activity_logger import log_agent_activity
from app.services.chat_persistence import persist_chat_message, persist_chat_update
from app.services.chat_prompts import build_chat_prompt, build_design_prompt, fetch_chat_history
from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code
from app.services.job_queue import update_job
from app.services.job_utils import (
    build_mcp_config,
    make_progress_callback,
    record_agent_timeline,
    resolve_repo_path,
    save_image_temp,
    section_locks,
)
from app.services.skill_loader import load_skill, load_skill_for_org

logger = structlog.get_logger(__name__)

# A small-edit chat needs at most: fetch prior wireframe, optionally fetch
# design system, write back. Four turns is the comfortable ceiling — the
# initial design agent keeps its 10-turn budget via the skill config.
DESIGN_ITERATION_MAX_TURNS = 4

# Anthropic prompt-cache TTL is 5 minutes and ``--resume`` is documented to
# invalidate the cache on very long sessions. Skip resume when the chat has
# accumulated past these thresholds — a fresh session is faster than a
# session whose cache will miss anyway.
RESUME_HISTORY_MSG_CAP = 50
# Bytes-of-content cap is conservative: real prompt size is ~1.5–2× the
# content bytes once role tags and chat scaffolding are added, so we cap
# below the 100KB target to leave headroom.
RESUME_HISTORY_BYTE_CAP = 60_000
# Per-message overhead used in the byte estimate (role tag + framing).
_RESUME_HISTORY_MSG_OVERHEAD = 200


def _should_resume_session(history: list[dict[str, str]] | None) -> bool:
    """Return True when reusing the CLI session via ``--resume`` is worthwhile.

    Returns False on long histories where the documented cache-invalidation
    behaviour on resume would make the round-trip slower, not faster.
    Adds a fixed per-message overhead so role tags and chat scaffolding
    aren't undercounted vs the raw content bytes.
    """
    if not history:
        return True
    if len(history) > RESUME_HISTORY_MSG_CAP:
        return False
    total = sum(len(m.get("message") or "") + _RESUME_HISTORY_MSG_OVERHEAD for m in history)
    return total <= RESUME_HISTORY_BYTE_CAP


def _is_subsequent_iteration(history: list[dict[str, str]] | None) -> bool:
    """Return True if a prior AI reply exists for this chat thread.

    First message in a thread → no prior AI message → ``False`` →
    caller should use ``--session-id`` to claim the namespace. Once an
    AI reply lands, subsequent calls use ``--resume`` to load the same
    CLI session from disk and warm the Anthropic prompt cache.
    """
    if not history:
        return False
    return any(m.get("role") == "ai" for m in history)


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

    repo_path: str | None = None
    mcp_config = None

    if payload.section == "design":
        # Design tools: read/write the wireframe row + browse design system.
        # Persistence is fully MCP-driven — no temp-file or stdout-JSON path.
        design_tools = [
            "list_design_systems",
            "get_design_system",
            "get_bud_designs",
            "write_bud_design",
        ]
        mcp_config = build_mcp_config(payload.org_id, tool_names=design_tools)

        repo_path = await resolve_repo_path(payload.repo_id, payload.org_id)
        _repo_name = Path(repo_path).name if repo_path else None
        prompt = await build_design_prompt(
            bud_ref,
            payload.title,
            payload.org_id,
            payload.message,
            payload.bud_id,
            repo_id=payload.repo_id,
            history=history,
            repo_name=_repo_name,
        )
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
        None,
        org_id=uuid_mod.UUID(_chat_org_id),
        event_type="skill_invoked",
        skill_slug=skill_name,
        message=f"Chat '{skill_name}' invoked for {payload.section}",
        bud_id=uuid_mod.UUID(payload.bud_id),
    )

    # Read config from the per-org skill row so admin edits to model /
    # max_turns / iteration_model in Settings → Agent Prompts take effect
    # without a redeploy. Fall back to the file default if the DB row is
    # missing (e.g. a fresh-install org that hasn't been seeded yet).
    try:
        async with AsyncSessionLocal() as _skill_db:
            skill = await load_skill_for_org(skill_name, uuid_mod.UUID(_chat_org_id), _skill_db)
    except (ValueError, LookupError):
        try:
            skill = load_skill(skill_name)
        except FileNotFoundError:
            skill = None

    # Design section needs a longer timeout (matches design agent job)
    chat_timeout = 900 if payload.section == "design" else 300

    # Iteration-specific design overrides: Haiku for speed, tighter turn
    # cap because the agent is editing an existing wireframe, and
    # ``--resume`` so the Anthropic prompt cache stays warm across the
    # hot iteration loop. The initial JOB_DESIGN_AGENT run keeps the
    # skill's Sonnet + max_turns config — only chat iteration changes.
    is_design_iteration = payload.section == "design"
    skill_model = (skill.model or None) if skill else None
    skill_turns = skill.max_turns if skill else 0
    # Iteration model comes from the skill's ``iteration_model`` field
    # (configurable in the agent-prompt frontend). Falls back to the skill's
    # main ``model`` when empty. Only the design section applies the
    # turn-cap override — other sections keep the skill's own turn budget.
    skill_iteration_model = (skill.iteration_model or skill.model or None) if skill else None
    iteration_model = skill_iteration_model if is_design_iteration else skill_model
    iteration_turns = DESIGN_ITERATION_MAX_TURNS if is_design_iteration else skill_turns

    # CLI session wiring for prompt-cache warmth across iterations.
    # First message in a thread → no prior AI reply → claim the namespace
    # with ``--session-id <uuid>``. Subsequent messages → ``--resume <uuid>``
    # so the CLI loads the prior session file and Anthropic returns a cache
    # hit on the stable prefix.
    cli_session_id: str | None = None
    is_resume = False
    if is_design_iteration and payload.session_id and _should_resume_session(history):
        cli_session_id = payload.session_id
        is_resume = _is_subsequent_iteration(history)

    def _build_config(*, session_id: str | None, resume: bool) -> ClaudeRunnerConfig:
        return ClaudeRunnerConfig(
            max_turns=iteration_turns,
            timeout_seconds=chat_timeout,
            mcp=mcp_config,
            model=iteration_model,
            effort=(skill.effort or None) if skill else None,
            cli_session_id=session_id,
            is_resume=resume,
        )

    try:
        result = await run_claude_code(
            prompt=prompt,
            working_dir=repo_path,
            config=_build_config(session_id=cli_session_id, resume=is_resume),
            progress_callback=make_progress_callback(job_id),
        )
        # Both ``--session-id`` and ``--resume`` can fail when the CLI's
        # session-file state disagrees with what we passed (backend restart
        # between iterations, stale client-provided id, a session file
        # already existing for a brand-new id we tried to claim, etc.).
        # Retry once dropping session affinity entirely — we pay the
        # cache-creation cost on this turn but the user's edit still
        # lands; the next turn re-warms with a fresh session.
        if not result.success and cli_session_id:
            logger.warning(
                "design_chat_retry_without_session_affinity",
                session_id=cli_session_id,
                was_resume=is_resume,
                error_code=result.error_code,
            )
            result = await run_claude_code(
                prompt=prompt,
                working_dir=repo_path,
                config=_build_config(session_id=None, resume=False),
                progress_callback=make_progress_callback(job_id),
            )
    finally:
        for p in image_paths:
            p.unlink(missing_ok=True)

    if not result.success:
        await log_agent_activity(
            None,
            org_id=uuid_mod.UUID(_chat_org_id),
            event_type="skill_failed",
            skill_slug=skill_name,
            message=result.error or "AI unavailable",
            bud_id=uuid_mod.UUID(payload.bud_id),
        )
        update_job(
            job_id,
            state=JobState.FAILED,
            error=result.error or "AI unavailable",
            error_code=result.error_code,
        )
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
            None,
            org_id=uuid_mod.UUID(_chat_org_id),
            event_type="skill_completed",
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

    # Persist non-design content updates from the JSON reply. Design
    # wireframes are persisted by the agent itself via the
    # ``write_bud_design`` MCP tool — we no longer parse stdout for HTML.
    updated: str | None = None
    if payload.section != "design":
        updated = response.get("updated_content")
        if updated is not None:
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
        None,
        org_id=uuid_mod.UUID(_chat_org_id),
        event_type="skill_completed",
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
