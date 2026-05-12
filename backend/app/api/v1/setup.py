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

"""First-time setup endpoint: creates org, admin user, auto-adds repo, triggers scan."""

import asyncio
import contextlib
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.user import UserRepository
from app.schemas.setup import (
    BrowseDirectoriesResponse,
    ClaudeCheckRequest,
    DirectoryEntry,
    FinalizeWithReposRequest,
    FinalizeWithReposResponse,
    InitOrgRequest,
    InitOrgResponse,
    SetupRequest,
    SetupResponse,
    SetupSourceCode,
    SetupStatusResponse,
)
from app.services.claude_env import (
    AUTH_MODE_HOST,
    VALID_AUTH_MODES,
)
from app.services.claude_runner import test_claude_connection
from app.services.deployment_info import deployment_info
from app.services.git_operations import list_remote_branches
from app.services.redis_setup_status import get_setup_complete, set_setup_complete
from app.services.repo_scanner import _detect_develop_branch, _detect_main_branch
from app.services.scan_progress import get_active_scan_for_org
from app.services.setup_finalize import setup_finalize_with_repos
from app.services.setup_init import setup_init_org

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["setup"])


@router.get("/status")
async def setup_status(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Check whether initial setup has been completed.

    Reads a Redis fast-path flag first so the wizard's polling
    doesn't grab a DB connection per request. Falls back to the
    canonical ``OrganizationRepository.check_setup_exists`` query
    when the flag is unset (e.g. older orgs initialised before this
    fast-path landed, or after a Redis flush) and re-warms the cache
    on a successful DB hit.

    Returns:
        A dict with ``is_setup_complete`` and ``org_slug``.
    """
    cached_slug = await get_setup_complete()
    if cached_slug is not None:
        return {"is_setup_complete": True, "org_slug": cached_slug}

    org_repo = OrganizationRepository(db)
    org = await org_repo.check_setup_exists()
    if org is None:
        return {"is_setup_complete": False, "org_slug": None}
    # Warm the Redis cache so the next poll skips the DB.
    await set_setup_complete(org.slug)
    return {"is_setup_complete": True, "org_slug": org.slug}


def _list_directory_sync(target: Path) -> list[DirectoryEntry]:
    """Walk ``target`` one level deep, flagging git repos and monorepos.

    Runs synchronously — callers from async endpoints must wrap this in
    ``asyncio.to_thread`` so the event loop doesn't block on the stat
    calls (users with deep home dirs can have hundreds of entries).
    """
    entries: list[DirectoryEntry] = []
    for child in sorted(target.iterdir()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        is_git = (child / ".git").exists()
        # For a git repo, peek one level down to flag monorepos — short-
        # circuits at the first nested `.git`, so the cost is one
        # iterdir call plus at most a handful of stats per repo.
        has_sub_repos = False
        if is_git:
            with contextlib.suppress(PermissionError, OSError):
                has_sub_repos = any(
                    (gc / ".git").exists()
                    for gc in child.iterdir()
                    if gc.is_dir() and not gc.name.startswith(".")
                )
        entries.append(
            DirectoryEntry(
                name=child.name,
                path=str(child),
                is_git_repo=is_git,
                has_sub_repos=has_sub_repos,
            )
        )
    return entries


@router.get("/browse-directories", response_model=BrowseDirectoriesResponse)
async def browse_directories(
    path: str = Query(default="", description="Directory path to list. Defaults to home."),
) -> BrowseDirectoriesResponse:
    """List subdirectories at a given path for the file picker.

    Returns the resolved current path, parent path, and child directories.
    Only directories are listed — no file contents are exposed.
    """
    target = Path(path).expanduser().resolve() if path else Path.home()

    if not target.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Path does not exist: {target}",
        )
    if not target.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a directory: {target}",
        )

    try:
        entries = await asyncio.to_thread(_list_directory_sync, target)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {target}",
        ) from exc

    parent = str(target.parent) if target != target.parent else None

    return BrowseDirectoriesResponse(
        current_path=str(target),
        parent_path=parent,
        directories=entries,
    )


@router.get("/repo-branches")
async def get_repo_branches(
    path: str = Query(..., description="Absolute path to a git repository"),
) -> dict[str, Any]:
    """List branches for a repo by path (no auth — used during setup).

    Args:
        path: Absolute path to the git repository.

    Returns:
        Dict with branches list and auto-detected main/develop.
    """
    repo_path = Path(path).resolve()
    if not repo_path.exists() or not (repo_path / ".git").exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not a git repository: {path}",
        )

    branches = await list_remote_branches(str(repo_path))
    detected_main = await _detect_main_branch(str(repo_path))
    detected_dev = await _detect_develop_branch(str(repo_path))

    return {
        "branches": branches,
        "detectedMain": detected_main,
        "detectedDevelop": detected_dev,
    }


async def _require_setup_incomplete(db: AsyncSession) -> None:
    """Reject the call when an organization already exists.

    All endpoints in this router are unauthenticated because the setup
    wizard runs *before* any user or JWT exists. Once setup completes,
    leaving them open would let anyone on the network exercise the
    clone-volume, mint a deploy key, or stress-test Anthropic with
    arbitrary API keys. We guard by checking for any organization row —
    the same signal the frontend uses to hide the wizard.
    """
    org_repo = OrganizationRepository(db)
    if await org_repo.check_setup_exists() is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup is already complete; this endpoint is disabled.",
        )


@router.get("/deployment-info")
async def get_deployment_info() -> dict[str, Any]:
    """Report whether the backend is running in Docker or on the host.

    Used by the setup wizard to decide which Claude auth options to surface:
    Docker deployments cannot reach a host ``claude login`` session, so the
    UI constrains the choice to an API key. Harmless to expose post-setup,
    so no guard.
    """
    return deployment_info()


# Removed: GET /setup/deploy-key, POST /setup/clone-repo.
# Both ran post-init (after the wizard's init-org step minted a JWT), so
# they're now served by their authenticated equivalents in
# settings_repos.py:
#   GET  /v1/settings/repos/deploy-key   — same {public_key} shape.
#   POST /v1/settings/repos/clone        — derives org from JWT; failures
#                                          surface as 4xx instead of a
#                                          {success: false} envelope.
# The legacy POST /setup/initialize below still uses _require_setup_incomplete
# because it runs the whole wizard in one unauthenticated shot.


@router.get("/check-claude")
async def check_claude(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Test Claude Code against the backend's current process env (no auth).

    Returns:
        Test results including cli_available, test_passed, output, error.
    """
    await _require_setup_incomplete(db)
    return await test_claude_connection()


@router.post("/check-claude")
async def check_claude_with_credentials(
    body: ClaudeCheckRequest | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Test Claude Code against provisional credentials during setup.

    When ``auth_mode == 'api_key'`` and ``api_key`` is supplied, the key
    is passed to the subprocess via ``env_extra`` — isolated to this one
    subprocess, with no mutation of the backend's process env (mutating
    ``os.environ`` would race with any concurrent agent run and could
    cross-wire billing between orgs).

    When ``auth_mode == 'host'`` (or no body), the test runs against the
    unmodified process env — mirrors the GET endpoint.
    """
    await _require_setup_incomplete(db)

    if body is None or body.auth_mode == AUTH_MODE_HOST:
        return await test_claude_connection()

    if body.auth_mode not in VALID_AUTH_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"auth_mode must be one of {sorted(VALID_AUTH_MODES)}",
        )

    api_key = (body.api_key or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="api_key is required when auth_mode is 'api_key'",
        )

    # Subprocess-scoped override — never touches os.environ.
    return await test_claude_connection(env_extra={"ANTHROPIC_API_KEY": api_key})


@router.post("/init-org", response_model=InitOrgResponse, status_code=status.HTTP_201_CREATED)
async def init_org(
    body: InitOrgRequest,
    db: AsyncSession = Depends(get_db),
) -> InitOrgResponse:
    """Stage-1 of the wizard — create the organization + admin user.

    The returned JWT must be sent on the follow-up call to
    ``POST /setup/finalize-with-repos`` (which is authenticated like
    every other Settings endpoint). Until that second call lands the
    org has zero tracked repos and ``is_setup_complete`` reports
    ``False`` from the wizard's perspective even though
    ``GET /setup/status`` will start returning ``True`` (an org now
    exists).
    """
    await _require_setup_incomplete(db)
    result = await setup_init_org(body, db)
    return InitOrgResponse(
        organization_id=str(result.org.id),
        user_id=str(result.user.id),
        org_slug=result.org.slug,
        access_token=result.access_token,
        mcp_token=result.mcp_token,
        is_setup_complete=False,
    )


@router.post(
    "/finalize-with-repos",
    response_model=FinalizeWithReposResponse,
    status_code=status.HTTP_201_CREATED,
)
async def finalize_with_repos(
    body: FinalizeWithReposRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FinalizeWithReposResponse:
    """Stage-2 of the wizard — register repos and kick off scanning.

    Authenticated via the JWT minted by ``init-org``; the caller's
    org membership is enforced through
    :meth:`OrganizationRepository.get_for_user`. The two payload arms
    are XOR-validated by the schema's ``model_validator``.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    return await setup_finalize_with_repos(
        org=org,
        user=current_user,
        req=body,
        db=db,
    )


# Removed: GET /setup/installable.
# Pre-init had no JWT, so this returned an empty NO_CREDENTIALS payload —
# but the wizard now only fetches the installable list AFTER init-org,
# which means the authenticated GET /v1/settings/repos/installable is the
# only path the frontend hits. Dropping the unauth mirror reduces the
# surface area gated by _require_setup_incomplete.


# DEPRECATED — kept for back-compat with the existing single-shot setup flow;
# new wizards should use POST /setup/init-org then POST /setup/finalize-with-repos.
@router.post("/initialize", response_model=SetupResponse, status_code=status.HTTP_201_CREATED)
async def initialize_setup(
    body: SetupRequest,
    db: AsyncSession = Depends(get_db),
) -> SetupResponse:
    """Legacy single-shot wizard endpoint — composes init-org + finalize.

    Internally calls :func:`setup_init_org` followed by
    :func:`setup_finalize_with_repos` with the legacy ``sourceCode``
    payload, preserving the original response shape (``scan_id``,
    ``mcp_token``, ``access_token``, ``embedding_warning``) so existing
    frontend callers don't break before Phase H lands.
    """
    await _require_setup_incomplete(db)

    init_req = InitOrgRequest(
        organization=body.organization,
        admin=body.admin,
        scan=body.scan,
        claude=body.claude,
    )
    init_result = await setup_init_org(init_req, db)

    finalize_req = FinalizeWithReposRequest(
        installable_items=None,
        source_code=SetupSourceCode(repos=body.source_code.repos),
    )
    org_repo = OrganizationRepository(db)
    # Reload the org through the repo so subsequent queries see the
    # committed row from stage-1 in this same request session.
    org = await org_repo.get_by_slug(body.organization.slug)
    assert org is not None  # Just created in setup_init_org above.
    finalize_result = await setup_finalize_with_repos(
        org=org,
        user=init_result.user,
        req=finalize_req,
        db=db,
    )

    logger.info(
        "setup_complete",
        org_id=str(init_result.org.id),
        org_slug=init_result.org.slug,
        admin_email=init_result.user.email,
        scan_id=finalize_result.scan_id,
    )

    return SetupResponse(
        organization_id=str(init_result.org.id),
        user_id=str(init_result.user.id),
        access_token=init_result.access_token,
        mcp_token=init_result.mcp_token,
        scanId=finalize_result.scan_id,
        embeddingWarning=finalize_result.embedding_warning,
    )


@router.get("/checklist-status", response_model=SetupStatusResponse)
async def get_checklist_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SetupStatusResponse:
    """Return setup checklist status for the dashboard widget.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        SetupStatusResponse with completion status for each checklist item.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    active_repos = await repo_repo.list_active()

    user_repo = UserRepository(db, org_id=org.id)
    users = await user_repo.list_by_org(org.id)

    # Check scan status

    scan_in_progress = False
    scan_id: str | None = None
    scan_progress = 0
    scan_complete = any(r.last_scanned_at is not None for r in active_repos)

    active_scan = await get_active_scan_for_org(str(org.id))
    if active_scan:
        scan_in_progress = True
        scan_id = active_scan.scan_id
        scan_progress = active_scan.progress_pct

    # "QA configured" = org has visited the QA Automation settings page and
    # saved any value. We treat the presence of ANY qa section as the done
    # signal (even default values count — visiting the page is the point).
    qa_configured = bool(org.config and org.config.get("qa"))

    return SetupStatusResponse(
        org_created=True,
        claude_code_tested=True,  # If they got past setup, Claude was tested
        repo_added=len(active_repos) > 0,
        scan_complete=scan_complete,
        scan_in_progress=scan_in_progress,
        scan_id=scan_id,
        scan_progress=scan_progress,
        github_connected=bool(org.github_app_id),
        slack_connected=bool(org.slack_bot_token),
        branches_mapped=all(r.main_branch for r in active_repos) if active_repos else False,
        members_imported=len(users) > 1,
        qa_configured=qa_configured,
    )
