"""Add ``webhook_logs`` and ``feature_match_log`` tables.

``webhook_logs`` is a general-purpose dedupe ledger keyed on
``X-GitHub-Delivery`` header. The webhook entry point inserts one row
per delivery before dispatching; an ``IntegrityError`` on the primary
key short-circuits the dispatch and returns ``200 {"status": "duplicate"}``.
The ``event_type`` column keeps the table reusable for future webhook
sources (issues, releases, etc.) — not just ``pull_request``.

``feature_match_log`` is an append-only audit trail of every reconciler
fork. Each ``FeatureWrite`` produces exactly one row recording which
match strategy fired (signature / jaccard / cosine / insert), the
score, and the resulting decision (inserted / updated / revived). It
exists to surface borderline matches so the 0.7 (Jaccard) and 0.85
(cosine) thresholds can be tuned from real data via the
``GET /v1/features/match-debug`` endpoint.

Both tables are write-once: rows are not updated after insert. Volume
is bounded by webhook delivery count and feature count per scan; long-
term retention is acceptable for now and a ``pg_cron``-style cleanup
can be added later if needed.

Revision ID: zaj_webhook_logs_and_match_log
Revises: zai_drop_partial_title_index
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "zaj_webhook_logs_and_match_log"
down_revision: str | None = "zai_drop_partial_title_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create both tables with their supporting indexes."""
    op.create_table(
        "webhook_logs",
        sa.Column("delivery_id", sa.String(length=64), primary_key=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("payload_summary", postgresql.JSONB, nullable=True),
    )
    op.create_index(
        "ix_webhook_logs_org_received",
        "webhook_logs",
        ["org_id", sa.text("received_at DESC")],
    )

    op.create_table(
        "feature_match_log",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("head_sha", sa.String(length=64), nullable=False),
        sa.Column("match_via", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("feature_title", sa.String(length=500), nullable=False),
        sa.Column(
            "matched_feature_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("features.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_fml_org_repo_created",
        "feature_match_log",
        ["org_id", "repo_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_fml_org_via_score",
        "feature_match_log",
        ["org_id", "match_via", "score"],
    )


def downgrade() -> None:
    """Drop both tables. Append-only data is unrecoverable from elsewhere."""
    op.drop_index("ix_fml_org_via_score", table_name="feature_match_log")
    op.drop_index("ix_fml_org_repo_created", table_name="feature_match_log")
    op.drop_table("feature_match_log")
    op.drop_index("ix_webhook_logs_org_received", table_name="webhook_logs")
    op.drop_table("webhook_logs")
