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

"""Stage-1 of the wizard: create the org + admin user.

Extracted from :func:`app.api.v1.setup.initialize_setup` so the new
two-stage wizard (``POST /setup/init-org`` then
``POST /setup/finalize-with-repos``) can run org provisioning ahead of
the GitHub-App install + repo selection step. The legacy single-shot
endpoint composes this helper with
:func:`app.services.setup_finalize.setup_finalize_with_repos` to keep
its existing contract.
"""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt_secret
from app.core.security import create_access_token, hash_password
from app.models.organization import AIProvider, Organization
from app.models.user import OrgToUser, User
from app.repositories.organization import OrganizationRepository
from app.repositories.role import RoleRepository
from app.schemas.setup import InitOrgRequest
from app.services.ai_runner.capabilities import capabilities_for
from app.services.bud_stage_seeder import seed_stage_mappings_for_org
from app.services.claude_env import (
    AUTH_MODE_API_KEY,
    AUTH_MODE_SUBSCRIPTION,
    apply_claude_auth_to_env,
)
from app.services.permission_seeder import seed_permissions
from app.services.repo_cloner import purge_org_clones
from app.services.skill_loader import seed_skills_for_org

logger = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────

_MCP_TOKEN_NUM_BYTES = 32
_OWNER_ROLE_NAME = "org_owner"
_LLM_PRESET = "claude-code"


@dataclass(slots=True)
class InitOrgResult:
    """Aggregate result of stage-1 provisioning.

    The mcp_token is the cleartext value (we only persist its hash on
    the org); callers must surface it to the user immediately because
    it cannot be recovered later.
    """

    org: Organization
    user: User
    access_token: str
    mcp_token: str


def _build_org_config(req: InitOrgRequest) -> dict[str, object]:
    """Build the ``Organization.config`` JSON for a freshly-provisioned org."""
    return {
        "llm": {"preset": _LLM_PRESET},
        "integrations": {
            "github": {"enabled": False},
            "slack": {"enabled": False},
        },
        "scan": {
            "timeout_seconds": req.scan.timeout_seconds,
            "max_turns": req.scan.max_turns,
            "auto_create_members": True,
        },
    }


def _clean_base_url(value: str | None) -> str | None:
    """Validate the wizard's server address, or None to use the default.

    Only http/https — this string reaches an HTTP client, and the wizard is
    unauthenticated, so it validates rather than trusts.
    """
    cleaned = (value or "").strip().rstrip("/")
    if not cleaned:
        return None
    if not cleaned.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="claude.base_url must start with http:// or https://",
        )
    return cleaned


def _resolve_claude_auth(req: InitOrgRequest) -> tuple[AIProvider, str, str | None]:
    """Validate the wizard's AI-provider choice → ``(provider, mode, key)``."""
    try:
        provider = AIProvider(req.claude.provider)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"claude.provider must be one of {[p.value for p in AIProvider]}",
        ) from exc

    claude_auth_mode = req.claude.auth_mode
    valid_modes = {m.value for m in capabilities_for(provider).auth_modes}
    if claude_auth_mode not in valid_modes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"claude.auth_mode must be one of {sorted(valid_modes)} for {provider.value}",
        )
    encrypted_key: str | None = None
    if claude_auth_mode == AUTH_MODE_API_KEY:
        key = (req.claude.api_key or "").strip()
        if not key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="claude.api_key is required when auth_mode is 'api_key'",
            )
        encrypted_key = encrypt_secret(key)
    elif claude_auth_mode == AUTH_MODE_SUBSCRIPTION:
        token = (req.claude.oauth_token or "").strip()
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="claude.oauth_token is required when auth_mode is 'subscription'",
            )
        encrypted_key = encrypt_secret(token)
    return provider, claude_auth_mode, encrypted_key


async def setup_init_org(req: InitOrgRequest, db: AsyncSession) -> InitOrgResult:
    """Provision the organization, admin user, role, and MCP token.

    Idempotency note: the caller must have already gated on
    ``_require_setup_incomplete``. Re-calling this without that gate
    will collide on the org slug and raise a 409.
    """
    org_repo = OrganizationRepository(db)
    if await org_repo.get_by_slug(req.organization.slug) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists. Setup may have been completed already.",
        )

    provider, claude_auth_mode, encrypted_key = _resolve_claude_auth(req)

    mcp_token = secrets.token_urlsafe(_MCP_TOKEN_NUM_BYTES)

    # Host-scoped settings only apply to a provider that runs against the org's
    # own machine; storing them for one that ignores them would leave state
    # nobody can see and nothing reads.
    caps = capabilities_for(provider)
    org = Organization(
        name=req.organization.name,
        slug=req.organization.slug,
        config=_build_org_config(req),
        mcp_token_hash=hash_password(mcp_token),
        ai_provider=provider,
        claude_auth_mode=claude_auth_mode,
        claude_api_key_encrypted=encrypted_key,
        ai_base_url=_clean_base_url(req.claude.base_url) if caps.requires_base_url else None,
        ai_model=((req.claude.model or "").strip() or None) if caps.dynamic_models else None,
        ai_thinking=bool(req.claude.thinking) if caps.supports_thinking else False,
    )
    db.add(org)
    await db.flush()

    # Push the chosen Claude auth into the backend process env so any
    # scan kicked off in stage-2 can reach Claude without a restart.
    apply_claude_auth_to_env(org)

    user = User(
        email=req.admin.email,
        name=req.admin.name,
        password_hash=hash_password(req.admin.password),
    )
    db.add(user)
    await db.flush()

    # Seed permissions, agent skills, and stage mappings before
    # attaching the membership so the role lookup below can rely on
    # the system roles existing.
    await seed_permissions(db)
    await seed_skills_for_org(org.id, db)
    await seed_stage_mappings_for_org(org.id, db)

    role_repo = RoleRepository(db)
    owner_role = await role_repo.get_by_name_system(_OWNER_ROLE_NAME)

    membership = OrgToUser(
        user_id=user.id,
        org_id=org.id,
        role_id=owner_role.id if owner_role else None,
    )
    db.add(membership)
    await db.flush()

    # Commit before returning so a follow-up stage-2 call (separate
    # request, separate session) sees the new rows. Stage-2 also opens
    # its own session for ``start_scan``.
    await db.commit()

    # Wipe any leftover clones from a prior deployment of this slug. The
    # DB has just been seeded with a fresh org row, so anything sitting
    # under ``repoclone/<slug>/`` is orphaned (no TrackedRepository points
    # at it) and would otherwise be picked up by the cloner's
    # ``already_cloned`` branch on the next bulk-onboard.
    await asyncio.to_thread(purge_org_clones, org.slug)

    token = create_access_token(data={"sub": str(user.id), "org_id": str(org.id)})

    logger.info(
        "setup_init_org_complete",
        org_id=str(org.id),
        org_slug=org.slug,
        admin_email=user.email,
    )
    return InitOrgResult(org=org, user=user, access_token=token, mcp_token=mcp_token)
