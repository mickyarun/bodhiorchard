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

"""Yield-offer data access."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.yield_offer import YieldOffer, YieldOfferStatus
from app.repositories.base import BaseRepository, rowcount


class YieldOfferRepository(BaseRepository[YieldOffer]):
    """Tenant-scoped CRUD for ``yield_offers``."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(YieldOffer, db, org_id=org_id)

    async def list_pending_for_org(self) -> list[YieldOffer]:
        """All pending offers in this org, oldest first.

        Admin lens: ``team:manage`` users (org owner / manager) see
        every yield offer in the org so they can reassign or oversee.
        """
        stmt = self._scoped(
            select(YieldOffer)
            .where(YieldOffer.status == YieldOfferStatus.PENDING)
            .order_by(YieldOffer.created_at)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_for_user(self, user_id: uuid.UUID) -> list[YieldOffer]:
        """Pending offers targeting ``user_id`` in this org, oldest first.

        Used by the BUD board notice and the home-view inbox tile. The
        TTL-on-read step (``expire_overdue``) is the caller's
        responsibility — keep this method side-effect free.
        """
        stmt = self._scoped(
            select(YieldOffer)
            .where(YieldOffer.target_user_id == user_id)
            .where(YieldOffer.status == YieldOfferStatus.PENDING)
            .order_by(YieldOffer.created_at)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_pending_for_user(self, user_id: uuid.UUID) -> int:
        """Pending-offer count for the nav notification badge."""
        offers = await self.list_pending_for_user(user_id)
        return len(offers)

    async def expire_overdue(self, *, older_than: datetime) -> int:
        """Flip every still-pending offer created before ``older_than`` to expired.

        TTL-on-read pattern (per the plan) — invoked from the service
        layer just before any read so callers never see stale offers.
        Cheap probe-first: skip the UPDATE entirely when no row is
        overdue, so concurrent bell-opens (the common case) don't take
        row locks just to confirm there's nothing to do. Returns the
        number of rows updated.
        """
        probe = self._scoped(
            select(YieldOffer.id)
            .where(YieldOffer.status == YieldOfferStatus.PENDING)
            .where(YieldOffer.created_at < older_than)
            .limit(1)
        )
        if (await self._db.execute(probe)).scalar_one_or_none() is None:
            return 0
        stmt = (
            update(YieldOffer)
            .where(YieldOffer.status == YieldOfferStatus.PENDING)
            .where(YieldOffer.created_at < older_than)
            .values(status=YieldOfferStatus.EXPIRED)
        )
        if self._org_id is not None:
            stmt = stmt.where(YieldOffer.org_id == self._org_id)
        result = await self._db.execute(stmt)
        await self._db.flush()
        return rowcount(result) or 0

    async def has_pending_for_incoming_bud(self, incoming_bud_id: uuid.UUID) -> bool:
        """True iff a pending offer for this incoming BUD already exists.

        Guard for the service path that fires offers: prevents creating
        duplicate offers for the same BUD across concurrent assignment
        attempts (e.g. retries after a transient failure).
        """
        stmt = self._scoped(
            select(YieldOffer.id)
            .where(YieldOffer.incoming_bud_id == incoming_bud_id)
            .where(YieldOffer.status == YieldOfferStatus.PENDING)
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None
