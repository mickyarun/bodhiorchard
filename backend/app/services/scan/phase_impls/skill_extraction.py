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

1. **Placing unknown authors.** Every git-author email missing from the
   org's email map goes through ``author_resolution.place_new_authors``:
   a GitHub noreply address links to the member with that login, a
   machine's default identity and an address owned by another org stay
   unmatched, and anyone else becomes a member when
   ``scan.auto_create_members`` is on (default). Unmatched authors are
   returned so the stage can surface them.

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

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user import UserRepository
from app.services.scan.author_resolution import auto_create_enabled, place_new_authors
from app.services.scan_helpers import upsert_skill_profiles


async def phase_e_skills(
    db: AsyncSession,
    org_id: uuid.UUID,
    repo_path: str,
    skill_entries: list[Any],
    email_to_user: dict[str, User],
    scan_cfg: dict[str, Any],
) -> tuple[int, list[str]]:
    """Git skill analysis — place unknown authors, then upsert profiles.

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
            the caller sees linked and freshly-created members in
            subsequent iterations.
        scan_cfg: Scan configuration dict from org config.

    Returns:
        Tuple of (profiles_count, unmatched_emails).
    """
    del repo_path  # accepted for the legacy signature; analysis happens upstream
    if skill_entries:
        user_repo = UserRepository(db)
        _refresh_email_map(email_to_user, await user_repo.get_email_map(org_id))
        await place_new_authors(
            db,
            org_id,
            ((entry.email, entry.author_name) for entry in skill_entries),
            email_to_user,
            auto_create=auto_create_enabled(scan_cfg),
        )
        _refresh_email_map(email_to_user, await user_repo.get_email_map(org_id))

    count, unmatched = await upsert_skill_profiles(db, org_id, skill_entries, email_to_user)
    return count, unmatched


def _refresh_email_map(target: dict[str, User], fresh: dict[str, User]) -> None:
    """Replace ``target``'s contents with ``fresh`` in place."""
    target.clear()
    target.update(fresh)
