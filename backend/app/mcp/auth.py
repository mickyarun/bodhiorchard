# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""MCP token verification for Bodhiorchard tool calls from Claude Code."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass

import structlog
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import verify_password
from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.user_mcp_token import UserMCPTokenRepository

logger = structlog.get_logger(__name__)

# Internal tokens: short-lived tokens for scan-initiated Claude CLI runs.
# Maps token → org_id. Populated by create_internal_mcp_token(),
# consumed by verify_mcp_token(). Tokens persist until server restart;
# eager revocation caused race conditions with the shared token file.
_internal_tokens: dict[str, uuid.UUID] = {}
_MAX_INTERNAL_TOKENS = 100


def compute_token_prefix(plaintext_token: str) -> str:
    """Compute a non-secret prefix for indexed token lookup.

    Uses SHA-256 of the plaintext, truncated to 16 hex chars.
    This is NOT a secret — it's stored in plaintext for fast filtering
    before the expensive bcrypt verification.

    Args:
        plaintext_token: The raw token string.

    Returns:
        16-character hex prefix.
    """
    return hashlib.sha256(plaintext_token.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class MCPAuthResult:
    """Result of MCP token verification.

    Always contains an org. Contains a user when the token is
    a per-user token (UserMCPToken), None for org-level or internal tokens.
    """

    org: Organization
    user: User | None = None


def create_internal_mcp_token(org_id: uuid.UUID) -> str:
    """Create a temporary MCP token for internal use (e.g. scan pipeline).

    The token is stored in-memory and valid until server restart.
    If the token pool exceeds ``_MAX_INTERNAL_TOKENS``, the oldest
    entry is evicted to bound memory usage.

    Args:
        org_id: The organization UUID to associate with the token.

    Returns:
        The plaintext token string.
    """
    token = secrets.token_urlsafe(32)
    # Evict oldest token if at capacity
    if len(_internal_tokens) >= _MAX_INTERNAL_TOKENS:
        oldest_key = next(iter(_internal_tokens))
        _internal_tokens.pop(oldest_key)
        logger.debug("internal_token_evicted", evicted_token=oldest_key[:8])
    _internal_tokens[token] = org_id
    return token


async def verify_mcp_token(
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(),
) -> MCPAuthResult:
    """Verify the bearer token from an MCP request.

    Resolution order:
    1. Internal tokens (in-memory, scan pipeline) → org only
    2. Per-user tokens (UserMCPToken table) → org + user
    3. Org-level tokens (Organization.mcp_token_hash) → org only

    Args:
        db: The async database session.
        authorization: The Authorization header value (Bearer <token>).

    Returns:
        MCPAuthResult with the authenticated org and optional user.

    Raises:
        HTTPException: If token is missing, invalid, or no match found.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    token = authorization[7:]

    logger.debug(
        "mcp_auth_attempt",
        token_prefix=token[:8] if len(token) >= 8 else token,
        internal_token_count=len(_internal_tokens),
    )

    org_repo = OrganizationRepository(db)

    # 1. Check internal tokens first (fast, in-memory)
    internal_org_id = _internal_tokens.get(token)
    if internal_org_id is not None:
        org = await org_repo.get_by_id(internal_org_id)
        if org:
            logger.debug("mcp_auth_internal", org_id=str(org.id))
            return MCPAuthResult(org=org)

    # 2. Check per-user tokens — filter by prefix (indexed), then bcrypt
    prefix = compute_token_prefix(token)
    candidates = await UserMCPTokenRepository(db).list_by_prefix_with_relations(prefix)
    for ut in candidates:
        if verify_password(token, ut.token_hash):
            logger.debug(
                "mcp_auth_user_token",
                org_id=str(ut.org_id),
                user_id=str(ut.user_id),
            )
            return MCPAuthResult(org=ut.organization, user=ut.user)

    # 3. Fall back to org-level token hashes
    orgs = await org_repo.get_all_with_mcp_tokens()
    for org in orgs:
        if org.mcp_token_hash and verify_password(token, org.mcp_token_hash):
            logger.debug(
                "mcp_auth_success",
                org_id=str(org.id),
                slug=org.slug,
            )
            return MCPAuthResult(org=org)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired MCP token",
    )
