# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Add scan_phase_checkpoints table for resumable scan pipeline.

Creates the ``scan_phase_checkpoints`` table that records per-phase
lifecycle state for each scan. Enables:

- Skip-if-done short-circuit: a phase that already succeeded in the
  current scan is not re-run on resume.
- Cross-scan SHA reuse: phases whose output is a pure function of the
  repo HEAD sha (``gitnexus_index``, ``skill_extraction``,
  ``design_system_extract``) reuse prior payloads when the sha matches.
- Durable, queryable audit trail powering the per-phase timeline UI.

See ``BODHIORCHARD-ARCHITECTURE.md §18.12``.

Revision ID: zn_scan_phase_checkpoints
Revises: zm_feature_registry_unique
Create Date: 2026-04-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "zn_scan_phase_checkpoints"
down_revision: str | None = "zm_feature_registry_unique"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PHASE_VALUES = (
    "mode_detection",
    "gitnexus_index",
    "repo_setup",
    "stale_cleanup",
    "skill_extraction",
    "design_system_extract",
    "feature_synthesis",
    "skill_remap",
    "feature_merge",
    "embedding_backfill",
    "persist_results",
)

_STATUS_VALUES = ("pending", "running", "done", "failed", "skipped")


def upgrade() -> None:
    # Enums created via raw SQL to avoid asyncpg + SQLAlchemy
    # before_create double-creation (same pattern as repo_status).
    phase_values = ", ".join(f"'{v}'" for v in _PHASE_VALUES)
    status_values = ", ".join(f"'{v}'" for v in _STATUS_VALUES)
    op.execute(f"CREATE TYPE scan_phase AS ENUM ({phase_values})")
    op.execute(f"CREATE TYPE scan_checkpoint_status AS ENUM ({status_values})")

    op.create_table(
        "scan_phase_checkpoints",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_scan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "repo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracked_repositories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "phase",
            postgresql.ENUM(*_PHASE_VALUES, name="scan_phase", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                *_STATUS_VALUES,
                name="scan_checkpoint_status",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sha_at_run", sa.String(40), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
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

    op.create_unique_constraint(
        "uq_scan_ckpt_scan_repo_phase_attempt",
        "scan_phase_checkpoints",
        ["scan_id", "repo_id", "phase", "attempt"],
    )
    # scan_id-only queries are served by ix_scan_ckpt_scan_phase via
    # leading-column match; no standalone single-column index needed.
    op.create_index(
        "ix_scan_ckpt_scan_phase",
        "scan_phase_checkpoints",
        ["scan_id", "phase"],
    )
    op.create_index(
        "ix_scan_ckpt_org_phase_sha",
        "scan_phase_checkpoints",
        ["org_id", "phase", "sha_at_run"],
    )
    op.create_index(
        "ix_scan_ckpt_org_status",
        "scan_phase_checkpoints",
        ["org_id", "status"],
    )
    op.create_index(
        "ix_scan_ckpt_parent",
        "scan_phase_checkpoints",
        ["parent_scan_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_scan_ckpt_parent", table_name="scan_phase_checkpoints")
    op.drop_index("ix_scan_ckpt_org_status", table_name="scan_phase_checkpoints")
    op.drop_index("ix_scan_ckpt_org_phase_sha", table_name="scan_phase_checkpoints")
    op.drop_index("ix_scan_ckpt_scan_phase", table_name="scan_phase_checkpoints")
    op.drop_constraint(
        "uq_scan_ckpt_scan_repo_phase_attempt",
        "scan_phase_checkpoints",
    )
    op.drop_table("scan_phase_checkpoints")
    op.execute("DROP TYPE IF EXISTS scan_checkpoint_status")
    op.execute("DROP TYPE IF EXISTS scan_phase")
