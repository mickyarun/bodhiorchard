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

"""BUD TODO endpoints — list, update, claim, auto-assign."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud import BUDStatus
from app.models.bud_todo import BUDTodo, BUDTodoStatus
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
from app.services.pr_auto_transition import check_all_repos_have_prs
from app.services.todo_sync import sync_todos_for_bud

logger = structlog.get_logger(__name__)

router = APIRouter()


def _to_read(todo: BUDTodo) -> BUDTodoRead:
    """Serialise a TODO including assignee_name (eager-loaded)."""
    data = BUDTodoRead.model_validate(todo)
    if todo.assignee is not None:
        data.assignee_name = todo.assignee.name
    return data


async def _fetch_or_404(db: AsyncSession, org_id: uuid.UUID, bud_id: uuid.UUID) -> None:
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

    became_completed = (
        new_status == BUDTodoStatus.COMPLETED.value
        and todo.status != BUDTodoStatus.COMPLETED.value
    )

    if new_status is not None:
        todo.status = new_status
    if body.assignee_id is not None or "assignee_id" in body.model_fields_set:
        todo.assignee_id = body.assignee_id
    if body.summary is not None:
        todo.summary = body.summary

    await db.flush()

    # Mirror of the MCP ``complete_todo`` re-check: if this PATCH was the
    # one that flipped a TODO to completed, the BUD's dev → code_review
    # gate may now be passable. Without this, a TODO completed via the
    # UI (rather than ``complete_todo``) would leave the BUD stuck in
    # development even though every precondition is met. The function
    # is a no-op when the gate or any other precondition isn't met.
    if became_completed:
        bud = await BUDRepository(db, org_id=current_user.org_id).get_by_id(bud_id)
        if bud is not None:
            await check_all_repos_have_prs(db, current_user.org_id, bud)

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
    return BUDTodoClaimResponse(todo=_to_read(refreshed), previous_assignee_id=previous)


@router.post(
    "/{bud_id}/todos/regenerate",
    response_model=list[BUDTodoRead],
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def regenerate_todos(
    bud_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BUDTodoRead]:
    """Re-derive TODOs from the current tech spec and return the new list.

    Synchronous: the deterministic parser runs in-request, the reconciler
    preserves any claimed / completed rows, and the response carries the
    fresh state. Concurrent calls for the same BUD are safe — the
    sequence-keyed reconciler is idempotent; the worst case is one
    request hitting a unique-constraint conflict and the client
    refreshing.
    """
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "BUD not found")
    if bud.status != BUDStatus.DEVELOPMENT.value:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"BUD must be in development phase (currently {bud.status}).",
        )

    count = await sync_todos_for_bud(db, current_user.org_id, bud, mode="regenerate")
    publish(
        f"todo:{bud_id}",
        {
            "event": "todos_regenerated",
            "bud_id": str(bud_id),
            "todo_count": count,
        },
    )
    todo_repo = BUDTodoRepository(db, org_id=current_user.org_id)
    todos = await todo_repo.list_for_bud(bud_id)
    return [_to_read(t) for t in todos]
