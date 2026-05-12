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

"""Phase E — extract skill profiles from one repo's git history.

The git-log walk lives in ``app.services.git_analyzer.analyze_repo_skills``;
this module is the bridge between that analyser and the database.

Two responsibilities:

1. **Optional member auto-creation.** When ``scan.auto_create_members``
   is on (default), every unique git-author email that is not already
   a ``User`` row triggers an INSERT + ``OrgToUser`` membership. The
   defaulted password is a placeholder — these accounts can't log in
   until the operator resets the password from Settings → Team. With
   the flag off, unknown authors are skipped and surface in
   ``UnmatchedAuthorsError`` from the orchestrator.

2. **Mutating the caller's email map in place.** The map flows from
   ``scan_pipeline.run_scan_pipeline`` into every per-repo iteration
   so a member created during repo N is visible during repo N+1.
   Rebinding the local would detach it from the caller's reference;
   ``_refresh_email_map`` clears + updates instead. (See the
   "self-clearing" bug history in ``BODHIORCHARD-ARCHITECTURE.md``.)
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import OrgToUser, User, UserRole
from app.repositories.user import UserRepository
from app.services.scan_helpers import upsert_skill_profiles

logger = structlog.get_logger(__name__)


async def phase_e_skills(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_path: str,
    skill_entries: list[Any],
    email_to_user: dict[str, User],
    scan_cfg: dict[str, Any],
) -> tuple[int, list[str]]:
    """Phase E: Git skill analysis — optionally auto-create members, then upsert profiles.

    ``email_to_user`` is mutated in-place so the caller's reference stays
    valid for later repos in the same scan. Rebinding would detach the
    dict from the closure that owns it and leave subsequent repos
    matching against a stale copy.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        repo_path: Absolute path to the repository.
        skill_entries: Skill entries from ``analyze_repo_skills()``.
        email_to_user: Lowercase email → User map, mutated in place so
            the caller sees freshly-created users (when auto-create is
            on) in subsequent iterations.
        scan_cfg: Scan configuration dict from org config.

    Returns:
        Tuple of (profiles_count, unmatched_emails).
    """
    del repo_path  # accepted for the legacy signature; analysis happens upstream
    user_repo = UserRepository(db)

    # Auto-create members from git authors if enabled. When disabled, the
    # passed-in ``email_to_user`` is used as-is — existing members still
    # get their skills linked; only unknown authors are skipped.
    auto_create = scan_cfg.get("auto_create_members", True)
    if auto_create and skill_entries:
        _refresh_email_map(email_to_user, await user_repo.get_email_map(org_id))
        seen_emails: set[str] = set()
        for entry in skill_entries:
            email_lower = entry.email.lower()
            if email_lower in email_to_user or email_lower in seen_emails:
                continue
            seen_emails.add(email_lower)
            new_user = User(
                email=entry.email,
                name=entry.author_name,
                password_hash=hash_password("changeme123"),
                is_active=True,
            )
            db.add(new_user)
            await db.flush()
            # Create org membership for the auto-created user
            membership = OrgToUser(user_id=new_user.id, org_id=org_id, role=UserRole.DEVELOPER)
            db.add(membership)
        await db.flush()
        _refresh_email_map(email_to_user, await user_repo.get_email_map(org_id))

    count, unmatched = await upsert_skill_profiles(db, org_id, skill_entries, email_to_user)
    return count, unmatched


def _refresh_email_map(target: dict[str, User], fresh: dict[str, User]) -> None:
    """Replace ``target``'s contents with ``fresh`` in place."""
    target.clear()
    target.update(fresh)
