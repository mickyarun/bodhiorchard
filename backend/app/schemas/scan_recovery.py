# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pydantic DTOs for the scan-recovery and resume APIs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FeatureRecoveryResult(BaseModel):
    """Outcome of a ``/scan/recover/feature/{id}`` call."""

    model_config = ConfigDict(populate_by_name=True)

    knowledge_item_id: uuid.UUID = Field(..., alias="knowledgeItemId")
    repo_id: uuid.UUID = Field(..., alias="repoId")
    feature_title: str = Field(..., alias="featureTitle")
    created_new: bool = Field(
        ...,
        alias="createdNew",
        description=(
            "True when the original KnowledgeItem had been hard-deleted "
            "and a fresh row was minted from the synthesized_features "
            "snapshot. False when the original row still existed and "
            "only the repo link was restored."
        ),
    )
    previous_merge_outcome: str | None = Field(
        ...,
        alias="previousMergeOutcome",
        description=(
            "The ``merge_outcome`` on the synth row *before* recovery. "
            "Surfaced so an admin UI can explain why this feature "
            "needed restoring (e.g. 'merged_into:<uuid>'). The synth "
            "row itself is not mutated by the recovery call."
        ),
    )


class CheckpointRead(BaseModel):
    """One row from ``scan_phase_checkpoints`` in the API shape."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    scan_id: uuid.UUID = Field(..., alias="scanId")
    parent_scan_id: uuid.UUID | None = Field(None, alias="parentScanId")
    org_id: uuid.UUID = Field(..., alias="orgId")
    repo_id: uuid.UUID | None = Field(None, alias="repoId")
    phase: str
    status: str
    attempt: int
    started_at: datetime | None = Field(None, alias="startedAt")
    finished_at: datetime | None = Field(None, alias="finishedAt")
    sha_at_run: str | None = Field(None, alias="shaAtRun")
    error_code: str | None = Field(None, alias="errorCode")
    error_message: str | None = Field(None, alias="errorMessage")


class CheckpointListResponse(BaseModel):
    """Response for ``GET /scan/{scan_id}/checkpoints``."""

    model_config = ConfigDict(populate_by_name=True)

    scan_id: uuid.UUID = Field(..., alias="scanId")
    total: int
    checkpoints: list[CheckpointRead]


class ResumeScanResponse(BaseModel):
    """Response for ``POST /scan/{scan_id}/resume``."""

    model_config = ConfigDict(populate_by_name=True)

    new_scan_id: uuid.UUID = Field(..., alias="newScanId")
    parent_scan_id: uuid.UUID = Field(..., alias="parentScanId")
    copied_checkpoints: int = Field(
        ...,
        alias="copiedCheckpoints",
        description=(
            "How many DONE / SKIPPED checkpoints were forwarded from "
            "the parent scan into the new one. Phases whose parent "
            "checkpoint was FAILED / PENDING / RUNNING are NOT copied — "
            "they will run fresh under the new scan_id."
        ),
    )


class RetryPhaseResponse(BaseModel):
    """Response for ``POST /scan/{scan_id}/phases/{phase}/retry``."""

    model_config = ConfigDict(populate_by_name=True)

    new_scan_id: uuid.UUID = Field(..., alias="newScanId")
    parent_scan_id: uuid.UUID = Field(..., alias="parentScanId")
    phase: str
    repo_id: uuid.UUID | None = Field(None, alias="repoId")
    copied_checkpoints: int = Field(..., alias="copiedCheckpoints")
