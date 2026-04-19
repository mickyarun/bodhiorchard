# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pull request model for tracking GitHub PRs linked to BUDs."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PRState(StrEnum):
    """GitHub PR lifecycle state."""

    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class PRReviewStatus(StrEnum):
    """Aggregated review status of a PR."""

    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class PullRequest(BaseModel):
    """A GitHub pull request linked to a BUD and tracked repository."""

    __tablename__ = "pull_requests"
    __table_args__ = (
        UniqueConstraint("org_id", "github_pr_id", name="uq_pr_org_github_id"),
        Index("ix_pr_bud_id", "bud_id"),
        Index("ix_pr_org_state", "org_id", "state"),
        # Lookup by the SHA written to the base branch on merge — used by
        # release-stage detection to find which BUD a release-PR commit
        # belongs to. Partial index keeps it small (most rows are unmerged).
        Index(
            "ix_pr_merge_commit_sha",
            "org_id",
            "merge_commit_sha",
            postgresql_where=text("merge_commit_sha IS NOT NULL"),
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False,
    )
    bud_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_repositories.id", ondelete="SET NULL"),
        nullable=True,
    )
    github_pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    github_pr_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    github_repo_full_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    head_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    base_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[PRState] = mapped_column(
        Enum(PRState, name="pr_state", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=PRState.OPEN,
    )
    author_github_login: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    merged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # SHA written to the base branch on merge (works for merge / squash /
    # rebase strategies). Captured from GitHub's pull_request.closed payload
    # via GitHubPullRequest.merge_commit_sha. Used by release-stage detection
    # to match which BUDs a downstream release PR carries.
    merge_commit_sha: Mapped[str | None] = mapped_column(
        String(40), nullable=True,
    )
    review_status: Mapped[PRReviewStatus] = mapped_column(
        Enum(
            PRReviewStatus,
            name="pr_review_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=PRReviewStatus.PENDING,
    )
    metadata_: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<PullRequest(#{self.github_pr_number} "
            f"{self.github_repo_full_name} {self.state.value})>"
        )
