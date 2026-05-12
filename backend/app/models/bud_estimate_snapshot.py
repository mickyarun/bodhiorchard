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

"""BUD estimate snapshot model for estimation audit trail.

Each snapshot captures the full estimation context and results at a point
in time, enabling accuracy tracking (predicted vs actual) and audit history.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class BUDEstimateSnapshot(BaseModel):
    """Point-in-time snapshot of a BUD's estimation results and input context."""

    __tablename__ = "bud_estimate_snapshots"
    __table_args__ = (Index("ix_bud_estimate_snapshot_bud_id", "bud_id"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    trigger: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    phase_estimates: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    complexity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<BUDEstimateSnapshot(id={self.id}, bud_id={self.bud_id}, trigger={self.trigger!r})>"
        )
