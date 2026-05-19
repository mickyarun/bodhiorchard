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

"""BUD CRUD endpoints and sub-router aggregation."""

import uuid
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.bud_chat import router as chat_router
from app.api.v1.bud_designs import router as designs_router
from app.api.v1.bud_estimates import router as estimates_router
from app.api.v1.bud_linked_features import router as linked_features_router
from app.api.v1.bud_prs import router as prs_router
from app.api.v1.bud_qa import router as qa_router
from app.api.v1.bud_todos import router as todos_router
from app.api.v1.bud_workflows import router as workflows_router
from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud import BUDDesignStatus, BUDDocument, BUDStatus, BUDTimelineEvent
from app.models.user import User
from app.repositories.agent_activity import AgentActivityLogRepository
from app.repositories.bud import BUDDesignRepository, BUDRepository
from app.repositories.bud_agent_task import BUDAgentTaskRepository
from app.repositories.bud_timeline import BUDTimelineRepository
from app.repositories.bug import BugRepository
from app.schemas.bud import (
    BUDAgentTaskRead,
    BUDCreate,
    BUDListItem,
    BUDRead,
    BUDUpdate,
    TimelineEventRead,
)
from app.schemas.bud_code_review import (
    CodeReviewOverrideRequest,
    CodeReviewRepoStatus,
    CodeReviewStatusResponse,
)
from app.schemas.bud_constants import EXPORTABLE_SECTIONS
from app.schemas.bud_design import BUDDesignRead
from app.schemas.dev_activity import (
    CommitRepoRead,
    ContributorRead,
    DevActivityRead,
    DevActivityResponse,
    DevCommitRead,
    DevStatsRead,
    UntrackedRepoRead,
)
from app.services.agent_activity_logger import PHASE_WORKER_SLUGS
from app.services.agent_task_cancel import (
    AgentTaskCancelError,
    cancel_task,
    is_task_terminal,
)
from app.services.bud_edit_policy import assert_section_editable

logger = structlog.get_logger(__name__)


async def _persist_stage_skill_overrides(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    overrides: dict[BUDStatus, uuid.UUID],
) -> None:
    """Validate then store per-stage skill picks for one BUD.

    Each ``skill_id`` must (a) belong to the caller's org and (b) have
    the correct ``agent_type`` for the stage it's being assigned to —
    e.g. picking a ``design`` skill for the ``testing`` stage is
    rejected with 400.
    """
    from app.agents.skill_mapping import BUD_STAGE_AGENT_TYPE
    from app.repositories.agent_skill import AgentSkillRepository
    from app.repositories.bud_stage_skill_override import (
        BUDStageSkillOverrideRepository,
    )

    skill_repo = AgentSkillRepository(db, org_id=org_id)

    for stage, skill_id in overrides.items():
        expected_agent_type = BUD_STAGE_AGENT_TYPE.get(stage)
        if expected_agent_type is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stage '{stage.value}' is not configurable",
            )
        skill = await skill_repo.get_by_id(skill_id)
        if skill is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Skill {skill_id} not found for stage {stage.value}",
            )
        if skill.agent_type != expected_agent_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Skill {skill.skill_slug!r} (agent_type={skill.agent_type.value}) "
                    f"cannot be assigned to stage {stage.value}; that stage runs the "
                    f"{expected_agent_type.value} agent."
                ),
            )

    override_repo = BUDStageSkillOverrideRepository(db, org_id=org_id)
    await override_repo.bulk_set_for_bud(bud_id, overrides)


async def _bud_response(
    bud: BUDDocument,
    org_id: uuid.UUID,
    db: AsyncSession,
) -> BUDRead:
    """Build BUDRead with active (or last-failed) agent task attached."""
    task_repo = BUDAgentTaskRepository(db, org_id=org_id)
    active_task = await task_repo.get_active_for_bud(bud.id)
    if not active_task:
        # Only show last-failed if no completed task exists after it (i.e. retry succeeded)
        failed = await task_repo.get_latest_failed(bud.id)
        if failed:
            completed = await task_repo.get_latest_completed(bud.id)
            if not completed or completed.created_at < failed.created_at:
                active_task = failed

    # `updated_at` has an ``onupdate=func.now()`` server default that
    # SQLAlchemy doesn't include in INSERT…RETURNING, so on a freshly
    # inserted BUD the attribute is "not loaded". Pydantic's sync
    # validator would then trigger a lazy SELECT — which can't spawn a
    # greenlet from sync context and raises MissingGreenlet. An explicit
    # refresh inside the async context eager-loads every column before
    # validation, and also picks up anything later phases (auto-assign,
    # agent-task creation) mutated on the same row.
    await db.refresh(bud)

    bud_data = BUDRead.model_validate(bud)
    if active_task:
        bud_data.active_agent_task = BUDAgentTaskRead.model_validate(active_task)

    # ``BUDDesignRead`` declares ``repo_name`` but the ORM model has no
    # column or relationship for it — ``from_attributes`` would leave
    # it None. Refetch designs via the JOIN-backed list so the per-repo
    # banners and chat-panel dropdown can render the actual repo name
    # instead of falling back to "default". Skip the extra query when
    # the BUD has no design rows (every non-design phase, plus design
    # phase before the user clicks "Add").
    if bud.designs:
        design_repo = BUDDesignRepository(db, org_id=org_id)
        design_rows = await design_repo.list_with_repo_names(bud.id)
        bud_data.designs = [BUDDesignRead.model_validate(row) for row in design_rows]

    # Re-attach the phase-progress banner for synthetic workers (assignment
    # / todo-gen / estimation) that don't have BUDAgentTask rows. Without
    # this the banner only catches events that fire AFTER mount, so the
    # whole chain is invisible if the user navigates away and back.
    # Uses the single source of truth ``PHASE_WORKER_SLUGS`` from
    # agent_activity_logger so adding a new worker touches exactly one
    # list.
    activity_repo = AgentActivityLogRepository(db, org_id=org_id)
    active_phase = await activity_repo.get_active_phase_worker(bud.id, PHASE_WORKER_SLUGS)
    if active_phase is not None:
        bud_data.active_phase_worker = {
            "skill_slug": active_phase.skill_slug or "",
            "message": active_phase.message or "",
        }

    # Sticky failure banner: most recent skill_failed newer than the
    # user's dismissal timestamp. Covers the restart-recovery and
    # missed-WS-event cases without any client-side reconnect logic —
    # if the failure happened, the next BUD load surfaces it; the user
    # dismisses, the column updates, the banner is gone for good.
    latest_failure = await activity_repo.get_latest_skill_failed(
        bud.id,
        skill_slugs=PHASE_WORKER_SLUGS,
        since=bud.phase_failure_acknowledged_at,
    )
    if latest_failure is not None:
        bud_data.last_phase_failure = {
            "skill_slug": latest_failure.skill_slug or "",
            "message": latest_failure.message or "",
            "failed_at": latest_failure.created_at.isoformat()
            if latest_failure.created_at
            else None,
            "metadata": latest_failure.metadata_ or {},
        }
    return bud_data


router = APIRouter(tags=["buds"])

# ── Sub-routers ───────────────────────────────────────────────────
router.include_router(designs_router, prefix="/{bud_id}/designs", tags=["bud-designs"])
router.include_router(estimates_router, prefix="/{bud_id}", tags=["bud-estimates"])
router.include_router(
    linked_features_router,
    prefix="/{bud_id}/linked-features",
    tags=["bud-linked-features"],
)
router.include_router(prs_router, tags=["bud-prs"])
router.include_router(qa_router, prefix="/{bud_id}/qa", tags=["bud-qa"])
router.include_router(workflows_router, prefix="/{bud_id}", tags=["bud-workflows"])
router.include_router(chat_router, prefix="/{bud_id}", tags=["bud-chat"])
router.include_router(todos_router, tags=["bud-todos"])


# ── CRUD ──────────────────────────────────────────────────────────


@router.get(
    "/",
    response_model=list[BUDListItem],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_buds(
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BUDDocument]:
    """List BUDs for the current user's organization."""
    if status_filter:
        try:
            BUDStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            ) from None

    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    buds = await bud_repo.list_buds(status_filter=status_filter)

    # Batch-fetch open bug counts for all BUDs in one query
    bug_repo = BugRepository(db, org_id=current_user.org_id)
    bug_counts = await bug_repo.open_bug_counts_by_bud([b.id for b in buds])

    # Inject open_bug_count as a transient attribute so Pydantic's
    # from_attributes picks it up alongside the ORM columns.
    for b in buds:
        b.open_bug_count = bug_counts.get(b.id, 0)  # type: ignore[attr-defined]
    return buds


@router.post(
    "/",
    response_model=BUDRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("buds:create"))],
)
async def create_bud(
    body: BUDCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDRead:
    """Create a new BUD with auto-incremented bud_number."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    next_number = await bud_repo.next_bud_number()

    bud = BUDDocument(
        org_id=current_user.org_id,
        bud_number=next_number,
        title=body.title,
        status=BUDStatus.BUD,
        requirements_md=body.requirements_md,
        metadata_=body.metadata_,
    )
    await bud_repo.create(bud)

    # Persist per-BUD stage skill overrides (Advanced settings on create).
    # Validates that each (stage, skill_id) pair points at a skill whose
    # agent_type matches the stage's expected agent — wrong picks get a
    # 400 instead of silently routing to the wrong skill at run-time.
    if body.stage_skill_overrides:
        await _persist_stage_skill_overrides(
            db,
            current_user.org_id,
            bud.id,
            body.stage_skill_overrides,
        )

    # Generate embedding so the bug linker can match bugs to this BUD.
    # Fast (~50ms) and done inline so the embedding is available immediately.
    try:
        from app.services.embedding_service import embedding_service

        embed_text = body.title
        if body.requirements_md:
            embed_text = f"{body.title} {body.requirements_md[:500]}"
        bud.embedding = await embedding_service.embed(embed_text)
        await db.flush()
    except Exception:
        logger.warning("bud_embedding_failed", bud_number=next_number, exc_info=True)

    from app.services.feature_lifecycle import create_planned_feature

    await create_planned_feature(
        db,
        current_user.org_id,
        next_number,
        body.title,
        body.requirements_md or "",
    )

    # Record timeline + auto-assign
    from app.services.bud_assignment import auto_assign_for_phase
    from app.services.bud_timeline import record_event

    await record_event(
        db,
        current_user.org_id,
        bud.id,
        "created",
        actor_id=current_user.id,
        actor_name=current_user.name,
        detail={"source": "web"},
    )
    await auto_assign_for_phase(
        db,
        current_user.org_id,
        bud,
        BUDStatus.BUD,
        actor_id=current_user.id,
        actor_name=current_user.name,
    )

    logger.info("bud_created", bud_id=str(bud.id), bud_number=next_number, org_id=str(bud.org_id))

    # Auto-trigger PM agent, same as the Slack approval flow
    from app.services.bud_agent_trigger import create_agent_task_for_stage

    await create_agent_task_for_stage(
        bud,
        "bud",
        current_user.org_id,
        db,
        triggered_by=current_user.id,
        force=True,
    )

    # Estimation deferred — triggers after PRD agent completes (via agent_result_handlers)

    return await _bud_response(bud, current_user.org_id, db)


@router.get(
    "/{bud_id}",
    response_model=BUDRead,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_bud(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDRead:
    """Retrieve a single BUD by ID, including active agent task."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    return await _bud_response(bud, current_user.org_id, db)


@router.get(
    "/{bud_id}/timeline",
    response_model=list[TimelineEventRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_bud_timeline(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BUDTimelineEvent]:
    """Fetch timeline events for a BUD in chronological order."""
    repo = BUDTimelineRepository(db, org_id=current_user.org_id)
    return await repo.list_for_bud(bud_id)


@router.get(
    "/{bud_id}/stage-skill-overrides",
    response_model=dict[BUDStatus, uuid.UUID],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_stage_skill_overrides(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[BUDStatus, uuid.UUID]:
    """Return the per-stage skill overrides set on this BUD.

    Used by the BUD detail page's "Skills" dialog to render the current
    pinned skill for each stage (so the user can see what they previously
    picked, plus the default for stages they didn't override).
    """
    from app.repositories.bud_stage_skill_override import (
        BUDStageSkillOverrideRepository,
    )

    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    override_repo = BUDStageSkillOverrideRepository(db, org_id=current_user.org_id)
    rows = await override_repo.list_for_bud(bud_id)
    return {row.bud_status: row.skill_id for row in rows}


@router.put(
    "/{bud_id}/stage-skill-overrides",
    response_model=dict[BUDStatus, uuid.UUID],
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def set_stage_skill_overrides(
    bud_id: uuid.UUID,
    body: dict[BUDStatus, uuid.UUID],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[BUDStatus, uuid.UUID]:
    """Replace the BUD's per-stage skill overrides in one shot.

    The body is the *full* desired map of stage → skill_id. Stages not
    present in the body are cleared — that way the same call shape works
    for "I added an override", "I changed one", and "I cleared one back
    to the org default". Each (stage, skill) pair is validated against
    the stage's expected agent type before persisting.
    """
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    await _persist_stage_skill_overrides(db, current_user.org_id, bud_id, body)
    await db.commit()

    logger.info(
        "bud_stage_skill_overrides_updated",
        bud_id=str(bud_id),
        org_id=str(current_user.org_id),
        count=len(body),
    )
    return body


@router.patch(
    "/{bud_id}",
    response_model=BUDRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def update_bud(
    bud_id: uuid.UUID,
    body: BUDUpdate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDRead:
    """Update a BUD (title, status, requirements, tech spec, test plan, metadata)."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    update_data = body.model_dump(exclude_unset=True)
    update_data.pop("status_override_reason", None)  # consumed separately, not a model field

    if "status" in update_data:
        try:
            update_data["status"] = BUDStatus(update_data["status"])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {update_data['status']}",
            ) from None

    # Guard: closed/discarded BUDs cannot be reopened. Placed before ANY
    # side-effect-producing code (transition_feature_for_bud, assignments)
    # so a rejected request never mutates state.
    if "status" in update_data and bud.status in (BUDStatus.CLOSED, BUDStatus.DISCARDED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot change status of a {bud.status.value} BUD. Create a new BUD instead."
            ),
        )

    # Guard: leaving the design phase while wireframe generation is still
    # in flight produces a phase-overlap state where the design task and
    # the next-phase task are both active. The per-design cancel path
    # walks ``get_active_for_bud`` and can write terminal state to the
    # wrong task in that window. Block the transition until every
    # ``bud_designs`` row is out of ``generating``. Discard is exempt —
    # abandoning the BUD entirely is a legitimate escape hatch.
    if (
        "status" in update_data
        and bud.status == BUDStatus.DESIGN
        and update_data["status"] not in (BUDStatus.DESIGN, BUDStatus.DISCARDED)
    ):
        design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
        in_flight = await design_repo.count_by_status(bud.id, BUDDesignStatus.GENERATING)
        if in_flight > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"{in_flight} wireframe{'s' if in_flight > 1 else ''} still generating — "
                    "cancel them or wait for completion before advancing the phase."
                ),
            )

    # Phase-edit policy: section-owning fields are only writable while the
    # BUD is in their owning phase. Frontend mirrors this rule in
    # SECTION_EDIT_STATUS; backend rejects with HTTP 409 here as
    # defense-in-depth against direct API calls.
    for field in update_data:
        assert_section_editable(bud, field)

    if "status" in update_data:
        from app.services.feature_lifecycle import transition_feature_for_bud

        await transition_feature_for_bud(
            db,
            current_user.org_id,
            bud.bud_number,
            update_data["status"],
        )

    # Capture old values BEFORE applying updates
    old_status = bud.status
    old_assignee_id = bud.assignee_id
    old_title = bud.title

    # Handle manual assignee_id changes (before status logic which may auto-assign)
    if "assignee_id" in update_data:
        from app.services.bud_assignment import assign_bud, unassign_bud

        new_aid = update_data.pop("assignee_id")
        if new_aid and new_aid != old_assignee_id:
            await assign_bud(
                db,
                current_user.org_id,
                bud,
                new_aid,
                current_user.id,
                current_user.name,
            )
        elif not new_aid and old_assignee_id:
            await unassign_bud(
                db,
                current_user.org_id,
                bud,
                current_user.id,
                current_user.name,
            )

    # Record status change + auto-assign
    if "status" in update_data:
        new_status = update_data["status"]

        # Manual code_review → testing:
        # If every impacted repo has a merged PR, this is the same as the
        # webhook-driven auto-transition — no bypass, no reason needed.
        # Only require a reason when the user is genuinely bypassing the
        # PR-merge gate (e.g. docs-only changes, manual merges).
        if old_status == BUDStatus.CODE_REVIEW and new_status == BUDStatus.TESTING:
            from app.services.bud_code_review_status import get_pr_status_summary

            repo_statuses = await get_pr_status_summary(db, current_user.org_id, bud)
            all_merged = bool(repo_statuses) and all(
                r["pr_state"] == "merged" for r in repo_statuses
            )

            if not all_merged:
                reason = body.status_override_reason
                if not reason or not reason.strip():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Reason required when manually advancing to testing",
                    )
                from app.services.bud_timeline import record_event as _record

                await _record(
                    db,
                    current_user.org_id,
                    bud.id,
                    "status_override",
                    actor_id=current_user.id,
                    actor_name=current_user.name,
                    detail={
                        "from": old_status.value,
                        "to": "testing",
                        "reason": reason.strip(),
                    },
                )

        # Manual testing → uat (or prod when UAT is disabled):
        # QA is only "done" when every manual test case has a terminal
        # result — pass / fail / blocked / skipped. Advancing past testing
        # while any case is still pending would bury real work in an
        # un-triaged state. Skipped counts as terminal because it's an
        # explicit tester decision ("not applicable"), unlike pending
        # which means "never looked at".
        #
        # This guard intentionally catches testing → prod even when UAT
        # IS enabled in the org config — a user manually jumping past UAT
        # still needs QA to have signed off on every case. Closing from
        # testing is NOT blocked: closed means "abandoning this BUD",
        # not "shipping it", so forcing every pending case to be resolved
        # would be friction rather than safety.
        if old_status == BUDStatus.TESTING and new_status in (
            BUDStatus.UAT,
            BUDStatus.PROD,
        ):
            pending_cases = [
                tc
                for tc in (bud.qa_manual_cases or [])
                if isinstance(tc, dict) and tc.get("result") == "pending"
            ]
            if pending_cases:
                pending_ids = [str(tc.get("id", "?")) for tc in pending_cases[:5]]
                more = len(pending_cases) - len(pending_ids)
                suffix = f" and {more} more" if more > 0 else ""
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Cannot advance to {new_status.value}: "
                        f"{len(pending_cases)} manual test case"
                        f"{'s' if len(pending_cases) != 1 else ''} still pending "
                        f"({', '.join(pending_ids)}{suffix}). "
                        f"Mark each as pass, fail, blocked, or skipped in the QA tab first."
                    ),
                )

        from app.services.bud_assignment import auto_assign_for_phase
        from app.services.bud_timeline import record_event

        await record_event(
            db,
            current_user.org_id,
            bud.id,
            "status_change",
            actor_id=current_user.id,
            actor_name=current_user.name,
            detail={"from": old_status.value, "to": new_status.value},
        )

        # Apply the status before the side effects so downstream hooks
        # and assignment policy see the correct phase.
        if old_status != BUDStatus.DEVELOPMENT and new_status == BUDStatus.DEVELOPMENT:
            bud.status = new_status

        # auto_assign_for_phase sets ``bud.assignee_id`` — must run before
        # the dev-transition hook so the hook can assign newly-synced
        # TODOs to that lead in the same transaction.
        await auto_assign_for_phase(
            db,
            current_user.org_id,
            bud,
            new_status,
            actor_id=current_user.id,
            actor_name=current_user.name,
        )

        # Same dev-transition side effects fired by approve_tech_arch — see
        # backend/app/services/bud_development.py. Synchronously parses
        # the tech spec into BUDTodo rows + assigns to the lead; spawns
        # a background task for PERT estimation.
        if old_status != BUDStatus.DEVELOPMENT and new_status == BUDStatus.DEVELOPMENT:
            from app.services.bud_development import on_bud_development_started

            await on_bud_development_started(
                db,
                current_user.org_id,
                bud,
                actor_id=current_user.id,
                actor_name=current_user.name,
            )

    # Record title change
    if "title" in update_data and update_data["title"] != old_title:
        from app.services.bud_timeline import record_event

        await record_event(
            db,
            current_user.org_id,
            bud.id,
            "content_updated",
            actor_id=current_user.id,
            actor_name=current_user.name,
            detail={"section": "title", "old_title": old_title, "new_title": update_data["title"]},
        )

    old_tech_spec_md = bud.tech_spec_md if "tech_spec_md" in update_data else None

    for field, value in update_data.items():
        setattr(bud, field, value)

    await db.flush()
    await db.refresh(bud)

    # If the developer edited tech_spec_md on a DEVELOPMENT-phase BUD,
    # refresh the Implementation TODO section (LLM patch when the diff
    # extends beyond the section) and re-derive BUDTodo rows. The
    # reconciler preserves in-flight developer work.
    if "tech_spec_md" in update_data and update_data["tech_spec_md"] != old_tech_spec_md:
        from app.services.tech_planner_patch import apply_tech_spec_edit

        # apply_tech_spec_edit mutates ``bud.tech_spec_md`` in place when
        # the patch flow rewrites the section, so the caller's commit
        # persists it without a second write here. ``sync_todos_for_bud``
        # already flushes newly-inserted BUDTodo rows.
        await apply_tech_spec_edit(
            bud=bud,
            old_spec=old_tech_spec_md,
            new_spec=update_data["tech_spec_md"],
            db=db,
            org_id=current_user.org_id,
        )

    # Award XP for BUD completion (prod or closed with assignee)
    if "status" in update_data:
        _completed = update_data["status"] in (BUDStatus.PROD, BUDStatus.CLOSED)
        if _completed and bud.assignee_id and old_status not in (BUDStatus.PROD, BUDStatus.CLOSED):
            try:
                from app.services.xp_service import award_quality_bonus, award_xp

                await award_xp(
                    db,
                    user_id=bud.assignee_id,
                    org_id=current_user.org_id,
                    amount=50,
                    source="bud_completed",
                    source_ref=f"bud:{bud.bud_number}",
                )
                await award_quality_bonus(
                    db,
                    user_id=bud.assignee_id,
                    org_id=current_user.org_id,
                    bud_id=bud.id,
                )
            except Exception:
                logger.warning("xp_award_failed_bud_completion", exc_info=True)

        # Post-closure side-effects: award contributor XP + trigger scan
        if _completed:
            try:
                from app.services.bud_closure import on_bud_closed

                await on_bud_closed(
                    db,
                    current_user.org_id,
                    bud,
                    actor_id=current_user.id,
                    actor_name=current_user.name,
                )
            except Exception:
                logger.warning("bud_closure_side_effects_failed", exc_info=True)

    logger.info("bud_updated", bud_id=str(bud.id), fields=list(update_data.keys()))

    # Trigger side-effect jobs on status transitions
    await _trigger_status_jobs(bud, old_status, update_data, response, current_user, db)

    return await _bud_response(bud, current_user.org_id, db)


async def _trigger_status_jobs(
    bud: BUDDocument,
    old_status: BUDStatus,
    update_data: dict[str, Any],
    response: Response,
    current_user: User,
    db: AsyncSession,
) -> None:
    """Enqueue agent jobs for status transitions using stage mappings.

    Looks up the agent_skill_bud_stages table to find which agent
    should run for the new status. Creates a BUDAgentTask row and
    enqueues a JOB_BUD_AGENT job with a standardized payload.
    """
    if "status" not in update_data:
        return

    new_status = update_data["status"]

    # Design phase: only prompt for generation if no designs exist yet
    if new_status == BUDStatus.DESIGN and old_status != BUDStatus.DESIGN:
        has_designs = bud.designs and any(d.status == "ready" for d in bud.designs)
        if not has_designs:
            response.headers["X-Design-Available"] = "true"

    # Data-driven agent triggering via stage mappings
    if new_status != old_status:
        from app.services.bud_agent_trigger import create_agent_task_for_stage

        # Skip the code review agent if there are no open PRs. The agent's
        # only purpose is to post automated feedback to open PRs — if every
        # impacted repo has a merged PR (tester rejected from testing) or no
        # PR raised yet (developer hasn't pushed), there's nothing to post to.
        # The BUD still transitions to code_review status; the agent just
        # doesn't run until a PR appears (webhook-driven).
        if new_status == BUDStatus.CODE_REVIEW:
            from app.services.bud_code_review_status import get_pr_status_summary

            repo_statuses = await get_pr_status_summary(db, current_user.org_id, bud)
            has_open_pr = any(r["pr_state"] == "open" for r in repo_statuses)
            if not has_open_pr:
                logger.info(
                    "code_review_agent_skip_no_open_prs",
                    bud_id=str(bud.id),
                    from_status=str(old_status),
                    pr_states=[r["pr_state"] for r in repo_statuses],
                )
                return

        # When entering testing: if test cases already exist from a previous
        # run, skip the QA agent (no need to regenerate). If they're empty
        # (previous run failed or produced nothing), force-run the agent
        # despite test_plan_md being populated (test_plan_md is just a
        # summary string like "0 automation + 0 manual" which the content-
        # exists guard in create_agent_task_for_stage would treat as "done").
        if new_status == BUDStatus.TESTING:
            has_cases = bool(bud.qa_automation_cases or bud.qa_manual_cases)
            if has_cases:
                logger.info(
                    "testing_agent_skip_cases_exist",
                    bud_id=str(bud.id),
                    auto_count=len(bud.qa_automation_cases or []),
                    manual_count=len(bud.qa_manual_cases or []),
                )
                return
            # No test cases yet — force the agent to run even if
            # test_plan_md has stale content from a previous empty run.
            await create_agent_task_for_stage(
                bud,
                str(new_status),
                current_user.org_id,
                db,
                triggered_by=current_user.id,
                force=True,
            )
            return

        # Force re-run when going back to code_review from a later stage.
        # The list of valid "later stages" depends on whether this org uses
        # UAT — if UAT is disabled, the transition code_review → uat is
        # impossible, so including UAT here would be dead code. We gate it
        # with an explicit is_uat_enabled() check so the intent is visible
        # in the source (rather than silently relying on unreachability).
        from app.repositories.organization import OrganizationRepository
        from app.services.org_settings import is_uat_enabled

        org = await OrganizationRepository(db).get_by_id(current_user.org_id)
        force_from_stages: list[BUDStatus] = [BUDStatus.TESTING]
        if is_uat_enabled(org.config if org else None):
            force_from_stages.append(BUDStatus.UAT)
        force = new_status == BUDStatus.CODE_REVIEW and old_status in force_from_stages
        await create_agent_task_for_stage(
            bud,
            str(new_status),
            current_user.org_id,
            db,
            triggered_by=current_user.id,
            force=force,
        )

    # Re-estimate delivery dates in the background on UAT/Prod transitions.
    # Uses its own DB session so the request can return immediately — the
    # frontend polls estimates via the existing useEstimates composable.
    if "status" in update_data and update_data["status"] in (BUDStatus.UAT, BUDStatus.PROD):
        import asyncio

        task = asyncio.create_task(
            _bg_estimate(
                bud.id,
                current_user.org_id,
                update_data["status"].value,
                current_user.id,
                current_user.name,
            ),
            name=f"bg_estimate_{bud.id}_{update_data['status'].value}",
        )
        task.add_done_callback(
            lambda t: t.result() if not t.cancelled() and not t.exception() else None,
        )


async def _bg_estimate(
    bud_id: uuid.UUID,
    org_id: uuid.UUID,
    trigger: str,
    actor_id: uuid.UUID,
    actor_name: str,
) -> None:
    """Run estimation in the background with its own DB session."""
    from app.database import AsyncSessionLocal
    from app.services.bud_estimation import estimate_bud_dates

    try:
        async with AsyncSessionLocal() as db:
            from app.repositories.bud import BUDRepository

            bud_repo = BUDRepository(db, org_id=org_id)
            bud = await bud_repo.get_by_id(bud_id)
            if bud is None:
                return
            await estimate_bud_dates(
                db,
                org_id,
                bud,
                trigger=f"status_to_{trigger}",
                actor_id=actor_id,
                actor_name=actor_name,
            )
            await db.commit()
    except Exception:
        logger.warning(
            "bg_estimation_failed",
            bud_id=str(bud_id),
            trigger=trigger,
            exc_info=True,
        )


@router.get(
    "/{bud_id}/code-review/status",
    response_model=CodeReviewStatusResponse,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_code_review_status(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CodeReviewStatusResponse:
    """Return PR status + comment count per impacted repo for the Code Review tab."""
    from app.services.bud_code_review_status import get_last_run_status, get_pr_status_summary

    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if not bud:
        raise HTTPException(status_code=404, detail="BUD not found")

    rows = await get_pr_status_summary(db, current_user.org_id, bud)
    last_run_status, last_run_message = await get_last_run_status(db, current_user.org_id, bud_id)
    return CodeReviewStatusResponse(
        repos=[CodeReviewRepoStatus(**r) for r in rows],
        last_run_status=last_run_status,
        last_run_message=last_run_message,
    )


@router.post(
    "/{bud_id}/code-review/override",
    response_model=BUDRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def override_code_review(
    bud_id: uuid.UUID,
    payload: CodeReviewOverrideRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDRead:
    """Force-transition a BUD from code_review to testing with a user-supplied reason.

    Used when PR merges don't cover the case (docs-only changes, manual merges,
    exceptional escalations). Records the reason in the timeline and triggers
    the QA test-case agent. Blocked if an agent task is currently running on
    this BUD.
    """
    from app.services.bud_agent_trigger import create_agent_task_for_stage
    from app.services.bud_timeline import record_event

    # Row lock serializes concurrent override requests — the second caller
    # waits on the first's transaction to resolve, then sees status=testing
    # and fails the guard below.
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id_for_update(bud_id)
    if not bud:
        raise HTTPException(status_code=404, detail="BUD not found")
    if bud.status != BUDStatus.CODE_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"BUD is not in code_review status (current: {bud.status})",
        )

    task_repo = BUDAgentTaskRepository(db, org_id=current_user.org_id)
    if await task_repo.get_active_for_bud(bud_id):
        raise HTTPException(
            status_code=409,
            detail="Cannot override while an agent task is running",
        )

    old_status = str(bud.status)
    await record_event(
        db,
        current_user.org_id,
        bud_id,
        "code_review_override",
        detail={
            "reason": payload.reason,
            "from": old_status,
            "to": "testing",
            "triggered_by": str(current_user.id),
        },
    )
    await record_event(
        db,
        current_user.org_id,
        bud_id,
        "status_change",
        detail={"from": old_status, "to": "testing", "auto": False},
    )

    bud.status = BUDStatus.TESTING

    # Commit the override + status transition FIRST, as a durable record,
    # before attempting to spawn the follow-on testing task. This prevents
    # a silent rollback if create_agent_task_for_stage hits one of its
    # early-return guards or raises — the override audit trail is preserved
    # even if the testing task fails to spawn, and operators can retry task
    # creation separately.
    await db.commit()
    logger.info(
        "code_review_override_committed",
        bud_id=str(bud_id),
        triggered_by=str(current_user.id),
    )

    # Now spawn the testing agent task. Failures here don't undo the override.
    try:
        await create_agent_task_for_stage(
            bud,
            "testing",
            current_user.org_id,
            db,
            triggered_by=current_user.id,
            force=True,
        )
    except Exception:
        logger.exception(
            "code_review_override_testing_task_failed",
            bud_id=str(bud_id),
        )

    # Refresh estimates so dashboards reflect the new phase.
    try:
        from app.services.bud_estimation import estimate_bud_dates

        refreshed_for_est = await bud_repo.get_by_id(bud_id)
        if refreshed_for_est is not None:
            await estimate_bud_dates(
                db,
                current_user.org_id,
                refreshed_for_est,
                trigger="code_review_override",
            )
            await db.commit()
    except Exception:
        logger.warning(
            "code_review_override_estimation_failed",
            bud_id=str(bud_id),
        )

    refreshed = await bud_repo.get_by_id(bud_id)
    if refreshed is None:
        raise HTTPException(status_code=500, detail="BUD vanished after override")
    return await _bud_response(refreshed, current_user.org_id, db)


@router.post(
    "/{bud_id}/agent-tasks/{task_id}/cancel",
    response_model=BUDAgentTaskRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def cancel_agent_task(
    bud_id: uuid.UUID,
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDAgentTaskRead:
    """Cancel a pending/running agent task.

    Thin wrapper around :func:`app.services.agent_task_cancel`: this
    handler validates tenancy / state, then delegates the actual
    signal + DB cleanup to the service. The service raises
    :class:`AgentTaskCancelError` if signalling a live job fails;
    we translate that into a ``409`` so the user sees why their
    cancel didn't land.
    """
    task_repo = BUDAgentTaskRepository(db, org_id=current_user.org_id)
    task = await task_repo.get_by_id(task_id)
    if not task or task.bud_id != bud_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if is_task_terminal(task):
        return BUDAgentTaskRead.model_validate(task)

    try:
        updated = await cancel_task(
            db,
            org_id=current_user.org_id,
            task=task,
            reason=f"Cancelled by {current_user.email}",
        )
    except AgentTaskCancelError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Could not cancel: {exc}",
        ) from exc

    return BUDAgentTaskRead.model_validate(updated)


@router.post(
    "/{bud_id}/agent-tasks/{task_id}/retry",
    response_model=BUDAgentTaskRead,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def retry_agent_task(
    bud_id: uuid.UUID,
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDAgentTaskRead:
    """Retry a failed agent task, creating a new attempt.

    Args:
        bud_id: The BUD UUID.
        task_id: The failed task UUID.
        current_user: The authenticated user.
        db: Async database session.

    Returns:
        The new agent task (202 Accepted).
    """
    from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
    from app.schemas.jobs import BUDAgentTaskPayload
    from app.services.job_queue import JOB_BUD_AGENT, create_job

    task_repo = BUDAgentTaskRepository(db, org_id=current_user.org_id)

    # Verify the old task
    old_task = await task_repo.get_by_id(task_id)
    if not old_task or old_task.bud_id != bud_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if old_task.status != AgentTaskStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Only failed tasks can be retried"
        )

    # Guard: no concurrent active task
    active = await task_repo.get_active_for_bud(bud_id)
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Another task is already running"
        )

    # Create new task with incremented attempt
    new_task = BUDAgentTask(
        org_id=current_user.org_id,
        bud_id=bud_id,
        skill_id=old_task.skill_id,
        task_type=old_task.task_type,
        status=AgentTaskStatus.PENDING,
        attempt=old_task.attempt + 1,
        triggered_by=current_user.id,
    )
    db.add(new_task)
    await db.flush()

    # Route to the correct job handler based on task type
    if old_task.task_type == "design":
        from app.schemas.jobs import DesignAgentJobPayload
        from app.services.job_queue import JOB_DESIGN_AGENT

        bud_repo = BUDRepository(db, org_id=current_user.org_id)
        bud = await bud_repo.get_by_id(bud_id)
        if not bud:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

        design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
        designs = await design_repo.list_for_bud(bud_id)
        if not designs:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No design rows found. Use Generate instead of Retry.",
            )

        # Re-enqueue each failed/stuck design (same pattern as regenerate_design)
        first_job_id: str | None = None
        for design in designs:
            if design.status not in (BUDDesignStatus.FAILED, BUDDesignStatus.GENERATING):
                continue
            design.status = BUDDesignStatus.GENERATING

            payload = DesignAgentJobPayload(
                org_id=str(current_user.org_id),
                bud_id=str(bud_id),
                bud_number=bud.bud_number,
                title=bud.title,
                requirements_md=bud.requirements_md or "",
                repo_id=str(design.repo_id) if design.repo_id else None,
                design_id=str(design.id),
                skill_id=str(old_task.skill_id) if old_task.skill_id else None,
                task_id=str(new_task.id),
            )
            job = create_job(
                JOB_DESIGN_AGENT,
                payload=payload.model_dump(),
                user_id=str(current_user.id),
            )
            design.job_id = job.job_id
            if first_job_id is None:
                first_job_id = job.job_id

        if first_job_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No failed designs to retry.",
            )
        new_task.job_id = first_job_id
        new_task.status = AgentTaskStatus.RUNNING
        await db.commit()
        await db.refresh(new_task)
        return BUDAgentTaskRead.model_validate(new_task)
    else:
        job = create_job(
            JOB_BUD_AGENT,
            payload=BUDAgentTaskPayload(
                org_id=str(current_user.org_id),
                bud_id=str(bud_id),
                task_id=str(new_task.id),
            ).model_dump(),
            user_id=str(current_user.id),
        )

    new_task.job_id = job.job_id
    new_task.status = AgentTaskStatus.RUNNING

    # Single atomic commit — must happen before return so the worker can read the task
    await db.commit()
    await db.refresh(new_task)

    return BUDAgentTaskRead.model_validate(new_task)


@router.delete(
    "/{bud_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("backlog:delete"))],
)
async def delete_bud(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a BUD."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    from app.services.feature_lifecycle import transition_feature_for_bud

    await transition_feature_for_bud(
        db,
        current_user.org_id,
        bud.bud_number,
        BUDStatus.DISCARDED,
    )

    await bud_repo.delete(bud)
    logger.info("bud_deleted", bud_id=str(bud.id))


# ── Commit tracking ───────────────────────────────────────────────


@router.get(
    "/{bud_id}/commits/repos",
    response_model=list[CommitRepoRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_commit_repos(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CommitRepoRead]:
    """List repos with commits for a BUD, grouped by repo.

    Used by the frontend when transitioning to code_review to show
    a confirmation dialog of which repos have been touched.
    """
    from app.repositories.dev_activity import DevActivityLogRepository

    activity_repo = DevActivityLogRepository(db, org_id=current_user.org_id)
    summaries = await activity_repo.list_commit_repos_for_bud(bud_id)

    return [
        CommitRepoRead(
            repo_path=s.repo_path,
            repo_name=Path(s.repo_path).name,
            commit_count=s.commit_count,
            first_sha=s.first_sha,
            last_sha=s.last_sha,
        )
        for s in summaries
    ]


def _parse_files_changed(raw: str) -> list[str]:
    """Parse comma-separated files_changed string into a clean list."""
    return [f.strip() for f in raw.split(",") if f.strip()] if raw else []


# ── Development Activity ─────────────────────────────────────────


@router.get(
    "/{bud_id}/dev-activity",
    response_model=DevActivityResponse,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_dev_activity(
    bud_id: uuid.UUID,
    role: str | None = Query(
        None,
        description=(
            "Optional actor_role filter — only return rows where the "
            "committer's snapshotted role matches. Used by the BUD detail "
            "testing tab (role=qa). Mutually exclusive with exclude_role."
        ),
    ),
    exclude_role: str | None = Query(
        None,
        description=(
            "Optional actor_role anti-filter — only return rows where the "
            "committer's snapshotted role does NOT match (NULL roles are "
            "still included as fall-through). Used by the BUD detail dev "
            "tab (exclude_role=qa) when QA automation is enabled. Mutually "
            "exclusive with role."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DevActivityResponse:
    """Get development activity summary: commits, MCP updates, and stats.

    Optional ``role`` / ``exclude_role`` query params filter the activity
    by the committer's snapshotted ``actor_role`` (set on the dev_activity
    row at write time by the MCP push handler). The two are mutually
    exclusive — passing both is a 400.
    """
    if role is not None and exclude_role is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role and exclude_role are mutually exclusive",
        )

    from app.repositories.dev_activity import DevActivityLogRepository

    activity_repo = DevActivityLogRepository(db, org_id=current_user.org_id)
    task_repo = BUDAgentTaskRepository(db, org_id=current_user.org_id)

    # Sequential — AsyncSession is not safe for concurrent use.
    # Threading the role filter through every list method keeps the
    # activities / commits / repos / untracked_repos views in lockstep.
    commits = await activity_repo.list_commits_for_bud(
        bud_id, limit=50, role=role, exclude_role=exclude_role
    )
    activities = await activity_repo.list_for_bud(
        bud_id, limit=50, role=role, exclude_role=exclude_role
    )
    repo_summaries = await activity_repo.list_commit_repos_for_bud(
        bud_id, role=role, exclude_role=exclude_role
    )
    untracked_summaries = await activity_repo.list_untracked_repos_for_bud(
        bud_id, role=role, exclude_role=exclude_role
    )
    agent_tasks = await task_repo.list_for_bud(bud_id)

    # Count unique files across all commits
    all_files: set[str] = set()
    for c in commits:
        if c.files_changed:
            all_files.update(_parse_files_changed(c.files_changed))

    # Calculate AI effectiveness (data-driven, no separate commits list)
    from app.services.dev_stats import calculate_effectiveness

    eff = calculate_effectiveness(activities, agent_tasks)

    # Build commit reads with user_name resolved
    commit_user_ids = {c.user_id for c in commits if c.user_id}
    user_names: dict[uuid.UUID, str] = {}
    if commit_user_ids:
        from app.repositories.user import UserRepository

        user_repo = UserRepository(db)
        user_names = await user_repo.get_names_by_ids(commit_user_ids)

    # Batch-resolve repo_id → path in a single query
    from app.repositories.tracked_repository import TrackedRepoRepository

    repo_ids = {c.repo_id for c in commits if c.repo_id}
    repo_id_to_path: dict[uuid.UUID, str] = {}
    if repo_ids:
        repo_repo = TrackedRepoRepository(db, org_id=current_user.org_id)
        repo_id_to_path = await repo_repo.get_paths_by_ids(repo_ids)

    commit_reads = [
        DevCommitRead(
            commit_sha=c.commit_sha or "",
            commit_message=c.message or "",
            branch_name=c.branch or "",
            files_changed=c.files_changed or "",
            repo_path=repo_id_to_path.get(c.repo_id, "") if c.repo_id else "",
            author_name=c.actor_name,
            author_email=(c.metadata_ or {}).get("author_email"),
            user_id=c.user_id,
            user_name=user_names.get(c.user_id) if c.user_id else None,
            created_at=c.created_at,
        )
        for c in commits
    ]

    # Group commits by contributor (user_id or author_email fallback)
    contrib_map: dict[str, ContributorRead] = {}
    for cr in commit_reads:
        key = str(cr.user_id) if cr.user_id else (cr.author_email or "unknown")
        if key not in contrib_map:
            contrib_map[key] = ContributorRead(
                user_id=str(cr.user_id) if cr.user_id else None,
                user_name=cr.user_name,
                author_name=cr.author_name,
                author_email=cr.author_email,
            )
        contrib = contrib_map[key]
        contrib.commit_count += 1
        if cr.files_changed:
            contrib.files_changed += len(_parse_files_changed(cr.files_changed))
        contrib.commits.append(cr)

    return DevActivityResponse(
        activities=[DevActivityRead.model_validate(a) for a in activities],
        commits=commit_reads,
        contributors=sorted(contrib_map.values(), key=lambda c: c.commit_count, reverse=True),
        repos=[
            CommitRepoRead(
                repo_path=s.repo_path,
                repo_name=Path(s.repo_path).name,
                commit_count=s.commit_count,
                first_sha=s.first_sha,
                last_sha=s.last_sha,
            )
            for s in repo_summaries
        ],
        untracked_repos=[
            UntrackedRepoRead(
                repo_path=u.repo_path,
                name=Path(u.repo_path).name,
                commit_count=u.commit_count,
            )
            for u in untracked_summaries
        ],
        stats=DevStatsRead(
            total_commits=len(commits),
            total_files_changed=len(all_files),
            repos_touched=len(repo_summaries),
            agent_runs=len(agent_tasks),
            effectiveness_score=eff["score"],
            confidence=eff["confidence"],
            completion_rate=eff["completion_rate"],
            cost_per_commit=eff["cost_per_commit"],
            total_cost_usd=eff["total_cost_usd"],
            test_coverage=eff["test_coverage"],
            risk_count=eff["risk_count"],
        ),
    )


# ── Export / Import ───────────────────────────────────────────────


@router.get(
    "/{bud_id}/export/{section}",
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def export_bud_section(
    bud_id: uuid.UUID,
    section: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """Download a BUD section as a markdown file."""
    if section not in EXPORTABLE_SECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid section. Must be one of: {', '.join(EXPORTABLE_SECTIONS)}.",
        )

    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    content = getattr(bud, section) or ""
    bud_ref = f"BUD-{bud.bud_number:03d}"
    section_suffix = section.replace("_md", "").replace("_", "-")
    filename = f"{bud_ref}-{section_suffix}.md"

    return PlainTextResponse(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/{bud_id}/import/{section}",
    response_model=BUDRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def import_bud_section(
    bud_id: uuid.UUID,
    section: str,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDDocument:
    """Upload a markdown file to replace a BUD section."""
    if section not in EXPORTABLE_SECTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid section. Must be one of: {', '.join(EXPORTABLE_SECTIONS)}.",
        )

    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    # Same phase-edit policy as PATCH /buds/{id} — uploading a markdown
    # file to ``requirements_md`` while the BUD is in development must
    # also be rejected, not just the JSON PATCH path.
    assert_section_editable(bud, section)

    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is not valid UTF-8. Please save as UTF-8 and try again.",
        ) from None

    if len(content) > 512_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum 500KB.",
        )

    setattr(bud, section, content)
    await db.flush()
    await db.refresh(bud)

    logger.info(
        "bud_section_imported",
        bud_id=str(bud.id),
        section=section,
        size=len(content),
    )

    return bud
