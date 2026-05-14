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

"""BUD ↔ Feature linkage endpoints.

Manual override + read endpoints for the link table the PM agent
populates automatically. The frontend uses these to (a) display which
existing features the requirement touches and (b) let a human correct
the PM agent's choices before downstream stages run.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud_feature_link import BUDFeatureLinkSource
from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo, FeatureToRepoRole
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.bud_feature_link import BUDFeatureLinkRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.bud_linked_features import (
    LinkedFeatureRead,
    LinkFeaturesRequest,
    LinkFeaturesResponse,
)
from app.services.bud_timeline import record_event

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=list[LinkedFeatureRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_linked_features(
    bud_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[LinkedFeatureRead]:
    """List every existing feature this BUD is linked to."""
    await _require_bud(bud_id, current_user.org_id, db)

    link_repo = BUDFeatureLinkRepository(db, org_id=current_user.org_id)
    features = await link_repo.list_features_for_bud(bud_id)
    raw_links = await link_repo.list_links_for_bud(bud_id)
    link_metadata = {link.feature_id: link for link in raw_links}

    repo_names = await _repo_id_to_name(db, current_user.org_id)

    out: list[LinkedFeatureRead] = []
    for feature in features:
        link = link_metadata.get(feature.id)
        primary = _primary_link(feature)
        out.append(
            LinkedFeatureRead(
                id=feature.id,
                title=feature.feature_title,
                link_type=(link.link_type.value if link else "touches"),
                source=(link.source.value if link else "pm_agent"),
                repo_id=(primary.repo_id if primary else None),
                repo_name=(repo_names.get(primary.repo_id) if primary else None),
                code_locations=(primary.code_locations if primary else None),
            )
        )
    return out


@router.post(
    "",
    response_model=LinkFeaturesResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def link_features(
    bud_id: uuid.UUID,
    body: LinkFeaturesRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> LinkFeaturesResponse:
    """Link the BUD to one or more existing features (manual override)."""
    await _require_bud(bud_id, current_user.org_id, db)

    link_repo = BUDFeatureLinkRepository(db, org_id=current_user.org_id)
    inserted = await link_repo.link_features(
        bud_id,
        list(dict.fromkeys(body.feature_ids)),
        source=BUDFeatureLinkSource.MANUAL,
    )
    # Record one timeline event per manual link request (not per inserted id),
    # so noisy multi-pick clicks show as a single audit row. Resolve titles
    # so the timeline can name the features instead of opaque UUIDs.
    if inserted:
        title_map = await link_repo.titles_by_ids(inserted)
        await record_event(
            db,
            current_user.org_id,
            bud_id,
            "feature_linked",
            actor_id=current_user.id,
            actor_name=current_user.name,
            detail={
                "feature_ids": [str(fid) for fid in inserted],
                "feature_titles": [title_map.get(fid, "") for fid in inserted],
                "count": len(inserted),
            },
        )
    await db.commit()
    logger.info(
        "linked_features_manual",
        bud_id=str(bud_id),
        requested=len(body.feature_ids),
        inserted=len(inserted),
    )
    return LinkFeaturesResponse(inserted_count=len(inserted), inserted_feature_ids=inserted)


@router.delete(
    "/{feature_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def unlink_feature(
    bud_id: uuid.UUID,
    feature_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a single BUD ↔ Feature link."""
    await _require_bud(bud_id, current_user.org_id, db)

    link_repo = BUDFeatureLinkRepository(db, org_id=current_user.org_id)
    removed = await link_repo.unlink_features(bud_id, [feature_id])
    if removed == 0:
        # No commit needed — nothing changed. 404 surfaces the no-op cleanly.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Link not found",
        )
    # Look up the title so the timeline names the feature instead of a UUID.
    # The Feature row isn't deleted (only the link row is), so this resolves
    # cleanly after the unlink.
    title_map = await link_repo.titles_by_ids([feature_id])
    await record_event(
        db,
        current_user.org_id,
        bud_id,
        "feature_unlinked",
        actor_id=current_user.id,
        actor_name=current_user.name,
        detail={
            "feature_id": str(feature_id),
            "feature_title": title_map.get(feature_id, ""),
        },
    )
    await db.commit()


async def _require_bud(bud_id: uuid.UUID, org_id: uuid.UUID, db: AsyncSession) -> None:
    """404 if the BUD doesn't exist or belongs to a different org."""
    bud_repo = BUDRepository(db, org_id=org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")


async def _repo_id_to_name(db: AsyncSession, org_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Map ``repo_id`` → ``name`` for every active repo in the org."""
    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    triples = await repo_repo.get_active_id_path_name()
    return {rid: name for rid, _path, name in triples}


def _primary_link(feature: Feature) -> FeatureToRepo | None:
    """Return the PRIMARY-role :class:`FeatureToRepo` row, if any."""
    for link in feature.repo_links:
        if link.role == FeatureToRepoRole.PRIMARY:
            return link
    return None
