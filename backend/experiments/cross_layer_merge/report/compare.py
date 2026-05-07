# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Before/after stats for the cross-layer merge sandbox.

Run after ``verify`` to see what changed. Prints to stdout — eyeball
the merge log and tune the prompt until the right rows merge for the
right reasons (and the wrong rows stay separate).
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from experiments.cross_layer_merge.schema import (
    XLMKnowledgeItem,
    XLMKnowledgeRepoLink,
    XLMPairLog,
    XLMPairPlan,
    XLMPairStatus,
)


@dataclass
class ReportStats:
    """Summary numbers printed at the top of the report."""

    active_ki_count: int
    inactive_ki_count: int
    multi_repo_ki_count: int
    pairs_done: int
    pairs_failed: int
    total_merges: int


async def collect_stats() -> ReportStats:
    """Aggregate counts across the sandbox tables."""
    async with AsyncSessionLocal() as session:
        active_ki = (
            await session.execute(
                select(func.count(XLMKnowledgeItem.id)).where(XLMKnowledgeItem.is_active.is_(True))
            )
        ).scalar_one()
        inactive_ki = (
            await session.execute(
                select(func.count(XLMKnowledgeItem.id)).where(
                    XLMKnowledgeItem.is_active.is_(False)
                )
            )
        ).scalar_one()

        multi_repo = (
            await session.execute(
                select(func.count()).select_from(
                    select(XLMKnowledgeRepoLink.knowledge_id)
                    .group_by(XLMKnowledgeRepoLink.knowledge_id)
                    .having(func.count(XLMKnowledgeRepoLink.repo_id) >= 2)
                    .subquery()
                )
            )
        ).scalar_one()

        pairs_done = (
            await session.execute(
                select(func.count(XLMPairPlan.id)).where(XLMPairPlan.status == XLMPairStatus.DONE)
            )
        ).scalar_one()
        pairs_failed = (
            await session.execute(
                select(func.count(XLMPairPlan.id)).where(
                    XLMPairPlan.status == XLMPairStatus.FAILED
                )
            )
        ).scalar_one()
        total_merges = (
            await session.execute(select(func.coalesce(func.sum(XLMPairPlan.merged_count), 0)))
        ).scalar_one()

    return ReportStats(
        active_ki_count=active_ki,
        inactive_ki_count=inactive_ki,
        multi_repo_ki_count=multi_repo,
        pairs_done=pairs_done,
        pairs_failed=pairs_failed,
        total_merges=total_merges,
    )


async def collect_merge_log() -> list[dict[str, Any]]:
    """Return one row per Claude verdict, ordered chronologically."""
    async with AsyncSessionLocal() as session:
        rows = (
            (await session.execute(select(XLMPairLog).order_by(XLMPairLog.created_at)))
            .scalars()
            .all()
        )
        return [
            {
                "action": r.action,
                "rationale": r.rationale,
                "source_synth_id": str(r.source_synth_id),
                "candidates": [str(c) for c in r.candidate_synth_ids],
                "absorbed": [str(c) for c in r.absorbed_synth_ids],
            }
            for r in rows
        ]


async def render_report() -> str:
    """Format stats + merge log as a single human-readable string."""
    stats = await collect_stats()
    log_rows = await collect_merge_log()

    multi_repo_pct = (
        (stats.multi_repo_ki_count / stats.active_ki_count * 100) if stats.active_ki_count else 0.0
    )

    lines = [
        "=== Cross-Layer Merge Sandbox Report ===",
        f"Active KIs:         {stats.active_ki_count}",
        f"Deactivated KIs:    {stats.inactive_ki_count}  (absorbed by merges)",
        f"Multi-repo KIs:     {stats.multi_repo_ki_count}  ({multi_repo_pct:.1f}%)",
        f"Pairs DONE:         {stats.pairs_done}",
        f"Pairs FAILED:       {stats.pairs_failed}",
        f"Total merges:       {stats.total_merges}",
        "",
        "=== Merge log ===",
    ]
    if not log_rows:
        lines.append("(no Claude verdicts recorded — run `verify` first)")
    for r in log_rows:
        action = r["action"]
        rat = r["rationale"] or ""
        if action == "merge":
            lines.append(
                f"  MERGE: source={r['source_synth_id'][:8]} "
                f"absorbed={[a[:8] for a in r['absorbed']]}  — {rat}"
            )
        else:
            lines.append(f"  no_match: source={r['source_synth_id'][:8]}  — {rat}")

    return "\n".join(lines)
