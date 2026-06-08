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

"""Developer skill profile endpoints.

Knowledge / feature endpoints retired with the legacy
``knowledge_items`` table — see :mod:`app.api.v1.features` for the
replacements (``GET /v1/features``, ``GET /v1/features/by-repo``,
``GET /v1/features/{id}``, ``GET /v1/features/contributors``).

Scan-trigger / status / cancel routes live in
``app.api.v1.scans`` (mounted at ``/v1/reposcanv2/scans``).
"""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.schemas.skills import (
    SKILL_RERUN_CONFIRMATION,
    ModuleSkill,
    SkillProfileRead,
    SkillRerunRequest,
    SkillRerunResponse,
)
from app.services.skill_rerun import rerun_skill_profiles

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["skills"])


@router.get("/profiles", response_model=list[SkillProfileRead])
async def list_profiles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SkillProfileRead]:
    """List all developer skill profiles for the organization.

    Groups skill entries by user and returns module-level detail.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    sp_repo = SkillProfileRepository(db, org_id=org.id)
    rows = await sp_repo.list_with_users()

    # Group by user
    profiles_map: dict[str, SkillProfileRead] = {}
    for profile, user in rows:
        key = str(profile.user_id) if profile.user_id else profile.module
        if key not in profiles_map:
            profiles_map[key] = SkillProfileRead(
                user_id=profile.user_id,
                user_name=user.name if user else "Unknown",
                email=user.email if user else "",
                modules=[],
            )
        profiles_map[key].modules.append(
            ModuleSkill(
                name=profile.module,
                score=float(profile.skill_score),
                languages=profile.languages or [],
                touch_count=profile.touch_count,
                lines_added=profile.lines_added,
                lines_removed=profile.lines_removed,
            )
        )

    return list(profiles_map.values())


@router.post(
    "/profiles/rerun",
    response_model=SkillRerunResponse,
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
async def rerun_profiles(
    body: SkillRerunRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SkillRerunResponse:
    """Wipe and recompute every ``skill_profile`` row for the caller's org.

    Recovery path for alias-routing corruption. Walks each tracked repo
    using the same ``analyze_repo_skills`` + ``phase_e_skills`` pair the
    scan pipeline uses, but skips indexing, feature synthesis, design
    extraction, and embeddings — so it finishes in seconds rather than
    hours. ``body.confirmation`` must equal the fixed
    ``SKILL_RERUN_CONFIRMATION`` phrase to defend against accidental
    invocation from outside the UI.
    """
    # Strip on the server too — a paste from chat/email commonly carries
    # a trailing newline and the UI is not the only valid client.
    if body.confirmation.strip() != SKILL_RERUN_CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Confirmation must equal {SKILL_RERUN_CONFIRMATION!r} to "
                "proceed with a destructive skill_profiles wipe."
            ),
        )

    org = await OrganizationRepository(db).get_for_user(current_user)
    result = await rerun_skill_profiles(db, org.id, wipe=body.wipe)
    await db.commit()

    logger.info(
        "skill_profiles_rerun",
        org_id=str(org.id),
        wipe=body.wipe,
        by=current_user.email,
        profiles_deleted=result.profiles_deleted,
        profiles_upserted=result.profiles_upserted,
        repos_walked=result.repos_walked,
        unmatched_emails=result.unmatched_emails,
    )
    return SkillRerunResponse(
        profiles_deleted=result.profiles_deleted,
        profiles_upserted=result.profiles_upserted,
        unmatched_emails=result.unmatched_emails,
        repos_walked=result.repos_walked,
    )
