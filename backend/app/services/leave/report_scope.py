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

"""Whose leave a viewer may see in reports and on a member's history.

Holders of leave:reports see everyone. Anyone else sees their direct reports
only: the same people approvals, the calendar and balances already show them
leave types for. A skip-level manager doesn't see their reports' reports.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.user import User
from app.services.leave.approvers import reports_of
from app.services.leave.errors import LeaveForbiddenError
from app.services.leave.permissions import APPROVE, REPORTS
from app.services.leave.type_privacy import sees_restricted

NO_REPORTS = "You can see leave reports for your direct reports, and you have none."


@dataclass(frozen=True)
class ReportScope:
    """Everyone (``user_ids`` None) or a fixed set of members."""

    user_ids: frozenset[uuid.UUID] | None
    # May see gender-limited leave types (:mod:`app.services.leave.type_privacy`).
    sees_restricted: bool = False

    @property
    def is_all(self) -> bool:
        return self.user_ids is None

    def narrow(self, user_id: uuid.UUID | None) -> "ReportScope":
        """Restrict to one member; never widens (someone outside stays out)."""
        if user_id is None:
            return self
        if self.user_ids is None or user_id in self.user_ids:
            return ReportScope(frozenset({user_id}), self.sees_restricted)
        return ReportScope(frozenset(), self.sees_restricted)

    def allows(self, user_id: uuid.UUID) -> bool:
        return self.user_ids is None or user_id in self.user_ids


async def report_scope(db: AsyncSession, viewer: User, perms: PermissionSet) -> ReportScope:
    """The members ``viewer`` may report on; LeaveForbiddenError if nobody."""
    sees = sees_restricted(perms)
    if perms.has(REPORTS):
        return ReportScope(None, sees)
    reports = await reports_of(db, viewer.org_id, viewer.id)
    if not reports:
        raise LeaveForbiddenError(NO_REPORTS)
    return ReportScope(frozenset(reports), sees)


async def may_view_member_leave(
    db: AsyncSession, viewer: User, perms: PermissionSet, user_id: uuid.UUID
) -> bool:
    """Self, HR (leave:approve), leave:reports, or one of their managers.

    One rule for a member's balances and their leave history, so the two
    halves of the profile's Leave tab never disagree.
    """
    if user_id == viewer.id or perms.has_any((APPROVE, REPORTS)):
        return True
    return user_id in await reports_of(db, viewer.org_id, viewer.id)
