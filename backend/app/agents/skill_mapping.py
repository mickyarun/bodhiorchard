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

"""Mapping from Bodhiorchard agent names to skill definition files.

Each Bodhiorchard agent (triage, bud, status, etc.) maps to a skill markdown
file in backend/app/agents/skills/ that defines its persona, tools, and workflow.

The map is also used to seed ``agent_skills`` rows (one per
``(slug, agent_type)`` pair). Runtime resolution prefers per-BUD overrides
and org-level ``is_default`` rows over this static map — see
``resolve_skill_for_agent``.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_skill import AgentSkill, AgentType
from app.models.bud import BUDStatus

AGENT_SKILL_MAP: dict[str, str] = {
    "triage": "triage-analyst",
    "bud": "product-manager",
    "status": "devops",
    "standup": "product-manager",
    "learning": "technical-writer",
    "bugLinker": "testing",
    "reassignment": "product-manager",
    "skill": "code-reviewer",
    "techPlan": "tech-planner",
    "testPlan": "testing",
    "design": "designer",
    "slackTriage": "slack-triage",
}

# Maps BUD section keys to the skill that handles chat for that section.
# Used by the chat job handler to read skill-level config (e.g. max_turns).
SECTION_SKILL_MAP: dict[str, str] = {
    "requirements_md": "product-manager",
    "tech_spec_md": "tech-planner",
    "test_plan_md": "testing",
    "design": "designer",
}


def get_skill_for_agent(agent_name: str) -> str | None:
    """Look up the seeded skill slug for an agent (static fallback map)."""
    return AGENT_SKILL_MAP.get(agent_name)


# Stages where an agent actually runs today — used by the "Advanced settings"
# UI to decide which stage dropdowns to show on BUD create. Kept here next to
# AGENT_SKILL_MAP so the two stay aligned.
BUD_STAGE_AGENT_TYPE: dict[BUDStatus, AgentType] = {
    BUDStatus.BUD: AgentType.BUD,
    BUDStatus.DESIGN: AgentType.DESIGN,
    BUDStatus.TECH_ARCH: AgentType.TECH_PLAN,
    BUDStatus.TESTING: AgentType.TEST_PLAN,
}

# Maps a BUD section key to the agent type that handles chat for that
# section. Used by ``job_chat`` to resolve the chat skill via the
# override-aware resolver instead of the agent-type-blind
# SECTION_SKILL_MAP slug lookup. Pair each section with the BUD stage
# whose override should govern its chat.
SECTION_AGENT_TYPE: dict[str, AgentType] = {
    "requirements_md": AgentType.BUD,
    "tech_spec_md": AgentType.TECH_PLAN,
    "test_plan_md": AgentType.TEST_PLAN,
    "design": AgentType.DESIGN,
}

SECTION_BUD_STATUS: dict[str, BUDStatus] = {
    "requirements_md": BUDStatus.BUD,
    "tech_spec_md": BUDStatus.TECH_ARCH,
    "test_plan_md": BUDStatus.TESTING,
    "design": BUDStatus.DESIGN,
}


async def resolve_skill_for_agent(
    agent_name: str,
    org_id: uuid.UUID,
    db: AsyncSession,
    *,
    bud_id: uuid.UUID | None = None,
    bud_status: BUDStatus | None = None,
) -> AgentSkill | None:
    """Resolve which ``AgentSkill`` row should run for an agent.

    Resolution order:
    1. Per-BUD stage override (``bud_stage_skill_overrides``) when
       ``bud_id`` and ``bud_status`` are both supplied.
    2. Org's default for the agent's type (``is_default = true``).
    3. ``AGENT_SKILL_MAP`` slug — load by (slug, agent_type).

    Returns ``None`` only when neither the override nor any seeded skill
    is in the DB (i.e. fresh org pre-seed).
    """
    from app.repositories.agent_skill import AgentSkillRepository
    from app.repositories.bud_stage_skill_override import (
        BUDStageSkillOverrideRepository,
    )

    try:
        agent_type = AgentType(agent_name)
    except ValueError:
        return None

    if bud_id is not None and bud_status is not None:
        override_repo = BUDStageSkillOverrideRepository(db, org_id=org_id)
        override = await override_repo.get_for_bud_and_stage(bud_id, bud_status)
        if override is not None:
            return override.skill

    skill_repo = AgentSkillRepository(db, org_id=org_id)
    default_row = await skill_repo.get_default_for_agent_type(agent_type)
    if default_row is not None:
        return default_row

    fallback_slug = AGENT_SKILL_MAP.get(agent_name)
    if fallback_slug is None:
        return None
    return await skill_repo.get_by_slug(fallback_slug, agent_type=agent_type)
