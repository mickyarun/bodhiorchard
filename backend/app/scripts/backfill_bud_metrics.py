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

"""Backfill post-close BUD metrics for rows left partial by a transient failure.

When ``compute_and_persist`` hits a transient error at close time (an
infra hiccup, a contributor-provisioning race), the Learning Agent can
still attach its recap via ``set_retrospective`` — leaving a
``feature_learnings`` row with ``retrospective_md`` but a NULL
``metrics`` envelope (and so NULL ``estimated_days`` / ``cycle_time_days``).
Those rows are invisible to the velocity-aggregate rollup, starving the
estimator's historical reference class.

This script re-runs ``compute_and_persist`` over every PROD / CLOSED BUD.
It is **idempotent**: the service's skip-if-rich guard keys on
``metrics is not None``, so already-computed rows are left untouched and
only the partial ones are filled (and rolled into ``velocity_aggregates``
for the first time).

Usage::

    python -m app.scripts.backfill_bud_metrics --dry-run          # all orgs, plan only
    python -m app.scripts.backfill_bud_metrics --org <uuid>       # one org, apply
    python -m app.scripts.backfill_bud_metrics                    # all orgs, apply

``--dry-run`` lists the BUDs whose ``metrics`` envelope is currently NULL
(the ones a real run would fill) without writing anything.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

import structlog

from app.database import AsyncSessionLocal
from app.models.bud import BUDStatus
from app.repositories.bud import BUDRepository
from app.repositories.feature_learning import FeatureLearningRepository
from app.repositories.organization import OrganizationRepository
from app.services.bud_metrics import compute_and_persist

logger = structlog.get_logger(__name__)

_CLOSED_STATUSES = [BUDStatus.PROD, BUDStatus.CLOSED]


async def _backfill_org(org_id: uuid.UUID, *, dry_run: bool) -> tuple[int, int]:
    """Process one org. Returns ``(buds_seen, rows_filled)``."""
    buds_seen = 0
    rows_filled = 0
    async with AsyncSessionLocal() as db:
        buds = await BUDRepository(db, org_id=org_id).list_full_in_statuses(_CLOSED_STATUSES)
        learning_repo = FeatureLearningRepository(db, org_id=org_id)
        for bud in buds:
            buds_seen += 1
            existing = await learning_repo.get_for_bud(bud.id)
            already_rich = existing is not None and existing.metrics is not None
            if already_rich:
                continue
            if dry_run:
                print(
                    f"  BUD-{bud.bud_number:03d}  {bud.id}  "
                    f"metrics=NULL (would backfill; recap "
                    f"{'present' if existing and existing.retrospective_md else 'absent'})"
                )
                continue
            row = await compute_and_persist(db, org_id, bud)
            if row is not None and row.metrics is not None:
                rows_filled += 1
                print(f"  BUD-{bud.bud_number:03d}  {bud.id}  metrics backfilled")
            else:
                print(f"  BUD-{bud.bud_number:03d}  {bud.id}  skipped (no created_at)")
        if not dry_run:
            await db.commit()
    return buds_seen, rows_filled


async def _run(org: uuid.UUID | None, *, dry_run: bool) -> None:
    if org is not None:
        org_ids = [org]
    else:
        async with AsyncSessionLocal() as db:
            org_ids = await OrganizationRepository(db).list_all_ids()

    total_buds = 0
    total_filled = 0
    for org_id in org_ids:
        print(f"org {org_id}{' (dry-run)' if dry_run else ''}")
        seen, filled = await _backfill_org(org_id, dry_run=dry_run)
        total_buds += seen
        total_filled += filled
    print(
        f"\nDone: {len(org_ids)} org(s), {total_buds} closed BUD(s), "
        f"{'0 (dry-run)' if dry_run else total_filled} backfilled."
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Backfill post-close metrics for partial feature_learnings rows."
    )
    parser.add_argument("--org", type=uuid.UUID, default=None, help="Limit to one org id.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the BUDs whose metrics are NULL without writing anything.",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.org, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
