"""Organization model for multi-tenant isolation."""

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class Organization(BaseModel):
    """Represents a tenant organization in the platform."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    github_pat: Mapped[str | None] = mapped_column(Text, nullable=True)
    slack_bot_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    slack_signing_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    mcp_token_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User", back_populates="organization", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, slug={self.slug!r})>"
