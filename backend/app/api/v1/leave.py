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

"""Self-service leave: overview, my requests, preview, submit, cancel.

Open to every member; each person only ever touches their own requests.
"""

import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.leave_request import LeaveStatus
from app.models.user import User
from app.repositories.leave_request import LeaveRequestRepository
from app.schemas.leave import (
    ExcludedDate,
    LeavePreview,
    LeaveRequestCreate,
    LeaveRequestRead,
    PersonRef,
)
from app.schemas.leave_summary import LeaveSummary
from app.services.leave.approvers import notify_targets
from app.services.leave.cancellation import cancel
from app.services.leave.evaluation import evaluate
from app.services.leave.lifecycle import submit
from app.services.leave.notify import after_cancel, stage_new_request
from app.services.leave.policies import resolve_member_policy, today_for
from app.services.leave.summary import build_summary
from app.services.leave.views import request_reads

router = APIRouter(tags=["leave"])


async def _today(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> date:
    """Today in the member's policy timezone (decides "can cancel")."""
    return today_for((await resolve_member_policy(db, org_id, user_id)).policy)


@router.get("/me/summary", response_model=LeaveSummary)
async def my_summary(
    year: int | None = Query(None, ge=2000, le=2100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaveSummary:
    """Policy, balances, optional holidays and approvers for the caller."""
    return await build_summary(db, current_user.org_id, current_user.id, year)


@router.get("/me/requests", response_model=list[LeaveRequestRead])
async def my_requests(
    scope: Literal["upcoming", "past", "all"] = "upcoming",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LeaveRequestRead]:
    """The caller's own requests."""
    org_id = current_user.org_id
    member = await resolve_member_policy(db, org_id, current_user.id)
    today = today_for(member.policy)
    requests = await LeaveRequestRepository(db, org_id=org_id).list_for_user(
        current_user.id, scope, today
    )
    return await request_reads(
        db, org_id, requests, viewer=current_user.id, today=today, private_ok=lambda _r: True
    )


@router.post("/requests/preview", response_model=LeavePreview)
async def preview_request(
    body: LeaveRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeavePreview:
    """What a request would cost and who'd approve it. Doesn't create a request."""
    member = await resolve_member_policy(db, current_user.org_id, current_user.id)
    result = await evaluate(db, member=member, user_id=current_user.id, body=body)
    return LeavePreview(
        days=result.days,
        lop_days=result.lop_days,
        excluded=[ExcludedDate(date=d, reason=r) for d, r in result.excluded],
        balance_before=result.balance_before,
        balance_after=result.balance_after,
        auto_approved=result.auto_approved,
        approvers=[PersonRef(user_id=u, name=n) for u, n in result.approvers.managers],
        routes_to_hr=result.approvers.routes_to_hr,
        problems=result.problems,
        high_leave=result.high_leave,
    )


@router.post("/requests", response_model=LeaveRequestRead, status_code=status.HTTP_201_CREATED)
async def create_request(
    body: LeaveRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestRead:
    """Send a request; WFH within the policy's allowance is approved at once."""
    org_id = current_user.org_id
    request, result = await submit(db, org_id, current_user.id, body)
    auto = request.status == LeaveStatus.APPROVED
    targets = (
        result.approvers.manager_ids
        if auto
        else await notify_targets(db, org_id, result.approvers, current_user.id)
    )
    notice = stage_new_request(
        db,
        org_id=org_id,
        request=request,
        requester_name=current_user.name,
        targets=targets,
        auto_approved=auto,
        high_leave=result.high_leave,
    )
    # Commit, then tell people: nobody hears about a request that rolled back.
    await db.commit()
    notice.send()
    reads = await request_reads(
        db,
        org_id,
        [request],
        viewer=current_user.id,
        today=await _today(db, org_id, current_user.id),
        private_ok=lambda _r: True,
    )
    return reads[0]


@router.post("/requests/{request_id}/cancel", response_model=LeaveRequestRead)
async def cancel_request(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LeaveRequestRead:
    """Cancel one of the caller's own requests."""
    org_id = current_user.org_id
    request = await cancel(db, org_id, current_user.id, request_id)
    notice = after_cancel(org_id, request)
    # Commit, then update approvers' Slack prompts (see create_request).
    await db.commit()
    notice.send()
    reads = await request_reads(
        db,
        org_id,
        [request],
        viewer=current_user.id,
        today=await _today(db, org_id, current_user.id),
        private_ok=lambda _r: True,
    )
    return reads[0]
