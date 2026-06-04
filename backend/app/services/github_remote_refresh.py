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

"""Refresh ``origin`` in a clone with a freshly-minted installation token.

The clone-path's ``.git/config`` carries whatever ``origin`` URL was
written at clone time. GitHub-App installation tokens expire after 1
hour (no refresh mechanism — every "refresh" is a new mint), so any
``git``/``gh`` operation the agent runs more than an hour after the
original clone can fail with ``Invalid username or token``. This helper
runs the same ``git remote set-url origin`` flip that
``repo_cloner.clone_or_update_repo`` does on the update path, but lifted
to a standalone call so it can be invoked right before each agent
spawn — guaranteeing the agent's git/gh commands see a fresh token.

Multi-repo BUDs need the plural :func:`refresh_origin_tokens`: a code-review
or testing prompt instructs the subprocess to ``git fetch`` against every
confirmed repo, so refreshing only the first one leaves the rest on stale
tokens. Per-path failures are isolated — one bad path does not stop the loop.

Best-effort by design: failures are logged and swallowed so they never
block the agent run. If the refresh fails (no App creds, repo not
tracked, git config write error), the agent run still starts — it may
then fail with the auth-rejection path, which the code-review parser
classifier now surfaces as ``git_auth_failed`` with an actionable banner.
"""

import uuid
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.organization import Organization
from app.repositories.tracked_repository import TrackedRepoRepository
from app.services.git_operations import run_git
from app.services.github_app_auth import get_installation_token

logger = structlog.get_logger(__name__)


async def refresh_origin_token(
    *,
    working_dir: str,
    org_id: uuid.UUID,
    db: AsyncSession,
) -> bool:
    """Re-stamp ``origin`` in ``working_dir``'s clone with a fresh token.

    Returns ``True`` when the URL was updated, ``False`` on any
    best-effort failure (no App creds, not a tracked GitHub repo, git
    config write error). Never raises — token freshness is a
    nice-to-have, not a precondition for the spawn.
    """
    repo_repo = TrackedRepoRepository(db, org_id=org_id)
    repo = await repo_repo.get_by_path(working_dir)
    if repo is None or not repo.github_repo_full_name:
        # Working dir isn't a tracked GitHub repo (could be the no-repo
        # scratch dir, a local-only repo, or a tracked repo without a
        # GitHub link). Nothing to refresh.
        return False

    org = await db.get(Organization, org_id)
    if org is None:
        logger.warning("origin_refresh_skip_no_org", org_id=str(org_id))
        return False

    token = await get_installation_token(org)
    if not token:
        # No App creds — caller may be on PAT-only or SSH auth. Skip;
        # those paths don't need an installation-token refresh. Logged
        # at debug so a downstream ``git_auth_failed`` banner can be
        # cross-referenced against "did we even attempt a refresh?".
        logger.debug(
            "origin_refresh_skip_no_app_creds",
            org_id=str(org_id),
            repo=repo.github_repo_full_name,
        )
        return False

    # Surface the common dev-machine failure (stale TrackedRepository row
    # pointing at a path that was moved or deleted) BEFORE we try to spawn
    # the subprocess — otherwise the only signal is a cryptic uvloop
    # FileNotFoundError stack that's indistinguishable from "git binary
    # missing".
    if not Path(working_dir).is_dir():
        logger.error(
            "origin_refresh_skip_missing_working_dir",
            org_id=str(org_id),
            repo=repo.github_repo_full_name,
            repo_path=working_dir,
            hint=(
                "TrackedRepository.local_path points at a directory that"
                " does not exist on disk. Re-clone the repo or update the"
                " tracked path in the DB."
            ),
        )
        return False

    # ``x-access-token`` is the documented username for installation-token
    # auth. Kept inline rather than importing the App-clone-URL template
    # to avoid a heavier dependency chain.
    new_url = f"https://x-access-token:{token}@github.com/{repo.github_repo_full_name}.git"

    # Catch OSError as a backstop for the only other subprocess failure
    # mode that bypasses git's own exit codes: ``git`` missing from PATH.
    # The working-dir-missing case is handled above with a clearer log.
    try:
        _, stderr, rc = await run_git(
            ["remote", "set-url", "origin", new_url],
            cwd=working_dir,
        )
    except OSError as exc:
        logger.warning(
            "origin_refresh_subprocess_failed",
            org_id=str(org_id),
            repo_path=working_dir,
            error=str(exc),
        )
        return False
    if rc != 0:
        scrubbed = stderr.replace(token, "<redacted>")
        logger.warning(
            "origin_refresh_failed",
            org_id=str(org_id),
            repo_path=working_dir,
            stderr=scrubbed[:300],
        )
        return False

    logger.info(
        "origin_refresh_ok",
        org_id=str(org_id),
        repo=repo.github_repo_full_name,
    )
    return True


async def refresh_origin_tokens(
    *,
    working_dirs: list[str],
    org_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, bool]:
    """Refresh ``origin`` for every clone in ``working_dirs``.

    Loops :func:`refresh_origin_token` once per unique path. Isolation
    is total: a per-path failure — git rc, OSError, or even a DB error
    from the tracked-repo lookup — is logged and recorded as ``False``
    so the loop still reaches the next path. The retry path needs this:
    one un-tracked or DB-blipped repo cannot block the refresh of the
    other N-1 repos the second spawn is about to fetch.

    Returns a ``{path: succeeded}`` map so callers can log how many of
    the N repos actually saw a fresh token.
    """
    results: dict[str, bool] = {}
    for path in dict.fromkeys(working_dirs):
        try:
            results[path] = await refresh_origin_token(
                working_dir=path,
                org_id=org_id,
                db=db,
            )
        except Exception as exc:
            # The singular helper already swallows OSError + git rc, so
            # anything reaching here is structural (DB, attribute lookup
            # on a misshapen TrackedRepository row). Record ``False`` and
            # keep looping — one bad clone can't take the batch down.
            logger.warning(
                "origin_refresh_unhandled",
                org_id=str(org_id),
                repo_path=path,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            results[path] = False
    return results


async def refresh_origin_token_for_spawn(
    *,
    working_dir: str | None,
    org_id: uuid.UUID,
) -> bool:
    """Pre-spawn refresh for callers without a db session in scope.

    Same contract as :func:`refresh_origin_token` but opens its own
    short-lived ``AsyncSessionLocal`` and short-circuits when
    ``working_dir`` is ``None`` / empty (pure-LLM spawns have no clone
    to re-stamp). Used by chat, design, and scanner spawn sites that
    don't already carry a db session into the function.
    """
    if not working_dir:
        return False
    async with AsyncSessionLocal() as db:
        return await refresh_origin_token(
            working_dir=working_dir,
            org_id=org_id,
            db=db,
        )
