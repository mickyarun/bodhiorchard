# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Clone GitHub repositories into the Docker ``/data/repos`` volume.

This is the Full Docker complement to local-path repos: when the backend
runs inside a container it can't reach a Mac/Windows host path, so we clone
the target repo into a persistent volume and hand the container-local path
to the rest of the scan pipeline.

Three auth shapes are supported:

* **Public HTTPS** — no credential; any ``https://github.com/<owner>/<name>``.
* **HTTPS with PAT** — user supplies a GitHub personal-access token; we
  interpolate it into the URL only for the clone invocation and never persist
  it to disk or log it.
* **SSH deploy key** — a ``git@github.com:...`` URL; we use the keypair from
  ``ssh_keys.py`` via ``GIT_SSH_COMMAND``. The user has already pasted the
  public key into the repo's Deploy keys on GitHub.

All git invocations use the argument-list subprocess API (no shell) so
there's no path for shell injection via repo URLs or tokens.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse

import structlog

from app.services.ssh_keys import ssh_env

logger = structlog.get_logger(__name__)

CLONE_ROOT = Path("/data/repos")

# Conservative GitHub repo-slug shape: letters, digits, hyphens, underscores,
# dots. Everything we match here becomes a directory name under CLONE_ROOT,
# so the pattern also rejects path traversal.
_SAFE_SEG = re.compile(r"^[A-Za-z0-9._-]+$")

# Matches an HTTPS-with-credentials URL in any form git might echo back,
# including truncated output. Used to scrub tokens from error messages
# even when our literal-replace on the original PAT misses a transformed
# variant (URL-encoded, re-wrapped, etc.).
_URL_CRED_RE = re.compile(r"https://[^@\s/]+:[^@\s]+@")


@dataclass
class CloneResult:
    """Outcome of a clone (or refresh) against ``CLONE_ROOT``."""

    success: bool
    path: str | None = None
    default_branch: str | None = None
    error: str | None = None


def _is_ssh_url(url: str) -> bool:
    """Match ``git@github.com:owner/repo(.git)`` or ``ssh://git@github.com/...``."""
    return url.startswith("git@") or url.startswith("ssh://")


def _parse_github_url(url: str) -> tuple[str, str] | None:
    """Extract ``(owner, repo)`` from a GitHub HTTPS or SSH URL.

    Returns ``None`` if the URL doesn't look like GitHub — we refuse to
    clone arbitrary hosts from this endpoint since known_hosts only trusts
    github.com. Supports trailing ``.git`` and optional trailing slash.
    """
    if _is_ssh_url(url):
        m = re.match(r"^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?/?$", url)
        if m:
            return m.group(1), m.group(2)
        m = re.match(r"^ssh://git@github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
        if m:
            return m.group(1), m.group(2)
        return None

    parsed = urlparse(url)
    if parsed.hostname != "github.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    return owner, repo


def _compose_authenticated_url(url: str, token: str) -> str:
    """Inject a PAT into the HTTPS URL without double-escaping existing user info."""
    parsed = urlparse(url)
    return f"https://x-access-token:{quote(token, safe='')}@{parsed.hostname}{parsed.path}"


async def _run_git(
    args: list[str],
    *,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a git subprocess (no shell) and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


async def _detect_default_branch(clone_path: Path, env: dict[str, str] | None) -> str | None:
    """Ask the remote which branch is HEAD (GitHub's ``default`` branch)."""
    rc, out, _ = await _run_git(
        ["symbolic-ref", "refs/remotes/origin/HEAD"],
        cwd=str(clone_path),
        env=env,
    )
    if rc != 0:
        return None
    return out.strip().removeprefix("refs/remotes/origin/").strip() or None


async def clone_or_update(
    url: str,
    *,
    org_slug: str,
    pat: str | None = None,
) -> CloneResult:
    """Clone ``url`` into ``/data/repos/<org_slug>/<repo>``, or fetch if present.

    Args:
        url: GitHub HTTPS or SSH URL.
        org_slug: Bodhiorchard org slug — used as the first path segment so
            clones from different orgs never collide.
        pat: Optional GitHub personal-access token for HTTPS private repos.

    Returns:
        ``CloneResult`` with the absolute clone path on success.
    """
    if not CLONE_ROOT.exists():
        return CloneResult(
            success=False,
            error=f"Clone root {CLONE_ROOT} is missing (volume not mounted?)",
        )

    parsed = _parse_github_url(url)
    if not parsed:
        return CloneResult(
            success=False,
            error=(
                "Only GitHub URLs are supported right now. Use "
                "https://github.com/<owner>/<repo> or git@github.com:<owner>/<repo>."
            ),
        )
    owner, repo = parsed
    if not _SAFE_SEG.match(owner) or not _SAFE_SEG.match(repo) or not _SAFE_SEG.match(org_slug):
        return CloneResult(success=False, error="Invalid characters in owner, repo, or org slug.")

    dest = CLONE_ROOT / org_slug / repo
    dest.parent.mkdir(parents=True, exist_ok=True)

    env: dict[str, str] | None = None
    effective_url = url
    if _is_ssh_url(url):
        env = ssh_env()
    elif pat:
        effective_url = _compose_authenticated_url(url, pat)

    already_cloned = (dest / ".git").exists()

    if already_cloned:
        logger.info("repo_clone_update_start", dest=str(dest), owner=owner, repo=repo)
        rc, _, stderr = await _run_git(
            ["-C", str(dest), "fetch", "--all", "--prune"],
            env=env,
        )
        if rc != 0:
            # The clone is usable; we just couldn't refresh. Return success
            # with a warning rather than a hard 400 so the caller can still
            # register the existing repo on this org.
            logger.warning("repo_clone_fetch_failed", rc=rc, stderr=stderr[:300])
            default_branch = await _detect_default_branch(dest, env)
            return CloneResult(
                success=True,
                path=str(dest),
                default_branch=default_branch,
                error=f"Refresh skipped: {_sanitize(stderr, pat)}",
            )
    else:
        logger.info(
            "repo_clone_start",
            dest=str(dest),
            owner=owner,
            repo=repo,
            ssh=_is_ssh_url(url),
        )
        rc, _, stderr = await _run_git(
            ["clone", "--no-single-branch", effective_url, str(dest)],
            env=env,
        )
        if rc != 0:
            # Only remove the destination if git created it during this
            # failed clone — avoid nuking a pre-existing directory we
            # didn't own (symlink, leftover from another process, etc.).
            if dest.exists() and (dest / ".git").exists():
                shutil.rmtree(dest, ignore_errors=True)
            logger.warning("repo_clone_failed", rc=rc, stderr=stderr[:300])
            return CloneResult(success=False, error=_sanitize(stderr, pat))

    default_branch = await _detect_default_branch(dest, env)

    logger.info("repo_clone_ok", path=str(dest), default_branch=default_branch)
    return CloneResult(success=True, path=str(dest), default_branch=default_branch)


def _sanitize(msg: str, pat: str | None) -> str:
    """Strip the PAT out of error output so we never return secrets to the UI.

    Handles both the exact PAT string and the ``https://user:token@host``
    pattern git sometimes echoes back — the latter catches URL-encoded or
    truncated variants of the token that a literal replace would miss.
    """
    if pat:
        msg = msg.replace(pat, "****")
    msg = _URL_CRED_RE.sub("https://***:***@", msg)
    return msg.strip()[:400]
