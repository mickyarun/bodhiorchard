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

"""Data access for leave, WFH and optional-holiday requests."""

import uuid
from collections.abc import Collection
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_request import LeaveKind, LeaveRequest, LeaveStatus
from app.models.user import OrgToUser
from app.repositories.base import BaseRepository

ACTIVE = (LeaveStatus.PENDING, LeaveStatus.APPROVED)
Scope = Literal["upcoming", "past", "all"]


class LeaveRequestRepository(BaseRepository[LeaveRequest]):
    """Requests, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Tenant whose requests this repository exposes.
        """
        super().__init__(LeaveRequest, db, org_id=org_id)
        self._org = org_id

    async def lock_member(self, user_id: uuid.UUID) -> None:
        """Serialize submit/approve/cancel for one member (row lock).

        Locks the member's ``org_to_user`` row until the transaction ends,
        so two requests can't both pass the overlap or balance check.
        """
        await self._db.execute(
            select(OrgToUser.id)
            .where(OrgToUser.org_id == self._org, OrgToUser.user_id == user_id)
            .with_for_update()
        )

    async def list_for_user(
        self, user_id: uuid.UUID, scope: Scope, today: date
    ) -> list[LeaveRequest]:
        """A member's requests, newest first."""
        stmt = self._scoped(select(LeaveRequest).where(LeaveRequest.user_id == user_id))
        if scope == "upcoming":
            stmt = stmt.where(LeaveRequest.end_date >= today, LeaveRequest.status.in_(ACTIVE))
        elif scope == "past":
            stmt = stmt.where(
                or_(LeaveRequest.end_date < today, LeaveRequest.status.notin_(ACTIVE))
            )
        result = await self._db.execute(stmt.order_by(LeaveRequest.start_date.desc()))
        return list(result.scalars().all())

    async def active_between(
        self,
        user_ids: Collection[uuid.UUID] | None,
        start: date,
        end: date,
        *,
        kinds: Collection[LeaveKind] | None = None,
        exclude: uuid.UUID | None = None,
    ) -> list[LeaveRequest]:
        """Pending or approved requests overlapping ``start..end``."""
        stmt = self._scoped(
            select(LeaveRequest).where(
                LeaveRequest.status.in_(ACTIVE),
                LeaveRequest.start_date <= end,
                LeaveRequest.end_date >= start,
            )
        )
        if user_ids is not None:
            stmt = stmt.where(LeaveRequest.user_id.in_(user_ids))
        if kinds is not None:
            stmt = stmt.where(LeaveRequest.kind.in_(kinds))
        if exclude is not None:
            stmt = stmt.where(LeaveRequest.id != exclude)
        result = await self._db.execute(stmt.order_by(LeaveRequest.start_date))
        return list(result.scalars().all())

    async def leave_day_totals(
        self, user_id: uuid.UUID, start: date, end: date
    ) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
        """``{leave_type_id: (approved_days, pending_days)}`` for a leave year."""
        stmt = self._scoped(
            select(LeaveRequest.leave_type_id, LeaveRequest.status, func.sum(LeaveRequest.days))
            .where(
                LeaveRequest.user_id == user_id,
                LeaveRequest.kind == LeaveKind.LEAVE,
                LeaveRequest.status.in_(ACTIVE),
                LeaveRequest.start_date >= start,
                LeaveRequest.start_date <= end,
            )
            .group_by(LeaveRequest.leave_type_id, LeaveRequest.status)
        )
        totals: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
        for type_id, status, days in (await self._db.execute(stmt)).all():
            approved, pending = totals.get(type_id, (Decimal("0"), Decimal("0")))
            if status == LeaveStatus.APPROVED:
                approved += days
            else:
                pending += days
            totals[type_id] = (approved, pending)
        return totals

    async def list_pending(self, user_ids: Collection[uuid.UUID] | None) -> list[LeaveRequest]:
        """Pending requests, oldest first; ``None`` = every member."""
        stmt = self._scoped(select(LeaveRequest).where(LeaveRequest.status == LeaveStatus.PENDING))
        if user_ids is not None:
            stmt = stmt.where(LeaveRequest.user_id.in_(user_ids))
        result = await self._db.execute(stmt.order_by(LeaveRequest.created_at))
        return list(result.scalars().all())

    async def list_decided(
        self, user_ids: Collection[uuid.UUID] | None, since: datetime
    ) -> list[LeaveRequest]:
        """Requests decided by a person since ``since``, newest first."""
        stmt = self._scoped(
            select(LeaveRequest).where(
                LeaveRequest.status.in_((LeaveStatus.APPROVED, LeaveStatus.REJECTED)),
                LeaveRequest.decided_by.is_not(None),
                LeaveRequest.decided_at >= since,
            )
        )
        if user_ids is not None:
            stmt = stmt.where(LeaveRequest.user_id.in_(user_ids))
        result = await self._db.execute(stmt.order_by(LeaveRequest.decided_at.desc()).limit(200))
        return list(result.scalars().all())

    async def calendar(self, start: date, end: date, viewer: uuid.UUID) -> list[LeaveRequest]:
        """Approved requests in the range, plus the viewer's own pending ones."""
        visible = or_(
            LeaveRequest.status == LeaveStatus.APPROVED,
            and_(LeaveRequest.status == LeaveStatus.PENDING, LeaveRequest.user_id == viewer),
        )
        stmt = self._scoped(
            select(LeaveRequest).where(
                visible, LeaveRequest.start_date <= end, LeaveRequest.end_date >= start
            )
        )
        result = await self._db.execute(stmt.order_by(LeaveRequest.start_date))
        return list(result.scalars().all())

    async def transition(
        self, request_id: uuid.UUID, from_statuses: Collection[LeaveStatus], **values: Any
    ) -> bool:
        """Update a request only if it's still in one of ``from_statuses``.

        Returns False when someone else changed it first (two managers
        deciding at once), so the caller can answer 409.
        """
        result = await self._db.execute(
            sql_update(LeaveRequest)
            .where(
                LeaveRequest.id == request_id,
                LeaveRequest.org_id == self._org,
                LeaveRequest.status.in_(from_statuses),
            )
            .values(**values)
            .returning(LeaveRequest.id)
        )
        return result.first() is not None

    async def pending_for_policy_from(
        self, policy_id: uuid.UUID, start: date
    ) -> list[LeaveRequest]:
        """Pending and future approved requests on a policy (holiday changes)."""
        stmt = self._scoped(
            select(LeaveRequest).where(
                LeaveRequest.policy_id == policy_id,
                LeaveRequest.status.in_(ACTIVE),
                LeaveRequest.end_date >= start,
            )
        )
        return list((await self._db.execute(stmt)).scalars().all())
