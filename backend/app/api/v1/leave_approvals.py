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

"""The approvals queue: managers decide their reports' requests, HR any."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import PermissionSet, get_current_user, get_db, get_permission_set
from app.models.user import User
from app.schemas.leave import LeaveRequestRead
from app.schemas.leave_views import ApprovalCount, ApprovalItem, DecisionBody
from app.services.leave.approvals_view import approval_count, approval_items
from app.services.leave.lifecycle import decide
from app.services.leave.notify import notify_decision
from app.services.leave.views import request_reads

router = APIRouter(tags=["leave"])


@router.get("/approvals", response_model=list[ApprovalItem])
async def list_approvals(
    status: Literal["pending", "decided"] = "pending",
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalItem]:
    """Requests the caller can decide, or decided in the last 90 days."""
    return await approval_items(db, current_user.org_id, current_user.id, perms, status)


@router.get("/approvals/count", response_model=ApprovalCount)
async def count_approvals(
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> ApprovalCount:
    """Pending requests awaiting the caller, and whether they approve at all."""
    return await approval_count(db, current_user.org_id, current_user.id, perms)


async def _decide(
    request_id: uuid.UUID,
    body: DecisionBody,
    approve: bool,
    current_user: User,
    perms: PermissionSet,
    db: AsyncSession,
) -> LeaveRequestRead:
    org_id = current_user.org_id
    request = await decide(
        db,
        org_id=org_id,
        actor=current_user.id,
        perms=perms,
        request_id=request_id,
        approve=approve,
        note=body.note,
    )
    # Commit before telling the requester (see create_request).
    await db.commit()
    notify_decision(db, org_id=org_id, request=request, decider_name=current_user.name)
    reads = await request_reads(
        db,
        org_id,
        [request],
        viewer=current_user.id,
        today=datetime.now(UTC).date(),
        private_ok=lambda _r: True,
    )
    return reads[0]


@router.post("/requests/{request_id}/approve", response_model=LeaveRequestRead)
async def approve_request(
    request_id: uuid.UUID,
    body: DecisionBody,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestRead:
    """Approve a pending request (first decision wins)."""
    return await _decide(request_id, body, True, current_user, perms, db)


@router.post("/requests/{request_id}/reject", response_model=LeaveRequestRead)
async def reject_request(
    request_id: uuid.UUID,
    body: DecisionBody,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestRead:
    """Reject a pending request; a note is required."""
    return await _decide(request_id, body, False, current_user, perms, db)
