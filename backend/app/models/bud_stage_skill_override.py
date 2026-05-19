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

"""Per-BUD per-stage skill override.

Records the user's "Advanced settings" choice on BUD creation: at stage
``bud_status`` for this specific BUD, run skill ``skill_id`` instead of
the org default. Resolved by ``resolve_skill_for_bud_stage()`` at agent
dispatch time.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel
from app.models.bud import BUDStatus

if TYPE_CHECKING:
    from app.models.agent_skill import AgentSkill


class BUDStageSkillOverride(BaseModel):
    """Per-BUD per-stage skill choice (advanced settings)."""

    __tablename__ = "bud_stage_skill_overrides"
    __table_args__ = (UniqueConstraint("bud_id", "bud_status", name="uq_override_bud_status"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bud_status: Mapped[BUDStatus] = mapped_column(
        Enum(BUDStatus, name="bud_status", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_skills.id", ondelete="RESTRICT"),
        nullable=False,
    )

    skill: Mapped["AgentSkill"] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<BUDStageSkillOverride(bud={self.bud_id}, "
            f"status={self.bud_status!r}, skill={self.skill_id})>"
        )
