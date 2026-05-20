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

"""GitHub App authentication — JWT generation and installation token caching.

Generates short-lived installation tokens from a GitHub App's
private key. Tokens are cached in memory with TTL to avoid
redundant API calls.

Also kicks off a fire-and-forget slug retrofit on first successful
token fetch when ``Organization.github_app_slug`` is ``None`` — see
:mod:`app.services.github_app_slug`.
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING

import structlog
from httpx import AsyncClient, HTTPStatusError

from app.core.encryption import decrypt_secret
from app.services.github_app_jwt import (
    GITHUB_BASE_URL,
    HTTP_TIMEOUT_SECONDS,
    app_jwt_headers,
    generate_app_jwt,
)
from app.services.github_app_slug import (
    fetch_and_persist_app_slug,
    spawn_slug_retrofit,
)

if TYPE_CHECKING:
    from app.models.organization import Organization

logger = structlog.get_logger(__name__)

# In-memory cache: org_id → (token, expires_at)
_token_cache: dict[str, tuple[str, float]] = {}
_CACHE_MARGIN = 60  # Refresh 60s before actual expiry
_DEFAULT_TOKEN_TTL_SECONDS = 3600

# Re-export so the call sites that already import from this module
# don't have to learn a new path. ``fetch_and_persist_app_slug`` is the
# request-time helper used by ``settings.py``.
__all__ = [
    "discover_installation_id_for_repo",
    "fetch_and_persist_app_slug",
    "get_installation_token",
    "invalidate_installation_token",
]


def invalidate_installation_token(org_id: str) -> None:
    """Drop any cached installation token for ``org_id``.

    Callers use this when a freshly-cached token still fails auth — most
    commonly an agent's git/gh subprocess returning
    ``Invalid username or token``. Removing the entry forces the next
    :func:`get_installation_token` call to mint a brand-new token rather
    than returning the rejected one again.
    """
    _token_cache.pop(org_id, None)


async def discover_installation_id_for_repo(
    org: "Organization",
    github_repo_full_name: str,
) -> int | None:
    """Resolve the App's installation id for a specific repo.

    Used when the org has the App's credentials saved but
    ``github_app_installation_id`` hasn't been auto-detected from a
    webhook yet (the existing flow only stamps it on first webhook
    delivery — which never happens for orgs whose repos haven't fired
    a tracked event since install).

    Calls ``GET /repos/{owner}/{repo}/installation`` with the App JWT
    (not an installation token) and returns the numeric ``id`` field.
    """
    if not org.github_app_id or not org.github_app_private_key:
        return None
    if "/" not in github_repo_full_name:
        return None
    pem = decrypt_secret(org.github_app_private_key)
    if not pem:
        return None
    app_jwt = generate_app_jwt(org.github_app_id, pem)
    url = f"{GITHUB_BASE_URL}/repos/{github_repo_full_name}/installation"
    async with AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        try:
            resp = await client.get(url, headers=app_jwt_headers(app_jwt))
            resp.raise_for_status()
        except HTTPStatusError:
            logger.warning(
                "github_app_installation_lookup_failed",
                status=resp.status_code,
                org_id=str(org.id),
                repo=github_repo_full_name,
            )
            return None
    data = resp.json()
    install_id = data.get("id")
    return int(install_id) if isinstance(install_id, int) else None


async def get_installation_token(org: "Organization") -> str | None:
    """Get a cached installation token, or generate a new one.

    Args:
        org: Organization with github_app_id, github_app_private_key,
             and github_app_installation_id set.

    Returns:
        Installation access token string, or None if credentials are missing.
    """
    if not org.github_app_id or not org.github_app_private_key:
        return None
    if not org.github_app_installation_id:
        logger.debug("github_app_no_installation_id", org_id=str(org.id))
        return None

    cache_key = str(org.id)
    cached = _token_cache.get(cache_key)
    if cached:
        token, expires_at = cached
        if time.time() < expires_at - _CACHE_MARGIN:
            return token

    # Decrypt private key and generate JWT
    pem = decrypt_secret(org.github_app_private_key)
    if not pem:
        return None

    app_jwt = generate_app_jwt(org.github_app_id, pem)

    # Exchange JWT for installation token
    url = f"{GITHUB_BASE_URL}/app/installations/{org.github_app_installation_id}/access_tokens"
    async with AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        try:
            resp = await client.post(url, headers=app_jwt_headers(app_jwt))
            resp.raise_for_status()
        except HTTPStatusError:
            logger.error(
                "github_app_token_exchange_failed",
                status=resp.status_code,
                org_id=str(org.id),
            )
            return None

    data = resp.json()
    raw_token = data["token"]
    if not isinstance(raw_token, str):
        logger.error("github_app_token_unexpected_payload", org_id=str(org.id))
        return None
    token = raw_token
    # GitHub returns expires_at as ISO string — parse to epoch
    expires_str = data.get("expires_at", "")
    try:
        expires_at = datetime.fromisoformat(
            expires_str.replace("Z", "+00:00"),
        ).timestamp()
    except (ValueError, AttributeError):
        expires_at = time.time() + _DEFAULT_TOKEN_TTL_SECONDS

    _token_cache[cache_key] = (token, expires_at)
    logger.info("github_app_token_generated", org_id=str(org.id))

    # First-time slug back-fill. Single null-check guards us from
    # repeating the call once the slug lands. The actual work runs in
    # a background task so token fetch latency is unaffected.
    if org.github_app_slug is None:
        spawn_slug_retrofit(org)

    return token
