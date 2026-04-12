"""Add UAT branch and merge_commit_sha for release-stage tracking.

Adds two nullable columns and one partial index to support BUD release-stage
tracking (UAT and Prod tabs on the BUD detail page):

- ``tracked_repositories.uat_branch``: optional branch name (e.g.
  ``release/uat``) to monitor for promotion-to-UAT events. Nullable so
  per-repo opt-in is preserved; the org-level ``bud_stages.uat_enabled``
  flag controls whether the column is read at all.

- ``pull_requests.merge_commit_sha``: the SHA written to the base branch
  when the PR was merged. Captured from GitHub's ``pull_request.closed``
  webhook payload, regardless of merge strategy (merge / squash / rebase).
  Used by the release-stage detector to find which BUDs a downstream
  release PR carries.

- ``ix_pr_merge_commit_sha``: partial index on
  ``(org_id, merge_commit_sha)`` filtered to non-null values, so the
  per-commit lookup that fans out from each release PR is fast and the
  index doesn't bloat with the OPEN PR rows that have no merge SHA yet.

No data backfill: detection is forward-only (PRs merged before this ship
won't be matchable, which is acceptable since release-stage tabs only
exist from this point on).

Revision ID: zb_bud_release_tracking
Revises: za_actor_role_dev_activity
Create Date: 2026-04-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zb_bud_release_tracking"
down_revision: str | None = "za_actor_role_dev_activity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the two columns and partial index."""
    op.add_column(
        "tracked_repositories",
        sa.Column("uat_branch", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "pull_requests",
        sa.Column("merge_commit_sha", sa.String(length=40), nullable=True),
    )
    op.create_index(
        "ix_pr_merge_commit_sha",
        "pull_requests",
        ["org_id", "merge_commit_sha"],
        postgresql_where=sa.text("merge_commit_sha IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop the partial index and the two columns."""
    op.drop_index("ix_pr_merge_commit_sha", table_name="pull_requests")
    op.drop_column("pull_requests", "merge_commit_sha")
    op.drop_column("tracked_repositories", "uat_branch")
