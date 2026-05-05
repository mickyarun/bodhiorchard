# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Repository management endpoints (CRUD, branches, classify, route extraction).

The GitHub-organisation members endpoint moved to
:mod:`settings_github_members` so this file stays focused on tracked-repo
state. Every endpoint that returns a ``RepoInfo`` row delegates to
:func:`build_repo_info` — schema additions only need to land in one
place.
"""

import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._repo_info_builder import build_repo_info
from app.core.deps import get_current_user, get_db
from app.models.repo_layer import RepoLayer
from app.models.tracked_repository import RepoStatus
from app.models.user import User
from app.repositories.backend_route_cache import BackendRouteCacheRepository
from app.repositories.design_system import DesignSystemRefRepository
from app.repositories.feature_scan import FeatureScanRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.scan_run import ScanRunRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.settings import (
    AddRepoRequest,
    RepoBranchList,
    RepoBranchUpdate,
    RepoInfo,
    RepoStatusRequest,
)
from app.services.git_operations import get_github_repo_full_name
from app.services.repo_cloner import clone_or_update
from app.services.repo_scanner import (
    _detect_develop_branch,
    _detect_main_branch,
    detect_uncommitted_changes,
    list_remote_branches,
)
from app.services.scan.backend_link import iter_route_records
from app.services.scan.repo_classify import classify
from app.services.ssh_keys import get_public_key

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings-repos"])


@router.get("/repos", response_model=list[RepoInfo])
async def list_repos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RepoInfo]:
    """List tracked repositories with last-scan summaries + classification chips."""
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    repos = await repo_repo.list_visible()

    ds_repo = DesignSystemRefRepository(db, org_id=org.id)
    all_ds = await ds_repo.list_all()
    ds_repo_ids = {str(ds.repo_id) for ds in all_ds}

    # One query joins each repo with its most-recent ScanRepoRun so the
    # row card can render "last scan: <relative time> • <N> features •
    # <status>" without any per-repo round trips.
    latest_runs = await ScanRunRepository(db, org_id=org.id).find_latest_per_repo(
        repo_ids=[r.id for r in repos]
    )

    return [
        build_repo_info(r, last_run=latest_runs.get(r.id), ds_repo_ids=ds_repo_ids) for r in repos
    ]


@router.post("/repos", response_model=RepoInfo)
async def add_repo(
    body: AddRepoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoInfo:
    """Add a repository by absolute path. Any valid git checkout is accepted."""
    repo_path = Path(body.path).resolve()
    if not repo_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path does not exist: {body.path}",
        )
    if not (repo_path / ".git").exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a git repository: {body.path}",
        )

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    repo = await repo_repo.upsert(str(repo_path), repo_path.name)

    detected_main = await _detect_main_branch(str(repo_path))
    detected_dev = await _detect_develop_branch(str(repo_path))
    has_dirty = await detect_uncommitted_changes(str(repo_path))

    if detected_main:
        repo.main_branch = detected_main
    if detected_dev:
        repo.develop_branch = detected_dev

    if not repo.github_repo_full_name:
        github_name = await get_github_repo_full_name(str(repo_path))
        if github_name:
            repo.github_repo_full_name = github_name

    await db.flush()
    return build_repo_info(repo, has_dirty=has_dirty)


class CloneRepoBody(BaseModel):
    """Body for ``POST /v1/settings/repos/clone`` — authenticated GitHub clone."""

    url: str = Field(..., description="GitHub HTTPS or SSH URL.")
    pat: str | None = Field(
        default=None,
        description="Optional GitHub personal-access token for HTTPS private repos.",
    )


@router.post("/repos/clone", response_model=RepoInfo)
async def clone_and_add_repo(
    body: CloneRepoBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoInfo:
    """Clone a GitHub repo into the backend volume and register it on this org.

    Combines :func:`clone_or_update` (which writes to ``/data/repos``) with
    the same "add by local path" flow as ``POST /repos`` above, so from the
    rest of the pipeline's perspective a cloned repo is indistinguishable
    from a pre-existing local one.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    result = await clone_or_update(body.url, org_slug=org.slug, pat=body.pat)
    if not result.success or not result.path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error or "Clone failed.",
        )

    repo_path = Path(result.path).resolve()
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    repo = await repo_repo.upsert(str(repo_path), repo_path.name)

    detected_main = result.default_branch or await _detect_main_branch(str(repo_path))
    detected_dev = await _detect_develop_branch(str(repo_path))
    has_dirty = await detect_uncommitted_changes(str(repo_path))

    if detected_main:
        repo.main_branch = detected_main
    if detected_dev:
        repo.develop_branch = detected_dev

    if not repo.github_repo_full_name:
        github_name = await get_github_repo_full_name(str(repo_path))
        if github_name:
            repo.github_repo_full_name = github_name

    await db.flush()

    logger.info(
        "repo_cloned_and_registered",
        org_id=str(org.id),
        repo_id=str(repo.id),
        path=str(repo_path),
        url_kind="ssh" if body.url.startswith(("git@", "ssh://")) else "https",
        pat_used=body.pat is not None,
    )

    return build_repo_info(repo, has_dirty=has_dirty, include_setup_compare=True)


@router.get("/repos/deploy-key")
async def get_repos_deploy_key(
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Return the backend SSH public key for the GitHub-clone flow.

    The setup wizard exposes the same key at ``GET /api/setup/deploy-key``
    only while setup is incomplete. Post-setup the Settings → Code "Add
    repositories" dialog needs the same key so the user can paste it into
    GitHub before queuing SSH URLs. The public key is harmless to share
    but we still gate it behind a session.
    """
    _ = current_user
    return {
        "public_key": get_public_key(),
        "fingerprint_algo": "ssh-ed25519",
    }


@router.delete("/repos", status_code=status.HTTP_200_OK)
async def remove_repo(
    body: AddRepoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Soft-delete a tracked repository and deactivate its knowledge rows."""
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    repo = await repo_repo.get_by_path(body.path)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    await repo_repo.set_status(repo.id, RepoStatus.REMOVED)

    # Soft-delete every feature whose PRIMARY junction points at this
    # repo. The junction rows themselves stay (they cascade out only
    # if the tracked_repository row is hard-deleted), so a future
    # un-remove + re-scan will revive matching features via the
    # reconciler.
    feat_scan = FeatureScanRepository(db, org_id=org.id)
    deactivated_ids = await feat_scan.soft_delete_by_repo_ids([repo.id])

    return {"removed": body.path, "deactivated": len(deactivated_ids)}


@router.patch("/repos/{repo_id}/status", response_model=RepoInfo)
async def update_repo_status(
    repo_id: uuid.UUID,
    body: RepoStatusRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoInfo:
    """Toggle a repo between ``active`` and ``ignored``."""
    if body.status not in ("active", "ignored"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be 'active' or 'ignored'.",
        )

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    repo = await repo_repo.set_status(repo_id, RepoStatus(body.status))
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )
    return build_repo_info(repo)


@router.get("/repos/{repo_id}/branches", response_model=RepoBranchList)
async def get_repo_branches(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoBranchList:
    """List all remote branches for a tracked repository."""
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    repo = await repo_repo.get_by_id(repo_id)

    if not repo or repo.org_id != org.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    branches = await list_remote_branches(repo.path)
    return RepoBranchList(
        branches=branches,
        currentMain=repo.main_branch,
        currentDevelop=repo.develop_branch,
        currentUat=repo.uat_branch,
    )


@router.post("/repos/{repo_id}/classify", response_model=RepoInfo)
async def classify_repo_endpoint(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoInfo:
    """Detect ``repo_layer`` / ``tech_stack`` / ``db_flavor`` for one repo.

    Cheap (file-glob inspection of ``package.json`` / ``pyproject.toml``)
    and idempotent — runs without spinning up a full scan. Today the
    Settings → Code page doesn't surface a button for this; the
    classification chips are populated by the per-repo ``classify_repo``
    scan stage. The endpoint stays available as the manual escape hatch
    (curl / future ops tooling) and shares the same :func:`classify`
    helper as the stage so behaviour stays in lockstep.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    repo = await repo_repo.get_by_id(repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")

    classification = classify(repo.name, repo.path)
    await repo_repo.set_classification(
        repo_id,
        layer=classification.layer,
        tech_stack=classification.tech_stack,
        db_flavor=classification.db_flavor,
    )
    await db.commit()
    repo = await repo_repo.get_by_id(repo_id)
    assert repo is not None  # Just persisted; cannot be missing.

    return build_repo_info(repo, include_classification=True)


@router.post("/repos/{repo_id}/extract-routes", response_model=RepoInfo)
async def extract_routes_endpoint(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoInfo:
    """Walk a backend repo's worktree and refresh its ``backend_route_cache``.

    Like the classify endpoint above, this is a manual escape hatch. The
    per-repo ``extract_routes`` scan stage does the same work; the
    endpoint exists for ops without a full scan. Returns 400 when the
    repo isn't classified BACKEND or has no ``head_sha`` yet.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    repo = await repo_repo.get_by_id(repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found.")
    if repo.repo_layer is not RepoLayer.BACKEND:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Route extraction only applies to repos classified as BACKEND.",
        )
    if not repo.head_sha:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Repository has no head_sha yet — run a scan first.",
        )

    records = list(iter_route_records(Path(repo.path)))
    cache_repo = BackendRouteCacheRepository(db, org_id=org.id)
    await cache_repo.replace_for_repo_sha(repo_id=repo_id, head_sha=repo.head_sha, records=records)
    await db.commit()

    return build_repo_info(repo, include_classification=True)


@router.patch("/repos/{repo_id}/branches", response_model=RepoInfo)
async def update_repo_branches(
    repo_id: uuid.UUID,
    body: RepoBranchUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoInfo:
    """Update the main / develop / UAT branch mapping for a tracked repo."""
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    repo = await repo_repo.get_by_id(repo_id)

    if not repo or repo.org_id != org.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Repository not found.",
        )

    if body.main_branch is not None:
        repo.main_branch = body.main_branch
    if body.develop_branch is not None:
        repo.develop_branch = body.develop_branch
    if body.uat_branch is not None:
        # Empty string → explicit clear; non-empty → set.
        repo.uat_branch = body.uat_branch or None
    await db.flush()
    return build_repo_info(repo)
