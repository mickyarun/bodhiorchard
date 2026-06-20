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

"""Backfill developer Skill Points for already-shipped BUDs.

After the SP rewrite, BUDs that shipped under the old (assignee-only,
silently-failing) logic never paid their developers. This script re-runs
the close-time developer awards over every PROD / CLOSED BUD so the
correct people are credited retroactively. It is **developer-only** and
**idempotent**: every award dedups on ``source_ref``, so re-running (or
overlapping with the live close handler) never double-credits.

Usage::

    python -m app.scripts.backfill_dev_sp --dry-run            # all orgs, plan only
    python -m app.scripts.backfill_dev_sp --org <uuid>         # one org, apply
    python -m app.scripts.backfill_dev_sp                      # all orgs, apply

``--dry-run`` prints the planned shipped-SP split per BUD (resolved from
todos / contributors) without writing anything.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid

import structlog

from app.database import AsyncSessionLocal
from app.models.bud import BUDStatus
from app.repositories.bud import BUDRepository
from app.repositories.organization import OrganizationRepository
from app.services.bud_shipped_sp import resolve_shipped_weights
from app.services.sp_developer import award_developer_sp_on_close
from app.services.sp_rules import SP_DEV_BUD_SHIPPED
from app.services.sp_split import compute_shares

logger = structlog.get_logger(__name__)

_SHIPPED_STATUSES = [BUDStatus.PROD, BUDStatus.CLOSED]


async def _backfill_org(org_id: uuid.UUID, *, dry_run: bool) -> tuple[int, int]:
    """Process one org. Returns ``(buds_seen, awards_made)``."""
    buds_seen = 0
    awards_made = 0
    async with AsyncSessionLocal() as db:
        buds = await BUDRepository(db, org_id=org_id).list_full_in_statuses(_SHIPPED_STATUSES)
        for bud in buds:
            buds_seen += 1
            if dry_run:
                # Plan only: equal-weight split (no LLM judge in dry-run) so
                # the report is deterministic and side-effect free.
                weights = await resolve_shipped_weights(db, org_id, bud, None)
                shares = compute_shares(SP_DEV_BUD_SHIPPED, weights)
                for user_id, amount in shares.items():
                    print(f"  BUD-{bud.bud_number:03d}  {user_id}  +{amount} SP (shipped)")
                continue
            await award_developer_sp_on_close(db, org_id, bud)
            awards_made += 1
        if not dry_run:
            await db.commit()
    return buds_seen, awards_made


async def _run(org: uuid.UUID | None, *, dry_run: bool) -> None:
    if dry_run:
        print(
            "DRY-RUN: shipped-pool split only, EQUAL weights (the LLM substance "
            "judge does not run here, so trivial-todo down-weighting and the "
            "review / quality / threshold rules are NOT previewed).\n"
        )

    if org is not None:
        org_ids = [org]
    else:
        async with AsyncSessionLocal() as db:
            org_ids = await OrganizationRepository(db).list_all_ids()

    total_buds = 0
    total_awards = 0
    for org_id in org_ids:
        print(f"org {org_id}{' (dry-run)' if dry_run else ''}")
        seen, awarded = await _backfill_org(org_id, dry_run=dry_run)
        total_buds += seen
        total_awards += awarded
    print(
        f"\nDone: {len(org_ids)} org(s), {total_buds} shipped BUD(s), "
        f"{'0 (dry-run)' if dry_run else total_awards} processed."
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Backfill developer SP for shipped BUDs.")
    parser.add_argument("--org", type=uuid.UUID, default=None, help="Limit to one org id.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned shipped-SP split without writing anything.",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.org, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
