# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""``WebhookLog`` — append-only delivery ledger for inbound webhooks.

One row per ``X-GitHub-Delivery`` (or equivalent vendor-supplied
delivery identifier). The webhook entry point records a row before
dispatching the event to handlers; a duplicate ``delivery_id`` raises
``IntegrityError`` on insert, signalling the caller to short-circuit
with ``200 {"status": "duplicate"}``.

Not based on :class:`BaseModel` because:
- The primary key is the vendor-supplied ``delivery_id``, not a UUID.
- Rows are write-once; ``updated_at`` would always equal ``received_at``.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WebhookLog(Base):
    """Inbound webhook delivery record. Primary-key dedupe."""

    __tablename__ = "webhook_logs"
    __table_args__ = (Index("ix_webhook_logs_org_received", "org_id", "received_at"),)

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

    def __repr__(self) -> str:
        return f"<WebhookLog(delivery_id={self.delivery_id!r}, event_type={self.event_type!r})>"
