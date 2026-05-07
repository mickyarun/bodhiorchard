# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Developer skill profile endpoints.

Knowledge / feature endpoints retired with the legacy
``knowledge_items`` table — see :mod:`app.api.v1.features` for the
replacements (``GET /v1/features``, ``GET /v1/features/by-repo``,
``GET /v1/features/{id}``, ``GET /v1/features/contributors``).

Scan-trigger / status / cancel routes live in
``app.api.v1.scans`` (mounted at ``/v1/reposcanv2/scans``).
"""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.schemas.skills import ModuleSkill, SkillProfileRead

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
                userId=profile.user_id,
                userName=user.name if user else "Unknown",
                email=user.email if user else "",
                modules=[],
            )
        profiles_map[key].modules.append(
            ModuleSkill(
                name=profile.module,
                score=float(profile.skill_score),
                languages=profile.languages or [],
                touchCount=profile.touch_count,
            )
        )

    return list(profiles_map.values())
