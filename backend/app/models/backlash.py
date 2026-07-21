# Copyright 2025-2026 Arun Rajkumar
# Licensed under the Apache License, Version 2.0

"""Persistent Backlash match history and per-player aggregate statistics."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class BacklashMatch(BaseModel):
    """One immutable, server-authoritative completed Backlash match."""

    __tablename__ = "backlash_matches"
    __table_args__ = (
        UniqueConstraint("match_id", name="uq_backlash_matches_match_id"),
        CheckConstraint(
            "white_user_id <> black_user_id",
            name="ck_backlash_match_distinct_players",
        ),
        CheckConstraint(
            "winner_user_id IS NULL OR winner_user_id IN (white_user_id, black_user_id)",
            name="ck_backlash_match_winner_participant",
        ),
        CheckConstraint("move_count >= 0 AND duration_ms >= 0", name="ck_backlash_match_metrics"),
        CheckConstraint(
            "(outcome = 'win' AND reason IN ('all_pieces', 'no_legal_moves') "
            "AND winner_user_id IS NOT NULL) OR "
            "(outcome = 'draw' AND reason IN ('repetition', 'no_progress') "
            "AND winner_user_id IS NULL) OR "
            "(outcome = 'forfeit' AND reason IN ('timeout', 'disconnect') "
            "AND winner_user_id IS NOT NULL)",
            name="ck_backlash_match_outcome_reason",
        ),
    )

    match_id: Mapped[str] = mapped_column(String(128), nullable=False)
    room_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    white_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    black_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    winner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    move_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)


class BacklashPlayerStats(BaseModel):
    """Org-scoped aggregate used by status and the wins leaderboard."""

    __tablename__ = "backlash_player_stats"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_backlash_stats_org_user"),
        Index("ix_backlash_stats_org_wins", "org_id", "wins"),
        CheckConstraint(
            "wins >= 0 AND losses >= 0 AND draws >= 0 AND matches = wins + losses + draws",
            name="ck_backlash_stats_totals",
        ),
        CheckConstraint(
            "current_streak >= 0 AND best_streak >= current_streak",
            name="ck_backlash_stats_streaks",
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    losses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    draws: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_played_date: Mapped[date | None] = mapped_column(Date, nullable=True)
