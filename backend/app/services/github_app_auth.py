# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""GitHub App authentication — JWT generation and installation token caching.

Generates short-lived installation tokens from a GitHub App's
private key. Tokens are cached in memory with TTL to avoid
redundant API calls.
"""

import time

import jwt
import structlog
from httpx import AsyncClient, HTTPStatusError

from app.core.encryption import decrypt_secret

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.github.com"

# In-memory cache: org_id → (token, expires_at)
_token_cache: dict[str, tuple[str, float]] = {}
_CACHE_MARGIN = 60  # Refresh 60s before actual expiry


def _generate_jwt(app_id: int, private_key_pem: str) -> str:
    """Create a JWT signed with the App's private key (10 min TTL)."""
    now = int(time.time())
    payload = {
        "iat": now - 60,  # Allow 60s clock drift
        "exp": now + (10 * 60),
        "iss": str(app_id),
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


async def get_installation_token(org: "Organization") -> str | None:  # noqa: F821
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

    app_jwt = _generate_jwt(org.github_app_id, pem)

    # Exchange JWT for installation token
    url = f"{_BASE_URL}/app/installations/{org.github_app_installation_id}/access_tokens"
    async with AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {app_jwt}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            resp.raise_for_status()
        except HTTPStatusError:
            logger.error(
                "github_app_token_exchange_failed",
                status=resp.status_code,
                org_id=str(org.id),
            )
            return None

    data = resp.json()
    token = data["token"]
    # GitHub returns expires_at as ISO string — parse to epoch
    expires_str = data.get("expires_at", "")
    try:
        from datetime import datetime

        expires_at = datetime.fromisoformat(
            expires_str.replace("Z", "+00:00"),
        ).timestamp()
    except (ValueError, AttributeError):
        expires_at = time.time() + 3600  # Default 1hr

    _token_cache[cache_key] = (token, expires_at)
    logger.info("github_app_token_generated", org_id=str(org.id))
    return token
