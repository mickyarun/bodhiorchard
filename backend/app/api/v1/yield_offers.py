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

"""HTTP endpoints for yield offers.

Three endpoints, all scoped to the authenticated user:
- ``GET /yield-offers`` — pending offers addressed to the caller
  (also runs TTL expiry as a side effect, no background job).
- ``POST /yield-offers/{id}/accept`` — release the yieldable BUD,
  take the incoming one.
- ``POST /yield-offers/{id}/reject`` — pass; assignment retries.
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, get_user_permissions, require_permissions
from app.models.user import User, UserRole
from app.repositories.role import RoleRepository
from app.schemas.yield_offer import YieldOfferRead
from app.services.yield_offer_service import (
    accept_offer,
    list_org_pending_with_expiry,
    list_pending_with_expiry,
    reassign_offer,
    reject_offer,
)

router = APIRouter(prefix="/yield-offers", tags=["yield-offers"])


async def _has_admin_scope(user: User, db: AsyncSession) -> bool:
    """True if ``user`` may see org-wide yield offers.

    Mirrors the bypass logic in ``require_permissions`` so the answer
    here matches what the rest of the app uses for ``team:manage``:
    org_owner always passes; otherwise the effective permission set
    must include ``team:manage``.
    """
    if getattr(user, "role", None) == UserRole.ORG_OWNER:
        return True
    role_id = getattr(user, "role_id", None)
    if role_id is not None:
        role_name = await RoleRepository(db).get_role_name(role_id)
        if role_name == "org_owner":
            return True
    perms = await get_user_permissions(user, db)
    return "team:manage" in perms


@router.get(
    "",
    response_model=list[YieldOfferRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_pending(
    scope: Literal["me", "org"] = Query("me", description="me = own offers; org = admin view"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[YieldOfferRead]:
    """Pending yield offers, oldest first.

    ``scope=me`` (default) returns offers addressed to the current
    user. ``scope=org`` is admin-only (``team:manage``) and returns
    every pending offer in the org so leads can spot stuck routing
    and reassign manually.
    """
    if scope == "org":
        if not await _has_admin_scope(current_user, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="scope=org requires team:manage permission",
            )
        offers = await list_org_pending_with_expiry(db, current_user.org_id)
    else:
        offers = await list_pending_with_expiry(db, current_user.org_id, current_user.id)
    return [YieldOfferRead.model_validate(o) for o in offers]


class ReassignRequest(BaseModel):
    """Admin override: re-route a pending offer to a different developer."""

    target_user_id: uuid.UUID


@router.post(
    "/{offer_id}/reassign",
    response_model=YieldOfferRead,
    dependencies=[Depends(require_permissions("team:manage"))],
)
async def reassign(
    offer_id: uuid.UUID,
    body: ReassignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> YieldOfferRead:
    """Re-route a pending yield offer to a different developer.

    Validates the new target has at least one BUD strictly
    lower-priority than the incoming BUD; replaces ``yieldable_bud_id``
    in lockstep. Old and new targets each get a WS event so their
    boards/badges update without a refresh.
    """
    try:
        offer = await reassign_offer(db, current_user.org_id, offer_id, body.target_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return YieldOfferRead.model_validate(offer)


@router.post(
    "/{offer_id}/accept",
    response_model=YieldOfferRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def accept(
    offer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> YieldOfferRead:
    """Accept the offer; release the yieldable BUD, take the incoming one."""
    try:
        offer = await accept_offer(
            db, current_user.org_id, offer_id, current_user.id, current_user.name
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return YieldOfferRead.model_validate(offer)


@router.post(
    "/{offer_id}/reject",
    response_model=YieldOfferRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def reject(
    offer_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> YieldOfferRead:
    """Reject the offer; another candidate will be considered."""
    try:
        offer = await reject_offer(db, current_user.org_id, offer_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return YieldOfferRead.model_validate(offer)
