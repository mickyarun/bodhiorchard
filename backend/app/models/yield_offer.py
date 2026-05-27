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

"""Yield-offer model.

A yield offer is raised when smart assignment can't find a free slot
for a higher-priority BUD but a candidate is currently holding a
lower-priority one they could yield. The offer is delivered as a
notification + board notice; the assignee can Accept (their old BUD
goes back to the queue, they take the new one) or Reject (assignment
tries the next candidate).
"""

import uuid
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class YieldOfferStatus(StrEnum):
    """Lifecycle stage of a yield offer."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class YieldOffer(BaseModel):
    """A pending request asking a developer to yield a lower-priority BUD."""

    __tablename__ = "yield_offers"
    __table_args__ = (
        Index("ix_yield_offer_target_pending", "target_user_id", "status"),
        Index("ix_yield_offer_incoming_bud", "incoming_bud_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    # The newly-arrived higher-priority BUD that needs an assignee.
    incoming_bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The candidate's currently-held lower-priority BUD that would be
    # released back to the queue on acceptance.
    yieldable_bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The developer being asked to yield.
    target_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[YieldOfferStatus] = mapped_column(
        Enum(
            YieldOfferStatus,
            name="yield_offer_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=YieldOfferStatus.PENDING,
        server_default=YieldOfferStatus.PENDING.value,
    )

    incoming_bud = relationship("BUDDocument", foreign_keys=[incoming_bud_id], lazy="joined")
    yieldable_bud = relationship("BUDDocument", foreign_keys=[yieldable_bud_id], lazy="joined")
    target_user = relationship("User", foreign_keys=[target_user_id], lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<YieldOffer(id={self.id}, target={self.target_user_id}, "
            f"incoming={self.incoming_bud_id}, status={self.status})>"
        )
