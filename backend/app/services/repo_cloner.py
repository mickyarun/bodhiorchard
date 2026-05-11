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

"""Clone GitHub repositories into ``settings.storage.repos_dir``.

This is the Full Docker complement to local-path repos: when the backend
runs inside a container it can't reach a Mac/Windows host path, so we clone
the target repo into ``settings.storage.repos_dir`` (a persistent Docker
volume at ``/data/repos`` in Full Docker mode, or ``<backend>/.data/repos``
on Hybrid host installs) and hand that container-local path to the rest
of the scan pipeline.

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

from app.config import settings
from app.services.ssh_keys import ssh_env

logger = structlog.get_logger(__name__)


def _clone_root() -> Path:
    """Resolve the clone-root from settings on each call.

    Reading at call time (not module import) lets tests or admins
    override ``BODHIORCHARD_DATA_DIR`` without reloading this module.
    """
    return settings.storage.repos_dir


# Conservative GitHub repo-slug shape: letters, digits, hyphens, underscores,
# dots. Everything we match here becomes a directory name under the clone
# root, so the pattern also rejects path traversal.
_SAFE_SEG = re.compile(r"^[A-Za-z0-9._-]+$")

# Matches an HTTPS-with-credentials URL in any form git might echo back,
# including truncated output. Used to scrub tokens from error messages
# even when our literal-replace on the original PAT misses a transformed
# variant (URL-encoded, re-wrapped, etc.).
_URL_CRED_RE = re.compile(r"https://[^@\s/]+:[^@\s]+@")


@dataclass
class CloneResult:
    """Outcome of a clone (or refresh) against the configured clone root."""

    success: bool
    path: str | None = None
    default_branch: str | None = None
    error: str | None = None


def is_ssh_url(url: str) -> bool:
    """Match ``git@github.com:owner/repo(.git)`` or ``ssh://git@github.com/...``."""
    return url.startswith("git@") or url.startswith("ssh://")


def _parse_github_url(url: str) -> tuple[str, str] | None:
    """Extract ``(owner, repo)`` from a GitHub HTTPS or SSH URL.

    Returns ``None`` if the URL doesn't look like GitHub — we refuse to
    clone arbitrary hosts from this endpoint since known_hosts only trusts
    github.com. Supports trailing ``.git`` and optional trailing slash.
    """
    if is_ssh_url(url):
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
    branch: str | None = None,
) -> CloneResult:
    """Clone ``url`` into ``<repos_dir>/<org_slug>/<repo>``, or fetch if present.

    Args:
        url: GitHub HTTPS or SSH URL.
        org_slug: Bodhiorchard org slug — used as the first path segment so
            clones from different orgs never collide.
        pat: Optional GitHub personal-access token for HTTPS private repos.
        branch: Branch the wizard onboarded the repo on. When set, ``git
            clone -b`` lands HEAD here directly (and on the update path
            we ``checkout`` + ``reset --hard`` to it) so every downstream
            stage sees the user-selected ref instead of GitHub's
            ``origin/HEAD``, which can be a feature branch.

    Returns:
        ``CloneResult`` with the absolute clone path on success.
    """
    clone_root = _clone_root()
    # Auto-create the clone root if it's missing. In Docker the volume
    # mount creates ``/data`` for us; on the host Hybrid install we own
    # the directory and creating it on first use is the right behaviour.
    clone_root.mkdir(parents=True, exist_ok=True)

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

    dest = clone_root / org_slug / repo
    dest.parent.mkdir(parents=True, exist_ok=True)

    env: dict[str, str] | None = None
    effective_url = url
    if is_ssh_url(url):
        env = ssh_env()
    elif pat:
        effective_url = _compose_authenticated_url(url, pat)

    already_cloned = (dest / ".git").exists()

    if already_cloned:
        logger.info("repo_clone_update_start", dest=str(dest), owner=owner, repo=repo)
        # Rewrite ``origin`` with the current credentials before fetching so
        # an expired GitHub-App installation token (or a rotated PAT) baked
        # into a prior clone doesn't dictate today's auth outcome.
        await _run_git(["-C", str(dest), "remote", "set-url", "origin", effective_url], env=env)
        rc, _, stderr = await _run_git(
            ["-C", str(dest), "fetch", "--all", "--prune"],
            env=env,
        )
        if rc != 0:
            # Hard-fail rather than returning the stale tree as success.
            # A silent fetch failure here cascades through the scan
            # pipeline (Stage 0 ingest, route extraction, feature synth)
            # against checkouts whose head_sha may be hours or days
            # behind, producing empty graphs that the audit greenlit.
            logger.warning("repo_clone_fetch_failed", rc=rc, stderr=stderr[:300])
            return CloneResult(success=False, error=_sanitize(stderr, pat))
        if branch:
            # Force HEAD onto the user-selected branch even if a previous
            # clone left it on the remote default. ``-B`` upserts the
            # local branch ref against ``origin/<branch>`` so a re-onboard
            # always converges, regardless of prior state.
            rc, _, stderr = await _run_git(
                ["-C", str(dest), "checkout", "-B", branch, f"origin/{branch}"],
                env=env,
            )
            if rc != 0:
                logger.warning("repo_clone_checkout_failed", branch=branch, stderr=stderr[:300])
                return CloneResult(success=False, error=_sanitize(stderr, pat))
    else:
        logger.info(
            "repo_clone_start",
            dest=str(dest),
            owner=owner,
            repo=repo,
            ssh=is_ssh_url(url),
            branch=branch,
        )
        clone_args = ["clone", "--no-single-branch"]
        if branch:
            # ``-b`` works with ``--no-single-branch``: all refs still
            # fetched, but HEAD lands on the user-selected branch.
            clone_args += ["-b", branch]
        clone_args += [effective_url, str(dest)]
        rc, _, stderr = await _run_git(clone_args, env=env)
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


def purge_org_clones(org_slug: str) -> int:
    """Remove every cached clone under ``<repos_dir>/<org_slug>/``.

    Used only by the init-org flow — a fresh init means the DB has no
    rows referencing any prior clones, so a leftover ``repoclone/<slug>/``
    tree from a previous deployment is by definition orphaned and safe
    to wipe. Do **not** call this from the bulk-onboard path: that runs
    on a populated DB where sibling repos may belong to other in-flight
    scans, and a whole-org purge would yank their working trees out.
    Use :func:`purge_repo_clones` (per-payload) there.

    Returns the number of repo directories removed.
    """
    if not _SAFE_SEG.match(org_slug):
        raise ValueError(f"Invalid org slug: {org_slug!r}")
    org_dir = _clone_root() / org_slug
    if not org_dir.exists():
        return 0
    removed = sum(1 for entry in org_dir.iterdir() if entry.is_dir())
    shutil.rmtree(org_dir, ignore_errors=True)
    logger.info("repo_clones_purged_init", org_slug=org_slug, removed=removed)
    return removed


def purge_repo_clones(org_slug: str, repo_names: list[str]) -> int:
    """Remove cached clones for the named repos under ``<repos_dir>/<org_slug>/``.

    Scoped to the *specific* repos being re-onboarded so sibling clones
    that other in-flight scans may still be reading from aren't wiped —
    a whole-org purge previously broke concurrent scans by yanking the
    working tree out from under them mid-extraction.

    The original wipe defended against stale ``origin`` URLs in the
    cloner's ``already_cloned`` branch. That defense moved into
    :func:`clone_or_update` itself (it now rewrites ``origin`` with
    fresh credentials before fetching and hard-fails on fetch errors),
    so this helper only needs to clean the specific repos a fresh
    onboard explicitly asked for.

    Returns the number of repo directories actually removed.
    """
    if not _SAFE_SEG.match(org_slug):
        raise ValueError(f"Invalid org slug: {org_slug!r}")
    org_dir = _clone_root() / org_slug
    if not org_dir.exists():
        return 0

    removed = 0
    for name in repo_names:
        if not _SAFE_SEG.match(name):
            raise ValueError(f"Invalid repo name: {name!r}")
        target = org_dir / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            removed += 1
    logger.info(
        "repo_clones_purged",
        org_slug=org_slug,
        requested=len(repo_names),
        removed=removed,
    )
    return removed


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
