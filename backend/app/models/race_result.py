# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Per-participant race result row — source of truth for the leaderboard.

Written by the Colyseus race-server via `POST /internal/colyseus/race-results`
when a `RaceRoom` disposes. Idempotent on `(room_id, user_id)` so bridge
retries never double-count, and indexed on `(org_id, distance_m,
finish_time_ms)` so the leaderboard query is one index scan.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class RaceResult(BaseModel):
    """One row per participant per race. DNFs keep a NULL `finish_time_ms`
    and a populated `distance_m_reached` so the leaderboard can rank them
    below finishers by how far they got.
    """

    __tablename__ = "race_results"
    __table_args__ = (
        # Idempotency: room_id + user_id uniquely identifies one result.
        UniqueConstraint("room_id", "user_id", name="uq_race_results_room_user"),
        # Leaderboard query: ORDER BY finish_time_ms ASC LIMIT N.
        Index(
            "ix_race_results_org_distance_time",
            "org_id",
            "distance_m",
            "finish_time_ms",
        ),
        # Per-user PR lookup: "show me alice's best 100 m time".
        Index(
            "ix_race_results_org_user_distance",
            "org_id",
            "user_id",
            "distance_m",
        ),
        # Distance is a closed set — mirrors `ALLOWED_DISTANCES_M` on the
        # shared race constants + the notifications validator.
        CheckConstraint(
            "distance_m IN (100, 200)",
            name="ck_race_results_distance_m",
        ),
    )

    # Colyseus race-room id (short slug). Not FK'd anywhere — the room is
    # ephemeral and lives outside the DB.
    room_id: Mapped[str] = mapped_column(nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    host_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    distance_m: Mapped[int] = mapped_column(Integer, nullable=False)
    # NULL for DNFs — rank those by `distance_m_reached DESC` instead.
    finish_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    place: Mapped[int] = mapped_column(Integer, nullable=False)
    finished: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Progress made before the running-phase timeout fired (for DNF ranking).
    distance_m_reached: Mapped[float] = mapped_column(Float, nullable=False)
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<RaceResult(room={self.room_id}, user={self.user_id}, "
            f"distance={self.distance_m}, time_ms={self.finish_time_ms})>"
        )
