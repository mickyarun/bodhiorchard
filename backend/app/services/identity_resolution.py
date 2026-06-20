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

"""Resolve a git/GitHub identity to a single canonical Bodhiorchard user.

Code-review and commit attribution arrive as a GitHub login and/or a
commit email. Either can fail to resolve on its own — a contributor whose
``users.github_username`` was never filled in (the live BUD-029 case) is
invisible to login lookup but still reachable by email/alias. This helper
tries both, in order, so SP attribution credits the right person instead
of silently dropping them.

Member-merge consolidates alternate emails onto the target user as
``user_email_aliases`` rows, so the email path already follows a merge
through :func:`resolve_user_by_email`.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user import UserRepository
from app.services.user_resolution import resolve_user_by_email

logger = structlog.get_logger(__name__)


async def resolve_canonical_user(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    github_login: str | None = None,
    email: str | None = None,
) -> uuid.UUID | None:
    """Resolve a GitHub login and/or email to one canonical user_id in the org.

    Tries the GitHub login first (``users.github_username``), then the email
    (primary address, then alias / merged identity). Returns ``None`` when
    neither resolves so callers can log a miss rather than mis-credit.
    """
    if github_login:
        user_id = await UserRepository(db).get_id_by_github_login(org_id, github_login)
        if user_id is not None:
            return user_id

    if email:
        user = await resolve_user_by_email(db, org_id, email)
        if user is not None:
            return user.id

    logger.debug(
        "canonical_user_unresolved",
        org_id=str(org_id),
        github_login=github_login,
        email=email,
    )
    return None
