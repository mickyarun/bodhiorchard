"""Shared user resolution logic for mapping emails to Bodhiorchard users.

Used by git hook endpoints and Claude Code hook handlers to resolve
commit authors and session owners to platform user IDs.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserEmailAlias
from app.repositories.user import UserRepository

logger = structlog.get_logger(__name__)


async def resolve_user_by_email(
    db: AsyncSession,
    org_id: uuid.UUID,
    email: str,
) -> User | None:
    """Resolve an email address to a Bodhiorchard user within an organization.

    Checks the primary user email first, then falls back to email aliases.

    Args:
        db: The async database session.
        org_id: Organization UUID to scope the lookup.
        email: Email address to resolve.

    Returns:
        The matched User, or None if no match found.
    """
    if not email:
        return None

    user_repo = UserRepository(db)
    user = await user_repo.get_by_email_in_org(org_id, email)
    if user:
        return user

    # Fall back to email aliases (devs may commit with different emails)
    alias_result = await db.execute(
        select(UserEmailAlias).where(
            UserEmailAlias.org_id == org_id,
            UserEmailAlias.email == email,
        )
    )
    alias = alias_result.scalar_one_or_none()
    if alias:
        user = await db.get(User, alias.user_id)
        if user:
            logger.debug(
                "user_resolved_via_alias",
                email=email,
                user_id=str(user.id),
                org_id=str(org_id),
            )
            return user

    return None
