"""Settings management endpoints for the authenticated user's organization."""

import secrets
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import hash_password
from app.models.user import User
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.organization import OrganizationRepository
from app.schemas.settings import (
    AddRepoRequest,
    AIConfigSettings,
    ConnectionsRead,
    ConnectionsUpdate,
    GitHubSettings,
    RepoInfo,
    ScanSettings,
    SlackSettings,
    SourceCodeSettings,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings"])


@router.get("/connections", response_model=ConnectionsRead)
async def get_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConnectionsRead:
    """Return the current organization's connection settings.

    Merges data from the JSONB config column and dedicated credential columns.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        ConnectionsRead with source code, GitHub, Slack, and AI config.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    config = org.config or {}

    source_code_cfg = config.get("source_code", {})
    integrations_cfg = config.get("integrations", {})
    github_cfg = integrations_cfg.get("github", {})
    slack_cfg = integrations_cfg.get("slack", {})
    llm_cfg = config.get("llm", {})
    scan_cfg = config.get("scan", {})

    return ConnectionsRead(
        sourceCode=SourceCodeSettings(
            localPath=source_code_cfg.get("local_path", ""),
            type=source_code_cfg.get("type", "single-repo"),
        ),
        github=GitHubSettings(
            enabled=github_cfg.get("enabled", False),
            pat=_mask_secret(org.github_pat),
        ),
        slack=SlackSettings(
            enabled=slack_cfg.get("enabled", False),
            botToken=_mask_secret(org.slack_bot_token),
            signingSecret=_mask_secret(org.slack_signing_secret),
        ),
        aiConfig=AIConfigSettings(
            preset=llm_cfg.get("preset", "hybrid"),
            ollamaUrl=llm_cfg.get("ollama_url", "http://localhost:11434"),
            ollamaModel=llm_cfg.get("ollama_model", "llama3:8b"),
            cloudProvider=llm_cfg.get("cloud_provider", "anthropic"),
            cloudApiKey=_mask_secret(llm_cfg.get("cloud_api_key")),
            cloudModel=llm_cfg.get("cloud_model", "claude-sonnet-4-5-20250514"),
        ),
        scan=ScanSettings(
            timeoutSeconds=scan_cfg.get("timeout_seconds", 300),
            maxTurns=scan_cfg.get("max_turns", 40),
        ),
    )


@router.patch("/connections", response_model=ConnectionsRead)
async def update_connections(
    body: ConnectionsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConnectionsRead:
    """Update organization connection settings.

    Only the provided sections are updated; omitted sections are left unchanged.
    Secrets that are sent as masked values (ending with '****') are ignored.

    Args:
        body: The partial update payload.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The updated ConnectionsRead.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    config = dict(org.config or {})

    # Source code
    if body.source_code is not None:
        config["source_code"] = {
            "local_path": body.source_code.local_path,
            "type": body.source_code.type,
        }

    # GitHub
    if body.github is not None:
        config.setdefault("integrations", {})
        config["integrations"]["github"] = {"enabled": body.github.enabled}
        if body.github.pat and not body.github.pat.endswith("****"):
            org.github_pat = body.github.pat or None

    # Slack
    if body.slack is not None:
        config.setdefault("integrations", {})
        config["integrations"]["slack"] = {"enabled": body.slack.enabled}
        if body.slack.bot_token and not body.slack.bot_token.endswith("****"):
            org.slack_bot_token = body.slack.bot_token or None
        if body.slack.signing_secret and not body.slack.signing_secret.endswith("****"):
            org.slack_signing_secret = body.slack.signing_secret or None

    # AI config
    if body.ai_config is not None:
        llm = config.get("llm", {})
        llm["preset"] = body.ai_config.preset
        llm["ollama_url"] = body.ai_config.ollama_url
        llm["ollama_model"] = body.ai_config.ollama_model
        llm["cloud_provider"] = body.ai_config.cloud_provider
        llm["cloud_model"] = body.ai_config.cloud_model
        if body.ai_config.cloud_api_key and not body.ai_config.cloud_api_key.endswith("****"):
            llm["cloud_api_key"] = body.ai_config.cloud_api_key
        config["llm"] = llm

    # Scan settings
    if body.scan is not None:
        config["scan"] = {
            "timeout_seconds": body.scan.timeout_seconds,
            "max_turns": body.scan.max_turns,
        }

    org.config = config
    await db.flush()
    await db.refresh(org)

    return await get_connections(current_user, db)


class MCPTokenResponse(BaseModel):
    """Response schema for MCP token generation."""

    mcp_token: str
    message: str = "MCP token generated. Store it securely — it will not be shown again."


@router.post("/mcp-token", response_model=MCPTokenResponse)
async def regenerate_mcp_token(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MCPTokenResponse:
    """Generate or regenerate the MCP bearer token for Claude Code integration.

    The token is shown only once. The hash is stored in the organization record.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        MCPTokenResponse with the plaintext token (one-time display).
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    mcp_token = secrets.token_urlsafe(32)
    org.mcp_token_hash = hash_password(mcp_token)
    await db.flush()

    logger.info("mcp_token_regenerated", org_id=str(org.id), user=current_user.email)

    return MCPTokenResponse(mcp_token=mcp_token)


@router.get("/mcp-token/status")
async def mcp_token_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Check whether an MCP token has been set for the organization.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Dict with has_token boolean.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    return {"has_token": org.mcp_token_hash is not None}


@router.get("/repos", response_model=list[RepoInfo])
async def list_repos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RepoInfo]:
    """List tracked repositories with knowledge item counts.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of RepoInfo with per-repo stats.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    config = org.config or {}
    source_code = config.get("source_code", {})
    knowledge_cfg = config.get("knowledge", {})
    repo_shas: dict[str, str] = knowledge_cfg.get("repo_shas", {})
    last_scan = knowledge_cfg.get("last_scan")

    # Discover repo paths
    repo_root = source_code.get("local_path", "")
    source_type = source_code.get("type", "single-repo")
    repo_paths: list[str] = []

    if repo_root:
        root = Path(repo_root)
        if source_type == "workspace" and root.exists():
            for child in sorted(root.iterdir()):
                if child.is_dir() and (child / ".git").exists():
                    repo_paths.append(str(child))
        elif root.exists() and (root / ".git").exists():
            repo_paths.append(str(root))

    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    result: list[RepoInfo] = []
    for rp in repo_paths:
        name = Path(rp).name
        prefix = f"[{name}]"
        k_count = await ki_repo.count_by_title_prefix(prefix)
        f_count = await ki_repo.count_features_by_title_prefix(prefix)
        result.append(
            RepoInfo(
                path=rp,
                name=name,
                lastScanned=last_scan,
                sha=repo_shas.get(name),
                knowledgeCount=k_count,
                featureCount=f_count,
            )
        )

    return result


@router.post("/repos", response_model=RepoInfo)
async def add_repo(
    body: AddRepoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RepoInfo:
    """Add a repository path to the workspace.

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
    config = dict(org.config or {})
    source_code = config.get("source_code", {})
    current_root = source_code.get("local_path", "")
    source_type = source_code.get("type", "single-repo")

    # If we're in workspace mode, check the repo is under the workspace root
    if source_type == "workspace" and current_root:
        workspace = Path(current_root).resolve()
        if repo_path.parent != workspace:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Repository must be under workspace root: {current_root}",
            )
    elif source_type == "single-repo":
        # Switch to workspace mode using the parent as workspace root
        config["source_code"] = {
            "local_path": str(repo_path.parent),
            "type": "workspace",
        }

    org.config = config
    await db.flush()
    await db.refresh(org)

    return RepoInfo(
        path=str(repo_path),
        name=repo_path.name,
        lastScanned=None,
        sha=None,
        knowledgeCount=0,
        featureCount=0,
    )


@router.delete("/repos", status_code=status.HTTP_200_OK)
async def remove_repo(
    body: AddRepoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove a tracked repository and deactivate its knowledge items.

    Args:
        body: Request with the path to remove.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Dict with removed path and deactivated count.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    config = dict(org.config or {})
    knowledge_cfg = config.get("knowledge", {})
    repo_shas: dict[str, str] = dict(knowledge_cfg.get("repo_shas", {}))

    repo_name = Path(body.path).name
    repo_shas.pop(repo_name, None)
    knowledge_cfg["repo_shas"] = repo_shas
    config["knowledge"] = knowledge_cfg
    org.config = config
    await db.flush()

    # Deactivate knowledge items for this repo
    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    prefix = f"[{repo_name}]"
    deactivated = await ki_repo.bulk_deactivate_by_titles(
        await ki_repo.list_titles_with_prefix(f"{prefix}%"),
        category="feature_registry",
    )

    return {"removed": body.path, "deactivated": deactivated}


def _mask_secret(value: str | None) -> str:
    """Mask a secret value for display, showing only the last 4 characters."""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]
