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

"""Who else is out on a pending request's days, for the approvals queue."""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.leave_request import LeaveRequest
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.user import UserRepository
from app.schemas.leave_views import AlsoOut
from app.services.leave.approvers import Approvers
from app.services.leave.permissions import APPROVE


async def also_out(
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
