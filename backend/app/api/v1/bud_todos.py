"""BUD TODO endpoints — list, update, claim, auto-assign."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud_todo import BUDTodo
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.bud_todo import BUDTodoRepository
from app.schemas.bud_todos import (
    BUDTodoClaimResponse,
    BUDTodoRead,
    BUDTodoUpdate,
)
from app.services.bud_timeline import record_event
from app.services.event_bus import publish

logger = structlog.get_logger(__name__)

router = APIRouter()


def _to_read(todo: BUDTodo) -> BUDTodoRead:
    """Serialise a TODO including assignee_name (eager-loaded)."""
    data = BUDTodoRead.model_validate(todo)
    if todo.assignee is not None:
        data.assignee_name = todo.assignee.name
    return data


async def _fetch_or_404(
    db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID
) -> None:
    """Ensure the BUD exists and belongs to the current org."""
    bud_repo = BUDRepository(db, org_id=org_id)
    if await bud_repo.get_by_id(bud_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "BUD not found")


@router.get(
    "/{bud_id}/todos",
    response_model=list[BUDTodoRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_todos(
    bud_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BUDTodoRead]:
    """List all TODOs for a BUD, ordered by sequence."""
    await _fetch_or_404(db, current_user.org_id, bud_id)
    repo = BUDTodoRepository(db, org_id=current_user.org_id)
    todos = await repo.list_for_bud(bud_id)
    return [_to_read(t) for t in todos]


@router.patch(
    "/{bud_id}/todos/{todo_id}",
    response_model=BUDTodoRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def update_todo(
    bud_id: uuid.UUID,
    todo_id: uuid.UUID,
    body: BUDTodoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BUDTodoRead:
    """Update a TODO's status, assignee, or summary."""
    repo = BUDTodoRepository(db, org_id=current_user.org_id)
    todo = await repo.get_by_id(todo_id)
    if todo is None or todo.bud_id != bud_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "TODO not found")

    try:
        new_status = body.validated_status()
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if new_status is not None:
        todo.status = new_status
    if body.assignee_id is not None or "assignee_id" in body.model_fields_set:
        todo.assignee_id = body.assignee_id
    if body.summary is not None:
        todo.summary = body.summary

    await db.flush()
    # Refresh to pick up any assignee relationship changes.
    refreshed = await repo.get_by_sequence(bud_id, todo.sequence)
    assert refreshed is not None
    return _to_read(refreshed)


@router.post(
    "/{bud_id}/todos/{todo_id}/claim",
    response_model=BUDTodoClaimResponse,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def claim_todo(
    bud_id: uuid.UUID,
    todo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BUDTodoClaimResponse:
    """Self-assign: current user claims this TODO.

    Publishes ``todo:{bud_id}`` so other sessions watching the BUD see
    the change. Does not move the TODO to ``in_progress`` — that's the
    ``takeover_todo`` MCP tool's job (it's stricter and atomic).
    """
    repo = BUDTodoRepository(db, org_id=current_user.org_id)
    todo = await repo.get_by_id(todo_id)
    if todo is None or todo.bud_id != bud_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "TODO not found")
    if todo.is_checkpoint:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Checkpoints cannot be claimed — they are review gates.",
        )

    previous = todo.assignee_id
    todo.assignee_id = current_user.id
    await db.flush()

    await record_event(
        db,
        current_user.org_id,
        bud_id,
        "todo_claimed",
        actor_id=current_user.id,
        actor_name=current_user.name,
        detail={
            "todo_id": str(todo_id),
            "sequence": todo.sequence,
            "previous_assignee_id": str(previous) if previous else None,
        },
    )

    publish(
        f"todo:{bud_id}",
        {
            "event": "claimed",
            "todo_id": str(todo_id),
            "sequence": todo.sequence,
            "claimed_by_id": str(current_user.id),
            "claimed_by_name": current_user.name,
            "previous_assignee_id": str(previous) if previous else None,
        },
    )

    refreshed = await repo.get_by_sequence(bud_id, todo.sequence)
    assert refreshed is not None
    return BUDTodoClaimResponse(
        todo=_to_read(refreshed), previous_assignee_id=previous
    )


