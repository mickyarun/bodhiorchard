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

"""Sandbox-isolated SQLAlchemy models that mirror the production merge schema.

Each ``XLM*`` class is a structural copy of the production model it
shadows — same columns, same types — so that when sandbox code is
promoted, the only required change is the import path. The ``XLMBase``
declarative base is intentionally separate from
``app.models.base.Base`` so Alembic autogenerate ignores these tables.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pgvector.sqlalchemy import Vector  # type: ignore[import-untyped]
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class XLMBase(DeclarativeBase):
    """Sandbox declarative base — isolated from production Alembic registry."""


class XLMRepoLayer(StrEnum):
    """Classification result for a tracked repo.

    ``BATCH`` is for periodic / cron / queue-driven workers that run server-
    side but aren't user-request-handlers (distinct from ``PROCESSOR`` which
    historically meant "tooling around the API"). Knowing which repos are
    batch matters for cross-layer linking: a frontend feature can't depend on
    a batch job's endpoints because batch jobs don't expose HTTP routes.
    """

    FRONTEND = "frontend"
    BACKEND = "backend"
    PROCESSOR = "processor"
    BATCH = "batch"
    DB = "db"
    SHARED = "shared"


class XLMMergeOutcome(StrEnum):
    """Mirrors the production ``MergeOutcome`` enum exactly."""

    CANONICAL = "canonical"
    MERGED_INTO = "merged_into"
    UNVISITED = "unvisited"


class XLMPairStatus(StrEnum):
    """Lifecycle status of a single repo-pair verification step."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class XLMTrackedRepo(XLMBase):
    """Mirror of ``tracked_repositories`` plus the new layer/tech/db columns."""

    __tablename__ = "xlm_tracked_repo"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    repo_layer: Mapped[XLMRepoLayer | None] = mapped_column(
        Enum(
            XLMRepoLayer,
            name="xlm_repo_layer",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=True,
    )
    tech_stack: Mapped[str | None] = mapped_column(String(100), nullable=True)
    db_flavor: Mapped[str | None] = mapped_column(String(100), nullable=True)


class XLMSynthesizedFeature(XLMBase):
    """Mirror of ``synthesized_features``. Same fields, same semantics."""

    __tablename__ = "xlm_synth_feature"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("xlm_tracked_repo.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    cluster_names: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    code_locations: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    embedding = mapped_column(Vector(384), nullable=True)
    knowledge_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("xlm_knowledge_item.id", ondelete="SET NULL"),
        nullable=True,
    )
    merge_outcome: Mapped[XLMMergeOutcome | None] = mapped_column(
        Enum(
            XLMMergeOutcome,
            name="xlm_synth_merge_outcome",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=True,
    )
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("xlm_synth_feature.id", ondelete="SET NULL"),
        nullable=True,
    )
    synthesized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Populated only for frontend rows by the ``backend_link`` stage.
    # Each backend_repo_id is a UUID from xlm_tracked_repo whose code declares
    # at least one endpoint that this frontend feature calls.
    backend_repo_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    # The actual ``${baseURL}`` paths from this feature's frontend code, e.g.
    # ``/payments/get-payment-details``. Cross-referenced against the backend
    # route declarations to populate ``backend_repo_ids``.
    backend_api_paths: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )


class XLMKnowledgeItem(XLMBase):
    """Mirror of ``knowledge_items`` (post-merge canonical view)."""

    __tablename__ = "xlm_knowledge_item"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    embedding = mapped_column(Vector(384), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)


class XLMKnowledgeRepoLink(XLMBase):
    """Mirror of ``knowledge_to_repo`` junction with code_locations payload."""

    __tablename__ = "xlm_ki_repo_link"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("xlm_knowledge_item.id", ondelete="CASCADE"),
        nullable=False,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("xlm_tracked_repo.id", ondelete="CASCADE"),
        nullable=False,
    )
    code_locations: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class XLMPairPlan(XLMBase):
    """Sandbox-only: ordered list of repo pairs the verifier will process."""

    __tablename__ = "xlm_pair_plan"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("xlm_tracked_repo.id", ondelete="CASCADE"),
        nullable=False,
    )
    repo_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("xlm_tracked_repo.id", ondelete="CASCADE"),
        nullable=False,
    )
    pair_kind: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g. "frontend×backend"
    status: Mapped[XLMPairStatus] = mapped_column(
        Enum(
            XLMPairStatus,
            name="xlm_pair_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=XLMPairStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class XLMMergeLog(XLMBase):
    """Audit row per Claude cluster-merge decision.

    Sandbox-only mirror of what the production merge phase would log
    if it kept a per-cluster trail. Recorded inside the runner after
    every ``ask_claude`` call so prompt iteration has data — without
    this, "Claude said no_match" looks identical to "Claude timed out"
    in the run summary.
    """

    __tablename__ = "xlm_merge_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_synth_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    canonical_ki_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cluster_member_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    related_existing_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    # One of: ``merge`` / ``no_match`` / ``error`` / NULL when Claude was never asked.
    action: Mapped[str | None] = mapped_column(String(50), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    absorbed_synth_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class XLMPairLog(XLMBase):
    """Sandbox-only: one row per Claude verifier call.

    Captures the source feature, candidates shown, prompt, response, and
    applied outcome — the audit trail used to iterate the prompt.
    """

    __tablename__ = "xlm_pair_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("xlm_pair_plan.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_synth_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    candidate_synth_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(String(50), nullable=True)  # merge | no_match
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_synth_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    absorbed_synth_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
