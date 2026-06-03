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

"""Backfill ``pull_requests.bud_id`` using the broadened resolver.

Usage:
    cd backend && python -m scripts.backfill_pr_bud_links [--dry-run] [--include-merged]

Background. Before the title-aware resolver landed, ``bud_id`` was only
set when the head branch matched ``bud-NNN/``. PRs whose author tagged
the BUD in the title (``[BUD-008] Fix Y``) but not the branch stayed
orphaned, so the release-stage views (UAT / PROD) leaned on a fallback
``or_(bud_id == X, repo_id IN impacted)`` predicate that over-matched
unrelated PRs. After this script runs, every orphan PR whose title or
head ref carries a BUD number is correctly linked and the three-way
predicate in ``list_open_for_bud_with_repo`` can do its job cleanly.

Defaults to **open PRs only** (``--include-merged`` opt-in). Setting
``bud_id`` on a merged PR does not directly re-fire ``_handle_pr_closed``
— that runs only from a fresh webhook — but the next pass of
``detect_release_promotion`` walks the SHA→BUD map and can fire
**new** ``merged_to_{stage}`` timeline events plus auto-close any BUD
previously orphaned in the release chain. XP guards are idempotent on
``source_ref`` (so no double-award), but the new timeline events and
status flips are real side-effects an operator should consent to.

The script is idempotent: it never overwrites an existing ``bud_id``.
Every successful backfill writes a ``pr_backfilled`` timeline event on
the BUD so the change is auditable.
"""

import argparse
import asyncio
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.pull_request import PRState, PullRequest
from app.repositories.bud import BUDRepository
from app.services.bud_timeline import record_event
from app.services.pr_auto_transition import extract_bud_number


async def _select_targets(db: AsyncSession, *, include_merged: bool) -> list[PullRequest]:
    """Return PR rows that are candidates for backfill.

    Filters out PRs that already have ``bud_id``. When ``include_merged``
    is False, also filters out non-open PRs so a one-shot backfill on a
    long-lived deployment doesn't retroactively change the SHA→BUD map
    used by release detection.
    """
    stmt = select(PullRequest).where(PullRequest.bud_id.is_(None))
    if not include_merged:
        stmt = stmt.where(PullRequest.state == PRState.OPEN)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _resolve_bud_id(
    db: AsyncSession,
    org_id: uuid.UUID,
    head_ref: str | None,
    title: str | None,
) -> tuple[uuid.UUID | None, int | None]:
    """Match a PR's head ref then title against existing BUDs in the org.

    Returns ``(bud_id, bud_number)`` or ``(None, None)``. Uses the same
    extractor as the webhook handler so the on-line and backfill paths
    can never drift on which strings count as a BUD reference.
    """
    bud_repo = BUDRepository(db, org_id=org_id)
    for source in (head_ref, title):
        bud_number = extract_bud_number(source)
        if bud_number is None:
            continue
        bud = await bud_repo.get_by_number(bud_number)
        if bud is not None:
            return bud.id, bud.bud_number
    return None, None


def _format_row(pr: PullRequest, bud_number: int | None) -> str:
    return (
        f"  pr#{pr.github_pr_number or '?':>5} "
        f"state={pr.state.value:<7} "
        f"head={(pr.head_branch or '')[:40]:<40} "
        f"title={(pr.title or '')[:50]:<50} "
        f"→ BUD-{bud_number}"
    )


async def _backfill(prs: Iterable[PullRequest], *, dry_run: bool) -> dict[str, int]:
    """Walk candidate PRs and write ``bud_id`` for those that resolve.

    Each successful write is paired with a ``pr_backfilled`` timeline
    event on the BUD so the audit trail records that the link wasn't set
    by a fresh GitHub webhook. Dry-run mode prints would-be mappings and
    commits nothing.
    """
    stats = {"scanned": 0, "matched": 0, "written": 0, "skipped_no_org": 0}
    async with AsyncSessionLocal() as db:
        for pr in prs:
            stats["scanned"] += 1
            org_id = pr.org_id
            if org_id is None:
                stats["skipped_no_org"] += 1
                continue
            bud_id, bud_number = await _resolve_bud_id(db, org_id, pr.head_branch, pr.title)
            if bud_id is None:
                continue
            stats["matched"] += 1
            print(_format_row(pr, bud_number))
            if dry_run:
                continue
            db_pr = await db.get(PullRequest, pr.id)
            if db_pr is None or db_pr.bud_id is not None:
                continue
            db_pr.bud_id = bud_id
            await record_event(
                db,
                org_id,
                bud_id,
                "pr_backfilled",
                detail={
                    "pr_number": pr.github_pr_number,
                    "head_branch": pr.head_branch,
                    "title": pr.title,
                    "source": "backfill_pr_bud_links",
                },
            )
            await db.commit()
            stats["written"] += 1
    return stats


async def _main(*, dry_run: bool, include_merged: bool, assume_yes: bool) -> None:
    print("PR ↔ BUD backfill")
    print(f"  dry_run        = {dry_run}")
    print(f"  include_merged = {include_merged}")
    print()

    # Runtime confirmation gate. The --help text explains the side effect,
    # but an operator chaining commands could miss it; an explicit prompt
    # forces a conscious "yes" before merged PRs get linked.
    if include_merged and not dry_run:
        print(
            "WARNING: --include-merged will write bud_id onto already-merged PRs.\n"
            "  The next release-detection pass walks the SHA→BUD map and may fire\n"
            "  new ``merged_to_{stage}`` timeline events and auto-close BUDs that\n"
            "  were previously orphaned in the release chain. XP awards are\n"
            "  idempotent on source_ref, but timeline and status side-effects are\n"
            "  real. Run with --dry-run first to inspect the diff.\n"
        )
        if not assume_yes:
            answer = input("Type CONFIRM to proceed: ").strip()
            if answer != "CONFIRM":
                print("Aborted.")
                return

    async with AsyncSessionLocal() as db:
        targets = await _select_targets(db, include_merged=include_merged)
    print(f"Candidate PRs (bud_id IS NULL): {len(targets)}")
    if not targets:
        return

    stats = await _backfill(targets, dry_run=dry_run)
    print()
    print(f"Scanned:         {stats['scanned']}")
    print(f"Matched a BUD:   {stats['matched']}")
    print(f"Written to DB:   {stats['written']}")
    if stats["skipped_no_org"]:
        print(f"Skipped (no org): {stats['skipped_no_org']}")
    if dry_run:
        print("\nDry run — no rows changed. Re-run without --dry-run to apply.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print would-be mappings without writing. Recommended first pass.",
    )
    parser.add_argument(
        "--include-merged",
        action="store_true",
        help=(
            "Also backfill already-merged PRs. Opt-in because the next release-"
            "detection pass can fire new merged_to_{stage} events and auto-close "
            "previously-orphaned BUDs based on the new SHA→BUD map."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        dest="assume_yes",
        help="Skip the CONFIRM prompt when --include-merged is set.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        _main(
            dry_run=args.dry_run,
            include_merged=args.include_merged,
            assume_yes=args.assume_yes,
        )
    )
