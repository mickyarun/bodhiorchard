"""BUD commit tracking model for developer activity visibility."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class BUDCommit(BaseModel):
    """A git commit associated with a BUD via branch naming convention.

    Commits are reported by post-commit hooks installed in tracked repos.
    Deduplication is by commit_sha (unique per org).
    """

    __tablename__ = "bud_commits"
    __table_args__ = (
        UniqueConstraint("org_id", "commit_sha", name="uq_bud_commit_org_sha"),
        Index("ix_bud_commit_bud_id", "bud_id"),
        Index("ix_bud_commit_org_repo", "org_id", "repo_path"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bud_documents.id", ondelete="CASCADE"), nullable=False
    )
    repo_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    branch_name: Mapped[str] = mapped_column(String(500), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    commit_message: Mapped[str] = mapped_column(String(500), nullable=False)
    files_changed: Mapped[str] = mapped_column(String(5000), nullable=False, default="")
    author_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    committed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<BUDCommit(sha={self.commit_sha[:8]}, bud_id={self.bud_id})>"
