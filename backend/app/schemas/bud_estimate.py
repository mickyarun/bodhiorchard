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

"""Schemas for the BUD AI-PERT estimation endpoints.

Split from ``schemas/bud.py`` so the per-BUD CRUD schemas and the
estimation-specific schemas can evolve independently — Phase D added
``project_buffer_days`` and ``commit_date`` and the file was sitting
right at the project's 300-line cap.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PhaseEstimate(BaseModel):
    """Estimated completion for a single BUD lifecycle phase."""

    phase: str
    estimated_completion: datetime
    p50_date: datetime | None = None
    p70_date: datetime | None = None
    p85_date: datetime | None = None
    expected_days: float | None = None
    std_dev_days: float | None = None
    source: str
    confidence: float
    override_reason: str | None = None


class BUDEstimatesRead(BaseModel):
    """Full estimation response for a BUD with Monte Carlo percentiles."""

    bud_id: uuid.UUID
    complexity: int | None = None
    phases: list[PhaseEstimate] = []
    prod_p50: datetime | None = None
    prod_p70: datetime | None = None
    prod_p85: datetime | None = None
    # Critical Chain Method (Phase D). Both nullable so old snapshots
    # generated before Phase D landed deserialize cleanly without a
    # backfill — the frontend renders no buffer pill in that case.
    project_buffer_days: float | None = None
    commit_date: datetime | None = None
    generated_at: datetime | None = None
    trigger: str | None = None


class EstimateOverrideRequest(BaseModel):
    """Request to manually override a phase's estimated date."""

    estimated_completion: datetime
    reason: str = Field(..., min_length=1, max_length=2000)


class EstimateSnapshotRead(BaseModel):
    """Read schema for a historical estimate snapshot."""

    id: uuid.UUID
    trigger: str
    phase_estimates: dict
    complexity: int | None = None
    context: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
