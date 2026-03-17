"""MCP token verification for FlowDev tool calls from Claude Code."""

import structlog
from fastapi import Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models.organization import Organization

logger = structlog.get_logger(__name__)


async def verify_mcp_token(
    db: "AsyncSession",
    authorization: str = Header(),
) -> Organization:
    """Verify the bearer token from an MCP request against org tokens.

    Looks up the organization by iterating orgs and checking token hash.
    In production, consider a lookup table or cache for performance.

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

    result = await db.execute(
        select(Organization).where(Organization.mcp_token_hash.is_not(None))
    )
    orgs = result.scalars().all()

    for org in orgs:
        if org.mcp_token_hash and verify_password(token, org.mcp_token_hash):
            logger.debug("mcp_auth_success", org_id=str(org.id), slug=org.slug)
            return org

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired MCP token",
    )
