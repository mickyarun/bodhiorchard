"""Add ``github_app_slug`` column to ``organizations``.

The slug is the lowercase identifier returned by ``GET /app`` (e.g.
``my-org-bodhi``). It is used to build the install URL
``https://github.com/apps/{slug}/installations/new`` for the bulk-import
flow so the Settings page and onboarding wizard can render the link
without an extra round-trip.

The column is nullable: existing orgs are back-filled lazily on the
first successful App-token use (``services/github_app_auth.py`` calls
``GET /app`` once, gated by ``slug is None``). No data migration is
required at upgrade time.

The slug is **not** a secret — it appears in public install URLs and
in App pages on github.com. Storing it plain text matches the
treatment of ``github_app_id`` and is the right call.

Revision ID: zak_org_github_app_slug
Revises: zaj_webhook_logs_and_match_log
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zak_org_github_app_slug"
down_revision: str | None = "zaj_webhook_logs_and_match_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable ``github_app_slug`` column."""
    op.add_column(
        "organizations",
        sa.Column("github_app_slug", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    """Drop the ``github_app_slug`` column."""
    op.drop_column("organizations", "github_app_slug")
