"""Code embedding model for semantic code search."""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class CodeEmbedding(BaseModel):
    """Vector embedding of a code fragment for semantic search."""

    __tablename__ = "code_embeddings"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    repo: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    function_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding = mapped_column(Vector(768), nullable=True)

    def __repr__(self) -> str:
        return f"<CodeEmbedding(id={self.id}, file_path={self.file_path!r})>"
