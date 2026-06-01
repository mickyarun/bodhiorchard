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

"""Re-process the post-close metrics pipeline for a single closed BUD.

Usage:
    cd backend && python -m scripts.reprocess_bud_learning <bud_number>

Wipes the existing feature_learnings row (and that BUD's contribution
to velocity_aggregates) and re-runs ``bud_metrics.compute_and_persist``.
Use this after fixing a metrics-shape bug to backfill the BUD's
envelope without changing anything else about the closed BUD.
"""

import asyncio
import sys
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.bud import BUDDocument
from app.models.feature_learning import FeatureLearning
from app.models.velocity_aggregate import VelocityAggregate
from app.services.bud_metrics import compute_and_persist


async def _purge_existing_state(db: Any, bud: BUDDocument) -> None:
    """Reset the BUD's contribution so compute_and_persist will re-run.

    We do NOT delete the FeatureLearning row — the LLM-written
    ``retrospective_md`` and its embedding are expensive to regenerate
    (one Claude subprocess at ~$0.16 a pop) and are still valid even
    when the structured metrics envelope changes. Clearing only the
    ``metrics`` field is enough to defeat the idempotency guard inside
    ``compute_and_persist`` (which short-circuits when ``metrics is
    not None``). The cycle/estimated/bug fields will be overwritten by
    the upsert anyway.

    Walks every velocity_aggregates bucket the BUD touched and removes
    its sample from the rolling window so the re-run lands on a clean
    slate for the rollup math too.
    """
    fl_row = (
        await db.execute(
            select(FeatureLearning).where(
                FeatureLearning.org_id == bud.org_id,
                FeatureLearning.bud_id == bud.id,
            )
        )
    ).scalar_one_or_none()
    if fl_row is not None:
        fl_row.metrics = None
        await db.flush()

    aggs = (
        (
            await db.execute(
                select(VelocityAggregate).where(
                    VelocityAggregate.org_id == bud.org_id,
                    VelocityAggregate.complexity == bud.complexity,
                )
            )
        )
        .scalars()
        .all()
    )
    bud_id_str = str(bud.id)
    for agg in aggs:
        contributing = list(agg.contributing_bud_ids or [])
        if bud_id_str not in contributing:
            continue
        idx = contributing.index(bud_id_str)
        contributing.pop(idx)
        window = list(agg.sample_window or [])
        if 0 <= idx < len(window):
            window.pop(idx)
        agg.contributing_bud_ids = contributing
        agg.sample_window = window
        agg.n_samples = max(0, agg.n_samples - 1)
        # Re-derive percentiles from the surviving window. When the
        # window is empty after removal, zero out the derived fields.
        if window:
            sorted_w = sorted(window)
            agg.p50_days = sorted_w[min(len(sorted_w) - 1, int(len(sorted_w) * 0.5))]
            agg.p70_days = sorted_w[min(len(sorted_w) - 1, int(len(sorted_w) * 0.7))]
            agg.p85_days = sorted_w[min(len(sorted_w) - 1, int(len(sorted_w) * 0.85))]
        else:
            agg.p50_days = None
            agg.p70_days = None
            agg.p85_days = None
            agg.pert_optimistic = None
            agg.pert_most_likely = None
            agg.pert_pessimistic = None
    await db.flush()


async def reprocess(bud_number: int) -> None:
    """Look up the BUD and re-run the metrics pipeline."""
    async with AsyncSessionLocal() as db:
        bud = (
            await db.execute(select(BUDDocument).where(BUDDocument.bud_number == bud_number))
        ).scalar_one_or_none()
        if bud is None:
            print(f"BUD-{bud_number} not found.")
            return
        print(f"Found BUD-{bud.bud_number} ({bud.title}) — status={bud.status.value}")
        await _purge_existing_state(db, bud)
        print("  cleared prior feature_learnings + velocity_aggregates contributions")
        result = await compute_and_persist(db, bud.org_id, bud)
        await db.commit()
        if result is None:
            print("  compute_and_persist returned None (likely missing created_at)")
            return
        print("  compute_and_persist wrote a new FeatureLearning row")
        if result.metrics:
            phase_metrics = result.metrics.get("phase_metrics") or {}
            print("  per-phase actual / estimated / drift:")
            for phase, entry in sorted(phase_metrics.items()):
                if not isinstance(entry, dict):
                    continue
                print(
                    f"    {phase:<14} actual={entry.get('actual_days')} "
                    f"estimated={entry.get('estimated_days')} "
                    f"drift={entry.get('drift_pct')}%"
                )
            print(
                f"  metrics.original_estimated_days = "
                f"{result.metrics.get('original_estimated_days')}"
            )


def main() -> None:
    """CLI entry point — parses bud_number from argv."""
    if len(sys.argv) < 2:
        print("usage: python -m scripts.reprocess_bud_learning <bud_number>")
        sys.exit(1)
    try:
        bud_number = int(sys.argv[1])
    except ValueError:
        print(f"bud_number must be an integer, got {sys.argv[1]!r}")
        sys.exit(1)
    asyncio.run(reprocess(bud_number))


if __name__ == "__main__":
    main()
