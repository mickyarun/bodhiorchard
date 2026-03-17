"""First-time setup endpoint: creates org, admin user, and stores config."""

from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import create_access_token, hash_password
from app.models.organization import Organization
from app.models.permission import Role
from app.models.user import User, UserRole
from app.schemas.setup import (
    BrowseDirectoriesResponse,
    DirectoryEntry,
    SetupRequest,
    SetupResponse,
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
    result = await db.execute(select(func.count()).select_from(Organization))
    count = result.scalar_one()
    return {"is_setup_complete": count > 0}


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
    db: AsyncSession = Depends(get_db),
) -> SetupResponse:
    """Run first-time platform setup.

    Creates the organization, admin user, and stores LLM/integration config.
    This endpoint is idempotent — it will reject if an org with the same slug
    already exists.

    Args:
        body: The complete setup payload from the frontend wizard.
        db: The async database session.

    Returns:
        SetupResponse with org ID, user ID, and JWT access token.

    Raises:
        HTTPException 409: If the organization slug is already taken.
    """
    # Check if org slug is already taken
    existing = await db.execute(
        select(Organization).where(Organization.slug == body.organization.slug)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists. Setup may have been completed already.",
        )

    # Build org config from LLM + integration + source code settings
    org_config = {
        "source_code": {
            "local_path": body.source_code.local_path,
            "type": body.source_code.type,
        },
        "llm": {
            "provider": body.llm.provider,
            "model": body.llm.model,
            "base_url": body.llm.base_url,
            "premium_provider": body.llm.premium_provider,
            "premium_model": body.llm.premium_model,
            "embedding_provider": body.llm.embedding_provider,
            "embedding_model": body.llm.embedding_model,
        },
        "integrations": {
            "github": {
                "enabled": body.integrations.github.enabled,
            },
            "slack": {
                "enabled": body.integrations.slack.enabled,
            },
        },
    }

    # Create organization
    org = Organization(
        name=body.organization.name,
        slug=body.organization.slug,
        config=org_config,
        github_pat=body.integrations.github.pat or None,
        slack_bot_token=body.integrations.slack.bot_token or None,
        slack_signing_secret=body.integrations.slack.signing_secret or None,
    )
    db.add(org)
    await db.flush()

    # Create admin user
    user = User(
        org_id=org.id,
        email=body.admin.email,
        name=body.admin.name,
        password_hash=hash_password(body.admin.password),
        role=UserRole.ORG_OWNER,
    )
    db.add(user)
    await db.flush()

    # Seed permissions and assign org_owner role to admin
    await seed_permissions(db)
    owner_result = await db.execute(
        select(Role).where(Role.name == "org_owner", Role.org_id.is_(None))
    )
    owner_role = owner_result.scalar_one_or_none()
    if owner_role is not None:
        user.role_id = owner_role.id
        await db.flush()

    # Issue JWT token
    token = create_access_token(data={"sub": str(user.id), "org_id": str(org.id)})

    logger.info(
        "setup_complete",
        org_id=str(org.id),
        org_slug=org.slug,
        admin_email=user.email,
    )

    return SetupResponse(
        organization_id=str(org.id),
        user_id=str(user.id),
        access_token=token,
    )
