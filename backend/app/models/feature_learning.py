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

"""Feature learning model for retrospective analysis and estimation improvement."""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class FeatureLearning(BaseModel):
    """Captures learnings from completed features to improve future estimates."""

    __tablename__ = "feature_learnings"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bud_documents.id"), nullable=False
    )
    cycle_time_days: Mapped[float | None] = mapped_column(
        Numeric(precision=8, scale=2), nullable=True
    )
    estimated_days: Mapped[float | None] = mapped_column(
        Numeric(precision=8, scale=2), nullable=True
    )
    bug_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retrospective_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding = mapped_column(Vector(384), nullable=True)

    def __repr__(self) -> str:
        return f"<FeatureLearning(id={self.id}, bud_id={self.bud_id})>"
