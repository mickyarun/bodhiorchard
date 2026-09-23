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

"""File attached to a :class:`app.models.bug.Bug`."""

import uuid

from sqlalchemy import BigInteger, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class BugAttachment(BaseModel):
    """Metadata for a screenshot, PDF or spreadsheet attached to a bug.

    The bytes live in object storage (local disk or S3) behind
    :class:`app.services.file_storage.FileStorage`; this row holds the
    pointer plus everything needed to render and serve the file without
    touching storage — mirroring
    :class:`app.models.qa_test_evidence.QATestEvidence`.

    ``mime_type`` is the *canonical* type derived from the filename
    extension at upload time, never the browser-supplied one, so the
    download route can serve it back without re-sniffing. Deleting a bug
    cascades these rows away; the orphaned objects in storage are
    removed by the delete route, which is the only supported path.
    """

    __tablename__ = "bug_attachments"
    __table_args__ = (Index("ix_bug_attachments_bug_created", "bug_id", "created_at"),)

    bug_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bugs.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # BigInteger rather than Integer: the per-org cap is configurable and
    # a future raise past 2 GB should not need a column migration.
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<BugAttachment(id={self.id}, bug_id={self.bug_id}, filename={self.filename!r})>"
