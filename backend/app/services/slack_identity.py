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

"""Who may change a member's Slack link.

A Slack link identifies who clicked Approve on a leave request, so changing
someone's link is treated like managing their account: you can't relink a
member who has access you don't (e.g. HR, unless you're the owner), and a
person who belongs to more than one org can't be relinked from just one of
them (the link is shared across their orgs).
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.user import User
from app.repositories.slack_identity import SlackIdentityRepository
from app.services.role_grants import assert_can_manage_member


async def assert_can_relink(
    db: AsyncSession,
    *,
    actor: PermissionSet,
    target: User,
    org_id: uuid.UUID,
    slack_id: str | None,
) -> None:
    """Raise 403/409 unless ``actor`` may set ``target``'s Slack link to ``slack_id``.

    ``target`` must carry the transient role attributes from
    ``UserRepository.get_by_id_with_membership``.
    """
    await assert_can_manage_member(db, actor=actor, target=target)
    identities = SlackIdentityRepository(db)
    if await identities.membership_count(target.id) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{target.name} belongs to another organization too, so their Slack "
            "link can't be changed from here.",
        )
    if slack_id is None:
        return
    others = set(await identities.members_with_slack_id(org_id, slack_id)) - {target.id}
    if others:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That Slack account is already linked to someone else here.",
        )
