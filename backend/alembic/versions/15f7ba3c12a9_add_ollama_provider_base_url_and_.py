"""add ollama provider, base url and thinking toggle

Revision ID: 15f7ba3c12a9
Revises: 18519f3dd565
Create Date: 2026-07-16 10:48:16.643518

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "15f7ba3c12a9"
down_revision: str | None = "18519f3dd565"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate detects the two columns but NOT the new enum value, so the
    # ALTER TYPE is hand-written. Postgres permits ADD VALUE inside the
    # transaction alembic runs us in, provided the new value is not *used* in
    # that same transaction — the columns below don't reference it.
    op.execute("ALTER TYPE ai_provider ADD VALUE IF NOT EXISTS 'ollama'")
    op.add_column("organizations", sa.Column("ai_base_url", sa.String(length=255), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("ai_thinking", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    # Reset any org still on ollama first. Code at the previous revision has no
    # such enum member, so it raises LookupError decoding the row — and since
    # organizations is loaded on nearly every authenticated request, that locks
    # the org out entirely rather than degrading it. Resetting to claude loses
    # the provider choice, which is the right trade against an unreadable row.
    # Safe here: 'ollama' was committed by the upgrade, so using it now is not
    # the "unsafe use of a new enum value" case.
    op.execute("UPDATE organizations SET ai_provider = 'claude' WHERE ai_provider = 'ollama'")
    op.drop_column("organizations", "ai_thinking")
    op.drop_column("organizations", "ai_base_url")
    # The 'ollama' label stays on the enum: Postgres cannot remove an enum
    # value, and rebuilding the type would mean rewriting every dependent
    # column. An unused label is harmless — unreadable rows were not.
