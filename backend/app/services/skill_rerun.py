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

"""Wipe and recompute ``skill_profiles`` for one organization.

Reuses the production scan-pipeline ``skill_extraction`` stage
(``analyze_repo_skills`` + ``phase_e_skills``) without re-running code
indexing, feature synthesis, design extraction, or embedding generation
— none of which the email-alias fix affects. Roughly a 30-second
operation on a 20-repo org versus a multi-hour full rescan.

Surfaces both as a Danger Zone action in Settings → Code (HTTP) and as
the operational primitive any future CLI/admin tool can wrap.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.user import UserRepository
from app.services.git_analyzer import analyze_repo_skills
from app.services.scan.phase_impls.skill_extraction import phase_e_skills
from app.services.scan_helpers import load_feature_map

logger = structlog.get_logger(__name__)


@dataclass
class SkillRerunResult:
    """Per-org outcome of a wipe-and-recompute run."""

    profiles_deleted: int
    profiles_upserted: int
    unmatched_emails: int
    repos_walked: int


async def rerun_skill_profiles(
    db: AsyncSession,
    org_id: uuid.UUID,
    *,
    wipe: bool,
) -> SkillRerunResult:
    """Walk every active tracked repo for ``org_id`` and rebuild skill_profiles.

    ``wipe`` first deletes every existing row for the org (required when
    fixing alias-routing corruption — without it, orphan rows under
    previously-deactivated users would survive). The walk uses each
    repo's ``develop_branch`` (Gitflow) falling back to ``main_branch``,
    matching the production stage's branch precedence.

    The caller is responsible for the surrounding ``db.commit()`` — this
    function only flushes per repo (to release SQL buffers, not to make
    progress durable). A mid-walk exception that escapes the caller
    rolls back the entire transaction including the wipe; reruns are
    safe and idempotent. If true per-repo durability becomes important,
    wrap each iteration in ``db.begin_nested()``.
    """
    sp_repo = SkillProfileRepository(db, org_id=org_id)
    deleted = await sp_repo.delete_all_for_org() if wipe else 0

    # Alias-aware. Loaded once, mutated in place by phase_e_skills as
    # new members get auto-created — must NOT be rebound below.
    email_to_user = await UserRepository(db).get_email_map(org_id)

    repos = await TrackedRepoRepository(db, org_id=org_id).list_active()
    total_profiles = 0
    total_unmatched = 0
    for repo in repos:
        branch = repo.develop_branch or repo.main_branch
        feature_map = await load_feature_map(db, org_id, repo.id)
        entries = await analyze_repo_skills(repo.path, branch=branch, feature_map=feature_map)
        count, unmatched = await phase_e_skills(
            db=db,
            org_id=org_id,
            repo_path=repo.path,
            skill_entries=entries,
            email_to_user=email_to_user,
            scan_cfg={"auto_create_members": True},
        )
        await db.flush()
        total_profiles += count
        total_unmatched += len(unmatched)
        logger.info(
            "skill_rerun_repo_done",
            org_id=str(org_id),
            repo=repo.name,
            profiles=count,
            unmatched=len(unmatched),
        )

    return SkillRerunResult(
        profiles_deleted=deleted,
        profiles_upserted=total_profiles,
        unmatched_emails=total_unmatched,
        repos_walked=len(repos),
    )
