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

"""Side-effect orchestration for BUD version restore.

The route handler in ``app/api/v1/bud_versions.py`` validates the
request and calls into this module to actually mutate the BUD. Keeping
the orchestration out of the route handler does two things:

* Lets the unit tests exercise restore behaviour without spinning up
  the full FastAPI app + dependency chain.
* Keeps the bud_versions route file under the project's 200-line
  ceiling.

Three derived artefacts MUST stay consistent across a restore, in
addition to the snapshot fields:

1. ``BUDDocument.embedding`` — bug-linker (0.40 cosine threshold) and
   MCP semantic search both index off it. Leaving the embedding from a
   newer ``requirements_md`` would silently link the wrong bugs.
2. ``BUDFeatureLink`` rows — derived from the trailing JSON fence in
   ``requirements_md``. Stale links mislead downstream agents
   (Designer / TechPlanner / Code Review).
3. ``bud_timeline_events`` — gives the activity log a visible
   ``content_updated`` row for the restore, not just a silent History
   change.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDesignStatus, BUDDocument, BUDStatus
from app.models.bud_feature_link import BUDFeatureLinkSource
from app.models.bud_version import BUDEditSource, BUDVersion
from app.repositories import bud_version as bud_version_repo
from app.repositories.bud import BUDDesignRepository
from app.repositories.bud_version import SNAPSHOT_FIELDS
from app.services.agent_result_handlers import persist_linked_features_from_markdown
from app.services.bud_timeline import record_event
from app.services.embedding_service import embedding_service

if TYPE_CHECKING:
    from app.models.user import User

logger = structlog.get_logger(__name__)


# Lifecycle ordering of phases that can host content edits. Restore is
# rejected when the BUD has progressed PAST the snapshot's phase,
# because the downstream artefacts derived from the newer content
# (todos, estimates, PRs) have already crystallised and the document
# would diverge from the world. Phases not in this map (UAT / PROD)
# never own editable content, so a snapshot from them shouldn't exist.
_PHASE_RANK: dict[BUDStatus, int] = {
    BUDStatus.BUD: 0,
    BUDStatus.DESIGN: 1,
    BUDStatus.TECH_ARCH: 2,
    BUDStatus.DEVELOPMENT: 3,
    BUDStatus.CODE_REVIEW: 4,
    BUDStatus.TESTING: 5,
}


def _phase_progressed_past_snapshot(current: BUDStatus, snapshot_phase: BUDStatus) -> bool:
    """True if the BUD has moved past the snapshot's phase in the lifecycle.

    Terminal statuses (CLOSED / DISCARDED) are handled by the caller
    with a separate 400 — they aren't compared via rank because their
    rank would be ambiguous (closed-from-design vs closed-from-prod).
    UAT and PROD count as "past everything" since the only snapshots
    that exist are from content-bearing phases.
    """
    if current in (BUDStatus.UAT, BUDStatus.PROD):
        return True
    current_rank = _PHASE_RANK.get(current)
    snap_rank = _PHASE_RANK.get(snapshot_phase)
    if current_rank is None or snap_rank is None:
        # Defensive fail-closed: an unknown phase should treat the
        # restore as "progressed past" so an operator notices and the
        # revert is blocked. If we ever add a new content-bearing
        # phase to BUDStatus, ``_PHASE_RANK`` must be updated in the
        # same change.
        logger.warning(
            "bud_revert_unknown_phase",
            current=current.value if current else None,
            snapshot_phase=snapshot_phase.value if snapshot_phase else None,
        )
        return True
    return current_rank > snap_rank


def assert_phase_allows_restore(bud: BUDDocument, snapshot_phase: BUDStatus) -> None:
    """Reject restores that would diverge the BUD from already-derived state.

    The contract: restoring content for a phase ``P`` is only safe
    while the BUD is still IN ``P`` or in an earlier phase that
    couldn't have read from ``P``. Once the BUD has moved past ``P``,
    downstream artefacts (todos, estimates, opened PRs) reference the
    newer content; restoring the source would leave those artefacts
    pointing at text that no longer exists in the BUD.

    The error response carries the current + required phase so the UI
    can surface "advance the BUD back to <phase> first" without
    guessing.
    """
    if bud.status in (BUDStatus.CLOSED, BUDStatus.DISCARDED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot revert a {bud.status.value} BUD.",
        )
    if _phase_progressed_past_snapshot(bud.status, snapshot_phase):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "phase_progressed",
                "message": (
                    f"Cannot restore {snapshot_phase.value} content while BUD is in "
                    f"{bud.status.value}. Downstream artefacts (todos, estimates, PRs) "
                    f"already reference the newer content. Move the BUD back to "
                    f"{snapshot_phase.value} first if you need to undo."
                ),
                "current_status": bud.status.value,
                "snapshot_phase": snapshot_phase.value,
            },
        )


def _apply_snapshot(bud: BUDDocument, snapshot: dict[str, object]) -> None:
    """Write snapshot values back onto the BUD, restricted to the allowlist.

    The allowlist (``SNAPSHOT_FIELDS``) guards against a future schema
    change accidentally widening the snapshot dict. ``assignee_id`` is
    coerced from its JSON-safe string form back to ``uuid.UUID``.
    """
    for key in SNAPSHOT_FIELDS:
        if key not in snapshot:
            continue
        value = snapshot[key]
        if key == "assignee_id" and isinstance(value, str):
            value = uuid.UUID(value)
        setattr(bud, key, value)


async def _restore_design_html_if_present(
    db: AsyncSession, bud: BUDDocument, snapshot: dict[str, object]
) -> bool:
    """Restore the targeted ``bud_designs`` row from the snapshot's
    ``__design_html`` + ``__design_repo_id`` sentinels, if present.

    Design content lives in ``bud_designs``, not ``bud_documents``,
    so the standard :func:`_apply_snapshot` (keyed off SNAPSHOT_FIELDS)
    can't restore it. The MCP design-phase write captures the prior
    HTML and the repo it belonged to; revert upserts back into that
    same ``(bud_id, repo_id)`` row.

    Returns ``True`` if a design row was upserted.
    """
    if "__design_html" not in snapshot:
        return False
    prior_html = snapshot["__design_html"]
    # ``None`` is a legitimate snapshot value (no design at the
    # time) but ``upsert`` with ``design_html=None`` would leave
    # the column at whatever's there now — wrong behaviour for
    # "restore to a no-design state". Treat None as no-op; a
    # future enhancement can add an explicit delete-on-restore
    # sentinel.
    if not isinstance(prior_html, str) or not prior_html:
        return False
    raw_repo_id = snapshot.get("__design_repo_id")
    if not isinstance(raw_repo_id, str) or not raw_repo_id:
        # Legacy snapshot without the repo sentinel — fall back to
        # the BUD-level slot so older history rows still restore
        # without the tab-mismatch we just fixed.
        repo_id: uuid.UUID | None = None
    else:
        try:
            repo_id = uuid.UUID(raw_repo_id)
        except ValueError:
            logger.warning(
                "bud_revert_bad_design_repo_id",
                bud_id=str(bud.id),
                raw_repo_id=raw_repo_id,
            )
            return False
    design_repo = BUDDesignRepository(db, org_id=bud.org_id)
    await design_repo.upsert(
        bud.id,
        repo_id,
        design_html=prior_html,
        status=BUDDesignStatus.READY,
    )
    return True


async def _refresh_derived_state_if_requirements_changed(
    db: AsyncSession,
    bud: BUDDocument,
    pre_requirements_md: str | None,
    actor: User,
) -> dict[str, int | bool]:
    """Re-derive embedding + linked features when requirements_md changed.

    Returns a summary the route handler echoes back so the UI knows
    which downstream artefacts the restore touched.
    """
    summary: dict[str, int | bool] = {
        "embedding_refreshed": False,
        "linked_features_reparsed": 0,
    }
    if bud.requirements_md == pre_requirements_md:
        return summary

    # Embedding regeneration — same shape the create + MCP-update paths
    # use, so the vector key stays consistent for the bug-linker.
    try:
        embed_text = f"{bud.title} {(bud.requirements_md or '')[:500]}"
        bud.embedding = await embedding_service.embed(embed_text)
        summary["embedding_refreshed"] = True
    except Exception:
        # Failure is non-fatal — a stale embedding produces worse
        # search results, not wrong data. Log loudly so ops can spot
        # systemic ONNX / model issues.
        logger.warning(
            "bud_revert_embedding_failed",
            bud_id=str(bud.id),
            exc_info=True,
        )

    # Linked-feature reparse — mirrors the REST PATCH path's call into
    # ``persist_linked_features_from_markdown`` with ``source=MANUAL``.
    # Empty / fence-less restored content yields 0 here, which is
    # correct (link rows from the newer content stay until the next
    # explicit edit clears them).
    if bud.requirements_md:
        try:
            accepted = await persist_linked_features_from_markdown(
                bud.id,
                bud.org_id,
                bud.requirements_md,
                db,
                source=BUDFeatureLinkSource.MANUAL,
                actor_name=actor.name or actor.email,
                actor_id=actor.id,
            )
            summary["linked_features_reparsed"] = accepted
        except Exception:
            logger.warning(
                "bud_revert_feature_link_reparse_failed",
                bud_id=str(bud.id),
                exc_info=True,
            )

    return summary


async def restore_bud_to_version(
    db: AsyncSession,
    bud: BUDDocument,
    target: BUDVersion,
    actor: User,
) -> dict[str, str | int | bool]:
    """Roll a BUD back to a specific snapshot and refresh derived state.

    Side-effect order is load-bearing:

    1. Phase-progression gate (raises 409 if too late to safely undo).
    2. Snapshot CURRENT state under ``source=revert`` so the restore
       is itself reversible.
    3. Apply the historical snapshot via the SNAPSHOT_FIELDS allowlist.
    4. Refresh embedding + linked features if ``requirements_md``
       changed.
    5. Emit a ``content_updated`` timeline event so the activity log
       reflects the restore (not just a silent History row).
    """
    assert_phase_allows_restore(bud, target.phase)

    pre_requirements_md = bud.requirements_md

    await bud_version_repo.insert_snapshot(
        db,
        bud=bud,
        phase=bud.status,
        source=BUDEditSource.REVERT,
        edited_by=actor.id,
        reason=f"revert to {target.phase.value} v{target.version_no}",
    )

    snap = target.snapshot or {}
    _apply_snapshot(bud, snap)
    design_html_restored = await _restore_design_html_if_present(db, bud, snap)
    await db.flush()

    summary = await _refresh_derived_state_if_requirements_changed(
        db, bud, pre_requirements_md, actor
    )

    await record_event(
        db,
        bud.org_id,
        bud.id,
        "content_updated",
        actor_id=actor.id,
        actor_name=actor.name,
        detail={
            "section": "revert",
            "snapshot_phase": target.phase.value,
            "snapshot_version_no": target.version_no,
            "embedding_refreshed": summary["embedding_refreshed"],
            "linked_features_reparsed": summary["linked_features_reparsed"],
            "design_html_restored": design_html_restored,
        },
    )

    logger.info(
        "bud_reverted",
        bud_id=str(bud.id),
        org_id=str(bud.org_id),
        actor_id=str(actor.id),
        phase=target.phase.value,
        version_no=target.version_no,
        embedding_refreshed=summary["embedding_refreshed"],
        linked_features_reparsed=summary["linked_features_reparsed"],
        design_html_restored=design_html_restored,
    )
    return {
        "bud_id": str(bud.id),
        "phase": target.phase.value,
        "reverted_to_version": target.version_no,
        "embedding_refreshed": summary["embedding_refreshed"],
        "linked_features_reparsed": summary["linked_features_reparsed"],
        "design_html_restored": design_html_restored,
    }
