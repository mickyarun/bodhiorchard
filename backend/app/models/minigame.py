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

"""Per-user-per-game garden mini-game state.

Mini-games are pure engagement loops — deliberately DECOUPLED from the XP
economy, which is reserved for real development work. Each row aggregates
one player's relationship with one game: their personal best (the
leaderboard key), how many times they've played, and a self-contained
"play this game on consecutive days" streak. Nothing here touches
``DeveloperXP`` or ``reward_events``.

Idempotent display state ("played today") comes from ``last_played_date``;
the leaderboard reads ``best_score`` via the ``(org_id, game, best_score)``
index.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class MinigameScore(BaseModel):
    """One player's aggregate state for one mini-game."""

    __tablename__ = "minigame_scores"
    __table_args__ = (
        # One row per player per game.
        UniqueConstraint("user_id", "game", name="uq_minigame_scores_user_game"),
        # Leaderboard: top-N best_score for a game within an org.
        Index(
            "ix_minigame_scores_org_game_best",
            "org_id",
            "game",
            "best_score",
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    game: Mapped[str] = mapped_column(nullable=False)
    best_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    plays: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_played_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<MinigameScore(user={self.user_id}, game={self.game}, "
            f"best={self.best_score}, streak={self.current_streak})>"
        )
