# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""``get_prompt`` MCP tool — expose our agent prompts to external LLMs.

When a user runs in External-LLM mode (auto_generate phase off), their
local AI can pull the exact same prompt our PM / Designer / TechPlanner /
Tester agents would use, then feed it to their own model. This avoids
the otherwise-inevitable "I wrote my own prompt and it produced a
different shape than your editors expect" failure mode.

Resolution honours the org's custom-skill overrides via
``resolve_skill_for_agent`` — what the external LLM gets back is exactly
what our internal agent would receive if it ran.

The handler does NOT accept a ``bud_id`` parameter. Per-BUD stage skill
overrides (the Advanced-settings picker on BUD create) are intentionally
NOT honoured here because the remote endpoint should be stateless and
predictable; if your local LLM needs a custom prompt for one specific
BUD, edit the prompt locally after fetching the org default.
"""

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.skill_mapping import BUD_STAGE_AGENT_TYPE
from app.models.bud import BUDStatus
from app.models.organization import Organization

logger = structlog.get_logger(__name__)

# Public mapping: which task_type tokens the caller can ask for. Keys
# match the BUDStatus string values that already show up in the
# auto_generate_phases dict, the BUD section editor tabs, and the
# Advanced-settings stage labels — one consistent vocabulary across the
# whole BYO-AI flow.
TASK_TYPE_TO_STAGE: dict[str, BUDStatus] = {
    "bud": BUDStatus.BUD,
    "design": BUDStatus.DESIGN,
    "tech_arch": BUDStatus.TECH_ARCH,
    "testing": BUDStatus.TESTING,
}


async def handle_get_prompt(
    db: AsyncSession, org: Organization, params: dict[str, Any]
) -> dict[str, Any]:
    """Return the active prompt text for a task type, scoped to the caller's org.

    Args:
        db: Request-scoped async session.
        org: Authenticated org (from MCPAuthResult).
        params: Tool call params. Requires ``task_type`` ∈
                {"bud", "design", "tech_arch", "testing"}.

    Returns:
        ``{task_type, agent_type, skill_slug, prompt}`` on success;
        ``{error}`` on unknown task_type or missing skill row.
    """
    from app.agents.skill_mapping import resolve_skill_for_agent

    task_type = params.get("task_type")
    if not isinstance(task_type, str) or task_type not in TASK_TYPE_TO_STAGE:
        return {
            "error": (
                "task_type must be one of: "
                f"{sorted(TASK_TYPE_TO_STAGE.keys())}"
            )
        }

    stage = TASK_TYPE_TO_STAGE[task_type]
    agent_type = BUD_STAGE_AGENT_TYPE[stage]

    # bud_id/bud_status intentionally omitted — see module docstring.
    skill = await resolve_skill_for_agent(agent_type.value, org.id, db)
    if skill is None:
        logger.info(
            "mcp_get_prompt_no_skill_for_agent",
            org_id=str(org.id),
            agent_type=agent_type.value,
            task_type=task_type,
        )
        return {
            "error": (
                f"No active skill found for task_type={task_type!r}. "
                "Has your org been seeded with default skills?"
            )
        }

    return {
        "task_type": task_type,
        "agent_type": agent_type.value,
        "skill_slug": skill.skill_slug,
        "prompt": skill.prompt,
    }
