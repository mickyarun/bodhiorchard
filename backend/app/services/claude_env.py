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

"""Claude Code auth-mode → process-environment bridge.

Bodhiorchard has eleven call sites that spawn ``claude`` as a subprocess via
``claude_runner.run_claude_code``. Each inherits ``os.environ``, so injecting
``ANTHROPIC_API_KEY`` into the parent process is the least-invasive way to
wire up per-org API keys without touching every call site.

This works cleanly for the documented single-tenant deployment model ("runs
locally on your laptop or Mac Mini"). Multi-tenant concurrent runs with
different keys would need per-call injection instead — see ``claude_runner``'s
``env_extra`` argument.
"""

from __future__ import annotations

import os

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret
from app.models.organization import AIProvider, Organization
from app.repositories.organization import OrganizationRepository
from app.services.ai_runner.capabilities import AuthModeSpec, capabilities_for

logger = structlog.get_logger(__name__)

AUTH_MODE_HOST = "host"
AUTH_MODE_API_KEY = "api_key"
# Claude Pro/Max subscription via a long-lived OAuth token from
# ``claude setup-token``. Works in Full Docker because the token is just a
# string — no host ``claude login`` session needed.
AUTH_MODE_SUBSCRIPTION = "subscription"
VALID_AUTH_MODES = frozenset({AUTH_MODE_HOST, AUTH_MODE_API_KEY, AUTH_MODE_SUBSCRIPTION})

# Modes that store an encrypted credential on the org (in
# ``claude_api_key_encrypted`` — an API key for api_key mode, an OAuth token for
# subscription mode). Used by the startup loader.
CREDENTIAL_AUTH_MODES = frozenset({AUTH_MODE_API_KEY, AUTH_MODE_SUBSCRIPTION})

_API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"
_OAUTH_ENV_VAR = "CLAUDE_CODE_OAUTH_TOKEN"

# Every credential env var the app injects, across all providers. On apply we
# clear the ones the active mode doesn't set, so a deselected provider's token
# can't shadow the active one. GH_TOKEN is deliberately EXCLUDED — it's the
# host's git/gh credential, never app-managed, so we must not clear it.
_MANAGED_CRED_VARS = frozenset(
    {_API_KEY_ENV_VAR, _OAUTH_ENV_VAR, "COPILOT_GITHUB_TOKEN", "OPENAI_API_KEY", "OLLAMA_API_KEY"}
)


def _provider_of(org: Organization) -> AIProvider:
    """The org's selected provider, defaulting to Claude."""
    return org.ai_provider or AIProvider.claude


def _auth_mode_spec(provider: AIProvider, mode: str) -> AuthModeSpec | None:
    """Find the provider's spec for ``mode`` (None if it doesn't support it)."""
    for spec in capabilities_for(provider).auth_modes:
        if spec.value == mode:
            return spec
    return None


def _host_preserved_vars(provider: AIProvider) -> set[str]:
    """Env vars the host/compose owns for ``provider`` — never cleared.

    Sourced from the provider's ``host`` auth-mode ``env_vars`` so the
    capability table is the single source of truth (e.g. a compose-level
    ``ANTHROPIC_API_KEY`` for Claude, the host's ``GH_TOKEN`` for Copilot).
    """
    host_spec = _auth_mode_spec(provider, AUTH_MODE_HOST)
    return set(host_spec.env_vars) if host_spec else set()


def apply_claude_auth_to_env(org: Organization) -> None:
    """Push an organization's AI-provider auth choice into ``os.environ``.

    Provider-aware: the env var the stored credential maps to is looked up
    from the provider's capability table (Claude → ``ANTHROPIC_API_KEY`` /
    ``CLAUDE_CODE_OAUTH_TOKEN``; Copilot → ``COPILOT_GITHUB_TOKEN``; Codex →
    ``OPENAI_API_KEY``). Applying a credentialed mode clears the other
    providers' app-managed vars so a deselected token can't shadow the active
    one. ``host`` mode leaves the process env alone except for clearing
    app-managed vars the host doesn't own (a compose ``ANTHROPIC_API_KEY`` for
    Claude, or the host's ``GH_TOKEN`` for Copilot, are preserved).

    The function name is kept for back-compat with existing call sites.
    Invoke on app startup and whenever the org's setting changes.
    """
    provider = _provider_of(org)
    spec = _auth_mode_spec(provider, org.claude_auth_mode)

    if spec is not None and spec.requires_secret and org.claude_api_key_encrypted:
        decrypted = decrypt_secret(org.claude_api_key_encrypted)
        if decrypted:
            # Never log any portion of the secret — even a prefix is a partial
            # credential that shouldn't reach log aggregators.
            for var in spec.env_vars:
                os.environ[var] = decrypted
            for var in _MANAGED_CRED_VARS - set(spec.env_vars):
                os.environ.pop(var, None)
            logger.info(
                "ai_env_credential_applied",
                org_id=str(org.id),
                provider=provider.value,
                mode=org.claude_auth_mode,
            )
            return

    # host mode (or a credentialed mode with an empty/corrupt secret): clear
    # app-managed vars the host doesn't own for this provider, but preserve
    # host/compose-supplied credentials (e.g. Claude's ANTHROPIC_API_KEY).
    preserve = _host_preserved_vars(provider)
    for var in _MANAGED_CRED_VARS - preserve:
        os.environ.pop(var, None)
    logger.info(
        "ai_env_host_mode",
        org_id=str(org.id),
        provider=provider.value,
        has_process_env_key=_API_KEY_ENV_VAR in os.environ,
    )


async def load_claude_env_at_startup(session: AsyncSession) -> None:
    """At boot, read the first org with a stored Claude credential and apply it.

    Covers both ``api_key`` (API key) and ``subscription`` (OAuth token) modes.
    Bodhiorchard's documented deployment model is single-tenant per machine,
    so the first configured org wins. If no org has a credential stored, the
    process env is left alone — Hybrid mode deployments rely on the host's
    existing login and don't need any DB-sourced override.
    """
    org = await OrganizationRepository(session).get_first_with_stored_claude_credential(
        CREDENTIAL_AUTH_MODES
    )
    if org is None:
        logger.info("claude_env_startup_no_stored_key")
        return
    apply_claude_auth_to_env(org)
