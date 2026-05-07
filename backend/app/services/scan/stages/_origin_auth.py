# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Refresh origin's credentials before scan-ingest fetches.

Mirrors the auth-refresh block of
``app.services.repo_cloner.clone_or_update`` (the already-cloned branch)
so the scan-ingest stage uses the same fresh GitHub-App installation
token / SSH command as the bulk-clone flow — instead of relying on the
credentials that were baked into ``.git/config`` at clone time, which
expire for App-auth orgs (token TTL ≈ 1h).

Decision tree:

* No ``origin`` remote → caller skips fetch anyway; we no-op.
* SSH origin URL (``git@github.com:…`` / ``ssh://git@github.com/…``)
  → return ``ssh_env()`` so the subprocess sees ``GIT_SSH_COMMAND``.
* HTTPS origin + the org's GitHub App is in ``READY`` state → mint a
  fresh installation token and rewrite ``origin`` via
  ``git remote set-url`` to embed it. Returns ``None`` because the URL
  itself now carries the credentials.
* HTTPS otherwise (PAT-baked URL, public repo, or no org context)
  → leave ``origin`` alone and return ``None``. The fetch will succeed
  if and only if whatever's already in the URL still authenticates;
  this is unchanged from the pre-fix behaviour.

Never logs the token. Logs only the resolved auth kind so an operator
can tell which path was taken.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.schemas.repo_install import AppInstallState
from app.services.git_operations import run_git
from app.services.github_app_auth import get_installation_token
from app.services.github_install_repos import (
    compose_app_clone_url,
    resolve_app_install_state,
)
from app.services.repo_cloner import is_ssh_url
from app.services.ssh_keys import ssh_env

if TYPE_CHECKING:
    from app.models.organization import Organization

logger = structlog.get_logger(__name__)


async def refresh_origin_auth(
    repo_path: str,
    org: Organization | None,
) -> dict[str, str] | None:
    """Refresh origin's auth in place; return env to pass to ``run_git``.

    See module docstring for the decision tree. Returns the env dict
    when the subprocess needs ``GIT_SSH_COMMAND`` (SSH origin), or
    ``None`` when no env override is required (HTTPS — credentials are
    in the URL or unmanaged).
    """
    origin_url = await _read_origin_url(repo_path)
    if origin_url is None:
        logger.debug("scan_ingest_origin_auth_skipped", reason="no_origin")
        return None

    if is_ssh_url(origin_url):
        logger.info("scan_ingest_origin_auth_refreshed", kind="ssh")
        return ssh_env()

    if org is None:
        logger.debug("scan_ingest_origin_auth_skipped", reason="no_org")
        return None

    state, _ = resolve_app_install_state(org)
    if state is not AppInstallState.READY:
        logger.debug(
            "scan_ingest_origin_auth_skipped",
            reason="app_not_ready",
            state=state.value,
        )
        return None

    token = await get_installation_token(org)
    if not token:
        logger.warning(
            "scan_ingest_origin_auth_token_unavailable",
            org_id=str(org.id),
        )
        return None

    full_name = _extract_github_full_name(origin_url)
    if full_name is None:
        logger.debug(
            "scan_ingest_origin_auth_skipped",
            reason="non_github_https",
        )
        return None

    authed_url = compose_app_clone_url(token, full_name)
    _, stderr, rc = await run_git(
        ["remote", "set-url", "origin", authed_url],
        cwd=repo_path,
    )
    if rc != 0:
        logger.warning(
            "scan_ingest_origin_auth_set_url_failed",
            org_id=str(org.id),
            stderr=stderr[:200],
        )
        return None

    logger.info(
        "scan_ingest_origin_auth_refreshed",
        kind="https_app",
        org_id=str(org.id),
    )
    return None


async def _read_origin_url(repo_path: str) -> str | None:
    """Return the configured ``origin`` URL, or ``None`` when absent."""
    stdout, _, rc = await run_git(
        ["remote", "get-url", "origin"],
        cwd=repo_path,
    )
    if rc != 0:
        return None
    url = stdout.strip()
    return url or None


def _extract_github_full_name(https_url: str) -> str | None:
    """Pull ``owner/repo`` out of an HTTPS GitHub URL.

    Strips any embedded credentials and a trailing ``.git`` so the result
    matches what ``compose_app_clone_url`` expects. Returns ``None`` for
    non-github.com hosts — we won't rewrite arbitrary remotes.

    Intentionally not ``repo_cloner._parse_github_url``: that one applies
    a stricter ``_SAFE_SEG`` filesystem-safety filter aimed at clone
    destination dirs and would reject perfectly valid org slugs we
    already trust at this stage. Here we just need the original
    ``owner/repo`` string back.
    """
    body = https_url
    if "://" in body:
        body = body.split("://", 1)[1]
    if "@" in body:
        body = body.split("@", 1)[1]
    if not body.startswith("github.com/"):
        return None
    path = body[len("github.com/") :].rstrip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    if "/" not in path:
        return None
    owner, _, rest = path.partition("/")
    repo = rest.split("/", 1)[0]
    if not owner or not repo:
        return None
    return f"{owner}/{repo}"
