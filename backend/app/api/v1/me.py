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

"""Self-service endpoints for the currently authenticated user.

Routes under ``/v1/me/*`` are gated only by authentication — NOT by any
org-level permission. They let a regular member manage resources that
belong to them personally (e.g. their own MCP tokens) without requiring
``org:edit_settings`` or any admin role.

The existing ``/v1/settings/mcp-token`` endpoint is the admin path:
it rotates the org-level token hash (for backward compat with legacy
integrations) AND upserts the caller's per-user token, gated by
``org:edit_settings``. Regular members can't reach it.

This router only writes to the per-user ``user_mcp_tokens`` table and
never touches ``organizations.mcp_token_hash`` — so a QA tester
regenerating their own token can't overwrite anyone else's access.

Two endpoint families live here:

* Legacy single-token endpoints (``POST /mcp-token``, ``GET /mcp-token/status``)
  preserve the Claude Code CLI's "regenerate my one token" mental model —
  they upsert a single row with ``name='Default'``.
* Multi-token endpoints (``POST /mcp-tokens``, ``GET /mcp-tokens``,
  ``DELETE /mcp-tokens/{id}``) let a user issue separately-revocable named
  tokens with optional TTLs — required for the BYO-AI flow where a user
  may connect Claude Desktop, Cursor, and Continue from different machines.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import hash_password
from app.mcp.auth import compute_token_prefix
from app.models.user import User
from app.models.user_mcp_token import DEFAULT_TOKEN_NAME, UserMCPToken
from app.repositories.user_mcp_token import UserMCPTokenRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/me", tags=["me"])

# Caps for token TTL. Default 90 days matches GitHub's PAT default; the
# 365-day max prevents long-tail "I forgot this token existed" leaks.
DEFAULT_EXPIRES_IN_DAYS = 90
MAX_EXPIRES_IN_DAYS = 365


class MCPTokenResponse(BaseModel):
    """Response schema returned after a token is minted.

    The plaintext token is returned exactly once — subsequent reads can
    only confirm that a token exists, never reveal it, because the DB
    stores a bcrypt hash.
    """

    mcp_token: str
    name: str = DEFAULT_TOKEN_NAME
    message: str = "MCP token generated. Store it securely — it will not be shown again."


class MCPTokenStatus(BaseModel):
    """Response schema for the self-service MCP token status check."""

    has_token: bool


class MCPTokenCreate(BaseModel):
    """Request body for ``POST /mcp-tokens`` (multi-token endpoint)."""

    name: str = Field(..., min_length=1, max_length=64)
    expires_in_days: int | None = Field(DEFAULT_EXPIRES_IN_DAYS, ge=1, le=MAX_EXPIRES_IN_DAYS)


class MCPTokenRead(BaseModel):
    """Listing entry — never contains plaintext."""

    id: uuid.UUID
    name: str
    token_prefix: str
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


def _resolve_expiry(expires_in_days: int | None) -> datetime | None:
    """Convert a TTL in days to an absolute expiry datetime (or None)."""
    if expires_in_days is None:
        return None
    return datetime.now(UTC) + timedelta(days=expires_in_days)


@router.post("/mcp-token", response_model=MCPTokenResponse)
async def regenerate_my_default_mcp_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MCPTokenResponse:
    """Generate or regenerate the caller's *default* MCP token.

    Preserves the legacy single-token mental model used by the Claude
    Code CLI: there's exactly one row with ``name='Default'`` per
    (user, org), and POSTing here replaces its hash. New named tokens
    for desktop AI clients go through ``POST /mcp-tokens``.
    """
    mcp_token = secrets.token_urlsafe(32)
    repo = UserMCPTokenRepository(db)
    existing = await repo.get_by_user_org_name(
        current_user.id, current_user.org_id, DEFAULT_TOKEN_NAME
    )
    if existing:
        existing.token_hash = hash_password(mcp_token)
        existing.token_prefix = compute_token_prefix(mcp_token)
        existing.expires_at = None  # legacy CLI token: no expiry
    else:
        db.add(
            UserMCPToken(
                user_id=current_user.id,
                org_id=current_user.org_id,
                name=DEFAULT_TOKEN_NAME,
                token_hash=hash_password(mcp_token),
                token_prefix=compute_token_prefix(mcp_token),
            )
        )
    await db.flush()

    logger.info(
        "self_service_mcp_token_regenerated",
        org_id=str(current_user.org_id),
        user=current_user.email,
    )

    return MCPTokenResponse(mcp_token=mcp_token, name=DEFAULT_TOKEN_NAME)


@router.get("/mcp-token/status", response_model=MCPTokenStatus)
async def my_default_mcp_token_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MCPTokenStatus:
    """Return whether the caller has the legacy ``Default`` token set up."""
    existing = await UserMCPTokenRepository(db).get_by_user_org_name(
        current_user.id, current_user.org_id, DEFAULT_TOKEN_NAME
    )
    return MCPTokenStatus(has_token=existing is not None)


@router.post(
    "/mcp-tokens",
    response_model=MCPTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_mcp_token(
    body: MCPTokenCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MCPTokenResponse:
    """Mint a new named token (typically for an external AI client).

    409s when ``name`` collides with an existing token for the same
    (user, org). The user must DELETE the old one first — preventing
    a silent revoke-on-create that would surprise the other client.
    """
    repo = UserMCPTokenRepository(db)
    if await repo.get_by_user_org_name(current_user.id, current_user.org_id, body.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have a token named {body.name!r}. Revoke it first.",
        )

    mcp_token = secrets.token_urlsafe(32)
    db.add(
        UserMCPToken(
            user_id=current_user.id,
            org_id=current_user.org_id,
            name=body.name,
            token_hash=hash_password(mcp_token),
            token_prefix=compute_token_prefix(mcp_token),
            expires_at=_resolve_expiry(body.expires_in_days),
        )
    )
    # Defensive catch for an integrity violation slipping past the
    # pre-check above. The pre-check covers the documented
    # ``(user_id, org_id, name)`` collision; an IntegrityError that
    # reaches here usually means a stale legacy index (e.g. the old
    # single-token-per-user constraint that migration 2c87d34be5bc was
    # supposed to drop — see migration 555236b875ed for the cleanup).
    # Convert to a 409 so the user sees an actionable message instead
    # of a 500 stack trace.
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "mcp_token_integrity_violation",
            org_id=str(current_user.org_id),
            user=current_user.email,
            name=body.name,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Could not create token — a uniqueness constraint blocked the "
                "insert. If this is your first attempt after a fresh deploy, "
                "ensure all DB migrations are applied (run "
                "``alembic upgrade head``)."
            ),
        ) from exc

    logger.info(
        "mcp_token_created",
        org_id=str(current_user.org_id),
        user=current_user.email,
        name=body.name,
        expires_in_days=body.expires_in_days,
    )
    return MCPTokenResponse(mcp_token=mcp_token, name=body.name)


@router.get("/mcp-tokens", response_model=list[MCPTokenRead])
async def list_my_mcp_tokens(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MCPTokenRead]:
    """List all of the caller's tokens, newest first. Never returns plaintext."""
    rows = await UserMCPTokenRepository(db).list_for_user(current_user.id, current_user.org_id)
    return [MCPTokenRead.model_validate(r) for r in rows]


@router.delete("/mcp-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_mcp_token(
    token_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke one of the caller's own tokens."""
    deleted = await UserMCPTokenRepository(db).delete_for_user(
        token_id, current_user.id, current_user.org_id
    )
    if deleted == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    logger.info(
        "mcp_token_revoked",
        org_id=str(current_user.org_id),
        user=current_user.email,
        token_id=str(token_id),
    )
