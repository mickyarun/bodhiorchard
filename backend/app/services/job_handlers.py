"""Job handlers for the async queue system.

Each handler receives a job_id and payload dict, performs the work,
and calls update_job() to report progress. Handlers run in worker
tasks and must not raise — they should catch errors and call
update_job(state=FAILED) instead.
"""

import asyncio
import os
import tempfile
import uuid as uuid_mod
from pathlib import Path
from typing import Any

import structlog

from app.agents.skill_mapping import SECTION_SKILL_MAP
from app.schemas.bud import SECTION_LABELS
from app.schemas.jobs import (
    ChatJobPayload,
    CodeReviewJobPayload,
    DesignAgentJobPayload,
    DesignExtractJobPayload,
    JobState,
    PRDAgentJobPayload,
    TechArchJobPayload,
    TriageJobPayload,
)
from app.services.claude_runner import ProgressCallback
from app.services.job_queue import (
    JOB_BUD_CHAT,
    JOB_CODE_REVIEW,
    JOB_DESIGN_AGENT,
    JOB_DESIGN_EXTRACT,
    JOB_PRD_AGENT,
    JOB_TECH_ARCH,
    JOB_TRIAGE,
    register_job_type,
    update_job,
)
from app.services.skill_loader import load_skill

logger = structlog.get_logger(__name__)

# ── Real-time progress for Claude agent jobs ──────────────────────


def _format_tool_progress(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Format a human-readable progress message from a tool_use event."""
    short = tool_name.split("__")[-1] if "__" in tool_name else tool_name

    # Extract common fields
    file_path = tool_input.get("file_path", "")
    if file_path:
        file_path = file_path.rsplit("/", 1)[-1]  # basename only

    match short:
        # Claude built-in tools — show detail from input
        case "Read":
            return f"Reading {file_path}..." if file_path else "Reading file..."
        case "Write":
            return f"Writing {file_path}..." if file_path else "Writing file..."
        case "Edit":
            return f"Editing {file_path}..." if file_path else "Editing file..."
        case "Glob":
            pattern = tool_input.get("pattern", "")
            return f"Finding {pattern}..." if pattern else "Finding files..."
        case "Grep":
            pattern = tool_input.get("pattern", "")
            return f"Searching for '{pattern[:40]}'..." if pattern else "Searching code..."
        case "Bash":
            cmd = tool_input.get("command", "")
            preview = cmd[:50].split("\n")[0]
            return f"Running: {preview}..." if preview else "Running command..."
        # MCP tools — static messages
        case "get_bud_context":
            return "Reading BUD requirements..."
        case "list_design_systems":
            return "Discovering design systems..."
        case "get_design_system":
            return "Loading design tokens..."
        case "update_task_status":
            return "Updating status..."
        case "check_feature_exists":
            return "Checking features..."
        case "search_bugs":
            return "Searching bugs..."
        case _:
            return f"Using {short}..."


def _make_progress_callback(job_id: str) -> ProgressCallback:
    """Create a progress callback that updates a job's status message on each tool call."""

    def _on_tool_use(tool_name: str, tool_input: dict[str, Any]) -> None:
        msg = _format_tool_progress(tool_name, tool_input)
        update_job(job_id, status_message=msg)

    return _on_tool_use


# Per-thread lock map for triage serialization
_thread_locks: dict[str, asyncio.Lock] = {}

# Per-section lock map for chat serialization.
# Prevents two concurrent chat jobs from reading the same section content,
# producing conflicting edits, and having last-write-wins overwrite the other.
_section_locks: dict[str, asyncio.Lock] = {}

# Max characters of chat history to include in LLM prompts
_HISTORY_CHAR_BUDGET = 2000


def setup_job_handlers() -> None:
    """Register all job types with the queue system.

    Called once from app lifespan before start_workers().
    To add a new job type, add a register_job_type() call here.
    """
    chat_workers = int(os.environ.get("JOB_CHAT_WORKERS", "2"))

    register_job_type(JOB_BUD_CHAT, handle_chat_job, worker_count=chat_workers)
    register_job_type(JOB_TRIAGE, handle_triage_job, worker_count=1)
    register_job_type(JOB_PRD_AGENT, handle_prd_job, worker_count=1)
    register_job_type(JOB_DESIGN_AGENT, handle_design_agent_job, worker_count=2)
    register_job_type(JOB_DESIGN_EXTRACT, handle_design_extract_job, worker_count=1)
    register_job_type(JOB_TECH_ARCH, handle_tech_arch_job, worker_count=1)
    register_job_type(JOB_CODE_REVIEW, handle_code_review_job, worker_count=1)


# ── Chat handler ───────────────────────────────────────────────────


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
    lock = _section_locks.setdefault(lock_key, asyncio.Lock())

    async with lock:
        await _run_chat_job(job_id, payload)


async def _run_chat_job(job_id: str, payload: ChatJobPayload) -> None:
    """Inner chat handler, called under the per-section lock."""
    update_job(job_id, status_message="Preparing prompt...", progress_pct=10)

    section_label = SECTION_LABELS[payload.section]

    bud_ref = f"BUD-{payload.bud_number:03d}"

    # Fetch recent chat history for LLM context
    history = await _fetch_chat_history(
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
        mcp_config = _build_mcp_config(payload.org_id, tool_names=design_tools)
        use_mcp = mcp_config is not None

        prompt, ds_temp_file = await _build_design_prompt(
            bud_ref,
            payload.title,
            payload.org_id,
            payload.current_content,
            payload.message,
            repo_id=payload.repo_id,
            history=history,
            use_mcp=use_mcp,
        )
        repo_path = await _resolve_repo_path(payload.repo_id, payload.org_id)
    else:
        prompt = _build_chat_prompt(
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
            p = _save_image_temp(data_url, i)
            if p:
                image_paths.append(p)

    if image_paths:
        prompt += "\n\n## Attached Images\n\n"
        prompt += "The user pasted the following images. Read each file to view them:\n"
        for p in image_paths:
            prompt += f"- {p}\n"

    update_job(job_id, status_message="Waiting for AI response...", progress_pct=20)

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
            progress_callback=_make_progress_callback(job_id),
        )
    finally:
        if ds_temp_file is not None:
            ds_temp_file.unlink(missing_ok=True)
        for p in image_paths:
            p.unlink(missing_ok=True)

    if not result.success:
        update_job(job_id, state=JobState.FAILED, error=result.error or "AI unavailable")
        await _record_agent_timeline(
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
        await _persist_chat_message(
            payload.bud_id,
            payload.org_id,
            payload.section,
            "ai",
            reply_text,
            payload.design_id,
            session_id=payload.session_id,
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
            await _persist_design(payload.design_id, payload.org_id, updated)
        elif payload.section != "design":
            await _persist_chat_update(payload.bud_id, payload.org_id, payload.section, updated)

    reply_text = response.get("reply", "Done.")
    await _persist_chat_message(
        payload.bud_id,
        payload.org_id,
        payload.section,
        "ai",
        reply_text,
        payload.design_id,
        session_id=payload.session_id,
    )

    update_job(
        job_id,
        state=JobState.COMPLETED,
        result={"reply": reply_text, "updated_content": updated},
        status_message="Complete",
        progress_pct=100,
    )

    await _record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        "ai_agent_completed",
        skill_name=skill_name,
        section=payload.section,
        job_id=job_id,
    )


# ── Triage handler ─────────────────────────────────────────────────


async def handle_triage_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Process a Slack triage event (start, continue, or approve/reject)."""
    payload = TriageJobPayload(**raw_payload)

    update_job(job_id, status_message=f"Processing {payload.action}...", progress_pct=10)

    thread_key = _get_thread_key(payload.event_data)
    lock = _thread_locks.setdefault(thread_key, asyncio.Lock())

    async with lock:
        from app.core.encryption import decrypt_secret
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            try:
                from app.api.v1.slack import _resolve_org_by_team_id

                org = await _resolve_org_by_team_id(db, payload.team_id)
                if org is None:
                    update_job(
                        job_id,
                        state=JobState.FAILED,
                        error=f"Organization not found for team {payload.team_id}",
                    )
                    return

                bot_token = decrypt_secret(org.slack_bot_token or "")
                if not bot_token:
                    update_job(job_id, state=JobState.FAILED, error="No bot token configured")
                    return

                from app.services.slack_intake import (
                    continue_triage,
                    handle_pm_approval,
                    start_triage,
                )

                event_data = payload.event_data

                if payload.action == "start_triage":
                    from app.schemas.slack import SlackReactionEvent

                    event = SlackReactionEvent.model_validate(event_data)
                    await start_triage(
                        db=db,
                        org=org,
                        bot_token=bot_token,
                        channel=event.item.channel,
                        message_ts=event.item.ts,
                        requester_slack_id=event.user,
                    )
                elif payload.action == "continue_triage":
                    from app.schemas.slack import SlackMessageEvent

                    event = SlackMessageEvent.model_validate(event_data)
                    await continue_triage(
                        db=db,
                        org=org,
                        bot_token=bot_token,
                        channel=event.channel,
                        thread_ts=event.thread_ts or event.ts,
                        new_message=event.text,
                        sender_slack_id=event.user or "",
                    )
                elif payload.action == "pm_approval":
                    from app.schemas.slack import SlackReactionEvent

                    event = SlackReactionEvent.model_validate(event_data)
                    await handle_pm_approval(
                        db=db,
                        org=org,
                        bot_token=bot_token,
                        channel=event.item.channel,
                        message_ts=event.item.ts,
                        approver_slack_id=event.user,
                        approved=payload.approved or False,
                    )

                await db.commit()
            except Exception:
                await db.rollback()
                raise

    update_job(job_id, state=JobState.COMPLETED, status_message="Done", progress_pct=100)


# ── PRD agent handler ──────────────────────────────────────────────


async def handle_prd_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Run the PRD agent to enrich a BUD with full specification."""
    payload = PRDAgentJobPayload(**raw_payload)

    update_job(job_id, status_message="Building PRD prompt...", progress_pct=10)

    from app.core.encryption import decrypt_secret
    from app.database import AsyncSessionLocal
    from app.models.organization import Organization
    from app.models.triage_session import TriageSession
    from app.repositories.bud import BUDRepository

    async with AsyncSessionLocal() as db:
        try:
            org = await db.get(Organization, uuid_mod.UUID(payload.org_id))

            org_id = org.id if org else uuid_mod.UUID(payload.org_id)
            bud_repo = BUDRepository(db, org_id=org_id)
            bud = await bud_repo.get_by_id(uuid_mod.UUID(payload.bud_id))

            session = await db.get(TriageSession, uuid_mod.UUID(payload.session_id))

            if not all([org, bud, session]):
                update_job(job_id, state=JobState.FAILED, error="BUD, org, or session not found")
                return

            bot_token = decrypt_secret(payload.bot_token_encrypted)
            if not bot_token:
                update_job(job_id, state=JobState.FAILED, error="Failed to decrypt bot token")
                return

            update_job(job_id, status_message="Running PM agent...", progress_pct=30)

            from app.services.slack_intake import _run_prd_agent

            await _run_prd_agent(db, org, bot_token, bud, session)

            # Clear prd_job_id from metadata so frontend stops showing the banner
            meta = dict(bud.metadata_ or {})
            meta.pop("prd_job_id", None)
            bud.metadata_ = meta

            await db.commit()
        except Exception:
            await db.rollback()
            raise

    await _record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        "ai_agent_completed",
        skill_name="product-manager",
        section="requirements_md",
        job_id=job_id,
    )

    update_job(
        job_id,
        state=JobState.COMPLETED,
        status_message="PRD complete",
        progress_pct=100,
    )


# ── Design agent handler (auto-trigger on phase transition) ───────


async def handle_design_agent_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Generate a design wireframe for a BUD using a repo-specific design system."""
    payload = DesignAgentJobPayload(**raw_payload)
    bud_ref = f"BUD-{payload.bud_number:03d}"
    repo_id = payload.repo_id
    design_id = payload.design_id

    update_job(job_id, status_message="Loading design system...", progress_pct=10)

    # Resolve repo path so Claude runs in the repo dir and reads its CLAUDE.md
    repo_path = await _resolve_repo_path(repo_id, payload.org_id)

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
    mcp_config = _build_mcp_config(payload.org_id, tool_names=design_tools)
    use_mcp = mcp_config is not None

    prompt, ds_temp_file = await _build_design_prompt(
        bud_ref=bud_ref,
        title=payload.title,
        org_id=payload.org_id,
        current_content="",
        message=(
            f"Generate an initial wireframe for {bud_ref}: {payload.title}.\n\n"
            "## BUD Requirements\n\n"
            f"{payload.requirements_md}\n\n"
            "Create a comprehensive wireframe that covers all the key screens "
            "and interactions described in the requirements. Focus on layout, "
            "information architecture, and user flow."
            f"{scope_note}"
        ),
        repo_id=repo_id,
        use_mcp=use_mcp,
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
            progress_callback=_make_progress_callback(job_id),
        )
    finally:
        if ds_temp_file is not None:
            ds_temp_file.unlink(missing_ok=True)

    if not result.success:
        if design_id:
            await _update_design_status(design_id, payload.org_id, "failed")
        update_job(job_id, state=JobState.FAILED, error=result.error or "AI unavailable")
        return

    update_job(job_id, status_message="Saving wireframe...", progress_pct=80)

    # Try to read wireframe from the expected file path
    wireframe_html = None
    reply = "Design wireframe generated."
    rel_path: str | None = None
    expected_path = (
        Path(repo_path) / ".flowdev" / "wireframes" / bud_ref / "wireframe.html"
        if repo_path
        else None
    )

    if expected_path and expected_path.exists():
        wireframe_html = expected_path.read_text(encoding="utf-8")
        rel_path = f".flowdev/wireframes/{bud_ref}/wireframe.html"
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
        await _persist_design(design_id, payload.org_id, wireframe_html, design_path=rel_path)
    elif design_id:
        await _update_design_status(design_id, payload.org_id, "failed")
        logger.warning(
            "design_no_html_extracted",
            design_id=design_id,
            output_preview=result.output[:200],
        )

    final_state = JobState.COMPLETED if wireframe_html else JobState.FAILED
    final_error = None if wireframe_html else "AI returned text instead of HTML wireframe"

    if wireframe_html:
        event_type = "design_generated"
        detail = {"design_id": design_id, "repo_id": repo_id}
    else:
        event_type = "ai_agent_failed"
        detail = {"agent": "designer", "section": "design", "job_id": job_id}
    await _record_agent_timeline(
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


# ── Design extract handler ────────────────────────────────────────


async def handle_design_extract_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Extract a design system from a tracked repository via LLM."""
    from datetime import UTC, datetime
    from pathlib import Path

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

    extraction = await extract_design_system(repo_path)

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


# ── Shared helpers ─────────────────────────────────────────────────


def _build_mcp_config(
    org_id: str,
    tool_names: list[str] | None = None,
) -> Any:
    """Build an MCPServerConfig for a Claude CLI run.

    Creates an internal MCP token scoped to the org and returns a config
    that the Claude runner will use to spawn the stdio bridge subprocess.

    Returns None if the MCP backend URL is not configured.
    """
    from app.services.claude_runner import MCPServerConfig

    try:
        from app.config import settings as app_settings
        from app.mcp.auth import create_internal_mcp_token

        if not app_settings.mcp_backend_url:
            return None

        token = create_internal_mcp_token(uuid_mod.UUID(org_id))
        return MCPServerConfig(
            backend_url=app_settings.mcp_backend_url,
            mcp_token=token,
            tool_names=tool_names or [],
        )
    except Exception:
        logger.warning("mcp_config_build_failed", org_id=org_id)
        return None


async def _resolve_repo_path(repo_id: str | None, org_id: str) -> str | None:
    """Look up a tracked repository's local path by its UUID.

    Returns the path string or None if not found / no repo_id given.
    """
    if not repo_id:
        return None
    from app.database import AsyncSessionLocal
    from app.models.tracked_repository import TrackedRepository

    try:
        async with AsyncSessionLocal() as db:
            tracked = await db.get(TrackedRepository, uuid_mod.UUID(repo_id))
            if tracked and tracked.org_id == uuid_mod.UUID(org_id):
                return tracked.path
            return None
    except Exception:
        logger.warning("resolve_repo_path_failed", repo_id=repo_id)
        return None


async def _fetch_chat_history(
    bud_id: str,
    org_id: str,
    section: str,
    design_id: str | None = None,
    session_id: str | None = None,
    limit: int = 10,
) -> list[dict[str, str]]:
    """Fetch recent chat messages for LLM context injection.

    Returns a list of dicts with 'role', 'user_name', 'message', 'created_at'.
    """
    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDChatMessageRepository

    async with AsyncSessionLocal() as db:
        chat_repo = BUDChatMessageRepository(db, org_id=uuid_mod.UUID(org_id))
        messages = await chat_repo.list_recent_messages(
            bud_id=uuid_mod.UUID(bud_id),
            section=section,
            design_id=uuid_mod.UUID(design_id) if design_id else None,
            session_id=uuid_mod.UUID(session_id) if session_id else None,
            limit=limit,
        )
        return [
            {
                "role": m.role,
                "user_name": m.user.name if m.user else None,
                "message": m.message,
                "created_at": m.created_at.strftime("%I:%M %p") if m.created_at else "",
            }
            for m in messages
        ]


def _format_history_block(history: list[dict[str, str]]) -> str:
    """Format chat history into a markdown block for prompt injection.

    Applies a character budget: if history exceeds ~2000 chars,
    keeps only the last 5 messages and prepends a note.
    """
    if not history:
        return ""

    def _fmt(msg: dict[str, str]) -> str:
        if msg["role"] == "user":
            name = msg.get("user_name") or "User"
            return f"[USER ({name}, {msg['created_at']})]: {msg['message']}"
        return f"[AI ({msg['created_at']})]: {msg['message']}"

    block = "\n".join(_fmt(m) for m in history)
    if len(block) > _HISTORY_CHAR_BUDGET:
        block = "Earlier messages omitted.\n" + "\n".join(_fmt(m) for m in history[-5:])

    return f"## Recent Conversation\n\n{block}\n"


async def _build_design_prompt(
    bud_ref: str,
    title: str,
    org_id: str,
    current_content: str,
    message: str,
    repo_id: str | None = None,
    history: list[dict[str, str]] | None = None,
    *,
    use_mcp: bool = False,
) -> tuple[str, Path | None]:
    """Build the Claude prompt for design wireframe generation.

    When ``use_mcp`` is True, the prompt tells Claude to call the
    ``get_design_system`` MCP tool instead of injecting the design system
    as a temp file.  This saves tokens when the DS is large but only
    partially needed.

    When ``use_mcp`` is False (or MCP is not configured for the run),
    falls back to the original temp-file approach.

    Returns:
        (prompt_text, optional_temp_file_path)
    """
    ds_content = ""
    ds_file: Path | None = None

    if not use_mcp:
        # Legacy: load DS and write to temp file for system prompt injection
        try:
            from app.database import AsyncSessionLocal
            from app.repositories.design_system import DesignSystemRefRepository

            async with AsyncSessionLocal() as db:
                ds_repo = DesignSystemRefRepository(db, org_id=uuid_mod.UUID(org_id))
                rid = uuid_mod.UUID(repo_id) if repo_id else None
                ds = await ds_repo.get_effective(repo_id=rid)
                if ds:
                    ds_content = ds.content
        except Exception:
            logger.warning("design_system_lookup_failed", org_id=org_id, repo_id=repo_id)

    parts = [
        f"You are designing a **visual HTML wireframe** for {bud_ref}: *{title}*.\n",
    ]

    if use_mcp:
        # MCP-based: Claude queries design systems on-demand
        if repo_id:
            mcp_hint = (
                f'Call `get_design_system` with `repo_id: "{repo_id}"` to get '
                "this repo's design system (primary).\n\n"
                "You can also call `list_design_systems` to see all available "
                "design systems across the organization. If other repos have "
                "relevant UI patterns, call `get_design_system` with their "
                "`repo_id` to cross-reference component styles and layouts."
            )
        else:
            mcp_hint = (
                "Call `list_design_systems` to see all available design systems, "
                "then call `get_design_system` with each relevant `repo_id` "
                "to fetch their content. Cross-reference multiple design "
                "systems to create a cohesive wireframe."
            )
        parts.append(
            "## Design System\n\n"
            f"{mcp_hint}\n\n"
            "Your wireframe MUST use the CDN boilerplate and color tokens "
            "from the primary design system. "
            "If no design system is available, use Vuetify 3 CDN with a clean "
            "dark theme as default.\n"
        )
    elif ds_content:
        fd, tmp_path = tempfile.mkstemp(
            suffix=".md",
            prefix="bodhigrove_design_system_",
        )
        os.close(fd)
        ds_file = Path(tmp_path)
        ds_file.write_text(ds_content, encoding="utf-8")

        parts.append(
            "## Design System\n\n"
            "The project's design system (colors, typography, component defaults, "
            "CDN boilerplate, and pattern library) has been loaded into your context. "
            "Your wireframe MUST use the CDN boilerplate and color tokens from it.\n"
        )
    else:
        parts.append(
            "## Design System\n\n"
            "No design system has been extracted for this organization. "
            "Use Vuetify 3 CDN with a clean dark theme as default.\n"
        )

    parts.append(
        "## Existing Application UI\n\n"
        "Read 2–3 existing Vue components or views from the `src/` directory "
        "to understand the current visual style, layout patterns, and component usage. "
        "Match your wireframe to these patterns.\n"
    )

    if current_content:
        parts.append(f"## Current Design\n\n```html\n{current_content}\n```\n")
    else:
        parts.append("## Current Design\n\nNo design exists yet. Create one from scratch.\n")

    # Inject conversation history for context
    if history:
        parts.append(_format_history_block(history))

    parts.append(f"## User Request\n\n{message}\n")

    parts.append(
        "## Instructions\n\n"
        f"1. Write the wireframe as a complete, self-contained HTML file to:\n"
        f"   `.flowdev/wireframes/{bud_ref}/wireframe.html`\n"
        "   Create the directory if it doesn't exist.\n\n"
        "2. The HTML file must:\n"
        "   - Use Vuetify CDN (with Vue 3) — no build step required\n"
        "   - Apply the project's design system colors and component defaults\n"
        "   - Include UX considerations as `<!-- UX: ... -->` HTML comments\n"
        "   - Include accessibility notes as `<!-- A11Y: ... -->` comments\n"
        "   - Render correctly when opened in any modern browser\n\n"
        "3. After writing the file, respond with a JSON object (no markdown fences):\n"
        '   {"reply": "<short explanation of design choices>", '
        '"updated_content": null}\n\n'
        "Focus on layout, information architecture, and interaction patterns. "
        "Use realistic placeholder data."
    )

    return "\n".join(parts), ds_file


def _build_chat_prompt(
    bud_ref: str,
    title: str,
    section_label: str,
    current_content: str,
    message: str,
    history: list[dict[str, str]] | None = None,
) -> str:
    """Build the Claude prompt for BUD section editing."""
    parts = [
        f"You are editing the **{section_label}** section of {bud_ref}: "
        f"*{title}*.\n\n"
        f"## Current Content\n\n```markdown\n{current_content}\n```\n",
    ]

    if history:
        parts.append(_format_history_block(history))

    parts.append(
        f"## User Request\n\n{message}\n\n"
        "## Instructions\n\n"
        "Respond with a JSON object (no markdown fences) with two fields:\n"
        '- `"reply"`: A short conversational explanation of what you changed or suggest.\n'
        '- `"updated_content"`: The full updated markdown for this section '
        "incorporating the user's request. If the user is just asking a question "
        "and no edits are needed, set this to null.\n\n"
        "Preserve existing content structure. Only modify what the user asked for."
    )

    return "\n".join(parts)


def _parse_chat_response(output: str) -> dict[str, Any] | None:
    """Parse and validate AI chat response against expected schema.

    Uses Pydantic validation to ensure response only contains
    ``reply`` and ``updated_content`` — rejects unexpected fields.
    """
    from app.services.json_parser import parse_chat_response

    validated = parse_chat_response(output)
    return validated.model_dump() if validated else None


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
    import re

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

    # 3. HTML fragment embedded in prose — starts with <meta>, <head>, <link>, <style>,
    #    or <!DOCTYPE (Claude sometimes omits the <html> wrapper or starts mid-document).
    #    Capture from the first HTML-like tag to end of content.
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


async def _persist_chat_message(
    bud_id: str,
    org_id: str,
    section: str,
    role: str,
    message: str,
    design_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """Save a chat message to the bud_chat_messages table."""
    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDChatMessageRepository

    async with AsyncSessionLocal() as db:
        chat_repo = BUDChatMessageRepository(db, org_id=uuid_mod.UUID(org_id))
        await chat_repo.add_message(
            bud_id=uuid_mod.UUID(bud_id),
            section=section,
            role=role,
            message=message,
            design_id=uuid_mod.UUID(design_id) if design_id else None,
            user_id=uuid_mod.UUID(user_id) if user_id else None,
            session_id=uuid_mod.UUID(session_id) if session_id else None,
        )
        await db.commit()


async def _persist_chat_update(
    bud_id: str,
    org_id: str,
    section: str,
    content: str,
) -> None:
    """Write updated chat content to the BUD in the database."""
    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDRepository

    async with AsyncSessionLocal() as db:
        bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(org_id))
        bud = await bud_repo.get_by_id(uuid_mod.UUID(bud_id))
        if bud is not None:
            setattr(bud, section, content)
            await db.commit()
            logger.info("chat_content_persisted", bud_id=bud_id, section=section)


async def _persist_design(
    design_id: str,
    org_id: str,
    html: str,
    design_path: str | None = None,
) -> None:
    """Write sanitized wireframe HTML to bud_designs row.

    Sanitizes AI-generated HTML to remove scripts and event handlers
    before storage. The raw file on disk stays unsanitized for developer review.
    """
    from app.database import AsyncSessionLocal
    from app.models.bud import BUDDesignStatus
    from app.repositories.bud import BUDDesignRepository
    from app.services.html_sanitizer import sanitize_design_html

    safe_html = sanitize_design_html(html)

    async with AsyncSessionLocal() as db:
        repo = BUDDesignRepository(db, org_id=uuid_mod.UUID(org_id))
        design = await repo.get_by_id(uuid_mod.UUID(design_id))
        if design is not None:
            design.design_html = safe_html
            design.design_path = design_path
            design.status = BUDDesignStatus.READY
            await db.commit()
            logger.info("design_persisted", design_id=design_id)


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


def _save_image_temp(data_url: str, index: int) -> Path | None:
    """Decode a base64 data-URL image and write it to a temp file.

    Args:
        data_url: A ``data:image/...;base64,...`` string.
        index: Image index (for unique naming).

    Returns:
        Path to the written temp file, or None on failure.
    """
    import base64

    try:
        header, data = data_url.split(",", 1)
        ext = "png"
        if "image/jpeg" in header:
            ext = "jpg"
        elif "image/gif" in header:
            ext = "gif"
        elif "image/webp" in header:
            ext = "webp"

        raw = base64.b64decode(data)
        fd, tmp_path = tempfile.mkstemp(suffix=f".{ext}", prefix=f"chat_image_{index}_")
        os.close(fd)
        path = Path(tmp_path)
        path.write_bytes(raw)
        return path
    except Exception:
        logger.warning("image_save_failed", index=index)
        return None


async def handle_tech_arch_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Generate a tech architecture plan for a BUD using the tech-planner skill."""
    payload = TechArchJobPayload(**raw_payload)
    bud_ref = f"BUD-{payload.bud_number:03d}"

    update_job(job_id, status_message="Preparing tech architecture prompt...", progress_pct=10)

    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDRepository
    from app.repositories.tracked_repository import TrackedRepoRepository

    # Load BUD to get design context + fetch active repos for the org
    async with AsyncSessionLocal() as db:
        bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(payload.org_id))
        bud = await bud_repo.get_by_id(uuid_mod.UUID(payload.bud_id))
        if not bud:
            update_job(job_id, state=JobState.FAILED, error="BUD not found")
            return

        # Gather design info for context
        design_context = ""
        if bud.designs:
            for d in bud.designs:
                if d.design_html:
                    repo_label = d.repo_id or "general"
                    design_context += f"\n## Design ({repo_label})\n{d.design_html[:2000]}\n"

        # Fetch all active repos for the org
        repo_repo = TrackedRepoRepository(db, org_id=uuid_mod.UUID(payload.org_id))
        repo_pairs = await repo_repo.get_active_path_name_pairs()

    # Use first repo as working_dir (gitnexus MCP auto-discovers .gitnexus/ in cwd)
    working_dir = repo_pairs[0][0] if repo_pairs else None

    # Build repo context for prompt
    repo_context = ""
    if repo_pairs:
        repo_list = "\n".join(f"- **{name}**: `{path}`" for path, name in repo_pairs)
        repo_context = (
            f"\n## Available Repositories\n\n{repo_list}\n\n"
            "## IMPORTANT: Code Exploration Rules\n\n"
            "You MUST use the gitnexus MCP tools to explore the codebase. "
            "Do NOT use bash commands like `find`, `grep`, `ls`, or `cat` "
            "for code exploration — use gitnexus instead.\n\n"
            "Available gitnexus MCP tools:\n"
            '- `gitnexus_query({query: "concept"})` — find code by concept '
            "(replaces find/grep)\n"
            '- `gitnexus_context({name: "symbolName"})` — 360° view of a '
            "symbol (callers, callees, execution flows)\n"
            '- `gitnexus_impact({target: "symbol", direction: "upstream"})` '
            "— blast radius analysis\n"
            "- Read `gitnexus://repo/*/processes` — list all execution flows\n"
            "- Read `gitnexus://repo/*/clusters` — list all functional areas\n"
            "- Read `gitnexus://repo/*/context` — codebase overview\n\n"
            "Start by reading `gitnexus://repo/*/context` to understand the "
            "codebase, then use `gitnexus_query` to find relevant code.\n"
        )

    # Build prompt for tech-planner skill
    try:
        skill = load_skill("tech-planner")
    except FileNotFoundError:
        skill = None

    prompt = (
        f"Generate a detailed technical implementation plan for {bud_ref}: {payload.title}.\n\n"
        f"## Requirements\n\n{payload.requirements_md}\n"
    )
    if design_context:
        prompt += f"\n## Existing Design Context\n{design_context}\n"
    if repo_context:
        prompt += repo_context
    if repo_pairs:
        prompt += (
            "\n## Instructions\n\n"
            "1. First, read `gitnexus://repo/*/context` to get a codebase overview.\n"
            "2. Use `gitnexus_query` to find code related to the requirements.\n"
            "3. Use `gitnexus_context` on key symbols to understand dependencies.\n"
            "4. Then create a comprehensive tech spec covering:\n"
            "   - Architecture approach and key design decisions\n"
            "   - Files to create or modify (with full paths)\n"
            "   - Data model changes (if any)\n"
            "   - API endpoints (if any)\n"
            "   - Dependencies and integration points\n"
            "   - Risk areas and mitigation strategies\n\n"
            "REMEMBER: Use gitnexus MCP tools, NOT bash find/grep/ls.\n\n"
            "Output the plan as clean markdown."
        )
    else:
        prompt += (
            "\n## Instructions\n\n"
            "Create a comprehensive tech spec covering:\n"
            "- Architecture approach and key design decisions\n"
            "- Files to create or modify (with paths)\n"
            "- Data model changes (if any)\n"
            "- API endpoints (if any)\n"
            "- Dependencies and integration points\n"
            "- Risk areas and mitigation strategies\n\n"
            "Output the plan as clean markdown."
        )

    update_job(
        job_id,
        status_message="Generating tech architecture (this may take a few minutes)...",
        progress_pct=20,
    )

    from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

    result = await run_claude_code(
        prompt=prompt,
        working_dir=working_dir,
        config=ClaudeRunnerConfig(
            max_turns=skill.max_turns if skill else 3,
            timeout_seconds=600,
            model=(skill.model or None) if skill else None,
            effort=(skill.effort or None) if skill else None,
        ),
        progress_callback=_make_progress_callback(job_id),
    )

    if not result.success:
        update_job(
            job_id,
            state=JobState.FAILED,
            error=result.error or "Tech architecture generation failed",
        )
        return

    # Persist to BUD
    update_job(job_id, status_message="Saving tech spec...", progress_pct=90)

    async with AsyncSessionLocal() as db:
        try:
            bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(payload.org_id))
            bud = await bud_repo.get_by_id(uuid_mod.UUID(payload.bud_id))
            if bud:
                bud.tech_spec_md = result.output
                # Clear tech_arch_job_id from metadata so frontend stops showing banner
                meta = dict(bud.metadata_ or {})
                meta.pop("tech_arch_job_id", None)
                bud.metadata_ = meta
                await db.commit()
        except Exception:
            await db.rollback()
            raise

    # Record timeline event
    await _record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        "tech_arch_started",
        skill_name="tech-planner",
        section="tech_spec_md",
        job_id=job_id,
    )

    # Send approval_requested notification to BUD assignee (tech_lead)
    from app.services.notification_service import send_lifecycle_notification

    async with AsyncSessionLocal() as db:
        bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(payload.org_id))
        bud = await bud_repo.get_by_id(uuid_mod.UUID(payload.bud_id))
        if bud and bud.assignee_id:
            send_lifecycle_notification(
                org_id=payload.org_id,
                user_id=str(bud.assignee_id),
                notification_type="approval_requested",
                title=f"Tech plan ready for review: {bud_ref}",
                message=f'The tech architecture for "{payload.title}" needs your approval.',
                bud_id=payload.bud_id,
            )

    update_job(
        job_id,
        state=JobState.COMPLETED,
        status_message="Tech architecture generated",
        progress_pct=100,
    )


# ── Code review handler ────────────────────────────────────────────


async def handle_code_review_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Run automated code review + test plan generation for a BUD.

    For each confirmed repo, diffs the develop worktree against the last
    commit SHA from bud_commits, then sends all diffs + tech spec to Claude
    for review comments and test plan generation.
    """
    payload = CodeReviewJobPayload(**raw_payload)
    bud_ref = f"BUD-{payload.bud_number:03d}"

    update_job(job_id, status_message="Collecting code changes...", progress_pct=10)

    from app.database import AsyncSessionLocal
    from app.repositories.bud import BUDRepository
    from app.repositories.bud_commit import BUDCommitRepository
    from app.services.repo_scanner import run_git

    # Step 1: Gather diffs for each confirmed repo
    all_diffs: list[dict[str, str]] = []

    async with AsyncSessionLocal() as db:
        org_id_uuid = uuid_mod.UUID(payload.org_id)
        commit_repo = BUDCommitRepository(db, org_id=org_id_uuid)
        last_shas = await commit_repo.get_last_sha_per_repo(uuid_mod.UUID(payload.bud_id))

    for repo_info in payload.confirmed_repos:
        repo_path = repo_info.get("repo_path", "")
        repo_name = repo_info.get("repo_name", Path(repo_path).name)
        if not repo_path:
            continue

        # Pull develop worktree to latest
        develop_wt = Path(repo_path) / ".bodhigrove" / "develop"
        if develop_wt.exists():
            await run_git(["pull"], cwd=str(develop_wt))

        # Get the last commit SHA for this repo
        last_sha = last_shas.get(repo_path)
        if not last_sha:
            logger.warning("code_review_no_commits", repo=repo_name, bud=bud_ref)
            continue

        # Get diff: develop...last_sha
        diff_base = "develop" if develop_wt.exists() else "HEAD~10"
        diff_stdout, diff_stderr, rc = await run_git(
            ["diff", f"{diff_base}...{last_sha}", "--stat", "--patch"],
            cwd=repo_path,
            timeout=120,
        )
        if rc != 0:
            # Fallback: diff against HEAD
            diff_stdout, _, _ = await run_git(
                ["diff", f"HEAD~5..{last_sha}"],
                cwd=repo_path,
                timeout=120,
            )

        if diff_stdout:
            # Truncate very large diffs
            all_diffs.append(
                {
                    "repo_name": repo_name,
                    "diff": diff_stdout[:50000],
                }
            )

    if not all_diffs:
        update_job(
            job_id,
            state=JobState.FAILED,
            error="No code changes found in confirmed repos",
        )
        return

    update_job(
        job_id,
        status_message="Running AI code review (this may take a few minutes)...",
        progress_pct=30,
    )

    # Step 2: Build prompt for Claude
    diff_sections = "\n\n".join(
        f"## Repository: {d['repo_name']}\n\n```diff\n{d['diff']}\n```" for d in all_diffs
    )

    prompt = (
        f"You are performing an automated code review for {bud_ref}: {payload.title}.\n\n"
        f"## Original Tech Spec\n\n{payload.tech_spec_md[:10000]}\n\n"
        f"## Code Changes\n\n{diff_sections}\n\n"
        "## Instructions\n\n"
        "Review the code changes and produce a JSON response with this exact structure:\n"
        "```json\n"
        "{\n"
        '  "code_review_comments": [\n'
        "    {\n"
        '      "repo": "repo_name",\n'
        '      "file": "path/to/file.py",\n'
        '      "line": 42,\n'
        '      "severity": "error|warning|suggestion",\n'
        '      "comment": "Description of the issue",\n'
        '      "deviates_from_spec": false\n'
        "    }\n"
        "  ],\n"
        '  "automation_test_plan_md": "## Automated Tests\\n\\n...",\n'
        '  "manual_test_plan_md": "## Manual Tests\\n\\n..."\n'
        "}\n"
        "```\n\n"
        "For the code review:\n"
        "- Check for bugs, security issues, and code quality problems\n"
        "- Flag any deviations from the tech spec\n"
        "- Note missing error handling or edge cases\n\n"
        "For test plans:\n"
        "- automation_test_plan_md: Unit and integration tests that should be automated\n"
        "- manual_test_plan_md: Manual QA test scenarios with steps\n\n"
        "Output ONLY the JSON — no markdown wrapper, no explanation."
    )

    # Step 3: Run Claude
    from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

    try:
        skill = load_skill("code-reviewer")
    except FileNotFoundError:
        skill = None

    working_dir = payload.confirmed_repos[0].get("repo_path") if payload.confirmed_repos else None
    result = await run_claude_code(
        prompt=prompt,
        working_dir=working_dir,
        config=ClaudeRunnerConfig(
            max_turns=skill.max_turns if skill else 3,
            timeout_seconds=600,
            output_format="json",
            model=(skill.model or None) if skill else None,
            effort=(skill.effort or None) if skill else None,
        ),
        progress_callback=_make_progress_callback(job_id),
    )

    if not result.success:
        update_job(
            job_id,
            state=JobState.FAILED,
            error=result.error or "Code review generation failed",
        )
        return

    # Step 4: Parse and persist results
    update_job(job_id, status_message="Saving review results...", progress_pct=85)

    review_data = _parse_code_review_output(result.output)

    async with AsyncSessionLocal() as db:
        try:
            bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(payload.org_id))
            bud = await bud_repo.get_by_id(uuid_mod.UUID(payload.bud_id))
            if bud:
                meta = dict(bud.metadata_ or {})
                meta["code_review_comments"] = review_data.get("code_review_comments", [])
                meta.pop("code_review_job_id", None)
                bud.metadata_ = meta

                # Store test plans
                auto_plan = review_data.get("automation_test_plan_md", "")
                manual_plan = review_data.get("manual_test_plan_md", "")
                if auto_plan or manual_plan:
                    meta["automation_test_plan_md"] = auto_plan
                    meta["manual_test_plan_md"] = manual_plan
                    bud.metadata_ = meta

                await db.commit()
        except Exception:
            await db.rollback()
            raise

    await _record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        "ai_agent_completed",
        skill_name="code-reviewer",
        section="code_review",
        job_id=job_id,
    )

    comments_count = len(review_data.get("code_review_comments", []))
    update_job(
        job_id,
        state=JobState.COMPLETED,
        result={
            "comments_count": comments_count,
            "has_auto_tests": bool(review_data.get("automation_test_plan_md")),
            "has_manual_tests": bool(review_data.get("manual_test_plan_md")),
        },
        status_message=f"Code review complete — {comments_count} comments",
        progress_pct=100,
    )


def _parse_code_review_output(output: str) -> dict[str, Any]:
    """Parse Claude's code review JSON output.

    Falls back to empty structure if parsing fails.

    Args:
        output: Raw text output from Claude.

    Returns:
        Dict with code_review_comments, automation_test_plan_md, manual_test_plan_md.
    """
    from app.services.json_parser import extract_json

    default: dict[str, Any] = {
        "code_review_comments": [],
        "automation_test_plan_md": "",
        "manual_test_plan_md": "",
    }

    if not output:
        return default

    try:
        parsed = extract_json(output)
        if isinstance(parsed, dict):
            return {
                "code_review_comments": parsed.get("code_review_comments", []),
                "automation_test_plan_md": parsed.get("automation_test_plan_md", ""),
                "manual_test_plan_md": parsed.get("manual_test_plan_md", ""),
            }
    except Exception:
        logger.warning("code_review_parse_failed", output_preview=output[:200])

    return default


async def _record_agent_timeline(
    org_id: str,
    bud_id: str,
    event_type: str,
    *,
    skill_name: str,
    section: str,
    job_id: str,
    extra_detail: dict[str, Any] | None = None,
) -> None:
    """Record an AI agent timeline event in a fresh DB session.

    Job handlers create their own sessions, so this uses AsyncSessionLocal.
    """
    from app.database import AsyncSessionLocal
    from app.services.bud_timeline import record_event

    detail = extra_detail or {
        "agent": skill_name,
        "section": section,
        "job_id": job_id,
    }
    try:
        async with AsyncSessionLocal() as tl_db:
            await record_event(
                tl_db,
                uuid_mod.UUID(org_id),
                uuid_mod.UUID(bud_id),
                event_type,
                detail=detail,
            )
            await tl_db.commit()
    except Exception:
        logger.warning(
            "timeline_event_failed",
            event_type=event_type,
            bud_id=bud_id,
        )


def _get_thread_key(event_data: dict[str, Any]) -> str:
    """Extract a unique key for Slack thread serialization."""
    item = event_data.get("item", {})
    channel = item.get("channel", event_data.get("channel", ""))
    ts = item.get("ts", event_data.get("thread_ts", ""))
    return f"{channel}:{ts}"
