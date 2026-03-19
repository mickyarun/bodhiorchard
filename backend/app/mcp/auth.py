"""MCP token verification for FlowDev tool calls from Claude Code."""

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
# consumed by verify_mcp_token(), cleaned up by revoke_internal_mcp_token().
_internal_tokens: dict[str, uuid.UUID] = {}


def create_internal_mcp_token(org_id: uuid.UUID) -> str:
    """Create a temporary MCP token for internal use (e.g. scan pipeline).

    The token is stored in-memory and valid until explicitly revoked.

    Args:
        org_id: The organization UUID to associate with the token.

    Returns:
        The plaintext token string.
    """
    token = secrets.token_urlsafe(32)
    _internal_tokens[token] = org_id
    return token


def revoke_internal_mcp_token(token: str) -> None:
    """Revoke a previously issued internal MCP token.

    Args:
        token: The token to revoke.
    """
    _internal_tokens.pop(token, None)


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
