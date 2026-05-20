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

"""Data access for the BUD ↔ Feature junction table.

Owns every SQL query that touches :class:`BUDFeatureLink`. All writes
defensively validate that the BUD and feature ids belong to the
repository's org scope — the PM agent can hallucinate uuids, so the
linker silently drops anything that doesn't pass cross-org checks (the
caller logs the drops).
"""

from __future__ import annotations

import uuid

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bud import BUDDocument
from app.models.bud_feature_link import (
    BUDFeatureLink,
    BUDFeatureLinkSource,
    BUDFeatureLinkType,
)
from app.models.feature import Feature


class BUDFeatureLinkRepository:
    """Read/write access to :class:`BUDFeatureLink`, scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialise with an async session and the requesting org."""
        self._db = db
        self._org_id = org_id

    async def link_features(
        self,
        bud_id: uuid.UUID,
        feature_ids: list[uuid.UUID],
        *,
        link_type: BUDFeatureLinkType = BUDFeatureLinkType.TOUCHES,
        source: BUDFeatureLinkSource = BUDFeatureLinkSource.PM_AGENT,
    ) -> list[uuid.UUID]:
        """Idempotently link a BUD to one or more existing features.

        Returns the feature ids that were ACTUALLY inserted (via
        ``RETURNING feature_id`` on the ``ON CONFLICT DO NOTHING``
        upsert). Already-linked features are silently skipped and not
        returned — call :meth:`list_links_for_bud` to read the full
        resolved set including pre-existing links.
        """
        if not feature_ids:
            return []
        valid_ids = await self._features_in_org(feature_ids)
        if not valid_ids or not await self._bud_in_org(bud_id):
            return []
        stmt = (
            pg_insert(BUDFeatureLink)
            .values(
                [
                    {
                        "bud_id": bud_id,
                        "feature_id": fid,
                        "link_type": link_type,
                        "source": source,
                    }
                    for fid in valid_ids
                ]
            )
            .on_conflict_do_nothing(constraint="uq_bfl_bud_feature")
            .returning(BUDFeatureLink.feature_id)
        )
        result = await self._db.execute(stmt)
        inserted = list(result.scalars().all())
        await self._db.flush()
        return inserted

    async def unlink_features(self, bud_id: uuid.UUID, feature_ids: list[uuid.UUID]) -> int:
        """Remove links for the given ``feature_ids`` and return the row count."""
        if not feature_ids or not await self._bud_in_org(bud_id):
            return 0
        stmt = delete(BUDFeatureLink).where(
            BUDFeatureLink.bud_id == bud_id,
            BUDFeatureLink.feature_id.in_(feature_ids),
        )
        # ``AsyncSession.execute`` is typed as returning ``Result[Any]``,
        # but for a DML statement the runtime object is a ``CursorResult``
        # which carries ``rowcount``. ``isinstance`` narrows for mypy
        # without leaning on a cast that strict mode flags as redundant.
        result = await self._db.execute(stmt)
        await self._db.flush()
        if isinstance(result, CursorResult):
            return result.rowcount or 0
        return 0

    async def list_features_for_bud(self, bud_id: uuid.UUID) -> list[Feature]:
        """Return every active feature linked to ``bud_id``.

        Eager-loads ``Feature.repo_links`` (selectin) so downstream
        prompt builders can render ``code_locations`` without firing N+1
        queries.
        """
        if not await self._bud_in_org(bud_id):
            return []
        stmt = (
            select(Feature)
            .join(BUDFeatureLink, BUDFeatureLink.feature_id == Feature.id)
            .where(
                BUDFeatureLink.bud_id == bud_id,
                Feature.is_active.is_(True),
                Feature.org_id == self._org_id,
            )
            .options(selectinload(Feature.repo_links))
            .order_by(Feature.feature_title)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_links_for_bud(self, bud_id: uuid.UUID) -> list[BUDFeatureLink]:
        """Return raw link rows (with `link_type` / `source` metadata)."""
        if not await self._bud_in_org(bud_id):
            return []
        stmt = (
            select(BUDFeatureLink)
            .where(BUDFeatureLink.bud_id == bud_id)
            .order_by(BUDFeatureLink.created_at)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def titles_by_ids(self, feature_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Return ``{feature_id: feature_title}`` for the given ids in this org.

        Used by callers that need to render which features were linked /
        unlinked in audit trails (timeline events, notifications). Out-of-org
        ids silently drop out of the result — same defensive behaviour as
        :meth:`_features_in_org`.
        """
        if not feature_ids:
            return {}
        stmt = select(Feature.id, Feature.feature_title).where(
            Feature.id.in_(feature_ids),
            Feature.org_id == self._org_id,
        )
        result = await self._db.execute(stmt)
        return {row.id: row.feature_title for row in result}

    async def _bud_in_org(self, bud_id: uuid.UUID) -> bool:
        """True iff the BUD exists and belongs to this repo's org."""
        stmt = select(BUDDocument.id).where(
            BUDDocument.id == bud_id, BUDDocument.org_id == self._org_id
        )
        return (await self._db.execute(stmt)).scalar_one_or_none() is not None

    async def _features_in_org(self, feature_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        """Filter ``feature_ids`` down to those in this repo's org + active."""
        stmt = select(Feature.id).where(
            Feature.id.in_(feature_ids),
            Feature.org_id == self._org_id,
            Feature.is_active.is_(True),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
