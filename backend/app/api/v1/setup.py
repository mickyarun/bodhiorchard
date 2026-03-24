"""First-time setup endpoint: creates org, admin user, and stores config."""

import secrets
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.encryption import encrypt_secret
from app.core.security import create_access_token, hash_password
from app.models.organization import Organization
from app.models.user import OrgToUser, User, UserRole
from app.repositories.organization import OrganizationRepository
from app.repositories.role import RoleRepository
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
    org_repo = OrganizationRepository(db)
    if await org_repo.get_by_slug(body.organization.slug) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists. Setup may have been completed already.",
        )

    # Build org config from AI config, source code, and integration settings
    org_config = {
        "source_code": {
            "local_path": body.source_code.local_path,
            "type": body.source_code.type,
        },
        "llm": {
            "preset": body.ai_config.preset,
            "ollama_url": body.ai_config.ollama_url,
            "ollama_model": body.ai_config.ollama_model,
            "cloud_provider": body.ai_config.cloud_provider,
            "cloud_api_key": encrypt_secret(body.ai_config.cloud_api_key)
            if body.ai_config.cloud_api_key
            else "",
            "cloud_model": body.ai_config.cloud_model,
            # Legacy fields from LLM config
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

    # Generate MCP token for Claude Code integration
    mcp_token = secrets.token_urlsafe(32)

    # Create organization
    org = Organization(
        name=body.organization.name,
        slug=body.organization.slug,
        config=org_config,
        github_pat=encrypt_secret(body.integrations.github.pat)
        if body.integrations.github.pat
        else None,
        slack_bot_token=encrypt_secret(body.integrations.slack.bot_token)
        if body.integrations.slack.bot_token
        else None,
        slack_signing_secret=encrypt_secret(body.integrations.slack.signing_secret)
        if body.integrations.slack.signing_secret
        else None,
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

    # Seed permissions and assign org_owner role to admin
    await seed_permissions(db)
    role_repo = RoleRepository(db)
    owner_role = await role_repo.get_by_name_system("org_owner")

    # Create org membership with owner role
    membership = OrgToUser(
        user_id=user.id,
        org_id=org.id,
        role=UserRole.ORG_OWNER,
        role_id=owner_role.id if owner_role else None,
    )
    db.add(membership)
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
        mcp_token=mcp_token,
    )
