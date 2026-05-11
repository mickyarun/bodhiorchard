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

"""HTTP endpoints for the Features tab.

Replaces ``/v1/skills/knowledge`` (retired with the legacy
``knowledge_items`` table). All endpoints are org-scoped via the
authenticated user, paginate via the existing ``limit`` / ``offset``
convention, and never leak soft-deleted (``is_active=False``) rows.

Mounted at ``/api/v1/features`` from :mod:`app.api.router`.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.feature import Feature
from app.models.feature_to_repo import FeatureToRepo, FeatureToRepoRole
from app.models.user import User
from app.repositories.dev_activity import DevActivityLogRepository
from app.repositories.feature_match_log import FeatureMatchLogRepository
from app.repositories.feature_reads import FeatureReadRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.feature import (
    BackendLinkRead,
    FeatureMatchLogRead,
    FeaturePage,
    FeatureRead,
    FeaturesByRepoRead,
    PrimaryLinkRead,
    RepoContributorRead,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["features"])


def _build_feature_read(
    feature: Feature,
    *,
    repo_names: dict[uuid.UUID, str],
) -> FeatureRead | None:
    """Assemble a ``FeatureRead`` from the ORM row + a repo-name lookup.

    Returns ``None`` when the feature has no PRIMARY junction — that
    is a data-integrity violation that the audit will surface; the
    API simply skips it so a single bad row does not blank the page.
    """
    primary_row: FeatureToRepo | None = None
    backend_rows: list[FeatureToRepo] = []
    for link in feature.repo_links:
        if link.role == FeatureToRepoRole.PRIMARY:
            primary_row = link
        elif link.role == FeatureToRepoRole.BACKEND:
            backend_rows.append(link)
    if primary_row is None:
        logger.warning(
            "feature_missing_primary_link",
            feature_id=str(feature.id),
            org_id=str(feature.org_id),
        )
        return None
    primary = PrimaryLinkRead(
        repoId=primary_row.repo_id,
        repoName=repo_names.get(primary_row.repo_id, "Unknown"),
        codeLocations=primary_row.code_locations,
    )
    backend_links = [
        BackendLinkRead(
            repoId=row.repo_id,
            repoName=repo_names.get(row.repo_id, "Unknown"),
            apiPaths=list(row.api_paths or []),
            codeLocations=row.code_locations,
        )
        for row in backend_rows
    ]
    return FeatureRead(
        id=feature.id,
        featureTitle=feature.feature_title,
        description=feature.description,
        capabilities=feature.capabilities or {},
        clusterNames=list(feature.cluster_names or []),
        tags=list(feature.tags or []),
        featureStatus=feature.feature_status,
        source=feature.source,
        sourceRef=feature.source_ref,
        synthesizedAt=feature.synthesized_at,
        primary=primary,
        backendLinks=backend_links,
    )


async def _repo_name_lookup(db: AsyncSession, *, org_id: uuid.UUID) -> dict[uuid.UUID, str]:
    """Return a ``{repo_id: name}`` dict for every active tracked repo."""
    tr_repo = TrackedRepoRepository(db, org_id=org_id)
    repos = await tr_repo.list_active()
    return {r.id: r.name for r in repos}


@router.get("", response_model=FeaturePage)
async def list_features(
    repo_id: uuid.UUID | None = Query(default=None, alias="repoId"),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=24, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeaturePage:
    """Paginated active features for the authenticated user's org.

    Filter shape mirrors the legacy ``/v1/skills/knowledge`` endpoint
    so frontend pagination state translates one-to-one. Only
    ``is_active=True`` rows are returned.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    reads = FeatureReadRepository(db, org_id=org.id)
    title_query = q.strip() if q and q.strip() else None
    features = await reads.list_with_links(
        repo_id=repo_id, q=title_query, limit=limit, offset=offset
    )
    total = await reads.count_with_links(repo_id=repo_id, q=title_query)
    repo_names = await _repo_name_lookup(db, org_id=org.id)
    items = [r for r in (_build_feature_read(f, repo_names=repo_names) for f in features) if r]
    return FeaturePage(items=items, total=total)


@router.get("/by-repo", response_model=list[FeaturesByRepoRead])
async def list_features_by_repo(
    repo_id: uuid.UUID | None = Query(default=None, alias="repoId"),
    q: str | None = Query(default=None, max_length=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FeaturesByRepoRead]:
    """Features grouped by their PRIMARY repo for the redesigned tab.

    No pagination — the redesigned UI is repo-grouped and lazy-loads
    the per-repo top contributors panel separately. Empty repos are
    omitted from the response.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    reads = FeatureReadRepository(db, org_id=org.id)
    title_query = q.strip() if q and q.strip() else None
    # Fetch all matching active features; the page-level cap is plenty
    # for the grouped view (the UI doesn't need pagination here).
    features = await reads.list_with_links(repo_id=repo_id, q=title_query, limit=500, offset=0)
    repo_names = await _repo_name_lookup(db, org_id=org.id)
    grouped: dict[uuid.UUID, list[FeatureRead]] = defaultdict(list)
    for f in features:
        read = _build_feature_read(f, repo_names=repo_names)
        if read is not None:
            grouped[read.primary.repo_id].append(read)
    return [
        FeaturesByRepoRead(
            repoId=rid,
            repoName=repo_names.get(rid, "Unknown"),
            featureCount=len(items),
            features=items,
        )
        for rid, items in grouped.items()
    ]


@router.get("/contributors", response_model=list[RepoContributorRead])
async def top_contributors(
    repo_id: uuid.UUID = Query(alias="repoId"),
    limit: int = Query(default=5, ge=1, le=25),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RepoContributorRead]:
    """All-time top contributors for one repo's commit activity."""
    org = await OrganizationRepository(db).get_for_user(current_user)
    activity_repo = DevActivityLogRepository(db, org_id=org.id)
    rows = await activity_repo.top_contributors_for_repo(repo_id, limit=limit)
    return [
        RepoContributorRead(
            userId=row.user_id,
            actorName=row.actor_name,
            commitCount=row.commit_count,
            filesChanged=row.files_changed,
        )
        for row in rows
    ]


@router.get("/match-debug", response_model=list[FeatureMatchLogRead])
async def list_match_debug(
    repo_id: uuid.UUID | None = Query(default=None, alias="repoId"),
    since: datetime | None = Query(default=None),
    match_via: str | None = Query(default=None, alias="matchVia"),
    score_min: float | None = Query(default=None, alias="scoreMin", ge=0.0, le=1.0),
    score_max: float | None = Query(default=None, alias="scoreMax", ge=0.0, le=1.0),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FeatureMatchLogRead]:
    """Recent reconciler match decisions for borderline-threshold tuning.

    Default surface for tuning the 0.7 (Jaccard) and 0.85 (cosine)
    cutoffs: filter by ``matchVia=jaccard&scoreMin=0.6&scoreMax=0.79``
    or ``matchVia=cosine&scoreMin=0.78&scoreMax=0.86`` to inspect
    recent borderline decisions and judge whether the threshold should
    move. Newest first, capped at 1000 rows.
    """
    if match_via is not None and match_via not in {"signature", "jaccard", "cosine", "insert"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="matchVia must be one of: signature, jaccard, cosine, insert.",
        )
    org = await OrganizationRepository(db).get_for_user(current_user)
    repo = FeatureMatchLogRepository(db, org_id=org.id)
    rows = await repo.list_for_repo(
        repo_id=repo_id,
        since=since,
        match_via=match_via,
        score_min=score_min,
        score_max=score_max,
        limit=limit,
    )
    return [
        FeatureMatchLogRead(
            id=row.id,
            repoId=row.repo_id,
            headSha=row.head_sha,
            matchVia=row.match_via,
            score=row.score,
            featureTitle=row.feature_title,
            matchedFeatureId=row.matched_feature_id,
            decision=row.decision,
            createdAt=row.created_at,
        )
        for row in rows
    ]


@router.get("/{feature_id}", response_model=FeatureRead)
async def get_feature(
    feature_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeatureRead:
    """Fetch one feature with all junction rows resolved.

    404 when the feature does not exist in the user's org. Soft-deleted
    rows are still returnable here so revival audits can inspect them.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    feature = await FeatureReadRepository(db, org_id=org.id).get_with_links(feature_id)
    if feature is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feature not found.",
        )
    repo_names = await _repo_name_lookup(db, org_id=org.id)
    read = _build_feature_read(feature, repo_names=repo_names)
    if read is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Feature is missing its PRIMARY junction row — run the audit.",
        )
    return read
