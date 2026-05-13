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

"""GitHub-App-installation repo + branch listing for the bulk-import flow.

All HTTP calls go through the org's GitHub App installation token (via
:func:`app.services.github_app_auth.get_installation_token`). No new
persisted credentials and no PATs — the token is fetched per request,
sent via ``Authorization: Bearer``, and never logged.

This module deliberately does not touch the DB directly: the only join
it needs (``already_tracked``) goes through
:class:`TrackedRepoRepository.get_full_names_by_org` to keep all SQL
inside the repository layer.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import structlog
from httpx import (
    AsyncClient,
    ConnectError,
    HTTPStatusError,
    ReadError,
    RemoteProtocolError,
    Response,
)

from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.repo_install import AppInstallState, InstallableRepo
from app.services.github_app_auth import get_installation_token
from app.services.github_app_jwt import (
    GITHUB_ACCEPT,
    GITHUB_API_VERSION,
    GITHUB_APP_INSTALL_URL_TEMPLATE,
    GITHUB_BASE_URL,
    HTTP_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.organization import Organization

logger = structlog.get_logger(__name__)

# Module-level constants — no magic strings/numbers anywhere below.
INSTALLATION_REPOS_PATH = "/installation/repositories"
REPO_BRANCHES_PATH_TEMPLATE = "/repos/{full_name}/branches"
GITHUB_PER_PAGE = 100
APP_CLONE_URL_TEMPLATE = "https://x-access-token:{token}@github.com/{full_name}.git"

# Retry policy for transient httpx transport errors (RemoteProtocolError,
# ReadError, ConnectError). GitHub's edge occasionally tears down a
# kept-alive connection mid-response; one or two short retries cover the
# common case without delaying the user when GitHub is genuinely down.
_TRANSIENT_HTTP_ERRORS: tuple[type[Exception], ...] = (
    RemoteProtocolError,
    ReadError,
    ConnectError,
)
_HTTP_RETRY_ATTEMPTS = 3
_HTTP_RETRY_BASE_DELAY_S = 0.25

# Strict ``owner/repo`` pattern; rejects any payload containing extra
# ``/``, ``.``-traversal, URL-encoded bytes, whitespace, or scheme
# markers — every known way to turn ``{full_name}`` into a different
# GitHub API endpoint than the caller intended. Slightly more permissive
# than GitHub's own UI rules (it allows trailing hyphens in either part);
# the goal is path-injection rejection, not exact mirror of GitHub's
# name validator. Non-matching real names just 404 against GitHub.
_FULL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def _validate_repo_full_name(full_name: str) -> str:
    """Return ``full_name`` if it matches the strict GitHub ``owner/repo`` shape.

    Raises :class:`ValueError` otherwise. Used as a defence-in-depth
    check before interpolating a caller-supplied identifier into a
    GitHub API URL — the route layer also enforces membership in the
    installation set, but the service layer can't assume that.
    """
    if not _FULL_NAME_PATTERN.match(full_name):
        raise ValueError(f"invalid GitHub repo identifier: {full_name!r}")
    return full_name


def compose_app_clone_url(token: str, full_name: str) -> str:
    """Return the HTTPS clone URL with the installation token embedded.

    Mirrors the format ``repo_cloner._compose_authenticated_url`` uses
    for PAT auth, but with the App-token convention (``x-access-token``
    as the username). The token must NEVER be logged — every log site
    that touches this URL must run it through ``repo_cloner._sanitize``
    first.

    Validates ``full_name`` before interpolation so a caller can't smuggle
    path-traversal characters into the URL.
    """
    return APP_CLONE_URL_TEMPLATE.format(
        token=token, full_name=_validate_repo_full_name(full_name)
    )


def _install_token_headers(token: str) -> dict[str, str]:
    """Build the headers for an installation-token-authenticated GitHub call."""
    return {
        "Accept": GITHUB_ACCEPT,
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }


async def _get_with_retry(
    client: AsyncClient,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None,
    path: str,
) -> Response:
    """Issue ``GET url`` with bounded retry on transient transport errors.

    Retries ``_HTTP_RETRY_ATTEMPTS`` times with linear backoff on
    ``RemoteProtocolError`` / ``ReadError`` / ``ConnectError`` — typical
    of a torn-down keep-alive connection or a brief GitHub edge flap.
    Anything else (including ``HTTPStatusError`` from a real 4xx/5xx)
    propagates on the first try; those won't fix themselves.
    """
    last_err: Exception | None = None
    for attempt in range(_HTTP_RETRY_ATTEMPTS):
        try:
            return await client.get(url, headers=headers, params=params)
        except _TRANSIENT_HTTP_ERRORS as err:
            last_err = err
            logger.warning(
                "github_install_repos_transient_http_error",
                path=path,
                attempt=attempt + 1,
                max_attempts=_HTTP_RETRY_ATTEMPTS,
                error_type=type(err).__name__,
            )
            if attempt + 1 < _HTTP_RETRY_ATTEMPTS:
                await asyncio.sleep(_HTTP_RETRY_BASE_DELAY_S * (attempt + 1))
    assert last_err is not None  # loop exits only via return or exception
    raise last_err


async def _paginated_get(
    client: AsyncClient,
    token: str,
    path: str,
    params: dict[str, Any] | None = None,
    items_key: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield items across all pages of a GitHub list endpoint.

    Follows RFC 5988 ``Link: rel="next"`` pagination headers. Some
    GitHub list endpoints return a top-level array (``/repos/{x}/{y}/branches``)
    while others wrap the payload in ``{total_count, repositories: [...]}``
    (``/installation/repositories``); the ``items_key`` argument selects
    between the two — pass ``None`` for the array shape.
    """
    page_params: dict[str, Any] = {"per_page": GITHUB_PER_PAGE}
    if params:
        page_params.update(params)

    url: str | None = f"{GITHUB_BASE_URL}{path}"
    headers = _install_token_headers(token)
    next_params: dict[str, Any] | None = page_params

    while url is not None:
        resp = await _get_with_retry(client, url, headers, next_params, path)
        try:
            resp.raise_for_status()
        except HTTPStatusError:
            logger.error(
                "github_install_repos_http_error",
                status=resp.status_code,
                path=path,
            )
            raise
        data = resp.json()
        items = data[items_key] if items_key is not None else data
        if not isinstance(items, list):
            logger.error(
                "github_install_repos_unexpected_payload",
                path=path,
                shape=type(items).__name__,
            )
            return
        for item in items:
            if isinstance(item, dict):
                yield item

        # ``Link`` is only set when there's a next page. Subsequent
        # requests use the absolute URL from the header verbatim — no
        # extra params, GitHub embeds them. The next URL is enforced to
        # share the GitHub origin to prevent a malicious upstream from
        # pivoting our bearer-token request at an internal host
        # (partial-SSRF via Link header).
        next_url = _next_link(resp.headers.get("link"))
        if next_url is not None and not _is_same_origin(next_url, GITHUB_BASE_URL):
            logger.warning(
                "github_install_repos_cross_origin_pagination_dropped",
                path=path,
            )
            next_url = None
        url = next_url
        next_params = None


def _next_link(link_header: str | None) -> str | None:
    """Parse an RFC 5988 ``Link`` header and return the ``rel="next"`` URL.

    Returns ``None`` when there is no next page or the header is absent
    / malformed. The returned URL is whatever the server sent — callers
    MUST verify it points at the expected origin before issuing a
    request (see :func:`_is_same_origin`); the ``Link`` header is part
    of the HTTP response and therefore not trusted on its own.
    """
    if not link_header:
        return None
    for part in link_header.split(","):
        section = part.strip()
        if not section.startswith("<"):
            continue
        try:
            url_part, *rel_parts = section.split(";")
        except ValueError:
            continue
        if any('rel="next"' in rp for rp in rel_parts):
            return url_part.strip().lstrip("<").rstrip(">")
    return None


def _is_same_origin(url: str, base: str) -> bool:
    """Return True when ``url`` matches ``base`` on scheme + host (+ port).

    Defends against partial-SSRF via a malicious ``Link`` header: GitHub
    paginated endpoints embed absolute URLs in their ``Link: …; rel="next"``
    header and we follow them verbatim. A compromised or MITM'd upstream
    could point us at an internal host, and our bearer token would ride
    along. Limiting follow-ups to the configured GitHub origin keeps the
    token in its intended audience without affecting legitimate GitHub
    traffic (real GitHub never paginates across hosts).

    Only ``http``/``https`` URLs are considered same-origin; anything
    else (``file://``, ``gopher://``, missing scheme) returns ``False``.
    """
    parsed = urlsplit(url)
    base_parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"}:
        return False
    return parsed.scheme == base_parsed.scheme and parsed.netloc == base_parsed.netloc


def _build_install_url(org: Organization) -> str | None:
    """Compose the GitHub install URL when the slug is known."""
    if not org.github_app_slug:
        return None
    return GITHUB_APP_INSTALL_URL_TEMPLATE.format(slug=org.github_app_slug)


def resolve_app_install_state(org: Organization) -> tuple[AppInstallState, str | None]:
    """Return the picker's view of the org's GitHub-App lifecycle.

    ``NO_CREDENTIALS``  — app_id or private key missing; install URL
    cannot be built (slug requires an authenticated ``GET /app``).
    ``NO_INSTALL``      — credentials present, ``installation_id`` not
    yet set (the install webhook hasn't fired).
    ``READY``           — both credentials and installation_id present;
    ``list_installation_repos`` will succeed.
    """
    if not org.github_app_id or not org.github_app_private_key:
        return AppInstallState.NO_CREDENTIALS, None
    install_url = _build_install_url(org)
    if not org.github_app_installation_id:
        return AppInstallState.NO_INSTALL, install_url
    return AppInstallState.READY, install_url


def _to_installable_repo(item: dict[str, Any], tracked_full_names: set[str]) -> InstallableRepo:
    """Map a raw GitHub repo payload to our DTO + ``already_tracked`` flag."""
    owner = item.get("owner") or {}
    full_name = str(item.get("full_name", ""))
    return InstallableRepo(
        full_name=full_name,
        owner_login=str(owner.get("login", "")),
        owner_avatar_url=str(owner.get("avatar_url", "")),
        default_branch=str(item.get("default_branch", "")),
        private=bool(item.get("private", False)),
        gh_repo_id=int(item.get("id", 0)),
        already_tracked=full_name in tracked_full_names,
        pushed_at=_parse_pushed_at(item.get("pushed_at")),
    )


def _parse_pushed_at(raw: Any) -> datetime | None:
    """Parse GitHub's ISO 8601 ``pushed_at`` (``...Z``) into a ``datetime``.

    Returns ``None`` when the field is missing, empty, non-string, or
    unparseable — the picker treats those as "never pushed" and sorts
    them last.
    """
    if not isinstance(raw, str) or not raw:
        return None
    # ``fromisoformat`` accepts ``+00:00`` but not the trailing ``Z``
    # GitHub uses; normalise so the parse succeeds.
    candidate = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


async def list_installation_repos(
    org: Organization,
    db: AsyncSession,
) -> list[InstallableRepo]:
    """Return every repo visible to the org's App installation.

    Joins the GitHub response against
    :meth:`TrackedRepoRepository.get_full_names_by_org` to set
    ``already_tracked`` for repos that the org has already onboarded.
    Returns an empty list if no installation token can be obtained
    (e.g. the App is not yet installed).
    """
    token = await get_installation_token(org)
    if not token:
        return []

    repo_repo = TrackedRepoRepository(db, org_id=org.id)
    tracked_full_names = await repo_repo.get_full_names_by_org()

    repos: list[InstallableRepo] = []
    async with AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        async for item in _paginated_get(
            client,
            token,
            INSTALLATION_REPOS_PATH,
            items_key="repositories",
        ):
            repos.append(_to_installable_repo(item, tracked_full_names))
    return repos


async def list_remote_branches_via_api(
    org: Organization,
    full_name: str,
) -> list[str]:
    """Return every branch name on a GitHub repo via the installation token.

    Used by the picker's branch dropdowns once the user selects a repo.
    Returns an empty list when no installation token is available.
    """
    token = await get_installation_token(org)
    if not token:
        return []

    path = REPO_BRANCHES_PATH_TEMPLATE.format(full_name=_validate_repo_full_name(full_name))
    branches: list[str] = []
    async with AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        async for item in _paginated_get(client, token, path):
            name = item.get("name")
            if isinstance(name, str):
                branches.append(name)
    return branches
