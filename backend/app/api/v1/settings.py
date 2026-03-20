"""Settings management endpoints for the authenticated user's organization."""

import secrets
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.deps import get_current_user, get_db
from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.security import hash_password
from app.models.tracked_repository import RepoStatus
from app.models.user import User
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.repositories.user import UserRepository
from app.schemas.settings import (
    AddRepoRequest,
    AIConfigSettings,
    ConnectionsRead,
    ConnectionsUpdate,
    GitHubSettings,
    RepoInfo,
    RepoStatusRequest,
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
            pat=_mask_secret(decrypt_secret(org.github_pat or "")),
            org=github_cfg.get("org", ""),
        ),
        slack=SlackSettings(
            enabled=slack_cfg.get("enabled", False),
            botToken=_mask_secret(decrypt_secret(org.slack_bot_token or "")),
            signingSecret=_mask_secret(decrypt_secret(org.slack_signing_secret or "")),
        ),
        aiConfig=AIConfigSettings(
            preset=llm_cfg.get("preset", "hybrid"),
            ollamaUrl=llm_cfg.get("ollama_url", "http://localhost:11434"),
            ollamaModel=llm_cfg.get("ollama_model", "llama3:8b"),
            cloudProvider=llm_cfg.get("cloud_provider", "anthropic"),
            cloudApiKey=_mask_secret(decrypt_secret(llm_cfg.get("cloud_api_key", ""))),
            cloudModel=llm_cfg.get("cloud_model", "claude-sonnet-4-5-20250514"),
        ),
        scan=ScanSettings(
            timeoutSeconds=scan_cfg.get("timeout_seconds", 300),
            maxTurns=scan_cfg.get("max_turns", 40),
            autoCreateMembers=scan_cfg.get("auto_create_members", True),
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
        is_new_pat = bool(body.github.pat and not body.github.pat.endswith("****"))
        # Auto-enable when a real PAT is provided
        enabled = body.github.enabled or is_new_pat
        config["integrations"]["github"] = {"enabled": enabled, "org": body.github.org}
        if is_new_pat:
            org.github_pat = encrypt_secret(body.github.pat) if body.github.pat else None

    # Slack
    if body.slack is not None:
        config.setdefault("integrations", {})
        config["integrations"]["slack"] = {"enabled": body.slack.enabled}
        if body.slack.bot_token and not body.slack.bot_token.endswith("****"):
            org.slack_bot_token = (
                encrypt_secret(body.slack.bot_token) if body.slack.bot_token else None
            )
        if body.slack.signing_secret and not body.slack.signing_secret.endswith("****"):
            org.slack_signing_secret = (
                encrypt_secret(body.slack.signing_secret) if body.slack.signing_secret else None
            )

    # AI config
    if body.ai_config is not None:
        llm = config.get("llm", {})
        llm["preset"] = body.ai_config.preset
        llm["ollama_url"] = body.ai_config.ollama_url
        llm["ollama_model"] = body.ai_config.ollama_model
        llm["cloud_provider"] = body.ai_config.cloud_provider
        llm["cloud_model"] = body.ai_config.cloud_model
        if body.ai_config.cloud_api_key and not body.ai_config.cloud_api_key.endswith("****"):
            llm["cloud_api_key"] = encrypt_secret(body.ai_config.cloud_api_key)
        config["llm"] = llm

    # Scan settings
    if body.scan is not None:
        config["scan"] = {
            "timeout_seconds": body.scan.timeout_seconds,
            "max_turns": body.scan.max_turns,
            "auto_create_members": body.scan.auto_create_members,
        }

    org.config = config
    flag_modified(org, "config")
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

    return RepoInfo(
        id=str(repo.id),
        path=repo.path,
        name=repo.name,
        status=repo.status.value,
        lastScanned=None,
        sha=repo.head_sha,
        knowledgeCount=repo.knowledge_count,
        featureCount=repo.feature_count,
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
    import httpx

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    if not org.github_pat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub is not connected. Add a PAT in Settings.",
        )

    # Decrypt the stored PAT
    pat = decrypt_secret(org.github_pat)
    if not pat:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub PAT could not be decrypted. Please re-enter it in Settings.",
        )

    # Debug: log PAT details to diagnose auth issues
    pat_preview = f"{pat[:4]}...{pat[-4:]}" if len(pat) > 8 else "***short***"
    logger.info(
        "github_pat_debug",
        pat_length=len(pat),
        pat_preview=pat_preview,
        starts_with_github=pat.startswith("github_pat_"),
    )

    config = org.config or {}
    github_cfg = config.get("integrations", {}).get("github", {})
    github_org = github_cfg.get("org", "")
    if not github_org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub organization name is not configured in Settings.",
        )

    # Fetch org members (paginated, up to 100)
    gh_headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient() as client:
        # Try Bearer first (fine-grained PATs), fall back to token (classic)
        for auth_prefix in ("Bearer", "token"):
            gh_headers["Authorization"] = f"{auth_prefix} {pat}"
            resp = await client.get(
                f"https://api.github.com/orgs/{github_org}/members",
                params={"per_page": 100},
                headers=gh_headers,
                timeout=15,
            )
            logger.info(
                "github_api_attempt",
                auth_prefix=auth_prefix,
                status=resp.status_code,
                body=resp.text[:300] if resp.text else "",
            )
            if resp.status_code != 401:
                break

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
    import asyncio

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
        gh_headers["Authorization"] = f"Bearer {pat}"
        profiles = await asyncio.gather(
            *[_fetch_profile(profile_client, m.get("login", "")) for m in members]
        )

    # Filter out members already added to FlowDev
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


def _mask_secret(value: str | None) -> str:
    """Mask a secret value for display, showing only the last 4 characters."""
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]
