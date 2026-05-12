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

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_skill import AgentSkill
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

    async def get_by_slug(self, skill_slug: str) -> AgentSkill | None:
        """Fetch a single skill by its slug.

        Args:
            skill_slug: The skill identifier (e.g. 'product-manager').

        Returns:
            The skill row, or None if not found.
        """
        stmt = self._scoped(select(AgentSkill).where(AgentSkill.skill_slug == skill_slug))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        skill_slug: str,
        name: str,
        description: str,
        tools: list[str],
        mcp_tools: list[str],
        prompt: str,
        max_turns: int = 0,
        model: str = "",
        effort: str = "",
    ) -> AgentSkill:
        """Insert or update a skill for a given slug.

        Args:
            skill_slug: The skill identifier.
            name: Display name.
            description: Short description.
            tools: List of file-based tools.
            mcp_tools: List of MCP tools.
            prompt: Full markdown prompt body.
            max_turns: Max Claude CLI turns (0 = unlimited).
            model: Claude model alias or ID (empty = CLI default).
            effort: Reasoning effort level (empty = default).

        Returns:
            The created or updated skill.
        """
        existing = await self.get_by_slug(skill_slug)
        if existing is not None:
            existing.name = name
            existing.description = description
            existing.tools = tools
            existing.mcp_tools = mcp_tools
            existing.prompt = prompt
            existing.max_turns = max_turns
            existing.model = model
            existing.effort = effort
            await self._db.flush()
            await self._db.refresh(existing)
            return existing

        skill = AgentSkill(
            org_id=self._org_id,
            skill_slug=skill_slug,
            name=name,
            description=description,
            tools=tools,
            mcp_tools=mcp_tools,
            prompt=prompt,
            max_turns=max_turns,
            model=model,
            effort=effort,
        )
        return await self.create(skill)

    async def delete_by_slug(self, skill_slug: str) -> bool:
        """Delete a skill by slug.

        Args:
            skill_slug: The skill identifier.

        Returns:
            True if a row was deleted, False if not found.
        """
        stmt = (
            delete(AgentSkill)
            .where(AgentSkill.org_id == self._org_id)
            .where(AgentSkill.skill_slug == skill_slug)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return (rowcount(result) or 0) > 0
