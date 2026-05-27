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

"""Single-BUD assignment + unassignment helpers.

Extracted from ``bud_assignment`` so the yield-offer service (and any
future caller) can use them without recreating a circular import. The
chain walker in ``bud_assignment`` and the yield-offer accept flow both
depend on these primitives; isolating them in a leaf module is the only
clean way to share.

Records a timeline event on every change and (for DEVELOPMENT)
cascades the new assignee onto non-claimed TODOs.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.bud_timeline import record_event
from app.services.todo_assignment import cascade_assignee_to_todos


async def assign_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    assignee_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
    *,
    method: str = "manual",
) -> None:
    """Assign a BUD. Records timeline event + cascades TODOs in DEVELOPMENT.

    ``method`` is stamped into the timeline detail so the BUD detail
    page can distinguish a manual reassignment from one driven by an
    accepted yield offer (``"yield_offer_accepted"``) or any future
    automated source.

    During DEVELOPMENT, also cascades the new assignee onto every
    non-checkpoint TODO — UNLESS any TODO is already in_progress,
    completed, or has been taken over via ``takeover_todo``. In that
    case the cascade is skipped to preserve developer claims, and the
    top-level reassignment still goes through for visibility.
    """
    assignee = await db.get(User, assignee_id)
    bud.assignee_id = assignee_id
    # Record the assignee's current role too, so continuity lookups on
    # phase re-entry can match this manual event. Falls back to None
    # when the role can't be resolved (legacy data, no membership row).
    user_role = await UserRepository(db).get_role(assignee_id, org_id)
    detail: dict[str, Any] = {
        "assignee_id": str(assignee_id),
        "assignee_name": assignee.name if assignee else None,
        "method": method,
        "phase": bud.status.value,
    }
    if user_role is not None:
        detail["role"] = user_role.value
    await record_event(
        db,
        org_id,
        bud.id,
        "assigned",
        actor_id=actor_id,
        actor_name=actor_name,
        detail=detail,
    )

    if bud.status == BUDStatus.DEVELOPMENT:
        # The cascade returns -1 (and is a no-op) when any TODO has been
        # claimed or progressed — no exception, so no try/except needed.
        # A genuine DB error must propagate so the outer transaction rolls
        # back; silently logging would leave the BUD assignee changed but
        # the TODOs stale, which is worse than failing the whole request.
        await cascade_assignee_to_todos(db, org_id, bud.id, assignee_id)


async def unassign_bud(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    actor_id: uuid.UUID | None,
    actor_name: str | None,
    *,
    reason: str | None = None,
) -> None:
    """Remove assignment from a BUD. Records timeline event.

    ``reason`` is stamped into the detail so the BUD detail page can
    explain *why* the BUD became unassigned (e.g. ``"yielded"`` when
    the previous owner accepted a yield offer).
    """
    old_id = bud.assignee_id
    bud.assignee_id = None
    detail: dict[str, Any] = {"previous_assignee_id": str(old_id) if old_id else None}
    if reason is not None:
        detail["reason"] = reason
    await record_event(
        db,
        org_id,
        bud.id,
        "unassigned",
        actor_id=actor_id,
        actor_name=actor_name,
        detail=detail,
    )
