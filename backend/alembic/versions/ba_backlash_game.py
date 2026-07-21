# Copyright 2025-2026 Arun Rajkumar
# Licensed under the Apache License, Version 2.0

"""Add Backlash match/stat tables and minigame invite notification type.

Revision ID: ba_backlash_game
Revises: 18519f3dd565
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ba_backlash_game"
down_revision: str | None = "18519f3dd565"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'minigame_invite'")
    op.create_table(
        "backlash_matches",
        sa.Column("match_id", sa.String(128), nullable=False),
        sa.Column("room_id", sa.String(64), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("white_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("black_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("winner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("move_count", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["white_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["black_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["winner_user_id"], ["users.id"]),
        sa.CheckConstraint(
            "white_user_id <> black_user_id", name="ck_backlash_match_distinct_players"
        ),
        sa.CheckConstraint(
            "winner_user_id IS NULL OR winner_user_id IN (white_user_id, black_user_id)",
            name="ck_backlash_match_winner_participant",
        ),
        sa.CheckConstraint(
            "move_count >= 0 AND duration_ms >= 0", name="ck_backlash_match_metrics"
        ),
        sa.CheckConstraint(
            "(outcome = 'win' AND reason IN ('all_pieces', 'no_legal_moves') "
            "AND winner_user_id IS NOT NULL) OR "
            "(outcome = 'draw' AND reason IN ('repetition', 'no_progress') "
            "AND winner_user_id IS NULL) OR "
            "(outcome = 'forfeit' AND reason IN ('timeout', 'disconnect') "
            "AND winner_user_id IS NOT NULL)",
            name="ck_backlash_match_outcome_reason",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_id", name="uq_backlash_matches_match_id"),
    )
    op.create_index("ix_backlash_matches_room_id", "backlash_matches", ["room_id"])
    op.create_index("ix_backlash_matches_org_id", "backlash_matches", ["org_id"])
    op.create_index("ix_backlash_matches_white_user_id", "backlash_matches", ["white_user_id"])
    op.create_index("ix_backlash_matches_black_user_id", "backlash_matches", ["black_user_id"])

    op.create_table(
        "backlash_player_stats",
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("wins", sa.Integer(), server_default="0", nullable=False),
        sa.Column("losses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("draws", sa.Integer(), server_default="0", nullable=False),
        sa.Column("matches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("current_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("best_streak", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_played_date", sa.Date(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.CheckConstraint(
            "wins >= 0 AND losses >= 0 AND draws >= 0 AND matches = wins + losses + draws",
            name="ck_backlash_stats_totals",
        ),
        sa.CheckConstraint(
            "current_streak >= 0 AND best_streak >= current_streak",
            name="ck_backlash_stats_streaks",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "user_id", name="uq_backlash_stats_org_user"),
    )
    op.create_index("ix_backlash_stats_org_id", "backlash_player_stats", ["org_id"])
    op.create_index("ix_backlash_stats_user_id", "backlash_player_stats", ["user_id"])
    op.create_index("ix_backlash_stats_org_wins", "backlash_player_stats", ["org_id", "wins"])


def downgrade() -> None:
    op.drop_table("backlash_player_stats")
    op.drop_table("backlash_matches")
    # PostgreSQL enum values are intentionally retained; removing a value
    # requires rebuilding the shared enum and can invalidate old migrations.
