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

"""Claude Code authentication settings.

Lets the org admin choose between Hybrid mode (the container trusts whatever
``claude login`` or ``ANTHROPIC_API_KEY`` the host already has) and Full Docker
mode (a per-org encrypted API key, applied to the backend process env).
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.core.encryption import encrypt_secret
from app.models.organization import AIProvider, Organization
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.services.ai_runner.capabilities import capabilities_for
from app.services.ai_runner.connection_check import check_provider_connection
from app.services.claude_env import (
    AUTH_MODE_API_KEY,
    AUTH_MODE_HOST,
    AUTH_MODE_SUBSCRIPTION,
    apply_claude_auth_to_env,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings-claude"])


class ClaudeSettingsRead(BaseModel):
    """Current AI-provider state for the org — the credential is never returned."""

    provider: str
    auth_mode: str
    has_api_key: bool
    # Only meaningful for providers that run against the org's own host.
    base_url: str | None = None
    model: str | None = None
    thinking: bool = False


class ClaudeSettingsUpdate(BaseModel):
    """Update the org's AI provider, auth mode, and (optionally) its credential.

    ``provider`` selects the agent (claude / copilot / codex / ollama).
    ``api_key`` is consumed in ``api_key`` mode (an Anthropic key, GitHub
    token, or OpenAI key depending on provider), ``oauth_token`` in Claude
    ``subscription`` mode. Omitting the credential while staying in the same
    mode keeps the stored one; switching modes requires the new credential.
    ``host`` mode clears it.

    ``base_url``/``model``/``thinking`` apply to providers that run against the
    org's own host; they are cleared when switching to one that doesn't, so a
    stale host can't linger on a provider that ignores it.
    """

    provider: str | None = Field(
        None, description="One of 'claude', 'copilot', 'codex', 'ollama'."
    )
    auth_mode: str = Field(..., description="An auth mode valid for the chosen provider.")
    api_key: str | None = None
    oauth_token: str | None = None
    base_url: str | None = Field(None, description="Server address, for HTTP-based providers.")
    model: str | None = Field(None, description="Model id, for host-provided model lists.")
    thinking: bool | None = Field(None, description="Let the model reason before answering.")


def _clean_base_url(value: str | None) -> str | None:
    """Validate a user-supplied server address, or None to use the default.

    Only http/https: this string is handed to an HTTP client, and anything else
    (file://, a shell fragment) has no business reaching it.
    """
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        return None
    if not cleaned.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="base_url must start with http:// or https://",
        )
    return cleaned


def _read_model(org: Organization) -> ClaudeSettingsRead:
    """The org's provider state as the UI sees it. One shape, two endpoints."""
    return ClaudeSettingsRead(
        provider=(org.ai_provider or AIProvider.claude).value,
        auth_mode=org.claude_auth_mode,
        has_api_key=bool(org.claude_api_key_encrypted),
        base_url=org.ai_base_url,
        model=org.ai_model,
        thinking=org.ai_thinking,
    )


def _resolve_provider(value: str | None, current: AIProvider) -> AIProvider:
    """Validate an incoming provider string, defaulting to the org's current."""
    if value is None:
        return current
    try:
        return AIProvider(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"provider must be one of {[p.value for p in AIProvider]}",
        ) from exc


def _apply_credential(
    org: Organization, *, supplied: str | None, field: str, mode_unchanged: bool
) -> None:
    """Store a freshly supplied credential, or keep the existing one only when
    staying in the same mode.

    Switching modes requires a new credential, so an old API key is never
    reinterpreted as an OAuth token (or vice versa) — both live in the same
    encrypted column.
    """
    if supplied is not None:
        trimmed = supplied.strip()
        if not trimmed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{field} cannot be blank for this auth mode",
            )
        org.claude_api_key_encrypted = encrypt_secret(trimmed)
        return
    if not (mode_unchanged and org.claude_api_key_encrypted):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} is required when switching to this auth mode",
        )


@router.get("/claude", response_model=ClaudeSettingsRead)
async def get_claude_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClaudeSettingsRead:
    """Return the org's current AI-provider auth configuration."""
    org = await OrganizationRepository(db).get_for_user(current_user)
    return _read_model(org)


@router.patch(
    "/claude",
    response_model=ClaudeSettingsRead,
    dependencies=[Depends(require_permissions("integrations:configure"))],
)
async def update_claude_settings(
    body: ClaudeSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ClaudeSettingsRead:
    """Update the org's AI provider + auth mode and optionally the credential.

    On save, the decrypted credential is also pushed into the backend
    process's ``os.environ`` so subsequent agent runs pick it up without a
    restart. Switching provider requires a fresh credential (an Anthropic key
    must never be reinterpreted as a GitHub/OpenAI token).
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    current_provider = org.ai_provider or AIProvider.claude
    target_provider = _resolve_provider(body.provider, current_provider)

    valid_modes = {m.value for m in capabilities_for(target_provider).auth_modes}
    if body.auth_mode not in valid_modes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"auth_mode must be one of {sorted(valid_modes)} for {target_provider.value}",
        )

    previous_mode = org.claude_auth_mode
    provider_changed = target_provider != current_provider
    org.ai_provider = target_provider
    org.claude_auth_mode = body.auth_mode

    if body.auth_mode == AUTH_MODE_API_KEY:
        _apply_credential(
            org,
            supplied=body.api_key,
            field="api_key",
            mode_unchanged=previous_mode == AUTH_MODE_API_KEY and not provider_changed,
        )
    elif body.auth_mode == AUTH_MODE_SUBSCRIPTION:
        _apply_credential(
            org,
            supplied=body.oauth_token,
            field="oauth_token",
            mode_unchanged=previous_mode == AUTH_MODE_SUBSCRIPTION and not provider_changed,
        )
    elif body.auth_mode == AUTH_MODE_HOST:
        org.claude_api_key_encrypted = None

    # Host-scoped settings only mean anything to a provider that runs against
    # the org's own machine. Clear them otherwise, so switching to Ollama later
    # can't silently inherit a host someone typed months ago for a different
    # provider — and so a stale model id can't outlive the provider that knew it.
    target_caps = capabilities_for(target_provider)
    if target_caps.requires_base_url:
        org.ai_base_url = _clean_base_url(body.base_url)
    else:
        org.ai_base_url = None
    if target_caps.dynamic_models:
        org.ai_model = (body.model or "").strip() or None
    else:
        org.ai_model = None
    org.ai_thinking = bool(body.thinking) if target_caps.supports_thinking else False

    await db.flush()
    apply_claude_auth_to_env(org)

    logger.info(
        "ai_settings_updated",
        org_id=str(org.id),
        provider=org.ai_provider.value,
        auth_mode=org.claude_auth_mode,
        has_api_key=bool(org.claude_api_key_encrypted),
        by=current_user.email,
    )

    return _read_model(org)


@router.post("/claude/test")
async def test_claude_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Run the org's provider version check + a trivial prompt against its auth."""
    # Ensure the most recent stored credential (if any) is in process env
    # first, in case the backend was restarted since the last PATCH.
    org = await OrganizationRepository(db).get_for_user(current_user)
    apply_claude_auth_to_env(org)
    return await check_provider_connection(org)
