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

"""History + revert endpoints for BUDDocument.

Mounted at ``/buds/{bud_id}/versions`` and ``/buds/{bud_id}/revert/...``.
Reads are open to any org member who can view BUDs; revert requires
``buds:edit`` so only users who could PATCH the BUD via the normal flow
can roll it back. Reverts are recorded as a new ``source='revert'``
snapshot, so history is append-only — no past state is ever destroyed.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud import BUDStatus
from app.models.bud_version import BUDEditSource
from app.models.user import User
from app.repositories import bud_version as bud_version_repo
from app.repositories.bud import BUDRepository
from app.repositories.bud_version import SNAPSHOT_FIELDS
from app.schemas.bud_version import BUDVersionDetail, BUDVersionRead

# Hard cap on the History tab page size — keeps an over-zealous client
# from pulling thousands of rows in one shot. Tune up if a real use case
# emerges; 500 covers ~25 phase transitions worth of edits per BUD.
_MAX_VERSIONS_LIMIT = 500

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["bud-versions"])


@router.get(
    "/versions",
    response_model=list[BUDVersionRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_bud_versions(
    bud_id: uuid.UUID,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[BUDVersionRead]:  # noqa: D401
    capped_limit = min(max(limit, 1), _MAX_VERSIONS_LIMIT)
    """Return version-history rows for one BUD, newest first.

    The snapshot blob is excluded — it can weigh tens of KB and the
    History tab only needs the summary line. A follow-up endpoint will
    surface a single snapshot when implementing the diff viewer.
    """
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")
    rows = await bud_version_repo.list_for_bud(db, bud_id, limit=capped_limit)
    return [BUDVersionRead.model_validate(row) for row in rows]


@router.get(
    "/versions/{phase}/{version_no}",
    response_model=BUDVersionDetail,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_bud_version_detail(
    bud_id: uuid.UUID,
    phase: BUDStatus,
    version_no: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BUDVersionDetail:
    """Return one version row including the snapshot blob.

    Used by the per-section diff viewer: the section opens this endpoint
    to fetch the historical snapshot, then diffs the field that the
    phase owns against the current BUD's value of that field. Reads use
    ``buds:view`` so QA / observers can review the trail without write
    rights.
    """
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")
    row = await bud_version_repo.get_one(db, bud_id, phase, version_no)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No version v{version_no} for phase '{phase.value}' on this BUD.",
        )
    return BUDVersionDetail.model_validate(row)


@router.post(
    "/revert/{phase}/{version_no}",
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def revert_bud_to_version(
    bud_id: uuid.UUID,
    phase: BUDStatus,
    version_no: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int]:
    """Roll a BUD's content back to a specific ``(phase, version_no)``.

    Implementation notes:

    * The current state is snapshotted with ``source='revert'`` BEFORE
      mutation so the revert itself is reversible and the History tab
      stays consistent.
    * Revert snapshots are excluded from the per-phase prune cap (see
      :func:`bud_version_repo._prune_to_cap`), so a revert-storm cannot
      evict real edits.
    * Terminal-phase BUDs (closed / discarded) cannot be reverted —
      mirrors the PATCH guard, and protects an explicit "discard this
      idea" decision from being silently undone via the history tab.
    """
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    if bud.status in (BUDStatus.CLOSED, BUDStatus.DISCARDED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot revert a {bud.status.value} BUD.",
        )

    target = await bud_version_repo.get_one(db, bud_id, phase, version_no)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No version v{version_no} for phase '{phase.value}' on this BUD.",
        )

    # Snapshot current state under source=revert so the revert is itself
    # reversible. This must happen before we apply ``target.snapshot``.
    await bud_version_repo.insert_snapshot(
        db,
        bud=bud,
        phase=bud.status,
        source=BUDEditSource.REVERT,
        edited_by=current_user.id,
        reason=f"revert to {phase.value} v{version_no}",
    )

    # Apply the historical snapshot. Restrict the keys we'll setattr
    # to the explicit allowlist used at capture time — protects against
    # a future schema migration accidentally widening the snapshot dict
    # (e.g. adding a property) and a revert silently writing through
    # to something the policy didn't intend. ``assignee_id`` is
    # stringified in the JSONB and coerced back here.
    #
    # Side-effects intentionally NOT replayed: embedding regeneration,
    # tech-spec patch reconciliation, linked-feature reparse. Revert is
    # a content-only operation by design; downstream consumers will
    # re-derive on the next real edit. UI surfaces this in the History
    # tab as "content restored — links/embedding unchanged".
    snap = target.snapshot or {}
    for key in SNAPSHOT_FIELDS:
        if key not in snap:
            continue
        value = snap[key]
        if key == "assignee_id" and isinstance(value, str):
            value = uuid.UUID(value)
        setattr(bud, key, value)

    await db.flush()

    logger.info(
        "bud_reverted",
        bud_id=str(bud_id),
        org_id=str(current_user.org_id),
        actor_id=str(current_user.id),
        phase=phase.value,
        version_no=version_no,
    )
    return {
        "bud_id": str(bud_id),
        "phase": phase.value,
        "reverted_to_version": version_no,
    }
