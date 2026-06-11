"""purge pre-circuit race results

Revision ID: ade529ed6144
Revises: c8c8c14dc765
Create Date: 2026-06-11 14:04:12.521066

Data-only migration (no schema change, so nothing to autogenerate).

The race track became circuit-only: the straight track was removed from
the UI and every new race is a circuit run. But `race_results` never
recorded the track shape — straight and circuit finishes both store
`distance_m` 100 (1 lap) or 200 (2 laps), so the leaderboard's circuit
boards were showing stale straight-track times commingled with circuit
ones, with no column to tell them apart.

Existing rows can't be reclassified after the fact, so this clears the
results log once. Because all future races are circuit, the boards stay
pure circuit from here on without needing a track-shape column.
Idempotent: a no-op when the table is already empty.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ade529ed6144"
down_revision: str | None = "c8c8c14dc765"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # DELETE (not TRUNCATE) so the op respects the active transaction and
    # is a clean no-op on an empty table.
    op.execute("DELETE FROM race_results")


def downgrade() -> None:
    # Irreversible — the purged finish times are gone and cannot be
    # reconstructed. Leaving downgrade a no-op keeps the chain reversible
    # for surrounding migrations without fabricating data.
    pass
