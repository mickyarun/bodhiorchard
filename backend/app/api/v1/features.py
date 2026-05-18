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
authenticated user and paginate via the existing ``limit`` /
``offset`` convention.

The Features tab's visibility filter is driven by a single
``?mode=<view_mode>`` query param:

* ``all`` (default) — every active row, shipped or in-progress.
* ``active`` — only shipped / live rows (excludes BUD WIP).
* ``in_progress`` — only BUD work-in-progress rows.
* ``deactivated`` — only soft-deleted rows.

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
from app.services.feature_presentation import resolve_pr_meta_for_features

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["features"])


def _build_feature_read(
    feature: Feature,
    *,
    repo_names: dict[uuid.UUID, str],
    pr_meta_by_sha: dict[str, tuple[int, str | None]] | None = None,
) -> FeatureRead | None:
    """Assemble a ``FeatureRead`` from the ORM row + a repo-name lookup.

    Returns ``None`` when the feature has no PRIMARY junction — that
    is a data-integrity violation that the audit will surface; the
    API simply skips it so a single bad row does not blank the page.

    ``pr_meta_by_sha`` is an optional bulk-resolved lookup table from
    any merge SHA on the feature (created / last-seen / deactivated)
    to ``(github_pr_number, html_url)``. The caller pre-builds this
    in one query so a page of N features renders without N+1 PR
    lookups. SHAs without a tracked PR fall back to null PR fields;
    the UI then renders the bare short SHA.
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
    created_pr = _lookup_pr(feature.created_at_sha, pr_meta_by_sha)
    last_seen_pr = _lookup_pr(feature.last_seen_sha, pr_meta_by_sha)
    deactivated_pr = _lookup_pr(feature.deactivated_at_sha, pr_meta_by_sha)
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
        createdAt=feature.created_at,
        createdAtSha=feature.created_at_sha,
        createdPrNumber=created_pr[0],
        createdPrUrl=created_pr[1],
        creationMode=_derive_creation_mode(feature, created_pr_number=created_pr[0]),
        updatedAt=feature.updated_at,
        lastSeenSha=feature.last_seen_sha,
        lastSeenPrNumber=last_seen_pr[0],
        lastSeenPrUrl=last_seen_pr[1],
        isActive=feature.is_active,
        deactivatedAt=feature.deactivated_at,
        deactivatedAtSha=feature.deactivated_at_sha,
        deactivatedPrNumber=deactivated_pr[0],
        deactivatedPrUrl=deactivated_pr[1],
    )


def _lookup_pr(
    sha: str | None,
    pr_meta_by_sha: dict[str, tuple[int, str | None]] | None,
) -> tuple[int | None, str | None]:
    """Resolve one SHA against the bulk-loaded PR dict.

    Returns ``(None, None)`` when the SHA is null or absent from the
    lookup. Pulled out so each FeatureRead field doesn't repeat the
    null/missing dance inline. Returns an explicit 2-tuple rather than
    the source tuple so a future broadening of ``map_shas_to_pr_meta``'s
    value shape doesn't silently widen this function's return type.
    """
    if not sha or not pr_meta_by_sha:
        return None, None
    meta = pr_meta_by_sha.get(sha)
    if meta is None:
        return None, None
    return meta[0], meta[1]


def _derive_creation_mode(feature: Feature, *, created_pr_number: int | None) -> str:
    """Label the row's creation context for the UI chip.

    * ``bud`` — BUD-lifecycle authored the row (no PRIMARY junction
      involvement, but ``source`` carries the marker).
    * ``narrow_synth`` — ``created_at_sha`` resolves to a tracked PR
      → a PR-merge narrow synthesis created it.
    * ``full_scan`` — ``created_at_sha`` is set but doesn't match any
      tracked PR → a baseline full scan walked the repo and Claude
      synthesised it (the scan ran against a SHA that wasn't a PR
      merge, e.g. the initial onboard).
    * ``unknown`` — ``created_at_sha`` is null. Either the row predates
      this column (all pre-Phase-5-fix features) or the BUD path
      didn't carry one.
    """
    if feature.source == "bud":
        return "bud"
    if feature.created_at_sha is None:
        return "unknown"
    return "narrow_synth" if created_pr_number is not None else "full_scan"


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
    mode: str = Query(default="all", pattern="^(all|active|in_progress|deactivated)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FeaturePage:
    """Paginated features for the authenticated user's org.

    ``mode`` selects the view: ``all`` / ``active`` / ``in_progress``
    / ``deactivated``. Pagination state translates one-to-one with the
    legacy ``/v1/skills/knowledge`` shape. The regex on ``mode``
    rejects unknown values at the FastAPI layer so bad clients get a
    422 instead of falling through to the safety-default ``all``.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    reads = FeatureReadRepository(db, org_id=org.id)
    title_query = q.strip() if q and q.strip() else None
    features = await reads.list_with_links(
        repo_id=repo_id,
        q=title_query,
        limit=limit,
        offset=offset,
        view_mode=mode,
    )
    total = await reads.count_with_links(
        repo_id=repo_id,
        q=title_query,
        view_mode=mode,
    )
    repo_names = await _repo_name_lookup(db, org_id=org.id)
    pr_meta = await resolve_pr_meta_for_features(db, org_id=org.id, features=features)
    items = [
        r
        for r in (
            _build_feature_read(f, repo_names=repo_names, pr_meta_by_sha=pr_meta) for f in features
        )
        if r
    ]
    return FeaturePage(items=items, total=total)


@router.get("/by-repo", response_model=list[FeaturesByRepoRead])
async def list_features_by_repo(
    repo_id: uuid.UUID | None = Query(default=None, alias="repoId"),
    q: str | None = Query(default=None, max_length=200),
    mode: str = Query(default="all", pattern="^(all|active|in_progress|deactivated)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FeaturesByRepoRead]:
    """Features grouped by their PRIMARY repo for the redesigned tab.

    No pagination — the redesigned UI is repo-grouped and lazy-loads
    the per-repo top contributors panel separately. Empty repos are
    omitted from the response. ``mode`` mirrors the flat-list endpoint
    above.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    reads = FeatureReadRepository(db, org_id=org.id)
    title_query = q.strip() if q and q.strip() else None
    # Fetch all matching features; the page-level cap is plenty for
    # the grouped view (the UI doesn't need pagination here).
    features = await reads.list_with_links(
        repo_id=repo_id,
        q=title_query,
        limit=500,
        offset=0,
        view_mode=mode,
    )
    repo_names = await _repo_name_lookup(db, org_id=org.id)
    pr_meta = await resolve_pr_meta_for_features(db, org_id=org.id, features=features)
    grouped: dict[uuid.UUID, list[FeatureRead]] = defaultdict(list)
    for f in features:
        read = _build_feature_read(f, repo_names=repo_names, pr_meta_by_sha=pr_meta)
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
    pr_meta = await resolve_pr_meta_for_features(db, org_id=org.id, features=[feature])
    read = _build_feature_read(feature, repo_names=repo_names, pr_meta_by_sha=pr_meta)
    if read is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Feature is missing its PRIMARY junction row — run the audit.",
        )
    return read
