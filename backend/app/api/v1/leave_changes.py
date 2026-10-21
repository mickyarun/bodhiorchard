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

"""Managers, HR and the owner change approved leave that isn't over yet."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import PermissionSet, get_current_user, get_db, get_permission_set
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.models.user import User
from app.schemas.leave import LeaveRequestRead
from app.schemas.leave_views import DecisionBody, RescheduleBody
from app.services.leave.changes import withdraw
from app.services.leave.notify_changes import stage_change
from app.services.leave.reschedule import reschedule
from app.services.leave.type_privacy import sees_restricted
from app.services.leave.views import request_reads

router = APIRouter(tags=["leave"])


async def _done(
    db: AsyncSession,
    request: LeaveRequest,
    current_user: User,
    perms: PermissionSet,
    *,
    withdrawn: bool,
) -> LeaveRequestRead:
    """Commit, tell the requester, and answer with the request as it is now."""
    org_id = current_user.org_id
    notice = stage_change(
        db, org_id=org_id, request=request, actor_name=current_user.name, withdrawn=withdrawn
    )
    # Commit, then tell them: nobody hears about a change that rolled back.
    await db.commit()
    notice.send()
    today = datetime.now(UTC).date()
    (read,) = await request_reads(
        db,
        org_id,
        [request],
        viewer=current_user.id,
        today=today,
        private_ok=lambda _r: True,
        sees_restricted=sees_restricted(perms),
    )
    still_open = request.status == LeaveStatus.APPROVED and request.end_date >= today
    return read.model_copy(update={"can_change": still_open})


@router.post("/requests/{request_id}/withdraw", response_model=LeaveRequestRead)
async def withdraw_approval(
    request_id: uuid.UUID,
    body: DecisionBody,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestRead:
    """Withdraw an approval (a note is required); leave under way ends today."""
    request = await withdraw(
        db,
        org_id=current_user.org_id,
        actor=current_user.id,
        perms=perms,
        request_id=request_id,
        note=body.note,
    )
    return await _done(db, request, current_user, perms, withdrawn=True)


@router.post("/requests/{request_id}/reschedule", response_model=LeaveRequestRead)
async def reschedule_leave(
    request_id: uuid.UUID,
    body: RescheduleBody,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestRead:
    """Move or shorten approved leave; started leave can only change its end."""
    request = await reschedule(
        db,
        org_id=current_user.org_id,
        actor=current_user.id,
        perms=perms,
        request_id=request_id,
        start=body.start_date,
        end=body.end_date,
        half_day=body.half_day,
        note=body.note,
    )
    return await _done(db, request, current_user, perms, withdrawn=False)
