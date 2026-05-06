# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""GitHub App slug back-fill — fetch and persist the lowercase ``slug``
returned by ``GET /app``.

The slug is what ``Organization.github_app_slug`` stores. It is needed
to build the install URL ``https://github.com/apps/{slug}/installations/new``
which the Settings page and bulk-import flow surface.

Two entry points:

- :func:`fetch_and_persist_app_slug` — synchronous-flavoured helper used
  during a request (e.g. ``PATCH /v1/settings/connections``). Uses the
  caller's session.
- :func:`spawn_slug_retrofit` — fire-and-forget background task used
  inside ``get_installation_token`` so token-fetch latency is unaffected.
  Spins up its own ``AsyncSessionLocal()`` because it lives outside the
  request lifecycle.
"""

import asyncio
import uuid
from typing import TYPE_CHECKING

import structlog
from httpx import AsyncClient, HTTPError, HTTPStatusError, RequestError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.repositories.organization import OrganizationRepository
from app.services.github_app_jwt import (
    GITHUB_APP_ENDPOINT,
    HTTP_TIMEOUT_SECONDS,
    app_jwt_headers,
    generate_app_jwt,
)

if TYPE_CHECKING:
    from app.models.organization import Organization

logger = structlog.get_logger(__name__)

# Phase J — typed error codes surfaced to the frontend so the
# credentials form can map them to localised messages without parsing
# free-text. The frontend mirrors these in
# ``frontend/src/types/connectionErrors.ts`` — keep the strings in
# lockstep.
ERROR_CODE_INVALID_CREDENTIALS = "github_app_credentials_invalid"
ERROR_CODE_APP_NOT_FOUND = "github_app_not_found"
ERROR_CODE_UNREACHABLE = "github_unreachable"


class GitHubAppValidationError(Exception):
    """Base class for typed credential-validation failures.

    Carries a stable ``code`` plus a human-readable ``message`` so the
    route handler can translate to the correct HTTP status without
    sniffing exception types twice.
    """

    code: str = ""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class GitHubCredentialsInvalid(GitHubAppValidationError):  # noqa: N818
    """GitHub returned 401 — the JWT signed with the user's private key
    was rejected. Usually means a wrong App ID / private key pair."""

    code = ERROR_CODE_INVALID_CREDENTIALS


class GitHubAppNotFound(GitHubAppValidationError):  # noqa: N818
    """GitHub returned 404 — the App ID does not point at any App we
    can see with the supplied JWT."""

    code = ERROR_CODE_APP_NOT_FOUND


class GitHubUnreachable(GitHubAppValidationError):  # noqa: N818
    """Network-level failure (DNS, TLS, timeout) calling ``GET /app``.
    Distinct from a GitHub-side rejection so the user sees the right
    nudge."""

    code = ERROR_CODE_UNREACHABLE


# Hold strong refs to in-flight slug-retrofit tasks so the GC doesn't
# eat them mid-await. Tasks remove themselves on completion.
_BACKGROUND_RETROFIT_TASKS: set[asyncio.Task[None]] = set()


async def _fetch_app_slug(app_id: int, private_key_pem: str) -> str | None:
    """Call ``GET /app`` with an App-JWT and return the ``slug`` field.

    Returns ``None`` on any HTTP error or missing field. Callers log;
    this helper stays silent so it composes inside background tasks.
    """
    app_jwt = generate_app_jwt(app_id, private_key_pem)
    async with AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        try:
            resp = await client.get(GITHUB_APP_ENDPOINT, headers=app_jwt_headers(app_jwt))
            resp.raise_for_status()
        except HTTPError:
            return None
    data = resp.json()
    slug = data.get("slug")
    return slug if isinstance(slug, str) and slug else None


async def _fetch_app_slug_strict(app_id: int, private_key_pem: str) -> str:
    """Strict counterpart of ``_fetch_app_slug`` for synchronous-validation
    callers — raises typed exceptions instead of returning ``None`` so the
    request handler can surface a precise HTTP error.

    Raises:
        GitHubCredentialsInvalid: GitHub responded 401.
        GitHubAppNotFound: GitHub responded 404.
        GitHubUnreachable: Network error or unexpected payload.
    """
    app_jwt = generate_app_jwt(app_id, private_key_pem)
    async with AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        try:
            resp = await client.get(GITHUB_APP_ENDPOINT, headers=app_jwt_headers(app_jwt))
        except RequestError as exc:
            raise GitHubUnreachable(
                "Could not reach GitHub to validate the App credentials.",
            ) from exc
        if resp.status_code == 401:
            raise GitHubCredentialsInvalid(
                "GitHub rejected the credentials. Check the App ID and private key.",
            )
        if resp.status_code == 404:
            raise GitHubAppNotFound(
                "GitHub could not find a GitHub App with this App ID.",
            )
        try:
            resp.raise_for_status()
        except HTTPStatusError as exc:
            raise GitHubUnreachable(
                f"GitHub returned an unexpected status ({resp.status_code}).",
            ) from exc
    data = resp.json()
    slug = data.get("slug")
    if not isinstance(slug, str) or not slug:
        raise GitHubUnreachable("GitHub returned an unexpected payload (missing slug).")
    return slug


async def fetch_and_persist_app_slug(org: "Organization", db: AsyncSession) -> str | None:
    """Fetch the App slug via ``GET /app`` and persist it on ``org``.

    Single-shot, gated by the caller (already null-checked
    ``org.github_app_slug``). Uses the request's session.

    Returns the slug if persisted, else ``None``. Logs a warning on
    GitHub failure but does not raise — failure to fetch the slug must
    not break the surrounding settings PATCH (this is the lenient
    variant; ``validate_and_persist_app_slug`` is the strict one used
    when the user has just supplied new credentials).
    """
    if not org.github_app_id or not org.github_app_private_key:
        return None
    pem = decrypt_secret(org.github_app_private_key)
    if not pem:
        return None
    slug = await _fetch_app_slug(org.github_app_id, pem)
    if slug is None:
        logger.warning("github_app_slug_fetch_failed", org_id=str(org.id))
        return None
    await OrganizationRepository(db).update_app_slug(org.id, slug)
    org.github_app_slug = slug
    await db.flush()
    await db.refresh(org)
    logger.info("github_app_slug_persisted", org_id=str(org.id), slug=slug)
    return slug


async def validate_and_persist_app_slug(org: "Organization", db: AsyncSession) -> str:
    """Strict validation path — used when the user has just submitted
    fresh credentials in ``PATCH /v1/settings/connections``.

    Always raises on failure (typed ``GitHubAppValidationError``) so
    the route handler can return a precise 400/502. On success persists
    the slug on the org row and returns it.
    """
    if not org.github_app_id or not org.github_app_private_key:
        raise GitHubCredentialsInvalid(
            "App ID or private key missing — supply both to validate.",
        )
    pem = decrypt_secret(org.github_app_private_key)
    if not pem:
        raise GitHubCredentialsInvalid(
            "Stored private key could not be decoded — re-paste the .pem contents.",
        )
    slug = await _fetch_app_slug_strict(org.github_app_id, pem)
    await OrganizationRepository(db).update_app_slug(org.id, slug)
    org.github_app_slug = slug
    await db.flush()
    await db.refresh(org)
    logger.info("github_app_slug_validated", org_id=str(org.id), slug=slug)
    return slug


async def _retrofit_app_slug_task(
    org_id: uuid.UUID, app_id: int, encrypted_private_key: str
) -> None:
    """Background task: fetch + persist the App slug in a fresh session.

    Lives outside the request lifecycle, so it spins up its own
    ``AsyncSessionLocal()`` rather than borrowing the request's session.
    Errors are logged and swallowed.
    """
    pem = decrypt_secret(encrypted_private_key)
    if not pem:
        return
    slug = await _fetch_app_slug(app_id, pem)
    if slug is None:
        logger.warning("github_app_slug_retrofit_fetch_failed", org_id=str(org_id))
        return
    async with AsyncSessionLocal() as session:
        try:
            await OrganizationRepository(session).update_app_slug(org_id, slug)
            await session.commit()
            logger.info("github_app_slug_retrofit_persisted", org_id=str(org_id), slug=slug)
        except Exception:
            await session.rollback()
            logger.exception("github_app_slug_retrofit_persist_failed", org_id=str(org_id))


def spawn_slug_retrofit(org: "Organization") -> None:
    """Schedule a background slug-retrofit task; idempotent on repeated calls.

    Stashes the task in a module-level set so the GC keeps a strong
    reference until completion; the task removes itself on done.
    """
    if not org.github_app_id or not org.github_app_private_key:
        return
    task = asyncio.create_task(
        _retrofit_app_slug_task(org.id, org.github_app_id, org.github_app_private_key)
    )
    _BACKGROUND_RETROFIT_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_RETROFIT_TASKS.discard)
