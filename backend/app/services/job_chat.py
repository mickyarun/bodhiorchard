"""Chat job handler for async BUD section editing via Claude.

Handles the BUD chat workflow: builds prompts, runs Claude,
parses responses, and persists content updates to the database.
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
from app.schemas.jobs import ChatJobPayload, JobState
from app.services.job_queue import update_job
from app.services.job_utils import (
    HISTORY_CHAR_BUDGET,
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
        mcp_config = build_mcp_config(payload.org_id, tool_names=design_tools)
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
        repo_path = await resolve_repo_path(payload.repo_id, payload.org_id)
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
            p = save_image_temp(data_url, i)
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
            progress_callback=make_progress_callback(job_id),
        )
    finally:
        if ds_temp_file is not None:
            ds_temp_file.unlink(missing_ok=True)
        for p in image_paths:
            p.unlink(missing_ok=True)

    if not result.success:
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

    await record_agent_timeline(
        payload.org_id,
        payload.bud_id,
        "ai_agent_completed",
        skill_name=skill_name,
        section=payload.section,
        job_id=job_id,
    )


# ── Chat helpers ──────────────────────────────────────────────────


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
    if len(block) > HISTORY_CHAR_BUDGET:
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
