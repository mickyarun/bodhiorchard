#!/usr/bin/env python3
# Local-only smoke harness — not part of any PR.
"""Re-run the global ``backend_link`` phase against the local DB.

Useful when you've changed the linker (added language coverage, fixed a
regex, etc.) and want to see the effect on real org data without rerunning
a full scan. Idempotent: ``replace_backend_links`` is the existing
"replace all backend-role rows for this feature" writer, so calling the
phase twice converges on the same set of links.

Reports a before/after table grouped by ``tracked_repositories.tech_stack``
so you can see at a glance whether Flutter (or any other language gate)
moved off zero.

Usage::

    cd backend && python scripts/rerun_backend_link.py
    cd backend && python scripts/rerun_backend_link.py --org-id <uuid>
    cd backend && python scripts/rerun_backend_link.py --snapshot-only
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.services.scan.phase_impls.backend_link import run_backend_link  # noqa: E402

_SNAPSHOT_SQL = """
SELECT tr.tech_stack,
       COUNT(DISTINCT tr.id)                    AS repos,
       COUNT(DISTINCT primary_link.feature_id)  AS features_owned,
       COUNT(DISTINCT backend_link.feature_id)  AS features_linked,
       ROUND(100.0 * COUNT(DISTINCT backend_link.feature_id)
             / NULLIF(COUNT(DISTINCT primary_link.feature_id), 0), 1)
         AS link_rate_pct
FROM tracked_repositories tr
JOIN feature_to_repo primary_link
  ON primary_link.repo_id = tr.id AND primary_link.role = 'primary'
LEFT JOIN feature_to_repo backend_link
  ON backend_link.feature_id = primary_link.feature_id
 AND backend_link.role = 'backend'
WHERE tr.org_id = :org_id
  AND tr.repo_layer = 'frontend'
GROUP BY tr.tech_stack
ORDER BY link_rate_pct DESC NULLS LAST;
"""


# Row shape returned by ``_SNAPSHOT_SQL``:
#   (tech_stack, repos, features_owned, features_linked, link_rate_pct)
SnapshotRow = tuple[str | None, int, int, int, float | None]


async def _snapshot(org_id: uuid.UUID) -> list[SnapshotRow]:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(text(_SNAPSHOT_SQL), {"org_id": str(org_id)})
        return [(r[0], r[1], r[2], r[3], r[4]) for r in rows.all()]


def _print_table(title: str, rows: list[SnapshotRow]) -> None:
    print(f"\n=== {title} ===")
    print(f"{'tech_stack':<14} {'repos':>6} {'owned':>7} {'linked':>7} {'rate%':>7}")
    print("-" * 46)
    for tech, repos, owned, linked, rate in rows:
        rate_str = f"{rate:.1f}" if rate is not None else "—"
        print(f"{(tech or '?'):<14} {repos:>6} {owned:>7} {linked:>7} {rate_str:>7}")


async def _resolve_org_id(arg: str | None) -> uuid.UUID:
    if arg:
        return uuid.UUID(arg)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Organization.id).limit(1))
        row = result.scalar_one_or_none()
    if row is None:
        raise SystemExit("no organizations in local DB — run setup first")
    return row


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", default=None)
    parser.add_argument(
        "--snapshot-only",
        action="store_true",
        help="Print the by-tech_stack link table and exit; do NOT re-run the phase.",
    )
    args = parser.parse_args()

    org_id = await _resolve_org_id(args.org_id)
    print(f"org_id: {org_id}")

    before = await _snapshot(org_id)
    _print_table("BEFORE", before)

    if args.snapshot_only:
        return 0

    scan_id = uuid.uuid4()
    print(f"\nrunning backend_link phase (synthetic scan_id={scan_id}) …")
    counters = await run_backend_link(org_id=org_id, scan_id=scan_id)
    print("phase counters:")
    for k, v in counters.items():
        print(f"  {k:<24} {v}")

    after = await _snapshot(org_id)
    _print_table("AFTER", after)

    # Highlight movement.
    before_map = {row[0]: row for row in before}
    moved = []
    for row in after:
        tech, _repos, owned, linked, rate = row
        b = before_map.get(tech)
        if b is None or b[3] != linked:
            moved.append((tech, b[3] if b else 0, linked, owned, rate))
    if moved:
        print("\n=== MOVEMENT ===")
        for tech, b_linked, a_linked, owned, rate in moved:
            delta = a_linked - b_linked
            sign = "+" if delta >= 0 else ""
            rate_str = f"{rate:.1f}" if rate is not None else "—"
            print(
                f"{(tech or '?'):<14} linked: {b_linked} -> {a_linked} "
                f"({sign}{delta}) of {owned} owned, rate {rate_str}%"
            )
    else:
        print("\nno tech_stack saw a change in features_linked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
