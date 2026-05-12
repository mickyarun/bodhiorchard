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

"""Settings management endpoints for the authenticated user's organization.

Connection config, MCP token management, and sub-router wiring for
repo management, GitHub integration, and Slack member sync.
"""

import re
import secrets
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.v1.settings_claude import router as claude_router
from app.api.v1.settings_github_members import router as gh_members_router
from app.api.v1.settings_repos import router as repos_router
from app.api.v1.settings_slack import router as slack_router
from app.core.deps import get_current_user, get_db, require_permissions
from app.core.encryption import decrypt_secret, encrypt_secret
from app.core.security import hash_password
from app.mcp.auth import compute_token_prefix
from app.models.organization import Organization
from app.models.user import User
from app.models.user_mcp_token import UserMCPToken
from app.repositories.organization import OrganizationRepository
from app.schemas.settings import (
    AIConfigSettings,
    ConnectionsRead,
    ConnectionsUpdate,
    GitHubAppStatus,
    GitHubSettings,
    JiraSettingsRead,
    ScanSettings,
    SlackSettings,
    SourceCodeSettings,
)
from app.services.github_app_auth import fetch_and_persist_app_slug
from app.services.github_app_jwt import (
    GITHUB_APP_INSTALL_URL_TEMPLATE as _APP_INSTALL_URL_TEMPLATE,
)
from app.services.github_app_slug import (
    GitHubAppNotFound,
    GitHubAppValidationError,
    GitHubCredentialsInvalid,
    GitHubUnreachable,
    validate_and_persist_app_slug,
)
from app.services.org_settings import (
    get_bud_stage_settings,
    get_jira_settings,
    get_presence_settings,
    get_qa_settings,
)
from app.services.slack_client import auth_test

# Re-exported from ``github_app_jwt`` so service-layer modules can use
# the same template without importing this route module (which would
# create a cycle through ``settings_repos``). Kept as a module-level
# name here for back-compat with anything that imports it from the
# route module.
GITHUB_APP_INSTALL_URL_TEMPLATE = _APP_INSTALL_URL_TEMPLATE

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings"])
router.include_router(repos_router)
router.include_router(slack_router)
router.include_router(claude_router)
router.include_router(gh_members_router)


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
    slack_cfg = integrations_cfg.get("slack", {})
    llm_cfg = config.get("llm", {})
    scan_cfg = config.get("scan", {})

    # qa / bud_stages / presence sections are resolved through org_settings
    # so defaults stay in lockstep with every other reader (prompt builder,
    # estimation, status transitions, presence sim). Never read those keys
    # directly from `config` — the helpers are the single source of truth.
    qa_cfg = get_qa_settings(config)
    stage_cfg = get_bud_stage_settings(config)
    presence_cfg = get_presence_settings(config)

    return ConnectionsRead(
        sourceCode=SourceCodeSettings(
            localPath=source_code_cfg.get("local_path", ""),
            type=source_code_cfg.get("type", "single-repo"),
        ),
        github=_build_github_settings(org),
        slack=SlackSettings(
            enabled=slack_cfg.get("enabled", False),
            connected=bool(org.slack_bot_token),
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
            mergeModelDefault=llm_cfg.get("merge_model_default"),
            mergeModelLarge=llm_cfg.get("merge_model_large"),
        ),
        scan=ScanSettings(
            timeoutSeconds=scan_cfg.get("timeout_seconds", 300),
            mergeTimeoutSeconds=scan_cfg.get("merge_timeout_seconds", 300),
            maxTurns=scan_cfg.get("max_turns", 40),
            autoCreateMembers=scan_cfg.get("auto_create_members", True),
        ),
        # qa_cfg / stage_cfg / presence_cfg are already schema instances
        # (the helpers reuse the same classes), so we can pass them through
        # directly — one source of defaults.
        qa_automation=qa_cfg,
        bud_stages=stage_cfg,
        presence=presence_cfg,
        jira=_build_jira_read(config),
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

    # GitHub App — track whether the user supplied any credential field
    # in this PATCH so we can run synchronous validation (Phase J) instead
    # of the lenient retrofit. Validating on unrelated PATCHes (e.g. a
    # presence-settings toggle) would be wrong; the lenient path keeps
    # the existing behaviour for those.
    github_credentials_supplied = False
    if body.github is not None:
        config.setdefault("integrations", {})
        if body.github.app_id is not None:
            org.github_app_id = body.github.app_id
            github_credentials_supplied = True
        if body.github.private_key:
            org.github_app_private_key = encrypt_secret(body.github.private_key)
            github_credentials_supplied = True
        if body.github.webhook_secret:
            org.github_webhook_secret = encrypt_secret(body.github.webhook_secret)
        if body.github.installation_id is not None:
            org.github_app_installation_id = body.github.installation_id
        config["integrations"]["github"] = {
            "enabled": bool(org.github_app_id),
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

    # AI config — preset + optional per-org merge model overrides.
    if body.ai_config is not None:
        existing_llm = dict(config.get("llm") or {})
        existing_llm["preset"] = body.ai_config.preset
        # None on either field means "use platform default"; persist as
        # absent rather than null so get_merge_models's allowlist logic
        # sees a clean fallback path.
        if body.ai_config.merge_model_default is None:
            existing_llm.pop("merge_model_default", None)
        else:
            existing_llm["merge_model_default"] = body.ai_config.merge_model_default
        if body.ai_config.merge_model_large is None:
            existing_llm.pop("merge_model_large", None)
        else:
            existing_llm["merge_model_large"] = body.ai_config.merge_model_large
        config["llm"] = existing_llm

    # Scan settings
    if body.scan is not None:
        config["scan"] = {
            "timeout_seconds": body.scan.timeout_seconds,
            "merge_timeout_seconds": body.scan.merge_timeout_seconds,
            "max_turns": body.scan.max_turns,
            "auto_create_members": body.scan.auto_create_members,
        }

    # QA automation — framework string is pattern-validated at schema level
    # (see QAAutomationSettings). model_dump() uses the canonical snake_case
    # field names that org_settings.get_qa_settings() reads back; this keeps
    # the write and read paths aligned via the one class definition.
    if body.qa_automation is not None:
        config["qa"] = body.qa_automation.model_dump()

    # BUD stage toggles (e.g. whether UAT is part of this org's lifecycle)
    if body.bud_stages is not None:
        config["bud_stages"] = body.bud_stages.model_dump()

    # Presence / auto-mode settings (working days, hours, timezone).
    # by_alias=False so stored JSON stays in snake_case to match the other
    # sections. ``get_presence_settings`` reads from this exact shape.
    if body.presence is not None:
        config["presence"] = body.presence.model_dump(mode="json", by_alias=False)

    org.config = config
    flag_modified(org, "config")
    await db.flush()
    await db.refresh(org)

    # GitHub-App credential validation (Phase J).
    #
    # When the user supplied at least one credential field in this
    # PATCH, we must give them a synchronous yes/no. ``GET /app`` either
    # accepts the JWT (good) or returns 401/404 (bad) — translate that
    # to a typed 400 so the credentials form can render an inline alert.
    #
    # If no credential fields are part of this PATCH (e.g. the user
    # only flipped a toggle elsewhere), keep the lenient retrofit so we
    # never break unrelated paths because of a transient GitHub blip.
    if org.github_app_id and org.github_app_private_key and github_credentials_supplied:
        try:
            await validate_and_persist_app_slug(org, db)
        except GitHubCredentialsInvalid as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": exc.code, "message": exc.message},
            ) from exc
        except GitHubAppNotFound as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": exc.code, "message": exc.message},
            ) from exc
        except GitHubUnreachable as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"error": exc.code, "message": exc.message},
            ) from exc
        except GitHubAppValidationError as exc:  # pragma: no cover — future codes
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": exc.code, "message": exc.message},
            ) from exc
    elif org.github_app_id and org.github_app_private_key and org.github_app_slug is None:
        # Lenient retrofit — fire and forget on the request session.
        # Logs a warning and continues if GitHub is unreachable.
        await fetch_and_persist_app_slug(org, db)

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

    Creates a per-user token (stored in user_mcp_tokens) that identifies
    both the organization and the specific developer. The old org-level
    token is also updated for backward compatibility.

    The token is shown only once.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        MCPTokenResponse with the plaintext token (one-time display).
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    mcp_token = secrets.token_urlsafe(32)
    token_hash = hash_password(mcp_token)
    token_prefix = compute_token_prefix(mcp_token)

    # Update org-level token (backward compat for existing integrations)
    org.mcp_token_hash = token_hash
    await db.flush()

    # Upsert per-user token (one token per user per org)
    existing = await db.execute(
        select(UserMCPToken).where(
            UserMCPToken.user_id == current_user.id,
            UserMCPToken.org_id == org.id,
        )
    )
    user_token = existing.scalar_one_or_none()
    if user_token:
        user_token.token_hash = token_hash
        user_token.token_prefix = token_prefix
    else:
        user_token = UserMCPToken(
            user_id=current_user.id,
            org_id=org.id,
            token_hash=token_hash,
            token_prefix=token_prefix,
        )
        db.add(user_token)
    await db.flush()

    logger.info(
        "mcp_token_regenerated",
        org_id=str(org.id),
        user=current_user.email,
        user_token=True,
    )

    return MCPTokenResponse(mcp_token=mcp_token)


@router.get(
    "/mcp-token/status",
    dependencies=[Depends(require_permissions("org:view_settings"))],
)
async def mcp_token_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
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


# ── GitHub Webhook Secret ─────────────────────────────────────────


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


def _resolve_github_app_status(org: Organization) -> GitHubAppStatus:
    """Map an org's GitHub App columns onto the public lifecycle enum."""
    if not org.github_app_id or not org.github_app_private_key:
        return GitHubAppStatus.NOT_CONFIGURED
    if not org.github_app_installation_id:
        return GitHubAppStatus.AWAITING_INSTALL
    return GitHubAppStatus.READY


def _build_github_settings(org: Organization) -> GitHubSettings:
    """Compose the ``GitHubSettings`` response payload for an org.

    ``connected`` is preserved as ``status != NOT_CONFIGURED`` so the
    legacy boolean keeps working alongside the richer ``status`` enum.
    """
    status = _resolve_github_app_status(org)
    install_url = (
        GITHUB_APP_INSTALL_URL_TEMPLATE.format(slug=org.github_app_slug)
        if org.github_app_slug
        else None
    )
    return GitHubSettings(
        enabled=bool(org.github_app_id),
        connected=status != GitHubAppStatus.NOT_CONFIGURED,
        appId=org.github_app_id,
        hasPrivateKey=bool(org.github_app_private_key),
        installationId=org.github_app_installation_id,
        webhookConfigured=bool(org.github_webhook_secret),
        status=status,
        slug=org.github_app_slug,
        installUrl=install_url,
    )


def _build_jira_read(config: dict[str, Any]) -> JiraSettingsRead:
    """Build the read-only Jira settings (no token) from org config."""
    jira = get_jira_settings(config)
    return JiraSettingsRead(
        enabled=jira.is_connected,
        site_url=jira.site_url,
        email=jira.email,
        connected_at=jira.connected_at,
    )
