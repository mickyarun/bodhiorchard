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

"""Prompt builders and history helpers for BUD chat interactions.

Separated from job_chat.py for modularity. These are pure business
logic functions with no job lifecycle dependencies.
"""

import uuid as uuid_mod

import structlog

from app.database import AsyncSessionLocal
from app.services.bud_agent_context import (
    format_code_locations_section,
    load_bud_agent_context,
)
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
    message: str,
    bud_id: str,
    repo_id: str | None = None,
    history: list[dict[str, str]] | None = None,
    *,
    repo_name: str | None = None,
) -> str:
    """Build the Claude prompt for design wireframe generation.

    The prompt is intentionally lean: it does NOT inline the current
    wireframe HTML or the design system tokens. Instead the agent fetches
    both on demand via MCP tools (``get_bud_designs``, ``get_design_system``)
    and writes the iterated wireframe back via ``write_bud_design`` —
    eliminating ~30KB of repeated content on every iteration and removing
    the dependency on stdout-JSON parsing for persistence.
    """
    linked_section = await _build_design_linked_section(org_id, bud_id)

    parts = [
        f"You are designing a **visual HTML wireframe** for {bud_ref}: *{title}*.\n",
    ]

    if repo_id:
        ds_hint = (
            f'Call `get_design_system` with `repo_id: "{repo_id}"` to get '
            "this repo's design system (primary).\n\n"
            "You can also call `list_design_systems` to see all available "
            "design systems. If other repos have relevant UI patterns, call "
            "`get_design_system` with their `repo_id` to cross-reference."
        )
    else:
        ds_hint = (
            "Call `list_design_systems` to see all available design systems, "
            "then call `get_design_system` with each relevant `repo_id`."
        )
    parts.append(
        "## Design System\n\n"
        f"{ds_hint}\n\n"
        "Your wireframe MUST use the CDN boilerplate and color tokens "
        "from the primary design system. "
        "If no design system is available, use Vuetify 3 CDN with a clean "
        "dark theme as default.\n"
    )

    if linked_section:
        parts.append(linked_section)

    parts.append(
        "## Existing Application UI\n\n"
        "Read 2–3 existing Vue components from `src/` to understand the visual style. "
        "Match your wireframe to these patterns.\n"
    )

    parts.append(
        "## Current Wireframe\n\n"
        f'Call `get_bud_designs` with `bud_id: "{bud_id}"`'
        + (f' and `repo_id: "{repo_id}"`' if repo_id else "")
        + " to fetch the existing wireframe (if any) before iterating. "
        "Do NOT assume the prior content from your own context — always fetch it.\n"
    )

    if history:
        parts.append(format_history_block(history))

    parts.append(f"## User Request\n\n{message}\n")

    repo_hint = f', `repo_id: "{repo_id}"`' if repo_id else ""
    parts.append(
        "## Instructions\n\n"
        "1. Build a complete, self-contained wireframe HTML that:\n"
        "   - Uses Vuetify CDN (with Vue 3) via the `vue.global.prod.js` build "
        "(NOT `vue.esm-browser.prod.js` — Vuetify's UMD bundle expects the "
        "global Vue instance).\n"
        "   - Wraps ALL Vuetify content inside a single `<v-app>` element "
        'directly under `<div id="app">`. Without this wrapper, '
        "`<v-main>` and other layout components throw "
        "`[Vuetify] Could not find injected layout` and the page renders "
        "blank.\n"
        "   - Applies the design system colors and component defaults\n"
        "   - Includes `<!-- UX: ... -->` and `<!-- A11Y: ... -->` comments\n"
        "   - Renders correctly in any modern browser\n\n"
        "2. **Persist the wireframe via the `write_bud_design` MCP tool** "
        f'with `bud_id: "{bud_id}"`{repo_hint}, and `html: <complete_wireframe_html>`. '
        "This is the ONLY supported persistence path — do NOT write the "
        "HTML to a file on disk and do NOT rely on the JSON reply for "
        "persistence.\n\n"
        "3. After `write_bud_design` succeeds, respond with JSON (no "
        "markdown fences):\n"
        '   {"reply": "<short explanation of design choices>"}\n\n'
        "Focus on layout, information architecture, and interaction patterns."
    )

    return "\n".join(parts)


async def _build_design_linked_section(org_id: str, bud_id: str | None) -> str:
    """Render the "Linked existing UI surface" section, or ``""`` if none.

    Pulls frontend ``code_locations`` from features the BUD is linked
    to (via :class:`BUDFeatureLink`) so the wireframe extends real
    components instead of being designed in isolation. Failures are
    swallowed with a warning — the prompt still works without this
    section.
    """
    if not bud_id:
        return ""
    try:
        async with AsyncSessionLocal() as db:
            ctx = await load_bud_agent_context(
                db, bud_id=uuid_mod.UUID(bud_id), org_id=uuid_mod.UUID(org_id)
            )
        if not ctx.linked_features:
            return ""
        return format_code_locations_section(
            ctx.linked_features,
            layers=["frontend"],
            heading="## Linked existing UI surface",
            instruction=(
                "Your wireframe MUST extend these existing components, not "
                "replace them. Read each file before sketching the layout."
            ),
        )
    except Exception:
        logger.warning("design_linked_features_lookup_failed", org_id=org_id, bud_id=bud_id)
        return ""


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
