# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Self-service endpoints for the currently authenticated user.

Routes under ``/v1/me/*`` are gated only by authentication — NOT by any
org-level permission. They let a regular member manage resources that
belong to them personally (e.g. their own MCP token) without requiring
``org:edit_settings`` or any admin role.

The existing ``/v1/settings/mcp-token`` endpoint is the admin path:
it rotates the org-level token hash (for backward compat with legacy
integrations) AND upserts the caller's per-user token, gated by
``org:edit_settings``. Regular members can't reach it.

This router only writes to the per-user ``user_mcp_tokens`` table and
never touches ``organizations.mcp_token_hash`` — so a QA tester
regenerating their own token can't overwrite anyone else's access.
"""

import secrets

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import hash_password
from app.mcp.auth import compute_token_prefix
from app.models.user import User
from app.models.user_mcp_token import UserMCPToken

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/me", tags=["me"])


class MCPTokenResponse(BaseModel):
    """Response schema for self-service MCP token generation.

    The plaintext token is returned exactly once — subsequent calls to
    the status endpoint only reveal whether a token exists, never the
    token itself, because the DB stores a bcrypt hash.
    """

    mcp_token: str
    message: str = "MCP token generated. Store it securely — it will not be shown again."


class MCPTokenStatus(BaseModel):
    """Response schema for the self-service MCP token status check."""

    has_token: bool


@router.post("/mcp-token", response_model=MCPTokenResponse)
async def regenerate_my_mcp_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MCPTokenResponse:
    """Generate or regenerate the calling user's per-user MCP token.

    Any authenticated user can call this — no permission gate beyond
    having a valid JWT. Generating a token doesn't expand the user's
    trust boundary; it just lets Claude Code authenticate as them when
    hooks push activity from their local repo.

    Only the per-user ``user_mcp_tokens`` row is affected. We deliberately
    do NOT update ``organizations.mcp_token_hash`` here (unlike the admin
    settings endpoint) — regular members must not be able to rotate the
    org-level token that other integrations might depend on.

    The plaintext token is returned once; subsequent reads can only
    confirm that a token exists via the status endpoint.
    """
    mcp_token = secrets.token_urlsafe(32)
    token_hash = hash_password(mcp_token)
    token_prefix = compute_token_prefix(mcp_token)

    # Upsert one row per (user_id, org_id). The JWT enforces that org_id
    # is the user's active org, so a user can't mint a token for an org
    # they don't belong to.
    existing = await db.execute(
        select(UserMCPToken).where(
            UserMCPToken.user_id == current_user.id,
            UserMCPToken.org_id == current_user.org_id,
        )
    )
    user_token = existing.scalar_one_or_none()
    if user_token:
        user_token.token_hash = token_hash
        user_token.token_prefix = token_prefix
    else:
        user_token = UserMCPToken(
            user_id=current_user.id,
            org_id=current_user.org_id,
            token_hash=token_hash,
            token_prefix=token_prefix,
        )
        db.add(user_token)
    await db.flush()

    logger.info(
        "self_service_mcp_token_regenerated",
        org_id=str(current_user.org_id),
        user=current_user.email,
    )

    return MCPTokenResponse(mcp_token=mcp_token)


@router.get("/mcp-token/status", response_model=MCPTokenStatus)
async def my_mcp_token_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MCPTokenStatus:
    """Return whether the calling user already has a per-user MCP token.

    The UI uses this to show "Generate token" vs "Regenerate token" on
    the profile page, and to gate the "your token is already set up"
    indicator in the MCPSetupHint component.
    """
    existing = await db.execute(
        select(UserMCPToken.id).where(
            UserMCPToken.user_id == current_user.id,
            UserMCPToken.org_id == current_user.org_id,
        )
    )
    return MCPTokenStatus(has_token=existing.scalar_one_or_none() is not None)
