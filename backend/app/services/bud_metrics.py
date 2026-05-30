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

"""Compute and persist per-BUD learning metrics on close.

Single entry point ``compute_and_persist(db, org_id, bud)``, called
from ``on_bud_closed()`` after the existing XP/SP/scan side-effects.
Produces the structured envelope written to
``feature_learnings.metrics`` (versioned dict with ``phase_metrics``,
``contributors``, ``parallelism_score``, ``original_estimated_days``)
and incrementally updates the ``velocity_aggregates`` rollup that the
estimator reads.

Idempotency: skip the whole computation when a FeatureLearning row
with non-null ``metrics`` already exists for the BUD. Manual
PROD-then-CLOSED transitions, webhook re-deliveries, and auto-close
races all converge on the same persisted row.
"""

import uuid
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.feature_learning import FeatureLearning
from app.repositories.feature_learning import FeatureLearningRepository
from app.services.bud_metrics_contributors import (
    build_contributor_breakdown,
    compute_parallelism_score,
    cycle_time_days,
)
from app.services.bud_metrics_phases import (
    build_phase_metrics,
    original_estimated_days_from_metrics,
)

logger = structlog.get_logger(__name__)

# Bump when the envelope shape changes — readers that depend on a
# specific shape can refuse to deserialize older versions instead of
# silently misinterpreting them.
METRICS_SCHEMA_VERSION = 1


def _bug_count(bud: BUDDocument) -> int:
    """Total QA test-case count (automation + manual) as a bug-volume proxy.

    Matches the existing field used by ``_record_feature_learning`` so
    downstream consumers see the same number after this service replaces
    that function. When real bug-tracking lands, swap to a query against
    the ``bugs`` table.
    """
    auto = len(bud.qa_automation_cases or [])
    manual = len(bud.qa_manual_cases or [])
    return auto + manual


def _resolve_closed_at(bud: BUDDocument) -> datetime:
    """Best-effort BUD close timestamp.

    ``bud.updated_at`` is set by the ORM on the same PATCH that sets
    ``status = CLOSED``, so it's the correct close moment for the
    manual path. The auto-close path also touches ``updated_at`` when
    it flips the status, so the same field works there.
    """
    return bud.updated_at or datetime.now(tz=bud.created_at.tzinfo)


async def _build_metrics_envelope(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    bud_closed_at: datetime,
) -> dict[str, Any]:
    """Assemble the full ``metrics`` JSONB envelope for a BUD."""
    phase_metrics = await build_phase_metrics(db, org_id, bud, bud_closed_at)
    contributors = await build_contributor_breakdown(db, org_id, bud)
    parallelism = await compute_parallelism_score(db, org_id, bud, phase_metrics)
    original_estimated = original_estimated_days_from_metrics(phase_metrics)
    return {
        "schema_version": METRICS_SCHEMA_VERSION,
        "original_estimated_days": original_estimated,
        "phase_metrics": phase_metrics,
        "contributors": contributors,
        "parallelism_score": parallelism,
    }


async def compute_and_persist(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> FeatureLearning | None:
    """Idempotent post-close metric write.

    Returns the persisted FeatureLearning row (existing or freshly
    inserted), or None when computation was skipped entirely (e.g.
    BUD has no ``created_at`` — defensive against malformed fixtures).
    Velocity-aggregate roll-forward fires only on the first successful
    persist so re-runs don't double-count a BUD's contribution to the
    bucket statistics.
    """
    if bud.created_at is None:
        logger.warning("bud_metrics_skipped_missing_created_at", bud_id=str(bud.id))
        return None

    repo = FeatureLearningRepository(db, org_id=org_id)
    existing = await repo.get_for_bud(bud.id)
    if existing is not None and existing.metrics is not None:
        logger.debug(
            "bud_metrics_skip_already_computed",
            bud_id=str(bud.id),
            bud_number=bud.bud_number,
        )
        return existing

    bud_closed_at = _resolve_closed_at(bud)
    metrics = await _build_metrics_envelope(db, org_id, bud, bud_closed_at)
    row = await repo.upsert_for_bud(
        bud.id,
        cycle_time_days=cycle_time_days(bud, bud_closed_at),
        estimated_days=metrics.get("original_estimated_days"),
        bug_count=_bug_count(bud),
        metrics=metrics,
    )

    # NOTE: roll-forward into ``velocity_aggregates`` is wired in the
    # commit that introduces that table. Until then, the estimator
    # continues to read history via the legacy proportional split — no
    # behaviour change at this point.

    logger.info(
        "bud_metrics_recorded",
        bud_id=str(bud.id),
        bud_number=bud.bud_number,
        phase_count=len(metrics.get("phase_metrics") or {}),
        contributor_count=len(metrics.get("contributors") or []),
        parallelism_score=metrics.get("parallelism_score"),
    )
    return row
