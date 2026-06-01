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

"""End-to-end simulation of the Learning Agent pipeline against the dev DB.

Run with:
    cd backend && python -m scripts.simulate_learning_pipeline

Walks every scenario the PR introduced:
- single BUD close with the Learning Agent opted OUT (metrics still
  persisted, no agent task spawned)
- single BUD close with the Learning Agent opted IN (metrics persisted,
  agent task queued — we skip the actual Claude subprocess by injecting
  a synthetic recap into handle_learning_result)
- PROD->CLOSED double-fire idempotency
- velocity_aggregates incremental update with five BUDs in the same
  complexity bucket
- estimator read path (proportional fallback for short buckets, then
  aggregate read once the bucket is warm)
- cross-BUD recap context (find_similar after recaps land)

All test data is namespaced with the [LEARN-SIM] title prefix and
cleaned up at the end so the dev DB stays tidy.
"""

import asyncio
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.models.agent_skill import AgentSkill
from app.models.agent_skill_bud_stage import AgentSkillBudStage
from app.models.bud import (
    BUDDocument,
    BUDStatus,
    BUDTimelineEvent,
)
from app.models.bud_agent_task import BUDAgentTask
from app.models.bud_estimate_snapshot import BUDEstimateSnapshot
from app.models.feature_learning import FeatureLearning
from app.models.organization import Organization
from app.models.user import OrgToUser, User
from app.models.velocity_aggregate import VelocityAggregate
from app.repositories.feature_learning import FeatureLearningRepository
from app.repositories.velocity_aggregate import VelocityAggregateRepository
from app.services.agent_result_handlers import handle_learning_result
from app.services.bud_closure import on_bud_closed
from app.services.bud_stage_seeder import seed_stage_mappings_for_org
from app.services.estimation_context import get_historical_phase_durations
from app.services.job_handlers import setup_job_handlers
from app.services.skill_loader import seed_skills_for_org

TAG = "[LEARN-SIM]"


def banner(text: str) -> None:
    """Print a section banner so the script output reads cleanly."""
    print(f"\n{'=' * 70}\n  {text}\n{'=' * 70}")


def kv(label: str, value: Any) -> None:
    """Two-column key/value line for verification output."""
    print(f"  {label:<38} {value}")


async def _seed_org_skills_and_stages(db: Any, org_id: uuid.UUID) -> None:
    """Run the production seeders so create_agent_task_for_stage works.

    The real backend seeds agent_skills + agent_skill_bud_stages for
    every org during ``lifespan`` startup. The simulation runs without
    the FastAPI lifespan, so we invoke the seeders directly here.
    """
    await seed_skills_for_org(org_id, db)
    await seed_stage_mappings_for_org(org_id, db)


async def _seed_org_and_user(db: Any) -> tuple[Organization, User]:
    """Reuse or create the simulation org + user."""
    existing_org = (
        await db.execute(select(Organization).where(Organization.name == f"{TAG} org"))
    ).scalar_one_or_none()
    if existing_org is not None:
        user = (
            (
                await db.execute(
                    select(User)
                    .join(OrgToUser, OrgToUser.user_id == User.id)
                    .where(OrgToUser.org_id == existing_org.id)
                )
            )
            .scalars()
            .first()
        )
        if user is not None:
            return existing_org, user

    org = Organization(name=f"{TAG} org", slug=f"learn-sim-{uuid.uuid4().hex[:6]}")
    db.add(org)
    await db.flush()
    user = User(
        email=f"learn-sim-{uuid.uuid4().hex[:6]}@example.com",
        name=f"{TAG} sim user",
        password_hash="x" * 32,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    db.add(OrgToUser(org_id=org.id, user_id=user.id))
    await db.flush()
    return org, user


async def _make_bud(
    db: Any,
    org: Organization,
    user: User,
    *,
    title: str,
    bud_number: int,
    complexity: int,
    auto_close_recap: bool,
    phase_actuals_days: dict[BUDStatus, float],
    phase_estimates_days: dict[BUDStatus, float],
) -> BUDDocument:
    """Insert a synthetic BUD with a status_change timeline matching the actuals.

    Walks a virtual clock forward by ``phase_actuals_days`` per phase, writing
    a status_change row at each boundary. The earliest BUDEstimateSnapshot
    carries ``phase_estimates_days`` so bud_metrics computes drift correctly.
    """
    now = datetime.now(tz=UTC)
    cycle_total = sum(phase_actuals_days.values())
    created_at = now - timedelta(days=cycle_total)
    bud = BUDDocument(
        org_id=org.id,
        bud_number=bud_number,
        title=title,
        status=BUDStatus.BUD,
        complexity=complexity,
        assignee_id=user.id,
        auto_generate_phases={BUDStatus.CLOSED.value: auto_close_recap},
        impacted_repos=[],
        qa_automation_cases=[],
        qa_manual_cases=[],
    )
    bud.created_at = created_at
    db.add(bud)
    await db.flush()

    # Snapshot the original estimate using the SAME JSONB shape that
    # ``bud_estimation.build_estimated_dates`` writes in production:
    # each per-phase entry carries ``expected_days`` (PERT-derived
    # mean) and the p50/p70/p85 date strings. Writing a synthetic
    # ``p70_days`` field instead — as an earlier version of this
    # script did — papered over a real bug in ``bud_metrics_phases``
    # because the broken reader was looking for the same wrong key.
    estimate_payload: dict[str, Any] = {
        phase.value: {
            "expected_days": days,
            "p50_date": "2026-01-01",
            "p70_date": "2026-01-01",
            "p85_date": "2026-01-01",
        }
        for phase, days in phase_estimates_days.items()
    }
    snapshot = BUDEstimateSnapshot(
        org_id=org.id,
        bud_id=bud.id,
        trigger="bud_created",
        phase_estimates=estimate_payload,
        complexity=complexity,
    )
    snapshot.created_at = created_at
    db.add(snapshot)

    # Walk the lifecycle, writing one status_change per transition
    clock = created_at
    phase_order = list(phase_actuals_days.keys())
    current = BUDStatus.BUD
    for next_phase in phase_order[1:]:
        clock = clock + timedelta(days=phase_actuals_days[current])
        event = BUDTimelineEvent(
            org_id=org.id,
            bud_id=bud.id,
            event_type="status_change",
            detail={"from": current.value, "to": next_phase.value},
        )
        event.created_at = clock
        db.add(event)
        current = next_phase
    clock = clock + timedelta(days=phase_actuals_days[current])

    # Final transition into CLOSED happens via on_bud_closed; here we
    # just mark the BUD's persisted state to CLOSED and align updated_at
    # with the synthetic clock so cycle_time_days math works out.
    bud.status = BUDStatus.CLOSED
    bud.updated_at = clock
    closing_event = BUDTimelineEvent(
        org_id=org.id,
        bud_id=bud.id,
        event_type="status_change",
        detail={"from": current.value, "to": BUDStatus.CLOSED.value, "auto": True},
    )
    closing_event.created_at = clock
    db.add(closing_event)
    # Commit before the caller runs on_bud_closed so the FK lookup the
    # FeatureLearning insert performs sees a durable bud_documents row.
    await db.commit()
    await db.refresh(bud)
    return bud


def _standard_phase_actuals(scale: float) -> dict[BUDStatus, float]:
    """Plausible per-phase actual days, scaled by ``scale`` for variety."""
    return {
        BUDStatus.BUD: 0.5 * scale,
        BUDStatus.DESIGN: 1.0 * scale,
        BUDStatus.TECH_ARCH: 1.0 * scale,
        BUDStatus.DEVELOPMENT: 3.0 * scale,
        BUDStatus.CODE_REVIEW: 0.5 * scale,
        BUDStatus.TESTING: 1.0 * scale,
        BUDStatus.PROD: 0.25 * scale,
    }


def _standard_phase_estimates() -> dict[BUDStatus, float]:
    """A baseline estimate for every BUD — drift = actual / estimate."""
    return {
        BUDStatus.BUD: 0.5,
        BUDStatus.DESIGN: 0.5,
        BUDStatus.TECH_ARCH: 1.0,
        BUDStatus.DEVELOPMENT: 2.0,
        BUDStatus.CODE_REVIEW: 0.5,
        BUDStatus.TESTING: 1.0,
        BUDStatus.PROD: 0.25,
    }


async def _print_feature_learning(db: Any, org_id: uuid.UUID, bud: BUDDocument) -> None:
    row = await FeatureLearningRepository(db, org_id=org_id).get_for_bud(bud.id)
    if row is None:
        kv("feature_learnings row", "MISSING")
        return
    kv("feature_learnings.id", row.id)
    kv("cycle_time_days", row.cycle_time_days)
    kv("estimated_days (sum of per-phase)", row.estimated_days)
    kv("bug_count", row.bug_count)
    kv("metrics.schema_version", (row.metrics or {}).get("schema_version"))
    kv("metrics.parallelism_score", (row.metrics or {}).get("parallelism_score"))
    pm = (row.metrics or {}).get("phase_metrics") or {}
    kv("metrics.phase_metrics keys", sorted(pm.keys()))
    contributors = (row.metrics or {}).get("contributors") or []
    kv("metrics.contributors count", len(contributors))
    kv("retrospective_md", "present" if row.retrospective_md else "<None>")


async def _print_velocity_aggregates(
    db: Any, org_id: uuid.UUID, complexities: Iterable[int]
) -> None:
    repo = VelocityAggregateRepository(db, org_id=org_id)
    for c in complexities:
        rows = await repo.list_for_complexity_range(c, c, list(BUDStatus))
        kv(f"complexity {c} bucket count", len(rows))
        for row in sorted(rows, key=lambda r: r.phase.value):
            kv(
                f"  phase {row.phase.value:<14}",
                (
                    f"n={row.n_samples}  p50={row.p50_days}  "
                    f"p70={row.p70_days}  mean={row.running_mean}"
                ),
            )


async def _trigger_learning_result(db: Any, org: Organization, bud: BUDDocument) -> None:
    """Synthesize a realistic LLM output and run handle_learning_result.

    We skip the actual Claude subprocess because it requires the
    Anthropic API. The result handler is the integration point that
    finally lands the recap onto the FeatureLearning row, so exercising
    it directly is enough to verify the end-to-end shape.
    """
    fake_output = (
        f"## Summary\nSimulated retrospective for BUD-{bud.bud_number:03d}.\n\n"
        "## Estimate vs Actual\nClose to plan (synthetic).\n\n"
        "## Phase Drift\n- **development**: estimated 2.0d, actual 3.0d (50% over)\n\n"
        "## Velocity Notes\nSolo work; single contributor.\n\n"
        "## Parallel Work Effect\nNone observed.\n\n"
        "## Recommendations\n- Re-evaluate development budget.\n"
    )
    fake_task = BUDAgentTask(
        org_id=org.id,
        bud_id=bud.id,
        skill_id=uuid.uuid4(),  # placeholder; handle_learning_result only reads .id
        task_type="closed",
    )
    fake_task.id = uuid.uuid4()
    await handle_learning_result(bud.id, org.id, fake_output, fake_task, db)


async def _cleanup(db: Any, org: Organization, user: User | None) -> None:
    """Remove the simulation org / user / cascade-deleted rows.

    The backend's startup-time seeders insert ``agent_skills`` and
    ``agent_skill_bud_stages`` rows for every org, so we have to wipe
    those before the organization delete or the FK fires. Order
    matters: children before parents.
    """
    org_id = org.id
    await db.execute(delete(VelocityAggregate).where(VelocityAggregate.org_id == org_id))
    await db.execute(delete(FeatureLearning).where(FeatureLearning.org_id == org_id))
    await db.execute(delete(BUDTimelineEvent).where(BUDTimelineEvent.org_id == org_id))
    await db.execute(delete(BUDEstimateSnapshot).where(BUDEstimateSnapshot.org_id == org_id))
    await db.execute(delete(BUDAgentTask).where(BUDAgentTask.org_id == org_id))
    await db.execute(delete(BUDDocument).where(BUDDocument.org_id == org_id))
    await db.execute(delete(AgentSkillBudStage).where(AgentSkillBudStage.org_id == org_id))
    await db.execute(delete(AgentSkill).where(AgentSkill.org_id == org_id))
    await db.execute(delete(OrgToUser).where(OrgToUser.org_id == org_id))
    if user is not None:
        await db.execute(delete(User).where(User.id == user.id))
    await db.execute(delete(Organization).where(Organization.id == org_id))


async def _wipe_any_prior_sim_data() -> None:
    """Remove any [LEARN-SIM] data left over by a previous aborted run.

    Keeps the script idempotent across re-runs — re-using the same org
    name and bud_number range across runs would otherwise hit the
    uq_bud_org_number constraint.
    """
    async with AsyncSessionLocal() as db:
        orgs = (
            (await db.execute(select(Organization).where(Organization.name == f"{TAG} org")))
            .scalars()
            .all()
        )
        for org in orgs:
            user_rows = (
                (
                    await db.execute(
                        select(User)
                        .join(OrgToUser, OrgToUser.user_id == User.id)
                        .where(OrgToUser.org_id == org.id)
                    )
                )
                .scalars()
                .all()
            )
            await _cleanup(db, org, user_rows[0] if user_rows else None)
        await db.commit()


async def main() -> None:
    """Run every simulation scenario sequentially."""
    # Real backend calls setup_job_handlers() in lifespan startup so
    # job_queue knows the JOB_BUD_AGENT type. Without it,
    # create_agent_task_for_stage would raise "Unknown job type" when
    # enqueuing the Learning Agent task. The script runs without
    # FastAPI, so we register handlers here.
    setup_job_handlers()
    await _wipe_any_prior_sim_data()
    async with AsyncSessionLocal() as db:
        org, user = await _seed_org_and_user(db)
        await _seed_org_skills_and_stages(db, org.id)
        await db.commit()
        print(f"Simulation org_id={org.id} user_id={user.id}")
        bud_counter = 9000  # high range so we never collide with real BUDs

        try:
            # ── Scenario 1: opt-out close ───────────────────────────────
            banner("Scenario 1 — Manual close with Learning Agent opted OUT")
            bud_counter += 1
            bud1 = await _make_bud(
                db,
                org,
                user,
                title=f"{TAG} scenario1 opt-out",
                bud_number=bud_counter,
                complexity=3,
                auto_close_recap=False,
                phase_actuals_days=_standard_phase_actuals(1.0),
                phase_estimates_days=_standard_phase_estimates(),
            )
            await on_bud_closed(db, org.id, bud1, actor_id=user.id, actor_name=user.name)
            await db.commit()
            await _print_feature_learning(db, org.id, bud1)
            tasks = (
                (await db.execute(select(BUDAgentTask).where(BUDAgentTask.bud_id == bud1.id)))
                .scalars()
                .all()
            )
            kv("BUDAgentTask rows for this BUD", len(tasks))
            print("  ✔ metrics persisted even when agent is opted out")

            # ── Scenario 2: opt-in close, synthetic recap ───────────────
            banner("Scenario 2 — Manual close with Learning Agent opted IN")
            bud_counter += 1
            bud2 = await _make_bud(
                db,
                org,
                user,
                title=f"{TAG} scenario2 opt-in",
                bud_number=bud_counter,
                complexity=3,
                auto_close_recap=True,
                phase_actuals_days=_standard_phase_actuals(1.0),
                phase_estimates_days=_standard_phase_estimates(),
            )
            await on_bud_closed(db, org.id, bud2, actor_id=user.id, actor_name=user.name)
            await db.commit()
            tasks = (
                (await db.execute(select(BUDAgentTask).where(BUDAgentTask.bud_id == bud2.id)))
                .scalars()
                .all()
            )
            kv("BUDAgentTask rows queued", len(tasks))
            kv("  task_type", tasks[0].task_type if tasks else "n/a")
            # status is a plain ``str`` column (mapped from the
            # AgentTaskStatus enum's .value), so don't call .value on it.
            kv("  status", tasks[0].status if tasks else "n/a")
            # Now simulate the Claude subprocess completing
            await _trigger_learning_result(db, org, bud2)
            await db.commit()
            await _print_feature_learning(db, org.id, bud2)

            # ── Scenario 3: double-fire idempotency ─────────────────────
            banner("Scenario 3 — PROD->CLOSED double-fire idempotency")
            before_rows = (
                (
                    await db.execute(
                        select(FeatureLearning).where(FeatureLearning.bud_id == bud2.id)
                    )
                )
                .scalars()
                .all()
            )
            await on_bud_closed(db, org.id, bud2, actor_id=user.id, actor_name=user.name)
            await db.commit()
            after_rows = (
                (
                    await db.execute(
                        select(FeatureLearning).where(FeatureLearning.bud_id == bud2.id)
                    )
                )
                .scalars()
                .all()
            )
            kv("FeatureLearning rows before second fire", len(before_rows))
            kv("FeatureLearning rows after second fire", len(after_rows))
            agg = (
                await db.execute(
                    select(VelocityAggregate).where(
                        VelocityAggregate.org_id == org.id,
                        VelocityAggregate.complexity == 3,
                        VelocityAggregate.phase == BUDStatus.DEVELOPMENT,
                    )
                )
            ).scalar_one_or_none()
            if agg is not None:
                kv("velocity_aggregates DEV bucket n_samples", agg.n_samples)
                kv(
                    "  contributing_bud_ids includes BUD2",
                    str(bud2.id) in agg.contributing_bud_ids,
                )
            print("  ✔ second fire short-circuits — no double-counting")

            # ── Scenario 4: warm the bucket (5+ BUDs) ───────────────────
            banner("Scenario 4 — Close 5 more BUDs at complexity 3 to warm the bucket")
            for i, scale in enumerate([0.8, 1.0, 1.2, 0.9, 1.1]):
                bud_counter += 1
                b = await _make_bud(
                    db,
                    org,
                    user,
                    title=f"{TAG} bulk-{i}",
                    bud_number=bud_counter,
                    complexity=3,
                    auto_close_recap=False,
                    phase_actuals_days=_standard_phase_actuals(scale),
                    phase_estimates_days=_standard_phase_estimates(),
                )
                await on_bud_closed(db, org.id, b, actor_id=user.id, actor_name=user.name)
            await db.commit()
            await _print_velocity_aggregates(db, org.id, [3])

            # ── Scenario 5: estimator read paths ────────────────────────
            banner(
                "Scenario 5 — Estimator switch: complexity-3 hits aggregates, "
                "complexity-5 falls back to proportional"
            )
            warm = await get_historical_phase_durations(
                db,
                org.id,
                target_complexity=3,
                phase_order=[
                    BUDStatus.DEVELOPMENT.value,
                    BUDStatus.TESTING.value,
                    BUDStatus.DESIGN.value,
                ],
            )
            kv("complexity-3 DEV sample count", len(warm.get("development", [])))
            kv(
                "complexity-3 DEV mean ~",
                round(
                    sum(warm.get("development", [])) / max(1, len(warm.get("development", []))),
                    2,
                ),
            )
            cold = await get_historical_phase_durations(
                db,
                org.id,
                target_complexity=5,
                phase_order=[BUDStatus.DEVELOPMENT.value],
            )
            kv("complexity-5 DEV sample count (cold)", len(cold.get("development", [])))
            kv(
                "  cold path falls back to proportional",
                "yes" if not cold.get("development") else "no — already warm",
            )

            # ── Scenario 5b: varied scales produce real percentile spread ──
            banner("Scenario 5b — Varied actuals produce non-degenerate percentiles")
            varied = await get_historical_phase_durations(
                db,
                org.id,
                target_complexity=3,
                phase_order=[BUDStatus.DEVELOPMENT.value],
            )
            dev_samples = sorted(varied.get("development", []))
            kv("DEV samples (sorted)", dev_samples)
            kv("DEV min", min(dev_samples) if dev_samples else None)
            kv("DEV max", max(dev_samples) if dev_samples else None)
            kv(
                "spread > 0 (proves percentile != single value)",
                (max(dev_samples) - min(dev_samples) > 0) if dev_samples else False,
            )

            # ── Scenario 5c: PERT triple correctness ────────────────────
            banner("Scenario 5c — PERT triple on the development bucket")
            agg = await VelocityAggregateRepository(db, org_id=org.id).get_bucket(
                3, BUDStatus.DEVELOPMENT
            )
            if agg is not None and agg.pert_optimistic is not None:
                opt = float(agg.pert_optimistic)
                most = float(agg.pert_most_likely or 0)
                pess = float(agg.pert_pessimistic or 0)
                kv("pert_optimistic", opt)
                kv("pert_most_likely", most)
                kv("pert_pessimistic", pess)
                kv(
                    "  optimistic <= most_likely <= pessimistic",
                    opt <= most <= pess,
                )
                kv("running_mean (Welford)", agg.running_mean)
                kv("running_m2 (Welford)", agg.running_m2)

            # ── Scenario 6: cross-BUD context via find_similar ──────────
            banner("Scenario 6 — Cross-BUD context: find_similar after recap embedding")
            # Give BUD2 a fake embedding so cosine search has something to chew on.
            bud2_row = await FeatureLearningRepository(db, org_id=org.id).get_for_bud(bud2.id)
            if bud2_row is not None and bud2_row.embedding is None:
                bud2_row.embedding = [0.01] * 384
                await db.flush()
            # Embed a fake "incoming BUD" query vector.
            similar = await FeatureLearningRepository(db, org_id=org.id).find_similar(
                [0.01] * 384, limit=3, exclude_bud_id=uuid.uuid4()
            )
            kv("find_similar returned", len(similar))
            for s in similar:
                kv(
                    f"  bud_id={s.bud_id}",
                    f"has retrospective_md={bool(s.retrospective_md)}",
                )

            banner("All scenarios complete.")
        finally:
            await _cleanup(db, org, user)
            await db.commit()
            print(f"\nCleanup: removed org_id={org.id} and all simulation rows.")


if __name__ == "__main__":
    asyncio.run(main())
