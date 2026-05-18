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

"""Agent skill data access repository."""

import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_skill import AgentSkill, AgentType
from app.repositories.base import BaseRepository, rowcount


class AgentSkillRepository(BaseRepository[AgentSkill]):
    """Repository for agent skills, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(AgentSkill, db, org_id=org_id)

    async def get_by_slug(
        self, skill_slug: str, agent_type: AgentType | None = None
    ) -> AgentSkill | None:
        """Fetch a skill by slug (and optionally agent_type).

        With ``agent_type`` provided, returns the unique (slug, agent_type)
        row. Without it, returns the first match — only safe for slugs that
        map to a single agent type (e.g. 'designer', 'tech-planner').
        """
        stmt = self._scoped(select(AgentSkill).where(AgentSkill.skill_slug == skill_slug))
        if agent_type is not None:
            stmt = stmt.where(AgentSkill.agent_type == agent_type)
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def get_default_for_agent_type(self, agent_type: AgentType) -> AgentSkill | None:
        """Return the org's default skill for the given agent type, if any."""
        stmt = self._scoped(
            select(AgentSkill)
            .where(AgentSkill.agent_type == agent_type)
            .where(AgentSkill.is_default.is_(True))
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_agent_type(self, agent_type: AgentType) -> list[AgentSkill]:
        """List every skill (seeded + custom) configured for an agent type."""
        stmt = self._scoped(
            select(AgentSkill)
            .where(AgentSkill.agent_type == agent_type)
            .order_by(AgentSkill.is_custom, AgentSkill.name)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_all_sorted(self) -> list[AgentSkill]:
        """List every skill for the current org, ordered by (agent_type, name)."""
        stmt = self._scoped(select(AgentSkill).order_by(AgentSkill.agent_type, AgentSkill.name))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def set_default(self, skill_id: uuid.UUID) -> AgentSkill:
        """Mark ``skill_id`` as default for its agent_type, demoting any prior default.

        The partial unique index on ``(org_id, agent_type) WHERE is_default``
        means we must demote-then-promote in two statements within the same
        transaction.
        """
        skill = await self.get_by_id(skill_id)
        if skill is None:
            raise ValueError(f"Skill not found: {skill_id}")

        await self._db.execute(
            update(AgentSkill)
            .where(AgentSkill.org_id == self._org_id)
            .where(AgentSkill.agent_type == skill.agent_type)
            .where(AgentSkill.id != skill_id)
            .values(is_default=False)
        )
        skill.is_default = True
        await self._db.flush()
        await self._db.refresh(skill)
        return skill

    async def create_custom(
        self,
        *,
        skill_slug: str,
        agent_type: AgentType,
        name: str,
        description: str,
        tools: list[str],
        mcp_tools: list[str],
        prompt: str,
        max_turns: int = 0,
        timeout_seconds: int = 0,
        model: str = "",
        iteration_model: str = "",
        effort: str = "",
    ) -> AgentSkill:
        """Insert a user-authored skill row (``is_custom = true``)."""
        skill = AgentSkill(
            org_id=self._org_id,
            skill_slug=skill_slug,
            agent_type=agent_type,
            is_default=False,
            is_custom=True,
            name=name,
            description=description,
            tools=tools,
            mcp_tools=mcp_tools,
            prompt=prompt,
            max_turns=max_turns,
            timeout_seconds=timeout_seconds,
            model=model,
            iteration_model=iteration_model,
            effort=effort,
        )
        return await self.create(skill)

    async def delete_custom(self, skill_id: uuid.UUID) -> bool:
        """Delete a custom skill row. Refuses to delete seeded rows.

        Before issuing the DELETE we null out the ``skill_id`` FK on
        any ``agent_activity_logs`` rows pointing at this skill. The
        column is nullable and the table has a denormalised
        ``skill_slug`` text column for audit display, so the
        historical record survives — without this step the NO-ACTION
        FK would permanently lock any skill that's ever been invoked,
        even after every BUD has been re-pointed off it.

        Returns True iff a row was deleted. Returns False both when
        the skill doesn't exist and when it's a seeded (non-custom)
        row — callers map that into a 4xx response.
        """
        from app.models.agent_activity import AgentActivityLog

        await self._db.execute(
            update(AgentActivityLog)
            .where(AgentActivityLog.org_id == self._org_id)
            .where(AgentActivityLog.skill_id == skill_id)
            .values(skill_id=None)
        )
        stmt = (
            delete(AgentSkill)
            .where(AgentSkill.org_id == self._org_id)
            .where(AgentSkill.id == skill_id)
            .where(AgentSkill.is_custom.is_(True))
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return (rowcount(result) or 0) > 0

    async def upsert(
        self,
        skill_slug: str,
        name: str,
        description: str,
        tools: list[str],
        mcp_tools: list[str],
        prompt: str,
        max_turns: int = 0,
        timeout_seconds: int = 0,
        model: str = "",
        iteration_model: str = "",
        effort: str = "",
        *,
        agent_type: AgentType,
        is_default: bool = True,
    ) -> AgentSkill:
        """Insert or update a SEEDED skill row keyed by (slug, agent_type).

        Used by ``seed_skills_for_org()``. Existing rows have their content
        updated in place; missing rows are inserted with ``is_default`` set
        per arg and ``is_custom=False``.
        """
        existing = await self.get_by_slug(skill_slug, agent_type=agent_type)
        if existing is not None:
            existing.name = name
            existing.description = description
            existing.tools = tools
            existing.mcp_tools = mcp_tools
            existing.prompt = prompt
            existing.max_turns = max_turns
            existing.timeout_seconds = timeout_seconds
            existing.model = model
            existing.iteration_model = iteration_model
            existing.effort = effort
            await self._db.flush()
            await self._db.refresh(existing)
            return existing

        skill = AgentSkill(
            org_id=self._org_id,
            skill_slug=skill_slug,
            agent_type=agent_type,
            is_default=is_default,
            is_custom=False,
            name=name,
            description=description,
            tools=tools,
            mcp_tools=mcp_tools,
            prompt=prompt,
            max_turns=max_turns,
            timeout_seconds=timeout_seconds,
            model=model,
            iteration_model=iteration_model,
            effort=effort,
        )
        return await self.create(skill)
