"""First-time setup endpoint: creates org, admin user, auto-adds repo, triggers scan."""

import secrets
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, hash_password
from app.models.organization import Organization
from app.models.user import OrgToUser, User, UserRole
from app.repositories.organization import OrganizationRepository
from app.repositories.role import RoleRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.user import UserRepository
from app.schemas.setup import (
    BrowseDirectoriesResponse,
    DirectoryEntry,
    SetupRequest,
    SetupResponse,
    SetupStatusResponse,
)
from app.services.claude_runner import test_claude_connection
from app.services.permission_seeder import seed_permissions

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

    entries: list[DirectoryEntry] = []
    try:
        for child in sorted(target.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                is_git = (child / ".git").exists()
                entries.append(
                    DirectoryEntry(
                        name=child.name,
                        path=str(child),
                        is_git_repo=is_git,
                    )
                )
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


@router.get("/check-claude")
async def check_claude() -> dict:
    """Test Claude Code CLI availability during setup (no auth required).

    Returns:
        Test results including cli_available, test_passed, output, error.
    """
    return await test_claude_connection()


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

    org = Organization(
        name=body.organization.name,
        slug=body.organization.slug,
        config=org_config,
        mcp_token_hash=hash_password(mcp_token),
    )
    db.add(org)
    await db.flush()

    # Create admin user
    user = User(
        email=body.admin.email,
        name=body.admin.name,
        password_hash=hash_password(body.admin.password),
    )
    db.add(user)
    await db.flush()

    # Seed permissions and assign org_owner role
    await seed_permissions(db)
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

    # Auto-trigger scan only if embedding service is healthy
    embedding_warning: str | None = None
    if valid_paths:
        from app.services.embedding_service import embedding_service

        embed_ok, embed_err = await embedding_service.check()
        if embed_ok:
            from app.schemas.skills import ScanStatus
            from app.services.scan_pipeline import run_scan_pipeline, scan_statuses

            scan_id = str(uuid.uuid4())
            scan_statuses[scan_id] = ScanStatus(scanId=scan_id, status="started", progressPct=0)

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
    from app.services.scan_pipeline import scan_statuses

    scan_in_progress = False
    scan_id: str | None = None
    scan_progress = 0
    scan_complete = any(r.last_scanned_at is not None for r in active_repos)

    for sid, ss in scan_statuses.items():
        if ss.status not in ("completed", "failed"):
            scan_in_progress = True
            scan_id = sid
            scan_progress = ss.progress_pct
            break

    return SetupStatusResponse(
        orgCreated=True,
        claudeCodeTested=True,  # If they got past setup, Claude was tested
        repoAdded=len(active_repos) > 0,
        scanComplete=scan_complete,
        scanInProgress=scan_in_progress,
        scanId=scan_id,
        scanProgress=scan_progress,
        githubConnected=bool(org.github_pat),
        slackConnected=bool(org.slack_bot_token),
        branchesMapped=all(r.main_branch for r in active_repos) if active_repos else False,
        membersImported=len(users) > 1,
    )
