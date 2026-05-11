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

"""Developer XP and gamification models.

DeveloperXP tracks aggregate XP, level, and streak per user per org.
RewardEvent records each individual XP or SP award for audit and transparency.
"""

import enum
import uuid
from datetime import date

from sqlalchemy import (
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class RewardType(enum.StrEnum):
    """Type of points awarded — XP (free-flowing) or SP (scarce currency)."""

    XP = "xp"
    SP = "sp"


class DeveloperXP(BaseModel):
    """Aggregate XP, level, and streak for a developer within an org."""

    __tablename__ = "developer_xp"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_xp_user_org"),
        Index("ix_xp_org_leaderboard", "org_id", "total_xp"),
        Index("ix_xp_org_level", "org_id", "level"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    total_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    level_name: Mapped[str] = mapped_column(String(30), nullable=False, default="seedling")
    streak_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    streak_best: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Skill points — scarce currency earned through role-based quality outcomes
    skill_points: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False),
        nullable=False,
        default=0,
        server_default="0",
    )
    house_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    vehicle_unlocks: Mapped[list[str]] = mapped_column(
        ARRAY(String(30)),
        nullable=False,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<DeveloperXP(user={self.user_id}, xp={self.total_xp}, lv={self.level})>"


class RewardEvent(BaseModel):
    """Individual XP or SP award record for audit trail and transparency."""

    __tablename__ = "reward_events"
    __table_args__ = (
        Index("ix_reward_events_user_org_time", "user_id", "org_id", "created_at"),
        Index("ix_reward_events_org_time", "org_id", "created_at"),
        Index("ix_reward_events_type_time", "org_id", "type", "created_at"),
        # Partial unique index: prevents duplicate awards for the same source_ref
        Index(
            "uq_reward_events_source_ref",
            "source_ref",
            "org_id",
            unique=True,
            postgresql_where="source_ref IS NOT NULL",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[RewardType] = mapped_column(
        Enum(RewardType, name="reward_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    amount: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    multiplier: Mapped[float] = mapped_column(
        Numeric(precision=3, scale=2),
        nullable=False,
        default=1.0,
    )
    metadata_: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<RewardEvent(user={self.user_id}, {self.type.value}+{self.amount} {self.source})>"
