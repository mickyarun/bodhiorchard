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

"""The approvals queue: what the caller can decide, with context.

Lookups are batched per page (approvers, profiles, the reporting graph),
and "balance after" is best-effort and read-only, so one member's data
can't break the whole queue.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.leave_request import LeaveKind, LeaveRequest
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.user import UserRepository
from app.schemas.leave_views import AlsoOut, ApprovalCount, ApprovalItem
from app.services.leave.approvers import APPROVE, Approvers, approvers_for_many, route_for
from app.services.leave.balances import balances_for, find_line
from app.services.leave.calendar_math import leave_year_bounds
from app.services.leave.policies import resolve_member_policy
from app.services.leave.views import request_reads

logger = structlog.get_logger(__name__)
DECIDED_WINDOW = timedelta(days=90)
Route = Literal["manager", "hr_queue", "hr_override"]


async def _decidable(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor: uuid.UUID,
    perms: PermissionSet,
    status: Literal["pending", "decided"],
) -> tuple[
    list[tuple[LeaveRequest, Route]], dict[uuid.UUID, Approvers], list[tuple[uuid.UUID, uuid.UUID]]
]:
    repo = LeaveRequestRepository(db, org_id=org_id)
    edges = await EmployeeReportingManagerRepository(db, org_id=org_id).reporting_edges()
    scope = None if perms.has(APPROVE) else {who for who, boss in edges if boss == actor}
    if scope is not None and not scope:
        return [], {}, edges
    requests = (
        await repo.list_pending(scope)
        if status == "pending"
        else await repo.list_decided(scope, datetime.now(UTC) - DECIDED_WINDOW)
    )
    approvers = await approvers_for_many(db, org_id, {r.user_id for r in requests})
    allowed: list[tuple[LeaveRequest, Route]] = []
    for request in requests:
        route = route_for(actor, perms, request.user_id, approvers[request.user_id])
        if route is not None:
            allowed.append((request, route))
    return allowed, approvers, edges


async def approval_items(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor: uuid.UUID,
    perms: PermissionSet,
    status: Literal["pending", "decided"],
) -> list[ApprovalItem]:
    """Requests the caller may decide (or decided recently)."""
    allowed, approvers, edges = await _decidable(db, org_id, actor, perms, status)
    requests = [r for r, _ in allowed]
    reads = await request_reads(
        db,
        org_id,
        requests,
        viewer=actor,
        today=datetime.now(UTC).date(),
        private_ok=lambda _r: True,
    )
    profiles = await EmployeeProfileRepository(db, org_id=org_id).by_users(
        {r.user_id for r in requests}
    )
    items = []
    for (request, route), read in zip(allowed, reads, strict=True):
        profile = profiles.get(request.user_id)
        items.append(
            ApprovalItem(
                request=read,
                route=route,
                designation=profile.designation if profile else None,
                department=profile.department if profile else None,
                balance_after=await _balance_after(db, org_id, request)
                if status == "pending"
                else None,
                also_out=await _also_out(db, org_id, request, approvers[request.user_id], edges)
                if status == "pending"
                else [],
            )
        )
    return items


async def _balance_after(
    db: AsyncSession, org_id: uuid.UUID, request: LeaveRequest
) -> Decimal | None:
    """Balance once approved (pending days already count); None if unknown."""
    if request.kind != LeaveKind.LEAVE or request.leave_type_id is None:
        return None
    try:
        member = await resolve_member_policy(db, org_id, request.user_id)
        year = leave_year_bounds(request.start_date, member.policy.year_start_month)
        lines = await balances_for(
            db, policy=member.policy, profile=member.profile, user_id=request.user_id, year=year
        )
    except Exception:
        logger.warning("leave_balance_after_failed", request_id=str(request.id), exc_info=True)
        return None
    line = find_line(lines, request.leave_type_id)
    return line.available if line else None


async def _also_out(
    db: AsyncSession,
    org_id: uuid.UUID,
    request: LeaveRequest,
    approvers: Approvers,
    edges: Sequence[tuple[uuid.UUID, uuid.UUID]],
) -> list[AlsoOut]:
    """Teammates (same manager) out on any of the requested days; no types."""
    team = {who for who, boss in edges if boss in approvers.manager_ids} - {request.user_id}
    if not team:
        return []
    clashes = await LeaveRequestRepository(db, org_id=org_id).active_between(
        team, request.start_date, request.end_date
    )
    names = await UserRepository(db).get_names_by_ids({c.user_id for c in clashes})
    return [
        AlsoOut(
            name=names.get(c.user_id, "Someone"),
            kind=c.kind,
            start_date=c.start_date,
            end_date=c.end_date,
        )
        for c in clashes
    ]


async def approval_count(
    db: AsyncSession, org_id: uuid.UUID, actor: uuid.UUID, perms: PermissionSet
) -> ApprovalCount:
    """Pending requests the caller can act on, for the nav badge (no extras)."""
    allowed, _, edges = await _decidable(db, org_id, actor, perms, "pending")
    is_approver = perms.has(APPROVE) or any(boss == actor for _, boss in edges)
    return ApprovalCount(pending=len(allowed), is_approver=is_approver)
