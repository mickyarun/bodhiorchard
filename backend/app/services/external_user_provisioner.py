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

"""Materialise stub User rows for unknown GitHub PR authors.

When a PR is ingested whose ``author_github_login`` doesn't match any
existing :class:`User.github_username` in the org, nothing surfaces in
Settings → Members for the admin to act on — the PR lands with
``author_user_id IS NULL`` and the post-close contributor breakdown
shows them as an opaque "(external)" row.

This provisioner creates a minimal-stub member instead: a non-loginable
User + an :class:`OrgToUser` membership. The admin then sees the entry
in Members and can merge it into the real person via the existing
Settings → Members → Merge flow. The merge writes the stub's primary
email as a :class:`UserEmailAlias` on the target, and the BUD-learning
alias resolver folds the contributor row into the target at read time.

The stub email follows the GitHub noreply convention
(``{login}@users.noreply.github.com``) so the alias backlink stays
human-readable. The password is a random bcrypt-hashed string so the
account can never authenticate — its only job is to surface in the
Members list for merging.
"""

from __future__ import annotations

import secrets
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.repositories.user import UserRepository

logger = structlog.get_logger(__name__)


async def ensure_user_for_github_login(
    db: AsyncSession,
    org_id: uuid.UUID,
    github_login: str,
) -> User | None:
    """Return the user with ``github_login``, creating a stub member if absent.

    Returns ``None`` only when ``github_login`` is empty/whitespace.
    Otherwise resolves in this order:

    1. Existing :class:`User` whose ``github_username`` matches → return
       as-is (active or deactivated; the caller decides what to do with
       a deactivated row).
    2. Existing user in this org with primary email matching the noreply
       convention but no ``github_username`` yet → stamp the field and
       return. Avoids creating a duplicate stub when an earlier scan
       path (e.g. skill_extraction.py auto-create from git commits)
       already provisioned the same person.
    3. Otherwise create a fresh stub User + ``OrgToUser`` membership.
    """
    login = (github_login or "").strip()
    if not login:
        return None

    user_repo = UserRepository(db)

    existing_uid = await user_repo.get_id_by_github_login(org_id, login)
    if existing_uid is not None:
        user = await db.get(User, existing_uid)
        if user is not None:
            return user

    stub_email = f"{login}@users.noreply.github.com"
    by_email = await user_repo.get_by_email_in_org(org_id, stub_email)
    if by_email is not None:
        if not by_email.github_username:
            by_email.github_username = login
            await db.flush()
        return by_email

    stub = await user_repo.create_stub_member(
        org_id,
        email=stub_email,
        name=login,
        github_username=login,
        password_hash=hash_password(secrets.token_urlsafe(24)),
    )
    logger.info(
        "external_user_provisioned",
        org_id=str(org_id),
        github_login=login,
        user_id=str(stub.id),
    )
    return stub
