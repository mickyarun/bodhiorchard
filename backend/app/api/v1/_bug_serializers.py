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

"""Bug ORM → Pydantic serialisers.

Pulled out of ``api/v1/bugs.py`` so the route file stays focused on
HTTP wiring. These helpers batch-resolve user names, BUD info, Feature
titles, and active comment counts so list / board responses stay
N+1-free.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bug import Bug
from app.repositories.bud import BUDRepository
from app.repositories.bug_comment import BugCommentRepository
from app.repositories.feature import FeatureRepository
from app.repositories.user import UserRepository
from app.schemas.bug import BugListItem, BugRead


async def bugs_to_list_items(
    db: AsyncSession,
    bugs: list[Bug],
    org_id: uuid.UUID,
) -> list[BugListItem]:
    """Serialise many bugs to BugListItem with all related names resolved."""
    user_ids: set[uuid.UUID] = set()
    bud_ids: set[uuid.UUID] = set()
    feature_ids: set[uuid.UUID] = set()
    bug_ids: list[uuid.UUID] = []
    for b in bugs:
        user_ids.add(b.reporter_id)
        if b.assignee_id:
            user_ids.add(b.assignee_id)
        if b.bud_id:
            bud_ids.add(b.bud_id)
        if b.feature_id:
            feature_ids.add(b.feature_id)
        bug_ids.append(b.id)

    user_names = await _resolve_user_names(db, org_id, user_ids)
    bud_info = await _resolve_bud_info(db, org_id, bud_ids)
    feature_titles = await _resolve_feature_titles(db, org_id, feature_ids)
    comment_counts = await BugCommentRepository(db, org_id=org_id).count_active_by_bug(bug_ids)

    return [
        BugListItem(
            id=str(b.id),
            title=b.title,
            severity=b.severity.value,
            status=b.status.value,
            bug_type=b.bug_type.value,
            module=b.module,
            bud_id=str(b.bud_id) if b.bud_id else None,
            bud_number=bud_info.get(b.bud_id, {}).get("number") if b.bud_id else None,
            feature_id=str(b.feature_id) if b.feature_id else None,
            feature_title=feature_titles.get(b.feature_id) if b.feature_id else None,
            reporter_name=user_names.get(b.reporter_id),
            assignee_id=str(b.assignee_id) if b.assignee_id else None,
            assignee_name=user_names.get(b.assignee_id) if b.assignee_id else None,
            comment_count=comment_counts.get(b.id, 0),
            created_at=b.created_at,
            updated_at=b.updated_at,
        )
        for b in bugs
    ]


async def bug_to_read(
    db: AsyncSession,
    bug: Bug,
    org_id: uuid.UUID,
) -> BugRead:
    """Serialise a single bug to BugRead with all related names resolved."""
    user_ids = {bug.reporter_id}
    if bug.assignee_id:
        user_ids.add(bug.assignee_id)
    user_names = await _resolve_user_names(db, org_id, user_ids)

    bud_number = None
    bud_title = None
    if bug.bud_id:
        bud_info = await _resolve_bud_info(db, org_id, {bug.bud_id})
        info = bud_info.get(bug.bud_id, {})
        bud_number = info.get("number") if isinstance(info, dict) else None
        bud_title = info.get("title") if isinstance(info, dict) else None

    feature_title = None
    if bug.feature_id:
        feature_titles = await _resolve_feature_titles(db, org_id, {bug.feature_id})
        feature_title = feature_titles.get(bug.feature_id)

    comment_counts = await BugCommentRepository(db, org_id=org_id).count_active_by_bug([bug.id])

    return BugRead(
        id=str(bug.id),
        title=bug.title,
        description=bug.description,
        severity=bug.severity.value,
        status=bug.status.value,
        bug_type=bug.bug_type.value,
        module=bug.module,
        linked_pr=bug.linked_pr,
        bud_id=str(bug.bud_id) if bug.bud_id else None,
        bud_number=bud_number,
        bud_title=bud_title,
        feature_id=str(bug.feature_id) if bug.feature_id else None,
        feature_title=feature_title,
        reporter_id=str(bug.reporter_id),
        reporter_name=user_names.get(bug.reporter_id),
        assignee_id=str(bug.assignee_id) if bug.assignee_id else None,
        assignee_name=user_names.get(bug.assignee_id) if bug.assignee_id else None,
        comment_count=comment_counts.get(bug.id, 0),
        resolved_at=bug.resolved_at,
        created_at=bug.created_at,
        updated_at=bug.updated_at,
    )


async def _resolve_user_names(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_ids: set[uuid.UUID],
) -> dict[uuid.UUID, str]:
    """Batch-resolve user IDs to display names."""
    if not user_ids:
        return {}
    return await UserRepository(db, org_id=org_id).get_names_by_ids(user_ids)


async def _resolve_bud_info(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_ids: set[uuid.UUID],
) -> dict[uuid.UUID, dict[str, str | int]]:
    """Batch-resolve BUD IDs to ``{number, title}`` dicts."""
    return await BUDRepository(db, org_id=org_id).get_minimal_info_by_ids(bud_ids)


async def _resolve_feature_titles(
    db: AsyncSession,
    org_id: uuid.UUID,
    feature_ids: set[uuid.UUID],
) -> dict[uuid.UUID, str]:
    """Batch-resolve Feature IDs to titles."""
    return await FeatureRepository(db, org_id=org_id).titles_by_ids(feature_ids)
