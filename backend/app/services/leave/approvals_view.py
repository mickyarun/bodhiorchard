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
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.leave_request import LeaveRequest
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.leave_request_filter import RequestFilter
from app.repositories.user import UserRepository
from app.schemas.leave_views import AlsoOut, ApprovalCount, ApprovalFilters, ApprovalItem
from app.services.leave.approval_context import RequesterContext, requester_context
from app.services.leave.approvers import Approvers, approvers_for_many, route_for
from app.services.leave.balance_after import balances_after
from app.services.leave.permissions import APPROVE
from app.services.leave.views import request_reads

DECIDED_WINDOW = timedelta(days=90)
Route = Literal["manager", "hr_queue", "hr_override"]


async def _decidable(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor: uuid.UUID,
    perms: PermissionSet,
    status: Literal["pending", "decided"],
    filters: ApprovalFilters | None = None,
) -> tuple[
    list[tuple[LeaveRequest, Route]], dict[uuid.UUID, Approvers], list[tuple[uuid.UUID, uuid.UUID]]
]:
    repo = LeaveRequestRepository(db, org_id=org_id)
    edges = await EmployeeReportingManagerRepository(db, org_id=org_id).reporting_edges()
    scope = None if perms.has(APPROVE) else {who for who, boss in edges if boss == actor}
    if filters is not None and filters.user_id is not None:
        # Narrows only: someone outside the caller's scope stays out.
        scope = {filters.user_id} if scope is None else scope & {filters.user_id}
    if scope is not None and not scope:
        return [], {}, edges
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
        else await repo.list_decided(scope, since, narrow)
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
    filters: ApprovalFilters | None = None,
) -> list[ApprovalItem]:
    """Requests the caller may decide (or decided recently), optionally filtered.

    The nav count (:func:`approval_count`) stays unfiltered.
    """
    allowed, approvers, edges = await _decidable(db, org_id, actor, perms, status, filters)
    requests = [r for r, _ in allowed]
    today = datetime.now(UTC).date()
    reads = await request_reads(
        db, org_id, requests, viewer=actor, today=today, private_ok=lambda _r: True
    )
    profiles = await EmployeeProfileRepository(db, org_id=org_id).by_users(
        {r.user_id for r in requests}
    )
    pending = status == "pending"
    after = await balances_after(db, org_id, requests) if pending else {}
    also = await _also_out(db, org_id, actor, perms, requests, approvers, edges) if pending else {}
    users = {r.user_id for r in requests}
    context = await requester_context(db, org_id, users, today) if pending else RequesterContext()
    items = []
    for (request, route), read in zip(allowed, reads, strict=True):
        profile = profiles.get(request.user_id)
        items.append(
            ApprovalItem(
                request=read,
                route=route,
                designation=profile.designation if profile else None,
                department=profile.department if profile else None,
                balance_after=after.get(request.id),
                also_out=also.get(request.id, []),
                balances=context.balances.get(request.user_id, []),
                balance_year=context.years.get(request.user_id),
                last_leave=context.last_leave.get(request.user_id),
            )
        )
    return items


async def _also_out(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor: uuid.UUID,
    perms: PermissionSet,
    requests: Sequence[LeaveRequest],
    approvers: dict[uuid.UUID, Approvers],
    edges: Sequence[tuple[uuid.UUID, uuid.UUID]],
) -> dict[uuid.UUID, list[AlsoOut]]:
    """Teammates out on any of each request's days, in one query; no types.

    A teammate shares one of the requester's managers. A manager only sees
    their own reports here (not another manager's team they happen to
    share a report with); HR sees the whole team.
    """
    own_reports = None if perms.has(APPROVE) else {who for who, boss in edges if boss == actor}
    teams: dict[uuid.UUID, set[uuid.UUID]] = {}
    for request in requests:
        bosses = approvers[request.user_id].manager_ids
        team = {who for who, boss in edges if boss in bosses} - {request.user_id}
        teams[request.id] = team if own_reports is None else team & own_reports
    everyone = set().union(*teams.values()) if teams else set()
    if not everyone:
        return {}
    clashes = await LeaveRequestRepository(db, org_id=org_id).active_between(
        everyone, min(r.start_date for r in requests), max(r.end_date for r in requests)
    )
    names = await UserRepository(db).get_names_by_ids({c.user_id for c in clashes})
    return {
        request.id: [
            AlsoOut(
                name=names.get(c.user_id, "Someone"),
                kind=c.kind,
                start_date=c.start_date,
                end_date=c.end_date,
            )
            for c in clashes
            if c.user_id in teams[request.id]
            and c.start_date <= request.end_date
            and c.end_date >= request.start_date
        ]
        for request in requests
    }


async def approval_count(
    db: AsyncSession, org_id: uuid.UUID, actor: uuid.UUID, perms: PermissionSet
) -> ApprovalCount:
    """Pending requests the caller can act on, for the nav badge (no extras)."""
    allowed, _, edges = await _decidable(db, org_id, actor, perms, "pending")
    is_approver = perms.has(APPROVE) or any(boss == actor for _, boss in edges)
    return ApprovalCount(pending=len(allowed), is_approver=is_approver)
