"""reset minigame leaderboards for server-authoritative scoring

Revision ID: e2248a46d87d
Revises: c323d36aa5f3
Create Date: 2026-06-15 18:23:36.766479

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2248a46d87d"
down_revision: str | None = "c323d36aa5f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Server-authoritative scoring (this release) makes the old, client-submitted
    # scores untrustworthy — some were tampered or test data. Wipe the three
    # games' aggregate rows so the leaderboards and streaks start clean under the
    # new, server-computed scores. Data-only migration — no schema change.
    #
    # Only minigame_scores is cleared: minigame_sessions is created by this same
    # release (one migration earlier), so it's empty on deploy — nothing to wipe.
    op.execute("DELETE FROM minigame_scores WHERE game IN ('fishing', 'pollen_pop', 'firefly')")


def downgrade() -> None:
    # Irreversible: deleted leaderboard rows cannot be restored.
    pass
