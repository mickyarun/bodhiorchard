"""Internal endpoints called by the Colyseus multiplayer server.

These routes are NOT for regular clients — they're for the Colyseus
server to pull initial state and verify user tokens. Authenticated
via shared secret in the `X-Bridge-Secret` header.

Endpoints:
    GET  /internal/colyseus/org-snapshot/{org_id}  — fetch org members + initial state
    POST /internal/colyseus/verify-token           — verify a user JWT (for room join)
"""

from __future__ import annotations

import hmac
import uuid

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_db
from app.core.security import verify_token
from app.models.developer_xp import DeveloperXP
from app.models.user import OrgToUser, User
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.presence_cache import get_presence_state
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

    # Fetch ALL active org members — full membership list, not filtered by
    # contribution activity. This is what the garden is keyed on.
    member_rows = await _collect_org_members(db, org_id)

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
    }


async def _collect_org_members(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> list[dict]:
    """Return every active member of an org for the Colyseus snapshot.

    Joins ``users`` via ``org_to_user`` membership (authoritative for
    "is this user in this org?") and left-joins ``developer_xp`` for level
    info. Excludes bot accounts and deactivated users. Unlike
    ``tree_data._collect_members``, this is NOT filtered by SkillProfile
    activity — managers and new joiners are included.

    Ordering is stable (by user_id) so the Colyseus room's house-grid slot
    assignment is deterministic across snapshot reloads.
    """
    stmt = (
        select(
            User.id,
            User.name,
            User.character_model,
            User.slack_id,
            DeveloperXP.level,
            DeveloperXP.level_name,
        )
        .join(OrgToUser, OrgToUser.user_id == User.id)
        .outerjoin(
            DeveloperXP,
            (DeveloperXP.user_id == User.id) & (DeveloperXP.org_id == org_id),
        )
        .where(OrgToUser.org_id == org_id)
        .where(User.is_active.is_(True))
        .where(~User.name.ilike("%[bot]%"))
        .order_by(User.id)
    )
    result = await db.execute(stmt)
    rows = result.all()

    members: list[dict] = []
    for row in rows:
        # Look up Slack presence state (falls back to "active" if no mapping)
        presence = "active"
        if row.slack_id:
            presence = get_presence_state(str(org_id), row.slack_id)

        members.append(
            {
                "user_id": str(row.id),
                "name": row.name or "",
                "character_model": row.character_model,
                "presence": presence,
                "level": row.level or 1,
                "level_name": row.level_name or "seedling",
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
        return {"valid": False}

    jwt_payload = verify_token(token)
    if jwt_payload is None:
        return {"valid": False}

    token_org_id = jwt_payload.get("org_id")
    if claimed_org_id and token_org_id and str(token_org_id) != str(claimed_org_id):
        return {"valid": False}

    return {
        "valid": True,
        "user_id": jwt_payload.get("sub", ""),
        "org_id": str(token_org_id) if token_org_id else "",
        "name": jwt_payload.get("name", ""),
    }
