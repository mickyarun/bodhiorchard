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

"""Incremental velocity-aggregate roll-forward.

Called from ``bud_metrics.compute_and_persist`` once per BUD close.
For each phase the BUD touched, runs an idempotent UPSERT against
``velocity_aggregates`` using the standard online-bootstrap pattern.
The actual math lives in ``velocity_aggregate_math``; this module is
just orchestration (per-phase loop + DB upsert + observability log).
"""

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.repositories.velocity_aggregate import VelocityAggregateRepository
from app.services.velocity_aggregate_math import derive_bucket_snapshot

logger = structlog.get_logger(__name__)


async def roll_bud_into_aggregates(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    metrics: dict[str, Any],
) -> int:
    """Apply this BUD's per-phase actuals to the org's velocity aggregates.

    Returns the number of phase buckets actually updated (zero when the
    BUD was already counted or its envelope has no phase actuals).
    """
    complexity = bud.complexity
    if complexity is None:
        logger.debug("velocity_agg_skip_no_complexity", bud_id=str(bud.id))
        return 0

    phase_metrics = metrics.get("phase_metrics") or {}
    if not isinstance(phase_metrics, dict) or not phase_metrics:
        return 0

    repo = VelocityAggregateRepository(db, org_id=org_id)
    bud_id_str = str(bud.id)
    updated = 0

    for phase_value, phase_entry in phase_metrics.items():
        if not isinstance(phase_entry, dict):
            continue
        actual_days = phase_entry.get("actual_days")
        if actual_days is None or float(actual_days) <= 0:
            continue
        try:
            phase_enum = BUDStatus(phase_value)
        except ValueError:
            logger.warning(
                "velocity_agg_unknown_phase_key",
                bud_id=bud_id_str,
                phase=phase_value,
            )
            continue

        existing = await repo.get_bucket(complexity, phase_enum)
        snapshot = derive_bucket_snapshot(
            current_window=list(existing.sample_window) if existing else [],
            current_contributing=list(existing.contributing_bud_ids) if existing else [],
            current_n=existing.n_samples if existing else 0,
            current_mean=float(existing.running_mean) if existing else 0.0,
            current_m2=float(existing.running_m2) if existing else 0.0,
            new_actual_days=float(actual_days),
            new_bud_id=bud_id_str,
        )
        if snapshot is None:
            continue

        await repo.upsert_bucket_state(
            complexity,
            phase_enum,
            sample_window=snapshot.sample_window,
            contributing_bud_ids=snapshot.contributing_bud_ids,
            n_samples=snapshot.n_samples,
            running_mean=snapshot.running_mean,
            running_m2=snapshot.running_m2,
            p50_days=snapshot.p50_days,
            p70_days=snapshot.p70_days,
            p85_days=snapshot.p85_days,
            pert_optimistic=snapshot.pert_optimistic,
            pert_most_likely=snapshot.pert_most_likely,
            pert_pessimistic=snapshot.pert_pessimistic,
        )
        updated += 1

    if updated:
        logger.info(
            "velocity_agg_rolled",
            bud_id=bud_id_str,
            bud_number=bud.bud_number,
            complexity=complexity,
            phases_updated=updated,
        )
    return updated
