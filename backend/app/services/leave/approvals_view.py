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

Every lookup is batched per page: approvers, profiles, the reporting
graph, balance-after, who else is out, and each requester's balances and
last leave, so the query count doesn't grow
with the queue.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.leave_request_filter import RequestFilter
from app.repositories.leave_type import LeaveTypeRepository
from app.schemas.leave_views import ApprovalCount, ApprovalFilters, ApprovalItem, ApprovalPage
from app.services.leave.also_out import also_out
from app.services.leave.approval_context import RequesterContext, requester_context
from app.services.leave.approvers import Approvers, approvers_for_many, route_for
from app.services.leave.balance_after import balances_after
from app.services.leave.high_leave import for_requests
from app.services.leave.permissions import APPROVE
from app.services.leave.type_privacy import sees_restricted, shown
from app.services.leave.views import request_reads

DECIDED_WINDOW = timedelta(days=90)
# The newest decisions shown; past this the page says so and asks for dates.
DECIDED_LIMIT = 200
Route = Literal["manager", "hr_queue", "hr_override"]


@dataclass(frozen=True)
class Decidable:
    """Requests the caller can act on, with what was loaded to decide that."""

    allowed: list[tuple[LeaveRequest, Route]]
    approvers: dict[uuid.UUID, Approvers]
    edges: list[tuple[uuid.UUID, uuid.UUID]]
    # More decisions matched than DECIDED_LIMIT; older ones were left out.
    truncated: bool = False


async def _hidden_type(
    db: AsyncSession, org_id: uuid.UUID, perms: PermissionSet, type_id: uuid.UUID | None
) -> bool:
    if type_id is None or sees_restricted(perms):
        return False
    leave_type = await LeaveTypeRepository(db, org_id=org_id).get_by_id(type_id)
    return not shown(leave_type, sees_all=False)


async def _decidable(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor: uuid.UUID,
    perms: PermissionSet,
    status: Literal["pending", "decided"],
    filters: ApprovalFilters | None = None,
) -> Decidable:
    repo = LeaveRequestRepository(db, org_id=org_id)
    edges = await EmployeeReportingManagerRepository(db, org_id=org_id).reporting_edges()
    scope = None if perms.has(APPROVE) else {who for who, boss in edges if boss == actor}
    if filters is not None and filters.user_id is not None:
        # Narrows only: someone outside the caller's scope stays out.
        scope = {filters.user_id} if scope is None else scope & {filters.user_id}
    if scope is not None and not scope:
        return Decidable([], {}, edges)
    if filters is not None and await _hidden_type(db, org_id, perms, filters.leave_type_id):
        # Filtering on a type the caller can't see would list who took it.
        return Decidable([], {}, edges)
    narrow = (
        RequestFilter(
            start=filters.start,
            end=filters.end,
            kind=filters.kind,
            leave_type_id=filters.leave_type_id,
        )
        if filters is not None
        else None
    )
    # A date range replaces the "last 90 days" window for decided requests.
    since = None if filters is not None and filters.dated else datetime.now(UTC) - DECIDED_WINDOW
    requests = (
        await repo.list_pending(scope, narrow)
        if status == "pending"
        else await repo.list_decided(
            scope, since, narrow, limit=DECIDED_LIMIT, open_from=datetime.now(UTC).date()
        )
    )
    approvers = await approvers_for_many(db, org_id, {r.user_id for r in requests})
    allowed: list[tuple[LeaveRequest, Route]] = []
    for request in requests:
        route = route_for(actor, perms, request.user_id, approvers[request.user_id])
        if route is not None:
            allowed.append((request, route))
    # Counted before routing drops any (e.g. the caller's own requests).
    truncated = status == "decided" and len(requests) >= DECIDED_LIMIT
    return Decidable(allowed, approvers, edges, truncated)


async def approval_items(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor: uuid.UUID,
    perms: PermissionSet,
    status: Literal["pending", "decided"],
    filters: ApprovalFilters | None = None,
) -> ApprovalPage:
    """Requests the caller may decide (or decided recently), optionally filtered.

    The nav count (:func:`approval_count`) stays unfiltered.
    """
    found = await _decidable(db, org_id, actor, perms, status, filters)
    allowed = found.allowed
    requests = [r for r, _ in allowed]
    today = datetime.now(UTC).date()
    sees = sees_restricted(perms)
    reads = await request_reads(
        db,
        org_id,
        requests,
        viewer=actor,
        today=today,
        private_ok=lambda _r: True,
        sees_restricted=sees,
    )
    profiles = await EmployeeProfileRepository(db, org_id=org_id).by_users(
        {r.user_id for r in requests}
    )
    pending = status == "pending"
    after = await balances_after(db, org_id, requests) if pending else {}
    also = (
        await also_out(db, org_id, actor, perms, requests, found.approvers, found.edges)
        if pending
        else {}
    )
    users = {r.user_id for r in requests}
    context = (
        await requester_context(db, org_id, users, today, sees_all=sees)
        if pending
        else RequesterContext()
    )
    high = await for_requests(db, org_id, requests) if pending else {}
    items = []
    for (request, route), read in zip(allowed, reads, strict=True):
        profile = profiles.get(request.user_id)
        # A hidden type's balance would match none of the lines shown beside it.
        hidden = request.leave_type_id is not None and read.leave_type is None
        if hidden:
            after.pop(request.id, None)
        # Approved and not over: the caller may still move it or withdraw it.
        open_ = (
            not pending and request.status == LeaveStatus.APPROVED and request.end_date >= today
        )
        items.append(
            ApprovalItem(
                request=read.model_copy(update={"can_change": open_}),
                route=route,
                designation=profile.designation if profile else None,
                department=profile.department if profile else None,
                balance_after=after[request.id].days if request.id in after else None,
                balance_after_year=after[request.id].year if request.id in after else None,
                also_out=also.get(request.id, []),
                balances=context.balances.get(request.user_id, []),
                balance_year=context.years.get(request.user_id),
                last_leave=context.last_leave.get(request.user_id),
                high_leave=high.get(request.id),
            )
        )
    return ApprovalPage(items=items, truncated=found.truncated)


async def approval_count(
    db: AsyncSession, org_id: uuid.UUID, actor: uuid.UUID, perms: PermissionSet
) -> ApprovalCount:
    """Pending requests the caller can act on, for the nav badge (no extras)."""
    found = await _decidable(db, org_id, actor, perms, "pending")
    has_reports = any(boss == actor for _, boss in found.edges)
    return ApprovalCount(
        pending=len(found.allowed),
        is_approver=perms.has(APPROVE) or has_reports,
        has_reports=has_reports,
    )
