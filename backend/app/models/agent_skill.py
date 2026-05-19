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

"""Agent skill model — per-org AI agent skill configuration.

Skills are seeded from file templates on startup and stored in the DB
as the primary source of truth. Orgs can customize prompts, tools,
and model settings per skill — and add their own custom skills tagged
to a specific agent type, with one marked as default per (org, agent_type).
"""

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.agent_skill_bud_stage import AgentSkillBudStage


class AgentType(StrEnum):
    """Bodhiorchard agent types that own (or will own) a Claude-driven skill.

    Values must mirror the keys of ``app.agents.skill_mapping.AGENT_SKILL_MAP``;
    the seed flow uses that map to assign agent_type to each seeded row.

    Three earlier enum values (``status``, ``standup``, ``reassignment``)
    were dropped after audit confirmed nothing in the runtime ever
    loaded their skill — standup is pure SQL aggregation, reassignment
    is plain Python, status was never wired. Their stale rows are
    removed by migration ``79884f63ba1a_drop_dead_agent_types``.

    ``TRIAGE``, ``LEARNING``, and ``BUG_LINKER`` are also currently
    unloaded by any runtime path, but kept as placeholders for planned
    AI flows (BUD triage / learning recaps / bug-to-BUD linker). Their
    seeded rows stay so an admin can pre-edit the prompts before the
    wiring lands.
    """

    TRIAGE = "triage"
    BUD = "bud"
    LEARNING = "learning"
    BUG_LINKER = "bugLinker"
    SKILL = "skill"
    TECH_PLAN = "techPlan"
    TEST_PLAN = "testPlan"
    DESIGN = "design"
    SLACK_TRIAGE = "slackTriage"


class AgentSkill(BaseModel):
    """Per-org agent skill configuration.

    Seeded from file-based templates in agents/skills/ on startup; users
    may also create custom skills via the settings UI. Each row is tied
    to exactly one ``agent_type``; one row per ``(org_id, agent_type)``
    can be marked ``is_default=true`` (the partial unique index on
    ``is_default WHERE is_default = true`` enforces this).
    """

    __tablename__ = "agent_skills"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "skill_slug", "agent_type", name="uq_skill_org_slug_agent_type"
        ),
        # Partial unique: at most one default per (org, agent_type).
        Index(
            "uq_skill_one_default_per_agent_type",
            "org_id",
            "agent_type",
            unique=True,
            postgresql_where="is_default = true",
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    skill_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_type: Mapped[AgentType] = mapped_column(
        Enum(AgentType, name="agent_type", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_custom: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    mcp_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Wall-clock cap on the Claude subprocess call for this skill. ``0`` means
    # "use the agent code's hard-coded fallback" (each agent picks something
    # sensible for its work — e.g. 600 s for multi-turn PRD writing, 90 s for
    # the tech-planner patch-mode touch-up). Per-org admins can bump this
    # when a slow tech spec / large repo causes spurious timeouts.
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="", server_default="")
    # Optional override used on chat-iteration paths (e.g. BUD design chat
    # follow-ups). Empty falls back to ``model``. A faster model here
    # (e.g. Haiku) gives ~3× faster iterations while ``model`` (Sonnet)
    # remains in charge of the initial generation.
    iteration_model: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default=""
    )
    effort: Mapped[str] = mapped_column(String(20), nullable=False, default="", server_default="")

    # Relationships
    bud_stages: Mapped[list["AgentSkillBudStage"]] = relationship(
        back_populates="skill", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<AgentSkill(id={self.id}, org={self.org_id}, slug={self.skill_slug!r})>"
