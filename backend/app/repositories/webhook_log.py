# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""``WebhookLog`` data access — primary-key dedupe for inbound deliveries.

The webhook entry point calls :meth:`record_delivery` before dispatching
each event. Returns ``True`` when the delivery is new and the caller
should proceed; returns ``False`` on a duplicate ``delivery_id`` so the
caller can short-circuit with ``200 {"status": "duplicate"}``.

Uses Postgres ``INSERT ... ON CONFLICT DO NOTHING`` so the dedupe check
is atomic with the write — no try/except on ``IntegrityError``, which
would poison the session and force a rollback on every duplicate.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_log import WebhookLog


class WebhookLogRepository:
    """Append-only delivery ledger keyed on vendor-supplied ``delivery_id``."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID | None = None) -> None:
        """Initialise the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Optional tenant scope. ``record_delivery`` requires
                an ``org_id`` parameter regardless; this is used by
                ``list_recent`` for org-scoped reads.
        """
        self._db = db
        self._org_id = org_id

    async def record_delivery(
        self,
        *,
        delivery_id: str,
        event_type: str,
        org_id: uuid.UUID,
        payload_summary: dict[str, Any] | None = None,
    ) -> bool:
        """Record an inbound delivery atomically.

        Returns:
            ``True`` if this is a fresh delivery (caller should
            dispatch); ``False`` if ``delivery_id`` was already recorded
            (caller should return ``200 {"status": "duplicate"}``).
        """
        stmt = (
            pg_insert(WebhookLog)
            .values(
                delivery_id=delivery_id,
                event_type=event_type,
                org_id=org_id,
                payload_summary=payload_summary,
            )
            .on_conflict_do_nothing(index_elements=["delivery_id"])
            .returning(WebhookLog.delivery_id)
        )
        result = await self._db.execute(stmt)
        inserted = result.scalar_one_or_none()
        return inserted is not None

    async def list_recent(
        self,
        *,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[WebhookLog]:
        """Recent deliveries for the configured org, newest first."""
        if self._org_id is None:
            return []
        stmt = (
            select(WebhookLog)
            .where(WebhookLog.org_id == self._org_id)
            .order_by(desc(WebhookLog.received_at))
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.where(WebhookLog.received_at >= since)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
