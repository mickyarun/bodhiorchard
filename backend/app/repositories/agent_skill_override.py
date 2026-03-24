"""Agent skill override data access repository."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_skill_override import AgentSkillOverride
from app.repositories.base import BaseRepository


class AgentSkillOverrideRepository(BaseRepository[AgentSkillOverride]):
    """Repository for agent skill overrides, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(AgentSkillOverride, db, org_id=org_id)

    async def get_by_slug(self, skill_slug: str) -> AgentSkillOverride | None:
        """Fetch a single override by its skill slug.

        Args:
            skill_slug: The skill identifier (e.g. 'triage-analyst').

        Returns:
            The override row, or None if no override exists.
        """
        stmt = self._scoped(
            select(AgentSkillOverride).where(AgentSkillOverride.skill_slug == skill_slug)
        )
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
    ) -> AgentSkillOverride:
        """Insert or update an override for a skill slug.

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
            The created or updated override.
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

        override = AgentSkillOverride(
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
        return await self.create(override)

    async def delete_by_slug(self, skill_slug: str) -> bool:
        """Delete an override by skill slug.

        Args:
            skill_slug: The skill identifier.

        Returns:
            True if a row was deleted, False if no override existed.
        """
        stmt = (
            delete(AgentSkillOverride)
            .where(AgentSkillOverride.org_id == self._org_id)
            .where(AgentSkillOverride.skill_slug == skill_slug)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return (result.rowcount or 0) > 0
