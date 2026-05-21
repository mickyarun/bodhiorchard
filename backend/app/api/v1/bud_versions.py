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

The revert orchestration lives in
:mod:`app.services.bud_version_restore` so the route stays thin and
the side-effect order (snapshot → apply → re-derive → timeline) can be
unit-tested without spinning up FastAPI.
"""

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud import BUDStatus
from app.models.user import User
from app.repositories import bud_version as bud_version_repo
from app.repositories.bud import BUDRepository
from app.schemas.bud_version import BUDVersionDetail, BUDVersionRead
from app.services.bud_version_restore import restore_bud_to_version

# Hard cap on the History tab page size — keeps an over-zealous client
# from pulling thousands of rows in one shot. Tune up if a real use case
# emerges; 500 covers ~25 phase transitions worth of edits per BUD.
_MAX_VERSIONS_LIMIT = 500

# Per-string truncation for snapshot fields returned by the detail
# endpoint. The diff viewer renders markdown — a few KB per section
# is plenty for visual diffing — and unbounded blob fetches would
# amplify egress on any BUD with very large requirements_md /
# tech_spec_md / test_plan_md.
_SNAPSHOT_FIELD_TRUNCATE = 20_000


def _truncate_snapshot_blob(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Cap string-typed snapshot fields to ``_SNAPSHOT_FIELD_TRUNCATE``
    characters. Non-string values (lists, dicts, None) pass through —
    they have their own size dynamics and aren't the typical hot path
    for amplification."""
    out: dict[str, Any] = {}
    for key, value in snapshot.items():
        if isinstance(value, str) and len(value) > _SNAPSHOT_FIELD_TRUNCATE:
            out[key] = value[:_SNAPSHOT_FIELD_TRUNCATE] + "…"
        else:
            out[key] = value
    return out


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
) -> list[BUDVersionRead]:
    """Return version-history rows for one BUD, newest first.

    The snapshot blob is excluded — it can weigh tens of KB and the
    History tab only needs the summary line. Fetch a single snapshot
    via :func:`get_bud_version_detail` when rendering the diff viewer.
    """
    capped_limit = min(max(limit, 1), _MAX_VERSIONS_LIMIT)
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
    to fetch the historical snapshot, then diffs the field the phase
    owns against the current BUD's value of that field. Reads use
    ``buds:view`` so QA / observers can review the trail without write
    rights.

    Each string field in the snapshot is truncated to
    ``_SNAPSHOT_FIELD_TRUNCATE`` chars to keep the response bounded.
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
    detail = BUDVersionDetail.model_validate(row)
    detail.snapshot = _truncate_snapshot_blob(detail.snapshot)
    return detail


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
) -> dict[str, str | int | bool]:
    """Roll a BUD's content back to a specific ``(phase, version_no)``.

    Validates existence and delegates the actual restore (snapshot,
    apply, re-derive, timeline) to
    :func:`app.services.bud_version_restore.restore_bud_to_version`.
    """
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    target = await bud_version_repo.get_one(db, bud_id, phase, version_no)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No version v{version_no} for phase '{phase.value}' on this BUD.",
        )
    return await restore_bud_to_version(db, bud, target, current_user)
