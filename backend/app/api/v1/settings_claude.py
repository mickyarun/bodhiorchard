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
from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.services.claude_env import (
    AUTH_MODE_API_KEY,
    AUTH_MODE_HOST,
    AUTH_MODE_SUBSCRIPTION,
    VALID_AUTH_MODES,
    apply_claude_auth_to_env,
)
from app.services.claude_runner import test_claude_connection

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["settings-claude"])


class ClaudeSettingsRead(BaseModel):
    """Current Claude auth state for the org — key itself is never returned."""

    auth_mode: str
    has_api_key: bool


class ClaudeSettingsUpdate(BaseModel):
    """Update the org's Claude auth mode and (optionally) its credential.

    ``api_key`` is consumed in ``api_key`` mode, ``oauth_token`` in
    ``subscription`` mode. Omitting the credential while staying in the same
    mode keeps the stored one; switching modes requires the new credential.
    Switching to ``host`` mode clears the stored credential.
    """

    auth_mode: str = Field(..., description="One of 'host', 'api_key', 'subscription'.")
    api_key: str | None = None
    oauth_token: str | None = None


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
    """Return the org's current Claude auth configuration."""
    org = await OrganizationRepository(db).get_for_user(current_user)
    return ClaudeSettingsRead(
        auth_mode=org.claude_auth_mode,
        has_api_key=bool(org.claude_api_key_encrypted),
    )


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
    """Update Claude auth mode and optionally the API key.

    On save, the decrypted key is also pushed into the backend process's
    ``os.environ`` so subsequent agent runs pick it up without a restart.
    """
    if body.auth_mode not in VALID_AUTH_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"auth_mode must be one of {sorted(VALID_AUTH_MODES)}",
        )

    org = await OrganizationRepository(db).get_for_user(current_user)
    previous_mode = org.claude_auth_mode
    org.claude_auth_mode = body.auth_mode

    if body.auth_mode == AUTH_MODE_API_KEY:
        _apply_credential(
            org,
            supplied=body.api_key,
            field="api_key",
            mode_unchanged=previous_mode == AUTH_MODE_API_KEY,
        )
    elif body.auth_mode == AUTH_MODE_SUBSCRIPTION:
        _apply_credential(
            org,
            supplied=body.oauth_token,
            field="oauth_token",
            mode_unchanged=previous_mode == AUTH_MODE_SUBSCRIPTION,
        )
    elif body.auth_mode == AUTH_MODE_HOST:
        org.claude_api_key_encrypted = None

    await db.flush()
    apply_claude_auth_to_env(org)

    logger.info(
        "claude_settings_updated",
        org_id=str(org.id),
        auth_mode=org.claude_auth_mode,
        has_api_key=bool(org.claude_api_key_encrypted),
        by=current_user.email,
    )

    return ClaudeSettingsRead(
        auth_mode=org.claude_auth_mode,
        has_api_key=bool(org.claude_api_key_encrypted),
    )


@router.post("/claude/test")
async def test_claude_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Run ``claude --version`` + a trivial prompt against the current auth."""
    # Ensure the most recent stored key (if any) is in process env first, in
    # case the backend was restarted since the last PATCH.
    org = await OrganizationRepository(db).get_for_user(current_user)
    apply_claude_auth_to_env(org)
    return await test_claude_connection()
