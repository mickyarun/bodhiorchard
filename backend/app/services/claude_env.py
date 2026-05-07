# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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
from app.models.organization import Organization
from app.repositories.organization import OrganizationRepository

logger = structlog.get_logger(__name__)

AUTH_MODE_HOST = "host"
AUTH_MODE_API_KEY = "api_key"
VALID_AUTH_MODES = frozenset({AUTH_MODE_HOST, AUTH_MODE_API_KEY})

_ENV_VAR = "ANTHROPIC_API_KEY"


def apply_claude_auth_to_env(org: Organization) -> None:
    """Push an organization's Claude auth choice into ``os.environ``.

    - ``api_key`` mode with a stored key → set ``ANTHROPIC_API_KEY``.
    - ``host`` mode → leave whatever the process started with (compose-level
      env, or the host's ``claude login`` session in Hybrid mode) untouched.

    Callers should invoke this on app startup and again whenever the org's
    setting is changed via the Settings UI.
    """
    if org.claude_auth_mode == AUTH_MODE_API_KEY and org.claude_api_key_encrypted:
        decrypted = decrypt_secret(org.claude_api_key_encrypted)
        if decrypted:
            os.environ[_ENV_VAR] = decrypted
            # Don't log any portion of the key — even a short prefix is a
            # partial secret that shouldn't end up in centralized log
            # aggregators.
            logger.info("claude_env_api_key_applied", org_id=str(org.id))
            return

    # host mode (or api_key mode with an empty/corrupt key): don't override the
    # process env — the compose/host ANTHROPIC_API_KEY stays authoritative.
    logger.info(
        "claude_env_host_mode",
        org_id=str(org.id),
        has_process_env_key=_ENV_VAR in os.environ,
    )


async def load_claude_env_at_startup(session: AsyncSession) -> None:
    """At boot, read the first org that has an ``api_key`` set and apply it.

    Bodhiorchard's documented deployment model is single-tenant per machine,
    so the first configured org wins. If no org has an API key stored, the
    process env is left alone — Hybrid mode deployments rely on the host's
    existing login and don't need any DB-sourced override.
    """
    org = await OrganizationRepository(session).get_first_with_claude_api_key(AUTH_MODE_API_KEY)
    if org is None:
        logger.info("claude_env_startup_no_stored_key")
        return
    apply_claude_auth_to_env(org)
