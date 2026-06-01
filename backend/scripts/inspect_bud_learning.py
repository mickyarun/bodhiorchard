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

"""Inspect the post-close Learning Agent state for a specific BUD.

Run with:
    cd backend && python -m scripts.inspect_bud_learning <bud_number>

Reports every row the Learning Agent pipeline should have written:
feature_learnings, velocity_aggregates buckets for the BUD's complexity,
BUDAgentTask rows for task_type=closed, and the matching timeline
events. Read-only — never mutates anything.
"""

import asyncio
import sys
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.bud import BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.bud_agent_task import BUDAgentTask
from app.models.feature_learning import FeatureLearning
from app.models.velocity_aggregate import VelocityAggregate


def banner(text: str) -> None:
    """Print a section banner so the output reads cleanly."""
    print(f"\n{'=' * 70}\n  {text}\n{'=' * 70}")


def kv(label: str, value: Any) -> None:
    """Two-column key/value line."""
    print(f"  {label:<38} {value}")


async def inspect(bud_number: int) -> None:
    """Print the full Learning Agent state for the given BUD number."""
    async with AsyncSessionLocal() as db:
        bud_result = await db.execute(
            select(BUDDocument).where(BUDDocument.bud_number == bud_number)
        )
        buds = list(bud_result.scalars().all())
        if not buds:
            print(f"No BUD with bud_number={bud_number} found.")
            return
        if len(buds) > 1:
            print(
                f"WARNING: {len(buds)} BUDs share bud_number={bud_number}. Reporting all of them."
            )

        for bud in buds:
            banner(f"BUD-{bud.bud_number:03d} — {bud.title}")
            kv("bud_id", bud.id)
            kv("org_id", bud.org_id)
            kv("status", bud.status.value)
            kv("complexity", bud.complexity)
            kv("created_at", bud.created_at)
            kv("updated_at", bud.updated_at)
            kv("assignee_id", bud.assignee_id)
            kv("auto_generate_phases", bud.auto_generate_phases)
            kv(
                "auto_generate_phases.closed",
                (bud.auto_generate_phases or {}).get(BUDStatus.CLOSED.value),
            )

            # ── FeatureLearning ────────────────────────────────────
            banner(f"feature_learnings for BUD-{bud.bud_number:03d}")
            fl_result = await db.execute(
                select(FeatureLearning).where(
                    FeatureLearning.org_id == bud.org_id,
                    FeatureLearning.bud_id == bud.id,
                )
            )
            fl_rows = list(fl_result.scalars().all())
            kv("row count", len(fl_rows))
            for fl in fl_rows:
                kv("  id", fl.id)
                kv("  cycle_time_days", fl.cycle_time_days)
                kv("  estimated_days", fl.estimated_days)
                kv("  bug_count", fl.bug_count)
                kv("  retrospective_md", "present" if fl.retrospective_md else "<None>")
                kv(
                    "  retrospective_md preview",
                    (fl.retrospective_md or "")[:300].replace("\n", " "),
                )
                kv("  embedding", "set (384d)" if fl.embedding is not None else "<None>")
                if fl.metrics:
                    kv("  metrics.schema_version", fl.metrics.get("schema_version"))
                    kv(
                        "  metrics.original_estimated_days",
                        fl.metrics.get("original_estimated_days"),
                    )
                    kv("  metrics.parallelism_score", fl.metrics.get("parallelism_score"))
                    pm = fl.metrics.get("phase_metrics") or {}
                    kv("  metrics.phase_metrics phases", sorted(pm.keys()))
                    for phase_name, entry in sorted(pm.items()):
                        if not isinstance(entry, dict):
                            continue
                        actual = entry.get("actual_days")
                        estimated = entry.get("estimated_days")
                        drift = entry.get("drift_pct")
                        kv(
                            f"    {phase_name:<14}",
                            (f"actual={actual}  estimated={estimated}  drift={drift}%"),
                        )
                    contributors = fl.metrics.get("contributors") or []
                    kv("  metrics.contributors count", len(contributors))
                    for c in contributors[:5]:
                        if not isinstance(c, dict):
                            continue
                        kv(
                            f"    {c.get('name', '?'):<14}",
                            (
                                f"commits={c.get('commits')}  "
                                f"prs={c.get('prs_merged')}  "
                                f"todos={c.get('todos_completed')}  "
                                f"days={c.get('active_days')}"
                            ),
                        )
                else:
                    kv("  metrics", "<None>  (envelope NOT populated — pipeline didn't run)")
                kv("  created_at", fl.created_at)
                kv("  updated_at", fl.updated_at)

            # ── BUDAgentTask ───────────────────────────────────────
            banner(f"BUDAgentTask (task_type=closed) for BUD-{bud.bud_number:03d}")
            task_result = await db.execute(
                select(BUDAgentTask)
                .where(
                    BUDAgentTask.org_id == bud.org_id,
                    BUDAgentTask.bud_id == bud.id,
                )
                .order_by(BUDAgentTask.created_at.desc())
            )
            tasks = list(task_result.scalars().all())
            kv("total agent tasks for this BUD", len(tasks))
            for task in tasks:
                if task.task_type != "closed":
                    continue
                kv("  task.id", task.id)
                kv("  task.status", task.status)
                kv("  task.task_type", task.task_type)
                kv("  task.attempt", task.attempt)
                kv("  task.job_id", task.job_id)
                kv("  task.created_at", task.created_at)
                kv("  task.result_summary", task.result_summary)
                kv(
                    "  task.error_message",
                    (task.error_message or "")[:200] if task.error_message else "<None>",
                )

            # ── Timeline events ────────────────────────────────────
            banner(f"Recent timeline events for BUD-{bud.bud_number:03d}")
            ev_result = await db.execute(
                select(BUDTimelineEvent)
                .where(
                    BUDTimelineEvent.org_id == bud.org_id,
                    BUDTimelineEvent.bud_id == bud.id,
                )
                .order_by(BUDTimelineEvent.created_at.desc())
                .limit(20)
            )
            events = list(ev_result.scalars().all())
            for ev in events:
                kv(
                    f"  {ev.created_at.isoformat()}",
                    f"{ev.event_type}  detail_keys={list((ev.detail or {}).keys())}",
                )
            learning_events = [e for e in events if e.event_type == "learning_recorded"]
            kv("learning_recorded event count", len(learning_events))

            # ── velocity_aggregates for this BUD's complexity ──────
            if bud.complexity is not None:
                banner(f"velocity_aggregates for org × complexity={bud.complexity}")
                agg_result = await db.execute(
                    select(VelocityAggregate).where(
                        VelocityAggregate.org_id == bud.org_id,
                        VelocityAggregate.complexity == bud.complexity,
                    )
                )
                aggs = sorted(
                    agg_result.scalars().all(),
                    key=lambda a: a.phase.value,
                )
                kv("bucket count", len(aggs))
                for agg in aggs:
                    contributes = str(bud.id) in (agg.contributing_bud_ids or [])
                    kv(
                        f"  phase {agg.phase.value:<14}",
                        (
                            f"n={agg.n_samples}  p50={agg.p50_days}  "
                            f"p70={agg.p70_days}  mean={agg.running_mean}  "
                            f"this_bud_counted={contributes}"
                        ),
                    )


def main() -> None:
    """CLI entry point — parses bud_number from argv."""
    if len(sys.argv) < 2:
        print("usage: python -m scripts.inspect_bud_learning <bud_number>")
        sys.exit(1)
    try:
        bud_number = int(sys.argv[1])
    except ValueError:
        print(f"bud_number must be an integer, got {sys.argv[1]!r}")
        sys.exit(1)
    asyncio.run(inspect(bud_number))


if __name__ == "__main__":
    main()
