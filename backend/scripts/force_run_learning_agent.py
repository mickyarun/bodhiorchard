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

"""Force-spawn the Learning Agent for an already-closed BUD.

Usage:
    cd backend && python -m scripts.force_run_learning_agent <bud_number>

Bypasses the ``auto_generate_phases.closed`` opt-in gate for orgs whose
BUDs were created before that toggle existed. Confirms the org has the
``bud_status="closed"`` stage mapping (seeding it if missing), removes
any prior ``learning_recorded`` event so the new run isn't an
amnesiac no-op, then calls ``create_agent_task_for_stage`` exactly the
way ``on_bud_closed`` would. The actual Claude subprocess is picked
up by the running JOB_BUD_AGENT worker pool — this script does NOT
need to keep running once the task row is committed.

The script does NOT re-run ``compute_and_persist`` (the metrics
envelope already exists for closed BUDs). If you want fresh metrics
plus a fresh recap, run ``scripts.reprocess_bud_learning <n>`` first
and then this script.
"""

import asyncio
import sys
from typing import Any

from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.bud import BUDDocument, BUDTimelineEvent
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.repositories.agent_skill_bud_stage import AgentSkillBudStageRepository
from app.repositories.feature_learning import FeatureLearningRepository
from app.services.bud_agent_handler import handle_bud_agent_job
from app.services.bud_agent_trigger import create_agent_task_for_stage
from app.services.bud_stage_seeder import seed_stage_mappings_for_org
from app.services.job_handlers import setup_job_handlers
from app.services.skill_loader import seed_skills_for_org


def banner(text: str) -> None:
    """Print a section banner so the output reads cleanly."""
    print(f"\n{'=' * 70}\n  {text}\n{'=' * 70}")


def kv(label: str, value: Any) -> None:
    """Two-column key/value line."""
    print(f"  {label:<38} {value}")


async def _ensure_closed_stage_mapping(db: Any, org_id: Any) -> None:
    """Seed agent_skills + agent_skill_bud_stages if they're missing for this org.

    The startup seeders run in FastAPI lifespan, so a long-lived dev
    backend already has these rows. But running this script standalone
    against a fresh org would otherwise fail at the
    ``get_for_status('closed')`` lookup.
    """
    stage_repo = AgentSkillBudStageRepository(db, org_id=org_id)
    mappings = await stage_repo.get_for_status("closed")
    if mappings:
        kv("bud_status=closed mapping", f"present ({len(mappings)} row(s))")
        return
    print("  bud_status=closed mapping missing — seeding now")
    await seed_skills_for_org(org_id, db)
    await seed_stage_mappings_for_org(org_id, db)
    await db.flush()


async def _clear_prior_learning_event(db: Any, bud: BUDDocument) -> None:
    """Wipe the previous ``learning_recorded`` event so a re-run is observable.

    The recap itself in ``feature_learnings.retrospective_md`` will be
    overwritten in place by ``handle_learning_result`` — no separate
    cleanup needed there.
    """
    await db.execute(
        delete(BUDTimelineEvent).where(
            BUDTimelineEvent.org_id == bud.org_id,
            BUDTimelineEvent.bud_id == bud.id,
            BUDTimelineEvent.event_type == "learning_recorded",
        )
    )
    await db.flush()


async def force_run(bud_number: int) -> None:
    """Look up the BUD and spawn the Learning Agent task for it."""
    setup_job_handlers()
    async with AsyncSessionLocal() as db:
        bud = (
            await db.execute(select(BUDDocument).where(BUDDocument.bud_number == bud_number))
        ).scalar_one_or_none()
        if bud is None:
            print(f"BUD-{bud_number} not found.")
            return

        banner(f"Force-running Learning Agent for BUD-{bud.bud_number}")
        kv("title", bud.title)
        kv("status", bud.status.value)
        kv("org_id", bud.org_id)
        kv("complexity", bud.complexity)

        # Make sure the metrics envelope already exists — the prompt
        # builder will inline ``{ '_warning': 'metrics envelope missing' }``
        # otherwise, which results in a thin, useless recap.
        existing = await FeatureLearningRepository(db, org_id=bud.org_id).get_for_bud(bud.id)
        if existing is None or not existing.metrics:
            print(
                "  ! No feature_learnings.metrics envelope for this BUD. Run "
                "``scripts.reprocess_bud_learning`` first so the agent has "
                "structured metrics to read."
            )
            return
        kv("feature_learnings present", "yes")
        kv("metrics envelope populated", "yes")
        kv("existing retrospective_md", "present" if existing.retrospective_md else "<None>")

        await _ensure_closed_stage_mapping(db, bud.org_id)
        await _clear_prior_learning_event(db, bud)

        # Cancel any half-finished prior agent task on this BUD so the
        # ``active_task_exists`` guard inside create_agent_task_for_stage
        # doesn't block the re-run. Only touch task_type='closed' rows.
        active_q = await db.execute(
            select(BUDAgentTask).where(
                BUDAgentTask.org_id == bud.org_id,
                BUDAgentTask.bud_id == bud.id,
                BUDAgentTask.task_type == "closed",
                BUDAgentTask.status.in_([AgentTaskStatus.PENDING, AgentTaskStatus.RUNNING]),
            )
        )
        for stale in active_q.scalars().all():
            stale.status = AgentTaskStatus.FAILED
            stale.error_message = "superseded by force_run_learning_agent"
        await db.flush()

        await create_agent_task_for_stage(
            bud,
            "closed",
            bud.org_id,
            db,
            triggered_by=bud.assignee_id,
        )

        # Re-fetch so we can report the row that just landed
        fresh = await db.execute(
            select(BUDAgentTask)
            .where(
                BUDAgentTask.bud_id == bud.id,
                BUDAgentTask.task_type == "closed",
            )
            .order_by(BUDAgentTask.created_at.desc())
            .limit(1)
        )
        task = fresh.scalar_one_or_none()
        if task is None:
            print(
                "  ! create_agent_task_for_stage did not create a task. The "
                "most likely cause is that the org has no 'closed' stage "
                "mapping and the seeders are also failing — check the "
                "process logs for warnings like 'stage mapping skill not "
                "found'."
            )
            return
        banner("Agent task created")
        kv("task.id", task.id)
        kv("task.task_type", task.task_type)
        kv("task.status", task.status)
        kv("task.attempt", task.attempt)
        kv("task.job_id", task.job_id)
        kv("task.skill_id", task.skill_id)
        task_id_str = str(task.id)
        org_id_str = str(bud.org_id)
        bud_id_str = str(bud.id)
        job_id_str = task.job_id or ""

    # The job_queue is process-local (an in-memory dict in
    # ``app.services.job_queue``). The dev backend can't see jobs
    # queued by this script. Drive ``handle_bud_agent_job`` inline so
    # the Claude subprocess runs in *this* process and writes the
    # recap directly. The bud_agent_handler opens its own session, so
    # we exit the outer ``async with AsyncSessionLocal()`` block before
    # invoking it.
    if not job_id_str:
        print("\n  ! task.job_id is empty — handler dispatch would 404. Aborting.")
        return
    banner("Running handle_bud_agent_job inline — Claude subprocess starts now")
    payload = {
        "org_id": org_id_str,
        "bud_id": bud_id_str,
        "task_id": task_id_str,
    }
    await handle_bud_agent_job(job_id_str, payload)
    banner("handle_bud_agent_job returned — inspect the recap below")
    async with AsyncSessionLocal() as db:
        refreshed = await FeatureLearningRepository(db, org_id=bud.org_id).get_for_bud(bud.id)
        if refreshed is None:
            print("  ! feature_learnings row disappeared (unexpected).")
            return
        kv("retrospective_md set", refreshed.retrospective_md is not None)
        if refreshed.retrospective_md:
            preview = refreshed.retrospective_md[:600].replace("\n", "\n  ")
            print("\n  ─── recap preview ──────────────────────────────")
            print(f"  {preview}")
            if len(refreshed.retrospective_md) > 600:
                print(f"  … ({len(refreshed.retrospective_md) - 600} more chars)")


def main() -> None:
    """CLI entry point — parses bud_number from argv."""
    if len(sys.argv) < 2:
        print("usage: python -m scripts.force_run_learning_agent <bud_number>")
        sys.exit(1)
    try:
        bud_number = int(sys.argv[1])
    except ValueError:
        print(f"bud_number must be an integer, got {sys.argv[1]!r}")
        sys.exit(1)
    asyncio.run(force_run(bud_number))


if __name__ == "__main__":
    main()
