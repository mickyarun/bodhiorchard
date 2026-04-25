"""Add scans table — one row per scan replaces the Redis hash.

Moves scan progress state from Redis (``scan:{scan_id}`` hash +
``scan_active:{org_id}`` pointer, both TTL 2h) into Postgres. This
removes the TTL-based failure mode where a failed scan would "age
out" of Redis after 2h and surface as a phantom 404 on /resume, or
where a freshly-dispatched scan couldn't be found via /scan/latest
until its first checkpoint was written.

Per-phase detail still lives in ``scan_phase_checkpoints``; this
table holds only the aggregate fields the UI and HTTP layer need.

Revision ID: zp_scans_table
Revises: zo_synthesized_features
Create Date: 2026-04-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "zp_scans_table"
down_revision: str | None = "zo_synthesized_features"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("parent_scan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.String(64),
            nullable=False,
            server_default="started",
        ),
        sa.Column(
            "scan_mode",
            sa.String(16),
            nullable=False,
            server_default="full",
        ),
        sa.Column(
            "progress_pct",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "features_indexed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "features_skipped",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "profiles_found",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "stale_cleaned",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "unmatched_authors",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column("synthesis_warning", sa.Text(), nullable=True),
        sa.Column("setup_pr_message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "repo_warnings",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_scans_org_created", "scans", ["org_id", "created_at"])
    op.create_index("ix_scans_org_updated", "scans", ["org_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_scans_org_updated", table_name="scans")
    op.drop_index("ix_scans_org_created", table_name="scans")
    op.drop_table("scans")
