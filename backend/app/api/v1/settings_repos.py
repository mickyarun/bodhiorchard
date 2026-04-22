# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Repository management endpoints (CRUD, branches, GitHub org members)."""

import asyncio
import uuid
from pathlib import Path

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.tracked_repository import RepoStatus
from app.models.user import User
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.user import UserRepository
from app.schemas.settings import (
    AddRepoRequest,
    RepoBranchList,
    RepoBranchUpdate,
    RepoInfo,
    RepoStatusRequest,
)
from app.services.repo_cloner import clone_or_update
from app.services.repo_scanner import (
    _detect_develop_branch,
    _detect_main_branch,
    detect_repo_type,
    detect_uncommitted_changes,
    list_remote_branches,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings-repos"])


def _detect_design_system_status(repo_id: str, ds_repo_ids: set[str]) -> str:
    """Check if a design system exists or is being extracted.

    Returns: 'ready' | 'extracting' | 'none'
    """
    if repo_id in ds_repo_ids:
        return "ready"
    from app.services.job_queue import JOB_DESIGN_EXTRACT, is_job_active

    if is_job_active(JOB_DESIGN_EXTRACT, {"repo_id": repo_id}):
        return "extracting"
    return "none"


def _detect_setup_status(repo_path: str) -> str:
    """Check if Bodhiorchard MCP + hooks are set up in a repo.

    Returns: 'merged' | 'not_setup'
    """
    mcp_config = Path(repo_path) / ".claude" / "settings.json"
    hooks_dir = Path(repo_path) / ".githooks" / "post-commit"
    if mcp_config.exists() and hooks_dir.exists():
        return "merged"
    return "not_setup"


@router.get("/repos", response_model=list[RepoInfo])
async def list_repos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RepoInfo]:
    """List tracked repositories from the database.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of RepoInfo (active and ignored repos).
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    repos = await repo_repo.list_visible()

    # Batch-fetch design system repo IDs for status check
    from app.repositories.design_system import DesignSystemRefRepository

    ds_repo = DesignSystemRefRepository(db, org_id=org.id)
    all_ds = await ds_repo.list_all()
    ds_repo_ids = {str(ds.repo_id) for ds in all_ds}

    return [
        RepoInfo(
            id=str(r.id),
            path=r.path,
            name=r.name,
            status=r.status.value,
            lastScanned=(r.last_scanned_at.isoformat() if r.last_scanned_at else None),
            sha=r.head_sha,
            knowledgeCount=r.knowledge_count,
            featureCount=r.feature_count,
            mainBranch=r.main_branch,
            developBranch=r.develop_branch,
            uatBranch=r.uat_branch,
            hasUncommittedChanges=False,
            repoType=detect_repo_type(r.path),
            githubRepo=r.github_repo_full_name,
            setupStatus=_detect_setup_status(r.path),
            designSystemStatus=_detect_design_system_status(str(r.id), ds_repo_ids),
        )
        for r in repos
    ]


@router.post("/repos", response_model=RepoInfo)
async def add_repo(
    body: AddRepoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoInfo:
    """Add a repository path. Any valid git repo path is accepted.

    Args:
        body: Request with the absolute path.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        RepoInfo for the newly added repo.
    """
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

    # Auto-detect branches and dirty state on add
    detected_main = await _detect_main_branch(str(repo_path))
    detected_dev = await _detect_develop_branch(str(repo_path))
    has_dirty = await detect_uncommitted_changes(str(repo_path))

    if detected_main:
        repo.main_branch = detected_main
    if detected_dev:
        repo.develop_branch = detected_dev

    # Auto-populate GitHub repo name from git remote origin
    if not repo.github_repo_full_name:
        from app.services.git_operations import get_github_repo_full_name

        github_name = await get_github_repo_full_name(str(repo_path))
        if github_name:
            repo.github_repo_full_name = github_name

    await db.flush()

    return RepoInfo(
        id=str(repo.id),
        path=repo.path,
        name=repo.name,
        status=repo.status.value,
        lastScanned=None,
        sha=repo.head_sha,
        knowledgeCount=repo.knowledge_count,
        featureCount=repo.feature_count,
        mainBranch=repo.main_branch,
        developBranch=repo.develop_branch,
        uatBranch=repo.uat_branch,
        hasUncommittedChanges=has_dirty,
        repoType=detect_repo_type(str(repo_path)),
        githubRepo=repo.github_repo_full_name,
    )


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

    Combines ``repo_cloner.clone_or_update`` (which writes to ``/data/repos``)
    with the same "add by local path" flow as ``POST /repos`` above — so from
    the rest of the pipeline's perspective a cloned repo is indistinguishable
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
        from app.services.git_operations import get_github_repo_full_name

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

    return RepoInfo(
        id=str(repo.id),
        path=repo.path,
        name=repo.name,
        status=repo.status.value,
        lastScanned=None,
        sha=repo.head_sha,
        knowledgeCount=repo.knowledge_count,
        featureCount=repo.feature_count,
        mainBranch=repo.main_branch,
        developBranch=repo.develop_branch,
        uatBranch=repo.uat_branch,
        hasUncommittedChanges=has_dirty,
        repoType=detect_repo_type(str(repo_path)),
        githubRepo=repo.github_repo_full_name,
    )


@router.delete("/repos", status_code=status.HTTP_200_OK)
async def remove_repo(
    body: AddRepoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove a tracked repository (soft delete) and deactivate its knowledge.

    Args:
        body: Request with the path to remove.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Dict with removed path and deactivated count.
    """
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

    # Deactivate knowledge items for this repo
    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    prefix = f"[{repo.name}]"
    deactivated = await ki_repo.bulk_deactivate_by_titles(
        await ki_repo.list_titles_with_prefix(f"{prefix}%"),
        category="feature_registry",
    )

    return {"removed": body.path, "deactivated": deactivated}


@router.patch("/repos/{repo_id}/status", response_model=RepoInfo)
async def update_repo_status(
    repo_id: uuid.UUID,
    body: RepoStatusRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoInfo:
    """Change a repo's status (active/ignored).

    Args:
        repo_id: The tracked repository UUID.
        body: New status.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Updated RepoInfo.
    """
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

    return RepoInfo(
        id=str(repo.id),
        path=repo.path,
        name=repo.name,
        status=repo.status.value,
        lastScanned=(repo.last_scanned_at.isoformat() if repo.last_scanned_at else None),
        sha=repo.head_sha,
        knowledgeCount=repo.knowledge_count,
        featureCount=repo.feature_count,
        mainBranch=repo.main_branch,
        developBranch=repo.develop_branch,
        uatBranch=repo.uat_branch,
        hasUncommittedChanges=False,
        repoType=detect_repo_type(repo.path),
        githubRepo=repo.github_repo_full_name,
    )


@router.get("/repos/{repo_id}/branches", response_model=RepoBranchList)
async def get_repo_branches(
    repo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoBranchList:
    """List all remote branches for a tracked repository.

    Args:
        repo_id: The tracked repository UUID.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        RepoBranchList with available branches and current mappings.
    """
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


@router.patch("/repos/{repo_id}/branches", response_model=RepoInfo)
async def update_repo_branches(
    repo_id: uuid.UUID,
    body: RepoBranchUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoInfo:
    """Update branch mapping for a tracked repository.

    Args:
        repo_id: The tracked repository UUID.
        body: Branch mapping update.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Updated RepoInfo.
    """
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
        # Empty string \u2192 explicit clear; non-empty \u2192 set.
        repo.uat_branch = body.uat_branch or None
    await db.flush()

    return RepoInfo(
        id=str(repo.id),
        path=repo.path,
        name=repo.name,
        status=repo.status.value,
        lastScanned=(repo.last_scanned_at.isoformat() if repo.last_scanned_at else None),
        sha=repo.head_sha,
        knowledgeCount=repo.knowledge_count,
        featureCount=repo.feature_count,
        mainBranch=repo.main_branch,
        developBranch=repo.develop_branch,
        uatBranch=repo.uat_branch,
        hasUncommittedChanges=False,
        repoType=detect_repo_type(repo.path),
        githubRepo=repo.github_repo_full_name,
    )


@router.get("/github/org-members")
async def list_github_org_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List members of the configured GitHub organization.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of GitHub org member dicts (login, name, avatar_url, email).
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    from app.services.github_app_auth import get_installation_token

    token = await get_installation_token(org)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub App is not configured. Set up a GitHub App in Settings.",
        )

    config = org.config or {}
    github_cfg = config.get("integrations", {}).get("github", {})
    github_org = github_cfg.get("org", "")
    if not github_org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub organization name is not configured in Settings.",
        )

    # Fetch org members using installation token
    gh_headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.github.com/orgs/{github_org}/members",
            params={"per_page": 100},
            headers=gh_headers,
            timeout=15,
        )

        if resp.status_code == 401:
            gh_msg = resp.json().get("message", "") if resp.text else ""
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    f"GitHub PAT is unauthorized: {gh_msg}. "
                    "Ensure the token has 'Members: Read' under "
                    "Organization permissions."
                ),
            )
        if resp.status_code == 403:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "GitHub PAT lacks required permissions. Go to GitHub → Settings → "
                    "Developer settings → Fine-grained tokens → edit your token and "
                    "add 'Members: Read' under Organization permissions."
                ),
            )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"GitHub organization '{github_org}' not found. "
                "Check the org name in Settings.",
            )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"GitHub API error ({resp.status_code}): {resp.text[:200]}",
            )
        members = resp.json()

    # Fetch real profile data (name + public email) for each member
    async def _fetch_profile(client: httpx.AsyncClient, login: str) -> dict[str, str | None]:
        try:
            r = await client.get(
                f"https://api.github.com/users/{login}",
                headers=gh_headers,
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "name": data.get("name") or login,
                    "email": data.get("email"),
                }
        except Exception:
            pass
        return {"name": login, "email": None}

    async with httpx.AsyncClient() as profile_client:
        profiles = await asyncio.gather(
            *[_fetch_profile(profile_client, m.get("login", "")) for m in members]
        )

    # Filter out members already added to Bodhiorchard
    user_repo = UserRepository(db, org_id=org.id)
    existing_users = await user_repo.list_by_org(org.id)
    existing_github = {u.github_username.lower() for u in existing_users if u.github_username}

    results = []
    for m, profile in zip(members, profiles, strict=True):
        login = m.get("login", "")
        results.append(
            {
                "login": login,
                "name": profile["name"],
                "avatar_url": m.get("avatar_url", ""),
                "email": profile["email"],
                "already_added": login.lower() in existing_github,
            }
        )
    return results
