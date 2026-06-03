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

"""Pydantic schemas for BUD CRUD endpoints.

Section + stage constants (``BUD_SECTIONS``, ``SECTION_REQUIRED_STAGES``,
``BUD_AGENT_SECTIONS``, etc.) live in :mod:`app.schemas.bud_constants`.
This module hosts only the request/response DTO classes.
"""

import re
import uuid
from datetime import datetime
from typing import Any, get_args

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.bud import BUDPriority, BUDStatus

# Re-export design schemas so legacy imports keep working; new code
# should import directly from :mod:`app.schemas.bud_design`.
from app.schemas.bud_design import (  # noqa: F401
    BUDDesignRead,
    DesignGenerateRequest,
    DesignHtmlUpdate,
)
from app.schemas.bud_release import ReleaseStage

# Single source of truth for the accepted Figma share-URL shape:
# - ``/file/<key>/...`` (legacy)
# - ``/design/<key>/...`` (current default since 2024)
# - ``/proto/<key>/...`` (prototype preview links)
# Reused by every BUD schema that accepts ``figma_url`` so a typo can't
# slip into the DB and feed a broken iframe to the Design tab.
_FIGMA_URL_RE = re.compile(
    r"^https://(?:www\.)?figma\.com/(file|design|proto)/[A-Za-z0-9]+(/.*)?$"
)


def _validate_optional_figma_url(value: str | None) -> str | None:
    """Pydantic validator hook — ``None`` / ``""`` pass through, malformed raises.

    Hoisted into a module helper so ``BUDCreate`` / ``BUDUpdate`` /
    ``BUDRead`` share the exact same predicate, not three drift-prone
    copies of the same regex check.
    """
    if value is None or value == "":
        return None
    if not _FIGMA_URL_RE.match(value):
        raise ValueError(
            "figma_url must look like https://www.figma.com/{file|design|proto}/<key>/..."
        )
    return value


class BUDCreate(BaseModel):
    """Schema for creating a new BUD."""

    title: str = Field(..., min_length=1, max_length=500)
    requirements_md: str | None = None
    priority: BUDPriority = BUDPriority.P2
    # Optional Figma file URL — see the bud_documents.figma_url column
    # comment in app.models.bud for the full rationale (Design-tab embed
    # + local-Claude tech-spec prompt). Validated against
    # ``_FIGMA_URL_RE`` so the Design tab never has to render a typo.
    figma_url: str | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")
    # Optional "Advanced settings" picks: map each BUD stage to a specific
    # AgentSkill id. Stages omitted (or the whole field omitted) fall back
    # to the org's default skill for that stage's agent type. Validated in
    # the route handler against the caller's org.
    stage_skill_overrides: dict[BUDStatus, uuid.UUID] | None = None
    # Per-phase auto-generation. Keys: "bud" / "design" / "tech_arch" /
    # "testing". Value true = our agent fires; false / missing = skip.
    # DEFAULT EMPTY DICT = all phases skip. User opts in per phase via
    # the Advanced-settings switches; for everything they leave off the
    # local-AI / external-LLM flow takes over.
    auto_generate_phases: dict[str, bool] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    _validate_figma_url = field_validator("figma_url")(_validate_optional_figma_url)


class BUDUpdate(BaseModel):
    """Schema for updating an existing BUD."""

    title: str | None = Field(None, min_length=1, max_length=500)
    status: str | None = None
    status_override_reason: str | None = Field(None, max_length=2000)
    priority: BUDPriority | None = None
    requirements_md: str | None = None
    tech_spec_md: str | None = None
    test_plan_md: str | None = None
    figma_url: str | None = None
    code_review_comments: list[dict[str, Any]] | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")
    assignee_id: uuid.UUID | None = None
    # Per-phase auto-generate map can be flipped post-creation from the
    # BUD detail page (BUDSkillSettingsDialog). The backend MERGES the
    # incoming dict with the existing column rather than replacing it
    # verbatim, so an older client that doesn't know about a future
    # phase won't silently drop it to false; unknown keys are dropped
    # with a warning log. To explicitly turn a phase off, send the key
    # with ``false`` — omitting it keeps the prior value.
    #
    # Intentionally NOT in FIELD_OWNING_STATUS — editable in any
    # status, including closed/discarded. Closed-BUD edits have no
    # runtime effect (no transitions fire post-close) but stay
    # auditable, and locking the field would surprise users who want
    # to fix the config after the fact.
    auto_generate_phases: dict[str, bool] | None = None
    # Per-BUD tracking-branch override for the UAT / PROD tabs. ``None``
    # falls back to the repo-wide ``uat_branch`` / ``main_branch`` setting;
    # a dict like ``{"uat": "release/*"}`` switches just that stage to the
    # given fnmatch pattern. Per-stage None inside the dict (``{"uat": None}``)
    # is the clear-this-stage signal — the PATCH handler MERGES with the
    # existing column and drops keys whose value is None, so editing one
    # stage does not clobber the other. The validator rejects unknown
    # stage keys and any whitespace-only / empty patterns.
    branch_overrides: dict[str, str | None] | None = None
    # Editable post-creation so the impacted_repos list can be corrected
    # when the tech-arch agent guessed wrong, or when scope changes
    # mid-development. Same merge-vs-replace policy as the column itself
    # (PATCH replaces the array verbatim — there is no merge key on a
    # repo-row identity, so partial edits don't make sense).
    impacted_repos: list[dict[str, Any]] | None = None

    model_config = {"populate_by_name": True}

    _validate_figma_url = field_validator("figma_url")(_validate_optional_figma_url)

    @field_validator("branch_overrides")
    @classmethod
    def _validate_branch_overrides(
        cls, value: dict[str, str | None] | None
    ) -> dict[str, str | None] | None:
        """Only ``uat`` and ``prod`` are valid override keys; values must
        be either ``None`` (clear that stage) or a non-empty / non-whitespace
        branch pattern.

        Allowed keys are derived from the existing ``ReleaseStage`` Literal
        in :mod:`app.schemas.bud_release` so the two contracts stay in
        sync: the only stages that have a release-stage tab are the only
        stages a per-BUD override can target. Surfaces three classes of
        bad input at the API edge:

        * Wrong-case / unknown stage key (``"UAT"`` / ``"production"``).
        * Empty string (``""``) — would otherwise read as truthy in some
          callers and break the fallback-to-repo-default contract.
        * Whitespace-only pattern (``"   "``) — passes Python truthiness
          but fnmatches nothing, so PRs would silently disappear from the
          tab without an obvious cause.
        """
        if value is None:
            return None
        allowed: set[str] = set(get_args(ReleaseStage))
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(
                f"Unsupported branch_overrides keys: {unknown}. Allowed: {sorted(allowed)}."
            )
        for stage, pattern in value.items():
            if pattern is None:
                continue
            if not isinstance(pattern, str) or not pattern.strip():
                raise ValueError(
                    f"branch_overrides[{stage!r}] must be a non-empty pattern or null."
                )
        return value


class BUDAgentTaskRead(BaseModel):
    """Schema for reading a BUD agent task."""

    id: uuid.UUID
    task_type: str
    skill_slug: str = ""
    status: str
    job_id: str | None = None
    attempt: int = 1
    status_message: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_skill_slug(cls, data: Any) -> Any:
        """Pull skill_slug from the joined AgentSkill relationship."""
        if hasattr(data, "skill") and data.skill is not None:
            data.skill_slug = data.skill.skill_slug
        return data


class BUDRead(BaseModel):
    """Schema for reading a single BUD with full content."""

    id: uuid.UUID
    org_id: uuid.UUID
    bud_number: int
    title: str
    status: str
    priority: BUDPriority
    requirements_md: str | None = None
    tech_spec_md: str | None = None
    test_plan_md: str | None = None
    figma_url: str | None = None
    qa_automation_cases: list[dict[str, Any]] | None = None
    qa_manual_cases: list[dict[str, Any]] | None = None
    qa_execution_plan_md: str | None = None
    code_review_comments: list[dict[str, Any]] | None = None
    # Empty dict / None means "all phases skip" — the new default for
    # newly created BUDs. Returned to the frontend so the BUD detail
    # banner can decide which phases are user-driven.
    auto_generate_phases: dict[str, bool] | None = None
    # Per-stage tracking-branch overrides; falls back to the repo-wide
    # setting when a stage is absent / the dict is null.
    branch_overrides: dict[str, str] | None = None
    designs: list[BUDDesignRead] = []
    metadata: dict[str, Any] | None = Field(None, validation_alias="metadata_")
    impacted_repos: list[dict[str, Any]] | None = None
    estimated_dates: dict[str, Any] | None = None
    complexity: int | None = None
    prod_p70_date: datetime | None = None
    current_phase_deadline: datetime | None = None
    assignee_id: uuid.UUID | None = None
    assignee_name: str | None = None
    active_agent_task: BUDAgentTaskRead | None = None
    # In-flight phase-worker event (assignment / todo-gen / estimation):
    # see services/agent_activity_logger.py. ``None`` when nothing is running.
    active_phase_worker: dict[str, str] | None = None
    # Sticky last-failed-phase banner sourced from agent_activity_logs newer
    # than ``phase_failure_acknowledged_at``; cleared via the dismiss endpoint.
    last_phase_failure: dict[str, Any] | None = None
    # Cheap tab-visibility flag for the BUD detail "Learnings" tab. Set
    # by the BUD detail endpoint after a feature_learnings row exists.
    # Full retrospective is fetched lazily via GET /buds/{id}/learning so
    # the BUD list payload stays small.
    has_learning: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def extract_assignee_name(cls, data: Any) -> Any:
        """Pull assignee name from the joined User relationship."""
        if hasattr(data, "assignee") and data.assignee is not None:
            data.assignee_name = data.assignee.name
        return data


class BUDLearningRead(BaseModel):
    """Post-close retrospective payload for the BUD detail Learnings tab.

    Exposes the FeatureLearning row's persisted fields plus the
    ``metrics`` JSONB envelope. The retrospective markdown is rendered
    via the existing markdown component; the metrics dict drives the
    three summary cards (phase-drift bars, contributor table,
    parallelism gauge).
    """

    bud_id: uuid.UUID
    retrospective_md: str | None = None
    cycle_time_days: float | None = None
    estimated_days: float | None = None
    bug_count: int = 0
    metrics: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class BUDListItem(BaseModel):
    """Schema for BUD list view (no full content)."""

    id: uuid.UUID
    bud_number: int
    title: str
    status: str
    priority: BUDPriority
    complexity: int | None = None
    prod_p70_date: datetime | None = None
    current_phase_deadline: datetime | None = None
    assignee_id: uuid.UUID | None = None
    assignee_name: str | None = None
    open_bug_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_assignee_name(cls, data: Any) -> Any:
        """Pull assignee name from the joined User relationship."""
        if hasattr(data, "assignee") and data.assignee is not None:
            data.assignee_name = data.assignee.name
        return data


class ChatMessageRead(BaseModel):
    """Schema for a persisted chat message."""

    id: uuid.UUID
    role: str
    message: str
    user_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    user_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RejectTechArchRequest(BaseModel):
    """Schema for rejecting a tech architecture plan."""

    reason: str = Field(..., min_length=1, max_length=5000)


class ReassignmentRequest(BaseModel):
    """Schema for requesting developer reassignment."""

    reason: str = Field(..., min_length=1, max_length=5000)


class TimelineEventRead(BaseModel):
    """Schema for reading a BUD timeline event."""

    id: uuid.UUID
    event_type: str
    actor_name: str | None = None
    detail: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
