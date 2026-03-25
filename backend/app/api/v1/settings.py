"""Settings management endpoints for the authenticated user's organization.

Connection config, MCP token management, and sub-router wiring for
repo management, GitHub integration, and Slack member sync.
"""

import re
import secrets

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.v1.settings_repos import router as repos_router
from app.api.v1.settings_slack import router as slack_router
from app.core.deps import get_current_user, get_db, require_permissions
from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.security import hash_password
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.schemas.settings import (
    AIConfigSettings,
    ConnectionsRead,
    ConnectionsUpdate,
    GitHubSettings,
    ScanSettings,
    SlackSettings,
    SourceCodeSettings,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings"])
router.include_router(repos_router)
router.include_router(slack_router)


@router.get(
    "/connections",
    response_model=ConnectionsRead,
    dependencies=[Depends(require_permissions("integrations:view"))],
)
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
            patExpiresAt=github_cfg.get("pat_expires_at"),
        ),
        slack=SlackSettings(
            enabled=slack_cfg.get("enabled", False),
            botToken=_mask_secret(decrypt_secret(org.slack_bot_token or "")),
            signingSecret=_mask_secret(decrypt_secret(org.slack_signing_secret or "")),
            teamId=org.slack_team_id or "",
        ),
        aiConfig=AIConfigSettings(
            preset=llm_cfg.get("preset", "claude-code"),
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


@router.patch(
    "/connections",
    response_model=ConnectionsRead,
    dependencies=[Depends(require_permissions("integrations:configure"))],
)
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

    # Source code — repos are managed via tracked_repositories table,
    # no longer stored in JSONB config.

    # GitHub
    if body.github is not None:
        config.setdefault("integrations", {})
        is_new_pat = bool(body.github.pat and not _is_masked(body.github.pat))
        # Auto-enable when a real PAT is provided
        enabled = body.github.enabled or is_new_pat
        # Preserve existing pat_expires_at unless we detect a new one
        existing_github = config.get("integrations", {}).get("github", {})
        pat_expires_at = existing_github.get("pat_expires_at")
        if is_new_pat:
            org.github_pat = encrypt_secret(body.github.pat) if body.github.pat else None
            pat_expires_at = await _check_github_pat_expiry(body.github.pat)
        config["integrations"]["github"] = {
            "enabled": enabled,
            "org": body.github.org,
            "pat_expires_at": pat_expires_at,
        }

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

    # AI config — only persist preset (Claude Code only for now)
    if body.ai_config is not None:
        config["llm"] = {"preset": body.ai_config.preset}

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


@router.post(
    "/mcp-token",
    response_model=MCPTokenResponse,
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
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


@router.get(
    "/mcp-token/status",
    dependencies=[Depends(require_permissions("org:view_settings"))],
)
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


# ── Helpers ───────────────────────────────────────────────────────


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


async def _check_github_pat_expiry(pat: str) -> str | None:
    """Call GitHub API to extract the token expiration date from response headers.

    Fine-grained PATs return a ``github-authentication-token-expiration``
    header (e.g. ``2026-06-15 00:00:00 UTC``). Classic PATs without expiry
    don't include this header, so None is returned.

    Args:
        pat: The raw (unencrypted) GitHub Personal Access Token.

    Returns:
        ISO-8601 expiry string, or None if the token has no expiry.
    """
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {pat}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=10,
            )
        expiry_header = resp.headers.get("github-authentication-token-expiration")
        if expiry_header:
            # Header formats vary: "2026-06-15 00:00:00 UTC" or "2027-03-26 11:37:19 +0530"
            from datetime import datetime

            raw = expiry_header.strip()
            # Replace timezone name "UTC" with "+0000" so %z handles both formats
            normalized = raw.replace(" UTC", " +0000")
            dt = datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S %z")
            return dt.isoformat()
    except Exception:
        logger.warning("github_pat_expiry_check_failed", exc_info=True)
    return None
