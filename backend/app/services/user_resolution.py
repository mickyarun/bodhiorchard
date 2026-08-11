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


async def walk_to_active_user(
    db: AsyncSession,
    org_id: uuid.UUID,
    user: User | None,
) -> User | None:
    """Follow the alias backlink chain until an active user is found.

    Members → Merge deactivates the source and records its primary email
    as a :class:`UserEmailAlias` on the target, so a deactivated row is a
    signpost to whoever absorbed it. Merges compose (A → B, then B → C),
    hence the loop rather than a single hop.

    This matters because a merged-away row keeps its primary email, and
    :func:`resolve_user_by_email` matches primary addresses before
    aliases — so a GitHub stub's ``{login}@users.noreply.github.com``
    resolves to the *stub* even after the merge. Walking the backlink
    turns that stale hit into the surviving member.

    Returns ``None`` when the chain dead-ends on a deactivated user with
    no alias to follow, so callers can log a miss rather than credit a
    row nobody owns. A visited set guards against alias cycles that
    would otherwise loop forever.
    """
    visited: set[uuid.UUID] = set()
    while user is not None and not user.is_active:
        if user.id in visited:
            return None
        visited.add(user.id)
        next_user = await UserRepository(db).find_user_by_alias_email(org_id, user.email)
        if next_user is None or next_user.id == user.id:
            return None
        user = next_user
    return user
