"""clear inflated minigame leaderboard scores

Revision ID: b656380431cb
Revises: e2248a46d87d
Create Date: 2026-06-16 21:35:18.194391

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b656380431cb"
down_revision: str | None = "e2248a46d87d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The new level-based formats + server-side anti-bot guards change what a
    # legitimate score looks like; the old high scores were either from the
    # short/exploitable formats or from bots that swept the games. Drop the
    # aggregate rows above each game's plausible-legit ceiling so the boards and
    # streaks start clean under the new scoring. Data-only — no schema change.
    op.execute("DELETE FROM minigame_scores WHERE game = 'fishing' AND best_score > 35")
    op.execute("DELETE FROM minigame_scores WHERE game = 'pollen_pop' AND best_score > 40")
    op.execute("DELETE FROM minigame_scores WHERE game = 'firefly' AND best_score > 13")


def downgrade() -> None:
    # Irreversible: deleted leaderboard rows cannot be restored.
    pass
