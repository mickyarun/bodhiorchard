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
from app.models.organization import Organization
from app.repositories.organization import OrganizationRepository

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


def apply_claude_auth_to_env(org: Organization) -> None:
    """Push an organization's Claude auth choice into ``os.environ``.

    - ``api_key`` mode with a stored key → set ``ANTHROPIC_API_KEY``.
    - ``subscription`` mode with a stored token → set ``CLAUDE_CODE_OAUTH_TOKEN``.
    - ``host`` mode → leave whatever the process started with (compose-level
      env, or the host's ``claude login`` session in Hybrid mode) untouched.

    api_key and subscription are mutually exclusive: applying one clears the
    other's env var so a leftover/compose ``ANTHROPIC_API_KEY`` can't shadow a
    subscription token (the CLI prefers the API key when both are present).

    Callers should invoke this on app startup and again whenever the org's
    setting is changed via the Settings UI.
    """
    if org.claude_auth_mode in CREDENTIAL_AUTH_MODES and org.claude_api_key_encrypted:
        decrypted = decrypt_secret(org.claude_api_key_encrypted)
        if decrypted:
            # Don't log any portion of the secret — even a short prefix is a
            # partial credential that shouldn't reach centralized log aggregators.
            if org.claude_auth_mode == AUTH_MODE_SUBSCRIPTION:
                os.environ[_OAUTH_ENV_VAR] = decrypted
                os.environ.pop(_API_KEY_ENV_VAR, None)
                logger.info("claude_env_subscription_applied", org_id=str(org.id))
            else:
                os.environ[_API_KEY_ENV_VAR] = decrypted
                os.environ.pop(_OAUTH_ENV_VAR, None)
                logger.info("claude_env_api_key_applied", org_id=str(org.id))
            return

    # host mode (or a credentialed mode with an empty/corrupt secret): don't
    # override the process env — the compose/host credential stays authoritative.
    logger.info(
        "claude_env_host_mode",
        org_id=str(org.id),
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
