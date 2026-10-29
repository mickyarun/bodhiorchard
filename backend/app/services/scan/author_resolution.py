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

"""Place git authors the org's email map doesn't know yet.

The email map already covers primary emails, aliases (which is where a
member merge records the merged-away address) and deactivated members, so
an admin's earlier merge or removal is honoured before this module runs.
For each author still unknown, in order:

1. A GitHub noreply address whose login matches a member's
   ``github_username`` links to that member and is recorded as an alias.
2. A machine's default identity (``name@Some-MacBook.local``) is left
   unmatched. No person owns it, so an admin merges it by hand; it still
   appears in the scan's unmatched authors.
3. An address that belongs to an account in another org is left unmatched.
4. Anyone else becomes a new member, when the org allows auto-creation.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Awaitable, Iterable, Mapping
from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import OrgToUser, User
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
from app.services.scan.author_addresses import github_noreply_login, is_machine_local
from app.services.user_resolution import walk_to_active_user

logger = structlog.get_logger(__name__)


def auto_create_enabled(scan_cfg: Mapping[str, Any]) -> bool:
    """The org's "create members from git authors" switch; on unless turned off."""
    return bool(scan_cfg.get("auto_create_members", True))


async def org_auto_creates_members(db: AsyncSession, org_id: uuid.UUID) -> bool:
    """Read the switch from the org's saved scan settings."""
    org = await OrganizationRepository(db).get_by_id(org_id)
    scan_cfg = (org.config or {}).get("scan") or {} if org else {}
    return auto_create_enabled(scan_cfg)


async def place_new_authors(
    db: AsyncSession,
    org_id: uuid.UUID,
    authors: Iterable[tuple[str, str]],
    email_to_user: dict[str, User],
    *,
    auto_create: bool,
) -> None:
    """Link or create members for ``(email, name)`` authors missing from ``email_to_user``.

    Linked authors are added to ``email_to_user``; created members appear
    once the caller reloads the map.
    """
    users = UserRepository(db)
    seen: set[str] = set()
    for email, name in authors:
        key = email.lower()
        if key in email_to_user or key in seen:
            continue
        seen.add(key)
        member = await _member_for_noreply(db, users, org_id, email)
        if member is not None:
            if await _insert_once(db, users.add_email_alias(org_id, member.id, email)):
                email_to_user[key] = member
        elif is_machine_local(email):
            logger.info("scan_author_machine_local_left_for_admin", org_id=str(org_id))
        elif await users.get_by_email(email) is not None:
            # Emails are unique across orgs: inserting would fail the stage,
            # and adding that account here would give it access to this org.
            logger.info("scan_author_belongs_to_another_org", org_id=str(org_id))
        elif auto_create:
            await _insert_once(db, _create_member(db, org_id, email, name))


async def _insert_once(db: AsyncSession, insert: Awaitable[object]) -> bool:
    """Run ``insert`` in a savepoint; ``False`` if another scan inserted the row first.

    Repos in one scan run concurrently, each in its own session, so two of
    them can meet the same new author. The loser skips it instead of failing
    its whole stage; the next scan finds the winner's row in the email map.
    """
    try:
        async with db.begin_nested():
            await insert
            await db.flush()
    except IntegrityError:
        logger.info("scan_author_inserted_by_concurrent_repo")
        return False
    return True


async def _member_for_noreply(
    db: AsyncSession, users: UserRepository, org_id: uuid.UUID, email: str
) -> User | None:
    """The member whose GitHub login the noreply ``email`` names, if any.

    A merged-away stub keeps its login, so the match is walked to whoever
    absorbed it. A member an admin deactivated is still returned: linking
    to them keeps the scan from creating the same person again.
    """
    login = github_noreply_login(email)
    user_id = await users.get_id_by_github_login(org_id, login) if login else None
    if user_id is None:
        return None
    member = await users.get_by_id(user_id)
    return await walk_to_active_user(db, org_id, member) or member


async def _create_member(db: AsyncSession, org_id: uuid.UUID, email: str, name: str) -> None:
    user = User(
        email=email,
        name=name,
        # Random and never shown: scan-created contributors can't sign in
        # until an admin sets a password or merges them.
        password_hash=hash_password(secrets.token_urlsafe(24)),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    db.add(OrgToUser(user_id=user.id, org_id=org_id))
