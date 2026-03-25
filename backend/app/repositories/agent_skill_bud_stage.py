"""Agent skill BUD stage mapping data access repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_skill_bud_stage import AgentSkillBudStage
from app.repositories.base import BaseRepository


class AgentSkillBudStageRepository(BaseRepository[AgentSkillBudStage]):
    """Repository for agent-skill-to-BUD-stage mappings, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(AgentSkillBudStage, db, org_id=org_id)

    async def get_for_status(self, bud_status: str) -> list[AgentSkillBudStage]:
        """Get all stage mappings for a BUD status, ordered by execution_order.

        Args:
            bud_status: The BUD status string (e.g. 'bud', 'tech_arch').

        Returns:
            List of mappings ordered by execution_order ascending.
        """
        stmt = self._scoped(
            select(AgentSkillBudStage)
            .where(AgentSkillBudStage.bud_status == bud_status)
            .order_by(AgentSkillBudStage.execution_order.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_for_status_and_order(
        self, bud_status: str, execution_order: int
    ) -> AgentSkillBudStage | None:
        """Get a specific stage mapping by status and order.

        Args:
            bud_status: The BUD status string.
            execution_order: The execution order position.

        Returns:
            The mapping, or None if not found.
        """
        stmt = self._scoped(
            select(AgentSkillBudStage)
            .where(AgentSkillBudStage.bud_status == bud_status)
            .where(AgentSkillBudStage.execution_order == execution_order)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
