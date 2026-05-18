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

"""``WebhookLog`` — durable inbound webhook delivery + replay queue.

One row per ``X-GitHub-Delivery`` (or equivalent vendor-supplied delivery
identifier). Two roles in one row:

1. **Append-only delivery ledger.** ``delivery_id`` is the primary key;
   the entry point uses ``INSERT … ON CONFLICT DO NOTHING`` so duplicate
   deliveries from GitHub's at-least-once retry are short-circuited with
   ``200 {"status": "duplicate"}``.

2. **Durable replay row.** ``status`` / ``attempts`` / ``payload``
   carry enough state for the per-(org, repo) Redis-stream consumer
   (``pr_merge_worker.py``) to rebuild handler input. ``payload``
   carries the minimum replay shape — head_sha, base_sha, pr_number,
   full_name, merged, action — distinct from ``payload_summary`` which
   remains the audit summary. ``next_attempt_at`` is retained for
   schema compatibility with Phase-4 deployments but is no longer
   written (the Redis-stream design has no defer-and-retry path).

Not based on :class:`BaseModel` because:
- The primary key is the vendor-supplied ``delivery_id``, not a UUID.
- ``received_at`` and ``next_attempt_at`` cover the temporal columns we
  need; ``updated_at`` would be redundant.
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WebhookDeliveryStatus(enum.StrEnum):
    """Lifecycle state of a webhook delivery in the durable replay row.

    * ``pending`` — fresh delivery published to the per-(org, repo)
      Redis stream, not yet dequeued. Orphan recovery republishes
      rows stuck here at backend startup.
    * ``running`` — dequeued by the PR-merge worker; handler is in
      flight. Orphan recovery also republishes rows stuck here (the
      previous backend died mid-handler).
    * ``done`` — handler completed successfully.
    * ``failed`` — handler raised. Terminal; no auto-retry. Operator
      flips back to ``pending`` to retry manually (the orphan-recovery
      path on the next backend boot then republishes the row).
    * ``skipped`` — delivery we intentionally don't replay (e.g.
      installation/install_repos events, deliveries for untracked repos).
    """

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


# Single source of truth for the Postgres enum type. Used by both the
# model column and the alembic migration so they stay in sync.
WEBHOOK_DELIVERY_STATUS_VALUES: tuple[str, ...] = tuple(s.value for s in WebhookDeliveryStatus)
WEBHOOK_DELIVERY_STATUS_TYPE_NAME = "webhook_delivery_status"


class WebhookLog(Base):
    """Inbound webhook delivery + durable replay-queue row."""

    __tablename__ = "webhook_logs"
    __table_args__ = (
        Index("ix_webhook_logs_org_received", "org_id", text("received_at DESC")),
        # Partial index drives the picker's ``claim_for_replay`` query.
        # Restricted to rows the picker actually scans so the index stays
        # small even as ``done``/``failed`` rows accumulate.
        Index(
            "ix_webhook_logs_replay",
            "status",
            "next_attempt_at",
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    delivery_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    payload_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Replay-queue columns ------------------------------------------------
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_repositories.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        Enum(
            WebhookDeliveryStatus,
            name=WEBHOOK_DELIVERY_STATUS_TYPE_NAME,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=text("'pending'"),
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Minimum replay shape for the PR-merge dispatcher — the handler can
    # rebuild its full input from this dict alone, no other tables read.
    # See ``app/services/pr_merge_worker.py`` for the consumer contract.
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<WebhookLog(delivery_id={self.delivery_id!r}, "
            f"event_type={self.event_type!r}, status={self.status!r})>"
        )
