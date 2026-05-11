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

"""reposcanv2: scan_repo_runs + scan_repo_steps

Revision ID: b3549cc9d508
Revises: d12dfd234b12
Create Date: 2026-04-26 05:37:38.995209

Adds the per-repo run + per-phase step tables that drive the v2
timeline UI and the resume mechanism. New PG enum types: ``repo_run_status``,
``step_status``. Reuses the existing ``scan_phase`` enum for ``scan_repo_steps.phase``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3549cc9d508"
down_revision: str | None = "d12dfd234b12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_REPO_RUN_STATUS_VALUES = (
    "queued",
    "running",
    "done",
    "failed",
    "skipped_unchanged",
    "cancelled",
)
_STEP_STATUS_VALUES = (
    "queued",
    "running",
    "done",
    "failed",
    "skipped_cache",
    "skipped",
)


def upgrade() -> None:
    op.create_table(
        "scan_repo_runs",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("scan_id", sa.UUID(), nullable=False),
        sa.Column("repo_id", sa.UUID(), nullable=False),
        sa.Column("head_sha_at_start", sa.String(length=40), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*_REPO_RUN_STATUS_VALUES, name="repo_run_status"),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("feature_count", sa.Integer(), nullable=True),
        sa.Column("skill_count", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["repo_id"], ["tracked_repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scan_id"], ["scans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_id", "repo_id", name="uq_scan_repo_run_scan_repo"),
    )
    op.create_index(
        "ix_scan_repo_run_org_repo",
        "scan_repo_runs",
        ["org_id", "repo_id"],
        unique=False,
    )
    op.create_index(
        "ix_scan_repo_run_scan_status",
        "scan_repo_runs",
        ["scan_id", "status"],
        unique=False,
    )

    op.create_table(
        "scan_repo_steps",
        sa.Column("scan_repo_run_id", sa.UUID(), nullable=False),
        # Reuse existing scan_phase PG enum.
        sa.Column(
            "phase",
            postgresql.ENUM(name="scan_phase", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(*_STEP_STATUS_VALUES, name="step_status"),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kept_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dropped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "extras",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["scan_repo_run_id"], ["scan_repo_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_repo_run_id", "phase", name="uq_scan_repo_step_run_phase"),
    )
    op.create_index(
        "ix_scan_repo_step_run_status",
        "scan_repo_steps",
        ["scan_repo_run_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scan_repo_step_run_status", table_name="scan_repo_steps")
    op.drop_table("scan_repo_steps")
    op.drop_index("ix_scan_repo_run_scan_status", table_name="scan_repo_runs")
    op.drop_index("ix_scan_repo_run_org_repo", table_name="scan_repo_runs")
    op.drop_table("scan_repo_runs")
    sa.Enum(name="step_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="repo_run_status").drop(op.get_bind(), checkfirst=True)
