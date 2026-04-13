"""Developer XP and gamification models.

DeveloperXP tracks aggregate XP, level, and streak per user per org.
XPEvent records each individual XP award for audit and transparency.
"""

import uuid
from datetime import date

from sqlalchemy import (
    Date,
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


class DeveloperXP(BaseModel):
    """Aggregate XP, level, and streak for a developer within an org."""

    __tablename__ = "developer_xp"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", name="uq_xp_user_org"),
        Index("ix_xp_org_leaderboard", "org_id", "total_xp"),
        Index("ix_xp_org_level", "org_id", "level"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    total_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    level_name: Mapped[str] = mapped_column(String(30), nullable=False, default="seedling")
    streak_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_active_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    streak_best: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Skill points — scarce currency earned through role-based quality outcomes
    skill_points: Mapped[float] = mapped_column(
        Numeric(10, 2, asdecimal=False), nullable=False, default=0, server_default="0",
    )
    house_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default="2",
    )
    vehicle_unlocks: Mapped[list[str]] = mapped_column(
        ARRAY(String(30)), nullable=False, server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<DeveloperXP(user={self.user_id}, xp={self.total_xp}, lv={self.level})>"


class XPEvent(BaseModel):
    """Individual XP award record for audit trail and transparency."""

    __tablename__ = "xp_events"
    __table_args__ = (
        Index("ix_xp_events_user_org_time", "user_id", "org_id", "created_at"),
        Index("ix_xp_events_org_time", "org_id", "created_at"),
        # Partial unique index: prevents duplicate awards for the same source_ref
        Index(
            "uq_xp_events_source_ref",
            "source_ref", "org_id",
            unique=True,
            postgresql_where="source_ref IS NOT NULL",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
    )
    xp_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    multiplier: Mapped[float] = mapped_column(
        Numeric(precision=3, scale=2), nullable=False, default=1.0,
    )
    metadata_: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<XPEvent(user={self.user_id}, +{self.xp_amount} {self.source})>"
