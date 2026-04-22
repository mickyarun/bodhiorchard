# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""First-time setup endpoint: creates org, admin user, auto-adds repo, triggers scan."""

import asyncio
import contextlib
import secrets
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.encryption import encrypt_secret
from app.core.security import create_access_token, hash_password
from app.models.organization import Organization
from app.models.user import OrgToUser, User, UserRole
from app.repositories.organization import OrganizationRepository
from app.repositories.role import RoleRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.user import UserRepository
from app.schemas.setup import (
    BrowseDirectoriesResponse,
    ClaudeCheckRequest,
    DirectoryEntry,
    SetupRequest,
    SetupResponse,
    SetupStatusResponse,
)
from app.services.claude_env import (
    AUTH_MODE_API_KEY,
    AUTH_MODE_HOST,
    VALID_AUTH_MODES,
    apply_claude_auth_to_env,
)
from app.services.claude_runner import test_claude_connection
from app.services.deployment_info import deployment_info
from app.services.permission_seeder import seed_permissions
from app.services.repo_cloner import CLONE_ROOT, clone_or_update
from app.services.ssh_keys import get_public_key

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["setup"])


@router.get("/status")
async def setup_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Check whether initial setup has been completed.

    Returns:
        A dict with `is_setup_complete` boolean.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.check_setup_exists()
    if org is None:
        return {"is_setup_complete": False, "org_slug": None}
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
) -> dict:
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

    from app.services.git_operations import list_remote_branches
    from app.services.repo_scanner import _detect_develop_branch, _detect_main_branch

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
async def get_deployment_info() -> dict:
    """Report whether the backend is running in Docker or on the host.

    Used by the setup wizard to decide which Claude auth options to surface:
    Docker deployments cannot reach a host ``claude login`` session, so the
    UI constrains the choice to an API key. Harmless to expose post-setup,
    so no guard.
    """
    return deployment_info()


@router.get("/deploy-key")
async def get_deploy_key(db: AsyncSession = Depends(get_db)) -> dict:
    """Return the backend's SSH public key, generating it on first call.

    The setup wizard shows this to the user so they can paste it into a
    private repo's **Settings → Deploy keys** on GitHub, granting the
    Bodhiorchard backend read access to that repo. Gated post-setup — the
    authenticated ``/v1/settings/repos/clone`` flow exposes its own
    deploy-key helper for ongoing use.
    """
    await _require_setup_incomplete(db)
    return {
        "public_key": get_public_key(),
        "fingerprint_algo": "ssh-ed25519",
    }


class CloneRepoRequest(BaseModel):
    """Body for ``POST /api/setup/clone-repo``."""

    url: str = Field(..., description="GitHub HTTPS or SSH URL.")
    org_slug: str = Field(
        ...,
        alias="orgSlug",
        min_length=2,
        max_length=100,
        # Mirror SetupOrganization.slug so the path segment under
        # /data/repos can't contain surprises even before the org exists.
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$",
    )
    pat: str | None = Field(
        default=None,
        description="Optional GitHub personal-access token for HTTPS private repos.",
    )

    model_config = {"populate_by_name": True}


@router.post("/clone-repo")
async def clone_repo(
    body: CloneRepoRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Clone a GitHub repo into the backend's ``/data/repos`` volume.

    Unauthenticated because this is part of the setup wizard, which runs
    before any org/user exists. The returned ``path`` is container-local
    and is the value the wizard passes back in ``/setup/initialize`` so the
    scan pipeline finds the clone. Refuses once setup is complete — the
    authenticated ``/v1/settings/repos/clone`` covers post-setup cloning.
    """
    await _require_setup_incomplete(db)
    result = await clone_or_update(body.url, org_slug=body.org_slug, pat=body.pat)
    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "path": result.path,
        }
    # Surface the list of branches for the UI to offer as main/develop options.
    from app.services.git_operations import list_remote_branches

    branches: list[str] = []
    try:
        branches = await list_remote_branches(result.path or "")
    except Exception:  # noqa: BLE001
        logger.warning("clone_branch_list_failed", path=result.path)
    return {
        "success": True,
        "path": result.path,
        "default_branch": result.default_branch,
        "branches": branches,
        "clone_root": str(CLONE_ROOT),
    }


@router.get("/check-claude")
async def check_claude(db: AsyncSession = Depends(get_db)) -> dict:
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
) -> dict:
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


@router.post("/initialize", response_model=SetupResponse, status_code=status.HTTP_201_CREATED)
async def initialize_setup(
    body: SetupRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> SetupResponse:
    """Run first-time platform setup.

    Creates the organization, admin user, auto-adds the repo, and
    triggers a background scan. Integrations (GitHub, Slack) are
    configured later via Settings.

    Args:
        body: Setup payload with org, admin, and repo path.
        background_tasks: FastAPI background task manager.
        db: The async database session.

    Returns:
        SetupResponse with org ID, user ID, JWT, and scan ID.

    Raises:
        HTTPException 409: If the organization slug is already taken.
    """
    org_repo = OrganizationRepository(db)
    if await org_repo.get_by_slug(body.organization.slug) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists. Setup may have been completed already.",
        )

    # Build org config — repos are tracked in tracked_repositories table
    org_config: dict = {
        "llm": {"preset": "claude-code"},
        "integrations": {
            "github": {"enabled": False},
            "slack": {"enabled": False},
        },
        "scan": {
            "timeout_seconds": body.scan.timeout_seconds,
            "max_turns": body.scan.max_turns,
            "auto_create_members": True,
        },
    }

    # Generate MCP token for Claude Code integration
    mcp_token = secrets.token_urlsafe(32)

    # Resolve Claude auth choice from the wizard.
    claude_auth_mode = body.claude.auth_mode
    if claude_auth_mode not in VALID_AUTH_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"claude.auth_mode must be one of {sorted(VALID_AUTH_MODES)}",
        )
    encrypted_key: str | None = None
    if claude_auth_mode == AUTH_MODE_API_KEY:
        key = (body.claude.api_key or "").strip()
        if not key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="claude.api_key is required when auth_mode is 'api_key'",
            )
        encrypted_key = encrypt_secret(key)

    org = Organization(
        name=body.organization.name,
        slug=body.organization.slug,
        config=org_config,
        mcp_token_hash=hash_password(mcp_token),
        claude_auth_mode=claude_auth_mode,
        claude_api_key_encrypted=encrypted_key,
    )
    db.add(org)
    await db.flush()

    # Push the newly-chosen Claude auth into the backend process env so the
    # auto-scan triggered below can reach Claude without a backend restart.
    apply_claude_auth_to_env(org)

    # Create admin user
    user = User(
        email=body.admin.email,
        name=body.admin.name,
        password_hash=hash_password(body.admin.password),
    )
    db.add(user)
    await db.flush()

    # Seed permissions, agent skills, and stage mappings
    await seed_permissions(db)

    from app.services.bud_stage_seeder import seed_stage_mappings_for_org
    from app.services.skill_loader import seed_skills_for_org

    await seed_skills_for_org(org.id, db)
    await seed_stage_mappings_for_org(org.id, db)
    role_repo = RoleRepository(db)
    owner_role = await role_repo.get_by_name_system("org_owner")

    membership = OrgToUser(
        user_id=user.id,
        org_id=org.id,
        role=UserRole.ORG_OWNER,
        role_id=owner_role.id if owner_role else None,
    )
    db.add(membership)
    await db.flush()

    # Auto-add repos from source_code with branch mappings
    scan_id: str | None = None
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    valid_paths: list[str] = []

    for repo_cfg in body.source_code.repos:
        repo_path = Path(repo_cfg.path).resolve()
        if not repo_path.exists() or not (repo_path / ".git").exists():
            logger.warning("setup_skip_invalid_repo", path=str(repo_path))
            continue

        tracked = await repo_repo.upsert(str(repo_path), repo_path.name)
        valid_paths.append(str(repo_path))

        # Use branch mappings from setup (user-selected)
        if repo_cfg.main_branch:
            tracked.main_branch = repo_cfg.main_branch
        if repo_cfg.develop_branch:
            tracked.develop_branch = repo_cfg.develop_branch

    await db.flush()

    # Commit BEFORE scheduling the background scan. FastAPI runs
    # BackgroundTasks after the response is sent but *before* the
    # request's dependency teardown (which is where get_db() normally
    # commits). The scan worker opens its own AsyncSessionLocal, so if we
    # only rely on the teardown commit the scan sees an empty DB and
    # crashes with `AttributeError: 'NoneType' object has no attribute
    # 'config'` at scan_pipeline.py:363.
    await db.commit()

    # Auto-trigger scan only if embedding service is healthy
    embedding_warning: str | None = None
    if valid_paths:
        from app.services.embedding_service import embedding_service

        embed_ok, embed_err = await embedding_service.check()
        if embed_ok:
            from app.services.scan_pipeline import run_scan_pipeline
            from app.services.scan_progress import create_scan_progress

            scan_id = str(uuid.uuid4())
            await create_scan_progress(scan_id, str(org.id))

            background_tasks.add_task(
                run_scan_pipeline,
                scan_id=scan_id,
                org_id=org.id,
                repo_paths=valid_paths,
                full_rescan=True,
                user_id=str(user.id),
            )

            logger.info(
                "setup_auto_scan_triggered",
                scan_id=scan_id,
                repos=len(valid_paths),
            )
        else:
            embedding_warning = (
                f"Embedding service unavailable ({embed_err}). "
                "Scan skipped — trigger it manually from Settings after fixing."
            )
            logger.warning("setup_embedding_check_failed", error=embed_err)

    # Issue JWT token
    token = create_access_token(data={"sub": str(user.id), "org_id": str(org.id)})

    logger.info(
        "setup_complete",
        org_id=str(org.id),
        org_slug=org.slug,
        admin_email=user.email,
        scan_id=scan_id,
    )

    return SetupResponse(
        organization_id=str(org.id),
        user_id=str(user.id),
        access_token=token,
        mcp_token=mcp_token,
        scanId=scan_id,
        embeddingWarning=embedding_warning,
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
    from app.services.scan_progress import get_active_scan_for_org

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
        orgCreated=True,
        claudeCodeTested=True,  # If they got past setup, Claude was tested
        repoAdded=len(active_repos) > 0,
        scanComplete=scan_complete,
        scanInProgress=scan_in_progress,
        scanId=scan_id,
        scanProgress=scan_progress,
        githubConnected=bool(org.github_app_id),
        slackConnected=bool(org.slack_bot_token),
        branchesMapped=all(r.main_branch for r in active_repos) if active_repos else False,
        membersImported=len(users) > 1,
        qaConfigured=qa_configured,
    )
