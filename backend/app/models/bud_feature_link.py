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

"""Junction between :class:`BUDDocument` and :class:`Feature`.

A BUD's requirement can touch multiple existing features in the org. This
table records those links so downstream agents (Designer, TechPlanner,
Code Reviewer, Tester) can pull the linked features'
``FeatureToRepo.code_locations`` and ground their prompts in the real
files instead of hallucinating.

The link is orthogonal to :func:`app.services.feature_lifecycle.create_planned_feature`,
which creates the *new* feature the BUD is building. This table is for
*existing* (scan-authored) features the BUD modifies.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.bud import BUDDocument
    from app.models.feature import Feature


class BUDFeatureLinkType(StrEnum):
    """How the BUD relates to the linked feature."""

    TOUCHES = "touches"
    DEPENDS_ON = "depends_on"


class BUDFeatureLinkSource(StrEnum):
    """Which subsystem created the link."""

    PM_AGENT = "pm_agent"
    MANUAL = "manual"
    TECH_ARCH = "tech_arch"


class BUDFeatureLink(Base):
    """One link between a BUD and an existing Feature."""

    __tablename__ = "bud_feature_link"
    __table_args__ = (
        UniqueConstraint("bud_id", "feature_id", name="uq_bfl_bud_feature"),
        Index("ix_bfl_bud_id", "bud_id"),
        Index("ix_bfl_feature_id", "feature_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("features.id", ondelete="CASCADE"),
        nullable=False,
    )
    link_type: Mapped[BUDFeatureLinkType] = mapped_column(
        Enum(
            BUDFeatureLinkType,
            name="bud_feature_link_type",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=BUDFeatureLinkType.TOUCHES,
    )
    source: Mapped[BUDFeatureLinkSource] = mapped_column(
        Enum(
            BUDFeatureLinkSource,
            name="bud_feature_link_source",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=BUDFeatureLinkSource.PM_AGENT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    bud: Mapped["BUDDocument"] = relationship(back_populates="feature_links")
    feature: Mapped["Feature"] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<BUDFeatureLink(bud={self.bud_id}, "
            f"feature={self.feature_id}, type={self.link_type})>"
        )
