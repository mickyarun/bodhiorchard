"""add ai_provider to organizations

Revision ID: 18519f3dd565
Revises: bd4971310859
Create Date: 2026-06-30 14:51:36.744648

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "18519f3dd565"
down_revision: str | None = "bd4971310859"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ai_provider_enum = sa.Enum("claude", "copilot", "codex", name="ai_provider")


def upgrade() -> None:
    # op.add_column does not auto-create the Postgres enum type, so create it
    # explicitly first (checkfirst=True keeps re-runs idempotent), then add the
    # column referencing the existing type (create_type=False avoids a re-create).
    ai_provider_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "organizations",
        sa.Column(
            "ai_provider",
            sa.Enum("claude", "copilot", "codex", name="ai_provider", create_type=False),
            server_default="claude",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "ai_provider")
    ai_provider_enum.drop(op.get_bind(), checkfirst=True)
