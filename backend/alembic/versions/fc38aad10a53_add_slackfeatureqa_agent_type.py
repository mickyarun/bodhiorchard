"""add slackFeatureQa agent_type

Revision ID: fc38aad10a53
Revises: 5aa33f92b7bd
Create Date: 2026-05-25 22:38:33.380044

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fc38aad10a53"
down_revision: str | None = "5aa33f92b7bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL ADD VALUE is non-transactional, so it runs in its own
    # execute() call outside a transaction block. Alembic autogenerate
    # does not detect enum value additions — see existing migrations
    # (a1_add_tech_arch_and_manager.py et al.) for the same pattern.
    op.execute("ALTER TYPE agent_type ADD VALUE IF NOT EXISTS 'slackFeatureQa'")


def downgrade() -> None:
    # PostgreSQL has no DROP VALUE; reverting an enum value requires
    # recreating the type. Left as a no-op — consistent with the other
    # ADD VALUE migrations in this codebase.
    pass
