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

"""``WebhookLog`` data access — delivery dedupe + replay-row lifecycle.

Two write paths, two read paths, one status-transition method:

* :meth:`record_delivery` — audit-only insert (``status='skipped'``).
  The webhook entry point uses this for events we never replay
  (installation lifecycle, deliveries for untracked repos).
* :meth:`record_replay_row` — durable insert (``status='pending'``).
  The entry point uses this for PR-merge deliveries; the row carries
  enough payload for the worker to rebuild its full input.
* :meth:`find_by_delivery_id` — load one row by primary key (the
  PR-merge worker uses this to recover the replay payload).
* :meth:`list_in_status` — find rows in a given lifecycle state. The
  startup-orphan-recovery path lists ``running`` rows to re-publish to
  the Redis stream.
* :meth:`update_status` — single status transition method. The
  PR-merge worker is the sole writer: it flips ``pending → running``
  on dequeue, then ``running → done`` (or ``failed``) on completion.
  Replaces the Phase-4 trio (``claim_for_replay`` / ``defer`` /
  ``mark_done`` / ``mark_failed`` / ``recover_running_at_startup``) —
  the Redis-stream consumer doesn't need claim-and-defer plumbing
  because per-(org, repo) FIFO is built into the stream.

All SQL stays here (per project convention — services never touch
SQLAlchemy expressions directly).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import desc, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_log import (
    WEBHOOK_DELIVERY_STATUS_TYPE_NAME,
    WebhookDeliveryStatus,
    WebhookLog,
)

logger = structlog.get_logger(__name__)
_LAST_ERROR_MAX_LEN = 500


class WebhookLogRepository:
    """Delivery ledger + replay-row access keyed on ``delivery_id``."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID | None = None) -> None:
        """Initialise.

        ``org_id`` scopes :meth:`list_recent`. Writes pass the org id as
        an explicit kwarg because the webhook entry point resolves it
        per-delivery before constructing the repository.
        """
        self._db = db
        self._org_id = org_id

    # --- Inserts ---------------------------------------------------------

    async def record_delivery(
        self,
        *,
        delivery_id: str,
        event_type: str,
        org_id: uuid.UUID,
        payload_summary: dict[str, Any] | None = None,
    ) -> bool:
        """Audit-only insert. Status is ``skipped`` so workers ignore it.

        Returns ``True`` if fresh, ``False`` if the delivery_id was already
        recorded (caller short-circuits with ``200 {"status":"duplicate"}``).
        """
        return await self._insert_or_skip(
            delivery_id=delivery_id,
            event_type=event_type,
            org_id=org_id,
            payload_summary=payload_summary,
            repo_id=None,
            payload=None,
            status=WebhookDeliveryStatus.SKIPPED,
        )

    async def record_replay_row(
        self,
        *,
        delivery_id: str,
        event_type: str,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        payload: dict[str, Any],
        payload_summary: dict[str, Any] | None = None,
    ) -> bool:
        """Durable insert. Status is ``pending`` until the worker dequeues.

        ``payload`` carries the minimum replay shape — ``head_sha``,
        ``base_sha``, ``pr_number``, ``full_name``, ``merged``, ``action``
        — enough for the PR-merge worker to rebuild its full input from
        this row alone.
        """
        return await self._insert_or_skip(
            delivery_id=delivery_id,
            event_type=event_type,
            org_id=org_id,
            payload_summary=payload_summary,
            repo_id=repo_id,
            payload=payload,
            status=WebhookDeliveryStatus.PENDING,
        )

    async def _insert_or_skip(
        self,
        *,
        delivery_id: str,
        event_type: str,
        org_id: uuid.UUID,
        payload_summary: dict[str, Any] | None,
        repo_id: uuid.UUID | None,
        payload: dict[str, Any] | None,
        status: WebhookDeliveryStatus,
    ) -> bool:
        stmt = (
            pg_insert(WebhookLog)
            .values(
                delivery_id=delivery_id,
                event_type=event_type,
                org_id=org_id,
                payload_summary=payload_summary,
                repo_id=repo_id,
                payload=payload,
                status=status.value,
            )
            .on_conflict_do_nothing(index_elements=["delivery_id"])
            .returning(WebhookLog.delivery_id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    # --- Reads -----------------------------------------------------------

    async def find_by_delivery_id(self, delivery_id: str) -> WebhookLog | None:
        """Load one row by primary key. The PR-merge worker uses this
        to recover replay payload from the durable row instead of the
        Redis-stream message body (Redis is for routing, Postgres is
        for state).
        """
        stmt = select(WebhookLog).where(WebhookLog.delivery_id == delivery_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

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

    async def list_in_status(
        self, status: WebhookDeliveryStatus, *, limit: int = 500
    ) -> list[WebhookLog]:
        """Rows currently in the given lifecycle state, oldest first.

        Used at startup to find ``running`` orphans (a backend that died
        mid-handler leaves rows here) and ``pending`` rows that were
        never published to the stream (e.g. the XADD raced a process
        crash).

        ``limit`` caps the number of rows pulled into memory at boot.
        Default 500 covers a healthy system many times over; if an
        extended outage produced more, the caller should log and pick
        up the remainder on the next boot (each republish makes
        progress, and the orphans are processed in arrival order).
        """
        stmt = (
            select(WebhookLog)
            .where(WebhookLog.status == status)
            .order_by(WebhookLog.received_at)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # --- Status transitions ---------------------------------------------

    async def update_status(
        self,
        *,
        delivery_id: str,
        status: WebhookDeliveryStatus,
        error: str | None = None,
        bump_attempts: bool = False,
    ) -> None:
        """Flip a row's status. Sole writer is the PR-merge worker.

        Passing ``error`` is only meaningful when ``status`` is
        :attr:`WebhookDeliveryStatus.FAILED`; on success paths the error
        column stays untouched. Long error messages are truncated; the
        truncation is logged so operators can grep the structured log
        for the full traceback.

        Setting ``bump_attempts=True`` increments the ``attempts``
        column in the same statement. The PR-merge worker passes this
        on the ``pending → running`` edge so the column tracks
        worker-handler invocations (useful when an orphan-recovery loop
        re-publishes the same delivery and we want to see the count
        climb).

        Explicit ``::webhook_delivery_status`` cast is required because
        asyncpg binds parameters as VARCHAR, killing the implicit
        text→enum coercion Postgres would otherwise apply.
        """
        if error is not None and len(error) > _LAST_ERROR_MAX_LEN:
            logger.warning(
                "webhook_log_error_truncated",
                delivery_id=delivery_id,
                full_length=len(error),
                kept=_LAST_ERROR_MAX_LEN,
            )
            error = error[:_LAST_ERROR_MAX_LEN]

        # The CAST is required because asyncpg binds parameters as
        # VARCHAR — without it Postgres can't coerce text to the enum
        # at runtime. Sourcing the type name from the model keeps the
        # SQL aligned if the enum is ever renamed.
        set_clauses: list[str] = [f"status = CAST(:st AS {WEBHOOK_DELIVERY_STATUS_TYPE_NAME})"]
        params: dict[str, Any] = {"st": status.value, "did": delivery_id}
        if error is not None:
            set_clauses.append("last_error = :err")
            params["err"] = error
        if bump_attempts:
            set_clauses.append("attempts = attempts + 1")
        sql = f"UPDATE webhook_logs SET {', '.join(set_clauses)} WHERE delivery_id = :did"
        await self._db.execute(text(sql).bindparams(**params))
