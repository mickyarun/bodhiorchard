"""Prompt builders and history helpers for BUD chat interactions.

Separated from job_chat.py for modularity. These are pure business
logic functions with no job lifecycle dependencies.
"""

import os
import tempfile
import uuid as uuid_mod
from pathlib import Path

import structlog

from app.services.job_utils import HISTORY_CHAR_BUDGET

logger = structlog.get_logger(__name__)


async def fetch_chat_history(
    bud_id: str,
    org_id: str,
    section: str,
    design_id: str | None = None,
    session_id: str | None = None,
    limit: int = 10,
) -> list[dict[str, str]]:
    """Fetch recent chat messages for LLM context injection."""
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


def format_history_block(history: list[dict[str, str]]) -> str:
    """Format chat history into a markdown block for prompt injection."""
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


async def build_design_prompt(
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
    """Build the Claude prompt for design wireframe generation."""
    ds_content = ""
    ds_file: Path | None = None

    if not use_mcp:
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
        if repo_id:
            mcp_hint = (
                f'Call `get_design_system` with `repo_id: "{repo_id}"` to get '
                "this repo's design system (primary).\n\n"
                "You can also call `list_design_systems` to see all available "
                "design systems. If other repos have relevant UI patterns, call "
                "`get_design_system` with their `repo_id` to cross-reference."
            )
        else:
            mcp_hint = (
                "Call `list_design_systems` to see all available design systems, "
                "then call `get_design_system` with each relevant `repo_id`."
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
        fd, tmp_path = tempfile.mkstemp(suffix=".md", prefix="bodhigrove_design_system_")
        os.close(fd)
        ds_file = Path(tmp_path)
        ds_file.write_text(ds_content, encoding="utf-8")
        parts.append(
            "## Design System\n\n"
            "The project's design system has been loaded into your context. "
            "Your wireframe MUST use the CDN boilerplate and color tokens from it.\n"
        )
    else:
        parts.append(
            "## Design System\n\n"
            "No design system extracted. Use Vuetify 3 CDN with a clean dark theme.\n"
        )

    parts.append(
        "## Existing Application UI\n\n"
        "Read 2–3 existing Vue components from `src/` to understand the visual style. "
        "Match your wireframe to these patterns.\n"
    )

    if current_content:
        parts.append(f"## Current Design\n\n```html\n{current_content}\n```\n")
    else:
        parts.append("## Current Design\n\nNo design exists yet. Create one from scratch.\n")

    if history:
        parts.append(format_history_block(history))

    parts.append(f"## User Request\n\n{message}\n")

    parts.append(
        "## Instructions\n\n"
        f"1. Write the wireframe as a complete HTML file to:\n"
        f"   `.flowdev/wireframes/{bud_ref}/wireframe.html`\n"
        "   Create the directory if it doesn't exist.\n\n"
        "2. The HTML file must:\n"
        "   - Use Vuetify CDN (with Vue 3)\n"
        "   - Apply the design system colors and component defaults\n"
        "   - Include `<!-- UX: ... -->` and `<!-- A11Y: ... -->` comments\n"
        "   - Render correctly in any modern browser\n\n"
        "3. Respond with JSON (no markdown fences):\n"
        '   {"reply": "<design choices>", "updated_content": null}\n\n'
        "Focus on layout, information architecture, and interaction patterns."
    )

    return "\n".join(parts), ds_file


def build_chat_prompt(
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
        parts.append(format_history_block(history))

    parts.append(
        f"## User Request\n\n{message}\n\n"
        "## Instructions\n\n"
        "Respond with JSON (no markdown fences) with two fields:\n"
        '- `"reply"`: Short explanation of what you changed.\n'
        '- `"updated_content"`: Full updated markdown, or null if no edits.\n\n'
        "Preserve existing content structure. Only modify what was asked."
    )

    return "\n".join(parts)
