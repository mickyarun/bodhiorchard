"""Default TODO assignment on DEVELOPMENT entry.

On DEVELOPMENT entry the BUD's phase lead (chosen by smart assignment)
owns every TODO. Other developers can pick up individual items via the
Claim UI or the MCP ``takeover_todo`` tool — that is the only way a
TODO transfers hands.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud_todo import BUDTodo, BUDTodoStatus

logger = structlog.get_logger(__name__)


async def assign_all_todos_to_lead(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    lead_user_id: uuid.UUID,
) -> int:
    """Assign every unassigned non-checkpoint TODO to the phase lead.

    Preserves the existing single-owner-per-BUD mental model. Other
    developers can self-assign individual TODOs afterwards via the UI
    or MCP ``takeover_todo``.

    Returns the number of TODOs newly assigned.
    """
    unassigned = await _list_unassigned_non_checkpoint_todos(db, org_id, bud_id)
    if not unassigned:
        return 0

    for todo in unassigned:
        todo.assignee_id = lead_user_id

    await db.flush()
    logger.info(
        "todo_assigned_to_lead",
        bud_id=str(bud_id),
        lead_user_id=str(lead_user_id),
        assigned=len(unassigned),
    )
    return len(unassigned)


async def _list_unassigned_non_checkpoint_todos(
    db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID
) -> list[BUDTodo]:
    result = await db.execute(
        select(BUDTodo)
        .where(
            BUDTodo.org_id == org_id,
            BUDTodo.bud_id == bud_id,
            BUDTodo.assignee_id.is_(None),
            BUDTodo.status == BUDTodoStatus.PENDING.value,
            BUDTodo.is_checkpoint.is_(False),
        )
        .order_by(BUDTodo.sequence.asc())
    )
    return list(result.scalars().all())
