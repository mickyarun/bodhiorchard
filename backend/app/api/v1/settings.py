"""Settings management endpoints for the authenticated user's organization."""

import re
import secrets
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
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
    RepoBranchList,
    RepoBranchUpdate,
    RepoInfo,
    RepoStatusRequest,
    ScanSettings,
    SlackSettings,
    SourceCodeSettings,
)
from app.services.repo_scanner import (
    _detect_develop_branch,
    _detect_main_branch,
    detect_repo_type,
    detect_uncommitted_changes,
    list_remote_branches,
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
            teamId=org.slack_team_id or "",
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
        is_new_pat = bool(body.github.pat and not _is_masked(body.github.pat))
        # Auto-enable when a real PAT is provided
        enabled = body.github.enabled or is_new_pat
        config["integrations"]["github"] = {"enabled": enabled, "org": body.github.org}
        if is_new_pat:
            org.github_pat = encrypt_secret(body.github.pat) if body.github.pat else None

    # Slack
    if body.slack is not None:
        config.setdefault("integrations", {})
        config["integrations"]["slack"] = {"enabled": body.slack.enabled}
        is_new_bot_token = bool(body.slack.bot_token and not _is_masked(body.slack.bot_token))
        if is_new_bot_token:
            org.slack_bot_token = (
                encrypt_secret(body.slack.bot_token) if body.slack.bot_token else None
            )
            # Auto-fetch team_id via auth.test so we can resolve orgs from webhooks
            from app.services.slack_client import auth_test

            auth_info = await auth_test(body.slack.bot_token)
            if auth_info and auth_info.get("team_id"):
                org.slack_team_id = auth_info["team_id"]
                logger.info(
                    "slack_team_id_set",
                    team_id=org.slack_team_id,
                    org_id=str(org.id),
                )
        if body.slack.signing_secret and not _is_masked(body.slack.signing_secret):
            raw_secret = body.slack.signing_secret.strip()
            if not re.fullmatch(r"[0-9a-f]{32,}", raw_secret):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Slack signing secret must be a hex string (at least 32 chars). "
                        "Copy the full value from "
                        "Slack App → Basic Information → Signing Secret."
                    ),
                )
            org.slack_signing_secret = encrypt_secret(raw_secret)
        # Allow manual team_id override (fallback if auth.test didn't work)
        if body.slack.team_id:
            org.slack_team_id = body.slack.team_id

    # AI config
    if body.ai_config is not None:
        llm = config.get("llm", {})
        llm["preset"] = body.ai_config.preset
        llm["ollama_url"] = body.ai_config.ollama_url
        llm["ollama_model"] = body.ai_config.ollama_model
        llm["cloud_provider"] = body.ai_config.cloud_provider
        llm["cloud_model"] = body.ai_config.cloud_model
        if body.ai_config.cloud_api_key and not _is_masked(body.ai_config.cloud_api_key):
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
            mainBranch=r.main_branch,
            developBranch=r.develop_branch,
            hasUncommittedChanges=False,
            repoType=detect_repo_type(r.path),
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
        hasUncommittedChanges=has_dirty,
        repoType=detect_repo_type(str(repo_path)),
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
        hasUncommittedChanges=False,
        repoType=detect_repo_type(repo.path),
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
        hasUncommittedChanges=False,
        repoType=detect_repo_type(repo.path),
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

    # Filter out members already added to Bodhigrove
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


def _is_masked(value: str | None) -> bool:
    """Check if a value is a masked secret (contains '****').

    Masked values should never be re-encrypted — they are display-only
    placeholders returned by _mask_secret().
    """
    return bool(value and "****" in value)


# ── Slack Member Sync ─────────────────────────────────────────────


class SlackMemberPreview(BaseModel):
    """A Slack workspace member with optional auto-matched Bodhigrove user."""

    slack_id: str
    slack_name: str
    slack_avatar: str | None = None
    matched_user_id: uuid.UUID | None = None
    matched_user_name: str | None = None
    already_linked: bool = False


class SlackLinkRequest(BaseModel):
    """Mapping of Slack ID → Bodhigrove user ID for bulk linking."""

    links: list[dict[str, str]]


@router.post("/slack/sync-members", response_model=list[SlackMemberPreview])
async def sync_slack_members(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SlackMemberPreview]:
    """Fetch all Slack workspace members and match against Bodhigrove users.

    Returns a preview list showing each Slack user with their best-guess
    Bodhigrove match (by email or existing slack_id link). The admin then
    confirms/adjusts the mappings before calling link-members.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of Slack members with suggested Bodhigrove user matches.
    """
    from app.services import slack_client

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    if not org.slack_bot_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack bot token not configured.",
        )

    bot_token = decrypt_secret(org.slack_bot_token)
    slack_members = await slack_client.users_list(bot_token)

    # Load all Bodhigrove users for this org
    user_repo = UserRepository(db, org_id=org.id)
    users = await user_repo.list_by_org(org.id)

    # Build lookup maps
    email_to_user = {u.email.lower(): u for u in users}
    slack_id_to_user = {u.slack_id: u for u in users if u.slack_id}

    results: list[SlackMemberPreview] = []
    for member in slack_members:
        # Skip bots and deactivated users
        if member.get("is_bot") or member.get("deleted") or member.get("id") == "USLACKBOT":
            continue

        sid = member["id"]
        profile = member.get("profile", {})
        display_name = (
            member.get("real_name") or profile.get("display_name") or member.get("name", sid)
        )
        avatar = profile.get("image_48")
        slack_email = (profile.get("email") or "").lower()

        # Check if already linked
        if sid in slack_id_to_user:
            linked_user = slack_id_to_user[sid]
            results.append(
                SlackMemberPreview(
                    slack_id=sid,
                    slack_name=display_name,
                    slack_avatar=avatar,
                    matched_user_id=linked_user.id,
                    matched_user_name=linked_user.name,
                    already_linked=True,
                )
            )
            continue

        # Try email match as a suggestion
        matched_user = email_to_user.get(slack_email) if slack_email else None

        results.append(
            SlackMemberPreview(
                slack_id=sid,
                slack_name=display_name,
                slack_avatar=avatar,
                matched_user_id=matched_user.id if matched_user else None,
                matched_user_name=matched_user.name if matched_user else None,
                already_linked=False,
            )
        )

    # Sort: unlinked first, then linked
    results.sort(key=lambda r: (r.already_linked, r.slack_name.lower()))

    return results


@router.post("/slack/link-members")
async def link_slack_members(
    body: SlackLinkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Bulk-link Slack IDs to Bodhigrove users.

    Args:
        body: List of {slack_id, user_id} mappings.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Count of linked users.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    user_repo = UserRepository(db, org_id=org.id)

    linked = 0
    for link in body.links:
        slack_id = link.get("slack_id", "")
        user_id_str = link.get("user_id", "")
        if not slack_id or not user_id_str:
            continue

        try:
            uid = uuid.UUID(user_id_str)
        except ValueError:
            continue

        user = await user_repo.get_by_id(uid)
        if user and user.org_id == org.id:
            user.slack_id = slack_id
            linked += 1

    await db.flush()

    logger.info(
        "slack_members_linked",
        linked=linked,
        total=len(body.links),
        by=current_user.email,
    )

    return {"linked": linked}


@router.post("/slack/unlink-member")
async def unlink_slack_member(
    body: dict[str, str],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Remove the Slack link from a Bodhigrove user.

    Args:
        body: Dict with ``slack_id`` to unlink.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Success flag.
    """
    slack_id = body.get("slack_id", "")
    if not slack_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="slack_id is required",
        )

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    result = await db.execute(select(User).where(User.org_id == org.id, User.slack_id == slack_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user linked with this Slack ID",
        )

    user.slack_id = None
    await db.flush()

    logger.info(
        "slack_member_unlinked",
        slack_id=slack_id,
        user_id=str(user.id),
        by=current_user.email,
    )

    return {"success": True}
