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

"""Internal endpoints called by the Colyseus multiplayer server.

These routes are NOT for regular clients — they're for the Colyseus
server to pull initial state and verify user tokens. Authenticated
via shared secret in the `X-Bridge-Secret` header.

Endpoints:
    GET  /internal/colyseus/org-snapshot/{org_id}  — fetch org members + initial state
    POST /internal/colyseus/verify-token           — verify a user JWT (for room join)
    POST /internal/colyseus/race-invite            — persist + WS-broadcast a race invitation
"""

from __future__ import annotations

import hmac
import uuid

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_db
from app.core.security import verify_token
from app.repositories.organization import OrganizationRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.user import UserRepository
from app.schemas.settings import PresenceSettings
from app.services.org_settings import get_presence_settings
from app.services.presence_cache import get_presence_state
from app.services.race_invite_service import (
    RaceInviteValidationError,
    send_race_invite_notification,
)
from app.services.tree_data import get_tree_data

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/internal/colyseus", tags=["internal"])


def _verify_bridge_secret(
    x_bridge_secret: str | None = Header(default=None, alias="X-Bridge-Secret"),
) -> None:
    """Verify the Colyseus bridge shared secret (constant-time comparison)."""
    configured = settings.colyseus.bridge_secret
    if not x_bridge_secret or not hmac.compare_digest(x_bridge_secret, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bridge secret",
        )


@router.get("/org-snapshot/{org_id}")
async def get_org_snapshot(
    org_id: uuid.UUID,
    _: None = Depends(_verify_bridge_secret),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a snapshot of the org's members + repos for Colyseus.

    Called by Colyseus when an OrgRoom is created (first client joins).
    The Colyseus server uses this data to initialize MemberState entries
    and compute initial placements based on presence.

    The member list includes ALL active org members (via ``OrgToUser``),
    not just contributors with ``SkillProfile`` entries — because anyone
    in the org can appear in the garden, including managers and new
    joiners who haven't committed any tracked code yet. Using ``tree_data``
    (contribution-filtered) would exclude them and leave their character
    unspawned when they load the dashboard.

    Args:
        org_id: The organization UUID.

    Returns:
        Dict with ``orgId``, ``members``, and ``repos`` fields.
    """
    # Fetch repo/tree info (used by DevActivitySim + AgentActivitySim for
    # tree-position lookups) from the contribution-based tree data.
    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    tracked_repos = await repo_repo.get_active_path_name_pairs()
    tree = await get_tree_data(db, org_id, tracked_repos, refresh=False)

    # Resolve per-org presence settings (working days, hours, timezone,
    # auto-mode toggle). Defaults preserve the legacy hardcoded behaviour
    # (Mon-Fri, 08:00-18:00, server-local) so un-migrated orgs get the
    # same presence sim output as before this field existed.
    org_config = await OrganizationRepository(db).get_config(org_id) or {}
    presence_settings = get_presence_settings(org_config)

    # Fetch ALL active org members — full membership list, not filtered by
    # contribution activity. This is what the garden is keyed on.
    member_rows = await _collect_org_members(db, org_id, presence_settings)

    logger.info(
        "colyseus_org_snapshot",
        org_id=str(org_id),
        members=len(member_rows),
        repos=len(tree.repos),
    )

    return {
        "orgId": str(org_id),
        "members": member_rows,
        "repos": [
            {
                "repo_name": r.repo_name,
                "growth_stage": r.growth_stage,
            }
            for r in tree.repos
        ],
        # camelCase alias matches the multiplayer TS side (PresenceSettingsPayload).
        "presenceSettings": presence_settings.model_dump(mode="json", by_alias=True),
    }


async def _collect_org_members(
    db: AsyncSession,
    org_id: uuid.UUID,
    presence_settings: PresenceSettings,
) -> list[dict]:
    """Return every active member of an org for the Colyseus snapshot.

    Joins ``users`` via ``org_to_user`` membership (authoritative for
    "is this user in this org?") and left-joins ``developer_xp`` for level
    info. Excludes bot accounts and deactivated users. Unlike
    ``tree_data._collect_members``, this is NOT filtered by SkillProfile
    activity — managers and new joiners are included.

    Ordering is stable (by user_id) so the Colyseus room's house-grid slot
    assignment is deterministic across snapshot reloads.

    The ``has_slack`` field per member tells the Colyseus server whether
    Slack is the authoritative presence source for that member. The
    InferredPresenceSim (Phase C) uses this to skip Slack-driven members
    and only apply dev-activity-based pseudo-presence to non-Slack users.
    A user has Slack if and only if (a) their ``slack_id`` is set AND
    (b) the org has a ``slack_bot_token`` configured (no token → no poll
    → no presence data → treat as inferred).

    Args:
        db: Async database session.
        org_id: The organization UUID.
        presence_settings: Per-org presence config, passed through to
            ``get_presence_state`` so Slack-driven state classification
            honours the org's working days, hours, and timezone.
    """
    # Check once whether the org has a Slack bot token configured. Used
    # below to compute `has_slack` per member without re-querying.
    org_has_slack_token = bool(await OrganizationRepository(db).get_slack_bot_token(org_id))

    rows = await UserRepository(db).list_active_members_with_xp(org_id)

    members: list[dict] = []
    for user, xp in rows:
        # Look up Slack presence state (falls back to "active" if no mapping).
        # ``get_presence_state`` applies the org's working-day + work-hours
        # rules when deciding ``on_break`` vs ``at_home`` for offline users.
        presence = "active"
        if user.slack_id:
            presence = get_presence_state(str(org_id), user.slack_id, presence_settings)

        # "has_slack" is true only when BOTH the user has a slack_id AND
        # the org has a bot token. A user with slack_id in an org that
        # removed its token is still non-Slack-driven for presence purposes.
        has_slack = bool(user.slack_id) and org_has_slack_token

        members.append(
            {
                "user_id": str(user.id),
                "name": user.name or "",
                "character_model": user.character_model,
                "presence": presence,
                "level": (xp.level if xp else None) or 1,
                "level_name": (xp.level_name if xp else None) or "seedling",
                "house_level": (xp.house_level if xp else None) or 1,
                "vehicle_unlocks": list(xp.vehicle_unlocks) if xp and xp.vehicle_unlocks else [],
                "has_slack": has_slack,
            }
        )
    return members


@router.post("/verify-token")
async def verify_user_token(
    payload: dict,
    _: None = Depends(_verify_bridge_secret),
) -> dict:
    """Verify a user JWT token.

    Called by Colyseus when a client attempts to join an OrgRoom.
    Prevents unauthorized users from joining org rooms they don't belong to.

    Args:
        payload: `{"token": "<jwt>", "org_id": "<uuid>"}`

    Returns:
        `{"valid": true, "user_id": "...", "org_id": "...", "name": "..."}`
        or `{"valid": false}`.
    """
    token = payload.get("token")
    claimed_org_id = payload.get("org_id")
    if not token:
        logger.warning("colyseus_verify_token_missing", claimed_org_id=claimed_org_id)
        return {"valid": False}

    jwt_payload = verify_token(token)
    if jwt_payload is None:
        # verify_token swallows JWTError (expired, bad signature, malformed).
        # Log the prefix so we can distinguish "no token" from "bad token"
        # without leaking the full credential. Most common cause in practice:
        # token expired (60min default lifetime) and the client didn't
        # refresh before joining the Colyseus room.
        logger.warning(
            "colyseus_verify_token_invalid",
            reason="jwt_decode_failed",
            token_prefix=token[:12] + "..." if len(token) > 12 else "***",
            claimed_org_id=claimed_org_id,
        )
        return {"valid": False}

    token_org_id = jwt_payload.get("org_id")
    if claimed_org_id and token_org_id and str(token_org_id) != str(claimed_org_id):
        logger.warning(
            "colyseus_verify_token_org_mismatch",
            token_org_id=str(token_org_id),
            claimed_org_id=str(claimed_org_id),
            user_id=jwt_payload.get("sub", ""),
        )
        return {"valid": False}

    return {
        "valid": True,
        "user_id": jwt_payload.get("sub", ""),
        "org_id": str(token_org_id) if token_org_id else "",
        "name": jwt_payload.get("name", ""),
    }


class RaceInviteRequest(BaseModel):
    """Body of the race-invite bridge call."""

    org_id: uuid.UUID = Field(alias="orgId")
    recipient_user_id: uuid.UUID = Field(alias="recipientUserId")
    host_user_id: uuid.UUID = Field(alias="hostUserId")
    host_name: str = Field(alias="hostName")
    room_id: str = Field(alias="roomId")
    distance_m: int = Field(alias="distanceM")

    model_config = {"populate_by_name": True}


class RaceInviteResponse(BaseModel):
    """Success response for a persisted + published race invite."""

    notification_id: uuid.UUID = Field(alias="notificationId")

    model_config = {"populate_by_name": True}


@router.post("/race-invite", response_model=RaceInviteResponse)
async def post_race_invite(
    body: RaceInviteRequest,
    _: None = Depends(_verify_bridge_secret),
    db: AsyncSession = Depends(get_db),
) -> RaceInviteResponse:
    """Persist a race invitation and push it over the recipient's WS topic.

    Called by the multiplayer server (via `BackendClient.postRaceInvite`)
    once per invitee when a host creates a race room. Validates the
    recipient is actually a member of the given org before writing so a
    compromised bridge can't spam notifications across tenants.
    """
    # Org-membership check — prevents the bridge from addressing a user
    # who doesn't belong to the claimed org. The existing
    # ``OrgToUser`` table is the authoritative membership record.
    if not await UserRepository(db).is_member_of_org(body.recipient_user_id, body.org_id):
        logger.warning(
            "race_invite_recipient_not_in_org",
            org_id=str(body.org_id),
            recipient_user_id=str(body.recipient_user_id),
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient is not a member of the specified organization",
        )

    try:
        notif_id = await send_race_invite_notification(
            db,
            org_id=str(body.org_id),
            recipient_user_id=str(body.recipient_user_id),
            host_user_id=str(body.host_user_id),
            host_name=body.host_name,
            room_id=body.room_id,
            distance_m=body.distance_m,
        )
    except RaceInviteValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err

    await db.commit()
    logger.info(
        "race_invite_persisted",
        notification_id=str(notif_id),
        recipient_user_id=str(body.recipient_user_id),
        room_id=body.room_id,
        distance_m=body.distance_m,
    )
    return RaceInviteResponse(notification_id=notif_id)
