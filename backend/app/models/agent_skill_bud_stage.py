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

"""Agent skill to BUD stage mapping model.

Maps which agent skill runs at which BUD lifecycle stage, with
execution ordering for future multi-agent pipelines.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.agent_skill import AgentSkill


class AgentSkillBudStage(BaseModel):
    """Maps an agent skill to a BUD lifecycle stage.

    Each row defines: "when a BUD enters *bud_status*, run the agent
    skill identified by *skill_id* at position *execution_order*."

    The unique constraint on ``(org_id, bud_status, execution_order)``
    ensures an ordered pipeline per stage per org. Today each stage
    has a single agent (order=1); future stages may chain multiple
    agents sequentially.
    """

    __tablename__ = "agent_skill_bud_stages"
    __table_args__ = (
        UniqueConstraint(
            "org_id",
            "bud_status",
            "execution_order",
            name="uq_skill_bud_stage_org_status_order",
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_skills.id", ondelete="CASCADE"),
        nullable=False,
    )
    bud_status: Mapped[str] = mapped_column(String(30), nullable=False)
    execution_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    output_section: Mapped[str | None] = mapped_column(String(50), nullable=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Relationships
    skill: Mapped["AgentSkill"] = relationship(back_populates="bud_stages", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<AgentSkillBudStage(id={self.id}, "
            f"status={self.bud_status!r}, order={self.execution_order}, "
            f"enabled={self.enabled})>"
        )
