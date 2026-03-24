"""MCP token verification for Bodhigrove tool calls from Claude Code."""

import secrets
import uuid

import structlog
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import verify_password
from app.models.organization import Organization
from app.repositories.organization import OrganizationRepository

logger = structlog.get_logger(__name__)

# Internal tokens: short-lived tokens for scan-initiated Claude CLI runs.
# Maps token → org_id. Populated by create_internal_mcp_token(),
# consumed by verify_mcp_token(). Tokens persist until server restart;
# eager revocation caused race conditions with the shared token file.
_internal_tokens: dict[str, uuid.UUID] = {}
_MAX_INTERNAL_TOKENS = 100


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
) -> Organization:
    """Verify the bearer token from an MCP request against org tokens.

    Checks internal (scan-pipeline) tokens first, then falls back to
    stored org token hashes.

    Args:
        db: The async database session.
        authorization: The Authorization header value (Bearer <token>).

    Returns:
        The authenticated Organization.

    Raises:
        HTTPException: If token is missing, invalid, or no matching org found.
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

    # Check internal tokens first (fast, in-memory)
    internal_org_id = _internal_tokens.get(token)
    if internal_org_id is not None:
        org = await org_repo.get_by_id(internal_org_id)
        if org:
            logger.debug("mcp_auth_internal", org_id=str(org.id))
            return org

    # Fall back to stored org token hashes
    orgs = await org_repo.get_all_with_mcp_tokens()

    for org in orgs:
        if org.mcp_token_hash and verify_password(token, org.mcp_token_hash):
            logger.debug("mcp_auth_success", org_id=str(org.id), slug=org.slug)
            return org

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired MCP token",
    )
